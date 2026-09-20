from app.services.project_validation import validate_project_files
from app.services.tester_service import _fallback_executable_tests, _fallback_test_cases


def _sample_project():
    return {
        "files": [
            {"path": "frontend/package.json", "content": '{"name":"demo","scripts":{"dev":"vite","build":"vite build"}}'},
            {"path": "frontend/src/main.jsx", "content": "import React from 'react';\nexport default function App(){ return <div>OK</div>; }"},
            {"path": "backend/main.py", "content": "def app():\n    return 'ok'\n"},
        ]
    }


def test_project_validation_rejects_empty_source():
    errors = validate_project_files([{"path": "frontend/src/Dashboard.jsx", "content": ""}])
    assert any("empty" in error.lower() for error in errors)


def test_fallback_tester_always_has_eight_project_wide_cases():
    project = _sample_project()
    cases = _fallback_test_cases(project)
    assert [case["test_id"] for case in cases] == [f"AI-{i:03d}" for i in range(1, 9)]


def test_fallback_executable_suite_covers_all_eight_cases():
    project = _sample_project()
    cases = _fallback_test_cases(project)
    files = _fallback_executable_tests(project, cases, "python-fastapi")
    ids = {test_id for item in files for test_id in item.get("test_ids", [])}
    assert ids == {f"AI-{i:03d}" for i in range(1, 9)}
    assert all(item["content"].strip() for item in files)


def test_preview_copy_removes_markdown_fences(tmp_path):
    from app.api.preview import _safe_write

    _safe_write(
        [{"path": "backend/app/routes.py", "content": "```python\ndef app():\n    return 'ok'\n```"}],
        str(tmp_path),
    )

    assert (tmp_path / "backend/app/routes.py").read_text(encoding="utf-8") == "def app():\n    return 'ok'\n"


def test_developer_file_generator_accepts_full_context_signature():
    import inspect
    from app.services.developer_service import generate_project_file

    params = list(inspect.signature(generate_project_file).parameters)
    assert params == [
        "project_name", "description", "requirements",
        "developer_opinion", "architecture", "project_plan", "file_info"
    ]
