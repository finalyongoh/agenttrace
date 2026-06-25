from __future__ import annotations

import json
import re


def parse_config_file(path: str, content: str) -> dict:
    """설정 파일 내용을 구조화된 의존 관계로 추출.

    algorithm.md §22.1: 경로만 보호하지 말고 별도 파서로 내용을 추출한다.
    """
    lower = path.lower()
    if lower.endswith("package.json"):
        return _parse_package_json(content)
    if lower.endswith("pyproject.toml"):
        return _parse_pyproject(content)
    if "dockerfile" in lower.split("/")[-1]:
        return _parse_dockerfile(content)
    if ".github/workflows/" in lower and lower.endswith((".yml", ".yaml")):
        return _parse_github_workflow(content)
    return {}


def _parse_package_json(content: str) -> dict:
    try:
        data = json.loads(content)
    except (json.JSONDecodeError, TypeError):
        return {}
    return {
        "type": "package.json",
        "dependencies": list((data.get("dependencies") or {}).keys()),
        "dev_dependencies": list((data.get("devDependencies") or {}).keys()),
        "scripts": list((data.get("scripts") or {}).keys()),
        "entrypoint": data.get("main") or data.get("module") or data.get("exports"),
    }


def _parse_pyproject(content: str) -> dict:
    deps: list[str] = []
    in_deps = False
    for line in content.splitlines():
        stripped = line.strip()
        if stripped.startswith("dependencies") and "=" in stripped:
            in_deps = True
            continue
        if in_deps:
            if stripped.startswith("[") and "dependencies" not in stripped:
                in_deps = False
                continue
            match = re.match(r'["\']([^"\']+)["\']', stripped)
            if match:
                raw_dep = match.group(1)
                # 버전 지정자 제거: "langgraph>=0.6" → "langgraph"
                dep_name = re.split(r"[><=!~\[;]", raw_dep)[0]
                deps.append(dep_name)
    return {
        "type": "pyproject.toml",
        "dependencies": deps,
    }


def _parse_dockerfile(content: str) -> dict:
    base_images = re.findall(r"^FROM\s+(\S+)", content, re.MULTILINE)
    cmds = re.findall(r"^(?:CMD|ENTRYPOINT)\s+(.+)", content, re.MULTILINE)
    return {
        "type": "dockerfile",
        "base_images": base_images,
        "commands": cmds,
    }


def _parse_github_workflow(content: str) -> dict:
    try:
        import yaml
    except ImportError:
        return {"type": "github_workflow", "raw_available": True}
    try:
        data = yaml.safe_load(content) or {}
    except Exception:
        return {"type": "github_workflow", "raw_available": True}
    triggers = data.get(True, data.get("on", "push"))
    if isinstance(triggers, dict):
        trigger_keys = list(triggers.keys())
    elif isinstance(triggers, list):
        trigger_keys = triggers
    else:
        trigger_keys = [str(triggers)]
    jobs = data.get("jobs", {})
    job_names = list(jobs.keys()) if isinstance(jobs, dict) else []
    return {
        "type": "github_workflow",
        "triggers": trigger_keys,
        "jobs": job_names,
    }
