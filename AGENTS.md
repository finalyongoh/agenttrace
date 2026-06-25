# AgentTrace Project Routing & Guidelines

이 문서는 AgentTrace 프로젝트에서 작업할 때 에이전트(AI)가 반드시 지켜야 할 행동 제약 조건과 규칙을 정의합니다.

---

## 🗺️ Documentation Map (참조 문서 지도)

상세 정보는 아래 전용 문서들을 가상환경 작업 및 분석 시 적극 참조하십시오.

* 🛠️ **[development.md](file:///Users/wolyong/workspace/AgentHub/agenttrace/docs/development.md)**: 패키지 관리(uv), 환경변수 설정, 구동 명령어 및 pytest 테스트 가이드.
* 📝 **[logging.md](file:///Users/wolyong/workspace/AgentHub/agenttrace/docs/logging.md)**: 중앙 structlog 설정, JSON 로깅 아키텍처 및 로그 필터 명령어 모음.
* ⚠️ **[troubleshooting_learnings.md](file:///Users/wolyong/workspace/AgentHub/agenttrace/docs/troubleshooting_learnings.md)**: 과거 개발 시 발생했던 고유 스코프 에러 및 라이브러리 충돌 디버깅 해결 로그.
* 📦 **[docs/reference](file:///Users/wolyong/workspace/AgentHub/agenttrace/docs/reference)**: 요구사항 스펙 및 MVP 설계 기준 문서의 로컬 복제본 리포지토리.

---

## 1. Context Handling & Reference (컨텍스트 관리)

- **검색/분석 필터링 활용**: 리포지토리 검색, 세어보기, 파싱 및 요약에는 대화에 소스를 직접 뿌리기보다 `context-mode` 및 배치 실행(`ctx_batch_execute`, `ctx_execute`)을 우선 사용하십시오.
- **문서 동기화**: 매 세션 시작 시 반드시 `rtk git -C docs/reference pull`을 실행하여 최신 참조 아티팩트를 획득한 후 해당 경로(`docs/reference/artifacts/current`)의 문서를 읽기 전용으로 참조하십시오.

## 2. MCP Server Routing (도구 연동)

- **GitHub MCP**: PR, 이슈, 커멘트 및 리뷰 관련 조사 작업 시 셸 커맨드 대신 GitHub MCP를 최우선으로 연동하여 사용하십시오. (기본 대상: `YonghoBae/agenttrace`)
- **LangChain 공식 문서 조사**: LangChain, LangGraph, LangSmith 관련 기능을
  구현하거나 크게 변경할 때는 사용 가능한 LangChain Docs MCP와 공식 API
  Reference를 사용해 현재 권장 접근법, 버전 호환성 및 deprecated 여부를
  먼저 확인하십시오. 조사 없이 범용 기능의 수동 구현을 시작하지 마십시오.
  자세한 절차는 §6을 따릅니다.

## 3. Development Workflow (개발 절차)

- **RTK 프록시**: 모든 터미널 명령어(git, pytest 등)는 반드시 `rtk` 접두사를 붙여 토큰 소비를 최소화해야 합니다. (예: `rtk git status`)
- **TDD (테스트 우선)**: 코드를 수정하거나 노드 동작을 바꾸기 전에 테스트 코드를 먼저 추가 혹은 보완하십시오.
- **점진적 코드 수정**: 대량의 파일을 전체 덮어쓰기보다 `replace_file_content` 및 `multi_replace_file_content`로 변경이 필요한 코드 블록만 치환하여 정확도를 높이고 아웃풋 토큰을 절감하십시오.
- **종속성 관리**: 패키지 설치에는 반드시 `uv`를 사용하고 변경 시 `uv.lock`이 커밋에 보장되게 하십시오.
- **명세서 동기화 보장**: 영역 ID, 보고서 섹션명, JSON 구조화 스키마 등 인터페이스 상수를 수정할 때는 반드시 `docs/reference/artifacts/current/AI_ANALYSIS_SPEC.md`, `docs/reference/artifacts/current/ANALYSIS_QUALITY_EVALUATION_GUIDE.md`, `docs/reference/artifacts/current/CONTEXT7_ANALYSIS_EVALUATION.md` 및 로컬 품질 문서(`docs/analysis_quality_review_playbook.md`, `docs/analysis_evidence_policy.md`, `docs/analysis_run_artifact_contract.md`)를 읽고 목표 규격과 100% 동일하게 맞춰야 합니다.
- **외부 시스템 영향 검토 (사용자 승인 필수)**: 데이터베이스 컬럼명이나 외부 백엔드(Spring 등)와 통신하는 API 요청/응답 필드 및 내부 JSON 키명을 변경할 때는, 기존 시스템과의 연동이 깨질 수 있으므로 변경 적용 전 반드시 사용자에게 명시적인 승인과 확인을 받아야 합니다.
- **Specification-as-Code**: 목표 설계 문서와 소스 코드 간의 정합성을 검증하는 정적 테스트 코드를 작성하고 유지보수하여 완료 전 항상 자동 검증이 통과되도록 관리하십시오.

## 4. Node Logging Pattern (노드 로깅 지침)

새로운 파이프라인 노드 작성 시 또는 기존 노드 개선 시 다음의 구조화 로그 패턴을 엄격하게 구현하십시오.

```python
import time
from agenttrace.logging_config import get_logger
from agenttrace.agents.analysis.state import AnalysisState

logger = get_logger(__name__)

def my_node(state: AnalysisState) -> AnalysisState:
    _t = time.perf_counter()
    run_id = state.get("run_id", "-")
    
    # run_id와 현재 노드명을 항상 구조화 필드로 바인딩
    log = logger.bind(node="my_node", run_id=run_id)
    log.info("시작")
    
    # ... 노드 전용 구현 로직 ...
    
    # 노드 종료 시 성공 결과 주요 정보를 딕셔너리로 바인딩하여 1회 완료 로그 생성
    log.info(
        "완료", 
        key=value,  # 성공 결과 지표 등
        duration_ms=int((time.perf_counter() - _t) * 1000)
    )
    return result
```

- LLM 실패·fallback 처리 시에는 `log.warning()`, 코드 예외 상황에는 `log.error()`를 사용하며 context-specific 정보 외의 API 키 등 민감 정보가 로그 문자열에 포함되어서는 안 됩니다.

## 5. Subagent-Driven Development (서브에이전트 실행 원칙)

`superpowers:subagent-driven-development` 스킬로 plan을 실행할 때 아래 원칙을 준수하십시오.

### 5-1. Task 세분화 기준

하나의 Task는 **단일 함수 추가, 단일 import 교체, 단일 블록 제거** 수준으로 쪼개야 합니다.  
아래 신호 중 하나라도 해당되면 Task를 더 잘게 분할하십시오:

- 변경 파일이 2개를 초과한다
- 테스트 rewrite와 구현 변경이 같은 Task에 있다
- "A를 하고 B도 한다"는 설명이 필요하다
- 구현자가 여러 파일의 기존 로직을 이해해야만 작성할 수 있다

**나쁜 예 (너무 큰 Task):**
```
Task 3: Mermaid 분리 + 기존 테스트 3개 rewrite + 신규 테스트 2개 추가
```

**좋은 예 (세분화된 Tasks):**
```
Task 3A: ReportBodySection / ReportBodyResult / MermaidResult 스키마 추가
Task 3B: _generate_mermaid_for_section 함수 구현
Task 3C: _build_report_sections에서 retry 블록 제거
Task 3D: _build_report_sections에 섹션 4·5 Mermaid 병렬 생성 추가
Task 3E: 기존 테스트 3개 rewrite (스키마 교체 반영)
Task 3F: _generate_mermaid_for_section 단위 테스트 2개 추가
```

### 5-2. Plan 상세화 기준

Task가 작을수록 Plan은 더 구체적이어야 합니다. 각 Step에 다음을 명시하십시오:

- **대상 파일 + 정확한 위치** (예: `finalize_analysis.py` L32 `ReportSynthesisResult` 다음에)
- **추가/교체/삭제할 코드 블록** (diff 수준으로 기술)
- **테스트 assert 조건** (함수 반환값, call_count 등 구체적 검증 기준)

서브에이전트가 코드를 "파악"하는 시간 없이 바로 실행할 수 있을 만큼 상세해야 합니다.

### 5-3. 서브에이전트 모델 Tier

| Task 유형 | 기준 | 사용 모델 |
|---|---|---|
| **Flash** | 단일 함수 추가·삭제, import 교체, 단순 블록 제거, 직관적 단위 테스트 추가 | `flash` (cheapest) |
| **Standard** | 기존 코드 흐름 이해가 필요한 리팩토링, 테스트 rewrite (기존 mock 구조 파악 필요) | `self` |
| **Full (리뷰어)** | Spec compliance 검토, Code quality 검토, 설계 판단 | `research` 또는 `self` |

> **원칙**: 서브에이전트에게 "이 코드를 이해해야 한다"는 부담을 주는 순간, 더 작은 Task로 분할하거나 모델을 올려야 한다는 신호입니다.

### 5-4. 금지 사항

- Task 하나에 구현 + 테스트 rewrite를 동시에 포함하는 것
- 서브에이전트에게 plan 파일을 직접 읽게 하는 것 (컨트롤러가 full text를 전달해야 함)
- Spec compliance 통과 전에 Code quality 리뷰를 시작하는 것
- 같은 파일을 수정하는 구현 서브에이전트를 병렬 실행하는 것

### 5-5. 병렬 실행 가능 조건

아래 조건을 **모두** 만족하면 구현 서브에이전트를 병렬로 디스패치할 수 있습니다:

1. **파일 비중복**: 각 Task가 수정하는 파일이 서로 겹치지 않는다
2. **순서 독립**: Task B가 Task A의 결과물(함수, 타입, 상수)에 의존하지 않는다
3. **독립 테스트 가능**: 각 Task를 단독으로 `pytest`로 검증할 수 있다

**병렬 가능 예시:**
```
동시 실행 OK:
  Task 3A: finalize_analysis.py — 새 스키마 클래스 추가
  Task 4A: config.py — finalize_model_timeout 필드 추가
  (다른 파일, 상호 의존 없음)
```

**병렬 불가 예시:**
```
순차 실행 필요:
  Task 3A: finalize_analysis.py — ReportBodyResult 스키마 추가
  Task 3B: finalize_analysis.py — _generate_mermaid_for_section 구현  ← 같은 파일
  Task 3C: finalize_analysis.py — _build_report_sections 수정          ← 같은 파일 + 3A 결과 의존
```

> **참고**: 병렬 실행 시 `superpowers:dispatching-parallel-agents` 스킬을 함께 적용하십시오.

---

## 6. Best-Practice-First 원칙

새로운 기능을 직접 구현하기 전에 기존 코드베이스와 공식 생태계에서
검증된 구현 방법이 존재하는지 확인하십시오.

범용 기능을 조사 없이 자체 구현하는 것을 금지합니다.

### 6-1. 필수 사전 조사 대상

다음 기능을 새로 구현하거나 기존 구현을 크게 변경할 때 반드시 조사합니다.

* 모델과 도구 사이의 반복 실행 루프
* Agent 또는 ReAct 형태의 실행 제어
* 문서 로딩, 청크 분할, 검색, 임베딩
* 구조화 출력 및 출력 검증
* 상태 관리, 메모리, 체크포인트
* 토큰 계산 및 컨텍스트 관리
* 재시도, 타임아웃, 동시성 및 스트리밍
* 범용 텍스트 변환 또는 파싱

단순한 도메인 로직이나 프로젝트 고유 정책까지 외부 라이브러리로
대체할 필요는 없습니다.

### 6-2. 조사 순서

#### 1. 요구사항과 제약 확인

다음을 먼저 명확히 합니다.

* 구현하려는 기능
* 프로젝트 고유 동작
* 필요한 확장 지점
* 성능, 비용, 의존성 및 호환성 제약

#### 2. 기존 코드베이스 조사

새 파일이나 함수를 작성하기 전에:

1. `grep`, `rg`, `glob`으로 동일하거나 유사한 기능 검색
2. 기존 유틸리티, 헬퍼, 스키마, 노드의 재사용 가능성 검토
3. 동일한 실행 패턴이 이미 구현되어 있는지 확인
4. 중복 구현이 필요한 경우 그 이유를 명확히 기록

#### 3. 공식 생태계 조사

LangChain, LangGraph 또는 LangSmith 관련 기능이라면 다음 순서로 확인합니다.

1. 사용 가능한 LangChain Docs MCP를 통해 공식 권장 접근법 검색
2. LangChain 공식 API Reference에서 관련 심볼과 deprecated 여부 확인
3. 공식 migration guide와 release note 확인
4. 프로젝트의 선언 및 잠금 의존성 확인

   * `pyproject.toml`
   * `uv.lock`, `poetry.lock` 또는 관련 lockfile
5. 실제 실행 환경의 설치 버전 확인

   * `python -m pip show <package>`
   * `uv pip list` 또는 이에 준하는 명령

MCP 도구를 사용할 수 없는 경우 공식 문서와 API Reference를 직접 확인합니다.

최신 문서의 권장 방식과 현재 프로젝트에 설치된 버전에서 사용할 수 있는
방식을 구분해야 합니다.

### 6-3. 조사 결과에 따른 결정

| 조사 결과                        | 행동                                |
| ---------------------------- | --------------------------------- |
| 현재 의존성에서 사용할 수 있는 권장 API가 존재 | 해당 API를 우선 사용                     |
| 의존성 업그레이드 또는 추가가 필요          | 호환성, 유지보수성, 라이선스, 변경 범위를 검토한 뒤 도입 |
| 권장 API가 요구사항 일부만 충족          | 권장 API의 확장 지점 또는 하위 수준 API 사용     |
| 프로젝트 고유 제약으로 직접 사용 불가능       | 공식 구현의 설계와 실행 계약을 참고하여 내부 구현      |
| 적합한 기존 방법이 없음                | 내부 구현                             |

의존성을 추가하거나 업그레이드할 때는 다음을 검토합니다.

* 기존 코드와의 버전 호환성
* lockfile 변경 범위
* 테스트 및 마이그레이션 비용
* 프로젝트 아키텍처와의 적합성
* 유지보수 상태와 deprecated 여부
* 불필요하게 큰 의존성인지 여부

외부 API가 존재한다는 이유만으로 무조건 도입하지 않으며,
직접 구현이 익숙하다는 이유만으로 검증된 API를 배제하지도 않습니다.

### 6-4. 조사 결과 기록

중요한 구현 결정은 PR 설명 또는 관련 설계 문서에 간단히 기록합니다.

* 조사한 공식 API 또는 패턴
* 확인한 패키지 버전
* 검토한 대안
* 선택한 방법
* 다른 방법을 사용하지 않은 이유
* 필요한 경우 공식 문서 링크

구현 이력을 설명하기 위한 주석을 소스 코드에 불필요하게 남기지 않습니다.

### 6-5. 즉시 중단하고 조사해야 하는 신호

다음 패턴이 나타나면 구현을 중단하고 기존 API를 조사합니다.

* 모델 호출과 도구 실행을 반복하는 범용 루프 작성
  → `create_agent`, LangGraph Graph API 조사
* 범용 도구 선택, 실행, 결과 메시지 생성을 직접 구현
  → Agent harness, `ToolNode` 조사
* 문서 청크 분할 알고리즘 직접 구현
  → LangChain text splitters 조사
* 모델별 토큰 계산 로직 직접 구현
  → 공식 tokenizer 또는 모델 통합 기능 조사
* 범용 검색, BM25 또는 벡터 검색 기능 직접 구현
  → retriever 및 vector store 통합 조사
* 구조화 출력 파싱과 재시도를 직접 구현
  → structured output 기능 조사
* 이미 존재하는 변환 또는 검증 로직과 유사한 함수 작성
  → 기존 코드 재검색

단, 프로젝트 고유 상태 전환이나 명시적으로 커스텀 설계가 필요한 경우에는
수동 구현 자체를 위반으로 판단하지 않습니다.

### 6-6. 금지 사항

* 공식 권장 방식을 조사하지 않고 범용 기능을 먼저 수동 구현하는 것
* 현재 버전을 확인하지 않고 최신 문서의 코드를 그대로 적용하는 것
* deprecated API임을 알면서 신규 코드에 도입하는 것
* 기존 코드에 동일 기능이 있는데 중복 구현하는 것
* 근거 없이 의존성을 추가하거나, 근거 없이 외부 라이브러리를 배제하는 것
