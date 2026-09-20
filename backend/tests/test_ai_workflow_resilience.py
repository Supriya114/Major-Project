from bson import ObjectId

from app.api import tester
from app.services import ai_service


def test_recursive_schema_validation_catches_nested_required_fields():
    value = {
        "project_summary": "demo",
        "technology_stack": {
            "frontend": "React",
            "backend": "FastAPI",
            "database": "MongoDB",
            "api": "REST",
            "authentication": "JWT",
        },
        "suggested_stack": [],
        "functional_requirements": [],
        "non_functional_requirements": [],
        "user_stories": [],
        "acceptance_criteria": [],
        "assumptions": [],
        "clarification_questions": [],
    }
    ok, reason = ai_service._validate_value(value, ai_service.PM_SCHEMA)
    assert not ok
    assert "other_tools" in reason


def test_schema_coercion_fills_nested_empty_metadata():
    value = {
        "project_summary": "demo",
        "technology_stack": {
            "frontend": "React",
            "backend": "FastAPI",
            "database": "MongoDB",
            "api": "REST",
            "authentication": "JWT",
        },
        "suggested_stack": [],
        "functional_requirements": [],
        "non_functional_requirements": [],
        "user_stories": [],
        "acceptance_criteria": [],
        "assumptions": [],
        "clarification_questions": [],
    }
    normalized = ai_service._coerce_to_schema(value, ai_service.PM_SCHEMA)
    ok, reason = ai_service._validate_value(normalized, ai_service.PM_SCHEMA)
    assert ok, reason
    assert normalized["technology_stack"]["other_tools"] == []
    assert normalized["technology_stack"]["source"] == ""


def test_pm_has_deterministic_fallback_when_llm_is_malformed(monkeypatch):
    monkeypatch.setattr(ai_service, "_generate", lambda prompt, schema=None: "not valid json")
    result = ai_service.generate_requirements(
        "College Event Management System",
        "Manage college events for students and administrators.",
    )
    assert result["technology_stack"]["source"] == "AI_FALLBACK"
    assert result["functional_requirements"]
    assert result["user_stories"]


def test_architecture_fallback_is_complete(monkeypatch):
    monkeypatch.setattr(ai_service, "_generate", lambda prompt, schema=None: "not valid json")
    requirements = ai_service.generate_requirements(
        "College Event Management System",
        "Manage college events.",
    )
    result = ai_service.generate_architecture(
        "College Event Management System",
        "Manage college events.",
        requirements,
        {"decision": "APPROVED"},
    )
    assert result["technology_stack"]["frontend"]
    assert result["modules"]
    assert result["api_design"]
    assert result["folder_structure"]


def test_tester_falls_back_when_llm_returns_no_executable_tests(monkeypatch):
    monkeypatch.setattr(
        "app.api.tester.generate_text",
        lambda prompt: "this is not test file output",
    )

    developer_project = {
        "files": [
            {
                "path": "app/main.py",
                "content": "from fastapi import FastAPI\napp = FastAPI()\n@app.get('/')\ndef root():\n    return {'ok': True}\n",
            },
            {
                "path": "requirements.txt",
                "content": "fastapi\n",
            },
        ]
    }

    result = tester.generate_executable_tests(
        {"name": "Demo", "description": "Demo app"},
        {"summary": "Demo requirements"},
        {"summary": "Demo architecture"},
        developer_project,
        [{
            "test_id": "AI-001",
            "title": "Smoke test",
            "description": "Smoke test description",
            "type": "SMOKE",
            "priority": "HIGH",
            "steps": ["Call the app"],
            "expected_result": "It responds successfully.",
        }],
    )

    assert result["test_files"]
    assert not result["validation_errors"]
    assert result["test_files"][0]["path"].startswith("tests/")


def test_run_tester_recovers_stale_empty_test_files(monkeypatch):
    class FakeCollection:
        def __init__(self, document):
            self.document = document

        def find_one(self, *args, **kwargs):
            return self.document

        def insert_one(self, *args, **kwargs):
            payload = args[0] if args else {}
            if isinstance(self.document, dict):
                self.document.update(payload)
            return type("Inserted", (), {"inserted_id": ObjectId()})()

        def update_one(self, *args, **kwargs):
            payload = args[1] if len(args) > 1 else {}
            changes = payload.get("$set", {})
            self.document["test_files"] = changes.get("test_files", self.document.get("test_files"))
            self.document["updated_at"] = changes.get("updated_at")
            return None

    project_id = str(ObjectId())
    developer_project = {
        "project_id": project_id,
        "version": 1,
        "files": [
            {"path": "app/main.py", "content": "from fastapi import FastAPI\napp = FastAPI()\n@app.get('/')\ndef root():\n    return {'ok': True}\n"},
            {"path": "requirements.txt", "content": "fastapi\n"},
        ],
    }
    tester_run = {"_id": ObjectId(), "project_id": project_id, "test_cases": [{"test_id": "AI-001"}], "test_files": []}

    class FakeDB:
        def __init__(self):
            self.tester_runs = FakeCollection(tester_run)
            self.developer_projects = FakeCollection(developer_project)
            self.projects = FakeCollection({"_id": ObjectId(project_id)})
            self.agent_activity = FakeCollection({})

    fake_db = FakeDB()
    monkeypatch.setattr(tester, "get_database", lambda: fake_db)
    monkeypatch.setattr(tester, "_get_project", lambda db, project_id: {"_id": ObjectId(project_id)})

    result = tester.run_tester_tests(project_id)

    assert result["status"] != "NO_EXECUTABLE_TESTS"
    assert result["execution"]["status"] in {"PASSED", "FAILED", "ERROR"}
    assert fake_db.tester_runs.document["test_files"]
