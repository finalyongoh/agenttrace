from __future__ import annotations

from agenttrace.agents.analysis.state import AnalysisState
from agenttrace.logging_config import get_logger

logger = get_logger(__name__)



REQUIRED_KEYWORDS = {
    "agent", "mcp", "server", "client", "tool", "skill", "eval",
    "benchmark", "framework", "workflow", "plugin",
}


def _claim_tokens(claim_text: str) -> set[str]:
    return {
        token.strip(".,:;()[]{}").lower()
        for token in claim_text.split()
        if len(token.strip(".,:;()[]{}")) >= 3
    }


def _target_paths(claims: list[dict], file_tree: list[dict]) -> list[str]:
    tokens: set[str] = set()
    for claim in claims:
        tokens.update(_claim_tokens(claim.get("claim_text", "")))

    paths = [item.get("path", "") for item in file_tree if isinstance(item, dict)]
    matched = [
        path for path in paths
        if any(token in path.lower() for token in tokens)
    ]
    defaults = [path for path in paths if path.startswith(("src/", "lib/", "app/", "packages/"))]
    return list(dict.fromkeys([*matched, *defaults, *paths[:5]]))[:12]


def analysis_planner(state: AnalysisState) -> AnalysisState:
    run_id = state.get("run_id", "-")
    log = logger.bind(node="analysis_planner", run_id=run_id)
    log.info("시작")
    claims = list(state.get("claims", []))

    file_tree = list(state.get("file_tree", []))
    repository_id = state.get("metadata", {}).get("repository_id") or state.get("repository_id")

    required_claims = [
        claim for claim in claims
        if _claim_tokens(claim.get("claim_text", "")) & REQUIRED_KEYWORDS
    ]
    optional_claims = [claim for claim in claims if claim not in required_claims]

    tasks: list[dict] = []
    if required_claims:
        tasks.append({
            "task_id": "task-001",
            "claims": [claim["claim_id"] for claim in required_claims],
            "target_paths": _target_paths(required_claims, file_tree),
            "required": True,
            "status": "PENDING",
            "result": None,
        })
    if optional_claims:
        tasks.append({
            "task_id": f"task-{len(tasks) + 1:03d}",
            "claims": [claim["claim_id"] for claim in optional_claims],
            "target_paths": _target_paths(optional_claims, file_tree),
            "required": False,
            "status": "PENDING",
            "result": None,
        })

    plan = {
        "plan_id": "plan-001",
        "repository_id": repository_id,
        "tasks": tasks,
    }
    log.info("완료", tasks=len(tasks))
    return {"analysis_plan": plan, "evidence_tasks": tasks}

