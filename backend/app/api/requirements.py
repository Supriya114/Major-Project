from datetime import datetime, timezone
from bson import ObjectId
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Any
from app.database.mongodb import get_database
from app.services.ai_service import generate_requirements, generate_developer_opinion
from app.utils.serialization import serialize_for_json

router = APIRouter(prefix="/api/projects", tags=["Requirements"])

class RequirementsUpdate(BaseModel):
    project_summary: str
    functional_requirements: list[dict[str, Any]]
    non_functional_requirements: list[dict[str, Any]]
    user_stories: list[dict[str, Any]]
    acceptance_criteria: list[str]
    assumptions: list[str]
    clarification_questions: list[str]
    
def _project(db, project_id: str):
    try:
        return db.projects.find_one({"_id": ObjectId(project_id)})
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid project ID")


def _serialize(value):
    return serialize_for_json(value)


@router.post("/{project_id}/requirements/generate")
def generate_project_requirements(project_id: str):
    db = get_database()
    project = _project(db, project_id)

    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    now = datetime.now(timezone.utc)
    db.agent_activity.insert_one({
        "project_id": project_id,
        "agent": "PRODUCT_MANAGER",
        "event": "PM_STARTED",
        "message": "Product Manager started requirement analysis.",
        "created_at": now,
    })

    try:
        requirements = generate_requirements(
            project["name"],
            project.get("description", ""),
        )
    except Exception as exc:
        db.agent_activity.insert_one({
            "project_id": project_id,
            "agent": "PRODUCT_MANAGER",
            "event": "PM_FAILED",
            "message": str(exc),
            "created_at": datetime.now(timezone.utc),
        })
        raise HTTPException(status_code=502, detail=str(exc))

    db.requirements.update_one(
        {"project_id": project_id},
        {
            "$set": {
                "project_id": project_id,
                **requirements,
                "updated_at": datetime.now(timezone.utc),
            }
        },
        upsert=True,
    )

    db.projects.update_one(
        {"_id": ObjectId(project_id)},
        {
            "$set": {
                "status": "REQUIREMENTS_READY",
                "current_agent": "DEVELOPER",
                "updated_at": datetime.now(timezone.utc),
            }
        },
    )

    db.agent_activity.insert_one({
        "project_id": project_id,
        "agent": "PRODUCT_MANAGER",
        "event": "PM_REQUIREMENTS_GENERATED",
        "message": "Requirements specification generated and stored.",
        "created_at": datetime.now(timezone.utc),
    })

    return _serialize(requirements)


@router.get("/{project_id}/requirements")
def get_requirements(project_id: str):
    db = get_database()
    _project_or_error = _project(db, project_id)

    if not _project_or_error:
        raise HTTPException(status_code=404, detail="Project not found")

    requirements = db.requirements.find_one({"project_id": project_id})
    if not requirements:
        return {"status": "NOT_GENERATED"}

    return _serialize(requirements)
@router.put("/{project_id}/requirements")
def update_project_requirements(
    project_id: str,
    payload: RequirementsUpdate,
):
    db = get_database()
    project = _project(db, project_id)

    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    updated = {
        "project_id": project_id,
        "project_summary": payload.project_summary,
        "functional_requirements": payload.functional_requirements,
        "non_functional_requirements": payload.non_functional_requirements,
        "user_stories": payload.user_stories,
        "acceptance_criteria": payload.acceptance_criteria,
        "assumptions": payload.assumptions,
        "clarification_questions": payload.clarification_questions,
        "updated_at": datetime.now(timezone.utc),
    }

    db.requirements.update_one(
        {"project_id": project_id},
        {"$set": updated},
        upsert=True,
    )

    # Record the human revision in the activity timeline
    db.agent_activity.insert_one({
        "project_id": project_id,
        "agent": "HUMAN",
        "event": "REQUIREMENTS_SENT_BACK",
        "message": "Human edited the requirements and sent them back for Developer review.",
        "created_at": datetime.now(timezone.utc),
    })

    db.projects.update_one(
        {"_id": ObjectId(project_id)},
        {
            "$set": {
                "status": "REQUIREMENTS_REVISED",
                "current_agent": "DEVELOPER",
                "updated_at": datetime.now(timezone.utc),
            }
        },
    )

    return _serialize(updated)

@router.post("/{project_id}/developer-opinion")
def create_developer_opinion(project_id: str):
    db = get_database()
    project = _project(db, project_id)

    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    requirements = db.requirements.find_one({"project_id": project_id})
    if not requirements:
        raise HTTPException(
            status_code=400,
            detail="Generate Product Manager requirements first.",
        )

    db.agent_activity.insert_one({
        "project_id": project_id,
        "agent": "DEVELOPER",
        "event": "DEVELOPER_FEASIBILITY_STARTED",
        "message": "Developer started feasibility review of the requirements.",
        "created_at": datetime.now(timezone.utc),
    })

    try:
        opinion = generate_developer_opinion(
            project["name"],
            project.get("description", ""),
            _serialize(requirements),
        )
    except Exception as exc:
        db.agent_activity.insert_one({
            "project_id": project_id,
            "agent": "DEVELOPER",
            "event": "DEVELOPER_FEASIBILITY_FAILED",
            "message": str(exc),
            "created_at": datetime.now(timezone.utc),
        })
        raise HTTPException(status_code=502, detail=str(exc))

    opinion_document = {
        "project_id": project_id,
        "stage": "REQUIREMENTS",
        **opinion,
        "created_at": datetime.now(timezone.utc),
    }

    db.developer_opinions.insert_one(opinion_document)

    db.projects.update_one(
        {"_id": ObjectId(project_id)},
        {
            "$set": {
                "status": "DEVELOPER_REVIEWED_REQUIREMENTS",
                "current_agent": "HUMAN_APPROVAL",
                "updated_at": datetime.now(timezone.utc),
            }
        },
    )

    db.agent_activity.insert_one({
        "project_id": project_id,
        "agent": "DEVELOPER",
        "event": "DEVELOPER_FEASIBILITY_COMPLETED",
        "message": f"Developer decision: {opinion.get('decision', 'UNKNOWN')}.",
        "created_at": datetime.now(timezone.utc),
    })

    return _serialize(opinion_document)


@router.get("/{project_id}/developer-opinion")
def get_developer_opinion(project_id: str):
    db = get_database()
    opinions = list(
        db.developer_opinions.find({"project_id": project_id}).sort("created_at", -1)
    )
    return {"opinions": _serialize(opinions)}


@router.post("/{project_id}/requirements/approve")
def approve_requirements(project_id: str):
    db = get_database()
    project = _project(db, project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    requirements = db.requirements.find_one({"project_id": project_id})
    opinion = db.developer_opinions.find_one({"project_id": project_id, "stage": "REQUIREMENTS"}, sort=[("created_at", -1)])
    if not requirements:
        raise HTTPException(status_code=400, detail="Generate requirements first.")
    if not opinion or opinion.get("decision") != "APPROVED":
        raise HTTPException(status_code=400, detail="Developer approval is required before continuing.")
    now = datetime.now(timezone.utc)
    db.requirements.update_one({"project_id": project_id}, {"$set": {"approval_status": "APPROVED", "approved_at": now, "updated_at": now}})
    db.projects.update_one({"_id": ObjectId(project_id)}, {"$set": {"status": "REQUIREMENTS_APPROVED", "current_agent": "ARCHITECT", "updated_at": now}})
    db.agent_activity.insert_one({"project_id": project_id, "agent": "HUMAN", "event": "REQUIREMENTS_APPROVED", "message": "Human approved requirements. Architect can continue.", "created_at": now})
    return {"status": "REQUIREMENTS_APPROVED", "current_agent": "ARCHITECT"}
