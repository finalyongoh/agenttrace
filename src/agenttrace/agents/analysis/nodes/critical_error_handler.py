from __future__ import annotations

from agenttrace.agents.analysis.state import AnalysisState


def critical_error_handler(state: AnalysisState) -> AnalysisState:
    errors = state.get("quality_gate_result", {}).get("critical_errors") or []
    if not errors and state.get("error_message"):
        errors = [state["error_message"]]
    message = "; ".join(errors) if errors else "Analysis failed."

    import shutil
    from pathlib import Path
    local_repo_dir_str = state.get("local_repo_dir")
    if local_repo_dir_str:
        local_repo_dir = Path(local_repo_dir_str)
        if local_repo_dir.exists():
            shutil.rmtree(local_repo_dir, ignore_errors=True)

    return {
        "status": "FAILED",
        "error_message": message,
        "callback_payload": {
            "analysis_id": state.get("run_id"),
            "status": "FAILED",
            "analysis_result": None,
            "error_message": message,
        },
    }
