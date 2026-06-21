from __future__ import annotations

from agenttrace.agents.analysis.state import AnalysisState


AGENT_TYPE_MAP = {
    "MCP_SERVER": "MCP",
    "MCP_CLIENT": "MCP",
    "SKILL": "Skill",
    "EVAL_HARNESS": "Eval",
    "TOOL_USE": "ToolUse",
    "AGENT_FRAMEWORK": "Framework",
    "OTHER": "Other",
    "UNKNOWN": "Unknown",
}


def repository_synthesizer(state: AnalysisState) -> AnalysisState:
    tasks = state.get("analysis_plan", {}).get("tasks", [])
    results_by_id = {
        result.get("task_id"): result
        for result in state.get("task_results", [])
    }
    required_tasks = [task for task in tasks if task.get("required")]
    required_results = [results_by_id.get(task.get("task_id")) for task in required_tasks]

    if required_tasks and any(not result for result in required_results):
        analysis_status = "insufficient_evidence"
    elif any(result and result.get("status") == "INSUFFICIENT_EVIDENCE" for result in required_results):
        analysis_status = "insufficient_evidence"
    elif any(result.get("status") == "INSUFFICIENT_EVIDENCE" for result in state.get("task_results", [])):
        analysis_status = "completed_with_limitations"
    elif not state.get("claims"):
        analysis_status = "uncertain_classification"
    else:
        analysis_status = "completed"

    metadata = state.get("metadata", {}) or {}
    primary_language = metadata.get("primary_language") or metadata.get("language") or "Unknown"
    agent_type = AGENT_TYPE_MAP.get(str(state.get("agent_type", "Unknown")), state.get("agent_type") or "Unknown")
    if agent_type in {None, "Unknown"}:
        agent_type = _infer_agent_type(state)
    if agent_type not in {"MCP", "Skill", "Eval", "ToolUse", "Framework", "Other", "Unknown"}:
        agent_type = "Unknown"

    return {
        "synthesis": {
            "analysis_status": analysis_status,
            "agent_type": agent_type,
            "tech_stack_summary": {
                "ko": f"{primary_language} 기반 정적 신호가 확인됩니다.",
                "en": f"Static signals indicate a {primary_language}-based project.",
            },
        }
    }


def _infer_agent_type(state: AnalysisState) -> str:
    metadata = state.get("metadata", {}) or {}
    text = " ".join([
        str(metadata.get("description", "")),
        " ".join(metadata.get("topics", []) or []),
        state.get("readme", ""),
        " ".join(item.get("path", "") for item in state.get("file_tree", [])),
    ]).lower()
    if "mcp" in text:
        return "MCP"
    if "skill" in text:
        return "Skill"
    if "eval" in text or "benchmark" in text or "harness" in text:
        return "Eval"
    if "tool" in text:
        return "ToolUse"
    if "agent" in text or "workflow" in text:
        return "Framework"
    return "Unknown"
