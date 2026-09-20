import json
import os
import re
import shutil
import subprocess
import tempfile
from pathlib import Path


TEXT_EXTENSIONS = {
    ".py", ".js", ".jsx", ".ts", ".tsx", ".mjs", ".cjs", ".json",
    ".html", ".css", ".md", ".txt", ".yml", ".yaml", ".toml", ".xml",
}


def _safe_path(path: str) -> str:
    value = str(path or "").replace("\\", "/").strip()
    p = Path(value)
    if not value or p.is_absolute() or ".." in p.parts:
        raise ValueError(f"Unsafe generated path: {path}")
    return value


def write_project(files: list[dict], root: str) -> None:
    for item in files or []:
        path = _safe_path(item.get("path", ""))
        target = Path(root, path)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(str(item.get("content", "")), encoding="utf-8")


def _normalize_json_configs(root: Path) -> list[str]:
    """Normalize common JSON config wrappers in the temporary build copy."""
    repaired: list[str] = []
    for path in root.rglob("*.json"):
        if any(part in {"node_modules", ".git", ".tester_venv"} for part in path.parts):
            continue
        if path.name != "package.json" and not path.name.startswith(("tsconfig", "jsconfig")):
            continue
        try:
            raw = path.read_text(encoding="utf-8").strip()
            candidate = re.sub(r"^```(?:json)?\s*", "", raw, flags=re.IGNORECASE)
            candidate = re.sub(r"\s*```$", "", candidate).strip()
            start = candidate.find("{")
            end = candidate.rfind("}")
            if start > 0 or end >= 0:
                candidate = candidate[start : end + 1]
            parsed = json.loads(candidate)
            if not isinstance(parsed, dict):
                continue
            if candidate != raw:
                path.write_text(json.dumps(parsed, indent=2) + "\n", encoding="utf-8")
                repaired.append(str(path.relative_to(root)))
        except (OSError, ValueError, json.JSONDecodeError):
            continue
    return repaired


def validate_project_files(files: list[dict]) -> list[str]:
    errors: list[str] = []
    seen: set[str] = set()
    if not files:
        return ["Developer generated no files."]

    for item in files:
        path = str(item.get("path", "")).replace("\\", "/").strip()
        if not path:
            errors.append("A generated file has no path.")
            continue
        try:
            _safe_path(path)
        except ValueError as exc:
            errors.append(str(exc))
        if path in seen:
            errors.append(f"Duplicate generated path: {path}")
        seen.add(path)

        content = str(item.get("content", ""))
        if Path(path).suffix.lower() in TEXT_EXTENSIONS and not content.strip():
            errors.append(f"Generated source/configuration file is empty: {path}")
        if Path(path).suffix.lower() == ".py" and content.strip() in {"None", "null", "undefined"}:
            errors.append(f"Generated Python source is a placeholder: {path}")

        if Path(path).name.lower() == "package.json" and content.strip():
            try:
                package = json.loads(content)
                if not isinstance(package, dict):
                    errors.append(f"package.json is not an object: {path}")
                elif not isinstance(package.get("scripts", {}), dict):
                    errors.append(f"package.json scripts must be an object: {path}")
            except Exception as exc:
                errors.append(f"Invalid package.json {path}: {exc}")

    return errors


def _find_frontend_packages(root: Path) -> list[Path]:
    packages = []
    for package_path in root.rglob("package.json"):
        if any(part in {"node_modules", ".git", ".tester_venv"} for part in package_path.parts):
            continue
        try:
            data = json.loads(package_path.read_text(encoding="utf-8"))
        except Exception:
            continue
        scripts = data.get("scripts", {}) if isinstance(data, dict) else {}
        if any(key in scripts for key in ("dev", "build", "start", "serve")):
            packages.append(package_path.parent)
    return packages


def _repair_missing_npm_version(package_dir: Path, output: str, npm: str) -> str | None:
    """Replace one registry-missing exact version reported by npm."""
    match = re.search(
        r"No matching version found for (@[^/\s]+/[^@\s]+|[A-Za-z0-9_.-]+)@([~^<>=]*\d+\.\d+\.\d+)",
        output or "",
        re.IGNORECASE,
    )
    if not match:
        return None

    package_name, requested_version = match.groups()
    manifest_path = package_dir / "package.json"
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        latest = subprocess.run(
            [npm, "view", package_name, "version", "--json"],
            cwd=package_dir,
            capture_output=True,
            text=True,
            timeout=30,
            shell=False,
        )
        if latest.returncode != 0:
            return None
        available_version = str(latest.stdout or "").strip().strip('"')
        if not re.fullmatch(r"\d+\.\d+\.\d+", available_version):
            return None

        changed = False
        for section in ("dependencies", "devDependencies", "optionalDependencies", "peerDependencies"):
            dependencies = manifest.get(section, {})
            if str(dependencies.get(package_name, "")).strip() == requested_version:
                dependencies[package_name] = available_version
                changed = True
        if not changed:
            return None

        manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
        return f"Replaced unavailable {package_name}@{requested_version} with {available_version}."
    except (OSError, ValueError, subprocess.SubprocessError):
        return None


def build_frontends(files: list[dict], timeout: int = 240) -> tuple[list[str], list[str]]:
    """Install/build each generated frontend in isolation.

    Returns (errors, logs). This is a quality gate, not a deployment step.
    """
    errors: list[str] = []
    logs: list[str] = []
    root = Path(tempfile.mkdtemp(prefix="smartdevagents_build_"))
    try:
        write_project(files, str(root))
        repaired_configs = _normalize_json_configs(root)
        if repaired_configs:
            logs.append("Normalized temporary JSON configs: " + ", ".join(repaired_configs))
        frontends = _find_frontend_packages(root)
        if not frontends:
            return [], ["No runnable frontend package detected; build gate skipped."]

        npm = "npm.cmd" if os.name == "nt" else "npm"
        for frontend in frontends:
            package = json.loads((frontend / "package.json").read_text(encoding="utf-8"))
            scripts = package.get("scripts", {})
            if not scripts.get("build"):
                logs.append(f"{frontend.relative_to(root)}: no build script; preview startup will validate it later.")
                continue
            install_cmd = [npm, "install", "--no-audit", "--no-fund", "--prefer-offline"]
            install = None
            for attempt in range(2):
                try:
                    install = subprocess.run(install_cmd, cwd=frontend, capture_output=True, text=True, timeout=timeout, shell=False)
                except (FileNotFoundError, subprocess.TimeoutExpired) as exc:
                    errors.append(f"{frontend.relative_to(root)} dependency setup failed: {exc}")
                    break
                output = f"{install.stdout or ''}\n{install.stderr or ''}"
                logs.append(f"{frontend.relative_to(root)} npm install (attempt {attempt + 1}):\n{output[-1500:]}")
                if install.returncode == 0:
                    break
                if attempt == 0:
                    repair = _repair_missing_npm_version(frontend, output, npm)
                    if repair:
                        logs.append(f"{frontend.relative_to(root)}: {repair}")
                        continue
                break
            if install is None:
                continue
            if install.returncode != 0:
                errors.append(f"{frontend.relative_to(root)} npm install failed:\n{(install.stderr or install.stdout)[-5000:]}")
                continue
            try:
                build = subprocess.run([npm, "run", "build"], cwd=frontend, capture_output=True, text=True, timeout=timeout, shell=False)
            except (FileNotFoundError, subprocess.TimeoutExpired) as exc:
                errors.append(f"{frontend.relative_to(root)} build failed: {exc}")
                continue
            logs.append(f"{frontend.relative_to(root)} npm run build:\n{(build.stdout or '')[-2000:]}\n{(build.stderr or '')[-3000:]}")
            if build.returncode != 0:
                errors.append(f"{frontend.relative_to(root)} build failed:\n{(build.stderr or build.stdout)[-6000:]}")
    finally:
        shutil.rmtree(root, ignore_errors=True)
    return errors, logs
