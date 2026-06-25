from pathlib import Path
import re
from agenttrace.agents.analysis.schemas.result import COMMON_ANALYSIS_AREAS
from agenttrace.agents.analysis.nodes.finalize_analysis import REPORT_SECTION_NAMES

EXPECTED_REFERENCE_DOCS = {
    "AI_ANALYSIS_SPEC.md",
    "ANALYSIS_QUALITY_EVALUATION_GUIDE.md",
    "CONTEXT7_ANALYSIS_EVALUATION.md",
}


def test_expected_reference_docs_are_current():
    reference_dir = Path("docs/reference/artifacts/current")
    missing = sorted(name for name in EXPECTED_REFERENCE_DOCS if not (reference_dir / name).exists())

    assert not missing, (
        "docs/reference is missing expected analysis reference docs. "
        "Run `rtk git -C docs/reference pull` and update EXPECTED_REFERENCE_DOCS if upstream changed: "
        + ", ".join(missing)
    )
    assert "ANALYSIS_AGENT_IMPLEMENTATION_EVAL_SPEC.md" not in EXPECTED_REFERENCE_DOCS


def test_project_guidance_does_not_require_removed_eval_spec():
    guidance = Path("AGENTS.md").read_text(encoding="utf-8")

    assert "ANALYSIS_AGENT_IMPLEMENTATION_EVAL_SPEC.md" not in guidance


def test_common_areas_sync_with_spec_markdown():
    spec_path = Path("docs/reference/artifacts/current/AI_ANALYSIS_SPEC.md")
    assert spec_path.exists(), "스펙 문서가 존재하지 않습니다."
    
    content = spec_path.read_text(encoding="utf-8")
    
    section_block = content.split("### 6.6 공통 분석 영역 (8대 영역)")[1].split("### 6.7")[0]
    spec_area_names = re.findall(r"\d+\.\s+\*\*([^*]+)\*\*:", section_block)
    assert len(spec_area_names) == 8, f"스펙에서 8개 영역을 찾지 못했습니다 (찾은 개수: {len(spec_area_names)})"

    code_areas = dict(COMMON_ANALYSIS_AREAS)

    assert list(code_areas.values()) == spec_area_names

def test_report_sections_sync_with_spec_markdown():
    spec_path = Path("docs/reference/artifacts/current/AI_ANALYSIS_SPEC.md")
    assert spec_path.exists()
    content = spec_path.read_text(encoding="utf-8")
    
    # 11대 고정 보고서 섹션 블록만 잘라냄
    section_block = content.split("#### 6.13.2 11대 고정 보고서 섹션")[1].split("#### 6.13.3")[0]
    
    # 11대 고정 보고서 섹션 타이틀 추출 (패턴: 1. **핵심 요약과 추천 독자**:)
    spec_sections = re.findall(r"\d+\.\s+\*\*([^*]+)\*\*:", section_block)
    assert len(spec_sections) == 11, f"스펙에서 11개 섹션을 찾지 못했습니다 (찾은 개수: {len(spec_sections)})"
    
    for idx, spec_sec in enumerate(spec_sections):
        assert spec_sec == REPORT_SECTION_NAMES[idx], f"Index {idx} 섹션명 불일치: 스펙='{spec_sec}', 코드='{REPORT_SECTION_NAMES[idx]}'"
