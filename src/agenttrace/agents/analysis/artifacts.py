from __future__ import annotations

import json
import argparse
from pathlib import Path
from typing import Any
from uuid import uuid4


def write_analysis_artifact_bundle(
    output_dir: Path,
    callback_payload: dict[str, Any],
    source_manifest: dict[str, Any],
) -> dict[str, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)

    paths = {
        "callback_payload": output_dir / "callback_payload.json",
        "report": output_dir / "report.md",
        "trace": output_dir / "trace.json",
        "source_manifest": output_dir / "source_manifest.json",
    }

    paths["callback_payload"].write_text(
        json.dumps(callback_payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    paths["report"].write_text(
        callback_payload.get("analysis_report", {}).get("body_markdown", ""),
        encoding="utf-8",
    )
    paths["trace"].write_text(
        json.dumps(callback_payload.get("trace", {}), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    paths["source_manifest"].write_text(
        json.dumps(source_manifest, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return paths


def build_github_snapshot(full_name: str, commit_sha: str = "HEAD") -> dict[str, Any]:
    return {
        "repository_id": full_name,
        "full_name": full_name,
        "github_url": f"https://github.com/{full_name}",
        "commit_sha": commit_sha,
        "external_ingest": {"enabled": False, "provider": "gitingest"},
    }


def run_snapshot_to_artifacts(
    snapshot: dict[str, Any],
    output_dir: Path,
    *,
    graph: Any | None = None,
) -> dict[str, Path]:
    if graph is None:
        from agenttrace.agents.analysis.graph import build_graph

        graph = build_graph()

    output_dir.mkdir(parents=True, exist_ok=True)
    result = graph.invoke(
        {
            "run_id": str(uuid4()),
            "trigger": "NEW_REPO",
            "repository_snapshot": snapshot,
            "output_path": str(output_dir / "callback_payload.json"),
            "preserve_local_repo_dir": True,
            "evidence_signals": [],
            "risk_signals": [],
            "quality_warnings": [],
            "quality_errors": [],
            "retry_count": 0,
        }
    )
    payload = result["callback_payload"]
    trace = payload.get("trace", {})
    input_manifest = trace.get("input_manifest", {})
    manifest = {
        "repository_full_name": snapshot.get("full_name") or input_manifest.get("repository_full_name"),
        "github_url": snapshot.get("github_url"),
        "commit_sha": snapshot.get("commit_sha") or "HEAD",
        "source_file_count": input_manifest.get("source_file_count", 0),
        "source_provider": input_manifest.get("source_provider"),
        "missing_inputs": trace.get("analysis_limitations", {}).get("missing_inputs", []),
        "deferred_file_paths": input_manifest.get("deferred_file_paths", []),
    }
    return write_analysis_artifact_bundle(output_dir, payload, manifest)


def main() -> None:
    parser = argparse.ArgumentParser(description="Run analysis and write local review artifacts.")
    parser.add_argument("full_name", help="GitHub repository full name, e.g. upstash/context7")
    parser.add_argument("--commit", default="HEAD", help="Commit SHA or ref to analyze")
    parser.add_argument("--out", required=True, help="Artifact output directory")
    args = parser.parse_args()

    snapshot = build_github_snapshot(args.full_name, args.commit)
    paths = run_snapshot_to_artifacts(snapshot, Path(args.out))
    for name, path in paths.items():
        print(f"{name}: {path}")


if __name__ == "__main__":
    main()
