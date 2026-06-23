# Central Logging Guide

이 문서는 AgentTrace의 structlog 기반 구조화 JSON 로깅 설정 및 운영 환경에서의 로그 분석 방법에 대한 가이드입니다.

---

## 1. 중앙 로깅 아키텍처

로깅 초기화는 `setup_logging()` ([logging_config.py](file:///Users/wolyong/workspace/AgentHub/agenttrace/src/agenttrace/logging_config.py))을 통해 애플리케이션 시작 시 단 **1회만** 초기화되어야 합니다.

* **API 서버**: `lifespan()` 진입 시 호출
* **Worker 데몬**: `main()` 진입 시 호출

외부 라이브러리(`httpx`, `openai`, `langchain`, `langgraph`, `uvicorn.access`)의 무분별한 디버그 로그 노이즈는 `setup_logging()`에서 `WARNING` 레벨 이상만 노출되도록 필터링되어 고정되어 있습니다.

---

## 2. 로그 출력 포맷 (JSON)

모든 애플리케이션 로그는 표준 출력(stdout)으로 JSON 구조화된 스트림 형태로 덤프됩니다.

### 실제 덤프 예시
```json
{"node":"collect_inputs","run_id":"abc-123","event":"완료","source_files":42,"mode":"normal","level":"info","timestamp":"2026-06-23T04:00:00Z"}
```

이 방식은 운영 환경의 클라우드 로깅 시스템(Splunk, Datadog, CloudWatch, Stackdriver 등)이나 로컬 터미널에서 `jq` 도구를 활용하여 필요한 키값을 추출하고 통계를 낼 때 매우 강력합니다.

---

## 3. 로그 추적 명령어 모음

로컬 또는 Docker Compose 환경에서 로깅 파이프라인의 흐름과 오류를 분석하는 데 요긴한 유틸리티 명령어 필터 예시입니다.

### 특정 분석 작업(run_id)의 전체 파이프라인 흐름만 추적
```bash
docker compose logs api | grep '"run_id":"<UUID>"'
```

### 파이프라인 진행 과정 중 에러 로그만 필터
```bash
docker compose logs api | grep '"level":"error"'
```

### 각 파이프라인 노드별 완료 소요 시간(duration_ms) 통계 확인
```bash
docker compose logs api | grep '"event":"완료"' | jq '{node,run_id,duration_ms}'
```

---

## 4. 로깅 주의 사항

* **보안 제한**: 로그 메시지 및 바인딩 키값에 API Key, 원본 소스코드 전체 텍스트, 개인정보(이메일, 비밀번호 등)가 포함되지 않도록 특별히 주의하십시오.
* **컨텍스트 바인딩 사용**: 전역 Logger 객체는 스레드/태스크 세이프한 컨텍스트(run_id 등)를 담지 못하므로, 반드시 호출 초기에 `log = logger.bind(...)`로 인스턴스를 받아 획득한 함수 로컬 변수 `log`를 통해 메시지를 남겨야 합니다.
