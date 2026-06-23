from pathlib import Path
import re
from agenttrace.agents.analysis.schemas.result import COMMON_ANALYSIS_AREAS
from agenttrace.agents.analysis.nodes.finalize_analysis import REPORT_SECTION_NAMES

def test_common_areas_sync_with_spec_markdown():
    spec_path = Path("docs/reference/artifacts/current/AI_ANALYSIS_SPEC.md")
    assert spec_path.exists(), "스펙 문서가 존재하지 않습니다."
    
    content = spec_path.read_text(encoding="utf-8")
    
    # AI_ANALYSIS_SPEC.md의 3대 분석 실행 묶음 설명부에서 영역 ID와 한국어 명칭 추출
    # 패턴 예: 영역 3: **아키텍처와 모듈 관계** (`architecture-and-modules`)
    spec_areas = re.findall(r"영역 \d+:\s+\*\*([^*]+)\*\*\s+\(\\?`([^`]+)\\?`\)", content)
    assert len(spec_areas) == 8, f"스펙에서 8개 영역을 찾지 못했습니다 (찾은 개수: {len(spec_areas)})"
    
    code_areas = dict(COMMON_ANALYSIS_AREAS)
    
    for name, area_id in spec_areas:
        assert area_id in code_areas, f"스펙의 영역 ID '{area_id}'가 코드(COMMON_ANALYSIS_AREAS)에 존재하지 않습니다."
        assert code_areas[area_id] == name, f"영역 ID '{area_id}'의 이름 불일치: 스펙='{name}', 코드='{code_areas[area_id]}'"

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
