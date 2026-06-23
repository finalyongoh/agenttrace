"""GitHub API-based source file provider.

Fetches source files directly from GitHub using the REST API,
supporting specific commit SHA and extension filtering.
"""
from __future__ import annotations

import base64
import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from urllib.parse import urlparse

import httpx

from agenttrace.agents.analysis.schemas.input import SourceFile

logger = logging.getLogger(__name__)

# 분석 대상 확장자 whitelist
SOURCE_EXTENSIONS = {
    ".py", ".ts", ".tsx", ".js", ".jsx",
    ".go", ".java", ".kt", ".rs", ".rb",
    ".cpp", ".c", ".h", ".cs", ".swift",
    ".md", ".mdx", ".json", ".yaml", ".yml",
    ".toml", ".env.example", ".dockerfile",
}

# 단일 파일 최대 크기 (bytes) — 500KB 초과 시 skip
MAX_FILE_SIZE = 500_000

# 레포 전체 파일 수 상한
MAX_FILES = 300


def _parse_owner_repo(github_url: str) -> tuple[str, str]:
    """https://github.com/owner/repo → (owner, repo)"""
    parsed = urlparse(github_url)
    path = parsed.path if parsed.scheme else github_url
    parts = [p for p in path.strip("/").split("/") if p]
    if len(parts) < 2:
        raise ValueError(f"Cannot parse owner/repo from: {github_url}")
    return parts[0], parts[1]


def _is_source_file(path: str, size: int) -> bool:
    if size > MAX_FILE_SIZE:
        return False
    lower = path.lower()
    # Dockerfile 계열
    if "dockerfile" in lower.split("/")[-1].lower():
        return True
    return any(lower.endswith(ext) for ext in SOURCE_EXTENSIONS)


def _score_file_path(path: str) -> int:
    lower = path.lower()
    # 1. Core source directory weights
    for source_dir in ["src/", "lib/", "app/", "packages/", "srcs/"]:
        if lower.startswith(source_dir) or f"/{source_dir}" in lower:
            return 100
    
    # 2. Documents and minor metadata penalties
    if lower.endswith(".md") or lower.endswith(".mdx") or "license" in lower or ".github/" in lower:
        return -50
        
    # 3. Environment configuration files penalties
    if any(lower.endswith(ext) for ext in [".json", ".yaml", ".yml", ".toml", ".ini", ".cfg"]):
        return -20
        
    return 0


class GitHubInputProvider:
    """GitHub REST API로 소스파일을 직접 수집하는 Provider."""

    API_BASE = "https://api.github.com"

    def __init__(self, token: str | None = None):
        headers = {
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }
        if token:
            headers["Authorization"] = f"Bearer {token}"
        self._client = httpx.Client(headers=headers, timeout=30.0)

    def load(
        self,
        github_url: str,
        commit_sha: str = "HEAD",
    ) -> list[SourceFile]:
        owner, repo = _parse_owner_repo(github_url)

        # 1. 파일 트리 전체 조회
        tree_url = f"{self.API_BASE}/repos/{owner}/{repo}/git/trees/{commit_sha}?recursive=1"
        resp = self._client.get(tree_url)
        resp.raise_for_status()
        data = resp.json()

        if data.get("truncated"):
            logger.warning("GitHub tree response truncated for %s/%s", owner, repo)

        # 2. Source file filtering and importance sorting
        all_blobs = [
            item for item in data.get("tree", [])
            if item["type"] == "blob"
            and _is_source_file(item["path"], item.get("size", 0))
        ]
        # Sort so that highest score files come first
        all_blobs.sort(key=lambda item: _score_file_path(item["path"]), reverse=True)
        blobs = all_blobs[:MAX_FILES]

        logger.info(
            "GitHub provider: %d source files selected from %s/%s@%s",
            len(blobs), owner, repo, commit_sha,
        )

        # 3. 파일 내용 병렬 fetch
        source_files: list[SourceFile] = []
        with ThreadPoolExecutor(max_workers=10) as executor:
            futures = {
                executor.submit(
                    self._fetch_file, owner, repo, item["path"], commit_sha
                ): item["path"]
                for item in blobs
            }
            for future in as_completed(futures):
                path = futures[future]
                try:
                    sf = future.result()
                    if sf:
                        source_files.append(sf)
                except Exception as exc:
                    logger.debug("Skip %s: %s", path, exc)

        source_files.sort(key=lambda f: f.path)
        return source_files

    def _fetch_file(
        self, owner: str, repo: str, path: str, ref: str
    ) -> SourceFile | None:
        url = f"{self.API_BASE}/repos/{owner}/{repo}/contents/{path}?ref={ref}"
        resp = self._client.get(url)
        if resp.status_code == 404:
            return None
        resp.raise_for_status()
        data = resp.json()

        encoding = data.get("encoding")
        raw_content = data.get("content", "")

        if encoding == "base64":
            try:
                content = base64.b64decode(raw_content).decode("utf-8", errors="replace")
            except Exception:
                return None  # binary 파일 skip
        else:
            content = raw_content

        return SourceFile(path=path, content=content)
