from agenttrace.agents.analysis.state import AnalysisState


def test_new_repo_map_fields_are_optional():
    state: AnalysisState = {}
    assert state.get("mentioned_fnames") is None
    assert state.get("mentioned_idents") is None
    assert state.get("chat_file_paths") is None
    assert state.get("definition_ranks") is None
    assert state.get("symbol_tags") is None
    assert state.get("repo_map_render") is None
    assert state.get("deferred_file_paths") is None


def test_new_fields_accept_expected_types():
    state: AnalysisState = {
        "mentioned_fnames": ["src/agent.py"],
        "mentioned_idents": ["Agent", "createAgent"],
        "chat_file_paths": ["src/agent.py"],
        "definition_ranks": {"src/agent.py::Agent": 0.9},
        "symbol_tags": [{"file_path": "src/agent.py", "symbol_name": "Agent"}],
        "repo_map_render": "src/agent.py:\n  class Agent",
        "deferred_file_paths": ["src/utils.py", "src/helpers.ts"],
    }
    assert state["mentioned_fnames"] == ["src/agent.py"]
    assert state["mentioned_idents"] == ["Agent", "createAgent"]
    assert state["chat_file_paths"] == ["src/agent.py"]
    assert "src/agent.py::Agent" in state["definition_ranks"]
    assert state["symbol_tags"][0]["symbol_name"] == "Agent"
    assert "class Agent" in state["repo_map_render"]
    assert len(state["deferred_file_paths"]) == 2
