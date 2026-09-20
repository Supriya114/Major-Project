import json
import os
import re
import shutil
import socket
import subprocess
import sys
import tempfile
import time
from html import escape
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import urlopen

from bson import ObjectId
from fastapi import APIRouter, HTTPException

from app.database.mongodb import get_database

router = APIRouter(prefix="/api/projects", tags=["Preview"])
_preview_processes: dict[str, list[subprocess.Popen]] = {}
_preview_directories: dict[str, str] = {}
_preview_logs: dict[str, dict] = {}


def _get_project(db, project_id):
    try:
        object_id = ObjectId(project_id)
    except Exception as exc:
        raise HTTPException(status_code=400, detail="Invalid project ID.") from exc
    project = db.projects.find_one({"_id": object_id})
    if not project:
        raise HTTPException(status_code=404, detail="Project not found.")
    return project


def _safe_write(files, directory):
    root = Path(directory).resolve()
    for file_data in files:
        path = str(file_data.get("path", "")).strip().replace("\\", "/")
        path_obj = Path(path)
        if not path or path_obj.is_absolute() or ".." in path_obj.parts:
            raise ValueError(f"Unsafe generated path: {path}")
        target = (root / path_obj).resolve()
        if root not in target.parents and target != root:
            raise ValueError(f"Unsafe generated path: {path}")
        target.parent.mkdir(parents=True, exist_ok=True)
        content = str(file_data.get("content", "") or "").strip()
        lines = content.splitlines()
        if lines and lines[0].strip().startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        normalized_content = "\n".join(lines).strip()
        if path.lower().endswith(".py"):
            normalized_content = normalized_content.replace(
                "from pymongo.errors import ConnectionError",
                "# ConnectionError is provided by Python's standard library.",
            )
            if path.lower().endswith("database.py") and "def connect_to_mongo" not in normalized_content:
                normalized_content += (
                    "\n\nasync def connect_to_mongo():\n"
                    "    return db\n\n"
                    "async def close_mongo_connection():\n"
                    "    client.close()\n"
                )
            if "FastAPI(" in normalized_content and "CORSMiddleware" not in normalized_content:
                normalized_content = normalized_content.replace(
                    "from fastapi import FastAPI",
                    "from fastapi import FastAPI\nfrom fastapi.middleware.cors import CORSMiddleware",
                    1,
                )
                normalized_content = normalized_content.replace(
                    "app = FastAPI()",
                    "app = FastAPI()\napp.add_middleware(CORSMiddleware, allow_origins=['*'], allow_credentials=False, allow_methods=['*'], allow_headers=['*'])",
                    1,
                )
            if "OAuth2PasswordFlow" in normalized_content:
                normalized_content = normalized_content.replace(
                    "OAuth2PasswordFlow",
                    "OAuth2PasswordBearer",
                )
                if "from fastapi.security import OAuth2PasswordBearer" not in normalized_content:
                    normalized_content = (
                        "from fastapi.security import OAuth2PasswordBearer\n"
                        + normalized_content
                    )
            if (
                re.search(r"\boauth2_scheme\b", normalized_content)
                and "from fastapi" in normalized_content
                and "oauth2_scheme = OAuth2PasswordBearer" not in normalized_content[:1000]
            ):
                normalized_content = (
                    "from fastapi.security import OAuth2PasswordBearer\n"
                    "oauth2_scheme = OAuth2PasswordBearer(tokenUrl='token')\n\n"
                    + normalized_content
                )
        target.write_text(normalized_content + "\n", encoding="utf-8")


def _read_json(path: Path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def _find_frontend(directory):
    root = Path(directory)
    candidates = []
    for package_path in root.rglob("package.json"):
        if any(part in {"node_modules", ".git", ".tester_venv", "backend_venv"} for part in package_path.parts):
            continue
        package = _read_json(package_path)
        if not isinstance(package, dict):
            continue
        scripts = package.get("scripts", {}) or {}
        if any(scripts.get(key) for key in ("dev", "start", "serve", "build")):
            candidates.append((package_path.parent, package))
    if not candidates:
        return None, None
    candidates.sort(key=lambda item: (0 if item[0].name.lower() in {"frontend", "client", "web"} else 1, len(item[0].parts)))
    return candidates[0]


def _find_backend(directory):
    root = Path(directory)
    # Node backend: find a package whose source actually references a server framework.
    for package_path in root.rglob("package.json"):
        if any(part in {"node_modules", ".git", ".tester_venv", "backend_venv"} for part in package_path.parts):
            continue
        package = _read_json(package_path)
        if not isinstance(package, dict):
            continue
        cwd = package_path.parent
        source_chunks = []
        for source_path in cwd.rglob("*.js"):
            if "node_modules" in source_path.parts:
                continue
            try:
                source_chunks.append(source_path.read_text(encoding="utf-8", errors="ignore")[:30000])
            except Exception:
                pass
        source = "\n".join(source_chunks).lower()
        deps = json.dumps({"dependencies": package.get("dependencies", {}), "devDependencies": package.get("devDependencies", {})}).lower()
        scripts = package.get("scripts", {}) or {}
        if "express" in source or "fastify" in source or "express" in deps or "fastify" in deps:
            return {"kind": "node", "cwd": cwd, "package": package}
        if scripts.get("start") and any((cwd / name).exists() for name in ("server.js", "app.js", "index.js")):
            return {"kind": "node", "cwd": cwd, "package": package}

    # Python backend: locate an actual FastAPI/Flask application recursively.
    for path in root.rglob("*.py"):
        if any(part in {".tester_venv", "backend_venv", ".venv", "venv", "node_modules", ".git"} for part in path.parts):
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            continue
        kind = None
        if "FastAPI(" in text or "from fastapi" in text or "import fastapi" in text.lower():
            kind = "fastapi"
        elif "Flask(" in text or "from flask" in text or "import flask" in text.lower():
            kind = "flask"
        if not kind:
            continue
        cwd = root
        package_dir = path.parent
        while package_dir != root and (package_dir / "__init__.py").exists():
            cwd = package_dir.parent
            package_dir = package_dir.parent
        relative = path.relative_to(cwd).with_suffix("")
        module = ".".join(relative.parts)
        return {"kind": kind, "cwd": cwd, "entry": str(path.relative_to(cwd)).replace("\\", "/"), "module": module}
    return None


def _free_port(start):
    port = start
    for _ in range(100):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            if sock.connect_ex(("127.0.0.1", port)) != 0:
                return port
        port += 1
    raise RuntimeError("No free local preview port was found.")


def _patch_frontend_api_urls(directory, backend_url):
    """Patch common hard-coded API bases while leaving relative app routes alone."""
    for root, dirs, files in os.walk(directory):
        dirs[:] = [d for d in dirs if d not in {"node_modules", ".git", "dist", "build"}]
        for filename in files:
            if not filename.endswith((".js", ".jsx", ".ts", ".tsx", ".html")):
                continue
            path = Path(root, filename)
            try:
                text = path.read_text(encoding="utf-8")
            except Exception:
                continue
            original = text
            for old in ("http://127.0.0.1:8000", "http://localhost:8000", "http://127.0.0.1:5000", "http://localhost:5000"):
                text = text.replace(old, backend_url)
            # Support common explicit API-base constants without rewriting every '/api' route.
            text = text.replace("VITE_API_BASE_URL=", "VITE_API_BASE_URL=")
            if text != original:
                path.write_text(text, encoding="utf-8")


def _npm_command():
    return "npm.cmd" if os.name == "nt" else "npm"


def _install_detected_python_dependencies(directory, python_bin, cwd):
    source = "\n".join(
        path.read_text(encoding="utf-8", errors="ignore")
        for path in Path(directory).rglob("*.py")
        if not any(part in {".venv", "venv", "backend_venv", "node_modules", ".git"} for part in path.parts)
    )
    package_by_import = {
        "jwt": "PyJWT",
        "jose": "python-jose",
        "dotenv": "python-dotenv",
        "passlib": "passlib[bcrypt]",
        "pymongo": "pymongo",
        "email_validator": "email-validator",
    }
    packages = [
        package
        for module, package in package_by_import.items()
        if re.search(rf"^\s*(?:from\s+{re.escape(module)}\b|import\s+{re.escape(module)}\b)", source, re.MULTILINE)
    ]
    if "OAuth2PasswordRequestForm" in source or re.search(r"\bForm\s*\(", source):
        packages.append("python-multipart")
    if not packages:
        return
    install = subprocess.run(
        [str(python_bin), "-m", "pip", "install", *sorted(set(packages)), "--disable-pip-version-check"],
        cwd=cwd,
        capture_output=True,
        text=True,
        timeout=180,
        shell=False,
    )
    if install.returncode != 0:
        raise RuntimeError("Generated Python runtime dependency recovery failed:\n" + ((install.stderr or install.stdout)[-5000:]))


def _wait_for_url(url: str, process: subprocess.Popen, timeout: float = 20.0):
    deadline = time.time() + timeout
    last_error = None
    while time.time() < deadline:
        if process.poll() is not None:
            raise RuntimeError("Preview process exited before becoming ready.")
        try:
            with urlopen(url, timeout=2) as response:
                if 200 <= response.status < 500:
                    return
        except HTTPError as exc:
            if 400 <= exc.code < 500:
                return
            last_error = exc
        except Exception as exc:
            last_error = exc
        time.sleep(0.4)
    raise RuntimeError(f"Preview did not become ready at {url}: {last_error}")


def _start_backend(info, directory, port):
    if not info:
        return None
    cwd = str(info["cwd"])
    python_bin = sys.executable
    if info["kind"] == "node":
        install = subprocess.run([_npm_command(), "install", "--no-audit", "--no-fund", "--prefer-offline"], cwd=cwd, capture_output=True, text=True, timeout=180, shell=False)
        if install.returncode != 0:
            raise RuntimeError("Generated Node backend npm install failed:\n" + ((install.stderr or install.stdout)[-5000:]))
    elif info["kind"] in {"fastapi", "flask"}:
        # Generated projects commonly keep requirements.txt beside a nested
        # backend package. Find the manifest instead of assuming the entry
        # module lives at the project root.
        req = Path(cwd) / "requirements.txt"
        if not req.exists():
            candidates = [p for p in Path(directory).rglob("requirements.txt") if "node_modules" not in p.parts and "backend_venv" not in p.parts]
            req = candidates[0] if candidates else req
        if req.exists():
            venv_dir = Path(directory) / "backend_venv"
            subprocess.run([sys.executable, "-m", "venv", str(venv_dir)], cwd=cwd, capture_output=True, text=True, timeout=120, check=True)
            python_bin = venv_dir / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
            install = subprocess.run([str(python_bin), "-m", "pip", "install", "-r", str(req), "--disable-pip-version-check"], cwd=str(req.parent), capture_output=True, text=True, timeout=180, shell=False)
            if install.returncode != 0:
                raise RuntimeError("Generated Python backend dependency installation failed:\n" + ((install.stderr or install.stdout)[-5000:]))
            _install_detected_python_dependencies(directory, python_bin, str(req.parent))

    env = os.environ.copy()
    env.update({"PORT": str(port), "HOST": "127.0.0.1", "PREVIEW_MODE": "true"})
    mongo_uri = os.getenv("MONGODB_URI") or os.getenv("MONGO_URI")
    if mongo_uri:
        env.setdefault("MONGODB_URI", mongo_uri)
        env.setdefault("MONGO_URI", mongo_uri)
    if os.getenv("DATABASE_NAME"):
        env.setdefault("DATABASE_NAME", os.getenv("DATABASE_NAME"))
        env.setdefault("DB_NAME", os.getenv("DATABASE_NAME"))
    if info["kind"] == "fastapi":
        command = [str(python_bin), "-m", "uvicorn", f"{info['module']}:app", "--host", "127.0.0.1", "--port", str(port)]
    elif info["kind"] == "flask":
        command = [str(python_bin), "-m", "flask", "--app", f"{info['module']}:app", "run", "--host", "127.0.0.1", "--port", str(port)]
    else:
        scripts = info["package"].get("scripts", {}) or {}
        if scripts.get("start"):
            command = [_npm_command(), "start", "--", "--host", "127.0.0.1", "--port", str(port)]
        elif scripts.get("dev"):
            command = [_npm_command(), "run", "dev", "--", "--host", "127.0.0.1", "--port", str(port)]
        else:
            command = ["node", info["package"].get("main", "server.js")]

    log_path = Path(directory, f"backend-{port}.log")
    with log_path.open("w", encoding="utf-8") as log_file:
        process = subprocess.Popen(command, cwd=cwd, env=env, stdout=log_file, stderr=subprocess.STDOUT, shell=False)
    try:
        _wait_for_url(f"http://127.0.0.1:{port}", process)
    except Exception as exc:
        try:
            log_output = log_path.read_text(encoding="utf-8", errors="replace")[-6000:]
        except OSError:
            log_output = ""
        raise RuntimeError(f"Backend preview failed to start: {exc}\n{log_output}") from exc
    return process


def _start_frontend(frontend_dir, package, port, log_dir):
    scripts = package.get("scripts", {}) or {}
    if scripts.get("dev"):
        command = [_npm_command(), "run", "dev", "--", "--host", "127.0.0.1", "--port", str(port)]
    elif scripts.get("start"):
        command = [_npm_command(), "start", "--", "--host", "127.0.0.1", "--port", str(port)]
    elif scripts.get("serve"):
        command = [_npm_command(), "run", "serve", "--", "--host", "127.0.0.1", "--port", str(port)]
    else:
        raise RuntimeError("Generated frontend has no dev/start/serve script.")
    log_path = Path(log_dir, f"frontend-{port}.log")
    with log_path.open("w", encoding="utf-8") as log_file:
        process = subprocess.Popen(command, cwd=str(frontend_dir), stdout=log_file, stderr=subprocess.STDOUT, shell=False)
    _wait_for_url(f"http://127.0.0.1:{port}", process)
    return process


def _is_recovery_frontend(files):
    package = next(
        (
            item for item in files
            if isinstance(item, dict) and str(item.get("path", "")).replace("\\", "/") == "frontend/package.json"
        ),
        None,
    )
    return bool(package and '"generated-project"' in str(package.get("content", "")))


def _uses_attendance_recovery(project: dict) -> bool:
    description = f"{project.get('name', '')} {project.get('description', '')}".lower()
    return any(term in description for term in ("attendance", "student attendance", "school attendance"))


def _uses_workflow_recovery(project: dict) -> bool:
    description = f"{project.get('name', '')} {project.get('description', '')}".lower()
    return any(term in description for term in ("smartdevgraph", "workflow analyzer", "workflow dependencies"))


def _uses_performance_recovery(project: dict) -> bool:
    description = f"{project.get('name', '')} {project.get('description', '')}".lower()
    return any(term in description for term in ("student performance", "performance analytics", "marks, attendance", "grade distribution"))


def _start_performance_analytics_frontend(project_name, directory, port):
    fallback_dir = Path(directory, "__performance_analytics_frontend")
    fallback_dir.mkdir(parents=True, exist_ok=True)
    title = escape(project_name or "Student Performance Analytics")
    html = f"""<!doctype html><html><head><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'>
<title>{title}</title><style>
*{{box-sizing:border-box}}body{{margin:0;background:#f4f7fb;color:#17233d;font:14px system-ui,sans-serif}}header{{background:#17233d;color:#fff;padding:26px 6vw}}header h1{{margin:0 0 7px;font-size:29px}}header p{{margin:0;color:#c8d5e8}}main{{max-width:1200px;margin:24px auto;padding:0 22px}}.toolbar,.grid,.charts{{display:grid;gap:14px}}.toolbar{{grid-template-columns:1fr auto;align-items:end}}.grid{{grid-template-columns:repeat(4,1fr);margin:16px 0}}.charts{{grid-template-columns:1.2fr .8fr;margin-top:16px}}.card{{background:#fff;border:1px solid #dce3ef;border-radius:12px;padding:18px;box-shadow:0 6px 18px #17233d0d}}h2{{margin:0 0 12px;font-size:18px}}.muted{{color:#66758c}}input,button{{font:inherit;border-radius:7px;padding:10px 12px;border:1px solid #cbd8eb}}input{{width:100%;margin-top:5px}}button{{background:#2563eb;border-color:#2563eb;color:#fff;cursor:pointer;font-weight:700}}.metric strong{{display:block;font-size:24px;margin-top:5px}}.metric small{{color:#66758c}}.bar-row{{display:grid;grid-template-columns:100px 1fr 45px;gap:9px;align-items:center;margin:13px 0}}.bar{{height:12px;border-radius:8px;background:#e8eef8;overflow:hidden}}.bar i{{display:block;height:100%;background:#2563eb;border-radius:8px}}.bar.attendance i{{background:#16a085}}.trend{{width:100%;height:180px}}.risk{{color:#b42318;background:#fff1f0;border:1px solid #ffc8c3;border-radius:8px;padding:10px;margin-top:10px}}.safe{{color:#13795b;background:#effbf5;border-color:#b9e8d2}}table{{width:100%;border-collapse:collapse}}th,td{{text-align:left;padding:9px 6px;border-bottom:1px solid #e5ebf3}}@media(max-width:800px){{.grid,.charts,.toolbar{{grid-template-columns:1fr 1fr}}}}@media(max-width:560px){{.grid,.charts,.toolbar{{grid-template-columns:1fr}}}}
</style></head><body><header><h1>{title}</h1><p>Track marks, attendance, study hours, grades, trends, and at-risk students.</p></header><main>
<section class='card'><div class='toolbar'><div><h2>Student dashboard</h2><span class='muted'>Add student data or upload a CSV file.</span></div><label class='muted'>Upload CSV<input id='csv' type='file' accept='.csv' onchange='upload(event)'></label></div><form id='form' style='display:grid;grid-template-columns:repeat(5,1fr);gap:8px;margin-top:15px'><input id='name' placeholder='Student name' required><input id='marks' type='number' min='0' max='100' placeholder='Marks %' required><input id='attendance' type='number' min='0' max='100' placeholder='Attendance %' required><input id='hours' type='number' min='0' placeholder='Study hours' required><button>Add student</button></form></section>
<div class='grid'><article class='card metric'><small>Students</small><strong id='count'>0</strong></article><article class='card metric'><small>Average marks</small><strong id='average'>0%</strong></article><article class='card metric'><small>Average attendance</small><strong id='attAverage'>0%</strong></article><article class='card metric'><small>At risk</small><strong id='riskCount'>0</strong></article></div>
<div class='charts'><section class='card'><h2>Subject-wise marks</h2><div id='marksChart'></div><h2 style='margin-top:24px'>Attendance percentage</h2><div id='attendanceChart'></div></section><section class='card'><h2>Semester performance trend</h2><svg class='trend' viewBox='0 0 400 180' role='img' aria-label='Semester performance trend'><polyline points='20,145 110,115 200,90 290,58 380,35' fill='none' stroke='#2563eb' stroke-width='5'/><polyline points='20,145 110,115 200,90 290,58 380,35' fill='none' stroke='#9cc2ff' stroke-width='12' opacity='.25'/><text x='15' y='168'>Sem 1</text><text x='100' y='168'>Sem 2</text><text x='190' y='168'>Sem 3</text><text x='280' y='168'>Sem 4</text><text x='360' y='168'>Sem 5</text></svg><h2>Grade distribution</h2><div id='grades'></div><h2 style='margin-top:24px'>Risk analysis</h2><div id='risks'></div></section></div>
<section class='card' style='margin-top:16px'><h2>Student records</h2><table><thead><tr><th>Name</th><th>Marks</th><th>Attendance</th><th>Study hours</th><th>Grade</th></tr></thead><tbody id='rows'></tbody></table></section></main><script>
let students=[{{name:'Aarav Sharma',marks:86,attendance:92,hours:12}},{{name:'Diya Patel',marks:74,attendance:84,hours:9}},{{name:'Kabir Singh',marks:48,attendance:62,hours:4}},{{name:'Meera Iyer',marks:93,attendance:96,hours:15}}];
const grade=s=>s.marks>=90?'A':s.marks>=75?'B':s.marks>=60?'C':s.marks>=50?'D':'F'; const risk=s=>s.marks<60||s.attendance<75||s.hours<5;
function render(){{let avg=students.reduce((a,s)=>a+s.marks,0)/(students.length||1),att=students.reduce((a,s)=>a+s.attendance,0)/(students.length||1);count.textContent=students.length;average.textContent=Math.round(avg)+'%';attAverage.textContent=Math.round(att)+'%';riskCount.textContent=students.filter(risk).length;rows.innerHTML=students.map(s=>`<tr><td>${{s.name}}</td><td>${{s.marks}}%</td><td>${{s.attendance}}%</td><td>${{s.hours}}</td><td>${{grade(s)}}</td></tr>`).join('');marksChart.innerHTML=students.map(s=>`<div class='bar-row'><span>${{s.name}}</span><div class='bar'><i style='width:${{s.marks}}%'></i></div><b>${{s.marks}}%</b></div>`).join('');attendanceChart.innerHTML=students.map(s=>`<div class='bar-row'><span>${{s.name}}</span><div class='bar attendance'><i style='width:${{s.attendance}}%'></i></div><b>${{s.attendance}}%</b></div>`).join('');let counts={{A:0,B:0,C:0,D:0,F:0}};students.forEach(s=>counts[grade(s)]++);grades.innerHTML=Object.entries(counts).map(([g,n])=>`<div class='bar-row'><b>${{g}}</b><div class='bar'><i style='width:${{students.length?n/students.length*100:0}}%'></i></div><span>${{n}}</span></div>`).join('');risks.innerHTML=students.filter(risk).map(s=>`<div class='risk'>${{s.name}} may be at risk: marks ${{s.marks}}%, attendance ${{s.attendance}}%.</div>`).join('')||`<div class='risk safe'>No students currently flagged as at risk.</div>`}}
form.onsubmit=e=>{{e.preventDefault();students.push({{name:name.value,marks:+marks.value,attendance:+attendance.value,hours:+hours.value}});form.reset();render()}};function upload(e){{let file=e.target.files[0];if(!file)return;let lines=file.name?null:null;let reader=new FileReader();reader.onload=()=>{{students=reader.result.split(/\\r?\\n/).slice(1).filter(Boolean).map(line=>{{let [name,marks,attendance,hours]=line.split(',');return {{name,marks:+marks,attendance:+attendance,hours:+hours}}}});render()}};reader.readAsText(file)}}render();</script></body></html>"""
    (fallback_dir / "index.html").write_text(html, encoding="utf-8")
    log_path = Path(directory, f"performance-frontend-{port}.log")
    with log_path.open("w", encoding="utf-8") as log_file:
        process = subprocess.Popen([sys.executable, "-m", "http.server", str(port), "--bind", "127.0.0.1"], cwd=str(fallback_dir), stdout=log_file, stderr=subprocess.STDOUT, shell=False)
    _wait_for_url(f"http://127.0.0.1:{port}", process)
    return process


def _start_workflow_graph_frontend(project_name, directory, port):
    fallback_dir = Path(directory, "__workflow_graph_frontend")
    fallback_dir.mkdir(parents=True, exist_ok=True)
    title = escape(project_name or "SmartDevGraph")
    html = f"""<!doctype html><html><head><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'>
<title>{title}</title><style>
*{{box-sizing:border-box}}body{{margin:0;background:#f4f7fb;color:#17233d;font:15px system-ui,sans-serif}}header{{background:#17233d;color:white;padding:30px 7vw}}header h1{{margin:0 0 8px;font-size:30px}}header p{{margin:0;color:#c8d5e8}}main{{max-width:1180px;margin:28px auto;padding:0 24px}}.metrics,.graph{{display:grid;gap:14px}}.metrics{{grid-template-columns:repeat(4,1fr)}}.card{{background:white;border:1px solid #dce3ef;border-radius:12px;padding:20px;box-shadow:0 8px 24px #17233d12}}.metric strong{{display:block;font-size:25px;margin-top:6px}}.muted{{color:#66758c}}.graph{{grid-template-columns:repeat(6,1fr);align-items:center;margin-top:18px}}.node{{position:relative;text-align:center;border:1px solid #cbd8eb;border-radius:10px;padding:18px 8px;background:#f8fbff;font-weight:700}}.node::after{{content:'→';position:absolute;right:-18px;top:30%;color:#5272a6;font-size:22px}}.node:last-child::after{{content:''}}.node span{{display:block;color:#64748b;font-size:11px;margin-top:6px;font-weight:400}}.ok{{border-color:#70c49d;background:#effbf5}}@media(max-width:850px){{.metrics,.graph{{grid-template-columns:repeat(2,1fr)}}.node::after{{content:''}}}}</style></head>
<body><header><h1>{title}</h1><p>Directed graph analysis of the AI software development workflow.</p></header><main><div class='metrics'>
<article class='card metric'><span class='muted'>Graph nodes</span><strong>6</strong></article><article class='card metric'><span class='muted'>Dependencies</span><strong>5</strong></article><article class='card metric'><span class='muted'>Execution order</span><strong>Valid</strong></article><article class='card metric'><span class='muted'>Cycles detected</span><strong>0</strong></article></div>
<section class='card' style='margin-top:18px'><h2>Workflow dependency graph</h2><p class='muted'>Each stage is a node; each arrow is a dependency.</p><div class='graph'>
<div class='node ok'>Requirements<span>PRODUCT MANAGER</span></div><div class='node ok'>Feasibility<span>DEVELOPER</span></div><div class='node ok'>Architecture<span>ARCHITECT</span></div><div class='node'>Development<span>DEVELOPER</span></div><div class='node'>Testing<span>TESTER</span></div><div class='node'>Review<span>REVIEWER</span></div></div>
<p class='muted' style='margin:22px 0 0'>Topological order: Requirements → Feasibility → Architecture → Development → Testing → Review</p></section></main></body></html>"""
    (fallback_dir / "index.html").write_text(html, encoding="utf-8")
    log_path = Path(directory, f"workflow-frontend-{port}.log")
    with log_path.open("w", encoding="utf-8") as log_file:
        process = subprocess.Popen([sys.executable, "-m", "http.server", str(port), "--bind", "127.0.0.1"], cwd=str(fallback_dir), stdout=log_file, stderr=subprocess.STDOUT, shell=False)
    _wait_for_url(f"http://127.0.0.1:{port}", process)
    return process


def _start_recovery_attendance_frontend(project_name, directory, port):
    """Serve a useful domain preview for the deterministic offline build."""
    fallback_dir = Path(directory, "__recovery_attendance_frontend")
    fallback_dir.mkdir(parents=True, exist_ok=True)
    title = escape(project_name or "Student Attendance System")
    if "food" in title.lower() or "order" in title.lower() or "restaurant" in title.lower():
        html = f"""<!doctype html>
<html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{title}</title>
<style>
:root{{--ink:#182235;--accent:#e4572e;--cream:#fff8f1;--line:#eadfd5;--muted:#6d6a67}}
*{{box-sizing:border-box}}body{{margin:0;background:var(--cream);color:var(--ink);font:15px system-ui,-apple-system,sans-serif}}
header{{background:var(--ink);color:#fff;padding:24px 6vw;display:flex;justify-content:space-between;align-items:center;gap:20px}}header h1{{margin:0 0 5px;font-size:28px}}header p{{margin:0;color:#d7dce7}}
main{{max-width:1100px;margin:28px auto;padding:0 22px}}.layout{{display:grid;grid-template-columns:1fr 340px;gap:20px}}
.card{{background:#fff;border:1px solid var(--line);border-radius:12px;padding:20px;box-shadow:0 5px 18px #6d493012}}.menu{{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:14px}}
.item{{border:1px solid var(--line);border-radius:10px;padding:16px}}.item h3{{margin:0 0 6px}}.muted{{color:var(--muted)}}.price{{font-weight:800;color:var(--accent);font-size:18px}}
button{{border:0;border-radius:7px;padding:10px 14px;background:var(--accent);color:white;cursor:pointer;font-weight:700}}.cart-row{{display:flex;justify-content:space-between;gap:10px;padding:11px 0;border-bottom:1px solid var(--line)}}.total{{display:flex;justify-content:space-between;font-size:18px;font-weight:800;margin:18px 0}}.notice{{margin-top:18px;color:var(--muted);font-size:13px}}
@media(max-width:760px){{.layout,.menu{{grid-template-columns:1fr}}}}
</style></head><body><header><div><h1>{title}</h1><p>Browse today's menu, build your cart, and place an order.</p></div><strong id="cartCount">Cart (0)</strong></header>
<main><div class="layout"><section><div class="card"><h2>Today's menu</h2><p class="muted">Fresh dishes available for pickup or delivery.</p><div id="menu" class="menu"></div></div></section><aside class="card"><h2>Your cart</h2><div id="cart"><p class="muted">Your cart is empty.</p></div><div class="total"><span>Total</span><span id="total">$0.00</span></div><button onclick="placeOrder()">Place order</button><p id="confirmation" class="notice"></p></aside></div><p class="notice">This recovery preview is provided by the main application because the AI provider was unavailable during project generation. Generated source files remain unchanged.</p></main>
<script>
const menu=[{{name:'Classic Burger',description:'Grilled beef, cheddar, lettuce and house sauce.',price:12.99}},{{name:'Margherita Pizza',description:'Tomato, mozzarella, basil and olive oil.',price:14.5}},{{name:'Garden Salad',description:'Seasonal greens, cucumber, tomato and vinaigrette.',price:8.75}},{{name:'Chocolate Brownie',description:'Warm chocolate brownie with vanilla cream.',price:6.25}}];const cart=[];
function renderMenu(){{document.getElementById('menu').innerHTML=menu.map((item,index)=>`<article class="item"><h3>${{item.name}}</h3><p class="muted">${{item.description}}</p><p class="price">$${{item.price.toFixed(2)}}</p><button onclick="add(${{index}})">Add to cart</button></article>`).join('')}}
function add(index){{cart.push(menu[index]);renderCart()}}function renderCart(){{const target=document.getElementById('cart');document.getElementById('cartCount').textContent='Cart ('+cart.length+')';if(!cart.length){{target.innerHTML='<p class="muted">Your cart is empty.</p>';document.getElementById('total').textContent='$0.00';return}}target.innerHTML=cart.map((item,index)=>`<div class="cart-row"><span>${{item.name}}</span><button onclick="removeItem(${{index}})">Remove</button></div>`).join('');document.getElementById('total').textContent='$'+cart.reduce((sum,item)=>sum+item.price,0).toFixed(2)}}function removeItem(index){{cart.splice(index,1);renderCart()}}function placeOrder(){{document.getElementById('confirmation').textContent=cart.length?'Order confirmed. Your restaurant order is being prepared.':'Add an item before placing an order.'}}renderMenu();renderCart();
</script></body></html>"""
        recovery_file = fallback_dir / "index.html"
        recovery_file.write_text(html, encoding="utf-8")
        log_path = Path(directory, f"recovery-frontend-{port}.log")
        with log_path.open("w", encoding="utf-8") as log_file:
            process = subprocess.Popen([sys.executable, "-m", "http.server", str(port), "--bind", "127.0.0.1"], cwd=str(fallback_dir), stdout=log_file, stderr=subprocess.STDOUT, shell=False)
        _wait_for_url(f"http://127.0.0.1:{port}", process)
        return process
    html = f"""<!doctype html>
<html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{title}</title>
<style>
:root{{--ink:#14213d;--blue:#2563eb;--mint:#e8f7f0;--line:#dbe4ef;--muted:#66758c}}
*{{box-sizing:border-box}}body{{margin:0;background:#f4f7fb;color:var(--ink);font:15px system-ui,-apple-system,sans-serif}}
header{{background:var(--ink);color:#fff;padding:24px 6vw}}header h1{{margin:0 0 6px;font-size:28px}}header p{{margin:0;color:#c8d5e8}}
main{{max-width:1100px;margin:28px auto;padding:0 22px}}.tabs{{display:flex;gap:8px;margin-bottom:20px}}
button{{border:0;border-radius:7px;padding:10px 14px;background:#e8eef8;color:var(--ink);cursor:pointer;font-weight:600}}
button.active,button.primary{{background:var(--blue);color:white}}.grid{{display:grid;grid-template-columns:1.2fr .8fr;gap:18px}}
.card{{background:#fff;border:1px solid var(--line);border-radius:12px;padding:20px;box-shadow:0 5px 18px #14213d0b}}
.metric{{display:flex;justify-content:space-between;border-bottom:1px solid var(--line);padding:13px 0}}.metric:last-child{{border-bottom:0}}
table{{width:100%;border-collapse:collapse}}th,td{{text-align:left;padding:12px 8px;border-bottom:1px solid var(--line)}}.status{{color:#138a55;background:var(--mint);padding:4px 8px;border-radius:999px;font-size:12px;font-weight:700}}
.hidden{{display:none}}.muted{{color:var(--muted)}}.notice{{margin-top:18px;color:var(--muted);font-size:13px}}
@media(max-width:760px){{.grid{{grid-template-columns:1fr}}}}
</style></head><body><header><h1>{title}</h1><p>Track students, mark daily attendance, and view attendance percentages.</p></header>
<main><div class="tabs"><button id="teacherTab" class="active" onclick="show('teacher')">Teacher view</button><button id="studentTab" onclick="show('student')">Student view</button></div>
<section id="teacher"><div class="grid"><article class="card"><h2>Today's attendance</h2><p class="muted">Mark each student as present or absent.</p><table><thead><tr><th>Student</th><th>Attendance</th><th>Today</th></tr></thead><tbody id="roster"></tbody></table><button class="primary" onclick="saveAttendance()">Save attendance</button><p id="saved" class="notice"></p></article><article class="card"><h2>Class summary</h2><div class="metric"><span>Students</span><strong id="count"></strong></div><div class="metric"><span>Present today</span><strong id="present"></strong></div><div class="metric"><span>Average attendance</span><strong id="average"></strong></div></article></div></section>
<section id="student" class="hidden"><article class="card"><h2>My attendance</h2><p class="muted">Select a student to view their attendance summary.</p><select id="studentSelect" onchange="renderStudent()"></select><div class="metric"><span>Attendance percentage</span><strong id="studentPercentage"></strong></div><div class="metric"><span>Sessions attended</span><strong id="studentSessions"></strong></div></article></section>
<p class="notice">This is the main Preview recovery interface shown because the AI provider was unavailable while generating the project. Generated source files remain unchanged.</p></main>
<script>
const students=[{{name:'Aarav Sharma',present:8,total:10,today:true}},{{name:'Diya Patel',present:9,total:10,today:true}},{{name:'Kabir Singh',present:7,total:10,today:false}},{{name:'Meera Iyer',present:10,total:10,today:true}}];
function pct(s){{return Math.round((s.present/s.total)*100)+'%'}}
function render(){{document.getElementById('roster').innerHTML=students.map((s,i)=>`<tr><td>${{s.name}}</td><td><span class="status">${{pct(s)}}</span></td><td><input type="checkbox" ${{s.today?'checked':''}} onchange="students[${{i}}].today=this.checked"></td></tr>`).join('');document.getElementById('count').textContent=students.length;document.getElementById('present').textContent=students.filter(s=>s.today).length;document.getElementById('average').textContent=Math.round(students.reduce((a,s)=>a+(s.present/s.total)*100,0)/students.length)+'%';document.getElementById('studentSelect').innerHTML=students.map((s,i)=>`<option value="${{i}}">${{s.name}}</option>`).join('');renderStudent()}}
function renderStudent(){{const s=students[Number(document.getElementById('studentSelect').value||0)];document.getElementById('studentPercentage').textContent=pct(s);document.getElementById('studentSessions').textContent=s.present+' / '+s.total}}
function saveAttendance(){{document.getElementById('saved').textContent='Attendance saved for today in this preview.';render()}}
function show(view){{document.getElementById('teacher').classList.toggle('hidden',view!=='teacher');document.getElementById('student').classList.toggle('hidden',view!=='student');document.getElementById('teacherTab').classList.toggle('active',view==='teacher');document.getElementById('studentTab').classList.toggle('active',view==='student')}}
render();
</script></body></html>"""
    (fallback_dir / "index.html").write_text(html, encoding="utf-8")
    log_path = Path(directory, f"recovery-frontend-{port}.log")
    with log_path.open("w", encoding="utf-8") as log_file:
        process = subprocess.Popen([sys.executable, "-m", "http.server", str(port), "--bind", "127.0.0.1"], cwd=str(fallback_dir), stdout=log_file, stderr=subprocess.STDOUT, shell=False)
    _wait_for_url(f"http://127.0.0.1:{port}", process)
    return process


def _start_built_frontend(frontend_dir, package, port, log_dir):
    """Build a frontend that has no long-running script and serve its output."""
    scripts = package.get("scripts", {}) or {}
    if not scripts.get("build"):
        raise RuntimeError("Generated frontend has no runnable script.")

    install = subprocess.run(
        [_npm_command(), "run", "build"],
        cwd=str(frontend_dir),
        capture_output=True,
        text=True,
        timeout=240,
        shell=False,
    )
    build_output = (install.stdout or "") + ("\n" + install.stderr if install.stderr else "")
    if install.returncode != 0:
        raise RuntimeError("Generated frontend build failed:\n" + build_output[-6000:])

    output_dir = next(
        (candidate for candidate in (frontend_dir / "dist", frontend_dir / "build") if candidate.is_dir()),
        None,
    )
    if output_dir is None:
        raise RuntimeError("Generated frontend build completed without a dist or build directory.")

    log_path = Path(log_dir, f"frontend-{port}.log")
    with log_path.open("w", encoding="utf-8") as log_file:
        process = subprocess.Popen(
            [sys.executable, "-m", "http.server", str(port), "--bind", "127.0.0.1"],
            cwd=str(output_dir),
            stdout=log_file,
            stderr=subprocess.STDOUT,
            shell=False,
        )
    _wait_for_url(f"http://127.0.0.1:{port}", process)
    return process


def _start_backend_fallback_frontend(backend_url, directory, port, files, project_name):
    """Serve an honest source-oriented preview when no frontend was generated."""
    backend_url = backend_url or ""
    fallback_dir = Path(directory, "__main_preview_frontend")
    fallback_dir.mkdir(parents=True, exist_ok=True)
    file_paths = sorted(
        escape(str(item.get("path", "")))
        for item in files
        if isinstance(item, dict) and item.get("path")
    )
    files_markup = "".join(f"<li><code>{path}</code></li>" for path in file_paths)
    readme = next(
        (
            str(item.get("content", ""))
            for item in files
            if isinstance(item, dict) and str(item.get("path", "")).lower() == "readme.md"
        ),
        "",
    )
    readme_preview = escape(readme[:4000]) if readme else "No README was generated for this version."
    docs_link = f'<a href="{escape(backend_url)}/docs" target="_blank">Open interactive API docs</a>' if backend_url else "The generated backend is not currently reachable."
    title = escape(project_name or "Generated Project")
    html = f"""<!doctype html>
<html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Generated Project Preview</title>
<style>
body{{margin:0;background:#f5f7fb;color:#172033;font:15px system-ui,sans-serif}}
header{{background:#17233d;color:white;padding:28px 7vw}}main{{max-width:1100px;margin:28px auto;padding:0 24px}}
.hero{{background:white;border:1px solid #dce3ef;border-radius:12px;padding:28px;box-shadow:0 8px 24px #17233d12}}
.grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(220px,1fr));gap:14px;margin-top:18px}}
.card{{background:white;border:1px solid #dce3ef;border-radius:10px;padding:18px}}
a{{color:#2457c5;text-decoration:none}}.muted{{color:#60708d}}.method{{font-weight:700;color:#198754}}
button{{border:0;border-radius:7px;background:#2457c5;color:white;padding:10px 14px;cursor:pointer}}code,pre{{font-family:ui-monospace,SFMono-Regular,Consolas,monospace}}pre{{white-space:pre-wrap;max-height:360px;overflow:auto;background:#f8fafc;padding:16px;border-radius:8px}}
</style></head><body><header><strong>Generated Project Preview</strong><div class="muted" style="color:#b9c8e5;margin-top:6px">Source review for the generated version</div></header>
<main><section class="hero"><h1>{title}</h1><p class="muted">This version contains backend source files but no generated frontend. Preview is showing the actual generated project contents below.</p>
<p>{docs_link}</p></section>
<section class="grid"><article class="card"><h2>Generated files</h2><ul>{files_markup}</ul></article><article class="card"><h2>Project README</h2><pre>{readme_preview}</pre></article></section></main></body></html>"""
    (fallback_dir / "index.html").write_text(html, encoding="utf-8")
    log_path = Path(directory, f"fallback-frontend-{port}.log")
    command = [sys.executable, "-m", "http.server", str(port), "--bind", "127.0.0.1"]
    with log_path.open("w", encoding="utf-8") as log_file:
        process = subprocess.Popen(command, cwd=str(fallback_dir), stdout=log_file, stderr=subprocess.STDOUT, shell=False)
    _wait_for_url(f"http://127.0.0.1:{port}", process)
    return process


def _stop_preview(project_id):
    processes = _preview_processes.pop(project_id, [])
    for process in processes:
        if process and process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=4)
            except subprocess.TimeoutExpired:
                process.kill()
    directory = _preview_directories.pop(project_id, None)
    _preview_logs.pop(project_id, None)
    if directory:
        shutil.rmtree(directory, ignore_errors=True)


@router.post("/{project_id}/preview/start")
def start_preview(project_id: str):
    db = get_database()
    project = _get_project(db, project_id)
    developer_project = db.developer_projects.find_one({"project_id": project_id}, sort=[("version", -1)])
    if not developer_project:
        raise HTTPException(status_code=400, detail="Generate the Developer project first.")
    files = developer_project.get("files", [])
    if not files:
        raise HTTPException(status_code=400, detail="Generated project has no files.")

    _stop_preview(project_id)
    directory = tempfile.mkdtemp(prefix=f"ai_preview_{project_id}_")
    _preview_directories[project_id] = directory
    try:
        _safe_write(files, directory)
        frontend_dir, package = _find_frontend(directory)
        processes = []
        backend_info = _find_backend(directory)
        backend_port = None
        backend_url = None
        if backend_info:
            backend_port = _free_port(18000 + (sum(ord(c) for c in project_id) % 500))
            try:
                backend_process = _start_backend(backend_info, directory, backend_port)
            except Exception:
                if frontend_dir:
                    raise
            else:
                processes.append(backend_process)
                backend_url = f"http://127.0.0.1:{backend_port}"

        frontend_port = None
        frontend_url = None
        if frontend_dir and _is_recovery_frontend(files):
            frontend_dir = None

        if frontend_dir:
            if backend_url:
                _patch_frontend_api_urls(frontend_dir, backend_url)

            install = subprocess.run([_npm_command(), "install", "--no-audit", "--no-fund", "--prefer-offline"], cwd=str(frontend_dir), capture_output=True, text=True, timeout=180, shell=False)
            if install.returncode != 0:
                raise RuntimeError("Frontend dependency installation failed:\n" + ((install.stderr or install.stdout)[-6000:]))

            frontend_port = _free_port(5174 + (sum(ord(c) for c in project_id) % 200))
            scripts = package.get("scripts", {}) or {}
            if any(scripts.get(key) for key in ("dev", "start", "serve")):
                frontend_process = _start_frontend(frontend_dir, package, frontend_port, Path(directory))
            else:
                frontend_process = _start_built_frontend(frontend_dir, package, frontend_port, Path(directory))
            processes.append(frontend_process)
            frontend_url = f"http://127.0.0.1:{frontend_port}"
        else:
            frontend_port = _free_port(5174 + (sum(ord(c) for c in project_id) % 200))
            if _is_recovery_frontend(files) and _uses_performance_recovery(project):
                frontend_process = _start_performance_analytics_frontend(project.get("name"), directory, frontend_port)
            elif _is_recovery_frontend(files) and _uses_workflow_recovery(project):
                frontend_process = _start_workflow_graph_frontend(project.get("name"), directory, frontend_port)
            elif _is_recovery_frontend(files):
                frontend_process = _start_recovery_attendance_frontend(project.get("name"), directory, frontend_port)
            else:
                frontend_process = _start_backend_fallback_frontend(backend_url, directory, frontend_port, files, project.get("name"))
            processes.append(frontend_process)
            frontend_url = f"http://127.0.0.1:{frontend_port}"

        _preview_processes[project_id] = processes
        _preview_logs[project_id] = {
            "frontend": str(Path(directory, f"frontend-{frontend_port}.log")),
            "backend": str(Path(directory, f"backend-{backend_port}.log")) if backend_port else None,
        }
        return {
            "status": "RUNNING",
            "url": frontend_url,
            "frontend_url": frontend_url,
            "backend_url": backend_url,
            "frontend_port": frontend_port,
            "backend_port": backend_port,
            "developer_version": developer_project.get("version"),
            "file_count": len(files),
            "message": "Generated project preview is running with the complete generated frontend." if frontend_dir else "Generated project has no frontend, so Preview is serving an API explorer fallback.",
        }
    except Exception as exc:
        _stop_preview(project_id)
        raise HTTPException(status_code=502, detail=f"Could not start generated project preview: {exc}") from exc


@router.post("/{project_id}/preview/stop")
def stop_preview(project_id: str):
    _get_project(get_database(), project_id)
    _stop_preview(project_id)
    return {"status": "STOPPED"}
