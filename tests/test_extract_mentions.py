from agenttrace.agents.analysis.nodes.extract_mentions import extract_mentions


def test_extract_idents_from_user_message():
    state = {
        "run_id": "run-1",
        "analysis_request": {"user_message": "Analyze the Agent class and createAgent function"},
        "file_tree": [],
    }
    result = extract_mentions(state)
    assert "Agent" in result["mentioned_idents"]
    assert "createAgent" in result["mentioned_idents"]


def test_extract_fnames_filtered_by_file_tree():
    state = {
        "run_id": "run-1",
        "analysis_request": {"user_message": "Check src/agent.py and src/utils.py"},
        "file_tree": [{"path": "src/agent.py"}, {"path": "src/main.py"}],
    }
    result = extract_mentions(state)
    assert "src/agent.py" in result["mentioned_fnames"]
    # file_tree에 없는 파일은 제외
    assert "src/utils.py" not in result["mentioned_fnames"]


def test_empty_message_returns_empty_lists():
    state = {
        "run_id": "run-1",
        "analysis_request": {"user_message": ""},
        "file_tree": [],
    }
    result = extract_mentions(state)
    assert result["mentioned_idents"] == []
    assert result["mentioned_fnames"] == []


def test_falls_back_to_readme_when_no_user_message():
    state = {
        "run_id": "run-1",
        "analysis_request": {},
        "readme": "This project provides an MCP server with tool registration.",
        "file_tree": [],
    }
    result = extract_mentions(state)
    assert "MCP" in result["mentioned_idents"]
    assert "tool" in result["mentioned_idents"]
