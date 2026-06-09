from __future__ import annotations

import json
from pathlib import Path


def test_analysis_graph_is_exported_from_new_package():
    from agenttrace.agents.analysis.graph import graph

    assert graph is not None


def test_langgraph_json_registers_analysis_graph():
    config_path = Path(__file__).resolve().parents[1] / "langgraph.json"

    config = json.loads(config_path.read_text())

    assert config["dependencies"] == ["."]
    assert (
        config["graphs"]["analysis"]
        == "./src/agenttrace/agents/analysis/graph.py:graph"
    )
