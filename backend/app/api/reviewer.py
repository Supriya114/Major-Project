from datetime import datetime, timezone

from bson import ObjectId
from fastapi import APIRouter, HTTPException

from app.database.mongodb import get_database
from app.services.ai_service import generate_json


router = APIRouter(
    prefix="/api/projects",
    tags=["Reviewer"],
)


REVIEW_SCHEMA = {
    "type": "object",
    "properties": {
        "quality_score": {
            "type": "number"
        },
        "security_score": {
            "type": "number"
        },
        "maintainability_score": {
            "type": "number"
        },
        "architecture_compliance": {
            "type": "string"
        },
        "summary": {
            "type": "string"
        },
        "findings": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "severity": {
                        "type": "string"
                    },
                    "title": {
                        "type": "string"
                    },
                    "description": {
                        "type": "string"
                    },
                    "suggestion": {
                        "type": "string"
                    }
                },
                "required": [
                    "severity",
                    "title",
                    "description",
                    "suggestion"
                ]
            }
        },
        "improvement_suggestions": {
            "type": "array",
            "items": {
                "type": "string"
            }
        },
        "recommendation": {
            "type": "string"
        }
    },
    "required": [
        "quality_score",
        "security_score",
        "maintainability_score",
        "architecture_compliance",
        "summary",
        "findings",
        "improvement_suggestions",
        "recommendation"
    ]
}


def _fallback_review(developer_project: dict, tester_summary: str, tester_run: dict) -> dict:
    """Create an honest review when configured AI providers are unavailable."""
    files = developer_project.get("files", []) or []
    non_empty_files = sum(1 for item in files if str(item.get("content", "")).strip())
    failed_tests = int(tester_run.get("failed_count", 0) or 0)
    error_tests = int(tester_run.get("error_count", 0) or 0)
    findings = []

    if non_empty_files != len(files):
        findings.append({
            "severity": "HIGH",
            "title": "Empty generated files detected",
            "description": f"{len(files) - non_empty_files} generated file(s) contain no content.",
            "suggestion": "Regenerate the affected files before approving the project.",
        })
    if failed_tests or error_tests:
        findings.append({
            "severity": "HIGH",
            "title": "Tester reported failures",
            "description": f"Tester results include {failed_tests} failed and {error_tests} error test(s).",
            "suggestion": "Resolve failing tests and run the approved test suite again.",
        })

    return {
        "quality_score": 80 if not findings else 55,
        "security_score": 70,
        "maintainability_score": 75,
        "architecture_compliance": "Reviewed against the stored project structure and technology stack.",
        "summary": f"Deterministic review completed for {len(files)} generated file(s). {tester_summary}",
        "findings": findings,
        "improvement_suggestions": [
            "Review environment configuration before deployment.",
            "Keep the Tester result approved and passing before final release.",
        ],
        "recommendation": "REQUEST_FIXES" if findings else "APPROVE",
    }


def _get_project(db, project_id):
    try:
        object_id = ObjectId(project_id)
    except Exception:
        raise HTTPException(
            status_code=400,
            detail="Invalid project ID."
        )

    project = db.projects.find_one({
        "_id": object_id
    })

    if not project:
        raise HTTPException(
            status_code=404,
            detail="Project not found."
        )

    return project


def _get_developer_project(db, project_id):
    developer_project = db.developer_projects.find_one(
        {"project_id": project_id},
        sort=[("version", -1)]
    )

    if not developer_project:
        raise HTTPException(
            status_code=400,
            detail="Generate the Developer project first."
        )

    return developer_project


@router.post("/{project_id}/reviewer/generate")
def generate_review(project_id: str):

    db = get_database()

    _get_project(db, project_id)

    developer_project = _get_developer_project(
        db,
        project_id
    )

    tester_run = db.tester_runs.find_one(
        {"project_id": project_id},
        sort=[("version", -1)]
    )

    if not tester_run:
        raise HTTPException(status_code=400, detail="Tester execution is required before Reviewer analysis.")

    execution = tester_run.get("execution") or {}
    if (
        tester_run.get("approval_status") != "APPROVED"
        or execution.get("status") != "PASSED"
        or int(tester_run.get("failed_count", 0) or 0)
        or int(tester_run.get("error_count", 0) or 0)
        or int(tester_run.get("not_executable_count", 0) or 0)
    ):
        raise HTTPException(
            status_code=400,
            detail="Reviewer requires a human-approved Tester run with all executable tests passing.",
        )

    files = developer_project.get("files", [])

    if not files:
        raise HTTPException(
            status_code=400,
            detail="Developer project contains no files."
        )

    source_code = []

    for file_data in files:
        path = file_data.get("path", "")
        content = file_data.get("content", "")

        source_code.append(
            f"\n===== {path} =====\n{content}"
        )

    tester_summary = "No Tester execution result available."

    if tester_run:
        execution = tester_run.get(
            "execution",
            {}
        ) or {}

        tester_summary = (
            f"Tester status: {tester_run.get('status', 'UNKNOWN')}\n"
            f"Passed: {tester_run.get('passed_count', 0)}\n"
            f"Failed: {tester_run.get('failed_count', 0)}\n"
            f"Errors: {tester_run.get('error_count', 0)}\n"
            f"Not executable: {tester_run.get('not_executable_count', 0)}\n"
            f"Framework: {execution.get('framework', 'N/A')}"
        )

    prompt = f"""
You are the Reviewer Agent in an AI Software Development Team.

Review the generated software project for:

1. Code quality
2. Security
3. Maintainability
4. Architecture compliance
5. Reliability based on Tester results

Project ID:
{project_id}

Developer project summary:
{developer_project.get('project_summary', '')}

Technology stack:
{developer_project.get('technology_stack', {})}

Project structure:
{developer_project.get('project_structure', [])}

Tester results:
{tester_summary}

Generated source files:
{''.join(source_code)}

IMPORTANT RULES:

- Review the actual generated source code.
- Do not invent files or functionality.
- Identify real issues visible in the supplied code.
- Severity must be one of:
  CRITICAL, HIGH, MEDIUM, LOW, INFO.
- Give practical improvement suggestions.
- A project may be recommended for approval even when minor issues exist.
- If tests failed, mention that in the review.
- Return ONLY valid JSON matching the supplied schema.
"""

    now = datetime.now(timezone.utc)

    try:
        review = generate_json(
            prompt,
            schema=REVIEW_SCHEMA
        )
    except Exception as exc:
        print(f"[Reviewer] Structured generation failed; using deterministic fallback: {exc}")
        review = _fallback_review(developer_project, tester_summary, tester_run)

    review_document = {
        "project_id": project_id,
        "version": (
            db.reviewer_runs.count_documents(
                {"project_id": project_id}
            ) + 1
        ),
        "review": review,
        "tester_summary": tester_summary,
        "status": "COMPLETED",
        "created_at": now,
        "updated_at": now,
    }

    result = db.reviewer_runs.insert_one(
        review_document
    )

    db.projects.update_one(
        {"_id": ObjectId(project_id)},
        {
            "$set": {
                "status": "REVIEW_READY",
                "current_agent": "REVIEWER",
                "updated_at": now,
            }
        }
    )

    db.agent_activity.insert_one({
        "project_id": project_id,
        "agent": "REVIEWER",
        "event": "REVIEW_COMPLETED",
        "message": (
            "Reviewer Agent completed the code review."
        ),
        "created_at": now,
    })

    saved = db.reviewer_runs.find_one({
        "_id": result.inserted_id
    })

    saved["_id"] = str(saved["_id"])

    return saved


@router.get("/{project_id}/reviewer")
def get_review(project_id: str):

    db = get_database()

    _get_project(db, project_id)

    review = db.reviewer_runs.find_one(
        {"project_id": project_id},
        sort=[("version", -1)]
    )

    if not review:
        return {
            "status": "NOT_GENERATED"
        }

    review["_id"] = str(review["_id"])

    return review


@router.post("/{project_id}/reviewer/approve")
def approve_review(project_id: str):
    """Persist human approval for the latest reviewer run."""

    db = get_database()
    project = _get_project(db, project_id)

    review = db.reviewer_runs.find_one(
        {"project_id": project_id},
        sort=[("version", -1)],
    )

    if not review:
        raise HTTPException(
            status_code=400,
            detail="Reviewer report is required before approval.",
        )

    now = datetime.now(timezone.utc)

    db.reviewer_runs.update_one(
        {"_id": review["_id"]},
        {
            "$set": {
                "approval_status": "APPROVED",
                "approved_at": now,
                "updated_at": now,
            }
        },
    )

    db.projects.update_one(
        {"_id": project["_id"]},
        {
            "$set": {
                "status": "PROJECT_COMPLETED",
                "current_agent": "HUMAN_APPROVAL",
                "updated_at": now,
            }
        },
    )

    db.agent_activity.insert_one({
        "project_id": project_id,
        "agent": "HUMAN",
        "event": "REVIEW_APPROVED",
        "message": "Human approved the generated project after review.",
        "created_at": now,
    })

    saved = db.reviewer_runs.find_one({"_id": review["_id"]})
    saved["_id"] = str(saved["_id"])
    return saved