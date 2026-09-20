from datetime import datetime, timezone

from bson import ObjectId
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.database.mongodb import get_database
from app.services.ai_service import generate_architecture
from app.utils.serialization import serialize_for_json


router = APIRouter(
    prefix="/api/projects",
    tags=["architecture"],
)
class ArchitectureRevisionRequest(BaseModel):
    feedback: str

def serialize(value):
    return serialize_for_json(value)


def get_project(db, project_id):
    try:
        return db.projects.find_one({
            "_id": ObjectId(project_id)
        })
    except Exception:
        return None


@router.post("/{project_id}/architecture/generate")
def generate_project_architecture(project_id: str):

    db = get_database()

    project = get_project(db, project_id)

    if not project:
        raise HTTPException(
            status_code=404,
            detail="Project not found."
        )

    requirements = db.requirements.find_one({
        "project_id": project_id
    })

    if not requirements:
        raise HTTPException(
            status_code=400,
            detail="Generate Product Manager requirements first."
        )

    developer_opinion = db.developer_opinions.find_one(
        {
            "project_id": project_id,
            "stage": "REQUIREMENTS",
        },
        sort=[("created_at", -1)],
    )

    if not developer_opinion:
        raise HTTPException(
            status_code=400,
            detail="Developer feasibility opinion is required before architecture."
        )

    db.agent_activity.insert_one({
        "project_id": project_id,
        "agent": "ARCHITECT",
        "event": "ARCHITECTURE_GENERATION_STARTED",
        "message": "Architect started technical design.",
        "created_at": datetime.now(timezone.utc),
    })

    try:
        architecture = generate_architecture(
            project["name"],
            project.get("description", ""),
            serialize(requirements),
            serialize(developer_opinion),
        )

    except Exception as exc:

        db.agent_activity.insert_one({
            "project_id": project_id,
            "agent": "ARCHITECT",
            "event": "ARCHITECTURE_GENERATION_FAILED",
            "message": str(exc),
            "created_at": datetime.now(timezone.utc),
        })

        raise HTTPException(
            status_code=502,
            detail=str(exc),
        )

    document = {
    "project_id": project_id,
    **architecture,
    "version": 1,
    "changes_made": [
        "Initial architecture created from the Product Manager requirements and Developer feasibility review."
    ],
    "created_at": datetime.now(timezone.utc),
}

    result = db.architectures.insert_one(document)

    document["_id"] = result.inserted_id

    db.projects.update_one(
        {"_id": ObjectId(project_id)},
        {
            "$set": {
                "status": "ARCHITECTURE_READY",
                "current_agent": "ARCHITECT",
                "updated_at": datetime.now(timezone.utc),
            }
        },
    )

    db.agent_activity.insert_one({
        "project_id": project_id,
        "agent": "ARCHITECT",
        "event": "ARCHITECTURE_GENERATION_COMPLETED",
        "message": "Technical architecture generated.",
        "created_at": datetime.now(timezone.utc),
    })

    return serialize(document)


@router.get("/{project_id}/architecture")
def get_project_architecture(project_id: str):

    db = get_database()

    project = get_project(db, project_id)

    if not project:
        raise HTTPException(
            status_code=404,
            detail="Project not found."
        )

    architecture = db.architectures.find_one(
        {"project_id": project_id},
        sort=[("created_at", -1)],
    )

    if not architecture:
        return {
            "status": "NOT_GENERATED"
        }

    return serialize(architecture)

@router.post("/{project_id}/architecture/revision")
def request_architecture_revision(
    project_id: str,
    payload: ArchitectureRevisionRequest,
):
    db = get_database()

    try:
        object_id = ObjectId(project_id)
    except Exception:
        raise HTTPException(
            status_code=400,
            detail="Invalid project ID",
        )

    project = db.projects.find_one({"_id": object_id})

    if not project:
        raise HTTPException(
            status_code=404,
            detail="Project not found",
        )

    requirements = db.requirements.find_one(
        {"project_id": project_id}
    )

    if not requirements:
        raise HTTPException(
            status_code=400,
            detail="Requirements are required before revising architecture.",
        )

    developer_opinion = db.developer_opinions.find_one(
        {
            "project_id": project_id,
            "stage": "REQUIREMENTS",
        },
        sort=[("created_at", -1)],
    )

    if not developer_opinion:
        raise HTTPException(
            status_code=400,
            detail="Developer feasibility opinion is required.",
        )

    previous_architecture = db.architectures.find_one(
        {"project_id": project_id},
        sort=[("created_at", -1)],
    )

    feedback = payload.feedback.strip()

    if not feedback:
        raise HTTPException(
            status_code=400,
            detail="Revision feedback cannot be empty.",
        )

    now = datetime.now(timezone.utc)

    # Record that the human requested a revision
    db.agent_activity.insert_one({
        "project_id": project_id,
        "agent": "HUMAN",
        "event": "ARCHITECTURE_REVISION_REQUESTED",
        "message": f"Human requested architecture revision: {feedback}",
        "created_at": now,
    })

    # Tell the project that Architect is working again
    db.projects.update_one(
        {"_id": object_id},
        {
            "$set": {
                "status": "ARCHITECTURE_REVISION_REQUESTED",
                "current_agent": "ARCHITECT",
                "updated_at": now,
            }
        },
    )

    try:
        revised_architecture = generate_architecture(
    project["name"],
    project.get("description", ""),
    serialize(requirements),
    serialize(developer_opinion),
    revision_feedback=feedback,
    previous_architecture=serialize(previous_architecture)
    if previous_architecture
    else None,
)
    except Exception as exc:
        db.agent_activity.insert_one({
            "project_id": project_id,
            "agent": "ARCHITECT",
            "event": "ARCHITECTURE_REVISION_FAILED",
            "message": str(exc),
            "created_at": datetime.now(timezone.utc),
        })

        raise HTTPException(
            status_code=502,
            detail=str(exc),
        )

    # Determine the next architecture version
    previous_version = 1

    if previous_architecture:
        previous_version = previous_architecture.get("version", 1)

    new_version = previous_version + 1

    document = {
        "project_id": project_id,
        **revised_architecture,
        "version": new_version,
        "revision_feedback": feedback,
        "created_at": datetime.now(timezone.utc),
    }

    result = db.architectures.insert_one(document)
    document["_id"] = result.inserted_id

    # Update project state
    db.projects.update_one(
        {"_id": object_id},
        {
            "$set": {
                "status": "ARCHITECTURE_READY",
                "current_agent": "ARCHITECT",
                "updated_at": datetime.now(timezone.utc),
            }
        },
    )

    # Record successful revision
    db.agent_activity.insert_one({
        "project_id": project_id,
        "agent": "ARCHITECT",
        "event": "ARCHITECTURE_REVISION_COMPLETED",
        "message": f"Architect generated revised architecture v{new_version}.",
        "created_at": datetime.now(timezone.utc),
    })

    return serialize(document)   
    
    
@router.post("/{project_id}/architecture/approve")
def approve_architecture(project_id: str):
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

    architecture = db.architectures.find_one(
        {"project_id": project_id},
        sort=[("created_at", -1)],
    )

    if not architecture:
        raise HTTPException(
            status_code=400,
            detail="Generate architecture before approving it."
        )

    now = datetime.now(timezone.utc)

    db.projects.update_one(
        {"_id": object_id},
        {
            "$set": {
                "status": "ARCHITECTURE_APPROVED",
                "current_agent": "DEVELOPER",
                "updated_at": now,
            }
        },
    )

    db.agent_activity.insert_one({
        "project_id": project_id,
        "agent": "HUMAN",
        "event": "ARCHITECTURE_APPROVED",
        "message": "Human approved the architecture. Developer can now generate source code.",
        "created_at": now,
    })

    return {
        "message": "Architecture approved",
        "status": "ARCHITECTURE_APPROVED",
        "current_agent": "DEVELOPER",
    }
    
@router.get("/{project_id}/architecture/versions")
def get_architecture_versions(project_id: str):
    db = get_database()

    try:
        object_id = ObjectId(project_id)
    except Exception:
        raise HTTPException(
            status_code=400,
            detail="Invalid project ID",
        )

    project = db.projects.find_one({"_id": object_id})

    if not project:
        raise HTTPException(
            status_code=404,
            detail="Project not found.",
        )

    architectures = list(
        db.architectures.find(
            {"project_id": project_id}
        ).sort("created_at", -1)
    )

    return {
        "versions": [
            serialize(architecture)
            for architecture in architectures
        ]
    }
    
@router.get("/{project_id}/architecture/versions/{version}")
def get_architecture_version(
    project_id: str,
    version: int,
):
    db = get_database()

    try:
        object_id = ObjectId(project_id)
    except Exception:
        raise HTTPException(
            status_code=400,
            detail="Invalid project ID",
        )

    project = db.projects.find_one({"_id": object_id})

    if not project:
        raise HTTPException(
            status_code=404,
            detail="Project not found.",
        )

    architecture = db.architectures.find_one({
        "project_id": project_id,
        "version": version,
    })

    if not architecture:
        raise HTTPException(
            status_code=404,
            detail=f"Architecture version {version} not found.",
        )

    return serialize(architecture)

@router.post("/{project_id}/architecture/restore/{version}")
def restore_architecture_version(
    project_id: str,
    version: int,
):
    db = get_database()

    try:
        object_id = ObjectId(project_id)
    except Exception:
        raise HTTPException(
            status_code=400,
            detail="Invalid project ID",
        )

    project = db.projects.find_one({"_id": object_id})

    if not project:
        raise HTTPException(
            status_code=404,
            detail="Project not found.",
        )

    source_architecture = db.architectures.find_one({
        "project_id": project_id,
        "version": version,
    })

    if not source_architecture:
        raise HTTPException(
            status_code=404,
            detail=f"Architecture version {version} not found.",
        )

    latest_architecture = db.architectures.find_one(
        {"project_id": project_id},
        sort=[("created_at", -1)],
    )

    latest_version = 0

    if latest_architecture:
        latest_version = latest_architecture.get(
            "version",
            0,
        )

    new_version = latest_version + 1

    now = datetime.now(timezone.utc)

    restored_architecture = {
        key: value
        for key, value in source_architecture.items()
        if key not in {
            "_id",
            "created_at",
            "version",
            "revision_feedback",
            "changes_made",
            "restored_from_version",
        }
    }

    restored_architecture.update({
        "project_id": project_id,
        "version": new_version,
        "restored_from_version": version,
        "revision_feedback": (
            f"Architecture restored from Version {version}."
        ),
        "changes_made": [
            f"Restored architecture from Version {version}.",
            (
                f"Version {new_version} is now the active architecture "
                f"while all previous versions remain available."
            ),
        ],
        "created_at": now,
    })

    result = db.architectures.insert_one(
        restored_architecture
    )

    restored_architecture["_id"] = result.inserted_id

    db.projects.update_one(
        {"_id": object_id},
        {
            "$set": {
                "status": "ARCHITECTURE_READY",
                "current_agent": "ARCHITECT",
                "updated_at": now,
            }
        },
    )

    db.agent_activity.insert_one({
        "project_id": project_id,
        "agent": "HUMAN",
        "event": "ARCHITECTURE_VERSION_RESTORED",
        "message": (
            f"Human restored architecture Version {version} "
            f"as new Version {new_version}."
        ),
        "created_at": now,
    })

    return serialize(restored_architecture)