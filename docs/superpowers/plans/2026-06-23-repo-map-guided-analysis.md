# Repo Map Guided Analysis Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add an Aider-inspired repo map node and use it to reduce evidence chunks before LLM verification.

**Architecture:** Build a deterministic structural repo map before claim analysis, then use area-specific file ranks and symbol matches in `evidence_scout`. Keep final evidence references tied to original source chunks.

**Tech Stack:** Python, LangGraph node functions, pytest, existing `AnalysisState` dict patterns, no new runtime dependency in the first version.

---

## File Structure

- Create `src/agenttrace/agents/analysis/repo_map.py`: pure helpers for symbol extraction, reference graph construction, area ranking, and chunk scoring inputs.
- Create `src/agenttrace/agents/analysis/nodes/build_repo_map.py`: LangGraph node wrapper with structured logging.
- Modify `src/agenttrace/agents/analysis/state.py`: add optional repo-map fields to `AnalysisState`.
- Modify `src/agenttrace/agents/analysis/graph.py`: wire `build_repo_map` after `build_file_catalog`.
- Modify `src/agenttrace/agents/analysis/nodes/evidence_scout.py`: score chunks using repo-map ranks, token overlap, symbol matches, and limits.
- Create `tests/test_analysis_repo_map.py`: tests for pure repo-map behavior and node output.
- Modify `tests/test_analysis_v2_nodes.py`: add evidence scout behavior coverage.

## Task 1: Repo Map Pure Helpers

**Files:**
- Create: `src/agenttrace/agents/analysis/repo_map.py`
- Test: `tests/test_analysis_repo_map.py`

- [ ] **Step 1: Write the failing tests**

```python
from agenttrace.agents.analysis.repo_map import build_repo_map


def test_build_repo_map_extracts_symbols_and_ranks_agent_file():
    source_files = [
        {
            "path": "packages/tools-ai-sdk/src/agents/context7.ts",
            "content": "export function createContext7Agent() { return callTool(); }\nfunction callTool() {}\n",
        },
        {
            "path": "packages/web/src/theme.ts",
            "content": "export const colors = { primary: 'blue' };\n",
        },
    ]

    repo_map = build_repo_map(source_files, file_tree=[])

    assert "packages/tools-ai-sdk/src/agents/context7.ts" in repo_map["files"]
    agent_file = repo_map["files"]["packages/tools-ai-sdk/src/agents/context7.ts"]
    assert "createContext7Agent" in agent_file["definitions"]
    assert repo_map["area_file_ranks"]["agent-and-llm"]["packages/tools-ai-sdk/src/agents/context7.ts"] > repo_map["area_file_ranks"]["agent-and-llm"].get("packages/web/src/theme.ts", 0)
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `rtk .venv/bin/pytest tests/test_analysis_repo_map.py::test_build_repo_map_extracts_symbols_and_ranks_agent_file -q`

Expected: FAIL because `agenttrace.agents.analysis.repo_map` does not exist.

- [ ] **Step 3: Implement minimal helper**

Create `repo_map.py` with:

```python
from __future__ import annotations

import math
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
DEF_PATTERNS = [
    re.compile(r"\b(?:export\s+)?(?:async\s+)?function\s+([A-Za-z_][A-Za-z0-9_]*)"),
    re.compile(r"\b(?:export\s+)?class\s+([A-Za-z_][A-Za-z0-9_]*)"),
    re.compile(r"\b(?:export\s+)?const\s+([A-Za-z_][A-Za-z0-9_]*)"),
    re.compile(r"\bdef\s+([A-Za-z_][A-Za-z0-9_]*)"),
    re.compile(r"\bclass\s+([A-Za-z_][A-Za-z0-9_]*)"),
]


def _source_path(source: dict[str, Any]) -> str:
    return str(source.get("path") or source.get("file_path") or "")


def _source_content(source: dict[str, Any]) -> str:
    return str(source.get("content") or source.get("text") or "")


def extract_symbols(path: str, content: str) -> dict[str, list[str]]:
    definitions: set[str] = set()
    for pattern in DEF_PATTERNS:
        definitions.update(pattern.findall(content))
    references = set(IDENT_RE.findall(content)) - definitions
    path_tokens = set(IDENT_RE.findall(path.replace("-", "_").replace("/", "_")))
    references.update(path_tokens)
    return {
        "definitions": sorted(definitions),
        "references": sorted(references),
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
            "category": _category(path),
        }
        for symbol in symbols["definitions"]:
            definitions_by_symbol[symbol.lower()].add(path)

    edges: dict[str, dict[str, float]] = {path: {} for path in files}
    for source_path, data in files.items():
        for ref in data["references"]:
            for target_path in definitions_by_symbol.get(ref.lower(), set()):
                if target_path == source_path:
                    continue
                edges[source_path][target_path] = edges[source_path].get(target_path, 0.0) + 1.0

    area_file_ranks = {
        area_id: _rank_files(files, edges, seeds)
        for area_id, seeds in AREA_SEEDS.items()
    }

    return {
        "files": files,
        "edges": edges,
        "area_file_ranks": area_file_ranks,
    }


def _category(path: str) -> str:
    lower = path.lower()
    if lower.endswith((".md", ".mdx")):
        return "docs"
    if "test" in lower or "spec" in lower:
        return "test"
    if any(token in lower for token in ("docker", "workflow", "kubernetes", ".env", "config")):
        return "critical_config"
    return "source"


def _rank_files(files: dict[str, dict[str, Any]], edges: dict[str, dict[str, float]], seeds: set[str]) -> dict[str, float]:
    if not files:
        return {}
    ranks = {path: _seed_score(path, data, seeds) for path, data in files.items()}
    if not any(ranks.values()):
        ranks = {path: 1.0 for path in files}
    ranks = _normalize(ranks)

    for _ in range(8):
        next_ranks = {path: 0.15 * ranks.get(path, 0.0) for path in files}
        for source, targets in edges.items():
            total = sum(targets.values())
            if total <= 0:
                continue
            for target, weight in targets.items():
                next_ranks[target] = next_ranks.get(target, 0.0) + 0.85 * ranks.get(source, 0.0) * (weight / total)
        ranks = _normalize(next_ranks)
    return ranks


def _seed_score(path: str, data: dict[str, Any], seeds: set[str]) -> float:
    haystack = " ".join([path, data.get("category", ""), *data.get("definitions", []), *data.get("references", [])]).lower()
    return float(sum(1 for seed in seeds if seed in haystack))


def _normalize(scores: dict[str, float]) -> dict[str, float]:
    total = math.fsum(scores.values())
    if total <= 0:
        return {key: 0.0 for key in scores}
    return {key: value / total for key, value in scores.items()}
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `rtk .venv/bin/pytest tests/test_analysis_repo_map.py::test_build_repo_map_extracts_symbols_and_ranks_agent_file -q`

Expected: PASS.

## Task 2: Graph Node Wiring

**Files:**
- Create: `src/agenttrace/agents/analysis/nodes/build_repo_map.py`
- Modify: `src/agenttrace/agents/analysis/state.py`
- Modify: `src/agenttrace/agents/analysis/graph.py`
- Test: `tests/test_analysis_repo_map.py`

- [ ] **Step 1: Write failing node test**

```python
from agenttrace.agents.analysis.nodes.build_repo_map import build_repo_map_node


def test_build_repo_map_node_adds_repo_map_to_state():
    state = {
        "run_id": "run-1",
        "source_files": [
            {"path": "src/agent.ts", "content": "export function createAgent() { return tool(); }"},
        ],
        "file_tree": [{"path": "src/agent.ts"}],
    }

    result = build_repo_map_node(state)

    assert "repo_map" in result
    assert result["repo_map"]["files"]["src/agent.ts"]["definitions"] == ["createAgent"]
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `rtk .venv/bin/pytest tests/test_analysis_repo_map.py::test_build_repo_map_node_adds_repo_map_to_state -q`

Expected: FAIL because node module does not exist.

- [ ] **Step 3: Implement node and wire graph**

Add node wrapper that calls pure `build_repo_map`, logs file count, and returns `{"repo_map": repo_map}`. Add optional `repo_map: dict[str, Any]` to `AnalysisState`. Wire graph edge as `build_file_catalog -> build_repo_map -> claim_analyzer`.

- [ ] **Step 4: Run focused tests**

Run: `rtk .venv/bin/pytest tests/test_analysis_repo_map.py -q`

Expected: PASS.

## Task 3: Repo-Map Guided Evidence Scout

**Files:**
- Modify: `src/agenttrace/agents/analysis/nodes/evidence_scout.py`
- Test: `tests/test_analysis_v2_nodes.py`

- [ ] **Step 1: Write failing ranking test**

```python
from agenttrace.agents.analysis.nodes.evidence_scout import evidence_scout


def test_evidence_scout_prefers_repo_map_ranked_chunks_and_caps_results():
    chunks = {
        f"chunk-{i}": {
            "chunk_id": f"chunk-{i}",
            "file_path": "src/agent.ts" if i == 7 else f"src/other_{i}.ts",
            "content_hash": f"h{i}",
            "line_start": 1,
            "line_end": 2,
        }
        for i in range(25)
    }
    state = {
        "run_id": "run-1",
        "current_task": {
            "task_id": "task-1",
            "area_id": "agent-and-llm",
            "queries": ["agent tool prompt"],
            "target_paths": [],
        },
        "chunk_index": {"chunks_by_id": chunks},
        "repo_map": {
            "files": {
                "src/agent.ts": {"definitions": ["createAgent"], "references": ["tool", "prompt"]},
            },
            "area_file_ranks": {"agent-and-llm": {"src/agent.ts": 1.0}},
        },
    }

    result = evidence_scout(state)

    assert result["selected_chunks"][0]["file_path"] == "src/agent.ts"
    assert len(result["selected_chunks"]) <= 15
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `rtk .venv/bin/pytest tests/test_analysis_v2_nodes.py::test_evidence_scout_prefers_repo_map_ranked_chunks_and_caps_results -q`

Expected: FAIL because current evidence scout does not rank and cap this way.

- [ ] **Step 3: Implement ranking**

Update `evidence_scout` to:

- Build query tokens from current task fields.
- Score every chunk by area file rank, token overlap, symbol match, and target path boost.
- Select positive-score chunks first, sorted descending.
- Fall back to existing behavior when no ranked chunks exist.
- Cap selected chunks to 15.

- [ ] **Step 4: Run focused tests**

Run: `rtk .venv/bin/pytest tests/test_analysis_v2_nodes.py::test_evidence_scout_prefers_repo_map_ranked_chunks_and_caps_results -q`

Expected: PASS.

## Task 4: Verification

**Files:**
- No new files.

- [ ] **Step 1: Run focused repo-map and node tests**

Run: `rtk .venv/bin/pytest tests/test_analysis_repo_map.py tests/test_analysis_v2_nodes.py -q`

Expected: PASS.

- [ ] **Step 2: Run Context7 smoke analysis and inspect chunk counts**

Run: `rtk .venv/bin/python -m agenttrace.agents.analysis.cli data/context7_snapshot.json --out out/context7_analysis_repo_map.json`

Expected:
- `collect_inputs` selects Context7 files.
- `build_repo_map` logs completion.
- `evidence_scout` selected chunk counts are lower than the previous 54 and 50 chunk baseline.
- Final status is `COMPLETED`.

## Self-Review

- Spec coverage: repo map, area-specific ranks, evidence scout capping, final evidence chunk references are covered.
- Placeholder scan: no TBD/TODO placeholders.
- Type consistency: repo map field names are consistent across tasks.
