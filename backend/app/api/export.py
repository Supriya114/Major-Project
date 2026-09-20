import io
import json
import zipfile
from datetime import datetime, timezone

from bson import ObjectId
from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse

from app.database.mongodb import get_database

router = APIRouter(prefix="/api/projects", tags=["Export"])


def _project(db, project_id: str):
    try:
        obj = ObjectId(project_id)
    except Exception as exc:
        raise HTTPException(status_code=400, detail="Invalid project ID.") from exc
    project = db.projects.find_one({"_id": obj})
    if not project:
        raise HTTPException(status_code=404, detail="Project not found.")
    return project


def _safe_member(path: str) -> str:
    value = str(path or "").replace("\\", "/").strip()
    if not value or value.startswith("/") or ".." in value.split("/"):
        raise ValueError(f"Unsafe generated path: {path}")
    return value


@router.get("/{project_id}/export")
def export_project(project_id: str):
    db = get_database()
    project = _project(db, project_id)
    developer = db.developer_projects.find_one({"project_id": project_id}, sort=[("version", -1)])
    if not developer or not developer.get("files"):
        raise HTTPException(status_code=400, detail="Generate the Developer project before exporting it.")

    tester = db.tester_runs.find_one({"project_id": project_id}, sort=[("version", -1)])
    buffer = io.BytesIO()
    root_name = str(project.get("name") or "generated-project").strip().replace(" ", "_")
    root_name = "".join(ch for ch in root_name if ch.isalnum() or ch in "-_") or "generated-project"

    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        written = set()
        for item in developer.get("files", []):
            path = _safe_member(item.get("path"))
            member = f"{root_name}/{path}"
            archive.writestr(member, str(item.get("content", "")))
            written.add(path)

        if tester:
            for item in tester.get("test_files", []):
                try:
                    path = _safe_member(item.get("path"))
                except ValueError:
                    continue
                # Never create duplicate ZIP members if the Developer already
                # supplied a tests/ file with the same path.
                if path in written:
                    path = f"generated-tests/{path}"
                archive.writestr(f"{root_name}/{path}", str(item.get("content", "")))

            archive.writestr(
                f"{root_name}/TEST_PLAN.json",
                json.dumps(tester.get("test_cases", []), indent=2, ensure_ascii=False),
            )

        archive.writestr(
            f"{root_name}/SETUP.md",
            "# Generated Project\n\n"
            "This archive contains the complete Developer Agent output and the generated test suite.\n\n"
            "## Run\n\n"
            "1. Inspect the generated frontend/backend folders.\n"
            "2. Install dependencies from the included manifests.\n"
            "3. Copy `.env.example` to `.env` where required and add your own secrets.\n"
            "4. Start the frontend and backend using the scripts documented in their package/configuration files.\n",
        )
        archive.writestr(
            f"{root_name}/PROJECT_METADATA.json",
            json.dumps(
                {
                    "name": project.get("name"),
                    "description": project.get("description"),
                    "developer_version": developer.get("version"),
                    "technology_stack": developer.get("technology_stack", {}),
                    "exported_at": datetime.now(timezone.utc).isoformat(),
                },
                indent=2,
                ensure_ascii=False,
            ),
        )

    buffer.seek(0)
    filename = f"{root_name}_v{developer.get('version', 1)}.zip"
    return StreamingResponse(
        buffer,
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
