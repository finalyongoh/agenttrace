from __future__ import annotations

from agenttrace.agents.analysis.schemas.result import AnalysisResult
from agenttrace.agents.analysis.state import AnalysisState


def finalize_analysis(state: AnalysisState) -> AnalysisState:
    synthesis = state.get("synthesis", {})
    
    # Map claim_id to evidence_signal_ids from task results
    claim_signals = {}
    for task_res in state.get("task_results", []):
        for verdict in task_res.get("claim_verdicts", []):
            cid = verdict.get("claim_id")
            sids = verdict.get("evidence_signal_ids", [])
            if cid and sids:
                if cid not in claim_signals:
                    claim_signals[cid] = []
                for sid in sids:
                    if sid not in claim_signals[cid]:
                        claim_signals[cid].append(sid)
                        
    updated_claims = []
    for claim in state.get("claims", []):
        cid = claim.get("claim_id") or claim.get("id")
        claim_copy = dict(claim)
        if cid in claim_signals:
            claim_copy["evidence_signal_ids"] = claim_signals[cid]
        updated_claims.append(claim_copy)

    result = AnalysisResult.model_validate({
        "analysis_status": synthesis.get("analysis_status", "insufficient_evidence"),
        "agent_type": synthesis.get("agent_type", "Unknown"),
        "tech_stack_summary": synthesis.get("tech_stack_summary"),
        "analysis_claims": updated_claims,
        "evidence_signals": state.get("evidence_signals", []),
        "evidence_task_results": state.get("task_results", []),
        "risk_signals": state.get("risk_signals", []),
        "follow_up_guide": state.get("follow_up_guide") or {
            "ko": "README와 근거 경로를 순서대로 확인하세요.",
            "en": "Review the README and evidence paths in order.",
        },
        "analysis_limitations": state.get("analysis_limitations") or {
            "missing_inputs": [],
            "truncated_inputs": [],
            "notes": [],
        },
    })
    return {"final_result": result.model_dump()}
