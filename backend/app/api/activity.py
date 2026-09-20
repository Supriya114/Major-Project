from bson import ObjectId
from fastapi import APIRouter
from app.database.mongodb import get_database
from app.utils.serialization import serialize_for_json

router = APIRouter(prefix="/api/projects", tags=["Activity"])


def serialize(value):
    return serialize_for_json(value)


@router.get("/{project_id}/activity")
def get_activity(project_id: str):
    db = get_database()
    events = list(
        db.agent_activity.find({"project_id": project_id}).sort("created_at", 1)
    )
    return {"events": serialize(events)}
