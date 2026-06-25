import json
from pathlib import Path

from agenttrace.agents.analysis.artifacts import (
    build_github_snapshot,
    run_snapshot_to_artifacts,
    write_analysis_artifact_bundle,
)


def test_write_analysis_artifact_bundle_writes_reviewable_files(tmp_path: Path):
    payload = {
        "analysis_id": "run-1",
        "analysis_result": {"analysis_status": "completed_with_limitations"},
        "analysis_report": {"body_markdown": "# Report\n\nBody"},
        "trace": {"analysis_version": "analysis-v2"},
    }
    manifest = {
        "repository_full_name": "owner/repo",
        "commit_sha": "abc123",
        "source_file_count": 1,
    }

    paths = write_analysis_artifact_bundle(tmp_path, payload, manifest)

    assert set(paths) == {
        "callback_payload",
        "report",
        "trace",
        "source_manifest",
    }
    assert json.loads((tmp_path / "callback_payload.json").read_text()) == payload
    assert (tmp_path / "report.md").read_text(encoding="utf-8") == "# Report\n\nBody"
    assert json.loads((tmp_path / "trace.json").read_text()) == payload["trace"]
    assert json.loads((tmp_path / "source_manifest.json").read_text()) == manifest


def test_run_snapshot_to_artifacts_invokes_graph_and_writes_bundle(tmp_path: Path):
    class FakeGraph:
        def invoke(self, state):
            assert state["preserve_local_repo_dir"] is True
            assert state["repository_snapshot"]["full_name"] == "owner/repo"
            return {
                "callback_payload": {
                    "analysis_id": "run-1",
                    "analysis_result": {"analysis_status": "completed_with_limitations"},
                    "analysis_report": {"body_markdown": "# Report"},
                    "trace": {
                        "input_manifest": {"source_file_count": 1},
                        "analysis_version": "analysis-v2",
                    },
                }
            }

    snapshot = {
        "full_name": "owner/repo",
        "github_url": "https://github.com/owner/repo",
        "commit_sha": "abc123",
    }

    paths = run_snapshot_to_artifacts(snapshot, tmp_path, graph=FakeGraph())

    assert paths["callback_payload"].exists()
    manifest = json.loads(paths["source_manifest"].read_text(encoding="utf-8"))
    assert manifest["repository_full_name"] == "owner/repo"
    assert manifest["commit_sha"] == "abc123"
    assert manifest["source_file_count"] == 1


def test_build_github_snapshot_uses_full_name_and_commit():
    snapshot = build_github_snapshot("upstash/context7", "abc123")

    assert snapshot["full_name"] == "upstash/context7"
    assert snapshot["github_url"] == "https://github.com/upstash/context7"
    assert snapshot["commit_sha"] == "abc123"
    assert snapshot["external_ingest"]["enabled"] is False
