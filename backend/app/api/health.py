from fastapi import APIRouter
from app.database.mongodb import get_database

router = APIRouter(prefix="/api", tags=["Health"])


@router.get("/health")
def health():
    try:
        db = get_database()
        db.command("ping")
        return {
            "status": "ok",
            "database": "connected",
            "service": "AI Software Development Team API",
        }
    except Exception as exc:
        return {
            "status": "degraded",
            "database": "disconnected",
            "service": "AI Software Development Team API",
            "detail": str(exc),
        }
