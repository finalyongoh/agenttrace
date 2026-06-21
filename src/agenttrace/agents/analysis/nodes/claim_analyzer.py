from __future__ import annotations

import re

from agenttrace.agents.analysis.schemas.result import AnalysisClaim
from agenttrace.agents.analysis.state import AnalysisState


CLAIM_MARKERS = [
    "support", "supports", "provide", "provides", "include", "includes",
    "implement", "implements", "server", "client", "tool", "resource",
    "prompt", "eval", "benchmark", "skill", "plugin", "workflow",
    "지원", "제공", "구현", "도구", "서버", "클라이언트", "평가",
]


def _strip_markdown(text: str) -> str:
    text = re.sub(r"\[([^\]]+)\]\([^)]*\)", r"\1", text)
    text = re.sub(r"[`*_#>]", "", text)
    return re.sub(r"\s+", " ", text).strip(" -\t")


def claim_analyzer(state: AnalysisState) -> AnalysisState:
    readme = state.get("readme", "")
    sentences = re.split(r"(?<=[.!?。])\s+|\n+", readme.strip())
    claims: list[dict] = []

    for sentence in sentences:
        clean = _strip_markdown(sentence)
        lower = clean.lower()
        if len(clean) < 12:
            continue
        if not any(marker in lower for marker in CLAIM_MARKERS):
            continue
        claim = AnalysisClaim(
            claim_id=f"claim-{len(claims) + 1}",
            claim_text=clean[:500],
            source_path="README.md",
            source_section=None,
            confidence=0.62,
            evidence_signal_ids=[],
        )
        claims.append(claim.model_dump())

    return {"claims": claims[:8]}
