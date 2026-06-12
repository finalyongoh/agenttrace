from __future__ import annotations

from fastapi import APIRouter

from agenttrace.config import get_settings

router = APIRouter(tags=["health"])


@router.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "service": get_settings().service_name}
