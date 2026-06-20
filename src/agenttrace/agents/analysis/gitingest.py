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
    response = httpx.get(url, timeout=30.0)
    response.raise_for_status()
    return response.text
