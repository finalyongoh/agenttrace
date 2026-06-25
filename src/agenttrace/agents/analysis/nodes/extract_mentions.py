from __future__ import annotations

import re
import time

from agenttrace.agents.analysis.state import AnalysisState
from agenttrace.logging_config import get_logger

logger = get_logger(__name__)

IDENT_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_]{2,}")
PATH_RE = re.compile(r"[\w\-./]+\.\w{1,5}")


def extract_mentions(state: AnalysisState) -> AnalysisState:
    """analysis_request에서 mentioned_idents/fnames 추출.

    algorithm.md §4.3, §4.4.
    """
    _t = time.perf_counter()
    run_id = state.get("run_id", "-")
    log = logger.bind(node="extract_mentions", run_id=run_id)
    log.info("시작")

    request = state.get("analysis_request", {}) or {}
    user_message = request.get("user_message", "") or state.get("readme", "")

    mentioned_idents = set(IDENT_RE.findall(user_message))
    mentioned_fnames = set(PATH_RE.findall(user_message))

    # file_tree에 존재하는 파일명만 필터
    tree_paths = {item.get("path", "") if isinstance(item, dict) else str(item) for item in state.get("file_tree", [])}
    mentioned_fnames &= tree_paths

    log.info(
        "완료",
        idents=len(mentioned_idents),
        fnames=len(mentioned_fnames),
        duration_ms=int((time.perf_counter() - _t) * 1000),
    )
    return {
        "mentioned_idents": sorted(mentioned_idents),
        "mentioned_fnames": sorted(mentioned_fnames),
    }
