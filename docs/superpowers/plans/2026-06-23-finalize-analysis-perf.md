# finalize_analysis 병목 개선 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** `finalize_analysis` 노드의 LLM 호출 시간을 145s → 60s 이하로 단축

**Architecture:** (1) config/models에 timeout 설정 추가 → (2) compact payload 함수 도입 → (3) Mermaid 생성 분리 → (4) 3-batch 병렬 실행

**Tech Stack:** Python, `concurrent.futures.ThreadPoolExecutor`, `langchain_openai.ChatOpenAI`, `pytest`

---

## Task 1: config + models에 timeout/max_tokens 설정 추가

**Files:**
- Modify: `src/agenttrace/config.py`
- Modify: `src/agenttrace/models.py`
- Test: `tests/test_analysis_v2_nodes.py` (기존 테스트 통과 확인)

- [ ] **Step 1: `config.py`에 분석 모델 timeout/max_tokens 필드 추가**

`src/agenttrace/config.py`의 Settings 클래스에 추가:
```python
analysis_model_timeout: int = 90          # 초, 환경변수: AGENTTRACE_ANALYSIS_MODEL_TIMEOUT
analysis_model_max_tokens: int = 4096     # 환경변수: AGENTTRACE_ANALYSIS_MODEL_MAX_TOKENS
```

그리고 `get_settings()` 팩토리 함수에서도 해당 env 변수를 읽어 반영:
```python
analysis_model_timeout=int(_get_env("AGENTTRACE_ANALYSIS_MODEL_TIMEOUT", env_values, "90")),
analysis_model_max_tokens=int(_get_env("AGENTTRACE_ANALYSIS_MODEL_MAX_TOKENS", env_values, "4096")),
```

- [ ] **Step 2: `models.py`의 `build_openai_analysis_model()`에 timeout/max_tokens/max_retries 적용**

```python
def build_openai_analysis_model() -> Any:
    settings = get_settings()
    ...
    kwargs = {
        "model": settings.analysis_model,
        "api_key": settings.openai_api_key,
        "temperature": 0,
        "timeout": settings.analysis_model_timeout,
        "max_tokens": settings.analysis_model_max_tokens,
        "max_retries": 1,
    }
    if settings.openai_api_base:
        kwargs["base_url"] = settings.openai_api_base
    return ChatOpenAI(**kwargs)
```

- [ ] **Step 3: 기존 테스트가 여전히 통과하는지 확인**

```bash
rtk uv run pytest tests/test_analysis_v2_nodes.py -x -q 2>&1 | tail -20
```

Expected: 모든 테스트 PASS (timeout 설정은 mock 환경에서 영향 없음)

- [ ] **Step 4: Commit**

```bash
rtk git add src/agenttrace/config.py src/agenttrace/models.py
rtk git commit -m "perf(finalize): add timeout/max_tokens/max_retries to analysis model"
```

---

## Task 2: compact payload 함수 도입

**Files:**
- Modify: `src/agenttrace/agents/analysis/nodes/finalize_analysis.py`
- Test: `tests/test_analysis_v2_nodes.py`

- [ ] **Step 1: TDD — `_compact_area_findings` / `_compact_evidence_refs` 실패 테스트 작성**

`tests/test_analysis_v2_nodes.py`에 추가:
```python
from agenttrace.agents.analysis.nodes.finalize_analysis import (
    _compact_area_findings,
    _compact_evidence_refs,
)

def test_compact_area_findings_reduces_size():
    findings = [
        {
            "area_id": "project-purpose",
            "area_name": "프로젝트 목적과 주요 기능",
            "status": "confirmed",
            "summary": "이 프로젝트는 X를 합니다.",
            "findings": [
                {"content": "finding 1", "type": "fact", "evidence_refs": ["ref-1"]},
                {"content": "finding 2", "type": "inference", "evidence_refs": ["ref-2"]},
                {"content": "finding 3", "type": "fact", "evidence_refs": ["ref-3"]},
                {"content": "finding 4", "type": "inference", "evidence_refs": ["ref-4"]},
            ],
            "limitations": ["한계 1"],
            "unresolved_questions": [],
        }
    ]
    result = _compact_area_findings(findings)
    assert "project-purpose" in result
    assert "confirmed" in result
    # top-3 findings만 포함, finding 4는 포함 안 됨
    assert "finding 4" not in result

def test_compact_evidence_refs_excludes_content_excerpt():
    refs = [
        {
            "id": "ref-1",
            "path": "src/main.py",
            "description": "설명",
            "content_excerpt": "def main(): ...",
            "symbol": None,
        }
    ]
    result = _compact_evidence_refs(refs)
    assert "ref-1" in result
    assert "src/main.py" in result
    assert "def main():" not in result  # content_excerpt 제외
```

- [ ] **Step 2: 테스트 실행하여 실패 확인**

```bash
rtk uv run pytest tests/test_analysis_v2_nodes.py::test_compact_area_findings_reduces_size tests/test_analysis_v2_nodes.py::test_compact_evidence_refs_excludes_content_excerpt -v 2>&1 | tail -15
```

Expected: `ImportError` 또는 `FAILED`

- [ ] **Step 3: `_compact_area_findings` / `_compact_evidence_refs` 구현**

`finalize_analysis.py`에 추가 (기존 함수들 아래에):
```python
def _compact_area_findings(area_findings: list[dict]) -> str:
    """Report synthesis용 compact payload: area별 top-3 findings만 포함."""
    compact = []
    for af in area_findings:
        compact.append({
            "area_id": af.get("area_id"),
            "status": af.get("status"),
            "summary": af.get("summary"),
            "findings": [
                {"content": f.get("content"), "type": f.get("type")}
                for f in af.get("findings", [])[:3]
            ],
            "limitations": af.get("limitations", [])[:2],
        })
    return json.dumps(compact, indent=2, ensure_ascii=False)


def _compact_evidence_refs(evidence_refs: list[dict]) -> str:
    """Report synthesis용 compact payload: id/path/description만 포함."""
    compact = [
        {
            "id": r.get("id"),
            "path": r.get("path"),
            "description": r.get("description"),
        }
        for r in evidence_refs
    ]
    return json.dumps(compact, indent=2, ensure_ascii=False)
```

- [ ] **Step 4: `_build_report_sections`에서 compact payload 사용하도록 변경**

`_build_report_sections` 함수 내부:
```python
# 변경 전
area_findings_str = json.dumps(area_findings, indent=2, ensure_ascii=False)
evidence_refs_str = json.dumps(evidence_refs, indent=2, ensure_ascii=False)

# 변경 후
area_findings_str = _compact_area_findings(area_findings)
evidence_refs_str = _compact_evidence_refs(evidence_refs)
```

- [ ] **Step 5: 테스트 통과 확인**

```bash
rtk uv run pytest tests/test_analysis_v2_nodes.py -x -q 2>&1 | tail -20
```

Expected: 모든 테스트 PASS

- [ ] **Step 6: Commit**

```bash
rtk git add src/agenttrace/agents/analysis/nodes/finalize_analysis.py tests/test_analysis_v2_nodes.py
rtk git commit -m "perf(finalize): add compact payload functions to reduce synthesis input tokens"
```

---

## Task 3: Mermaid 생성/재시도 분리

**Files:**
- Modify: `src/agenttrace/agents/analysis/nodes/finalize_analysis.py`
- Test: `tests/test_analysis_v2_nodes.py`

- [ ] **Step 1: TDD — Mermaid 분리 테스트 작성**

`tests/test_analysis_v2_nodes.py`에 추가:
```python
from agenttrace.agents.analysis.nodes.finalize_analysis import _generate_mermaid_for_section

def test_generate_mermaid_for_section_returns_valid_diagram(monkeypatch):
    """_generate_mermaid_for_section이 유효한 Mermaid 코드를 반환하는지 테스트."""
    from unittest.mock import MagicMock
    import agenttrace.agents.analysis.nodes.finalize_analysis as fa_module

    mock_model = MagicMock()
    mock_model.with_structured_output.return_value = mock_model
    mock_model.invoke.return_value = MagicMock(
        mermaid_code="flowchart TD\n  A[Input] --> B[Output]"
    )
    monkeypatch.setattr(fa_module, "build_openai_analysis_model", lambda: mock_model)

    result = _generate_mermaid_for_section(
        section_id=4,
        section_name="전체 동작 방식",
        readme="# Test Repo",
        area_summary="흐름 요약"
    )
    assert result is not None
    assert "flowchart" in result or result is None  # 실패 시 None 반환도 허용
```

- [ ] **Step 2: 테스트 실행하여 실패 확인**

```bash
rtk uv run pytest tests/test_analysis_v2_nodes.py::test_generate_mermaid_for_section_returns_valid_diagram -v 2>&1 | tail -10
```

Expected: `ImportError` 또는 `FAILED`

- [ ] **Step 3: `_generate_mermaid_for_section` 함수 추가 및 `_build_report_sections` 수정**

`finalize_analysis.py`에 추가:
```python
class MermaidResult(BaseModel):
    mermaid_code: str = Field(default="")


def _generate_mermaid_for_section(
    section_id: int,
    section_name: str,
    readme: str,
    area_summary: str,
) -> str | None:
    """섹션 4·5용 Mermaid 다이어그램을 별도 경량 LLM 호출로 생성."""
    try:
        model = build_openai_analysis_model()
        structured_model = model.with_structured_output(MermaidResult)
        prompt = ChatPromptTemplate.from_messages([
            ("system",
             "You are a technical diagram expert. Generate a valid Mermaid diagram for the given section. "
             "Output ONLY raw mermaid syntax (no markdown code blocks). "
             "Use one of: flowchart TD/LR, graph TD/LR, sequenceDiagram, classDiagram. "
             "Keep it concise (5-15 nodes). Labels with special characters must be double-quoted."),
            ("human",
             "Section {section_id}: {section_name}\n\nContext:\n{context}\n\n"
             "Generate a Mermaid diagram that best illustrates this section."),
        ])
        result = structured_model.invoke(prompt.invoke({
            "section_id": section_id,
            "section_name": section_name,
            "context": f"README (excerpt):\n{readme[:5000]}\n\nArea summary:\n{area_summary[:2000]}",
        }))
        code = result.mermaid_code
        if "```" in code:
            code = re.sub(r"```(mermaid)?", "", code).strip()
        if validate_mermaid_syntax(code):
            return code
        return None
    except Exception as exc:
        logger.warning(f"Mermaid generation for section {section_id} failed: {exc}")
        return None
```

`_build_report_sections` 내부 수정:
1. `ReportSynthesisResult` 스키마에서 `mermaid_diagram` 필드를 제거하고 body_markdown만 받도록 별도 스키마 `ReportBodyResult` 추가
2. synthesis 호출 후, 섹션 4와 5에 대해 `_generate_mermaid_for_section` 별도 호출
3. 기존 retry 루프와 final cleanup 유지

> 참고: `ReportBodyResult` 스키마:
> ```python
> class ReportBodySection(BaseModel):
>     section_id: int
>     section_name: str
>     status: str
>     title: str
>     body_markdown: str
>     mermaid_diagram: None = None  # synthesis 단계에서는 항상 None
>
> class ReportBodyResult(BaseModel):
>     report_sections: list[ReportBodySection] = Field(default_factory=list)
> ```

- [ ] **Step 4: system_prompt에서 Mermaid 생성 지시 제거**

`_build_report_sections`의 system_prompt에서:
```python
# 제거할 부분 (기존)
"2. For section 4 ('전체 동작 방식') and section 5 ('아키텍처와 주요 컴포넌트'), "
"you MUST generate a valid Mermaid diagram in `mermaid_diagram` field. ..."

# 대체 (새로운)
"2. The `mermaid_diagram` field must always be null. Mermaid diagrams are generated separately."
```

- [ ] **Step 5: Mermaid 별도 호출 추가 (synthesis 완료 후)**

`_build_report_sections` 내 final_sections 구성 직후:
```python
# sections 4, 5에 Mermaid 생성
mermaid_section_ids = {4, 5}
area_summary_map = {af.get("area_id"): af.get("summary", "") for af in area_findings}
execution_summary = area_summary_map.get("execution-flow", "")
arch_summary = area_summary_map.get("architecture-and-modules", "")

for sec in final_sections:
    sid = sec.get("section_id")
    if sid == 4:
        sec["mermaid_diagram"] = _generate_mermaid_for_section(
            4, "전체 동작 방식", readme, execution_summary
        )
    elif sid == 5:
        sec["mermaid_diagram"] = _generate_mermaid_for_section(
            5, "아키텍처와 주요 컴포넌트", readme, arch_summary
        )
```

- [ ] **Step 6: 전체 테스트 통과 확인**

```bash
rtk uv run pytest tests/test_analysis_v2_nodes.py -x -q 2>&1 | tail -20
```

Expected: 모든 테스트 PASS

- [ ] **Step 7: Commit**

```bash
rtk git add src/agenttrace/agents/analysis/nodes/finalize_analysis.py tests/test_analysis_v2_nodes.py
rtk git commit -m "perf(finalize): separate mermaid generation from report synthesis"
```

---

## Task 4: 3-batch 병렬 실행

**Files:**
- Modify: `src/agenttrace/agents/analysis/nodes/finalize_analysis.py`
- Test: `tests/test_analysis_v2_nodes.py`

- [ ] **Step 1: TDD — 병렬 실행 테스트 작성**

`tests/test_analysis_v2_nodes.py`에 추가:
```python
def test_build_area_findings_calls_batches_concurrently(monkeypatch):
    """3개 배치가 별도 스레드에서 병렬 실행되는지 확인 (호출 횟수 기반)."""
    import threading
    import agenttrace.agents.analysis.nodes.finalize_analysis as fa_module
    from unittest.mock import MagicMock

    call_times = []
    lock = threading.Lock()

    def fake_invoke(prompt_value):
        import time
        t = time.perf_counter()
        time.sleep(0.05)  # 50ms 지연 시뮬레이션
        with lock:
            call_times.append(t)
        return MagicMock(
            area_findings=[],
            evidence_refs=[],
        )

    mock_model = MagicMock()
    mock_model.with_structured_output.return_value = mock_model
    mock_model.invoke.side_effect = fake_invoke
    monkeypatch.setattr(fa_module, "build_openai_analysis_model", lambda: mock_model)
    monkeypatch.setattr(fa_module, "get_settings", lambda: MagicMock(openai_api_key="test"))

    state = {
        "readme": "# Test",
        "file_tree": [],
        "content_chunks": [],
    }
    _build_area_findings(state, [{"id": "ref-1", "path": "README.md", ...}])

    # 3번 호출됨
    assert mock_model.invoke.call_count == 3
    # 병렬이면 첫 호출~마지막 호출 간격이 순차(150ms)보다 훨씬 짧아야 함 (< 100ms)
    if len(call_times) == 3:
        elapsed = max(call_times) - min(call_times)
        assert elapsed < 0.1, f"배치가 병렬이 아닌 것 같음: {elapsed:.3f}s"
```

- [ ] **Step 2: 테스트 실행하여 실패 확인 (현재 순차 실행이므로 elapsed > 0.1)**

```bash
rtk uv run pytest tests/test_analysis_v2_nodes.py::test_build_area_findings_calls_batches_concurrently -v 2>&1 | tail -15
```

Expected: `FAILED` (elapsed > 0.1s 또는 assertion error)

- [ ] **Step 3: `_build_area_findings`에 ThreadPoolExecutor 도입**

`finalize_analysis.py` 상단에 import 추가:
```python
import concurrent.futures
```

`_build_area_findings` 함수 내부 배치 실행 부분을 수정:

```python
# 변경 전 (순차)
for batch in batches_definition:
    ...
    batch_res = structured_model.invoke(prompt_value)
    all_area_findings.extend(batch_res.area_findings)
    all_evidence_refs.extend(batch_res.evidence_refs)

# 변경 후 (병렬)
def _invoke_single_batch(batch_def: dict) -> tuple[list, list]:
    areas_list_text = ", ".join(
        [f"'{area_id}' ({area_name})" for area_id, area_name in batch_def["areas"]]
    )
    areas_detail_text = "\n".join(
        [f"- {area_id}: {area_name}" for area_id, area_name in batch_def["areas"]]
    )
    prompt_value = prompt.invoke({
        "areas_list_text": areas_list_text,
        "areas_detail_text": areas_detail_text,
        "readme": readme[:30000],
        "file_tree": file_tree_str[:20000],
        "chunks_text": chunks_text,
    })
    batch_res = structured_model.invoke(prompt_value)
    return batch_res.area_findings, batch_res.evidence_refs

with concurrent.futures.ThreadPoolExecutor(max_workers=3) as executor:
    futures = [executor.submit(_invoke_single_batch, b) for b in batches_definition]
    for future in concurrent.futures.as_completed(futures):
        findings, refs = future.result()
        all_area_findings.extend(findings)
        all_evidence_refs.extend(refs)
```

> 주의: `structured_model`과 `prompt` 객체는 ThreadPoolExecutor 진입 전에 생성해두고 각 스레드에서 공유 사용.

- [ ] **Step 4: 테스트 통과 확인**

```bash
rtk uv run pytest tests/test_analysis_v2_nodes.py -x -q 2>&1 | tail -20
```

Expected: 모든 테스트 PASS

- [ ] **Step 5: Commit**

```bash
rtk git add src/agenttrace/agents/analysis/nodes/finalize_analysis.py tests/test_analysis_v2_nodes.py
rtk git commit -m "perf(finalize): parallelize 3 area-finding batches with ThreadPoolExecutor"
```

---

## Task 5: 최종 검증 및 로그 확인

**Files:**
- Read: smoke 테스트 실행 로그

- [ ] **Step 1: 전체 테스트 스위트 실행**

```bash
rtk uv run pytest tests/ -x -q 2>&1 | tail -30
```

Expected: 전체 PASS

- [ ] **Step 2: smoke 실행으로 duration_ms 측정**

```bash
# smoke 스크립트가 있다면
rtk uv run python scripts/smoke_context7.py 2>&1 | grep -E "duration_ms|finalize"
```

Expected: `finalize_analysis` 노드의 `duration_ms` ≤ 60000

- [ ] **Step 3: `.env.example` 업데이트**

```
# Analysis Model Settings
AGENTTRACE_ANALYSIS_MODEL_TIMEOUT=90
AGENTTRACE_ANALYSIS_MODEL_MAX_TOKENS=4096
```

- [ ] **Step 4: 최종 Commit**

```bash
rtk git add .env.example
rtk git commit -m "docs: add analysis model timeout/max_tokens env vars to .env.example"
```
