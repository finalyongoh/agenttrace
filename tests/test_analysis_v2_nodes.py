from agenttrace.agents.analysis.nodes.analysis_precheck import analysis_precheck
from agenttrace.agents.analysis.nodes.analysis_planner import analysis_planner
from agenttrace.agents.analysis.nodes.claim_analyzer import claim_analyzer
from agenttrace.agents.analysis.nodes.content_preprocessor import content_preprocessor


def test_content_preprocessor_builds_chunks_from_source_files():
    state = {
        "source_files": [{"path": "src/server.py", "content": "def register_tool(): pass"}],
        "missing_inputs": [],
    }

    result = content_preprocessor(state)

    assert result["content_chunks"]
    assert result["chunk_index"]["entries"][0]["file_path"] == "src/server.py"


def test_analysis_precheck_allows_limited_readme_file_tree_analysis():
    state = {
        "readme": "# Repo\nProvides MCP tools.",
        "file_tree": [{"path": "src/server.py"}],
        "missing_inputs": ["source_files"],
        "content_chunks": [],
    }

    result = analysis_precheck(state)

    assert result["precheck_result"]["can_analyze"] is True
    assert result["analysis_mode"] == "limited"
    assert "source_files" in result["analysis_limitations"]["missing_inputs"]


def test_claim_analyzer_extracts_readme_claims_without_summary_regeneration():
    result = claim_analyzer(
        {"readme": "# Repo\nProvides an MCP server.\nSupports tool registration."}
    )

    assert [claim["claim_id"] for claim in result["claims"]] == ["claim-1", "claim-2"]
    assert "MCP server" in result["claims"][0]["claim_text"]


def test_analysis_planner_groups_claims_into_required_tasks():
    result = analysis_planner(
        {
            "metadata": {"repository_id": "repo-1"},
            "claims": [
                {"claim_id": "claim-1", "claim_text": "Provides an MCP server.", "source_path": "README.md"},
                {"claim_id": "claim-2", "claim_text": "Supports tool registration.", "source_path": "README.md"},
            ],
            "file_tree": [{"path": "src/server.py"}, {"path": "README.md"}],
        }
    )

    task = result["analysis_plan"]["tasks"][0]
    assert task["required"] is True
    assert task["status"] == "PENDING"
    assert "claim-1" in task["claims"]
