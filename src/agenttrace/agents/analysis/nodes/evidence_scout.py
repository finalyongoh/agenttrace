from __future__ import annotations

import re
import time

from agenttrace.agents.analysis.state import AnalysisState
from agenttrace.logging_config import get_logger

logger = get_logger(__name__)

MAX_SELECTED_CHUNKS = 15


def _current_task(state: AnalysisState) -> dict | None:
    current_task_id = state.get("current_task_id")
    for task in state.get("analysis_plan", {}).get("tasks", []):
        if task.get("task_id") == current_task_id:
            return task
    return None


def _claim_texts(state: AnalysisState, task: dict) -> list[str]:
    wanted = set(task.get("claims", []))
    return [
        claim.get("claim_text", "")
        for claim in state.get("claims", [])
        if claim.get("claim_id") in wanted
    ]


def _tokens(text: str) -> set[str]:
    return {token.lower() for token in re.findall(r"[A-Za-z_][A-Za-z0-9_]{2,}", text)}


def _query_tokens(state: AnalysisState, task: dict) -> set[str]:
    query_tokens = set()
    for text in _claim_texts(state, task):
        query_tokens.update(_tokens(text))
    for query in task.get("queries", []):
        query_tokens.update(_tokens(str(query)))
    return query_tokens


def _repo_map_score_inputs(state: AnalysisState, task: dict) -> tuple[dict[str, float], dict[str, dict]]:
    repo_map = state.get("repo_map", {}) or {}
    area_id = task.get("area_id") or ""
    area_ranks = repo_map.get("area_file_ranks", {}).get(area_id, {}) or {}
    files = repo_map.get("files", {}) or {}

    lower_ranks = {path.lower(): float(score) for path, score in area_ranks.items()}
    lower_files = {path.lower(): data for path, data in files.items()}
    return lower_ranks, lower_files


def _chunk_score(
    chunk: dict,
    *,
    query_tokens: set[str],
    target_paths: set[str],
    file_ranks: dict[str, float],
    repo_files: dict[str, dict],
) -> float:
    path = chunk.get("file_path", "")
    lower_path = path.lower()
    repo_file = repo_files.get(lower_path, {})
    symbol_tokens = _tokens(
        " ".join([
            *repo_file.get("definitions", []),
            *repo_file.get("references", []),
        ])
    )
    chunk_tokens = _tokens(
        " ".join([
            path,
            str(chunk.get("content", "")),
            str(chunk.get("content_hash", "")),
        ])
    )

    score = 0.0
    score += 3.0 * file_ranks.get(lower_path, 0.0)
    if query_tokens:
        score += 2.0 * len(query_tokens & chunk_tokens)
        score += 1.5 * len(query_tokens & symbol_tokens)
    if lower_path in target_paths:
        score += 1.0
    if repo_file.get("category") == "critical_config":
        score += 1.0
    return score


def evidence_scout(state: AnalysisState) -> AnalysisState:
    _t = time.perf_counter()
    run_id = state.get("run_id", "-")
    task_id = state.get("current_task_id", "-")
    log = logger.bind(node="evidence_scout", run_id=run_id, task_id=task_id)
    log.info("시작")
    task = _current_task(state)

    if not task:
        log.warning("현재 태스크 없음 — analysis_plan이 올바르게 생성됐는지 확인하세요",
                    duration_ms=int((time.perf_counter() - _t) * 1000))
        return {"selected_chunks": [], "search_attempt": {}}

    chunk_index = state.get("chunk_index", {})
    target_paths = {path.lower() for path in task.get("target_paths", [])}
    query_tokens = _query_tokens(state, task)
    chunks_by_id = chunk_index.get("chunks_by_id", {})
    file_ranks, repo_files = _repo_map_score_inputs(state, task)

    scored_chunks = []
    for cid, chunk in chunks_by_id.items():
        score = _chunk_score(
            chunk,
            query_tokens=query_tokens,
            target_paths=target_paths,
            file_ranks=file_ranks,
            repo_files=repo_files,
        )
        if score > 0:
            scored_chunks.append((score, cid, chunk))

    if scored_chunks:
        scored_chunks.sort(key=lambda item: (-item[0], item[1]))
        selected = scored_chunks[:MAX_SELECTED_CHUNKS]
        selected_ids = [cid for _, cid, _ in selected]
        selected_chunks = [chunk for _, _, chunk in selected]
    else:
        # Filter chunks that belong to the target paths
        selected_chunks = []
        selected_ids = []
        for cid, chunk in chunks_by_id.items():
            if chunk.get("file_path", "").lower() in target_paths:
                selected_chunks.append(chunk)
                selected_ids.append(cid)
    
        # Fallback 1: if no chunks matched the target paths, select chunks that match query tokens
        if not selected_chunks:
            for cid, chunk in chunks_by_id.items():
                chunk_tokens = _tokens(f"{chunk.get('file_path', '')} {chunk.get('content_hash', '')}")
                if query_tokens & chunk_tokens:
                    selected_chunks.append(chunk)
                    selected_ids.append(cid)

        # Fallback 2: if still empty, select first chunks to prevent empty analysis
        if not selected_chunks:
            first_keys = list(chunks_by_id.keys())[:MAX_SELECTED_CHUNKS]
            selected_chunks = [chunks_by_id[k] for k in first_keys]
            selected_ids = first_keys
        else:
            selected_chunks = selected_chunks[:MAX_SELECTED_CHUNKS]
            selected_ids = selected_ids[:MAX_SELECTED_CHUNKS]

    attempt = {
        "attempt": 1,
        "queries": sorted(query_tokens)[:20],
        "candidate_chunk_ids": list(chunks_by_id.keys()),
        "selected_chunk_ids": selected_ids,
        "excluded_chunk_ids": [cid for cid in chunks_by_id if cid not in selected_ids],
        "exclusion_reasons": {},
    }

    log.info("완료", selected_chunks=len(selected_chunks), duration_ms=int((time.perf_counter() - _t) * 1000))
    return {
        "selected_chunks": selected_chunks,
        "search_attempt": attempt,
    }

