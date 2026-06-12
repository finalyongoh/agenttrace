from __future__ import annotations

from typing import Any

from agenttrace.config import get_settings
from agenttrace.shared.errors import MissingSummaryModelError


def build_openai_summary_model() -> Any:
    settings = get_settings()

    if not settings.openai_api_key:
        raise MissingSummaryModelError("OPENAI_API_KEY is required for summary generation.")

    try:
        from langchain_openai import ChatOpenAI
    except ImportError as exc:
        raise MissingSummaryModelError(
            "langchain-openai is required for OpenAI summary generation."
        ) from exc

    kwargs = {
        "model": settings.summary_model,
        "api_key": settings.openai_api_key,
        "temperature": 0,
    }
    if settings.openai_api_base:
        kwargs["base_url"] = settings.openai_api_base

    return ChatOpenAI(**kwargs)
