from __future__ import annotations

import time
from pathlib import Path

from agenttrace.agents.analysis.repo_map import build_repo_map
from agenttrace.agents.analysis.repo_map_renderer import render_repo_map
from agenttrace.agents.analysis.state import AnalysisState
from agenttrace.logging_config import get_logger

logger = get_logger(__name__)


def build_repo_map_node(state: AnalysisState) -> AnalysisState:
    _t = time.perf_counter()
    run_id = state.get("run_id", "-")
    log = logger.bind(node="build_repo_map", run_id=run_id)
    log.info("시작")

    source_files = _source_files_with_content(state)
    repo_map = build_repo_map(
        source_files,
        file_tree=state.get("file_tree", []),
        mentioned_idents=state.get("mentioned_idents", []),
        mentioned_fnames=state.get("mentioned_fnames", []),
        chat_file_paths=state.get("chat_file_paths", []),
    )

    definition_ranks = repo_map.get("definition_ranks", {})
    critical_config_paths = state.get("critical_config_paths", [])
    repo_map_render = render_repo_map(
        definition_ranks=definition_ranks,
        special_files=critical_config_paths,
        max_tokens=4096,
    )

    symbol_tags: list[dict] = []
    for path, data in repo_map.get("files", {}).items():
        for tag in data.get("symbol_tags", []):
            tag_with_path = dict(tag) if isinstance(tag, dict) else {"value": tag}
            tag_with_path["path"] = path
            symbol_tags.append(tag_with_path)

    log.info(
        "완료",
        files=len(repo_map.get("files", {})),
        edges=sum(len(targets) for targets in repo_map.get("edges", {}).values()),
        definition_ranks=len(definition_ranks),
        repo_map_render_tokens=len(repo_map_render) // 4,
        symbol_tags=len(symbol_tags),
        duration_ms=int((time.perf_counter() - _t) * 1000),
    )
    return {
        "repo_map": repo_map,
        "definition_ranks": definition_ranks,
        "repo_map_render": repo_map_render,
        "symbol_tags": symbol_tags,
    }


def _source_files_with_content(state: AnalysisState) -> list[dict]:
    local_repo_dir = state.get("local_repo_dir")
    base_dir = Path(local_repo_dir).resolve() if local_repo_dir else None
    result: list[dict] = []

    for source in state.get("source_files", []):
        source_dict = dict(source)
        if source_dict.get("content") or not base_dir:
            result.append(source_dict)
            continue

        source_path = source_dict.get("path") or source_dict.get("file_path")
        if not source_path:
            result.append(source_dict)
            continue

        file_path = (base_dir / str(source_path)).resolve()
        try:
            if not file_path.is_relative_to(base_dir):
                result.append(source_dict)
                continue
            source_dict["content"] = file_path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            pass
        result.append(source_dict)

    return result
