from app.services.ai_service import generate_json, generate_text
import json

def fallback_project_file(project_name: str, description: str, file_info: dict) -> dict:
    """Return a valid baseline file when all configured AI providers are unavailable."""
    path = str(file_info.get("path", "")).replace("\\", "/")
    language = str(file_info.get("language", "text"))
    filename = path.rsplit("/", 1)[-1].lower()
    title = json.dumps(project_name)

    if filename == "package.json":
        content = json.dumps({
            "name": "generated-project",
            "private": True,
            "scripts": {"dev": "vite", "build": "vite build"},
            "dependencies": {"@vitejs/plugin-react": "latest", "vite": "latest", "react": "latest", "react-dom": "latest"},
            "devDependencies": {},
        }, indent=2)
    elif filename == "index.html":
        content = '<div id="root"></div><script type="module" src="/src/main.jsx"></script>'
    elif filename in {"main.jsx", "app.jsx"} or path.endswith("/src/main.jsx") or path.endswith("/src/App.jsx"):
        content = f"import React from 'react';\nimport {{ createRoot }} from 'react-dom/client';\nimport './styles.css';\n\nexport default function App() {{ return <main><h1>{project_name}</h1><p>{description}</p></main>; }}\n\nif (document.getElementById('root')) createRoot(document.getElementById('root')).render(<App />);"
    elif filename == "styles.css":
        content = "body { margin: 0; font-family: sans-serif; padding: 2rem; } main { max-width: 900px; margin: auto; }"
    elif filename == "requirements.txt":
        content = "fastapi\nuvicorn\npython-dotenv\n"
    elif filename == "main.py":
        content = 'from fastapi import FastAPI\n\napp = FastAPI(title=' + title + ')\n\n@app.get("/health")\ndef health():\n    return {"status": "ok"}\n'
    elif filename == "routes.py":
        content = 'from fastapi import APIRouter\n\nrouter = APIRouter(prefix="/api")\n\n@router.get("/health")\ndef health():\n    return {"status": "ok"}\n'
    elif filename == "database.py":
        content = 'import os\n\nDATABASE_URL = os.getenv("MONGODB_URI", "")\n\ndef get_db():\n    return None\n\ndef close_database():\n    return None\n'
    elif language.lower() in {"python", "javascript", "jsx", "typescript", "tsx"} or path.endswith((".py", ".js", ".jsx", ".ts", ".tsx")):
        content = f'"""Baseline generated module for {project_name}."""\n'
    elif filename == "readme.md":
        content = f"# {project_name}\n\n{description}\n"
    else:
        content = f"Generated baseline for {project_name}.\n"

    return {"path": path, "language": language, "content": content}

# ============================================================
# DEVELOPER PLAN SCHEMA
# ============================================================

DEVELOPER_PLAN_SCHEMA = {
    "type": "object",
    "properties": {
        "project_summary": {
            "type": "string"
        },
        "technology_stack": {
            "type": "object",
            "properties": {
                "frontend": {
                    "type": "string"
                },
                "backend": {
                    "type": "string"
                },
                "database": {
                    "type": "string"
                },
                "other_tools": {
                    "type": "array",
                    "items": {
                        "type": "string"
                    }
                }
            },
            "required": [
                "frontend",
                "backend",
                "database",
                "other_tools"
            ]
        },
        "project_structure": {
            "type": "array",
            "items": {
                "type": "string"
            }
        },
        "files": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string"
                    },
                    "language": {
                        "type": "string"
                    },
                    "purpose": {
                        "type": "string"
                    }
                },
                "required": [
                    "path",
                    "language",
                    "purpose"
                ]
            }
        },
        "dependencies": {
            "type": "array",
            "items": {
                "type": "string"
            }
        },
        "implementation_decisions": {
            "type": "array",
            "items": {
                "type": "string"
            }
        },
        "test_suggestions": {
            "type": "array",
            "items": {
                "type": "string"
            }
        }
    },
    "required": [
        "project_summary",
        "technology_stack",
        "project_structure",
        "files",
        "dependencies",
        "implementation_decisions",
        "test_suggestions"
    ]
}


# ============================================================
# FILE SCHEMA
# ============================================================

FILE_SCHEMA = {
    "type": "object",
    "properties": {
        "path": {
            "type": "string"
        },
        "language": {
            "type": "string"
        },
        "content": {
            "type": "string"
        }
    },
    "required": [
        "path",
        "language",
        "content"
    ]
}


# ============================================================
# PROJECT PLAN GENERATION
# ============================================================

# Keep generated applications practical.  Each source file is a separate
# LLM request, so an unnecessarily large manifest makes generation slow and
# increases the chance of inconsistent output.  The plan generator is told
# to stay below this limit, and normalization enforces the same safety net.
MAX_GENERATED_PROJECT_FILES = 24

def generate_project_plan(
    project_name: str,
    description: str,
    requirements: dict,
    developer_opinion: dict,
    architecture: dict,
    developer_fix_request: dict | None = None,
):
    """
    Generate a complete implementation plan for the project.

    IMPORTANT:
    This function generates METADATA only.
    Actual source code is generated later by generate_project_file().
    """

    prompt = f"""
You are the Developer Agent in an AI-powered
multi-agent software development team.

Your responsibility is to create a COMPLETE and
IMPLEMENTABLE project plan.

============================================================
PROJECT
============================================================

Name:
{project_name}

Description:
{description}

============================================================
PRODUCT MANAGER REQUIREMENTS
============================================================

{json.dumps(requirements, indent=2, ensure_ascii=False)}

============================================================
DEVELOPER FEASIBILITY OPINION
============================================================

{json.dumps(developer_opinion, indent=2, ensure_ascii=False)}

============================================================
APPROVED ARCHITECTURE
============================================================

{json.dumps(architecture, indent=2, ensure_ascii=False)}

============================================================
DEVELOPER FIX REQUEST
============================================================

{json.dumps(developer_fix_request or {}, indent=2, ensure_ascii=False)}

============================================================
GLOBAL DEVELOPMENT RULES
============================================================

1. Follow the approved architecture.

2. Follow the original user request exactly.

3. Follow the Product Manager requirements.

4. The technology stack explicitly selected by the user
   is authoritative.

5. NEVER silently replace:
   - MySQL with SQLite
   - MongoDB with PostgreSQL
   - PostgreSQL with SQLite
   - Express with FastAPI
   - FastAPI with Flask
   - React with another frontend
   - Java with Python
   - Node.js with another backend

6. If the user did not specify a technology stack,
   use the stack approved by the Product Manager and Architect.

7. Keep the same technology stack across the ENTIRE project.

8. Every generated project must be a REAL runnable application.

9. Generate all files required for a complete application.

10. Include:
    - frontend files when applicable
    - backend files when applicable
    - database configuration
    - models/entities
    - schemas/DTOs where required
    - services
    - routes/controllers
    - authentication
    - middleware/security
    - configuration
    - dependency files
    - startup/entry files
    - tests/test configuration when appropriate

11. Every imported module must have a corresponding generated file
    or be a real external dependency.

12. NEVER plan imports to files that are not included in the
    "files" array.

13. File paths must be explicit and relative to the generated
    project root.

14. Python projects must use a coherent package structure.

15. Node.js projects must contain the required package.json.

16. Java Maven projects must contain pom.xml.

17. Java Gradle projects must contain build.gradle or
    build.gradle.kts.

18. Frontend projects must contain their package configuration
    and entry files.

19. Database-dependent applications must include all required
    database configuration and initialization/migration files.

20. Authentication must be completely planned when required:
    - registration
    - login
    - password hashing
    - token/session handling
    - protected routes
    - current-user handling
    - logout/session invalidation where applicable

21. Do not create fake authentication.

22. Do not create fake APIs.

23. Do not create placeholder modules.

24. Do not create imports for modules that do not exist.

25. Do not create dead links or fake buttons.

26. Do not omit configuration files required to run the project.

27. If environment variables are required, include an
    .env.example file in the plan.

28. Do not put secrets or API keys directly into generated source.

29. API contracts must be consistent between frontend and backend.

30. Every endpoint referenced by the frontend must exist in
    the backend plan.

31. Every backend endpoint should identify its HTTP method,
    path, request data, response data and authentication
    requirements in the relevant file purpose.

32. Database entities/tables/collections must be consistent
    with the actual database technology.

33. Do not invent a second database.

34. Do not mix database technologies unless the architecture
    explicitly requires it.

35. Tests must target actual public behavior of the generated
    project.

36. The test plan must be compatible with the actual project stack.

37. Include test configuration/dependencies when the selected
    stack supports automated testing.

    For FastAPI projects, include pytest and httpx in the backend
    requirements because FastAPI TestClient depends on httpx.

38. Keep the implementation compact. The complete generated project MUST
    contain no more than 24 files.

39. Consolidate small components, route definitions, schemas, and simple
    helpers into existing files when that keeps the application complete.

40. Prefer a small runnable application over many tiny files.

41. Do NOT create separate files merely for:
    - one small form
    - one small card
    - one small route
    - one small utility
    - documentation that is not needed to run the project

42. The 24-file limit is a HARD limit. If the application appears to need
    more files, combine related functionality into fewer files.

43. If a Developer fix request is provided:
    - fix the reported issue
    - preserve the architecture unless genuinely necessary
    - do not introduce unrelated features
    - prioritize critical/high severity findings

============================================================
IMPORTANT FILE CONSISTENCY RULE
============================================================

The "files" array is the SOURCE OF TRUTH for the Developer Agent.

Every source file that another generated file may import MUST
appear in the "files" array.

For example, if a Python backend uses:

from app.database import get_db

then the plan MUST contain:

app/database.py

If the backend uses:

from app.models import User

then the plan MUST contain:

app/models.py

If the backend uses:

from app.schemas import UserCreate

then the plan MUST contain:

app/schemas.py

If the backend uses:

from app.middleware import get_current_user

then the plan MUST contain:

app/middleware.py

Do NOT create references to imaginary modules.

============================================================
PYTHON PROJECT RULE
============================================================

For Python applications:

Use a consistent package structure.

For example:

app/
    __init__.py
    main.py
    database.py
    models.py
    schemas.py
    services/
        __init__.py
        auth_service.py
    routes/
        __init__.py
        auth.py

If such imports are required, ALL corresponding files must
be included in the generated project.

The generated tests must import using the actual package paths.

Do NOT expect packages named:

database
models
schemas
middleware

unless those files actually exist at the project root.

Prefer explicit imports such as:

from app.database import ...
from app.models import ...
from app.schemas import ...

============================================================
TEST COMPATIBILITY RULE
============================================================

The generated project must expose a clear testable public entry point.

Examples:

FastAPI:
app/main.py containing:
app = FastAPI(...)

Flask:
app.py or app/main.py containing:
app = Flask(...)

Express:
server/app.js or equivalent exporting:
app

Java:
normal public classes and application entry point.

Tests must inspect the generated project structure and use
the actual paths and exported symbols.

============================================================
FILE COUNT REQUIREMENT
============================================================

The "files" array MUST contain 24 OR FEWER files.

A practical full-stack college application normally fits within
roughly 15-24 files by combining small related modules.

Do NOT return 40, 50, 60 or more files.

============================================================
OUTPUT REQUIREMENTS
============================================================

Return ONLY valid JSON.

The JSON must contain:

project_summary
technology_stack
project_structure
files
dependencies
implementation_decisions
test_suggestions

The "files" array must contain ONLY:

path
language
purpose

Do NOT generate source code here.

Do NOT include file contents.

Do NOT use markdown.

Do NOT include explanations outside JSON.

Make the plan complete enough that another agent can generate
every file without guessing missing modules or dependencies.
"""

    try:
        result = generate_json(prompt, DEVELOPER_PLAN_SCHEMA)
        # Keep the plan usable even when a free model omits harmless metadata.
        result.setdefault("project_summary", f"Runnable implementation of {project_name}.")
        result.setdefault("technology_stack", architecture.get("technology_stack", {}))
        result.setdefault("project_structure", architecture.get("folder_structure", []))
        result.setdefault("files", [])
        result.setdefault("dependencies", [])
        result.setdefault("implementation_decisions", [])
        result.setdefault("test_suggestions", [])
        return normalize_project_plan(result, architecture)
    except Exception as exc:
        print(f"[Developer] Project-plan generation failed; using deterministic fallback: {exc}")
        stack = architecture.get("technology_stack", {}) or {}
        frontend = str(stack.get("frontend") or "React + Vite")
        backend = str(stack.get("backend") or "FastAPI + Python")
        database = str(stack.get("database") or "MongoDB")

        # This fallback is intentionally small and coherent. The LLM still
        # generates each source file, but the file manifest cannot disappear.
        files = [
            {"path": "frontend/package.json", "language": "json", "purpose": "Frontend dependency manifest and Vite scripts."},
            {"path": "frontend/index.html", "language": "html", "purpose": "Frontend HTML entry point."},
            {"path": "frontend/src/main.jsx", "language": "jsx", "purpose": "React application entry point."},
            {"path": "frontend/src/App.jsx", "language": "jsx", "purpose": "Main application UI implementing the requested workflow."},
            {"path": "frontend/src/styles.css", "language": "css", "purpose": "Responsive application styling."},
            {"path": "backend/requirements.txt", "language": "text", "purpose": f"Python dependencies for {backend}."},
            {"path": "backend/app/__init__.py", "language": "python", "purpose": "Backend package marker."},
            {"path": "backend/app/main.py", "language": "python", "purpose": f"Runnable {backend} API entry point."},
            {"path": "backend/app/database.py", "language": "python", "purpose": f"{database} connection configuration using environment variables."},
            {"path": ".env.example", "language": "text", "purpose": "Environment variable template without secrets."},
            {"path": "README.md", "language": "markdown", "purpose": "Local setup and run instructions."},
        ]
        return {
            "project_summary": f"Runnable implementation of {project_name}.",
            "technology_stack": {
                "frontend": frontend,
                "backend": backend,
                "database": database,
                "other_tools": stack.get("other_tools", []),
            },
            "project_structure": architecture.get("folder_structure", ["frontend/", "backend/"]),
            "files": files,
            "dependencies": [frontend, backend, database],
            "implementation_decisions": [
                "Use the approved architecture as the source of truth.",
                "Keep frontend API contracts aligned with backend routes.",
                "Read credentials from environment variables.",
            ],
            "test_suggestions": [
                "Validate authentication flow.",
                "Validate the requested core application workflow.",
                "Validate frontend/backend API integration.",
            ],
        }


# ============================================================
# PROJECT PLAN NORMALIZATION
# ============================================================

def normalize_project_plan(plan: dict, architecture: dict) -> dict:
    """Guarantee the minimum runnable file manifest for common web stacks.

    Free models sometimes return an unrealistically small file list even when
    the prompt explicitly requires a complete application. This function adds
    only missing baseline files; it never removes model-planned files.
    """
    plan = dict(plan or {})
    files = list(plan.get("files") or [])
    existing = {str(item.get("path", "")).replace("\\", "/") for item in files if isinstance(item, dict)}
    stack = architecture.get("technology_stack", {}) or {}
    frontend = str(stack.get("frontend", "")).lower()
    backend = str(stack.get("backend", "")).lower()
    database = str(stack.get("database", "")).lower()

    def add(path, language, purpose):
        if path not in existing:
            files.append({"path": path, "language": language, "purpose": purpose})
            existing.add(path)

    if any(x in frontend for x in ("react", "vite", "next")):
        # Preserve the directory convention chosen by the model/architecture
        # (some plans use frontend/, others use client/).
        frontend_root = "client" if any(
            p.startswith("client/") for p in existing
        ) and not any(p.startswith("frontend/") for p in existing) else "frontend"

        add(f"{frontend_root}/package.json", "json", "Frontend dependency manifest and runnable scripts.")
        add(f"{frontend_root}/index.html", "html", "Frontend HTML entry point.")
        is_typescript = any(p.endswith((".ts", ".tsx")) for p in existing)
        entry_ext = "tsx" if is_typescript else "jsx"
        add(f"{frontend_root}/src/main.{entry_ext}", entry_ext, "Frontend application entry point.")
        add(f"{frontend_root}/src/App.{entry_ext}", entry_ext, "Main frontend application implementing the requested user workflows.")
        add(f"{frontend_root}/src/styles.css", "css", "Responsive styling for the complete frontend.")

        if is_typescript:
            # TypeScript projects need the compiler configuration and should
            # not be mixed with JSX-only entry files.
            add(f"{frontend_root}/tsconfig.json", "json", "TypeScript compiler configuration.")

    if any(x in backend for x in ("fastapi", "flask", "django", "python")):
        add("backend/requirements.txt", "text", "Backend Python dependencies.")
        add("backend/app/__init__.py", "python", "Backend package marker.")
        add("backend/app/main.py", "python", "Runnable backend API entry point.")
        if "fastapi" in backend:
            add("backend/app/routes.py", "python", "Backend API routes/controllers for the requested application behavior.")

    if any(x in backend for x in ("express", "node", "node.js")):
        add("backend/package.json", "json", "Backend dependency manifest and start scripts.")
        add("backend/server.js", "javascript", "Runnable backend/server entry point.")

    if database and database not in ("none", "n/a", "not required"):
        if any(x in database for x in ("mongo", "mysql", "postgres", "sqlite", "database")) and any("backend/" in p for p in existing):
            add("backend/app/database.py", "python", "Database connection/configuration using environment variables.")

    add(".env.example", "text", "Environment variable template without secrets.")
    add("README.md", "markdown", "Complete local setup, run, preview, and configuration instructions.")

    # ------------------------------------------------------------
    # Canonicalize the frontend manifest. Free models sometimes return a
    # second plan with client/ + frontend/ or mix JSX and TSX entry points.
    # That produces exactly the kind of App/main mismatch seen in failed
    # generations. Keep one frontend root and one language family.
    # ------------------------------------------------------------
    def norm_path(value):
        return str(value or "").replace("\\", "/").strip()

    has_frontend = any(norm_path(x.get("path")).startswith("frontend/") for x in files if isinstance(x, dict))
    has_client = any(norm_path(x.get("path")).startswith("client/") for x in files if isinstance(x, dict))
    if has_frontend and has_client:
        frontend_root = "frontend"
        files = [x for x in files if not (isinstance(x, dict) and norm_path(x.get("path")).startswith("client/"))]

    # Detect the language from the canonical frontend root and remove mixed
    # duplicate entry files. main.jsx + App.tsx is never allowed.
    frontend_root = "frontend" if any(norm_path(x.get("path")).startswith("frontend/") for x in files if isinstance(x, dict)) else ("client" if any(norm_path(x.get("path")).startswith("client/") for x in files if isinstance(x, dict)) else None)
    if frontend_root:
        root_paths = [norm_path(x.get("path")) for x in files if isinstance(x, dict) and norm_path(x.get("path")).startswith(frontend_root + "/")]
        use_ts = any(path.endswith((".ts", ".tsx")) for path in root_paths)
        if use_ts:
            files = [
                x for x in files
                if not (isinstance(x, dict) and norm_path(x.get("path")) in {
                    f"{frontend_root}/src/main.jsx", f"{frontend_root}/src/App.jsx"
                })
            ]
            existing = {norm_path(x.get("path")) for x in files if isinstance(x, dict)}
            if f"{frontend_root}/src/main.tsx" not in existing:
                files.append({"path": f"{frontend_root}/src/main.tsx", "language": "tsx", "purpose": "Frontend application entry point."})
            if f"{frontend_root}/src/App.tsx" not in existing:
                files.append({"path": f"{frontend_root}/src/App.tsx", "language": "tsx", "purpose": "Main frontend application implementing the requested workflows."})
        else:
            files = [
                x for x in files
                if not (isinstance(x, dict) and norm_path(x.get("path")) in {
                    f"{frontend_root}/src/main.tsx", f"{frontend_root}/src/App.tsx"
                })
            ]
            existing = {norm_path(x.get("path")) for x in files if isinstance(x, dict)}
            if f"{frontend_root}/src/main.jsx" not in existing:
                files.append({"path": f"{frontend_root}/src/main.jsx", "language": "jsx", "purpose": "Frontend application entry point."})
            if f"{frontend_root}/src/App.jsx" not in existing:
                files.append({"path": f"{frontend_root}/src/App.jsx", "language": "jsx", "purpose": "Main frontend application implementing the requested workflows."})

    # Remove duplicate paths case-insensitively while preserving the first
    # complete plan entry.
    unique = []
    seen_paths = set()
    for item in files:
        if not isinstance(item, dict):
            continue
        key = norm_path(item.get("path")).lower()
        if not key or key in seen_paths:
            continue
        seen_paths.add(key)
        item["path"] = norm_path(item.get("path"))
        unique.append(item)
    files = unique

    # Enforce the practical file-count limit as a final safety net.
    # The prompt normally makes the model stay under the limit. If a free
    # model ignores it, retain the files that make the project runnable and
    # consolidate the rest into the existing application files rather than
    # issuing dozens of LLM requests.
    if len(files) > MAX_GENERATED_PROJECT_FILES:
        priority_tokens = (
            "package.json", "requirements.txt", "pom.xml", "build.gradle",
            "index.html", "vite.config", "tsconfig", "main.", "index.",
            "app.", "server.", "routes", "router", "database", "db.",
            "models", "schema", "auth", "service", "api", "App.",
            "styles", "css", ".env.example", "README"
        )

        def file_score(item):
            path = str(item.get("path", "")).replace("\\", "/").lower()
            purpose = str(item.get("purpose", "")).lower()
            score = 0
            for i, token in enumerate(priority_tokens):
                if token.lower() in path:
                    score += 100 - i
            # Keep application entry points and backend/frontend roots highly
            # visible even when the model used an unusual filename.
            if "/src/" in path and any(x in path for x in ("app.", "main.", "index.")):
                score += 120
            if path.endswith("/__init__.py"):
                score += 25
            if any(x in purpose for x in ("entry", "runnable", "route", "api", "database", "authentication")):
                score += 20
            # Prefer shallower files when otherwise equivalent: these tend to
            # be shared/core files rather than one-off UI fragments.
            score -= path.count("/") * 2
            return score

        ranked = sorted(
            enumerate(files),
            key=lambda pair: (-file_score(pair[1]), pair[0])
        )
        selected = [item for _, item in ranked[:MAX_GENERATED_PROJECT_FILES]]

        # Preserve stable order from the original plan.
        selected_ids = {id(item) for item in selected}
        files = [item for item in files if id(item) in selected_ids]

        print(
            f"[Developer] Project plan requested {len(plan.get('files', []))} "
            f"files; compacting to {MAX_GENERATED_PROJECT_FILES} files."
        )

    plan["files"] = files
    plan.setdefault("dependencies", [])
    plan.setdefault("implementation_decisions", [])
    plan.setdefault("test_suggestions", [])
    return plan


# ============================================================
# PROJECT FILE GENERATION
# ============================================================

def generate_project_file(
    project_name: str,
    description: str,
    requirements: dict,
    developer_opinion: dict,
    architecture: dict,
    project_plan: dict,
    file_info: dict,
):
    """
    Generate ONE complete project file.

    The file is generated using the complete project context
    so that imports and interfaces remain consistent.
    """

    current_path = str(
        file_info.get("path", "")
    ).strip()

    current_language = str(
        file_info.get("language", "")
    ).strip()

    current_purpose = str(
        file_info.get("purpose", "")
    ).strip()

    # --------------------------------------------------------
    # Build a compact file manifest
    # --------------------------------------------------------

    planned_files = project_plan.get(
        "files",
        []
    )

    file_manifest = []

    for item in planned_files:
        if not isinstance(item, dict):
            continue

        path = str(
            item.get("path", "")
        ).strip()

        language = str(
            item.get("language", "")
        ).strip()

        purpose = str(
            item.get("purpose", "")
        ).strip()

        if path:
            file_manifest.append(
                {
                    "path": path,
                    "language": language,
                    "purpose": purpose,
                }
            )

    # --------------------------------------------------------
    # Prompt
    # --------------------------------------------------------

    prompt = f"""
You are the Developer Agent in an AI-powered
multi-agent software development team.

Generate ONE COMPLETE source/configuration file.

============================================================
PROJECT
============================================================

Name:
{project_name}

Description:
{description}

============================================================
REQUIREMENTS
============================================================

{json.dumps(requirements, indent=2, ensure_ascii=False)}

============================================================
APPROVED ARCHITECTURE
============================================================

{json.dumps(architecture, indent=2, ensure_ascii=False)}

============================================================
COMPLETE PROJECT PLAN
============================================================

{json.dumps(project_plan, indent=2, ensure_ascii=False)}

============================================================
ALL PLANNED FILES
============================================================

{json.dumps(file_manifest, indent=2, ensure_ascii=False)}

============================================================
CURRENT FILE
============================================================

Path:
{current_path}

Language:
{current_language}

Purpose:
{current_purpose}

============================================================
CRITICAL PROJECT CONSISTENCY RULES
============================================================

1. Generate code that works with the OTHER files listed
   in the project plan.

2. NEVER invent modules that are not present in the project plan.

3. NEVER invent imports.

4. Before importing a project-local module, verify that its
   exact path exists in the "ALL PLANNED FILES" list.

5. Preserve the exact package structure.

6. Preserve the exact technology stack.

7. Do not substitute technologies.

8. Use correct relative/absolute imports for the selected
   language and framework.

9. Every external package imported by this file must appear
   in the project's dependency configuration.

10. Do not import a dependency merely because it is commonly
    used. Only import packages actually required.

============================================================
PYTHON IMPORT RULES
============================================================

If this is a Python project:

1. Use the actual package structure from the plan.

2. Prefer explicit imports such as:

   from app.database import ...
   from app.models import ...
   from app.schemas import ...

   ONLY if those exact files exist.

3. Do NOT write:

   from database import ...
   from models import ...
   from schemas import ...
   from middleware import ...

   unless those exact root-level files exist.

4. Do not invent:
   database.py
   models.py
   schemas.py
   middleware.py
   auth.py

   if they are not included in the project plan.

5. If app/ is the package root, ensure imports use app.*

6. If a package directory is planned, its __init__.py must
   exist when required by the selected Python packaging layout.

7. FastAPI projects must expose the actual FastAPI application
   from the planned entry module.

8. Flask projects must expose the actual Flask application
   from the planned entry module.

============================================================
DATABASE RULES
============================================================

1. Use ONLY the database selected in the architecture.

2. Do not silently switch databases.

3. Database imports must correspond to actual generated files.

4. Database configuration must use environment variables.

5. For MongoDB, keep the MongoClient and selected database as
    separate variables. For example:

    client = MongoClient(mongodb_uri)
    db = client[database_name]

    Never assign the database object back to client. Any close_db
    or close_database helper must call client.close() on the
    MongoClient, and must not call is_closed or close on db.

6. Never hard-code passwords, API keys or secrets.

7. If the application uses a database session/connection
   helper, that helper must exist in the project plan.

8. Models/entities must match the database schema.

============================================================
AUTHENTICATION RULES
============================================================

If authentication is required:

Implement the actual authentication mechanism selected
by the architecture.

It must be consistent across:

- registration
- password hashing
- login
- token/session creation
- protected routes
- current-user lookup
- logout/session invalidation where applicable

Do not claim authentication exists unless this file actually
implements the part assigned to this file.

Do not invent imports such as:

from app.auth import ...
from app.middleware import ...

unless those exact files are present in the plan.

============================================================
API CONSISTENCY RULES
============================================================

If this is a backend file:

- Implement only endpoints described in the architecture.
- Use the actual database/models.
- Use the actual schemas.
- Use the actual authentication mechanism.
- Return consistent response structures.

If this is frontend code:

- Call only backend endpoints listed in the architecture.
- Use the exact HTTP methods and paths.
- Handle loading states.
- Handle errors.
- Handle empty states.
- Handle successful responses.
- Do not create fake API calls.

============================================================
DEPENDENCY RULES
============================================================

Every external import must have a corresponding dependency.

Examples:

Python:
fastapi
uvicorn
sqlalchemy
pydantic
python-jose
passlib/bcrypt/etc. depending on the architecture

Node:
express
cors
dotenv
jsonwebtoken
bcrypt
etc.

Java:
dependencies must be declared in pom.xml/build.gradle.

Do not import unused dependencies.

Do not create fake package names.

============================================================
FRONTEND QUALITY RULES
============================================================

For frontend files:

- Build a real usable interface.
- Responsive layout.
- Clear navigation.
- Accessible forms.
- Validation.
- Loading states.
- Error states.
- Empty states.
- Project-specific UI.
- Real API integration.
- No fake buttons.
- No dead links.
- No TODO placeholders.

============================================================
CODE QUALITY RULES
============================================================

1. Generate complete code.

2. Do not generate pseudocode.

3. Do not generate placeholders.

4. Do not use:

   TODO
   FIXME
   implement later
   ...

   as substitutes for required implementation.

5. Close every:
   - function
   - class
   - object
   - array
   - string
   - parenthesis
   - JSX tag
   - callback
   - conditional block

6. Keep syntax valid.

7. Do not include markdown code fences.

8. Do not explain the code.

9. Do not include the file path.

10. Return ONLY the raw contents of the requested file.

============================================================
IMPORTANT
============================================================

This file will be combined with all the other files generated
from the SAME project plan.

Therefore:

DO NOT redesign the project.

DO NOT create new modules.

DO NOT invent exports.

DO NOT invent APIs.

DO NOT invent database entities.

DO NOT invent authentication.

DO NOT assume a different framework.

Use ONLY the architecture and project plan supplied above.

============================================================
FINAL OUTPUT
============================================================

Return ONLY the complete raw contents of:

{current_path}

No markdown fences.
No explanation.
No filename.
No JSON wrapper unless JSON is the actual file format.
"""

    content = generate_text(prompt)

    # --------------------------------------------------------
    # Remove accidental markdown fences
    # --------------------------------------------------------

    content = str(
        content or ""
    ).strip()

    if content.startswith("```"):
        lines = content.splitlines()

        if lines:
            lines = lines[1:]

        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]

        content = "\n".join(
            lines
        ).strip()

    # --------------------------------------------------------
    # Return generated file
    # --------------------------------------------------------

    return {
        "path": current_path,
        "language": current_language,
        "content": content,
    }