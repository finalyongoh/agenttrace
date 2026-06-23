# Developer Guide (Environment, Running, & Testing)

이 문서는 AgentTrace의 개발 환경 구성, 실행 방법 및 테스트 작성을 돕는 안내서입니다.

---

## 1. 패키지 및 종속성 관리 (uv)

본 프로젝트는 패키지 관리에 `uv`를 독점적으로 사용합니다. `pip install`을 직접적으로 실행하지 마십시오.

* **파이썬 버전**: `>=3.12, <3.13`
* **락 파일**: `uv.lock` (버전 관리 대상)

### 가상환경 설정 및 초기화
```bash
# 최초 환경 설정 및 lock 파일 업데이트 후 동기화
uv sync --extra dev
```

### 종속성 패키지 관리
```bash
# 런타임 종속성 패키지 추가
uv add <package_name>

# 개발용(dev) 종속성 패키지 추가
uv add --optional dev <package_name>

# 종속성 패키지 제거
uv remove <package_name>
```

### 가상환경 경로
* 모든 실행 환경은 프로젝트 루트의 `.venv/` 내에 설정됩니다.

---

## 2. 환경 설정 (Environment Variables)

프로젝트 루트에 `.env` 파일을 생성하여 필요한 값을 입력하십시오. (기본 설정은 `.env.example`을 복사하여 시작합니다)

```bash
cp .env.example .env
```

### 주요 환경변수 정의

| 환경변수명 | 설명 | 기본값 |
|---|---|---|
| `GITHUB_TOKEN` | GitHub API 토큰 (소스 수집용) | - |
| `OPENAI_API_KEY` | OpenAI API 키 | - |
| `OPENAI_API_BASE` | API 엔드포인트 커스텀 주소 | OpenAI 공식 주소 |
| `AGENTTRACE_ANALYSIS_MODEL` | 분석 수행용 LLM 모델 | `gpt-4o-mini` |
| `AGENTTRACE_SUMMARY_MODEL` | 요약 수행용 LLM 모델 | `gpt-4o-mini` |
| `DATABASE_URL` | PostgreSQL 연결 문자열 | `postgresql://agenthub_user:agenthub_password@localhost:5432/agenthub` |
| `LANGSMITH_TRACING` | LangSmith 트레이싱 활성화 여부 | `true` |
| `LANGSMITH_API_KEY` | LangSmith API 키 | - |

---

## 3. 프로젝트 기동 및 실행 (Running the Project)

### API 서버 구동
```bash
# 방법 1: 엔트리포인트 사용 (권장)
rtk .venv/bin/agenttrace-api

# 방법 2: uvicorn 직접 실행
.venv/bin/python -m uvicorn agenttrace.app.main:app --app-dir src --host 127.0.0.1 --port 8000
```
* 기본 주소: `http://127.0.0.1:8000`

### 분석 CLI (단독 실행)
```bash
rtk .venv/bin/python -m agenttrace.agents.analysis.cli data/sample_repo.json --out out/analysis.json
```

### 요약 CLI 실행
```bash
rtk .venv/bin/agenttrace-summary
```

### Worker 데몬 구동
```bash
rtk .venv/bin/agenttrace-worker
```

### LangGraph Dev Server (LangGraph Studio 연동용)
```bash
# langgraph CLI가 전역 또는 가상환경에 설치된 후 실행
langgraph dev
```
* 그래프 진입점: `src/agenttrace/agents/analysis/graph.py:graph`

---

## 4. 테스트 가이드 (Testing Guide)

테스트는 모의 데이터(`tests/fixtures/`)를 활용하여 실제 외부 DB 및 LLM 호출 없이 mock 기반으로 신속하게 동작합니다.

### 테스트 실행 명령어
```bash
# 전체 테스트 실행 (최종 완료 검증 기준)
rtk .venv/bin/pytest

# 빠른 실패 및 요약 모드로 실행 (개발 루프 중 권장)
rtk .venv/bin/pytest -x -q

# 특정 도메인 노드 테스트만 집중 실행
rtk .venv/bin/pytest tests/test_analysis_v2_nodes.py -x -q   # 분석 파이프라인 노드
rtk .venv/bin/pytest tests/test_api_analysis.py -x -q        # API 레이어
rtk .venv/bin/pytest tests/test_summary_service.py -x -q     # summary 서비스

# 테스트 커버리지 확인 (pytest-cov 필요)
rtk .venv/bin/pytest --cov=src/agenttrace --cov-report=term-missing
```
