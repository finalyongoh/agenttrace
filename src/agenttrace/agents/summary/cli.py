from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Sequence

from pydantic import ValidationError

from agenttrace.agents.summary import (
    RepositorySummaryRequest,
    build_openai_summary_model,
)
from agenttrace.agents.summary.service import requires_llm_summary, summarize_repository
from agenttrace.config import configure_runtime_environment
from agenttrace.shared.errors import SummaryServiceError
from agenttrace.logging_config import setup_logging


def main(argv: Sequence[str] | None = None) -> None:
    setup_logging()
    parser = argparse.ArgumentParser(
        description="Run AgentTrace repository summary generation once."
    )
    parser.add_argument("input", help="Path to RepositorySummaryRequest JSON")
    parser.add_argument("--output", help="Output JSON path. Defaults to stdout.")
    args = parser.parse_args(argv)

    try:
        request = _load_request(Path(args.input))
    except (OSError, json.JSONDecodeError, ValidationError) as exc:
        parser.error(f"Invalid RepositorySummaryRequest JSON: {exc}")

    try:
        configure_runtime_environment()
        model = build_openai_summary_model() if requires_llm_summary(request) else None
        summary = summarize_repository(request, model=model)
    except SummaryServiceError as exc:
        print(f"Summary generation failed: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc

    output = json.dumps(summary.model_dump(mode="json"), ensure_ascii=False, indent=2)
    if args.output:
        output_path = Path(args.output)
        try:
            output_path.parent.mkdir(parents=True, exist_ok=True)
            output_path.write_text(output + "\n", encoding="utf-8")
        except OSError as exc:
            print(f"Failed to write summary output: {exc}", file=sys.stderr)
            raise SystemExit(1) from exc
        return

    print(output)


def _load_request(path: Path) -> RepositorySummaryRequest:
    payload = json.loads(path.read_text(encoding="utf-8"))
    return RepositorySummaryRequest.model_validate(payload)


if __name__ == "__main__":
    main()
