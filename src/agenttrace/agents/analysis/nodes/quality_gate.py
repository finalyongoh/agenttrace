from __future__ import annotations

from agenttrace.agents.analysis.criteria.agent_type_keywords import BANNED_ASSERTIVE_WORDS
from agenttrace.agents.analysis.state import AnalysisState


def quality_gate(state: AnalysisState) -> AnalysisState:
    errors: list[str] = []
    warnings: list[str] = []

    status = state.get("status", "COLLECTED")

    for claim in state.get("claims", []):
        if not claim.get("source"):
            errors.append(f"{claim.get('id', 'unknown claim')}에 source가 없습니다.")
        if not claim.get("claim_text"):
            errors.append(f"{claim.get('id', 'unknown claim')}에 claim_text가 없습니다.")

    evidence_signals = state.get("evidence_signals", [])
    linked_claim_ids: set[str] = set()
    for evidence in evidence_signals:
        if not evidence.get("path"):
            errors.append("EvidenceSignal에 path가 없습니다.")
        if evidence.get("claim_id"):
            linked_claim_ids.add(evidence["claim_id"])

    if status != "OUT_OF_SCOPE" and not state.get("followup_actions"):
        errors.append("OUT_OF_SCOPE이 아닌 분석에는 followup_actions가 필요합니다.")

    has_uncertainty_risk = any(
        risk.get("risk_type") == "ANALYSIS_UNCERTAIN"
        for risk in state.get("risk_signals", [])
    )
    final_status = "UNCERTAIN" if has_uncertainty_risk else status
    would_complete = final_status not in {"OUT_OF_SCOPE", "INSUFFICIENT_EVIDENCE", "UNCERTAIN"}

    missing_claim_evidence = [
        claim_id
        for claim_id in (claim.get("id") for claim in state.get("claims", []))
        if claim_id and claim_id not in linked_claim_ids
    ]

    if would_complete:
        if not evidence_signals:
            errors.append("COMPLETED 상태에는 하나 이상의 EvidenceSignal이 필요합니다.")

        for claim_id in missing_claim_evidence:
            errors.append(f"{claim_id}에 연결된 EvidenceSignal이 없습니다.")
    elif final_status == "UNCERTAIN":
        for claim_id in missing_claim_evidence:
            warnings.append(f"{claim_id}에 연결된 EvidenceSignal이 없습니다.")

    harness_relevance = state.get("harness_relevance", {})
    if (
        harness_relevance.get("level") == "high"
        and not harness_relevance.get("evidence")
    ):
        errors.append("harness_relevance cannot be high without harness evidence.")

    text_fields = [
        state.get("classification_reason", ""),
        "\n".join(action.get("reason", "") for action in state.get("followup_actions", [])),
        "\n".join(risk.get("summary", "") for risk in state.get("risk_signals", [])),
    ]
    for banned_word in BANNED_ASSERTIVE_WORDS:
        if any(banned_word in text for text in text_fields):
            errors.append(f"과장 또는 단정 표현이 포함되어 있습니다: {banned_word}")

    if state.get("agent_type") in {"UNKNOWN", None}:
        warnings.append("agent_type 분류가 불확실합니다.")

    if errors:
        return {
            "status": "NEEDS_HUMAN_REVIEW",
            "quality_errors": errors,
            "quality_warnings": warnings,
        }

    if final_status in {"OUT_OF_SCOPE", "INSUFFICIENT_EVIDENCE", "UNCERTAIN"}:
        return {
            "status": final_status,
            "quality_warnings": warnings,
        }

    return {
        "status": "COMPLETED",
        "quality_warnings": warnings,
    }
