import os
import re
import subprocess
import tempfile
from datetime import datetime, timezone
from typing import Any
import sys
import shutil
from pathlib import Path


from bson import ObjectId
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.database.mongodb import get_database
from app.services.ai_service import generate_json, generate_text
from app.services.tester_service import _fallback_executable_tests, _fallback_test_cases
from app.utils.serialization import serialize_for_json


router = APIRouter(
    prefix="/api/projects",
    tags=["tester"],
)


class CustomTestCase(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    description: str = Field(min_length=1, max_length=2000)
    test_type: str = Field(default="FUNCTIONAL", max_length=50)
    priority: str = Field(default="MEDIUM", max_length=20)
    steps: list[str] = Field(default_factory=list)
    expected_result: str = Field(min_length=1, max_length=2000)


# ============================================================
# TEST PLAN SCHEMA
# ============================================================

TEST_PLAN_SCHEMA = {
    "type": "object",
    "properties": {
        "summary": {
            "type": "string"
        },
        "test_cases": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "test_id": {
                        "type": "string"
                    },
                    "title": {
                        "type": "string"
                    },
                    "description": {
                        "type": "string"
                    },
                    "type": {
                        "type": "string"
                    },
                    "priority": {
                        "type": "string"
                    },
                    "steps": {
                        "type": "array",
                        "items": {
                            "type": "string"
                        }
                    },
                    "expected_result": {
                        "type": "string"
                    }
                },
                "required": [
                    "test_id",
                    "title",
                    "description",
                    "type",
                    "priority",
                    "steps",
                    "expected_result"
                ]
            }
        }
    },
    "required": [
        "summary",
        "test_cases"
    ]
}


# ============================================================
# PROJECT FILE HELPERS
# ============================================================

IMPORTANT_FILENAMES = {
    "package.json",
    "package-lock.json",
    "requirements.txt",
    "pyproject.toml",
    "pom.xml",
    "build.gradle",
    "build.gradle.kts",
    "docker-compose.yml",
    "docker-compose.yaml",
    "vite.config.js",
    "vite.config.ts",
    "tsconfig.json",
    ".env.example",
}


def _normalize_path(path: str) -> str:
    return str(path or "").replace("\\", "/").strip()


def _is_important_file(path: str) -> bool:
    normalized = _normalize_path(path)
    filename = os.path.basename(normalized).lower()

    if filename in IMPORTANT_FILENAMES:
        return True

    return filename.endswith((".env", ".sql"))


def _build_files_text(
    developer_project: dict,
    max_file_chars: int = 8000,
) -> str:

    files = developer_project.get("files", []) or []

    parts = []

    for file_data in files:

        if not isinstance(file_data, dict):
            continue

        path = _normalize_path(
            file_data.get("path", "")
        )

        if not path:
            continue

        language = str(
            file_data.get("language", "")
        ).strip()

        content = str(
            file_data.get("content", "")
        )

        if _is_important_file(path):
            visible_content = content

        elif len(content) > max_file_chars:
            visible_content = (
                content[:max_file_chars]
                + "\n\n[FILE CONTENT TRUNCATED]"
            )

        else:
            visible_content = content

        parts.append(
            "============================================================\n"
            f"FILE PATH: {path}\n"
            f"LANGUAGE: {language}\n"
            "============================================================\n"
            f"{visible_content}\n"
        )

    return "\n".join(parts)


def _build_project_manifest(
    developer_project: dict,
) -> str:

    files = developer_project.get("files", []) or []

    paths = []

    for file_data in files:

        if not isinstance(file_data, dict):
            continue

        path = _normalize_path(
            file_data.get("path", "")
        )

        if path:
            paths.append(path)

    return "\n".join(
        f"- {path}"
        for path in sorted(set(paths))
    )


# ============================================================
# STACK DETECTION
# ============================================================

def _detect_project_stack(
    developer_project: dict,
) -> str:

    files = developer_project.get("files", []) or []

    paths = [
        _normalize_path(
            file_data.get("path", "")
        ).lower()
        for file_data in files
        if isinstance(file_data, dict)
    ]

    contents = [
        str(
            file_data.get("content", "")
        )
        for file_data in files
        if isinstance(file_data, dict)
    ]

    joined = "\n".join(contents).lower()

    # --------------------------------------------------------
    # Java
    # --------------------------------------------------------

    if any(
        path.endswith("pom.xml")
        for path in paths
    ):
        return "java-maven"

    if any(
        path.endswith("build.gradle")
        or path.endswith("build.gradle.kts")
        for path in paths
    ):
        return "java-gradle"

    # --------------------------------------------------------
    # Python
    # --------------------------------------------------------

    if any(
        path.endswith(".py")
        for path in paths
    ):

        if (
            "fastapi" in joined
            or "from fastapi" in joined
            or "import fastapi" in joined
        ):
            return "python-fastapi"

        if (
            "flask" in joined
            or "from flask" in joined
            or "import flask" in joined
        ):
            return "python-flask"

        if (
            "django" in joined
            or "from django" in joined
        ):
            return "python-django"

        return "python"

    # --------------------------------------------------------
    # Node / JavaScript / TypeScript
    # --------------------------------------------------------

    has_node_files = any(
        path.endswith(
            (
                ".js",
                ".jsx",
                ".ts",
                ".tsx",
                "package.json"
            )
        )
        for path in paths
    )

    if has_node_files:

        if (
            "express" in joined
            or "require('express')" in joined
            or 'require("express")' in joined
            or "from 'express'" in joined
            or 'from "express"' in joined
        ):
            return "node-express"

        if (
            "next/" in joined
            or "nextjs" in joined
            or '"next"' in joined
        ):
            return "nextjs"

        if (
            "react" in joined
            or "from 'react'" in joined
            or 'from "react"' in joined
        ):
            return "react"

        return "javascript"

    return "unknown"


# ============================================================
# SOURCE ANALYSIS
# ============================================================

def _extract_python_modules(
    developer_project: dict,
) -> list[str]:

    files = developer_project.get("files", []) or []

    modules = []

    for file_data in files:

        if not isinstance(file_data, dict):
            continue

        path = _normalize_path(
            file_data.get("path", "")
        )

        if not path.endswith(".py"):
            continue

        module_path = path[:-3]

        if module_path.endswith("/__init__"):
            module_path = module_path[:-9]

        module_path = module_path.replace("/", ".")

        if module_path.startswith("."):
            module_path = module_path[1:]

        if module_path:
            modules.append(module_path)

    return sorted(set(modules))


def _extract_python_imports(
    developer_project: dict,
) -> list[str]:

    files = developer_project.get("files", []) or []

    imports = set()

    patterns = [
        r"^\s*from\s+([A-Za-z_][\w.]*)\s+import",
        r"^\s*import\s+([A-Za-z_][\w.]*)",
    ]

    for file_data in files:

        if not isinstance(file_data, dict):
            continue

        content = str(
            file_data.get("content", "")
        )

        for line in content.splitlines():

            for pattern in patterns:

                match = re.search(
                    pattern,
                    line
                )

                if match:
                    imports.add(
                        match.group(1)
                    )

    return sorted(imports)


def _build_python_source_map(
    developer_project: dict,
) -> str:

    modules = _extract_python_modules(
        developer_project
    )

    imports = _extract_python_imports(
        developer_project
    )

    return (
        "ACTUAL PYTHON MODULES IN PROJECT:\n"
        + "\n".join(
            f"- {module}"
            for module in modules
        )
        + "\n\n"
        "IMPORTS FOUND IN PROJECT SOURCE:\n"
        + "\n".join(
            f"- {item}"
            for item in imports
        )
    )


# ============================================================
# CODE CLEANING
# ============================================================

def _clean_code_block(
    content: str,
) -> str:

    content = str(
        content or ""
    ).strip()

    if not content:
        return ""

    if content.startswith("```"):

        lines = content.splitlines()

        if lines:
            lines = lines[1:]

        if (
            lines
            and lines[-1].strip() == "```"
        ):
            lines = lines[:-1]

        content = "\n".join(lines)

    return content.strip()


# ============================================================
# TEST FILE PARSER
# ============================================================

def _parse_executable_test_files(
    raw_output: str,
) -> list[dict]:

    files = []

    if not raw_output:
        return files

    marker = "===TEST_FILE==="

    if marker not in raw_output:
        return files

    sections = raw_output.split(marker)

    for section in sections[1:]:

        if "===CONTENT===" not in section:
            continue

        header, content = section.split(
            "===CONTENT===",
            1
        )

        if "===END_TEST_FILE===" in content:

            content = content.split(
                "===END_TEST_FILE===",
                1
            )[0]

        path = ""
        test_ids = []

        for line in header.splitlines():

            line = line.strip()

            if line.startswith("PATH:"):

                path = line[
                    len("PATH:"):
                ].strip()

            elif line.startswith("TEST_IDS:"):

                ids_text = line[
                    len("TEST_IDS:"):
                ].strip()

                if ids_text:

                    test_ids = [
                        item.strip()
                        for item in ids_text.split(",")
                        if item.strip()
                    ]

        content = _clean_code_block(
            content
        )

        if not path or not content:
            continue

        normalized_path = _normalize_path(
            path
        )

        if (
            normalized_path.startswith("/")
            or normalized_path.startswith("../")
            or "/../" in normalized_path
            or normalized_path == ".."
        ):
            continue

        files.append(
            {
                "path": normalized_path,
                "content": content,
                "test_ids": test_ids,
            }
        )

    return files


# ============================================================
# TEST ID VALIDATION
# ============================================================

def _validate_test_ids(
    files: list[dict],
) -> list[str]:

    errors = []

    seen = set()

    for file_data in files:

        path = str(
            file_data.get(
                "path",
                ""
            )
        )

        test_ids = file_data.get(
            "test_ids",
            []
        )

        if not isinstance(
            test_ids,
            list
        ):

            errors.append(
                f"{path}: TEST_IDS must be a list"
            )

            continue

        if not test_ids:

            errors.append(
                f"{path}: missing TEST_IDS metadata"
            )

        for test_id in test_ids:

            test_id = str(test_id)

            if not re.fullmatch(
                r"AI-\d{3}",
                test_id
            ):

                errors.append(
                    f"{path}: invalid test ID {test_id}"
                )

            if test_id in seen:

                errors.append(
                    f"{path}: duplicate test ID {test_id}"
                )

            seen.add(
                test_id
            )

    return errors


# ============================================================
# EXECUTABLE TEST VALIDATION
# ============================================================

def _validate_executable_test_files(
    files: list[dict],
) -> list[str]:

    errors = []

    errors.extend(
        _validate_test_ids(files)
    )

    for file_data in files:

        path = str(
            file_data.get(
                "path",
                ""
            )
        )

        extension = os.path.splitext(
            path
        )[1].lower()

        content = str(
            file_data.get(
                "content",
                ""
            )
        )

        if extension not in {
            ".py",
            ".js",
            ".mjs",
            ".cjs",
        }:
            continue

        temporary_path = None

        try:

            suffix = extension

            with tempfile.NamedTemporaryFile(
                mode="w",
                suffix=suffix,
                encoding="utf-8",
                delete=False,
            ) as temporary_file:

                temporary_file.write(
                    content
                )

                temporary_path = (
                    temporary_file.name
                )

            if extension == ".py":

                command = [
                    "python",
                    "-m",
                    "py_compile",
                    temporary_path,
                ]

            else:

                command = [
                    "node",
                    "--check",
                    temporary_path,
                ]

            result = subprocess.run(
                command,
                capture_output=True,
                text=True,
                timeout=20,
                shell=False,
            )

            if result.returncode != 0:

                message = (
                    result.stderr
                    or result.stdout
                    or "Unknown syntax error"
                ).strip()

                errors.append(
                    f"{path}: {message[-1000:]}"
                )

        except (
            OSError,
            subprocess.TimeoutExpired,
        ) as exc:

            errors.append(
                f"{path}: syntax validation failed: {exc}"
            )

        finally:

            if temporary_path:

                try:
                    os.unlink(
                        temporary_path
                    )
                except OSError:
                    pass

    return errors


# ============================================================
# GENERATE TEST PLAN
# ============================================================

def generate_test_plan(
    project: dict,
    requirements: dict,
    architecture: dict,
    developer_project: dict,
):

    files_text = _build_files_text(
        developer_project,
        max_file_chars=7000,
    )

    manifest = _build_project_manifest(
        developer_project
    )

    prompt = f"""
You are the Tester Agent in SmartDevAgents.

Create a practical test plan for the ACTUAL generated project.

PROJECT:
{project.get("name", "")}

DESCRIPTION:
{project.get("description", "")}

REQUIREMENTS:
{requirements}

ARCHITECTURE:
{architecture}

ACTUAL FILE MANIFEST:
{manifest}

ACTUAL SOURCE CODE:
{files_text}

RULES:

1. Test only functionality that actually exists.

2. Do not assume filenames.

3. Do not invent modules.

4. Do not invent endpoints.

5. Do not invent database tables.

6. Do not invent functions or classes.

7. Do not invent authentication.

8. Use the actual generated source as the source of truth.

9. Cover authentication, authorization, validation, persistence,
   API behavior and core functionality only when implemented.

10. Generate between 8 and 15 meaningful tests.

11. Every test must have a unique ID:

AI-001
AI-002
AI-003

12. Return ONLY valid JSON.

Each test case must contain:

test_id
title
description
type
priority
steps
expected_result
"""

    return generate_json(
        prompt,
        schema=TEST_PLAN_SCHEMA,
    )


# ============================================================
# GENERATE EXECUTABLE TESTS
# ============================================================

def generate_executable_tests(
    project: dict,
    requirements: dict,
    architecture: dict,
    developer_project: dict,
    test_cases: list,
):

    stack = _detect_project_stack(
        developer_project
    )

    files_text = _build_files_text(
        developer_project,
        max_file_chars=8000,
    )

    manifest = _build_project_manifest(
        developer_project
    )

    python_source_map = (
        _build_python_source_map(
            developer_project
        )
        if stack.startswith("python")
        else ""
    )

    # --------------------------------------------------------
    # NORMALIZE TEST CASES
    # --------------------------------------------------------

    normalized_test_cases = []

    for index, test in enumerate(
        test_cases or [],
        start=1,
    ):

        if not isinstance(
            test,
            dict
        ):
            continue

        test_copy = dict(test)

        test_copy["test_id"] = (
            test_copy.get("test_id")
            or f"AI-{index:03d}"
        )

        normalized_test_cases.append(
            test_copy
        )

    test_cases_text = "\n\n".join(
        f"""
TEST ID: {test.get("test_id")}
TITLE: {test.get("title", "")}
TYPE: {test.get("type", "")}
PRIORITY: {test.get("priority", "")}
DESCRIPTION: {test.get("description", "")}
STEPS: {" | ".join(
    str(step)
    for step in test.get("steps", [])
)}
EXPECTED: {test.get("expected_result", "")}
"""
        for test in normalized_test_cases
    )

    # --------------------------------------------------------
    # FRAMEWORK SELECTION
    # --------------------------------------------------------

    if stack == "python-fastapi":

        framework_instructions = """
Use pytest.

Use FastAPI TestClient when possible.

Find the ACTUAL FastAPI app object from the project.

Do NOT assume app.main exists.

Do NOT assume database.py exists.

Do NOT assume models.py exists.

Do NOT assume schemas.py exists.

Do NOT assume middleware.py exists.

Import only modules and symbols that actually exist.

Do not require a running production server.
"""

        extension = ".py"

    elif stack == "python-flask":

        framework_instructions = """
Use pytest.

Find the ACTUAL Flask application in the generated source.

Do not assume app.py or main.py.

Use Flask test_client when appropriate.

Use only actual routes and application objects.
"""

        extension = ".py"

    elif stack == "python-django":

        framework_instructions = """
Use pytest and the Django testing facilities already present.

Inspect the actual settings, URLs, applications and models.

Do not invent Django applications or models.
"""

        extension = ".py"

    elif stack == "python":

        framework_instructions = """
Use pytest.

Import only actual Python modules from the manifest.

Import only actual functions/classes found in source.

Every standard-library object must be explicitly imported.

Never use undefined names such as:

Path
ast
importlib
json
os
sys
re
tempfile

without imports.

Do not invent project modules.
"""

        extension = ".py"

    elif stack == "node-express":

        framework_instructions = """
Use the Node.js built-in test runner whenever possible:

node:test
node:assert

DO NOT add new npm dependencies.

DO NOT use supertest unless supertest is ALREADY present in the
actual package.json.

DO NOT use jest unless jest is ALREADY present in package.json.

DO NOT use mocha unless mocha is ALREADY present in package.json.

Inspect package.json before selecting the framework.

For Express applications:

1. Find the actual exported Express app.
2. Find the actual route paths.
3. Find the actual HTTP methods.
4. Find the actual request and response format.
5. Use only existing exports.
6. Never assume app.js, server.js or index.js.
7. Never invent database modules.
8. Never invent routes.

If the actual application exports an Express app, prefer testing it
without starting a production server.

If the app does not export an app object, test only actual exported
functions/services that can safely be tested.

IMPORTANT:
Do not install any additional package.
Do not create a new package.json.
Do not modify the application's dependencies.
"""

        extension = ".test.js"

    elif stack in {
        "javascript",
        "react",
        "nextjs",
    }:

        framework_instructions = """
Inspect package.json.

Use ONLY the test framework already installed in the project.

Do not add dependencies.

Do not invent components, functions, hooks or routes.

Use only actual exported code.
"""

        extension = ".test.js"

    elif stack == "java-maven":

        framework_instructions = """
Inspect pom.xml.

Use the testing framework already declared there.

Prefer JUnit when available.

Import only actual classes and packages.
"""

        extension = ".java"

    elif stack == "java-gradle":

        framework_instructions = """
Inspect build.gradle or build.gradle.kts.

Use the testing framework already declared.

Do not invent packages or classes.
"""

        extension = ".java"

    else:

        framework_instructions = """
Inspect the actual project.

Use the existing test framework if one exists.

Do not invent APIs, modules, packages or application behavior.
"""

        extension = ".test"

    # --------------------------------------------------------
    # MASTER PROMPT
    # --------------------------------------------------------

    prompt = f"""
You are the Automated Testing Engineer in SmartDevAgents.

Generate REAL executable automated tests for the ACTUAL project.

============================================================
PROJECT
============================================================

Name:
{project.get("name", "")}

Description:
{project.get("description", "")}

============================================================
STACK
============================================================

{stack}

============================================================
REQUIREMENTS
============================================================

{requirements}

============================================================
ARCHITECTURE
============================================================

{architecture}

============================================================
ACTUAL FILE MANIFEST
============================================================

{manifest}

============================================================
ACTUAL PROJECT SOURCE
============================================================

{files_text}

============================================================
PYTHON SOURCE MAP
============================================================

{python_source_map}

============================================================
TEST CASES
============================================================

{test_cases_text}

============================================================
TEST FRAMEWORK
============================================================

{framework_instructions}

============================================================
NON-NEGOTIABLE RULES
============================================================

1. Generated tests will actually be executed.

2. Use only files that exist.

3. Use only functions/classes/routes/components that exist.

4. Never invent:

database.py
models.py
schemas.py
middleware.py
auth.py
services.py
config.py
app.py
main.py
server.js
index.js

unless the exact file exists.

5. Never invent an import.

6. Every imported project module must exist in the manifest.

7. Every imported symbol must exist in the source.

8. Every Python standard-library symbol must have its import.

9. Never use undefined variables.

10. Never use undefined functions.

11. Never use undefined fixtures.

12. Never use packages that are not already declared.

13. NEVER add npm packages.

14. NEVER generate package.json.

15. NEVER generate package-lock.json.

16. NEVER modify dependencies.

17. NEVER use supertest unless package.json already contains it.

18. NEVER use jest unless package.json already contains it.

19. NEVER use mocha unless package.json already contains it.

20. For Node/Express, prefer node:test and node:assert because they
    are built into Node.js.

21. Do not require a production database.

22. Do not require paid external services.

23. Do not require browser automation.

24. Keep tests deterministic.

25. Do not create fake application implementations.

26. Do not monkeypatch nonexistent modules.

27. Do not monkeypatch nonexistent functions.

28. Do not invent database schemas.

29. Do not invent authentication behavior.

30. If a requirement is not actually implemented, omit its executable
    test instead of creating fake behavior.

31. Generate maximum 3 test files.

32. Prefer one test file.

33. Every test ID must appear exactly once.

34. Every test ID must correspond to one test function.

35. Use names such as:

test_ai_001_registration()

test_ai_002_login()

36. Do not combine multiple AI IDs into one test function.

37. Do not generate markdown.

38. Do not generate explanations.

39. Do not generate pseudocode.

40. Do not generate TODOs.

41. Do not use "...".

42. Close every function, class, object, array, parenthesis,
    string and syntax structure.

43. Generated code must be syntactically valid.

44. Do not use absolute machine-specific paths.

45. Do not depend on the current working directory.

46. Keep the test environment lightweight.

47. Do not add unnecessary dependencies.

48. Do not create fake routes.

49. Do not create fake database connections.

50. Do not claim a test exists if it was not generated.

============================================================
NODE/EXPRESS SPECIAL RULE
============================================================

If the project is node-express:

Use Node's built-in testing tools whenever possible.

Allowed:

node:test
node:assert
node:http

Do not add:

supertest
jest
mocha
chai
axios

unless the actual package.json already contains them.

The test must work with the dependencies already installed by the
generated project.

============================================================
OUTPUT FORMAT
============================================================

Return ONLY test files.

Use exactly:

===TEST_FILE===
PATH: tests/example{extension}
TEST_IDS: AI-001, AI-002
===CONTENT===
actual executable source code
===END_TEST_FILE===

Rules:

- Relative paths only.
- Maximum 3 files.
- Prefer tests/.
- No JSON.
- No markdown fences.
- No explanations.
- TEST_IDS must match actual test functions.
- Every ID must appear exactly once.
"""

    # --------------------------------------------------------
    # FIRST GENERATION
    # --------------------------------------------------------

    try:
        raw_output = generate_text(prompt)
    except Exception as exc:
        print(f"[Tester] LLM executable-test generation failed; using deterministic fallback: {exc}")
        executable_files = _fallback_executable_tests(
            developer_project,
            normalized_test_cases,
            stack,
        )
        return {
            "test_files": executable_files,
            "validation_errors": _validate_executable_test_files(executable_files),
            "manual_test_ids": [],
        }

    executable_files = (
        _parse_executable_test_files(
            raw_output
        )
    )

    expected_ids = {
        str(
            test.get("test_id")
        )
        for test in normalized_test_cases
        if test.get("test_id")
    }

    generated_ids = {
        str(test_id)
        for file_data in executable_files
        for test_id in file_data.get(
            "test_ids",
            []
        )
    }

    validation_errors = (
        _validate_executable_test_files(
            executable_files
        )
    )

    skipped_ids = sorted(
        expected_ids - generated_ids
    )

    if skipped_ids:

        print(
            "[Tester] Manual-only tests: "
            + ", ".join(skipped_ids)
        )

    # --------------------------------------------------------
    # REPAIR LOOP
    # --------------------------------------------------------

    max_repairs = 2

    for repair_number in range(
        max_repairs
    ):

        if not validation_errors:
            break

        print(
            f"[Tester] Validation failed. "
            f"Repair attempt {repair_number + 1}/"
            f"{max_repairs}"
        )

        repair_prompt = f"""
You generated automated tests for a real project.

The generated test files failed validation.

============================================================
PROJECT MANIFEST
============================================================

{manifest}

============================================================
STACK
============================================================

{stack}

============================================================
VALIDATION ERRORS
============================================================

{chr(10).join(validation_errors[:30])}

============================================================
REPAIR REQUIREMENTS
============================================================

Regenerate the COMPLETE affected test files.

You MUST:

1. Use only files in the project manifest.

2. Use only symbols actually defined in source.

3. Import every standard-library symbol explicitly.

4. Never use undefined names.

5. Never invent project modules.

6. Never invent packages.

7. Never install packages.

8. Never add npm dependencies.

9. Never use supertest unless already present.

10. Never use jest unless already present.

11. Never use mocha unless already present.

12. For Node/Express, prefer node:test and node:assert.

13. Keep tests deterministic.

14. Keep every AI test ID unique.

15. Every test ID must appear exactly once.

16. The files must be syntactically valid.

17. Do not generate package.json.

18. Do not generate package-lock.json.

19. Do not generate dependencies.

20. Return only corrected test files.

============================================================
ORIGINAL REQUIREMENTS
============================================================

{prompt}

============================================================
OUTPUT
============================================================

===TEST_FILE===
PATH: tests/example{extension}
TEST_IDS: AI-001
===CONTENT===
actual executable source
===END_TEST_FILE===
"""

        try:
            raw_output = generate_text(repair_prompt)
        except Exception as exc:
            print(f"[Tester] LLM test repair failed; using deterministic fallback: {exc}")
            executable_files = _fallback_executable_tests(
                developer_project,
                normalized_test_cases,
                stack,
            )
            validation_errors = _validate_executable_test_files(executable_files)
            break

        executable_files = (
            _parse_executable_test_files(
                raw_output
            )
        )

        validation_errors = (
            _validate_executable_test_files(
                executable_files
            )
        )

    # --------------------------------------------------------
    # FINAL VALIDATION
    # --------------------------------------------------------

    if validation_errors:

        print(
            "[Tester] Rejected invalid executable tests:"
        )

        for error in validation_errors[:30]:

            print(
                f"[Tester] {error}"
            )

        print(
            "[Tester] Raw response:"
        )

        print(
            raw_output[:5000]
        )

        return {
            "test_files": [],
            "validation_errors": validation_errors,
        }

    # --------------------------------------------------------
    # NO TESTS
    # --------------------------------------------------------

    if not executable_files:
        print(
            "[Tester] No safe executable tests were generated; using deterministic project-integrity suite."
        )
        executable_files = _fallback_executable_tests(
            developer_project,
            normalized_test_cases,
            stack,
        )
        validation_errors = _validate_executable_test_files(executable_files)

        if not executable_files:
            print(
                "[Tester] No safe executable tests "
                "were generated."
            )

            return {
                "test_files": [],
                "validation_errors": [],
                "manual_test_ids": sorted(
                    expected_ids
                ),
            }

        print(
            "[Tester] Deterministic integrity suite generated successfully."
        )

    # --------------------------------------------------------
    # FINAL TEST ID CHECK
    # --------------------------------------------------------

    generated_ids = {
        str(test_id)
        for file_data in executable_files
        for test_id in file_data.get(
            "test_ids",
            []
        )
    }

    skipped_ids = sorted(
        expected_ids - generated_ids
    )

    if skipped_ids:

        print(
            "[Tester] Some tests remain manual-only: "
            + ", ".join(skipped_ids)
        )

    print(
        "[Tester] Parsed "
        f"{len(executable_files)} "
        "executable test file(s)."
    )

    return {
        "test_files": executable_files,
        "validation_errors": [],
        "manual_test_ids": skipped_ids,
    }


# ============================================================
# TESTER API ROUTES
# ============================================================

def _get_project(db, project_id: str):

    try:
        object_id = ObjectId(project_id)
    except Exception:
        raise HTTPException(
            status_code=400,
            detail="Invalid project ID.",
        )

    project = db.projects.find_one(
        {"_id": object_id}
    )

    if not project:
        raise HTTPException(
            status_code=404,
            detail="Project not found.",
        )

    return project


@router.post("/{project_id}/tester/generate")
def generate_tester_project(
    project_id: str,
):

    db = get_database()

    project = _get_project(
        db,
        project_id,
    )

    requirements = db.requirements.find_one(
        {"project_id": project_id}
    )

    if not requirements:
        raise HTTPException(
            status_code=400,
            detail="Requirements are required before testing.",
        )

    architecture = db.architectures.find_one(
        {"project_id": project_id},
        sort=[("created_at", -1)],
    )

    if not architecture:
        raise HTTPException(
            status_code=400,
            detail="Architecture is required before testing.",
        )

    developer_project = db.developer_projects.find_one(
        {"project_id": project_id},
        sort=[("version", -1)],
    )

    if not developer_project:
        raise HTTPException(
            status_code=400,
            detail="Developer project is required before testing.",
        )

    now = datetime.now(timezone.utc)

    db.agent_activity.insert_one({
        "project_id": project_id,
        "agent": "TESTER",
        "event": "TESTER_GENERATION_STARTED",
        "message": "Tester Agent started generating the test plan.",
        "created_at": now,
    })

    db.projects.update_one(
        {"_id": ObjectId(project_id)},
        {
            "$set": {
                "status": "TESTER_GENERATING",
                "current_agent": "TESTER",
                "updated_at": now,
            }
        },
    )

    try:

        # ----------------------------------------------------
        # STEP 1: Generate test plan
        # ----------------------------------------------------

        print(
            "[Tester] Generating test plan..."
        )

        try:
            test_plan = generate_test_plan(
                project,
                serialize_for_json(requirements),
                serialize_for_json(architecture),
                serialize_for_json(developer_project),
            )
        except Exception as exc:
            print(f"[Tester] LLM test-plan generation failed; using deterministic fallback: {exc}")
            test_plan = {
                "summary": "Deterministic project integrity and runtime checks.",
                "test_cases": _fallback_test_cases(developer_project),
            }

        if not isinstance(
            test_plan,
            dict
        ):
            raise ValueError(
                "Tester returned an invalid test plan."
            )

        test_cases = test_plan.get(
            "test_cases",
            []
        )
        normalized_cases = []
        for index, test_case in enumerate(test_cases, start=1):
            if not isinstance(test_case, dict):
                continue
            item = dict(test_case)
            item["test_id"] = str(item.get("test_id") or f"AI-{index:03d}")
            item["source"] = item.get("source") or "AI"
            normalized_cases.append(item)
        test_cases = normalized_cases

        print(
            f"[Tester] Generated "
            f"{len(test_cases)} test cases."
        )

        db.agent_activity.insert_one({
            "project_id": project_id,
            "agent": "TESTER",
            "event": "TEST_PLAN_CREATED",
            "message": (
                f"Tester created {len(test_cases)} test cases."
            ),
            "created_at": datetime.now(timezone.utc),
        })

        # ----------------------------------------------------
        # STEP 2: Generate executable tests
        # ----------------------------------------------------

        print(
            "[Tester] Generating executable tests..."
        )

        executable_result = generate_executable_tests(
            project,
            serialize_for_json(requirements),
            serialize_for_json(architecture),
            serialize_for_json(developer_project),
            test_cases,
        )

        test_files = executable_result.get(
            "test_files",
            []
        )

        validation_errors = executable_result.get(
            "validation_errors",
            []
        )

        manual_test_ids = executable_result.get(
            "manual_test_ids",
            []
        )

        print(
            f"[Tester] Generated "
            f"{len(test_files)} executable test file(s)."
        )

        # ----------------------------------------------------
        # STEP 3: Determine version
        # ----------------------------------------------------

        latest = db.tester_runs.find_one(
            {"project_id": project_id},
            sort=[("version", -1)],
        )

        version = 1

        if latest:
            version = latest.get(
                "version",
                0
            ) + 1

        # ----------------------------------------------------
        # STEP 4: Save Tester result
        # ----------------------------------------------------

        tester_document = {
            "project_id": project_id,
            "version": version,
            "developer_version": developer_project.get(
                "version",
                1,
            ),
            "summary": test_plan.get(
                "summary",
                "",
            ),
            "test_cases": test_cases,
            "test_files": test_files,
            "manual_test_ids": manual_test_ids,
            "validation_errors": validation_errors,
            "stack": _detect_project_stack(
                developer_project
            ),
            "created_at": datetime.now(timezone.utc),
        }

        result = db.tester_runs.insert_one(
            tester_document
        )

        tester_document["_id"] = result.inserted_id

        # ----------------------------------------------------
        # STEP 5: Update project status
        # ----------------------------------------------------

        db.projects.update_one(
            {"_id": ObjectId(project_id)},
            {
                "$set": {
                    "status": "TESTER_READY",
                    "current_agent": "TESTER",
                    "updated_at": datetime.now(timezone.utc),
                }
            },
        )

        db.agent_activity.insert_one({
            "project_id": project_id,
            "agent": "TESTER",
            "event": "TESTER_GENERATION_COMPLETED",
            "message": (
                f"Tester generated version {version} with "
                f"{len(test_cases)} test cases and "
                f"{len(test_files)} executable test file(s)."
            ),
            "created_at": datetime.now(timezone.utc),
        })

        print(
            "[Tester] Generation completed successfully."
        )

        return serialize_for_json(
            tester_document
        )

    except HTTPException:
        raise

    except Exception as exc:

        import traceback

        print(
            "\n========== TESTER GENERATION ERROR =========="
        )
        print(
            str(exc)
        )
        traceback.print_exc()
        print(
            "===============================================\n"
        )

        db.agent_activity.insert_one({
            "project_id": project_id,
            "agent": "TESTER",
            "event": "TESTER_GENERATION_FAILED",
            "message": str(exc),
            "created_at": datetime.now(timezone.utc),
        })

        db.projects.update_one(
            {"_id": ObjectId(project_id)},
            {
                "$set": {
                    "status": "TESTER_GENERATION_FAILED",
                    "current_agent": "TESTER",
                    "updated_at": datetime.now(timezone.utc),
                }
            },
        )

        raise HTTPException(
            status_code=502,
            detail=str(exc),
        )


@router.post("/{project_id}/tester/custom")
def add_custom_test(project_id: str, payload: CustomTestCase):
    """Append a human-authored test case to the latest Tester run."""
    db = get_database()
    _get_project(db, project_id)
    tester_run = db.tester_runs.find_one({"project_id": project_id}, sort=[("version", -1)])
    if not tester_run:
        raise HTTPException(status_code=400, detail="Generate the Tester test plan before adding a custom test.")

    existing = tester_run.get("test_cases", []) or []
    next_number = 1
    used = {str(item.get("test_id")) for item in existing if isinstance(item, dict)}
    while f"CUSTOM-{next_number:03d}" in used:
        next_number += 1
    test_case = {
        "test_id": f"CUSTOM-{next_number:03d}",
        "title": payload.title.strip(),
        "description": payload.description.strip(),
        "type": payload.test_type.strip().upper(),
        "priority": payload.priority.strip().upper(),
        "steps": [step.strip() for step in payload.steps if step.strip()],
        "expected_result": payload.expected_result.strip(),
        "source": "USER",
        "status": "MANUAL",
    }
    existing.append(test_case)
    now = datetime.now(timezone.utc)
    db.tester_runs.update_one({"_id": tester_run["_id"]}, {"$set": {"test_cases": existing, "updated_at": now}})
    db.agent_activity.insert_one({"project_id": project_id, "agent": "HUMAN", "event": "CUSTOM_TEST_ADDED", "message": f"Human added custom test {test_case['test_id']}.", "created_at": now})
    tester_run["test_cases"] = existing
    tester_run["updated_at"] = now
    return serialize_for_json(tester_run)



@router.post("/{project_id}/tester/approve")
def approve_tester_results(project_id: str):
    """Approve the latest test execution only when the complete suite passed."""
    db = get_database()
    project = _get_project(db, project_id)
    tester_run = db.tester_runs.find_one({"project_id": project_id}, sort=[("version", -1)])
    if not tester_run:
        raise HTTPException(status_code=400, detail="Generate and run the Tester suite before approving it.")

    execution = tester_run.get("execution") or {}
    passed = int(tester_run.get("passed_count", 0) or 0)
    failed = int(tester_run.get("failed_count", 0) or 0)
    errors = int(tester_run.get("error_count", 0) or 0)
    not_executable = int(tester_run.get("not_executable_count", 0) or 0)
    if execution.get("status") != "PASSED" or passed <= 0 or failed or errors or not_executable:
        raise HTTPException(
            status_code=400,
            detail=(
                "All executable tests must pass before approval. "
                f"Passed={passed}, Failed={failed}, Errors={errors}, Not executable={not_executable}."
            ),
        )

    now = datetime.now(timezone.utc)
    db.tester_runs.update_one(
        {"_id": tester_run["_id"]},
        {"$set": {"approval_status": "APPROVED", "approved_at": now, "updated_at": now}},
    )
    db.projects.update_one(
        {"_id": ObjectId(project_id)},
        {"$set": {"status": "TESTS_APPROVED", "current_agent": "REVIEWER", "updated_at": now}},
    )
    db.agent_activity.insert_one({
        "project_id": project_id,
        "agent": "HUMAN",
        "event": "TESTS_APPROVED",
        "message": "Human approved the passing Tester suite. Reviewer can continue.",
        "created_at": now,
    })
    return {"status": "TESTS_APPROVED", "current_agent": "REVIEWER", "version": tester_run.get("version")}

@router.get("/{project_id}/tester")
def get_tester_result(
    project_id: str,
):

    db = get_database()

    _get_project(
        db,
        project_id,
    )

    tester_run = db.tester_runs.find_one(
        {"project_id": project_id},
        sort=[("version", -1)],
    )

    if not tester_run:
        return {
            "status": "NOT_GENERATED"
        }

    return serialize_for_json(
        tester_run
    )
def _get_venv_python(venv_root: str) -> str:
    """
    Return the Python executable inside a virtual environment.

    Works on:
    - Windows
    - Linux
    - macOS

    Raises FileNotFoundError if the virtual environment
    does not contain a Python executable.
    """

    venv_root = os.path.abspath(venv_root)

    if os.name == "nt":
        candidates = [
            os.path.join(
                venv_root,
                "Scripts",
                "python.exe",
            ),
            os.path.join(
                venv_root,
                "Scripts",
                "python",
            ),
        ]

    else:
        candidates = [
            os.path.join(
                venv_root,
                "bin",
                "python",
            ),
            os.path.join(
                venv_root,
                "bin",
                "python3",
            ),
        ]

    for candidate in candidates:
        if os.path.isfile(candidate):
            return candidate

    raise FileNotFoundError(
        "Python executable was not found inside virtual "
        f"environment: {venv_root}"
    )
@router.post("/{project_id}/tester/run")
def run_tester_tests(project_id: str):
    """
    Execute Tester-generated tests against an isolated copy of the
    ACTUAL Developer-generated project.

    This runner is intentionally project-agnostic.

    It does NOT assume:
        - to_do_list
        - FoodExpress
        - server.js
        - app.js
        - main.py
        - database.py
        - models.py
        - schemas.py
        - any specific framework

    Instead it reconstructs the Developer Agent's project from
    MongoDB and executes the Tester files inside that project root.
    """

    db = get_database()

    # =========================================================
    # 1. VERIFY PROJECT
    # =========================================================

    project = _get_project(
        db,
        project_id,
    )

    # Latest Tester generation
    tester_run = db.tester_runs.find_one(
        {"project_id": project_id},
        sort=[("version", -1)],
    )

    if not tester_run:
        raise HTTPException(
            status_code=400,
            detail="Generate tester project before running tests.",
        )

    test_files = tester_run.get(
        "test_files",
        [],
    )

    # Refresh only the main app's deterministic fallback suite when an older
    # tester run still stores a pre-versioned integrity test. AI-generated
    # suites and the generated project itself are left unchanged.
    stale_fallback = any(
        isinstance(test_file, dict)
        and _normalize_path(test_file.get("path", ""))
        == "tests/project_integrity_test.py"
        and "SMARTDEVAGENTS_INTEGRITY_SUITE_V3"
        not in str(test_file.get("content", ""))
        for test_file in test_files
    )

    if not test_files or stale_fallback:
        developer_project = db.developer_projects.find_one(
            {"project_id": project_id},
            sort=[("version", -1)],
        )
        if developer_project:
            stack = _detect_project_stack(developer_project)
            fallback_files = _fallback_executable_tests(
                developer_project,
                tester_run.get("test_cases", []) or [],
                stack,
            )
            if fallback_files:
                now = datetime.now(timezone.utc)
                db.tester_runs.update_one(
                    {"_id": tester_run["_id"]},
                    {"$set": {"test_files": fallback_files, "updated_at": now}},
                )
                tester_run["test_files"] = fallback_files
                test_files = fallback_files

    if not test_files:
        now = datetime.now(timezone.utc)

        execution = {
            "status": "NO_EXECUTABLE_TESTS",
            "framework": "N/A",
            "command": "N/A",
            "exit_code": None,
            "output": "No executable test files were generated.",
            "results": [],
            "executed_at": now,
        }

        db.tester_runs.update_one(
            {"_id": tester_run["_id"]},
            {
                "$set": {
                    "execution": execution,
                    "passed_count": 0,
                    "failed_count": 0,
                    "error_count": 0,
                    "not_executable_count": 0,
                    "passed": 0,
                    "failed": 0,
                    "updated_at": now,
                }
            },
        )

        return {
            "status": "NO_EXECUTABLE_TESTS",
            "passed": 0,
            "failed": 0,
            "passed_count": 0,
            "failed_count": 0,
            "error_count": 0,
            "not_executable_count": 0,
            "results": [],
            "execution": execution,
        }

    # =========================================================
    # 2. GET ACTUAL DEVELOPER PROJECT
    # =========================================================

    developer_project = db.developer_projects.find_one(
        {"project_id": project_id},
        sort=[("version", -1)],
    )

    if not developer_project:
        raise HTTPException(
            status_code=400,
            detail="Developer project is required before running tests.",
        )

    developer_files = developer_project.get(
        "files",
        [],
    )

    if not developer_files:
        raise HTTPException(
            status_code=400,
            detail="Developer project contains no files.",
        )

    # =========================================================
    # 3. HELPERS
    # =========================================================

    def normalize_relative_path(path: str) -> str:
        """
        Normalize a generated project path and prevent path traversal.
        """
        path = str(path or "").strip()

        path = path.replace("\\", "/")

        while path.startswith("./"):
            path = path[2:]

        # Reject absolute Windows paths.
        if re.match(r"^[A-Za-z]:/", path):
            raise ValueError(
                f"Absolute path is not allowed: {path}"
            )

        if path.startswith("/"):
            raise ValueError(
                f"Absolute path is not allowed: {path}"
            )

        normalized = os.path.normpath(path)

        if normalized in {
            "",
            ".",
            "..",
        }:
            raise ValueError(
                f"Invalid project path: {path}"
            )

        if normalized.startswith(
            ".." + os.sep
        ) or normalized == "..":
            raise ValueError(
                f"Path traversal is not allowed: {path}"
            )

        return normalized

    def write_project_file(
        project_root: str,
        relative_path: str,
        content: str,
    ):
        """
        Safely write one generated project file.
        """

        safe_path = normalize_relative_path(
            relative_path
        )

        destination = os.path.abspath(
            os.path.join(
                project_root,
                safe_path,
            )
        )

        root = os.path.abspath(
            project_root
        )

        # Extra safety check.
        if (
            destination != root
            and not destination.startswith(
                root + os.sep
            )
        ):
            raise ValueError(
                f"Unsafe file path: {relative_path}"
            )

        os.makedirs(
            os.path.dirname(destination),
            exist_ok=True,
        )

        normalized_content = str(content or "").strip()
        content_lines = normalized_content.splitlines()
        if content_lines and content_lines[0].strip().startswith("```"):
            content_lines = content_lines[1:]
        if content_lines and content_lines[-1].strip() == "```":
            content_lines = content_lines[:-1]
        normalized_content = "\n".join(content_lines).strip()

        with open(
            destination,
            "w",
            encoding="utf-8",
        ) as file:
            file.write(
                normalized_content
            )

        return destination

    def find_file(
        files: list,
        names: set[str],
    ):
        """
        Find a project file by basename.
        """
        for file_data in files:

            if not isinstance(
                file_data,
                dict,
            ):
                continue

            path = _normalize_path(
                file_data.get(
                    "path",
                    "",
                )
            )

            filename = os.path.basename(
                path
            ).lower()

            if filename in names:
                return file_data

        return None

    def has_file(
        files: list,
        filename: str,
    ) -> bool:
        return (
            find_file(
                files,
                {filename.lower()},
            )
            is not None
        )

    # =========================================================
    # 4. DETECT STACK FROM ACTUAL PROJECT
    # =========================================================

    stack = _detect_project_stack(
        developer_project
    )

    # =========================================================
    # 5. CREATE ISOLATED PROJECT DIRECTORY
    # =========================================================

    project_root = tempfile.mkdtemp(
        prefix="smartdevagents_test_"
    )

    results = []

    passed_count = 0
    failed_count = 0
    error_count = 0
    not_executable_count = 0

    output_parts = []
    commands_used = []
    frameworks_used = []

    try:

        # =====================================================
        # 6. RECREATE DEVELOPER PROJECT
        # =====================================================

        for file_data in developer_files:

            if not isinstance(
                file_data,
                dict,
            ):
                continue

            original_path = _normalize_path(
                file_data.get(
                    "path",
                    "",
                )
            )

            content = str(
                file_data.get(
                    "content",
                    "",
                )
            )

            if not original_path:
                continue

            try:
                write_project_file(
                    project_root,
                    original_path,
                    content,
                )

            except Exception as exc:

                raise HTTPException(
                    status_code=500,
                    detail=(
                        "Could not reconstruct generated "
                        f"project file '{original_path}': {exc}"
                    ),
                )

        # =====================================================
        # 7. WRITE TEST FILES INTO PROJECT
        # =====================================================

        executable_test_paths = []

        for index, test_file in enumerate(
            test_files,
            start=1,
        ):

            if not isinstance(
                test_file,
                dict,
            ):
                not_executable_count += 1

                results.append(
                    {
                        "test_id": "UNKNOWN",
                        "title": "Invalid test file",
                        "path": "",
                        "status": "NOT_EXECUTABLE",
                        "message": "Test file metadata is invalid.",
                    }
                )

                continue

            relative_test_path = _normalize_path(
                test_file.get(
                    "path",
                    "",
                )
            )

            content = str(
                test_file.get(
                    "content",
                    "",
                )
            )

            if not relative_test_path:
                not_executable_count += 1

                results.append(
                    {
                        "test_id": test_file.get(
                            "test_id",
                            "UNKNOWN",
                        ),
                        "title": test_file.get(
                            "title",
                            "Unknown test",
                        ),
                        "path": "",
                        "status": "NOT_EXECUTABLE",
                        "message": "Test file path is missing.",
                    }
                )

                continue

            if not content.strip():
                not_executable_count += 1

                results.append(
                    {
                        "test_id": test_file.get(
                            "test_id",
                            "UNKNOWN",
                        ),
                        "title": test_file.get(
                            "title",
                            relative_test_path,
                        ),
                        "path": relative_test_path,
                        "status": "NOT_EXECUTABLE",
                        "message": "Test file content is empty.",
                    }
                )

                continue

            try:

                written_test_path = write_project_file(
                    project_root,
                    relative_test_path,
                    content,
                )

                executable_test_paths.append(
                    {
                        "metadata": test_file,
                        "path": written_test_path,
                        "relative_path": relative_test_path,
                    }
                )

            except Exception as exc:

                not_executable_count += 1

                results.append(
                    {
                        "test_id": test_file.get(
                            "test_id",
                            "UNKNOWN",
                        ),
                        "title": test_file.get(
                            "title",
                            relative_test_path,
                        ),
                        "path": relative_test_path,
                        "status": "NOT_EXECUTABLE",
                        "message": str(exc),
                    }
                )

        # =====================================================
        # 8. INSTALL PROJECT DEPENDENCIES
        # =====================================================

        dependency_commands = []

        package_json = find_file(
            developer_files,
            {"package.json"},
        )

        requirements_file = find_file(
            developer_files,
            {
                "requirements.txt",
            },
        )

        pyproject_file = find_file(
            developer_files,
            {
                "pyproject.toml",
            },
        )

        pom_file = find_file(
            developer_files,
            {
                "pom.xml",
            },
        )

        package_lock = find_file(
            developer_files,
            {
                "package-lock.json",
            },
        )

        # -----------------------------------------------------
        # Node / JavaScript
        # -----------------------------------------------------

        if stack in {
            "node-express",
            "javascript",
            "react",
            "nextjs",
        } and package_json:

            package_json_path = os.path.join(
                project_root,
                "package.json",
            )

            if package_lock:

                install_command = [
                    "npm",
                    "ci",
                    "--ignore-scripts",
                ]

            else:

                install_command = [
                    "npm",
                    "install",
                    "--ignore-scripts",
                ]

            dependency_commands.append(
                install_command
            )

                # -----------------------------------------------------
        # Python
        # -----------------------------------------------------

        python_executable = sys.executable
        python_environment_root = None

        if stack.startswith("python"):

            # -------------------------------------------------
            # Create isolated Python environment when the
            # generated project has requirements.txt
            # -------------------------------------------------

            if requirements_file:

                python_environment_root = os.path.join(
                    project_root,
                    ".tester_venv",
                )

                # Create virtual environment immediately.
                # Do NOT put the venv creation command into
                # dependency_commands because the following
                # commands may need the Python executable.
                if not os.path.isdir(
                    python_environment_root
                ):

                    print(
                        "[Tester] Creating isolated Python "
                        "environment..."
                    )

                    create_venv_command = [
                        sys.executable,
                        "-m",
                        "venv",
                        python_environment_root,
                    ]

                    try:

                        venv_result = subprocess.run(
                            create_venv_command,
                            cwd=project_root,
                            capture_output=True,
                            text=True,
                            timeout=120,
                            shell=False,
                        )

                    except subprocess.TimeoutExpired:

                        raise HTTPException(
                            status_code=500,
                            detail=(
                                "Creating the project Python "
                                "environment timed out."
                            ),
                        )

                    if venv_result.returncode != 0:

                        raise HTTPException(
                            status_code=500,
                            detail=(
                                "Failed to create the project "
                                "Python environment.\n"
                                + (
                                    venv_result.stderr
                                    or venv_result.stdout
                                    or ""
                                )
                            ),
                        )

                # -------------------------------------------------
                # Find the correct Python executable
                # -------------------------------------------------

                if os.name == "nt":

                    python_executable = os.path.join(
                        python_environment_root,
                        "Scripts",
                        "python.exe",
                    )

                else:

                    python_executable = os.path.join(
                        python_environment_root,
                        "bin",
                        "python",
                    )

                if not os.path.isfile(
                    python_executable
                ):

                    raise HTTPException(
                        status_code=500,
                        detail=(
                            "Python executable was not found "
                            "inside the tester virtual environment: "
                            + python_executable
                        ),
                    )

                print(
                    "[Tester] Python executable:"
                    f" {python_executable}"
                )

                # -------------------------------------------------
                # Install pytest into the isolated tester environment
                # -------------------------------------------------

                dependency_commands.append(
                    [
                        python_executable,
                        "-m",
                        "pip",
                        "install",
                        "pytest",
                    ]
                )

                # FastAPI's TestClient requires httpx, but generated
                # requirements files may omit this transitive test dependency.
                if stack == "python-fastapi":
                    dependency_commands.append(
                        [
                            python_executable,
                            "-m",
                            "pip",
                            "install",
                            "httpx",
                        ]
                    )

                # -------------------------------------------------
                # Install the ACTUAL project requirements
                # -------------------------------------------------

                requirements_path = ""

                if isinstance(
                    requirements_file,
                    dict,
                ):

                    requirements_path = _normalize_path(
                        requirements_file.get(
                            "path",
                            "",
                        )
                    )

                else:

                    requirements_path = _normalize_path(
                        str(requirements_file or "")
                    )

                if requirements_path:

                    requirements_path = os.path.abspath(
                        os.path.join(
                            project_root,
                            requirements_path,
                        )
                    )

                if requirements_path and os.path.isfile(
                    requirements_path
                ):

                    pip_command = [
                        python_executable,
                        "-m",
                        "pip",
                        "install",
                        "-r",
                        requirements_path,
                    ]

                    dependency_commands.append(
                        pip_command
                    )

        # -----------------------------------------------------
        # Java / Maven
        # -----------------------------------------------------

        if stack == "java-maven" and pom_file:

            # Maven resolves dependencies during test execution.
            pass

        # =====================================================
        # 9. RUN DEPENDENCY SETUP
        # =====================================================

        for setup_command in dependency_commands:

            command_string = " ".join(
                str(part)
                for part in setup_command
            )

            commands_used.append(
                command_string
            )

            try:

                setup_result = subprocess.run(
                    setup_command,
                    cwd=project_root,
                    capture_output=True,
                    text=True,
                    timeout=180,
                    shell=False,
                )

            except FileNotFoundError as exc:

                error_count += 1

                error_message = (
                    "Dependency setup command could not be started: "
                    + str(exc)
                )

                output_parts.append(
                    "\n===== DEPENDENCY SETUP =====\n"
                    + error_message
                )

                results.append(
                    {
                        "test_id": "SETUP",
                        "title": "Project dependency setup",
                        "path": "",
                        "status": "ERROR",
                        "message": error_message,
                        "stdout": "",
                        "stderr": str(exc),
                    }
                )

                execution = {
                    "status": "ERROR",
                    "framework": (
                        ", ".join(
                            frameworks_used
                        )
                        if frameworks_used
                        else stack
                    ),
                    "command": "\n".join(
                        commands_used
                    ),
                    "exit_code": 1,
                    "output": "\n".join(
                        output_parts
                    ),
                    "results": results,
                    "executed_at": datetime.now(
                        timezone.utc
                    ),
                }

                now = datetime.now(
                    timezone.utc
                )

                db.tester_runs.update_one(
                    {"_id": tester_run["_id"]},
                    {
                        "$set": {
                            "execution": execution,
                            "passed_count": passed_count,
                            "failed_count": failed_count,
                            "error_count": error_count,
                            "not_executable_count": (
                                not_executable_count
                            ),
                            "passed": passed_count,
                            "failed": failed_count,
                            "updated_at": now,
                        }
                    },
                )

                return {
                    "status": "ERROR",
                    "passed": passed_count,
                    "failed": failed_count,
                    "passed_count": passed_count,
                    "failed_count": failed_count,
                    "error_count": error_count,
                    "not_executable_count": (
                        not_executable_count
                    ),
                    "results": results,
                    "execution": execution,
                    "test_cases": tester_run.get(
                        "test_cases",
                        [],
                    ),
                    "version": tester_run.get(
                        "version"
                    ),
                    "summary": tester_run.get(
                        "summary",
                        "",
                    ),
                }

            except subprocess.TimeoutExpired:

                raise HTTPException(
                    status_code=500,
                    detail=(
                        "Project dependency installation "
                        "timed out."
                    ),
                )

            setup_output = (
                setup_result.stdout or ""
            )

            setup_error = (
                setup_result.stderr or ""
            )

            combined_setup_output = (
                setup_output
                + (
                    "\n" + setup_error
                    if setup_error
                    else ""
                )
            )

            output_parts.append(
                "\n===== DEPENDENCY SETUP =====\n"
                + combined_setup_output
            )

            if setup_result.returncode != 0 and "-r" in setup_command:
                requirements_index = setup_command.index("-r") + 1
                source_requirements = setup_command[requirements_index]
                skipped_packages = set()

                try:
                    with open(source_requirements, "r", encoding="utf-8") as requirements_handle:
                        requirement_lines = requirements_handle.readlines()

                    def requirement_name(line):
                        value = line.split("#", 1)[0].strip()
                        if not value or value.startswith(("-", "git+", "http:", "https:")):
                            return ""
                        return re.split(r"[<=>!~\[]", value, maxsplit=1)[0].strip().lower().replace("_", "-")

                    while setup_result.returncode != 0:
                        recovery_output = (setup_result.stdout or "") + (
                            "\n" + setup_result.stderr
                            if setup_result.stderr
                            else ""
                        )
                        unavailable_match = re.search(
                            r"(?:No matching distribution found for|requirement)\s+([A-Za-z0-9_.-]+)",
                            recovery_output,
                            re.IGNORECASE,
                        )
                        if not unavailable_match:
                            break

                        unavailable_name = unavailable_match.group(1).lower().replace("_", "-")
                        if unavailable_name in skipped_packages:
                            break

                        filtered_lines = [
                            line for line in requirement_lines
                            if requirement_name(line) != unavailable_name
                        ]
                        if len(filtered_lines) == len(requirement_lines):
                            break

                        skipped_packages.add(unavailable_name)
                        temporary_requirements = tempfile.NamedTemporaryFile(
                            mode="w",
                            suffix="-tester-requirements.txt",
                            encoding="utf-8",
                            delete=False,
                        )
                        temporary_requirements.writelines(
                            line for line in requirement_lines
                            if requirement_name(line) not in skipped_packages
                        )
                        temporary_requirements.close()
                        retry_command = list(setup_command)
                        retry_command[requirements_index] = temporary_requirements.name
                        commands_used.append(" ".join(str(part) for part in retry_command))
                        retry_result = subprocess.run(
                            retry_command,
                            cwd=project_root,
                            capture_output=True,
                            text=True,
                            timeout=180,
                            shell=False,
                        )
                        retry_output = (retry_result.stdout or "") + (
                            "\n" + retry_result.stderr
                            if retry_result.stderr
                            else ""
                        )
                        output_parts.append(
                            "\n===== DEPENDENCY RECOVERY =====\n"
                            f"Skipped unavailable package: {unavailable_name}\n"
                            + retry_output
                        )
                        setup_result = retry_result
                        setup_output = retry_result.stdout or ""
                        setup_error = retry_result.stderr or ""
                        try:
                            os.unlink(temporary_requirements.name)
                        except OSError:
                            pass
                except OSError:
                    pass

            if setup_result.returncode != 0:

                error_count += 1

                results.append(
                    {
                        "test_id": "SETUP",
                        "title": "Project dependency setup",
                        "path": "",
                        "status": "ERROR",
                        "message": (
                            "Project dependency installation failed."
                        ),
                        "stdout": setup_output,
                        "stderr": setup_error,
                    }
                )

                execution = {
                    "status": "ERROR",
                    "framework": (
                        ", ".join(
                            frameworks_used
                        )
                        if frameworks_used
                        else stack
                    ),
                    "command": "\n".join(
                        commands_used
                    ),
                    "exit_code": setup_result.returncode,
                    "output": "\n".join(
                        output_parts
                    ),
                    "results": results,
                    "executed_at": datetime.now(
                        timezone.utc
                    ),
                }

                now = datetime.now(
                    timezone.utc
                )

                db.tester_runs.update_one(
                    {"_id": tester_run["_id"]},
                    {
                        "$set": {
                            "execution": execution,
                            "passed_count": passed_count,
                            "failed_count": failed_count,
                            "error_count": error_count,
                            "not_executable_count": (
                                not_executable_count
                            ),
                            "passed": passed_count,
                            "failed": failed_count,
                            "updated_at": now,
                        }
                    },
                )

                return {
                    "status": "ERROR",
                    "passed": passed_count,
                    "failed": failed_count,
                    "passed_count": passed_count,
                    "failed_count": failed_count,
                    "error_count": error_count,
                    "not_executable_count": (
                        not_executable_count
                    ),
                    "results": results,
                    "execution": execution,
                    "test_cases": tester_run.get(
                        "test_cases",
                        [],
                    ),
                    "version": tester_run.get(
                        "version"
                    ),
                    "summary": tester_run.get(
                        "summary",
                        "",
                    ),
                }

        # =====================================================
        # 10. EXECUTE TEST FILES AS A PROJECT-WIDE SUITE
        # =====================================================
        # A test file is not a test case. Run the complete suite together so
        # the UI reports the actual number of cases that passed/failed.
        suite_paths = [item["relative_path"] for item in executable_test_paths]
        suite_extensions = {os.path.splitext(path)[1].lower() for path in suite_paths}
        ran_as_suite = False

        if suite_paths and suite_extensions.issubset({".py"}):
            framework = "pytest"
            frameworks_used.append(framework)
            command = [python_executable, "-m", "pytest", *suite_paths, "-vv", "-rA"]
            commands_used.append(" ".join(str(part) for part in command))
            try:
                suite_result = subprocess.run(command, cwd=project_root, capture_output=True, text=True, timeout=300, shell=False)
                stdout = suite_result.stdout or ""
                stderr = suite_result.stderr or ""
                combined = stdout + ("\n" + stderr if stderr else "")
                output_parts.append("\n===== PROJECT TEST SUITE =====\n" + combined)
                ran_as_suite = True
                case_map = {str(tc.get("test_id")): tc for tc in tester_run.get("test_cases", []) if isinstance(tc, dict) and tc.get("test_id")}
                seen_ids = set()
                for test_id, tc in case_map.items():
                    token = re.escape(test_id.split("-")[0]) + r"[-_]" + re.escape(test_id.split("-", 1)[1])
                    match = re.search(rf"{token}.*?\b(PASSED|FAILED|ERROR)\b", combined, re.IGNORECASE)
                    status = match.group(1).upper() if match else None
                    if status == "PASSED":
                        passed_count += 1
                    elif status == "FAILED":
                        failed_count += 1
                    elif status == "ERROR":
                        error_count += 1
                    else:
                        continue
                    seen_ids.add(test_id)
                    results.append({
                        "test_id": test_id,
                        "title": tc.get("title", test_id),
                        "path": next((x["relative_path"] for x in executable_test_paths if test_id in x["metadata"].get("test_ids", [])), ""),
                        "status": status,
                        "message": "Automated test executed as part of the complete project suite.",
                        "stdout": stdout[-4000:],
                        "stderr": stderr[-4000:],
                    })
                # If the framework did not expose individual IDs, use its real summary counts.
                if not seen_ids:
                    summary_match = re.search(r"(\d+) passed", combined)
                    fail_match = re.search(r"(\d+) failed", combined)
                    error_match = re.search(r"(\d+) error", combined)
                    passed_count += int(summary_match.group(1)) if summary_match else 0
                    failed_count += int(fail_match.group(1)) if fail_match else 0
                    error_count += int(error_match.group(1)) if error_match else 0
                    results.append({
                        "test_id": "SUITE",
                        "title": "Complete project test suite",
                        "path": ", ".join(suite_paths),
                        "status": "PASSED" if suite_result.returncode == 0 else "FAILED",
                        "message": "All generated Python test files were executed together.",
                        "stdout": stdout[-4000:],
                        "stderr": stderr[-4000:],
                    })
            except FileNotFoundError as exc:
                error_count += 1
                results.append({"test_id": "SUITE", "title": "Complete project test suite", "path": ", ".join(suite_paths), "status": "ERROR", "message": str(exc)})
                ran_as_suite = True
            except subprocess.TimeoutExpired as exc:
                error_count += 1
                results.append({"test_id": "SUITE", "title": "Complete project test suite", "path": ", ".join(suite_paths), "status": "ERROR", "message": "Project test suite timed out after 300 seconds."})
                ran_as_suite = True

        elif suite_paths and suite_extensions.issubset({".js", ".mjs", ".cjs"}):
            framework = "node:test"
            frameworks_used.append(framework)
            command = ["node", "--test", *suite_paths]
            commands_used.append(" ".join(str(part) for part in command))
            try:
                suite_result = subprocess.run(command, cwd=project_root, capture_output=True, text=True, timeout=300, shell=False)
                stdout = suite_result.stdout or ""
                stderr = suite_result.stderr or ""
                combined = stdout + ("\n" + stderr if stderr else "")
                output_parts.append("\n===== PROJECT TEST SUITE =====\n" + combined)
                ran_as_suite = True
                case_map = {str(tc.get("test_id")): tc for tc in tester_run.get("test_cases", []) if isinstance(tc, dict) and tc.get("test_id")}
                seen_ids = set()
                for test_id, tc in case_map.items():
                    match = re.search(rf"Subtest:\s*{re.escape(test_id)}[\s\S]*?\n(?:ok|not ok)\s+\d+\s+-", combined, re.IGNORECASE)
                    if not match:
                        continue
                    block = match.group(0).lower()
                    status = "PASSED" if "\nok " in block else "FAILED"
                    if status == "PASSED": passed_count += 1
                    else: failed_count += 1
                    seen_ids.add(test_id)
                    results.append({"test_id": test_id, "title": tc.get("title", test_id), "path": next((x["relative_path"] for x in executable_test_paths if test_id in x["metadata"].get("test_ids", [])), ""), "status": status, "message": "Automated test executed as part of the complete project suite.", "stdout": stdout[-4000:], "stderr": stderr[-4000:]})
                if not seen_ids:
                    pass_match = re.search(r"# pass (\d+)", combined)
                    fail_match = re.search(r"# fail (\d+)", combined)
                    passed_count += int(pass_match.group(1)) if pass_match else 0
                    failed_count += int(fail_match.group(1)) if fail_match else 0
                    results.append({"test_id": "SUITE", "title": "Complete project test suite", "path": ", ".join(suite_paths), "status": "PASSED" if suite_result.returncode == 0 else "FAILED", "message": "All generated Node test files were executed together.", "stdout": stdout[-4000:], "stderr": stderr[-4000:]})
            except FileNotFoundError as exc:
                error_count += 1
                results.append({"test_id": "SUITE", "title": "Complete project test suite", "path": ", ".join(suite_paths), "status": "ERROR", "message": str(exc)})
                ran_as_suite = True
            except subprocess.TimeoutExpired:
                error_count += 1
                results.append({"test_id": "SUITE", "title": "Complete project test suite", "path": ", ".join(suite_paths), "status": "ERROR", "message": "Project test suite timed out after 300 seconds."})
                ran_as_suite = True

        if not ran_as_suite:
            for test_info in executable_test_paths:

                test_file = test_info["metadata"]

                absolute_test_path = test_info["path"]

                relative_test_path = test_info[
                    "relative_path"
                ]

                extension = os.path.splitext(
                    relative_test_path
                )[1].lower()

                command = None
                framework = None

                # =================================================
                # PYTHON
                # =================================================

                if extension == ".py":

                    framework = "pytest"

                    frameworks_used.append(
                        framework
                    )

                    command = [
                        python_executable,
                        "-m",
                        "pytest",
                        relative_test_path,
                        "-q",
                        "-rA",
                    ]

                # =================================================
                # JAVASCRIPT / NODE
                # =================================================

                elif extension in {
                    ".js",
                    ".mjs",
                    ".cjs",
                }:

                    framework = "node:test"

                    frameworks_used.append(
                        framework
                    )

                    command = [
                        "node",
                        "--test",
                        relative_test_path,
                    ]

                # =================================================
                # JAVA
                # =================================================

                elif extension == ".java":

                    if pom_file:

                        framework = "maven"

                        frameworks_used.append(
                            framework
                        )

                        command = [
                            "mvn",
                            "test",
                        ]

                    else:

                        not_executable_count += 1

                        results.append(
                            {
                                "test_id": test_file.get(
                                    "test_id",
                                    "UNKNOWN",
                                ),
                                "title": test_file.get(
                                    "title",
                                    relative_test_path,
                                ),
                                "path": relative_test_path,
                                "status": "NOT_EXECUTABLE",
                                "message": (
                                    "Java test requires a Maven project."
                                ),
                            }
                        )

                        continue

                # =================================================
                # UNSUPPORTED
                # =================================================

                else:

                    not_executable_count += 1

                    results.append(
                        {
                            "test_id": test_file.get(
                                "test_id",
                                "UNKNOWN",
                            ),
                            "title": test_file.get(
                                "title",
                                relative_test_path,
                            ),
                            "path": relative_test_path,
                            "status": "NOT_EXECUTABLE",
                            "message": (
                                "Unsupported test file type: "
                                + (
                                    extension
                                    or "unknown"
                                )
                            ),
                        }
                    )

                    continue

                # =================================================
                # RUN COMMAND
                # =================================================

                command_string = " ".join(
                    str(part)
                    for part in command
                )

                commands_used.append(
                    command_string
                )

                try:

                    result = subprocess.run(
                        command,
                        cwd=project_root,
                        capture_output=True,
                        text=True,
                        timeout=180,
                        shell=False,
                    )

                    stdout = (
                        result.stdout or ""
                    )

                    stderr = (
                        result.stderr or ""
                    )

                    combined_output = (
                        stdout
                        + (
                            "\n" + stderr
                            if stderr
                            else ""
                        )
                    )

                    output_parts.append(
                        f"\n===== {relative_test_path} =====\n"
                        f"{combined_output}"
                    )

                    if result.returncode == 0:

                        passed_count += 1

                        results.append(
                            {
                                "test_id": test_file.get(
                                    "test_id",
                                    "UNKNOWN",
                                ),
                                "title": test_file.get(
                                    "title",
                                    relative_test_path,
                                ),
                                "path": relative_test_path,
                                "status": "PASSED",
                                "message": (
                                    "Test file executed successfully."
                                ),
                                "stdout": stdout,
                                "stderr": stderr,
                            }
                        )

                    else:

                        failed_count += 1

                        results.append(
                            {
                                "test_id": test_file.get(
                                    "test_id",
                                    "UNKNOWN",
                                ),
                                "title": test_file.get(
                                    "title",
                                    relative_test_path,
                                ),
                                "path": relative_test_path,
                                "status": "FAILED",
                                "message": (
                                    "Test execution failed."
                                ),
                                "stdout": stdout,
                                "stderr": stderr,
                            }
                        )

                except FileNotFoundError as exc:

                    error_count += 1

                    error_message = (
                        "Test command could not be started: "
                        + str(exc)
                    )

                    output_parts.append(
                        f"\n===== {relative_test_path} =====\n"
                        f"ERROR: {error_message}"
                    )

                    results.append(
                        {
                            "test_id": test_file.get(
                                "test_id",
                                "UNKNOWN",
                            ),
                            "title": test_file.get(
                                "title",
                                relative_test_path,
                            ),
                            "path": relative_test_path,
                            "status": "ERROR",
                            "message": error_message,
                        }
                    )

                except subprocess.TimeoutExpired as exc:

                    error_count += 1

                    timeout_output = ""

                    if exc.stdout:

                        timeout_output += str(
                            exc.stdout
                        )

                    if exc.stderr:

                        timeout_output += (
                            "\n"
                            + str(exc.stderr)
                        )

                    output_parts.append(
                        f"\n===== {relative_test_path} =====\n"
                        "TIMEOUT\n"
                        f"{timeout_output}"
                    )

                    results.append(
                        {
                            "test_id": test_file.get(
                                "test_id",
                                "UNKNOWN",
                            ),
                            "title": test_file.get(
                                "title",
                                relative_test_path,
                            ),
                            "path": relative_test_path,
                            "status": "ERROR",
                            "message": (
                                "Test execution timed out "
                                "after 180 seconds."
                            ),
                        }
                    )

                except Exception as exc:

                    error_count += 1

                    error_message = str(
                        exc
                    )

                    output_parts.append(
                        f"\n===== {relative_test_path} =====\n"
                        f"ERROR: {error_message}"
                    )

                    results.append(
                        {
                            "test_id": test_file.get(
                                "test_id",
                                "UNKNOWN",
                            ),
                            "title": test_file.get(
                                "title",
                                relative_test_path,
                            ),
                            "path": relative_test_path,
                            "status": "ERROR",
                            "message": error_message,
                        }
                    )

        # =====================================================
        # 11. FINAL STATUS
        # =====================================================

        executable_count = (
            passed_count
            + failed_count
            + error_count
        )

        if executable_count == 0:

            final_status = (
                "NO_EXECUTABLE_TESTS"
            )

        elif error_count > 0:

            final_status = "ERROR"

        elif failed_count > 0:

            final_status = "FAILED"

        else:

            final_status = "PASSED"

        # =====================================================
        # 12. EXECUTION INFORMATION
        # =====================================================

        now = datetime.now(
            timezone.utc
        )

        framework = (
            ", ".join(
                dict.fromkeys(
                    frameworks_used
                )
            )
            if frameworks_used
            else stack
        )

        command = (
            "\n".join(
                dict.fromkeys(
                    commands_used
                )
            )
            if commands_used
            else "N/A"
        )

        output = (
            "\n".join(
                output_parts
            )
            if output_parts
            else "No execution output."
        )

        execution = {
            "status": final_status,
            "framework": framework,
            "command": command,
            "exit_code": (
                0
                if final_status == "PASSED"
                else 1
                if final_status in {
                    "FAILED",
                    "ERROR",
                }
                else None
            ),
            "output": output,
            "results": results,
            "executed_at": now,
        }

        # =====================================================
        # 13. SAVE EXECUTION RESULT
        # =====================================================

        db.tester_runs.update_one(
            {"_id": tester_run["_id"]},
            {
                "$set": {
                    "execution": execution,
                    "passed_count": passed_count,
                    "failed_count": failed_count,
                    "error_count": error_count,
                    "not_executable_count": (
                        not_executable_count
                    ),
                    "passed": passed_count,
                    "failed": failed_count,
                    "updated_at": now,
                }
            },
        )

        # =====================================================
        # 14. PROJECT WORKFLOW STATE
        # =====================================================

        if final_status == "PASSED" and not_executable_count == 0:
            workflow_status = "TESTS_COMPLETED"
            workflow_agent = "HUMAN_APPROVAL"
        else:
            workflow_status = "TESTS_FAILED"
            workflow_agent = "DEVELOPER"

        db.projects.update_one(
            {"_id": ObjectId(project_id)},
            {"$set": {
                "status": workflow_status,
                "current_agent": workflow_agent,
                "updated_at": now,
            }},
        )

        # =====================================================
        # 15. AGENT ACTIVITY
        # =====================================================

        db.agent_activity.insert_one(
            {
                "project_id": project_id,
                "agent": "TESTER",
                "event": "TESTS_EXECUTED",
                "message": (
                    f"Executed {executable_count} "
                    f"test file(s): "
                    f"{passed_count} passed, "
                    f"{failed_count} failed, "
                    f"{error_count} errors, "
                    f"{not_executable_count} "
                    f"not executable."
                ),
                "created_at": now,
            }
        )

        # =====================================================
        # 15. RESPONSE
        # =====================================================

        return {
            "status": final_status,
            "passed": passed_count,
            "failed": failed_count,
            "passed_count": passed_count,
            "failed_count": failed_count,
            "error_count": error_count,
            "not_executable_count": (
                not_executable_count
            ),
            "results": results,
            "execution": execution,
            "test_cases": tester_run.get(
                "test_cases",
                [],
            ),
            "version": tester_run.get(
                "version"
            ),
            "summary": tester_run.get(
                "summary",
                "",
            ),
        }

    finally:

        # =====================================================
        # 16. CLEANUP TEMPORARY PROJECT
        # =====================================================

        try:

            shutil.rmtree(
                project_root,
                ignore_errors=True,
            )

        except Exception:

            pass
