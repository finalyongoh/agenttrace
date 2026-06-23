# AgentTrace Project Routing

## Context Handling

- Use `context-mode` for repo-wide search, analysis, counting, filtering, parsing, and summarizing.
- Prefer `ctx_batch_execute` for gathering multiple related command outputs.
- Prefer `ctx_execute` for derived answers from files or command output.
- Do not dump large raw files or command output into chat when a filtered answer is enough.

## Reference Artifacts

- Reference project artifacts from `artifacts/current` in the repository `finalyongoh/docs`.
- Use the local clone at [docs/reference](file:///Users/wolyong/workspace/AgentHub/agenttrace/docs/reference) to inspect reference artifact documents. Do not rely on old copies.
- Always run `rtk git -C docs/reference pull` at the start of any new work session to ensure the local documents are up-to-date.
- Treat artifact documents in `docs/reference/artifacts/current` as read-only reference material.

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

## Package Management (uv)

- This project uses `uv` exclusively for package management. Do not use `pip install` directly.
- Python version: `>=3.12,<3.13`
- Lock file: `uv.lock` (committed to version control)

### Setup

```bash
# 환경 초기화 (최초 또는 lock 변경 후)
uv sync --extra dev
```

### Adding / Removing Packages

```bash
# 런타임 의존성 추가
uv add <package>

# dev 의존성 추가
uv add --optional dev <package>

# 패키지 제거
uv remove <package>
```

### Running Tests

```bash
# 전체 테스트
rtk .venv/bin/pytest

# 특정 파일만
rtk .venv/bin/pytest tests/path/to/test_file.py -x -q
```

### Running the API Server

```bash
rtk .venv/bin/agenttrace-api
```

### Notes

- `uv.lock` is the single source of truth for installed packages.
- After pulling changes, always run `uv sync --extra dev` to stay in sync.
- The venv is located at `.venv/` in the project root.

## Environment Setup

`.env` 파일을 프로젝트 루트에 생성 (`.env.example` 참고):

```bash
cp .env.example .env
# 이후 .env에 실제 키 값 입력
```

주요 환경변수:

| 변수 | 설명 | 기본값 |
|---|---|---|
| `OPENAI_API_KEY` | OpenAI API 키 | - |
| `OPENAI_API_BASE` | API 엔드포인트 (커스텀 시) | OpenAI 공식 |
| `AGENTTRACE_ANALYSIS_MODEL` | 분석 LLM 모델 | `gpt-4o-mini` |
| `AGENTTRACE_SUMMARY_MODEL` | 요약 LLM 모델 | `gpt-4o-mini` |
| `AGENTTRACE_REPO_INGEST_BASE_URL` | gitingest 주소 (로컬 시 변경) | `https://gitingest.com` |
| `AGENTTRACE_REPO_INGEST_HOST_HEADER` | gitingest Host 헤더 오버라이드 | - |
| `AGENTTRACE_EXTERNAL_INGEST_ENABLED` | 외부 gitingest 사용 여부 | `false` |
| `DATABASE_URL` | PostgreSQL 연결 문자열 | `postgresql://agenthub_user:agenthub_password@localhost:5432/agenthub` |
| `LANGSMITH_TRACING` | LangSmith 트레이싱 활성화 | `true` |
| `LANGSMITH_API_KEY` | LangSmith API 키 | - |

## Running the Project

### API 서버

```bash
# 방법 1: entrypoint 사용 (권장)
rtk .venv/bin/agenttrace-api

# 방법 2: Makefile 사용
make dev-api

# 방법 3: 직접 uvicorn 실행
.venv/bin/python -m uvicorn agenttrace.app.main:app --app-dir src --host 127.0.0.1 --port 8000
```

기본 주소: `http://127.0.0.1:8000`

### Analysis CLI (단독 실행)

```bash
rtk .venv/bin/python -m agenttrace.agents.analysis.cli data/sample_repo.json --out out/analysis.json
```

### Summary CLI

```bash
rtk .venv/bin/agenttrace-summary
```

### Worker

```bash
rtk .venv/bin/agenttrace-worker
```

### LangGraph Dev Server

`langgraph.json` 기반으로 LangGraph Studio와 연동 가능:

```bash
# langgraph CLI 설치 후
langgraph dev
```

그래프 진입점: `src/agenttrace/agents/analysis/graph.py:graph`

## Testing Guide

```bash
# 전체 테스트 (완료 기준)
rtk .venv/bin/pytest

# 빠른 실패 우선 실행
rtk .venv/bin/pytest -x -q

# 특정 도메인만
rtk .venv/bin/pytest tests/test_analysis_v2_nodes.py -x -q   # analysis nodes
rtk .venv/bin/pytest tests/test_api_analysis.py -x -q        # API 레이어
rtk .venv/bin/pytest tests/test_summary_service.py -x -q     # summary 서비스

# 커버리지 확인 (pytest-cov 설치 시)
rtk .venv/bin/pytest --cov=src/agenttrace --cov-report=term-missing
```

> 테스트는 실제 DB/LLM 호출 없이 mock 기반으로 동작.
> `tests/fixtures/` 아래 샘플 데이터 사용.

