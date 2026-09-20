from datetime import datetime, timezone
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from app.database.mongodb import get_database
from app.utils.serialization import serialize_for_json

router = APIRouter(prefix="/api/projects", tags=["Projects"])


class ProjectCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    description: str = Field(default="", max_length=5000)


@router.post("")
def create_project(payload: ProjectCreate):
    db = get_database()

    document = {
        "name": payload.name.strip(),
        "description": payload.description.strip(),
        "status": "CREATED",
        "current_agent": "PRODUCT_MANAGER",
        "created_at": datetime.now(timezone.utc),
        "updated_at": datetime.now(timezone.utc),
    }

    result = db.projects.insert_one(document)
    document["_id"] = result.inserted_id
    return serialize_for_json(document)


@router.get("")
def list_projects():
    db = get_database()

    projects = [serialize_for_json(project) for project in db.projects.find().sort("created_at", -1)]
    return {"projects": projects}


@router.get("/{project_id}")
def get_project(project_id: str):
    from bson import ObjectId

    db = get_database()

    try:
        document = db.projects.find_one({"_id": ObjectId(project_id)})
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid project ID")

    if not document:
        raise HTTPException(status_code=404, detail="Project not found")

    return serialize_for_json(document)


@router.delete("/{project_id}")
def delete_project(project_id: str):
    from bson import ObjectId

    db = get_database()

    try:
        object_id = ObjectId(project_id)
    except Exception:
        raise HTTPException(
            status_code=400,
            detail="Invalid project ID"
        )

    project = db.projects.find_one({"_id": object_id})

    if not project:
        raise HTTPException(
            status_code=404,
            detail="Project not found"
        )

    # Delete the project
    db.projects.delete_one({"_id": object_id})

    # Delete related project data
    db.requirements.delete_many({"project_id": project_id})
    db.agent_activity.delete_many({"project_id": project_id})
    db.architectures.delete_many({"project_id": project_id})
    db.developer_opinions.delete_many({"project_id": project_id})
    db.developer_projects.delete_many({"project_id": project_id})
    db.developer_fix_requests.delete_many({"project_id": project_id})
    db.tester_runs.delete_many({"project_id": project_id})
    db.reviewer_runs.delete_many({"project_id": project_id})

    return {
        "message": "Project deleted successfully",
        "project_id": project_id
    }
    
    
    