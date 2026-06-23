# AgentTrace Project Routing

## Context Handling

- Use `context-mode` for repo-wide search, analysis, counting, filtering, parsing, and summarizing.
- Prefer `ctx_batch_execute` for gathering multiple related command outputs.
- Prefer `ctx_execute` for derived answers from files or command output.
- Do not dump large raw files or command output into chat when a filtered answer is enough.

## Reference Artifacts

- Reference project artifacts from `artifacts/current` in the GitHub repository `finalyongoh/docs`.
- Use GitHub MCP to inspect artifact documents from `finalyongoh/docs`; do not rely on local `docs/artifacts/` copies as the source of truth.
- Treat artifact documents in `finalyongoh/docs:artifacts/current` as read-only reference material unless the user explicitly asks to update that repository.

## GitHub MCP

- Use GitHub MCP for repository, issue, pull request, and review context.
- Default repository for this workspace: `YonghoBae/agenttrace`.
- Use GitHub MCP instead of ad hoc shell/API calls when inspecting PRs, issues, comments, or GitHub-hosted review data.

## LangChain and LangGraph Docs MCP

- Use `mcp__langchain_docs` before answering or changing code that depends on current LangChain, LangGraph, or LangSmith APIs.
- Prefer Python docs for this repo unless the code path is clearly JavaScript-specific.
- For broad questions, start with `search_docs_by_lang_chain`.
- For exact API details or examples, use `query_docs_filesystem_docs_by_lang_chain` on the returned `.mdx` path.

## Development Workflow

- Add or update tests before changing behavior.
- Run focused tests first, then full `pytest` before claiming completion.
- Treat LLM output as untrusted unless the code explicitly constrains or re-derives fields from deterministic inputs.

## RTK (Rust Token Killer) Command Proxy

- Always prefix terminal commands with `rtk` (e.g., `rtk git status`, `rtk pytest`, `rtk grep`, `rtk find`) to minimize token consumption by 60-90%.
- Use `rtk gain` to view token savings stats.
