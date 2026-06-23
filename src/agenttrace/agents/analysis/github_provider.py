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
    if "dockerfile" in lower.split("/")[-1]:
        return True
    return any(lower.endswith(ext) for ext in SOURCE_EXTENSIONS)


# 항상 포함을 보장할 중요 설정 파일 파터는 이름/경로 기준
# 알고리듬 문서 §12 (중요 설정 파일 보호) 참조
_CRITICAL_CONFIG_NAMES: frozenset[str] = frozenset({
    # 패키지/빌드 매니페스트
    "pyproject.toml", "requirements.txt", "setup.py", "setup.cfg",
    "package.json", "package-lock.json", "yarn.lock", "pnpm-lock.yaml",
    "go.mod", "go.sum", "cargo.toml", "cargo.lock",
    "pom.xml", "build.gradle", "build.gradle.kts", "gemfile",
    # 컨테이너/배포
    "dockerfile", "docker-compose.yml", "docker-compose.yaml",
    "serverless.yml", "serverless.yaml",
    # API/DB 스키마
    "openapi.yaml", "openapi.yml", "swagger.yaml", "swagger.yml",
    "schema.sql",
    # 프로젝트 설정
    "tsconfig.json", "jest.config.js", "jest.config.ts",
    "pytest.ini", "tox.ini", "mypy.ini", ".env.example",
    "makefile",
})


def _is_critical_config(path: str) -> bool:
    """Always-include 파일 보호 목록에 해당하는지 확인한다.

    다음 파일은 MAX_FILES 제한과 무관하게 항상 포함을 보장한다.
    - 패키지/빌드 매니페스트
    - Dockerfile 계열
    - CI/CD (.github/workflows 하위 yml/yaml)
    - API 스키마 및 DB DDL
    - 주요 툴체인 설정
    """
    lower = path.lower()
    filename = lower.split("/")[-1]

    # 파일명 일치
    if filename in _CRITICAL_CONFIG_NAMES:
        return True

    # Dockerfile 계열 (접두어 포함: Dockerfile.dev 등)
    if "dockerfile" in filename:
        return True

    # CI/CD: .github/workflows 하위의 yml/yaml
    if ".github/workflows/" in lower and (lower.endswith(".yml") or lower.endswith(".yaml")):
        return True

    return False


def _select_blobs(blobs: list[dict]) -> list[dict]:
    """MAX_FILES 제한 안에서 파일을 선별한다.

    중요 설정 파일은 항상 포함을 보장한다.
    나머지 슬롯은 입력 순서(트리 API 반환 순서)를 유지한 대로 체운다.
    """
    if len(blobs) <= MAX_FILES:
        return blobs

    guaranteed = [b for b in blobs if _is_critical_config(b["path"])]
    rest = [b for b in blobs if not _is_critical_config(b["path"])]

    remaining_slots = MAX_FILES - len(guaranteed)
    return guaranteed + rest[:max(remaining_slots, 0)]


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

        # 2. 소스 파일 필터링 및 중요 파일 보유 선별
        all_blobs = [
            item for item in data.get("tree", [])
            if item["type"] == "blob"
            and _is_source_file(item["path"], item.get("size", 0))
        ]
        blobs = _select_blobs(all_blobs)

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
