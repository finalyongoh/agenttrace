from __future__ import annotations

import math
import posixpath
import re
from collections import defaultdict
from typing import Any

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
DEF_PATTERNS = [
    re.compile(r"\b(?:export\s+)?(?:async\s+)?function\s+([A-Za-z_][A-Za-z0-9_]*)"),
    re.compile(r"\b(?:export\s+)?class\s+([A-Za-z_][A-Za-z0-9_]*)"),
    re.compile(r"\b(?:export\s+)?const\s+([A-Za-z_][A-Za-z0-9_]*)"),
    re.compile(r"\bdef\s+([A-Za-z_][A-Za-z0-9_]*)"),
    re.compile(r"\bclass\s+([A-Za-z_][A-Za-z0-9_]*)"),
]


def extract_symbols(path: str, content: str) -> dict[str, list[str]]:
    definitions: set[str] = set()
    for pattern in DEF_PATTERNS:
        definitions.update(pattern.findall(content))
    references = set(IDENT_RE.findall(content)) - definitions
    references.update(IDENT_RE.findall(path.replace("-", "_").replace("/", "_")))
    return {
        "definitions": sorted(definitions),
        "references": sorted(references),
        "imports": sorted(_extract_imports(content)),
    }


def build_repo_map(source_files: list[dict[str, Any]], file_tree: list[Any] | None = None) -> dict[str, Any]:
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
            "imports": symbols["imports"],
            "category": _category(path),
        }
        for symbol in symbols["definitions"]:
            definitions_by_symbol[symbol.lower()].add(path)

    edges = _build_edges(files, definitions_by_symbol)
    return {
        "files": files,
        "edges": edges,
        "area_file_ranks": {
            area_id: _rank_files(files, edges, seeds)
            for area_id, seeds in AREA_SEEDS.items()
        },
    }


def _source_path(source: dict[str, Any]) -> str:
    return str(source.get("path") or source.get("file_path") or "")


def _source_content(source: dict[str, Any]) -> str:
    return str(source.get("content") or source.get("text") or "")


def _build_edges(
    files: dict[str, dict[str, Any]],
    definitions_by_symbol: dict[str, set[str]],
) -> dict[str, dict[str, float]]:
    edges: dict[str, dict[str, float]] = {path: {} for path in files}
    available_paths = set(files)
    for source_path, data in files.items():
        for reference in data["references"]:
            for target_path in definitions_by_symbol.get(reference.lower(), set()):
                if target_path == source_path:
                    continue
                edges[source_path][target_path] = edges[source_path].get(target_path, 0.0) + 1.0
        for import_target in data.get("imports", []):
            target_path = _resolve_import_path(source_path, import_target, available_paths)
            if target_path and target_path != source_path:
                edges[source_path][target_path] = edges[source_path].get(target_path, 0.0) + 1.0
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


def _rank_files(
    files: dict[str, dict[str, Any]],
    edges: dict[str, dict[str, float]],
    seeds: set[str],
) -> dict[str, float]:
    if not files:
        return {}
    ranks = {
        path: _seed_score(path, data, seeds)
        for path, data in files.items()
    }
    if not any(ranks.values()):
        ranks = {path: 1.0 for path in files}
    ranks = _normalize(ranks)

    for _ in range(8):
        next_ranks = {path: 0.15 * ranks.get(path, 0.0) for path in files}
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
