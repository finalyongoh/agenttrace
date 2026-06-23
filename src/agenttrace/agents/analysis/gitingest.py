from __future__ import annotations

import re
from urllib.parse import urlparse

import httpx

from agenttrace.agents.analysis.schemas.input import SourceFile


FILE_RE = re.compile(
    r"^={48}\nFILE: (?P<path>.+?)\n={48}\n(?P<content>.*?)(?=\n={48}\nFILE: |\Z)",
    re.DOTALL | re.MULTILINE,
)


def parse_gitingest_output(raw: str) -> list[SourceFile]:
    files: list[SourceFile] = []
    for match in FILE_RE.finditer(raw):
        path = match.group("path").strip()
        content = match.group("content").strip("\n")
        if path:
            files.append(SourceFile(path=path, content=content))
    return files


def build_gitingest_url(
    github_url: str, base_url: str = "https://gitingest.com"
) -> str:
    parsed = urlparse(github_url)
    repository_path = parsed.path if parsed.scheme else github_url
    return f"{base_url.rstrip('/')}/{repository_path.strip('/')}"


def fetch_gitingest_text(url: str) -> str:
    parsed = urlparse(url)
    path_parts = [p for p in parsed.path.strip("/").split("/") if p]
    if path_parts and path_parts[0] != "api":
        api_path = "/api/" + "/".join(path_parts)
        url = parsed._replace(path=api_path).geturl()

    from agenttrace.config import get_settings
    settings = get_settings()
    headers = {}
    if settings.repo_ingest_host_header:
        headers["Host"] = settings.repo_ingest_host_header

    response = httpx.get(url, headers=headers, timeout=30.0)
    response.raise_for_status()
    try:
        data = response.json()
        if isinstance(data, dict) and "content" in data:
            return data["content"]
    except Exception:
        pass
    return response.text
