from datetime import datetime, timezone
import threading

from bson import ObjectId
from pymongo import ReturnDocument
from fastapi import APIRouter, HTTPException

from app.database.mongodb import get_database
from app.services.developer_service import (
    generate_project_plan,
    generate_project_file,
    fallback_project_file,
)
from app.utils.serialization import serialize_for_json
from app.services.project_validation import validate_project_files, build_frontends


router = APIRouter(
    prefix="/api/projects",
    tags=["developer"],
)

# One Developer generation is allowed per project at a time.  This prevents
# double-clicks, duplicate browser requests, and stale frontend retries from
# creating two different plans/files for the same project simultaneously.
_generation_locks: dict[str, threading.Lock] = {}
_generation_locks_guard = threading.Lock()

def _project_generation_lock(project_id: str) -> threading.Lock:
    with _generation_locks_guard:
        return _generation_locks.setdefault(project_id, threading.Lock())


# Each backend process gets its own generation owner. A generation that was
# interrupted by CTRL+C/reload cannot leave a permanent MongoDB lock.
_PROCESS_GENERATION_OWNER = __import__("uuid").uuid4().hex


def recover_interrupted_generations(db):
    """Clear generation claims left by a previous backend process.

    MongoDB persists project status, while the in-memory generation lock does
    not survive a Uvicorn restart. Therefore DEVELOPER_GENERATING projects
    belonging to an older process are safe to mark failed and retry.
    """
    result = db.projects.update_many(
        {"status": "DEVELOPER_GENERATING",
         "developer_generation_owner": {"$ne": _PROCESS_GENERATION_OWNER}},
        {"$set": {
            "status": "DEVELOPER_GENERATION_FAILED",
            "current_agent": "DEVELOPER",
            "updated_at": datetime.now(timezone.utc),
            "developer_generation_recovered": True,
        }, "$unset": {"developer_generation_owner": ""}},
    )
    if result.modified_count:
        print(f"[Developer] Recovered {result.modified_count} interrupted generation(s).")


def serialize(document):
    return serialize_for_json(document)


def get_project(db, project_id: str):
    try:
        object_id = ObjectId(project_id)
    except Exception:
        raise HTTPException(
            status_code=400,
            detail="Invalid project ID.",
        )

    project = db.projects.find_one({"_id": object_id})

    if not project:
        raise HTTPException(
            status_code=404,
            detail="Project not found.",
        )

    return project


@router.post("/{project_id}/developer/generate")
def generate_developer_project(project_id: str):
    db = get_database()

    project = get_project(db, project_id)

    requirements = db.requirements.find_one(
        {"project_id": project_id}
    )

    if not requirements:
        raise HTTPException(
            status_code=400,
            detail="Requirements are required before code generation.",
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

    architecture = db.architectures.find_one(
        {"project_id": project_id},
        sort=[("created_at", -1)],
    )
    developer_fix_request = db.developer_fix_requests.find_one(
        {
            "project_id": project_id,
            "status": "PENDING",
        },
        sort=[("created_at", -1)],
    )

    if not architecture:
        raise HTTPException(
            status_code=400,
            detail="Approved architecture is required before code generation.",
        )

    # Claim the generation atomically in MongoDB before doing any LLM work.
    # A second POST for the same project receives 409 instead of starting a
    # second project plan. The owner token also makes interrupted/reloaded
    # backend processes recoverable instead of leaving a permanent 409.
    now = datetime.now(timezone.utc)
    claimed = db.projects.find_one_and_update(
        {
            "_id": ObjectId(project_id),
            "status": {"$ne": "DEVELOPER_GENERATING"},
        },
        {
            "$set": {
                "status": "DEVELOPER_GENERATING",
                "current_agent": "DEVELOPER",
                "developer_generation_started_at": now,
                "developer_generation_owner": _PROCESS_GENERATION_OWNER,
                "updated_at": now,
            }
        },
        return_document=ReturnDocument.AFTER,
    )
    if not claimed:
        raise HTTPException(
            status_code=409,
            detail="Developer generation is already running for this project. Wait for the current run to finish.",
        )

    generation_lock = _project_generation_lock(project_id)
    if not generation_lock.acquire(blocking=False):
        raise HTTPException(
            status_code=409,
            detail="Developer generation is already running for this project. Wait for the current run to finish.",
        )

    # --------------------------------------------------
    # Mark Developer Agent as started
    # --------------------------------------------------

    db.agent_activity.insert_one({
        "project_id": project_id,
        "agent": "DEVELOPER",
        "event": "DEVELOPER_GENERATION_STARTED",
        "message": "Developer Agent started generating the project.",
        "created_at": now,
    })

    try:

        # --------------------------------------------------
        # STEP 1: Generate implementation plan
        # --------------------------------------------------

        print("[Developer] Generating project plan...")

        project_plan = generate_project_plan(
            project["name"],
            project.get("description", ""),
            serialize(requirements),
            serialize(developer_opinion),
            serialize(architecture),
            serialize(developer_fix_request) if developer_fix_request else {},
        )

        files_to_generate = project_plan.get("files", [])

        print(
            f"[Developer] Project plan created with "
            f"{len(files_to_generate)} files."
        )

        db.agent_activity.insert_one({
            "project_id": project_id,
            "agent": "DEVELOPER",
            "event": "DEVELOPER_PLAN_CREATED",
            "message": (
                f"Developer created an implementation plan "
                f"with {len(files_to_generate)} files."
            ),
            "created_at": datetime.now(timezone.utc),
        })

        # --------------------------------------------------
        # STEP 2: Generate each file
        # --------------------------------------------------

        generated_files = []

        for index, file_info in enumerate(
            files_to_generate,
            start=1,
        ):

            file_path = file_info.get("path", "unknown")

            print(
                f"[Developer] Generating file "
                f"{index}/{len(files_to_generate)}: {file_path}"
            )

            db.agent_activity.insert_one({
                "project_id": project_id,
                "agent": "DEVELOPER",
                "event": "DEVELOPER_FILE_GENERATION_STARTED",
                "message": (
                    f"Generating file {index}/"
                    f"{len(files_to_generate)}: {file_path}"
                ),
                "created_at": datetime.now(timezone.utc),
            })

            generated_file = None
            last_generation_error = None
            for attempt in range(1, 3):
                try:
                    retry_info = dict(file_info)
                    if attempt > 1:
                        retry_info["purpose"] = (
                            str(file_info.get("purpose", ""))
                            + "\n\nCRITICAL RETRY: The previous generation was empty or invalid. "
                            "Return the complete non-empty implementation for this file. "
                            "Do not return an empty response, placeholder, TODO, or mock. "
                        )
                    candidate = generate_project_file(
                        project["name"],
                        project.get("description", ""),
                        serialize(requirements),
                        serialize(developer_opinion),
                        serialize(architecture),
                        project_plan,
                        retry_info,
                    )
                    content = str(candidate.get("content", "")).strip()
                    if not content:
                        raise ValueError("LLM returned empty file content")
                    if (
                        str(file_path).lower().endswith((
                            ".py", ".js", ".jsx", ".ts", ".tsx", ".json",
                            ".html", ".css", ".txt", ".yml", ".yaml", ".toml",
                        ))
                        and content.lower() in {"none", "null", "undefined"}
                    ):
                        raise ValueError(
                            "LLM returned a placeholder instead of a complete file implementation"
                        )
                    generated_file = candidate
                    break
                except Exception as exc:
                    last_generation_error = exc
                    print(f"[Developer] Retry {attempt}/2 for {file_path}: {exc}")

            if generated_file is None:
                print(
                    f"[Developer] AI unavailable for {file_path}; using deterministic baseline: "
                    f"{last_generation_error}"
                )
                generated_file = fallback_project_file(
                    project["name"],
                    project.get("description", ""),
                    file_info,
                )

            generated_files.append(generated_file)

            print(
                f"[Developer] Completed file "
                f"{index}/{len(files_to_generate)}: {file_path}"
            )

            db.agent_activity.insert_one({
                "project_id": project_id,
                "agent": "DEVELOPER",
                "event": "DEVELOPER_FILE_GENERATION_COMPLETED",
                "message": (
                    f"Generated {file_path} "
                    f"({index}/{len(files_to_generate)})."
                ),
                "created_at": datetime.now(timezone.utc),
            })

        # --------------------------------------------------
        # QUALITY GATE: validate the COMPLETE generated project
        # --------------------------------------------------
        validation_errors = validate_project_files(generated_files)
        if validation_errors:
            raise RuntimeError(
                "Generated project quality gate failed:\n"
                + "\n".join(validation_errors[:50])
            )

        planned_stack = project_plan.get("technology_stack", {}) or {}
        architecture_stack = architecture.get("technology_stack", {}) or {}
        planned_frontend = str(
            planned_stack.get("frontend") or architecture_stack.get("frontend", "")
        ).lower()
        if any(token in planned_frontend for token in ("react", "vite", "next", "frontend")):
            generated_paths = {
                str(item.get("path", "")).replace("\\", "/").lower()
                for item in generated_files
                if isinstance(item, dict)
            }
            frontend_manifests = {
                path for path in generated_paths
                if path.endswith("/package.json") and path.split("/")[0] in {"frontend", "client", "web"}
            }
            frontend_entries = {
                path for path in generated_paths
                if path.startswith(("frontend/", "client/", "web/"))
                and path.endswith(("/src/main.jsx", "/src/main.tsx", "/src/main.js", "/src/index.jsx", "/src/index.tsx", "/src/App.jsx", "/src/App.tsx"))
            }
            if not frontend_manifests or not frontend_entries:
                raise RuntimeError(
                    "Generated project quality gate failed: the planned frontend was not generated."
                )

        # Frontend projects must be buildable before they are handed to the
        # Tester/Preview stages. Set DEVELOPER_RUN_BUILD_GATE=false only when
        # working in an environment that intentionally has no npm toolchain.
        import os
        if os.getenv("DEVELOPER_RUN_BUILD_GATE", "true").strip().lower() not in {"0", "false", "no"}:
            build_errors, build_logs = build_frontends(generated_files, timeout=240)
            if build_errors:
                raise RuntimeError(
                    "Generated frontend quality gate failed:\n"
                    + "\n".join(build_errors[:20])
                )

        # --------------------------------------------------
        # STEP 3: Determine version
        # --------------------------------------------------

        latest = db.developer_projects.find_one(
            {"project_id": project_id},
            sort=[("version", -1)],
        )

        version = 1

        if latest:
            version = latest.get("version", 0) + 1

        # --------------------------------------------------
        # STEP 4: Build final document
        # --------------------------------------------------

        document = {
            "project_id": project_id,
            "version": version,
            "project_summary": project_plan.get(
                "project_summary",
                "",
            ),
            "technology_stack": project_plan.get(
                "technology_stack",
                {},
            ),
            "project_structure": project_plan.get(
                "project_structure",
                [],
            ),
            "files": generated_files,
            "dependencies": project_plan.get(
                "dependencies",
                [],
            ),
            "implementation_decisions": project_plan.get(
                "implementation_decisions",
                [],
            ),
            "test_suggestions": project_plan.get(
                "test_suggestions",
                [],
            ),
            "created_at": datetime.now(timezone.utc),
        }

        print(
            f"[Developer] Saving version {version} "
            f"with {len(generated_files)} files to MongoDB..."
        )

        # --------------------------------------------------
        # STEP 5: Save generated project
        # --------------------------------------------------

        result = db.developer_projects.insert_one(document)
        if developer_fix_request:
            db.developer_fix_requests.update_one(
                {"_id": developer_fix_request["_id"]},
                {
                    "$set": {
                        "status": "APPLIED",
                        "developer_version": version,
                        "updated_at": datetime.now(timezone.utc),
                    }
                },
            )

            db.agent_activity.insert_one({
                "project_id": project_id,
                "agent": "DEVELOPER",
                "event": "DEVELOPER_FIXES_COMPLETED",
                "message": (
                    f"Developer applied Reviewer fixes in Version {version}."
                ),
                "created_at": datetime.now(timezone.utc),
            })
        

        document["_id"] = result.inserted_id

        print(
            f"[Developer] Project version {version} saved successfully."
        )

        # --------------------------------------------------
        # STEP 6: Mark Developer work as ready
        # --------------------------------------------------

        db.projects.update_one(
            {"_id": ObjectId(project_id)},
            {
                "$set": {
                    "status": "DEVELOPER_READY",
                    "current_agent": "HUMAN_APPROVAL",
                    "updated_at": datetime.now(timezone.utc),
                },
                "$unset": {"developer_generation_owner": ""},
            },
        )

        db.agent_activity.insert_one({
            "project_id": project_id,
            "agent": "DEVELOPER",
            "event": "DEVELOPER_GENERATION_COMPLETED",
            "message": (
                f"Developer Agent generated project version "
                f"{version} with {len(generated_files)} files "
                "and submitted it for human approval."
            ),
            "created_at": datetime.now(timezone.utc),
        })

        print("[Developer] Generation completed successfully.")
        generation_lock.release()
        return serialize(document)

    except Exception as exc:

        # Print the REAL error to the backend terminal.
        import traceback

        print("\n========== DEVELOPER GENERATION ERROR ==========")
        print(str(exc))
        traceback.print_exc()
        print("=================================================\n")

        db.agent_activity.insert_one({
            "project_id": project_id,
            "agent": "DEVELOPER",
            "event": "DEVELOPER_GENERATION_FAILED",
            "message": str(exc),
            "created_at": datetime.now(timezone.utc),
        })

        db.projects.update_one(
            {"_id": ObjectId(project_id)},
            {
                "$set": {
                    "status": "DEVELOPER_GENERATION_FAILED",
                    "current_agent": "DEVELOPER",
                    "updated_at": datetime.now(timezone.utc),
                }
            },
        )

        if generation_lock.locked():
            generation_lock.release()

        raise HTTPException(
            status_code=502,
            detail=str(exc),
        )


@router.get("/{project_id}/developer")
def get_developer_project(project_id: str):
    db = get_database()

    get_project(db, project_id)

    developer_project = db.developer_projects.find_one(
        {"project_id": project_id},
        sort=[("version", -1)],
    )

    if not developer_project:
        return {
            "status": "NOT_GENERATED"
        }

    return serialize(developer_project)

@router.get("/{project_id}/developer/fix-request")
def get_developer_fix_request(project_id: str):
    db = get_database()

    fix_request = db.developer_fix_requests.find_one(
        {
            "project_id": project_id,
            "status": "PENDING",
        },
        sort=[("created_at", -1)],
    )

    if not fix_request:
        return None

    fix_request["_id"] = str(fix_request["_id"])

    if fix_request.get("reviewer_run_id"):
        fix_request["reviewer_run_id"] = str(
            fix_request["reviewer_run_id"]
        )

    return fix_request

@router.post("/{project_id}/developer/fix-request")
def request_developer_fixes(project_id: str):
    db = get_database()

    project = get_project(db, project_id)

    reviewer = db.reviewer_runs.find_one(
        {"project_id": project_id},
        sort=[("created_at", -1)],
    )
    developer_fix_request = db.developer_fix_requests.find_one(
        {
            "project_id": project_id,
            "status": "PENDING",
        },
        sort=[("created_at", -1)],
    )

    if not reviewer:
        raise HTTPException(
            status_code=400,
            detail="Reviewer report is required before requesting fixes.",
        )

    now = datetime.now(timezone.utc)

    fix_request = {
        "project_id": project_id,
        "reviewer_run_id": reviewer.get("_id"),
        "findings": reviewer.get("findings", []),
        "improvement_suggestions": reviewer.get(
            "improvement_suggestions",
            [],
        ),
        "recommendation": reviewer.get(
            "recommendation",
            "",
        ),
        "status": "PENDING",
        "created_at": now,
    }

    result = db.developer_fix_requests.insert_one(fix_request)
    fix_request["_id"] = result.inserted_id

    db.projects.update_one(
        {"_id": ObjectId(project_id)},
        {
            "$set": {
                "status": "DEVELOPER_FIX_REQUESTED",
                "current_agent": "DEVELOPER",
                "updated_at": now,
            }
        },
    )

    db.agent_activity.insert_one({
        "project_id": project_id,
        "agent": "REVIEWER",
        "event": "DEVELOPER_FIX_REQUESTED",
        "message": (
            "Reviewer requested Developer fixes based on the "
            "latest review findings."
        ),
        "created_at": now,
    })

    fix_request["_id"] = str(fix_request["_id"])
    fix_request["_id"] = str(fix_request["_id"])

    if fix_request.get("reviewer_run_id"):
        fix_request["reviewer_run_id"] = str(
            fix_request["reviewer_run_id"]
        )

    return fix_request



@router.post("/{project_id}/developer/approve")
def approve_developer_project(project_id: str):
    db = get_database()
    project = get_project(db, project_id)
    developer_project = db.developer_projects.find_one({"project_id": project_id}, sort=[("version", -1)])
    if not developer_project:
        raise HTTPException(status_code=400, detail="Generate the project before approving it.")
    now = datetime.now(timezone.utc)
    db.developer_projects.update_one({"_id": developer_project["_id"]}, {"$set": {"approval_status": "APPROVED", "approved_at": now}})
    db.projects.update_one({"_id": project["_id"]}, {"$set": {"status": "DEVELOPER_APPROVED", "current_agent": "TESTER", "updated_at": now}})
    db.agent_activity.insert_one({"project_id": project_id, "agent": "HUMAN", "event": "DEVELOPER_APPROVED", "message": "Human approved generated code. Tester can continue.", "created_at": now})
    return {"status": "DEVELOPER_APPROVED", "current_agent": "TESTER"}
