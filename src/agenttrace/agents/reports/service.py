from __future__ import annotations

from datetime import datetime, timezone
from importlib import resources
from typing import Any

from langchain_core.prompts import ChatPromptTemplate

from agenttrace.agents.reports.schemas import TrendReport, TrendReportRequest
from agenttrace.config import get_settings

REPORT_PROMPT_VERSION = "weekly-trend-report@1.3.0"


def generate_trend_report(request: TrendReportRequest, *, model: Any) -> TrendReport:
    prompt = ChatPromptTemplate.from_messages(
        [
            ("system", _load_prompt()),
            (
                "human",
                "{period_start}부터 {period_end}까지의 주간 리포트를 작성하세요. "
                "모든 사용자용 본문은 한국어로 작성하세요.\n"
                "저장소 지표:\n{repositories}",
            ),
        ]
    ).invoke(
        {
            "period_start": request.period_start,
            "period_end": request.period_end,
            "repositories": request.model_dump_json(indent=2),
        }
    )
    result = model.with_structured_output(TrendReport).invoke(prompt)
    allowed_ids = {repository.repository_id for repository in request.repositories}
    result.featured_repositories = [
        repository
        for repository in result.featured_repositories
        if repository.repository_id in allowed_ids
    ]
    result.generated_at = datetime.now(timezone.utc).isoformat()
    result.model_name = get_settings().summary_model
    result.prompt_version = REPORT_PROMPT_VERSION
    if len(request.repositories) < 3:
        result.limitations.append("폭넓은 추세를 판단하기에는 사용 가능한 저장소 이력이 부족합니다.")
    return result


def _load_prompt() -> str:
    return (
        resources.files("agenttrace.agents.reports")
        .joinpath("prompt.md")
        .read_text(encoding="utf-8")
    )
