# Repo Map Guided Analysis Design

## Goal

Speed up real repository analysis and improve evidence selection by adding an Aider-style repository map as a retrieval guide before LLM verification.

## Current Problem

The Context7 run completed, but most time was spent in LLM calls:

- `evidence_evaluator` task 1 took about 183 seconds with 54 selected chunks.
- `evidence_evaluator` task 2 took about 282 seconds with 50 selected chunks.
- `finalize_analysis` took about 192 seconds.

The current `evidence_scout` mostly selects chunks by target paths and fallback matching. It does not rank candidate chunks by repository structure, symbol importance, or area-specific intent. This sends too many chunks into structured LLM verification.

## Proposed Architecture

Add a `build_repo_map` node between `build_file_catalog` and `claim_analyzer`. The node builds a lightweight structural index from source files:

- Symbol definitions by file.
- Symbol references by file.
- File-level dependency edges from references to definition files.
- Area-specific file ranks using deterministic personalized propagation.

Then update `evidence_scout` to use repo-map ranks, claim token overlap, path/category boosts, and symbol matches to select a smaller set of chunks.

The repo map is a navigation and retrieval aid. Final evidence references must still point to source chunks, not to the repo map itself.

## Scope

This first version intentionally avoids a full Tree-sitter dependency. It uses deterministic regex-based symbol extraction for Python, TypeScript, JavaScript, TSX, JSX, Markdown headings, JSON package names, and config files. The interface is designed so a future Tree-sitter implementation can replace the extractor without changing downstream nodes.

## Data Flow

```text
collect_inputs
-> build_file_catalog
-> build_repo_map
-> claim_analyzer
-> analysis_planner
-> select_next_task
-> evidence_scout
-> evidence_evaluator
-> finalize_analysis
-> quality_gate
-> persist_analysis
```

## Ranking

`build_repo_map` computes area-specific file rank for the common analysis areas. Seeds come from area keywords:

- `agent-and-llm`: agent, tool, prompt, model, mcp, context, openai, langchain
- `architecture-and-modules`: package, module, service, client, server, sdk, api
- `configuration-and-deployment`: docker, workflow, env, deploy, kubernetes, config
- `examples-and-tests`: test, spec, example, fixture, demo

`evidence_scout` computes chunk score:

```text
score =
  3.0 * repo_map_file_rank
+ 2.0 * claim_or_task_token_overlap
+ 1.5 * symbol_match
+ 1.0 * critical_config_or_target_path_boost
```

It selects at most 15 chunks per task by default while preserving critical config chunks when relevant.

## Testing

Add node-level tests that verify:

- `build_repo_map` extracts definitions and references from a small fixture repository.
- Area rank prioritizes relevant files for `agent-and-llm`.
- `evidence_scout` prefers repo-map-ranked chunks over unrelated chunks and caps the selected chunk count.
- Existing fallback behavior still returns evidence when repo-map data is missing.

Run focused tests before broad node tests.

## Success Criteria

- Context7 analysis sends far fewer chunks to `evidence_evaluator` for each task.
- Existing analysis graph still completes.
- Final report still has 8 area findings and 11 report sections for Context7.
- Quality gate has no critical errors.
