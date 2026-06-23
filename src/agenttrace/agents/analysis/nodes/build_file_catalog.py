"""build_file_catalog 노드.

collect_inputs → content_preprocessor 사이에 위치하며 전체 파일 트리를
카테고리별로 분류한 카탈로그를 State에 추가한다.

이후 analysis_planner가 file_catalog와 critical_config_paths를 참조해
보다 정확한 target_paths를 생성할 수 있도록 한다.
"""
from __future__ import annotations

import time

from agenttrace.agents.analysis.github_provider import _is_critical_config
from agenttrace.agents.analysis.state import AnalysisState
from agenttrace.logging_config import get_logger

logger = get_logger(__name__)

# 테스트/스펙 파일 판별 패턴
_TEST_PATH_SEGMENTS = {"test", "tests", "spec", "specs", "__tests__"}
_TEST_SUFFIXES = ("_test.go", "_test.py", "_spec.rb", ".test.ts", ".spec.ts",
                  ".test.js", ".spec.js", ".test.tsx", ".spec.tsx")

# 문서 확장자
_DOC_EXTENSIONS = {".md", ".mdx", ".rst", ".txt"}


def _classify_file(path: str) -> str:
    """파일 경로를 카테고리 문자열로 분류한다.

    반환값:
        "critical_config" | "source" | "test" | "docs" | "other"
    """
    lower = path.lower()
    parts = lower.split("/")
    filename = parts[-1]
    _, _, ext = filename.rpartition(".")
    ext = "." + ext if ext else ""

    # 1. 중요 설정 파일 (화이트리스트 우선)
    if _is_critical_config(path):
        return "critical_config"

    # 2. 문서
    if ext in _DOC_EXTENSIONS:
        return "docs"

    # 3. 테스트
    if any(seg in _TEST_PATH_SEGMENTS for seg in parts[:-1]):
        return "test"
    if any(filename.endswith(sfx) for sfx in _TEST_SUFFIXES):
        return "test"

    # 4. 소스 — 소스 확장자 보유 파일은 전부 source
    _SOURCE_EXTS = {
        ".py", ".ts", ".tsx", ".js", ".jsx", ".go", ".java", ".kt",
        ".rs", ".rb", ".cpp", ".c", ".h", ".cs", ".swift", ".scala",
        ".clj", ".ex", ".exs", ".php", ".lua", ".r",
    }
    if ext in _SOURCE_EXTS:
        return "source"

    return "other"


def build_file_catalog(state: AnalysisState) -> AnalysisState:
    """전체 file_tree를 분류해 file_catalog와 critical_config_paths를 생성한다.

    State에 추가하는 키:
        file_catalog: list[dict] — {path, size, ext, category} 목록
        critical_config_paths: list[str] — 항상 포함 보장 파일 경로 목록
    """
    _t = time.perf_counter()
    run_id = state.get("run_id", "-")
    log = logger.bind(node="build_file_catalog", run_id=run_id)
    log.info("시작")

    raw_tree = state.get("file_tree", []) or []

    catalog: list[dict] = []
    critical_paths: list[str] = []

    for item in raw_tree:
        if isinstance(item, str):
            path = item
            size = 0
        elif isinstance(item, dict):
            path = item.get("path", "")
            size = item.get("size", 0) or 0
        else:
            continue

        if not path:
            continue

        filename = path.split("/")[-1]
        _, _, ext_part = filename.rpartition(".")
        ext = ("." + ext_part) if ext_part else ""

        category = _classify_file(path)
        entry = {
            "path": path,
            "size": size,
            "ext": ext,
            "category": category,
        }
        catalog.append(entry)

        if category == "critical_config":
            critical_paths.append(path)

    log.info(
        "완료",
        total=len(catalog),
        critical_configs=len(critical_paths),
        duration_ms=int((time.perf_counter() - _t) * 1000),
    )
    return {
        "file_catalog": catalog,
        "critical_config_paths": critical_paths,
    }
