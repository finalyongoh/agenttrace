from agenttrace.agents.analysis.schemas.repo_map import (
    SymbolTag,
    SymbolEdge,
    FileRank,
    DefinitionRank,
    RepoMapEntry,
)


def test_symbol_tag_definition():
    tag = SymbolTag(
        file_path="src/agent.py",
        symbol_name="Agent",
        symbol_kind="class",
        line_start=10,
        line_end=50,
        tag_kind="definition",
    )
    assert tag.file_path == "src/agent.py"
    assert tag.symbol_name == "Agent"
    assert tag.tag_kind == "definition"
    assert tag.line_end == 50


def test_symbol_tag_reference_without_line_end():
    tag = SymbolTag(
        file_path="src/agent.py",
        symbol_name="createAgent",
        symbol_kind="function",
        line_start=15,
        tag_kind="reference",
    )
    assert tag.line_end is None
    assert tag.tag_kind == "reference"


def test_symbol_edge():
    edge = SymbolEdge(
        source_file="src/api.py",
        target_file="src/service.py",
        symbol_name="createUser",
        reference_count=3,
        weight=10.0,
    )
    assert edge.source_file == "src/api.py"
    assert edge.reference_count == 3
    assert edge.weight == 10.0


def test_file_rank_with_default_reasons():
    rank = FileRank(
        file_path="src/agent.py",
        pagerank_score=0.85,
    )
    assert rank.pagerank_score == 0.85
    assert rank.personalization_reasons == []


def test_definition_rank_with_default_edges():
    rank = DefinitionRank(
        file_path="src/agent.py",
        symbol_name="Agent",
        score=0.92,
    )
    assert rank.score == 0.92
    assert rank.supporting_edges == []


def test_repo_map_entry_with_defaults():
    entry = RepoMapEntry(
        file_path="src/agent.py",
        selected_symbols=["Agent", "createAgent"],
    )
    assert entry.selected_symbols == ["Agent", "createAgent"]
    assert entry.rendered_context is None
    assert entry.selection_reason == []


def test_symbol_tag_model_dump():
    tag = SymbolTag(
        file_path="src/agent.py",
        symbol_name="Agent",
        symbol_kind="class",
        line_start=10,
        tag_kind="definition",
    )
    dumped = tag.model_dump()
    assert dumped["symbol_name"] == "Agent"
    assert dumped["tag_kind"] == "definition"
