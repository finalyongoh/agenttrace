from __future__ import annotations

import math
import posixpath
import re
from collections import defaultdict
from typing import Any

from agenttrace.agents.analysis.symbol_extractor import extract_symbols_tree_sitter

AREA_SEEDS: dict[str, set[str]] = {
    "project-purpose": {"readme", "overview", "purpose", "about"},
    "execution-flow": {"main", "index", "cli", "server", "handler", "command"},
    "architecture-and-modules": {"package", "module", "service", "client", "server", "sdk", "api"},
    "agent-and-llm": {"agent", "tool", "prompt", "model", "mcp", "context", "openai", "langchain"},
    "tools-and-integrations": {"tool", "integration", "client", "api", "sdk", "provider"},
    "state-and-storage": {"state", "store", "storage", "database", "cache", "memory"},
    "configuration-and-deployment": {"docker", "workflow", "env", "deploy", "kubernetes", "config"},
    "examples-and-tests": {"test", "spec", "example", "fixture", "demo"},
}

IDENT_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_]{2,}")
IMPORT_RE = re.compile(
    r"(?:from\s+['\"]([^'\"]+)['\"]|import\s+['\"]([^'\"]+)['\"]|from\s+\S+\s+import\s+([A-Za-z_][A-Za-z0-9_\.]*))"
)

# Reference count tracking for edge weight calculation
from collections import Counter


def extract_symbols(path: str, content: str) -> dict[str, list[str]]:
    tags = extract_symbols_tree_sitter(path, content)
    definitions = sorted({t.symbol_name for t in tags if t.tag_kind == "definition"})
    ref_tags = [t for t in tags if t.tag_kind == "reference"]
    references = sorted({t.symbol_name for t in ref_tags})
    # 중복 포함 참조 리스트 (간선 가중치 참조 횟수 계산용)
    references_with_duplicates = [t.symbol_name for t in ref_tags]
    return {
        "definitions": definitions,
        "references": references,
        "references_raw": references_with_duplicates,
        "imports": sorted(_extract_imports(content)),
        "symbol_tags": [t.model_dump() for t in tags],
    }


def build_repo_map(
    source_files: list[dict[str, Any]],
    file_tree: list[Any] | None = None,
    *,
    mentioned_idents: list[str] | None = None,
    mentioned_fnames: list[str] | None = None,
    chat_file_paths: list[str] | None = None,
) -> dict[str, Any]:
    files: dict[str, dict[str, Any]] = {}
    definitions_by_symbol: dict[str, set[str]] = defaultdict(set)

    for source in source_files:
        path = _source_path(source)
        if not path:
            continue
        symbols = extract_symbols(path, _source_content(source))
        files[path] = {
            "definitions": symbols["definitions"],
            "references": symbols["references"],
            "references_raw": symbols.get("references_raw", symbols["references"]),
            "imports": symbols["imports"],
            "category": _category(path),
        }
        for symbol in symbols["definitions"]:
            definitions_by_symbol[symbol.lower()].add(path)

    mentioned_idents_set = {i.lower() for i in (mentioned_idents or [])}
    mentioned_fnames_set = set(mentioned_fnames or [])
    chat_file_paths_set = set(chat_file_paths or [])

    edges = _build_edges(
        files,
        definitions_by_symbol,
        mentioned_idents=mentioned_idents_set,
        chat_file_paths=chat_file_paths_set,
    )

    personalization = _build_personalization(
        files,
        mentioned_fnames_set,
        mentioned_idents_set,
        chat_file_paths_set,
    )

    area_file_ranks = {
        area_id: _rank_files(files, edges, seeds, personalization=personalization)
        for area_id, seeds in AREA_SEEDS.items()
    }

    avg_file_ranks = _average_file_ranks(area_file_ranks)
    definition_ranks = _rank_definitions(files, edges, avg_file_ranks)

    return {
        "files": files,
        "edges": edges,
        "area_file_ranks": area_file_ranks,
        "definition_ranks": {
            f"{path}::{symbol}": score
            for (path, symbol), score in sorted(
                definition_ranks.items(), key=lambda x: -x[1]
            )
        },
    }


def _source_path(source: dict[str, Any]) -> str:
    return str(source.get("path") or source.get("file_path") or "")


def _source_content(source: dict[str, Any]) -> str:
    return str(source.get("content") or source.get("text") or "")


def _is_named_identifier(symbol: str) -> bool:
    """snake_case, kebab-case, camelCase, PascalCase 중 하나且 len>=8. §8.2."""
    has_case = any(c.isupper() for c in symbol) and any(c.islower() for c in symbol)
    has_sep = "_" in symbol or "-" in symbol
    return has_case or has_sep


def _edge_weight(
    symbol: str,
    reference_count: int,
    *,
    mentioned_idents: set[str],
    chat_file_paths: set[str],
    source_path: str,
    definitions_by_symbol: dict[str, set[str]],
) -> float:
    """algorithm.md §8: 간선 가중치 6종 휴리스틱."""
    weight = 1.0
    # §8.1 사용자 언급 심볼 ×10
    if symbol.lower() in mentioned_idents:
        weight *= 10.0
    # §8.2 긴 의미있는 식별자 ×10
    if len(symbol) >= 8 and _is_named_identifier(symbol):
        weight *= 10.0
    # §8.3 비공개 식별자 ×0.1
    if symbol.startswith("_"):
        weight *= 0.1
    # §8.4 5개 초과 파일 정의 ×0.1
    if len(definitions_by_symbol.get(symbol.lower(), set())) > 5:
        weight *= 0.1
    # §8.5 현재 대화 파일 참조 ×50
    if source_path in chat_file_paths:
        weight *= 50.0
    # §8.6 sqrt(참조 횟수)
    weight *= math.sqrt(reference_count)
    return weight


def _build_edges(
    files: dict[str, dict[str, Any]],
    definitions_by_symbol: dict[str, set[str]],
    *,
    mentioned_idents: set[str] | None = None,
    chat_file_paths: set[str] | None = None,
) -> dict[str, dict[str, float]]:
    edges: dict[str, dict[str, float]] = {path: {} for path in files}
    available_paths = set(files)
    mentioned_idents = mentioned_idents or set()
    chat_file_paths = chat_file_paths or set()

    for source_path, data in files.items():
        # Count references per symbol (중복 포함 raw 리스트 사용)
        ref_counts: Counter[str] = Counter(data.get("references_raw", data["references"]))
        for reference in data["references"]:
            for target_path in definitions_by_symbol.get(reference.lower(), set()):
                if target_path == source_path:
                    continue
                weight = _edge_weight(
                    reference,
                    ref_counts[reference],
                    mentioned_idents=mentioned_idents,
                    chat_file_paths=chat_file_paths,
                    source_path=source_path,
                    definitions_by_symbol=definitions_by_symbol,
                )
                edges[source_path][target_path] = (
                    edges[source_path].get(target_path, 0.0) + weight
                )
        for import_target in data.get("imports", []):
            target_path = _resolve_import_path(source_path, import_target, available_paths)
            if target_path and target_path != source_path:
                edges[source_path][target_path] = edges[source_path].get(target_path, 0.0) + 1.0

    # §7.4: 참조가 없는 정의에 self-edge (weight=0.1)
    for path in files:
        if not edges[path]:
            edges[path][path] = edges[path].get(path, 0.0) + 0.1

    return edges


def _extract_imports(content: str) -> set[str]:
    imports: set[str] = set()
    for match in IMPORT_RE.findall(content):
        target = next((part for part in match if part), "")
        if target:
            imports.add(target)
    return imports


def _resolve_import_path(source_path: str, import_target: str, available_paths: set[str]) -> str | None:
    if not import_target.startswith("."):
        return None
    source_dir = posixpath.dirname(source_path)
    base = posixpath.normpath(posixpath.join(source_dir, import_target))
    candidates = [
        base,
        f"{base}.ts",
        f"{base}.tsx",
        f"{base}.js",
        f"{base}.jsx",
        f"{base}.py",
        posixpath.join(base, "index.ts"),
        posixpath.join(base, "index.tsx"),
        posixpath.join(base, "index.js"),
        posixpath.join(base, "index.jsx"),
        posixpath.join(base, "__init__.py"),
    ]
    for candidate in candidates:
        if candidate in available_paths:
            return candidate
    return None


def _category(path: str) -> str:
    lower = path.lower()
    if lower.endswith((".md", ".mdx")):
        return "docs"
    if "test" in lower or "spec" in lower:
        return "test"
    if any(token in lower for token in ("docker", "workflow", "kubernetes", ".env", "config")):
        return "critical_config"
    return "source"


def _build_personalization(
    files: dict[str, dict[str, Any]],
    mentioned_fnames: set[str],
    mentioned_idents: set[str],
    chat_file_paths: set[str],
) -> dict[str, float]:
    """algorithm.md §9: Personalized PageRank용 personalization vector."""
    N = len(files)
    if N == 0:
        return {}
    base = 100.0 / N
    pvec = {path: 0.0 for path in files}
    for path in files:
        if path in chat_file_paths:
            pvec[path] += base
        if path in mentioned_fnames:
            pvec[path] += base
        # 경로 구성요소가 mentioned_idents와 일치
        path_tokens = set(path.lower().replace("/", "_").replace("-", "_").split("_"))
        if path_tokens & mentioned_idents:
            pvec[path] += base
    return pvec


def _rank_files(
    files: dict[str, dict[str, Any]],
    edges: dict[str, dict[str, float]],
    seeds: set[str],
    *,
    personalization: dict[str, float] | None = None,
) -> dict[str, float]:
    """Personalized PageRank. algorithm.md §9."""
    if not files:
        return {}
    N = len(files)

    # §9.2: personalization vector
    if personalization and any(personalization.values()):
        pvec = {path: personalization.get(path, 0.0) for path in files}
    else:
        # fallback: seed score 기반
        pvec = {path: _seed_score(path, data, seeds) for path, data in files.items()}

    pvec_total = math.fsum(pvec.values())
    if pvec_total <= 0:
        pvec = {path: 1.0 / N for path in files}
    else:
        pvec = {path: v / pvec_total for path, v in pvec.items()}

    # 초기 rank = personalization
    ranks = dict(pvec)

    # PageRank 반복 (personalization을 teleport에 사용)
    for _ in range(8):
        next_ranks = {path: 0.15 * pvec.get(path, 0.0) for path in files}
        for source_path, targets in edges.items():
            total = math.fsum(targets.values())
            if total <= 0:
                continue
            for target_path, weight in targets.items():
                next_ranks[target_path] = (
                    next_ranks.get(target_path, 0.0)
                    + 0.85 * ranks.get(source_path, 0.0) * (weight / total)
                )
        ranks = _normalize(next_ranks)
    return ranks


def _rank_definitions(
    files: dict[str, dict[str, Any]],
    edges: dict[str, dict[str, float]],
    file_ranks: dict[str, float],
) -> dict[tuple[str, str], float]:
    """파일 PageRank를 정의 단위 점수로 분해. algorithm.md §10."""
    definition_scores: dict[tuple[str, str], float] = defaultdict(float)
    for source_path, targets in edges.items():
        total_outgoing = math.fsum(targets.values())
        if total_outgoing <= 0:
            continue
        source_pr = file_ranks.get(source_path, 0.0)
        source_refs_lower = {r.lower() for r in files.get(source_path, {}).get("references", [])}
        for target_path, weight in targets.items():
            for symbol in files.get(target_path, {}).get("definitions", []):
                if symbol.lower() in source_refs_lower:
                    contribution = source_pr * weight / total_outgoing
                    definition_scores[(target_path, symbol)] += contribution
    return dict(definition_scores)


def _average_file_ranks(area_file_ranks: dict[str, dict[str, float]]) -> dict[str, float]:
    """모든 영역의 file_ranks를 평균내어 definition ranking의 기반으로 사용."""
    if not area_file_ranks:
        return {}
    all_paths: set[str] = set()
    for ranks in area_file_ranks.values():
        all_paths.update(ranks.keys())
    avg = {}
    for path in all_paths:
        scores = [ranks.get(path, 0.0) for ranks in area_file_ranks.values()]
        avg[path] = math.fsum(scores) / len(scores) if scores else 0.0
    return avg


def _seed_score(path: str, data: dict[str, Any], seeds: set[str]) -> float:
    haystack = " ".join([
        path,
        data.get("category", ""),
        *data.get("definitions", []),
        *data.get("references", []),
    ]).lower()
    return float(sum(1 for seed in seeds if seed in haystack))


def _normalize(scores: dict[str, float]) -> dict[str, float]:
    total = math.fsum(scores.values())
    if total <= 0:
        return {key: 0.0 for key in scores}
    return {key: value / total for key, value in scores.items()}
