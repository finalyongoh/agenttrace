# AgentTrace Project Routing

## Context Handling

- Use `context-mode` for repo-wide search, analysis, counting, filtering, parsing, and summarizing.
- Prefer `ctx_batch_execute` for gathering multiple related command outputs.
- Prefer `ctx_execute` for derived answers from files or command output.
- Do not dump large raw files or command output into chat when a filtered answer is enough.

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
