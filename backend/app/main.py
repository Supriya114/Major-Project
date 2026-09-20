from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.health import router as health_router
from app.api.projects import router as projects_router
from app.api.requirements import router as requirements_router
from app.api.activity import router as activity_router
from app.api.architecture import router as architecture_router
from app.api import tester
from app.api.developer import recover_interrupted_generations
from app.database.mongodb import get_database

from app.api import (
    health,
    projects,
    requirements,
    architecture,
    activity,
    developer,
    reviewer,
    preview,
    export,
)

app = FastAPI(
    title="AI Software Development Team API",
    version="0.1.0",
    description="Backend foundation for the LLM-based multi-agent SDLC platform.",
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health_router)
app.include_router(projects_router)
app.include_router(requirements_router)
app.include_router(activity_router)
app.include_router(architecture_router)
app.include_router(developer.router)
app.include_router(tester.router)
app.include_router(reviewer.router)
app.include_router(preview.router)
app.include_router(export.router)

@app.on_event("startup")
def recover_developer_generation_locks():
    recover_interrupted_generations(get_database())


@app.get("/")
def root():
    return {
        "message": "AI Software Development Team API is running",
        "version": "0.1.0",
    }
