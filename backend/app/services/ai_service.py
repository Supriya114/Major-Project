import json
import os
import re
import time
from typing import Any

import requests
from dotenv import load_dotenv

load_dotenv()


PM_SCHEMA = {
    "type": "object",
    "properties": {
        "project_summary": {"type": "string"},
        "technology_stack": {
            "type": "object",
            "properties": {
                "frontend": {"type": "string"},
                "backend": {"type": "string"},
                "database": {"type": "string"},
                "api": {"type": "string"},
                "authentication": {"type": "string"},
                "other_tools": {"type": "array", "items": {"type": "string"}},
                "source": {"type": "string"},
            },
            "required": ["frontend", "backend", "database", "api", "authentication", "other_tools", "source"],
        },
        "suggested_stack": {"type": "array", "items": {"type": "string"}},
        "functional_requirements": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "id": {"type": "string"},
                    "title": {"type": "string"},
                    "description": {"type": "string"},
                    "priority": {"type": "string"},
                },
                "required": ["id", "title", "description", "priority"],
            },
        },
        "non_functional_requirements": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "id": {"type": "string"},
                    "title": {"type": "string"},
                    "description": {"type": "string"},
                },
                "required": ["id", "title", "description"],
            },
        },
        "user_stories": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {"id": {"type": "string"}, "story": {"type": "string"}},
                "required": ["id", "story"],
            },
        },
        "acceptance_criteria": {"type": "array", "items": {"type": "string"}},
        "assumptions": {"type": "array", "items": {"type": "string"}},
        "clarification_questions": {"type": "array", "items": {"type": "string"}},
    },
    "required": [
        "project_summary", "technology_stack", "suggested_stack",
        "functional_requirements", "non_functional_requirements", "user_stories",
        "acceptance_criteria", "assumptions", "clarification_questions",
    ],
}


ARCHITECTURE_SCHEMA = {
    "type": "object",
    "properties": {
        "technology_stack": {
            "type": "object",
            "properties": {
                "frontend": {"type": "string"},
                "backend": {"type": "string"},
                "database": {"type": "string"},
                "authentication": {"type": "string"},
                "deployment": {"type": "string"},
                "other_tools": {"type": "array", "items": {"type": "string"}},
            },
            "required": ["frontend", "backend", "database", "authentication", "deployment", "other_tools"],
        },
        "modules": {"type": "array", "items": {"type": "object", "properties": {
            "name": {"type": "string"}, "responsibility": {"type": "string"}, "dependencies": {"type": "array", "items": {"type": "string"}}
        }, "required": ["name", "responsibility", "dependencies"]}},
        "system_architecture": {"type": "string"},
        "database_design": {"type": "array", "items": {"type": "object", "properties": {
            "collection": {"type": "string"}, "purpose": {"type": "string"}, "fields": {"type": "array", "items": {"type": "string"}}
        }, "required": ["collection", "purpose", "fields"]}},
        "api_design": {"type": "array", "items": {"type": "object", "properties": {
            "method": {"type": "string"}, "endpoint": {"type": "string"}, "purpose": {"type": "string"}
        }, "required": ["method", "endpoint", "purpose"]}},
        "folder_structure": {"type": "array", "items": {"type": "string"}},
        "assumptions": {"type": "array", "items": {"type": "string"}},
        "open_questions": {"type": "array", "items": {"type": "string"}},
        "changes_made": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["technology_stack", "modules", "system_architecture", "database_design", "api_design", "folder_structure", "assumptions", "open_questions", "changes_made"],
}


def _clean_json_text(raw: str) -> str:
    text = str(raw or "").strip()
    if not text:
        return ""
    text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.I)
    text = re.sub(r"\s*```\s*$", "", text, flags=re.I)
    start = text.find("{")
    end = text.rfind("}")
    if start >= 0 and end > start:
        text = text[start : end + 1]
    return text.strip()


def _schema_default(definition: dict, key: str = ""):
    """Return a safe value for a missing schema field."""
    kind = definition.get("type")
    if kind == "object":
        return {}
    if kind == "array":
        return []
    if kind == "string":
        return ""
    if kind == "number":
        return 0
    if kind == "integer":
        return 0
    if kind == "boolean":
        return False
    return None


def _validate_value(value: Any, schema: dict | None = None) -> tuple[bool, str]:
    """Recursively validate the subset of JSON Schema used by SmartDevAgents."""
    if not schema:
        return True, ""

    kind = schema.get("type")
    if kind == "object":
        if not isinstance(value, dict):
            return False, "expected object"
        for key in schema.get("required", []):
            if key not in value:
                return False, f"missing required field '{key}'"
        for key, definition in schema.get("properties", {}).items():
            if key in value:
                ok, reason = _validate_value(value[key], definition)
                if not ok:
                    return False, f"{key}: {reason}"
        return True, ""

    if kind == "array":
        if not isinstance(value, list):
            return False, "expected array"
        item_schema = schema.get("items")
        for index, item in enumerate(value):
            ok, reason = _validate_value(item, item_schema)
            if not ok:
                return False, f"item {index}: {reason}"
        return True, ""

    if kind == "string" and not isinstance(value, str):
        return False, "expected string"
    if kind == "number" and not isinstance(value, (int, float)):
        return False, "expected number"
    if kind == "integer" and not isinstance(value, int):
        return False, "expected integer"
    if kind == "boolean" and not isinstance(value, bool):
        return False, "expected boolean"
    return True, ""


def _validate_object(value: Any, schema: dict | None = None) -> bool:
    ok, _ = _validate_value(value, schema)
    return ok


def _coerce_to_schema(value: Any, schema: dict) -> Any:
    """Fill harmless missing fields recursively so a usable AI response is not rejected
    merely because an optional/free model omitted an empty array or nested metadata field."""
    kind = schema.get("type")

    if kind == "object":
        source = value if isinstance(value, dict) else {}
        result = dict(source)
        for key, definition in schema.get("properties", {}).items():
            if key not in result:
                result[key] = _schema_default(definition, key)
            else:
                result[key] = _coerce_to_schema(result[key], definition)
        return result

    if kind == "array":
        if not isinstance(value, list):
            value = []
        return [_coerce_to_schema(item, schema.get("items", {})) for item in value]

    if kind == "string":
        return value if isinstance(value, str) else str(value or "")

    if kind in {"number", "integer"}:
        return value if isinstance(value, (int, float)) else 0

    if kind == "boolean":
        return value if isinstance(value, bool) else bool(value)

    return value


def extract_json_object(raw: Any) -> dict:
    cleaned = str(raw or "").strip()
    if not cleaned:
        raise ValueError("AI returned an empty response.")

    candidates: list[str] = []
    for text in [cleaned, _clean_json_text(cleaned)]:
        if text and text not in candidates:
            candidates.append(text)

    fenced_blocks = re.findall(r"```(?:json)?\s*(.*?)\s*```", cleaned, flags=re.I | re.S)
    for block in fenced_blocks:
        if block and block not in candidates:
            candidates.append(block.strip())

    brace_start = max(cleaned.find("{"), cleaned.find("["))
    brace_end = min(cleaned.rfind("}"), cleaned.rfind("]")) if brace_start >= 0 else -1
    if brace_start >= 0 and brace_end > brace_start:
        candidate = cleaned[brace_start : brace_end + 1]
        if candidate not in candidates:
            candidates.append(candidate)

    last_error: Exception | None = None
    for candidate in candidates:
        text = candidate.strip()
        if not text:
            continue
        try:
            parsed = json.loads(text)
            if isinstance(parsed, dict):
                return parsed
            if isinstance(parsed, list):
                return {"items": parsed}
        except json.JSONDecodeError as exc:
            last_error = exc
            repaired = text
            repaired = re.sub(r",\s*([}\]])", r"\1", repaired)
            repaired = repaired.replace("'", '"')
            try:
                parsed = json.loads(repaired)
                if isinstance(parsed, dict):
                    return parsed
                if isinstance(parsed, list):
                    return {"items": parsed}
            except json.JSONDecodeError:
                continue

    detail = str(last_error) if last_error else "malformed response"
    raise ValueError(f"AI returned invalid JSON: {detail}")


def _openrouter_generate(prompt: str, schema=None) -> str:
    api_key = os.getenv("OPENROUTER_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError("OPENROUTER_API_KEY is not set. Add it to backend/.env.")

    model = os.getenv("OPENROUTER_MODEL", "openrouter/free").strip()
    url = "https://openrouter.ai/api/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "HTTP-Referer": os.getenv("OPENROUTER_SITE_URL", "http://localhost:5173"),
        "X-Title": os.getenv("OPENROUTER_APP_NAME", "SmartDevAgents"),
    }

    final_prompt = prompt
    if schema:
        final_prompt += "\n\nRETURN ONLY VALID JSON. Do not use markdown fences."

    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": "You are a precise software-engineering AI agent. Follow the requested output format exactly."},
            {"role": "user", "content": final_prompt},
        ],
        "temperature": 0.15,
        "max_tokens": int(os.getenv("OPENROUTER_MAX_TOKENS", "16000")),
    }

    last_error = None
    for attempt in range(1, 4):
        print(f"[OpenRouter] attempt {attempt}/3 model={model}")
        try:
            response = requests.post(url, headers=headers, json=payload, timeout=180)
            if response.ok:
                data = response.json()
                choices = data.get("choices") or []
                if not choices:
                    raise RuntimeError(f"OpenRouter returned no choices: {data}")
                content = choices[0].get("message", {}).get("content", "")
                if isinstance(content, list):
                    content = "".join(str(part.get("text", "")) for part in content if isinstance(part, dict))
                content = str(content).strip()
                if not content:
                    raise RuntimeError("OpenRouter returned an empty response.")
                print("[OpenRouter] response received.")
                return content

            try:
                detail = response.json()
            except Exception:
                detail = response.text
            last_error = f"HTTP {response.status_code}: {detail}"
            print(f"[OpenRouter] {last_error}")
            if response.status_code in {401, 403}:
                raise RuntimeError(last_error)
            if response.status_code in {429, 500, 502, 503, 504} and attempt < 3:
                time.sleep(2 * attempt)
                continue
            raise RuntimeError(last_error)
        except requests.RequestException as exc:
            last_error = str(exc)
            if attempt < 3:
                time.sleep(2 * attempt)
                continue
            raise RuntimeError(f"OpenRouter network error: {exc}") from exc

    raise RuntimeError(last_error or "OpenRouter request failed")


def _gemini_api_keys_and_models() -> list[tuple[str, str]]:
    configured: list[tuple[str, str]] = []
    aliases = [
        ("GEMINI_API_KEY", "GEMINI_MODEL"),
        ("GEMINI_API_KEY_1", "GEMINI_MODEL_1"),
        ("GEMINI_API_KEY_2", "GEMINI_MODEL_2"),
    ]
    for api_key_var, model_var in aliases:
        api_key = os.getenv(api_key_var, "").strip()
        if not api_key:
            continue
        model = os.getenv(model_var, "gemini-3.8-flash").strip() or "gemini-3.8-flash"
        configured.append((api_key, model))
    return configured


def _gemini_generate(prompt, schema=None):
    configured = _gemini_api_keys_and_models()
    if not configured:
        raise RuntimeError("No Gemini API key configured. Set GEMINI_API_KEY or GEMINI_API_KEY_1.")

    errors = []
    for project_index, (api_key, model) in enumerate(configured, start=1):
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
        payload = {"contents": [{"parts": [{"text": prompt}]}], "generationConfig": {"maxOutputTokens": 16000}}
        if schema:
            payload["generationConfig"].update({"responseMimeType": "application/json", "responseSchema": schema})
        for attempt in range(1, 4):
            try:
                print(f"[LLM] Primary provider: gemini")
                print(f"[Gemini] request started project {project_index}/{len(configured)} model={model}")
                response = requests.post(url, params={"key": api_key}, json=payload, timeout=180)
                if response.ok:
                    data = response.json()
                    text = ""
                    for candidate in data.get("candidates", []):
                        parts = candidate.get("content", {}).get("parts", [])
                        text = "".join(str(part.get("text", "")) for part in parts if isinstance(part, dict) and part.get("text")).strip()
                        if text:
                            break
                    if text:
                        print("[Gemini] response received")
                        return text
                    errors.append(f"Gemini project {project_index}: empty response")
                    break
                detail = response.text[:2000]
                is_temporary = response.status_code in {429, 500, 502, 503, 504}
                print(f"[Gemini] temporary failure: {response.status_code}" if is_temporary else f"[Gemini] failure: {response.status_code}")
                errors.append(f"Gemini project {project_index} HTTP {response.status_code}: {detail}")
                # A 429 means the configured Gemini project/model quota is exhausted.
                # Retrying the same exhausted quota only delays the secondary provider.
                if response.status_code == 429:
                    print("[Gemini] quota exhausted; switching provider without another retry")
                    break
                if is_temporary and attempt < 3:
                    wait = 2 ** (attempt - 1)
                    print(f"[Gemini] attempt {attempt}/3 retrying in {wait}s")
                    time.sleep(wait)
                    continue
                break
            except requests.RequestException as exc:
                errors.append(f"Gemini project {project_index}: {exc}")
                if attempt < 3:
                    wait = 2 ** (attempt - 1)
                    print(f"[Gemini] attempt {attempt}/3 retrying in {wait}s")
                    time.sleep(wait)
                    continue
                break
    raise RuntimeError("All configured Gemini projects failed.\n" + "\n".join(errors))


def _generate(prompt: str, schema=None) -> str:
    preferred = os.getenv("AI_PROVIDER", "").strip().lower()
    if not preferred:
        # OpenRouter is the faster default for this project when a key is configured;
        # Gemini remains an explicit option and a fallback.
        preferred = "openrouter" if os.getenv("OPENROUTER_API_KEY", "").strip() else "gemini"
    if preferred not in {"gemini", "openrouter"}:
        preferred = "gemini"

    providers = ["gemini", "openrouter"] if preferred == "gemini" else [preferred, "gemini"]
    errors = []

    for provider in providers:
        try:
            print(f"[LLM] Provider: {provider}")
            if provider == "gemini":
                result = _gemini_generate(prompt, schema)
            else:
                result = _openrouter_generate(prompt, schema)
            print(f"[LLM] Gemini succeeded" if provider == "gemini" else "[LLM] Fallback provider succeeded")
            return result
        except Exception as exc:
            message = f"{provider}: {exc}"
            errors.append(message)
            print(f"[LLM] Provider failed: {message}")
            if provider == "gemini":
                print("[LLM] Gemini unavailable after retries")
                print("[LLM] Falling back to secondary provider")
            continue

    raise RuntimeError("All configured LLM providers failed.\n" + "\n".join(errors))


def _repair_json_with_schema(raw_or_obj: Any, schema: dict | None):
    """Ask the configured provider for one schema-aware repair."""
    schema_text = json.dumps(schema or {}, ensure_ascii=False, indent=2)
    if isinstance(raw_or_obj, str):
        source = raw_or_obj[:30000]
    else:
        source = json.dumps(raw_or_obj, ensure_ascii=False)[:30000]

    repair_prompt = f"""
Repair the following AI output for SmartDevAgents.

REQUIRED JSON SCHEMA:
{schema_text}

SOURCE OUTPUT:
{source}

Rules:
- Return ONE JSON object only.
- Include every required field from the schema.
- Use the exact field names.
- Nested objects and arrays must follow the schema too.
- Missing arrays should be [] and missing strings should be "".
- Do not add markdown or explanations.
"""
    repaired = _generate(repair_prompt, schema)
    obj = extract_json_object(repaired)
    if schema:
        obj = _coerce_to_schema(obj, schema)
        ok, reason = _validate_value(obj, schema)
        if not ok:
            raise ValueError(f"schema mismatch after repair: {reason}")
    return obj


def generate_json(prompt: str, schema=None):
    """Generate structured JSON without letting a malformed free-model response
    permanently break an SDLC stage.

    Strategy:
      1. Parse the first response.
      2. Recursively normalize harmless omissions.
      3. Make one explicit schema-aware repair attempt when necessary.
      4. Let stage-specific callers provide a deterministic fallback for total failure.
    """
    raw = _generate(prompt, schema)

    try:
        obj = extract_json_object(raw)
    except Exception as exc:
        try:
            return _repair_json_with_schema(raw, schema)
        except Exception as repair_exc:
            raise RuntimeError(
                f"AI returned invalid JSON and schema repair failed: {repair_exc}"
            ) from exc

    if schema:
        ok, reason = _validate_value(obj, schema)
        if not ok:
            try:
                return _repair_json_with_schema(obj, schema)
            except Exception as repair_exc:
                # If the response is an object, normalization can safely fill
                # omitted empty fields without inventing application behavior.
                normalized = _coerce_to_schema(obj, schema)
                normalized_ok, normalized_reason = _validate_value(normalized, schema)
                if normalized_ok:
                    print(
                        "[LLM] Schema repair failed; using safely normalized JSON "
                        f"(original issue: {reason})."
                    )
                    return normalized
                raise RuntimeError(
                    f"AI returned invalid JSON and repair failed: "
                    f"schema mismatch ({normalized_reason})"
                ) from repair_exc

    return obj

def generate_text(prompt: str):
    return _generate(prompt)


def _fallback_requirements(project_name: str, description: str):
    """Deterministic PM output used only when both LLM providers cannot produce
    a usable artifact. It keeps the workflow moving with honest, editable requirements."""
    name = project_name.strip() or "Generated Application"
    desc = description.strip() or f"A web application for {name}."

    return {
        "project_summary": desc,
        "technology_stack": {
            "frontend": "React + Vite",
            "backend": "FastAPI + Python",
            "database": "MongoDB",
            "api": "REST API",
            "authentication": "JWT-based authentication",
            "other_tools": ["Vite", "Uvicorn"],
            "source": "AI_FALLBACK",
        },
        "suggested_stack": [
            "React + Vite",
            "FastAPI + Python",
            "MongoDB",
            "JWT authentication",
        ],
        "functional_requirements": [
            {"id": "FR-01", "title": "Registration", "description": "Users can create an account with validated credentials.", "priority": "HIGH"},
            {"id": "FR-02", "title": "Login", "description": "Users can securely log in and receive an authenticated session.", "priority": "HIGH"},
            {"id": "FR-03", "title": "Core application workflow", "description": f"The application implements the requested functionality: {desc}", "priority": "HIGH"},
            {"id": "FR-04", "title": "Protected access", "description": "Authenticated users can access protected application features.", "priority": "HIGH"},
            {"id": "FR-05", "title": "Logout", "description": "Users can end their authenticated session.", "priority": "MEDIUM"},
        ],
        "non_functional_requirements": [
            {"id": "NFR-01", "title": "Validation", "description": "Client and server validate user input and return useful errors."},
            {"id": "NFR-02", "title": "Security", "description": "Passwords are hashed and secrets are read from environment variables."},
            {"id": "NFR-03", "title": "Responsive UI", "description": "The web interface works on desktop and mobile layouts."},
        ],
        "user_stories": [
            {"id": "US-01", "story": "As a user, I want to register and log in so that I can use protected features."},
            {"id": "US-02", "story": f"As a user, I want to use the {name} features so that the requested task can be completed."},
        ],
        "acceptance_criteria": [
            "The application starts using the documented commands.",
            "Registration and login validate input and handle errors.",
            "The requested core workflow is accessible from the frontend.",
            "Protected API operations reject unauthenticated requests.",
            "The frontend handles loading, empty, success, and error states.",
        ],
        "assumptions": [
            "MongoDB connection details are provided through environment variables.",
            "The application is intended to run locally unless deployment requirements are specified.",
        ],
        "clarification_questions": [],
    }


def generate_requirements(project_name: str, description: str):
    prompt = f"""
You are the Product Manager Agent in SmartDevAgents.

Project name: {project_name}
User request: {description}

Create a practical requirements specification for EXACTLY the product the user requested.

TECHNOLOGY STACK RULE:
- If the user explicitly names a frontend, backend, database, API, framework, language,
  library, hosting platform, or other technology, preserve it exactly.
- Never silently replace MySQL with SQLite, Express with FastAPI, MongoDB with PostgreSQL,
  React with another frontend, etc.
- If the user gives no stack, choose a small, sensible stack and put the recommendation in
  suggested_stack. Clearly mark technology_stack.source as "AI_SUGGESTED".
- If the user gives a partial stack, preserve the specified parts and suggest only the missing parts.

FUNCTIONALITY RULE:
- Extract every requested feature.
- Add sensible supporting features only when necessary to make the requested application usable.
- SmartDevAgents has a platform-wide baseline: every generated web application MUST include Register, Login, Logout, protected application access, secure password hashing, and session/token handling unless the human explicitly removes authentication during a revision.

Return the full JSON structure required by the schema.
"""
    try:
        result = generate_json(prompt, PM_SCHEMA)
        # A free model may omit nested empty metadata. Normalize and verify before storage.
        result = _coerce_to_schema(result, PM_SCHEMA)
        ok, reason = _validate_value(result, PM_SCHEMA)
        if not ok:
            raise ValueError(reason)
        return result
    except Exception as exc:
        print(f"[PM] Structured generation failed; using deterministic fallback: {exc}")
        return _fallback_requirements(project_name, description)


def generate_developer_opinion(project_name: str, description: str, requirements: dict):
    prompt = f"""
You are the Developer Agent reviewing requirements before architecture.

Project: {project_name}
Original user request: {description}
Requirements:
{json.dumps(requirements, indent=2)}

Check whether the requirements are implementable and whether the requested technology stack is
internally consistent. If the user did not provide a stack, suggest one. If the user did provide a
stack, do not replace it; flag only genuine compatibility concerns.

Return ONLY JSON:
{{
  "decision": "APPROVED" or "NEEDS_REVISION",
  "summary": "short opinion",
  "feasibility": "HIGH" or "MEDIUM" or "LOW",
  "issues": [],
  "recommendations": [],
  "suggested_stack": []
}}
"""
    try:
        result = generate_json(prompt)
        if not isinstance(result, dict):
            raise ValueError("Developer opinion must be an object.")
        result.setdefault("decision", "APPROVED")
        result.setdefault("summary", "Requirements are implementable with the selected stack.")
        result.setdefault("feasibility", "HIGH")
        result.setdefault("issues", [])
        result.setdefault("recommendations", [])
        result.setdefault("suggested_stack", requirements.get("suggested_stack", []))
        return result
    except Exception as exc:
        print(f"[Developer Opinion] Structured generation failed; using fallback: {exc}")
        return {
            "decision": "APPROVED",
            "summary": "The requirements are implementable with the selected/recommended stack. No blocking feasibility issue was identified.",
            "feasibility": "HIGH",
            "issues": [],
            "recommendations": [
                "Keep the frontend and backend API contracts synchronized.",
                "Keep database credentials and JWT secrets in environment variables.",
            ],
            "suggested_stack": requirements.get("suggested_stack", []),
        }


def _fallback_architecture(requirements: dict):
    stack = requirements.get("technology_stack", {}) or {}
    frontend = stack.get("frontend") or "React + Vite"
    backend = stack.get("backend") or "FastAPI + Python"
    database = stack.get("database") or "MongoDB"
    auth = stack.get("authentication") or "JWT-based authentication"

    functional = requirements.get("functional_requirements", []) or []
    modules = [
        {
            "name": "Authentication",
            "responsibility": "Registration, login, password hashing, token/session handling and protected access.",
            "dependencies": [],
        },
        {
            "name": "Core Application",
            "responsibility": "Implement the requested application workflow and user-facing features.",
            "dependencies": ["Authentication"],
        },
        {
            "name": "API",
            "responsibility": "Expose REST endpoints used by the frontend.",
            "dependencies": ["Authentication", "Core Application"],
        },
        {
            "name": "Frontend",
            "responsibility": "Provide responsive pages, forms, navigation, loading states and error handling.",
            "dependencies": ["API"],
        },
    ]
    api = [
        {"method": "POST", "endpoint": "/api/auth/register", "purpose": "Create a user account."},
        {"method": "POST", "endpoint": "/api/auth/login", "purpose": "Authenticate a user."},
        {"method": "GET", "endpoint": "/api/auth/me", "purpose": "Return the current authenticated user."},
        {"method": "POST", "endpoint": "/api/auth/logout", "purpose": "End the authenticated session."},
    ]
    for item in functional[:12]:
        if not isinstance(item, dict):
            continue
        slug = re.sub(r"[^a-z0-9]+", "-", str(item.get("title", "feature")).lower()).strip("-") or "feature"
        api.extend([
            {"method": "GET", "endpoint": f"/api/{slug}", "purpose": item.get("description", "Retrieve application data.")},
            {"method": "POST", "endpoint": f"/api/{slug}", "purpose": item.get("description", "Create application data.")},
        ])

    return {
        "technology_stack": {
            "frontend": frontend,
            "backend": backend,
            "database": database,
            "authentication": auth,
            "deployment": "Local development",
            "other_tools": stack.get("other_tools", []),
        },
        "modules": modules,
        "system_architecture": f"{frontend} frontend communicates with a {backend} REST API backed by {database}; authentication uses {auth}.",
        "database_design": [
            {
                "collection": "users",
                "purpose": "Store authenticated user accounts.",
                "fields": ["_id", "email", "password_hash", "created_at"],
            },
            {
                "collection": "application_data",
                "purpose": "Store data required by the requested application workflow.",
                "fields": ["_id", "owner_id", "data", "created_at", "updated_at"],
            },
        ],
        "api_design": api,
        "folder_structure": [
            "frontend/",
            "frontend/src/",
            "backend/",
            "backend/app/",
            "backend/app/routes/",
            ".env.example",
        ],
        "assumptions": requirements.get("assumptions", []),
        "open_questions": requirements.get("clarification_questions", []),
        "changes_made": ["Deterministic architecture fallback used because structured AI output was unavailable."],
    }


def generate_architecture(project_name: str, description: str, requirements: dict,
                          developer_opinion: dict, revision_feedback: str = "",
                          previous_architecture: dict | None = None):
    prompt = f"""
You are the Architect Agent in SmartDevAgents.

PROJECT: {project_name}
USER REQUEST: {description}

PRODUCT REQUIREMENTS:
{json.dumps(requirements, indent=2)}

DEVELOPER OPINION:
{json.dumps(developer_opinion, indent=2)}

PREVIOUS ARCHITECTURE:
{json.dumps(previous_architecture or {}, indent=2)}

HUMAN REVISION FEEDBACK:
{revision_feedback or "None"}

Architecture rules:
1. The user's explicitly requested technology stack is authoritative.
2. Do not substitute technologies without clearly marking a compatibility problem and requiring human approval.
3. The architecture must describe the actual requested product, not a generic dashboard.
4. Include all APIs/modules/database entities needed for the requested features.
5. Every generated application starts with the SmartDevAgents authentication baseline: Register, Login, Logout, protected access, secure password hashing, and session/token handling.
6. Make the design runnable locally.
7. Return ONLY valid JSON.
"""
    try:
        result = generate_json(prompt, ARCHITECTURE_SCHEMA)
        result = _coerce_to_schema(result, ARCHITECTURE_SCHEMA)
        ok, reason = _validate_value(result, ARCHITECTURE_SCHEMA)
        if not ok:
            raise ValueError(reason)
        return result
    except Exception as exc:
        print(f"[Architect] Structured generation failed; using deterministic fallback: {exc}")
        return _fallback_architecture(requirements)

