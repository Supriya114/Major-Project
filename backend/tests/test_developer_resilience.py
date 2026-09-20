from app.services import developer_service


def test_developer_plan_has_fallback_when_llm_fails(monkeypatch):
    monkeypatch.setattr(
        developer_service,
        "generate_json",
        lambda prompt, schema=None: (_ for _ in ()).throw(RuntimeError("provider unavailable")),
    )
    result = developer_service.generate_project_plan(
        "College Event Management System",
        "Manage college events.",
        {"technology_stack": {"frontend": "React + Vite", "backend": "FastAPI + Python", "database": "MongoDB"}},
        {"decision": "APPROVED"},
        {"technology_stack": {"frontend": "React + Vite", "backend": "FastAPI + Python", "database": "MongoDB"}},
    )
    paths = {item["path"] for item in result["files"]}
    assert "frontend/package.json" in paths
    assert "frontend/src/App.jsx" in paths
    assert "backend/app/main.py" in paths
    assert all(item["path"] and item["purpose"] for item in result["files"])
