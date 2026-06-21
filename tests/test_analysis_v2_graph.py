from uuid import uuid4

from agenttrace.agents.analysis.graph import build_graph


def test_analysis_v2_graph_limited_path_completes_with_insufficient_evidence():
    graph = build_graph()
    result = graph.invoke(
        {
            "analysis_request": {
                "analysis_id": str(uuid4()),
                "repository": {"full_name": "owner/repo", "github_url": "https://github.com/owner/repo"},
                "snapshot": {"snapshot_id": "snap-1"},
                "readme_text": "# Repo\nProvides an MCP server.",
                "file_tree": ["README.md", "src/server.py"],
                "external_ingest": {"enabled": False, "provider": "gitingest"},
            },
            "claims": [],
            "evidence_signals": [],
            "risk_signals": [],
            "quality_warnings": [],
            "quality_errors": [],
            "task_results": [],
            "task_traces": [],
        }
    )

    assert result["final_result"]["analysis_status"] in {"insufficient_evidence", "completed_with_limitations"}
    assert result["callback_payload"]["analysis_result"]["analysis_limitations"]["missing_inputs"]
