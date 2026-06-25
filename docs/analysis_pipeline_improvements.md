# 분석 파이프라인 LLM 에이전트 실구동 개선

## 배경

기존 분석 파이프라인은 LLM 에이전트가 실제로 호출되지 않고 모든 결과가 fallback 템플릿으로 생성되는 문제가 있었다. 두 개 리포지토리(upstash/context7, obra/superpowers)로 테스트한 결과:

- 8개 영역 전부 동일한 `partially_confirmed` 템플릿 문구
- 11개 보고서 섹션 내용이 전부 동일
- evidence가 전부 `fallback-ref-XXX` (실제 코드 분석 아님)
- agent_type이 fallback 휴리스틱으로만 판별

원인은 3가지였다:

1. `build_repo_map_node`가 `repo_map_render` state 키를 채우지 않음
2. ReAct 에이전트의 컨텍스트 폭발 (128K 토큰 한도 초과)
3. fallback 파일 선택이 메타데이터 위주 (package.json, .yml 등)

## 개선 사항

### 1. build_repo_map_node: state 키 채우기 (`build_repo_map.py`)

**문제**: `repo_map_render`, `definition_ranks`, `symbol_tags` state 키가 선언되어 있었으나 어떤 노드도 채우지 않았다. `area_explorer`가 빈 구조 지도로 시작했다.

**해결**: `build_repo_map_node`에서 `render_repo_map()`을 호출하여 토큰 예산에 맞춘 구조 지도를 생성하고, `definition_ranks`와 `symbol_tags`를 state에 추가.

```python
repo_map_render = render_repo_map(
    definition_ranks=definition_ranks,
    special_files=critical_config_paths,
    max_tokens=4096,
)
return {
    "repo_map": repo_map,
    "definition_ranks": definition_ranks,
    "repo_map_render": repo_map_render,
    "symbol_tags": symbol_tags,
}
```

### 2. area_explorer: 단일 structured output 방식 도입 (`area_explorer.py`)

**문제**: ReAct 에이전트가 도구로 파일을 탐색하면서 컨텍스트가 폭발 (context7: 136,887 tokens > 128K limit)하거나, recursion limit 초과, rate limit 초과로 fallback.

**해결**: PageRank 상위 파일을 프롬프트에 미리 로드하여 단일 LLM 호출로 분석 수행.

```python
key_files = _select_key_files(state)  # PageRank 상위 15개 실제 소스 코드
if len(key_files) >= 5:
    # 단일 structured output 호출 (ReAct 없이)
    structured_model = model.with_structured_output(AreaExplorationResult)
    structured_response = structured_model.invoke(prompt)
else:
    # 파일이 부족한 경우만 ReAct 에이전트 사용
    agent = create_agent(model=model, tools=tools, ...)
```

### 3. _select_key_files: 실제 소스 코드 우선 선택 (`area_explorer.py`)

**문제**: 기존 파일 선택이 `critical_config`에 +100점을 줘서 package.json, .yml, Dockerfile 등 메타데이터만 선택됨. 실제 .ts 소스 코드가 하나도 포함되지 않음.

**해결**: 소스 코드(.ts, .py, .go 등)와 메타데이터(.json, .yml 등)를 분리하여 소스 코드를 우선 선택. 메타데이터는 최대 3개로 제한.

```
이전: .env.example, .github/workflows/*.yml, package.json, Dockerfile (전부 메타데이터)
이후: packages/mcp/src/index.ts, packages/cli/src/commands/setup.ts, packages/sdk/src/client.ts (실제 소스)
```

### 4. 도구 결과 크기 제한 (`react_tools.py`)

**문제**: `read_file` 20KB, `search_code` 50결과, `get_structure_map` 200엔트리로 컨텍스트 폭발 원인.

**해결**: 각 도구의 결과 크기를 대폭 축소.

| 도구 | 이전 | 이후 |
|---|---|---|
| `read_file` | 20,000자 | 8,000자 |
| `search_code` | 50결과 | 20결과 |
| `get_structure_map` | 200엔트리 | 100엔트리 |

### 5. Rate limit 재시도 로직 (`area_explorer.py`, `finalize_analysis.py`)

**문제**: gpt-4o-mini TPM 200K 한도 초과 시 즉시 fallback.

**해결**: 429 에러 시 20s → 40s → 60s 간격으로 최대 3회 재시도.

```python
def _invoke_with_retry(fn, *args, max_retries=3, **kwargs):
    for attempt in range(max_retries):
        try:
            return fn(*args, **kwargs)
        except Exception as exc:
            if "rate_limit" in str(exc).lower() and attempt < max_retries - 1:
                time.sleep(20 * (attempt + 1))
                continue
            raise
```

### 6. finalize_analysis: 보고서 품질 개선 (`finalize_analysis.py`)

**문제**: 보고서 섹션이 1-2문장 (100-150자)으로 정보량 부족. 구체적 코드 참조 없음.

**해결**: 3가지 개선:

1. **프롬프트 강화**: 섹션당 최소 800자, 4-6단락 요구. GOOD/BAD 예시 제공.
2. **compact payload 확장**: `_compact_area_findings` findings 3→5개, limitations 2→3개. `_compact_evidence_refs`에 `content_excerpt`, `line_start/end` 추가.
3. **max_tokens 증가**: 8,192 → 16,384.

### 7. agent_type 정규화 (`finalize_analysis.py`)

**문제**: LLM이 `"Skill."` (마침표 포함)을 반환하면 Pydantic validation 실패.

**해결**: `agent_type` 값을 정규화하는 헬퍼 함수 추가.

### 8. 에러 로깅 개선 (`area_explorer.py`)

**문제**: fallback 시 에러 메시지만 로깅되어 원인 파악困难.

**해결**: traceback, 마지막 메시지 타입/내용, 메시지 개수를 구조화 로그에 포함.

## 결과 비교

| 항목 | 이전 (fallback) | context7 (개선 후) | superpowers (개선 후) |
|---|---|---|---|
| LLM 호출 | 없음 | 단일 structured output | 단일 structured output |
| analysis_status | completed_with_limitations | **completed** | **completed** |
| agent_type | fallback 휴리스틱 | **MCP** (정확) | **Skill** (정확) |
| confirmed 영역 | 0/8 | **5/8** | **8/8** |
| evidence | 12개 fallback-ref | **16개 실제 ref** | **17개 실제 ref** |
| 총 body 문자수 | ~1,500자 | **7,532자** | **6,086자** |
| 섹션당 평균 | ~136자 | **684자** | **553자** |
| Mermaid | 하드코딩 1개 | **LLM 생성 2개** | **LLM 생성 2개** |
| 실행 시간 | ~170s (fallback) | **75s** | **165s** |
| 구체적 함수명 | 없음 | `resolve-library-id`, `createMcpServer` 등 | `SuperpowersPlugin`, `server.cjs` 등 |

## 수정 파일 목록

| 파일 | 변경 내용 |
|---|---|
| `src/agenttrace/agents/analysis/nodes/build_repo_map.py` | `repo_map_render`, `definition_ranks`, `symbol_tags` state 키 추가 |
| `src/agenttrace/agents/analysis/nodes/area_explorer.py` | `_select_key_files`, 단일 structured output, 재시도 로직, 프롬프트 개선 |
| `src/agenttrace/agents/analysis/nodes/finalize_analysis.py` | 재시도 로직, 프롬프트 강화, compact payload 확장, agent_type 정규화 |
| `src/agenttrace/agents/analysis/react_tools.py` | 도구 결과 크기 제한 (read_file 20K→8K, search 50→20, structure_map 200→100) |
| `src/agenttrace/config.py` | `finalize_model_max_tokens` 8192→16384 |
| `tests/test_analysis_v2_nodes.py` | `_compact_area_findings`, `_compact_evidence_refs` 테스트 업데이트 |
