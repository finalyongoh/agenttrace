from __future__ import annotations

from agenttrace.agents.analysis.state import AnalysisState


def select_next_task(state: AnalysisState) -> AnalysisState:
    completed = {result.get("task_id") for result in state.get("task_results", [])}
    for task in state.get("analysis_plan", {}).get("tasks", []):
        if task.get("task_id") not in completed:
            return {
                "current_task_id": task["task_id"],
                "next_task_id": task["task_id"],
            }
    return {
        "current_task_id": "",
        "next_task_id": "",
    }
