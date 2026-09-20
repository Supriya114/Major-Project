# SmartDevAgents — LLM-Based Multi-Agent Software Development Team

SmartDevAgents is a React + Vite / FastAPI / MongoDB platform that coordinates a software project through Product Manager, Architect, Developer, Tester, and Reviewer stages.

## Workflow

1. **Dashboard** — create/select a project.
2. **Product Manager** — generate requirements.
3. **Developer feasibility** — review the requirements.
4. **Human approval** — approve requirements.
5. **Architect** — generate and approve the technical architecture.
6. **Developer** — generate the complete project source tree.
7. **Developer quality gate** — reject empty/duplicate/unsafe generated files before a version is saved.
8. **Tester** — generate tests from the actual complete Developer project.
9. **Test execution** — reconstruct the complete project in an isolated temporary directory and execute the full test suite together. Test-file count is not used as the test-case count.
10. **Reviewer** — review the generated source and Tester results.
11. **Generated Project** — inspect every generated file.
12. **Preview** — start the generated frontend and, when detectable, its local backend.
13. **Export** — download the complete generated project and generated test suite as a ZIP.

## AI providers

The backend supports Gemini with OpenRouter fallback. Gemini `429` quota responses are treated as provider failures and the secondary provider is used instead of repeatedly waiting on an exhausted daily quota.

Use `backend/.env.example` as the template. **Do not commit or distribute `backend/.env` or API keys.**

## Backend

```bash
cd backend
python -m venv venv
# Windows
venv\\Scripts\\activate
# macOS/Linux
# source venv/bin/activate
pip install -r requirements.txt
copy .env.example .env   # Windows
# cp .env.example .env   # macOS/Linux
uvicorn app.main:app --reload
```

API: `http://127.0.0.1:8000`

Swagger: `http://127.0.0.1:8000/docs`

## Frontend

```bash
cd frontend
npm install
npm run dev
```

Frontend: `http://localhost:5173`

## Tester behavior

The Tester is project-wide. It reconstructs **all Developer-generated files** before writing and executing tests. If an LLM provider is unavailable or returns an unusable test plan, SmartDevAgents creates a deterministic integrity suite from the actual project manifest instead of displaying `0 tests`.

The fallback suite checks the complete generated project for:

- non-empty generated files
- duplicate paths
- valid dependency manifests
- Python syntax
- JavaScript syntax
- frontend structure
- backend structure when present
- complete project reconstruction

These are genuine checks; a broken or empty generated file can fail the suite rather than being falsely marked as passed.

## Preview

The Preview service recursively detects generated frontend and backend packages instead of assuming one fixed filename. It waits for the generated server to become reachable before returning the preview URL.

The preview is isolated in a temporary directory and is stopped/cleaned up when the preview is stopped or startup fails.

## Export

The **Generated Project** and **Export Project** pages download a ZIP containing:

- every Developer-generated file
- generated executable test files
- `TEST_PLAN.json`
- `PROJECT_METADATA.json`
- `SETUP.md`

Secrets from the SmartDevAgents development environment are not exported.

## Corrected workflow

The application now keeps one active project selected across reloads and exposes a working project selector in the top bar. The intended workflow is:

1. Product Manager generates requirements.
2. Developer reviews requirements; a human approves them.
3. Architect generates the architecture; a human approves it.
4. Developer generates the complete project and the frontend build gate rejects empty/broken frontend output before saving a version.
5. A human approves the generated project.
6. Tester generates a project-wide test plan and executable suite. The deterministic fallback suite guarantees a visible executable baseline when an LLM test response is incomplete or unsafe.
7. Tests must actually run and pass before the human can approve testing.
8. Reviewer is blocked until the passing Tester run is human-approved.
9. Reviewer approval marks the project complete and opens the Generated Project page.
10. Generated Project supports source browsing, Preview, and complete ZIP export.

### AI provider

OpenRouter can be used as the preferred provider with `OPENROUTER_MODEL=openrouter/free`. Gemini remains available as a secondary provider. Gemini HTTP 429 quota exhaustion now switches providers without repeatedly waiting on an exhausted quota.

### Developer quality gate

`DEVELOPER_RUN_BUILD_GATE=true` builds detected frontend packages before a Developer version is saved. Empty generated files are retried up to three times and are never saved as a valid Developer version.


### Developer generation recovery
If Uvicorn is stopped/reloaded during generation, the next backend startup automatically clears the interrupted generation claim. This prevents a permanent HTTP 409 on the Developer page.
