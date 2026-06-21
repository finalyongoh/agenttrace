from __future__ import annotations

import asyncio
import logging
from typing import Any

import httpx
from fastapi import APIRouter, BackgroundTasks, HTTPException, status
from pydantic import BaseModel, Field, UUID4

from agenttrace.agents.analysis.graph import build_graph
from agenttrace.agents.analysis.schemas.input import AnalysisInputRequest
from agenttrace.config import get_settings
from agenttrace.services.repo_ingest import (
    _github_full_name,
    fetch_repo_digest,
    repo_digest_to_summary_request,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/analysis", tags=["analysis"])
active_analyses = set()


class AnalysisRequest(BaseModel):
    analysis_id: UUID4
    repository: dict[str, Any] | None = None
    snapshot: dict[str, Any] | None = None
    readme_text: str | None = None
    file_tree: list[str] = Field(default_factory=list)
    summary_result: dict[str, Any] = Field(default_factory=dict)
    source_files: list[dict[str, Any]] = Field(default_factory=list)
    external_ingest: dict[str, Any] = Field(default_factory=lambda: {"enabled": False, "provider": "gitingest"})

    # Legacy Backend payload
    repository_id: UUID4 | None = None
    snapshot_id: UUID4 | None = None
    commit_sha: str | None = None
    github_url: str | None = None

    async def to_input_request(self) -> AnalysisInputRequest:
        if self.repository:
            return AnalysisInputRequest.model_validate(self.model_dump(mode="json", exclude_none=True))

        if not self.github_url:
            raise ValueError("github_url is required for legacy analysis requests")

        full_name = _github_full_name(self.github_url)
        digest = await asyncio.to_thread(fetch_repo_digest, full_name)
        summary_req = repo_digest_to_summary_request(digest, fallback_full_name=full_name)
        file_tree = [path.rstrip("/") for path in summary_req.shallow_file_tree if path.rstrip("/")]
        return AnalysisInputRequest.model_validate({
            "analysis_id": str(self.analysis_id),
            "repository": {
                "repository_id": str(self.repository_id) if self.repository_id else None,
                "full_name": summary_req.repository.full_name,
                "github_url": summary_req.repository.github_url or self.github_url,
                "description": summary_req.repository.description,
                "primary_language": summary_req.repository.primary_language,
                "topics": summary_req.repository.topics,
            },
            "snapshot": {
                "snapshot_id": str(self.snapshot_id) if self.snapshot_id else None,
                "commit_sha": self.commit_sha,
            },
            "readme_text": summary_req.readme_text,
            "file_tree": file_tree,
            "summary_result": {},
            "source_files": [],
            "external_ingest": {"enabled": False, "provider": "gitingest"},
        })


def _failure_payload(req: AnalysisRequest, exc: Exception) -> dict[str, Any]:
    return {
        "analysis_id": str(req.analysis_id),
        "status": "FAILED",
        "analysis_result": None,
        "result_json": {
            "agent_type": "UNKNOWN",
            "tech_stack_summary": {},
            "claims": [],
            "limitations": [],
            "missing_evidence": [],
            "followup_questions": [],
        },
        "error_message": str(exc),
    }


def _compat_result_json(analysis_result: dict[str, Any], input_req: AnalysisInputRequest) -> dict[str, Any]:
    agent_type_map = {
        "MCP": "MCP_SERVER",
        "Skill": "SKILL",
        "Eval": "EVAL_HARNESS",
        "ToolUse": "TOOL_USE",
        "Framework": "AGENT_FRAMEWORK",
        "Other": "OTHER",
        "Unknown": "UNKNOWN",
        None: "UNKNOWN",
    }
    evidence_by_id = {
        signal.get("signal_id"): signal
        for signal in analysis_result.get("evidence_signals", [])
    }
    verdict_by_claim = {}
    for task in analysis_result.get("evidence_task_results", []):
        for verdict in task.get("claim_verdicts", []):
            verdict_by_claim[verdict.get("claim_id")] = verdict

    claims = []
    for claim in analysis_result.get("analysis_claims", []):
        verdict = verdict_by_claim.get(claim.get("claim_id"), {})
        evidence_paths = [
            evidence_by_id.get(signal_id, {}).get("path")
            for signal_id in verdict.get("evidence_signal_ids", [])
        ]
        claims.append({
            "claim_text": claim.get("claim_text", ""),
            "evidence_status": verdict.get("verdict", "INSUFFICIENT_EVIDENCE"),
            "confidence_level": str(claim.get("confidence", 0.0)),
            "supporting_evidence": [path for path in evidence_paths if path],
            "limitation": "; ".join(verdict.get("limitations", [])) or None,
        })

    limitations = analysis_result.get("analysis_limitations", {})
    agent_type = agent_type_map.get(analysis_result.get("agent_type"), "UNKNOWN")
    if agent_type == "UNKNOWN":
        text = " ".join([
            input_req.repository.full_name,
            input_req.repository.description or "",
            " ".join(input_req.repository.topics),
            input_req.readme_text or "",
        ]).lower()
        if "harness" in text or "eval" in text or "benchmark" in text:
            agent_type = "EVAL_HARNESS"
        elif "mcp" in text:
            agent_type = "MCP_SERVER"
        elif "skill" in text:
            agent_type = "SKILL"

    return {
        "agent_type": agent_type,
        "tech_stack_summary": {
            "primary_language": input_req.repository.primary_language,
            "topics": input_req.repository.topics,
            "description": input_req.repository.description,
        },
        "claims": claims,
        "limitations": limitations.get("notes", []) + limitations.get("missing_inputs", []),
        "missing_evidence": [
            claim["claim_text"]
            for claim in claims
            if claim["evidence_status"] == "INSUFFICIENT_EVIDENCE"
        ],
        "followup_questions": [],
    }


async def run_pipeline_async(req: AnalysisRequest) -> None:
    try:
        logger.info("Starting async analysis pipeline for run_id=%s", req.analysis_id)
        input_req = await req.to_input_request()
        graph = build_graph()
        result = await asyncio.to_thread(
            graph.invoke,
            {
                "analysis_request": input_req.model_dump(mode="json"),
                "claims": [],
                "evidence_signals": [],
                "risk_signals": [],
                "quality_warnings": [],
                "quality_errors": [],
                "task_results": [],
                "task_traces": [],
            },
        )
        payload = result.get("callback_payload") or _failure_payload(req, RuntimeError("missing callback payload"))
        if payload.get("analysis_result") is not None:
            payload["result_json"] = _compat_result_json(payload["analysis_result"], input_req)

        settings = get_settings()
        await asyncio.to_thread(httpx.post, settings.agents_callback_url, json=payload, timeout=10.0)
        logger.info("Successfully completed analysis pipeline for run_id=%s", req.analysis_id)
    except Exception as exc:
        logger.error("Analysis pipeline failed for run_id=%s: %s", req.analysis_id, exc, exc_info=True)
        settings = get_settings()
        payload = _failure_payload(req, exc)
        try:
            await asyncio.to_thread(httpx.post, settings.agents_callback_url, json=payload, timeout=10.0)
        except Exception as callback_exc:
            logger.error("Failed to send failure callback: %s", callback_exc)
        raise
    finally:
        active_analyses.discard(str(req.analysis_id))


@router.post("", status_code=status.HTTP_202_ACCEPTED)
async def trigger_analysis(
    request: AnalysisRequest,
    background_tasks: BackgroundTasks,
) -> dict[str, str]:
    analysis_id_str = str(request.analysis_id)
    if analysis_id_str in active_analyses:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Analysis already in progress for this analysis_id.",
        )
    active_analyses.add(analysis_id_str)

    background_tasks.add_task(run_pipeline_async, request)
    return {"status": "queued", "message": "Analysis started asynchronously."}
