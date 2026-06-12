from __future__ import annotations

from collections.abc import Callable
from typing import Any

from agenttrace.models import build_openai_summary_model


def get_summary_model_factory() -> Callable[[], Any]:
    return build_openai_summary_model
