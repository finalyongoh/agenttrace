from __future__ import annotations

import asyncio
from typing import Any

from fastapi import APIRouter, BackgroundTasks, HTTPException, status
from pydantic import BaseModel, UUID4

router = APIRouter(prefix="/api/v1/analysis", tags=["analysis"])
active_analyses = set()


class AnalysisRequest(BaseModel):
    analysis_id: UUID4
    repository_id: UUID4
    snapshot_id: UUID4
    commit_sha: str
    github_url: str


async def run_pipeline_async(req: AnalysisRequest) -> None:
    try:
        # Placeholder for graph execution. We will integrate actual LangGraph logic in Task 4/5.
        await asyncio.sleep(0.5)
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
