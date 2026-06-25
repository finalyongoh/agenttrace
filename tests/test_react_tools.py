from agenttrace.agents.analysis.react_tools import create_react_tools
from pathlib import Path
import tempfile


def test_read_file_tool_returns_content(tmp_path):
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "agent.ts").write_text("export function createAgent() { return true; }")

    tools = create_react_tools(tmp_path, {}, [])
    read_file = tools[0]
    result = read_file.invoke({"file_path": "src/agent.ts"})
    assert "createAgent" in result


def test_read_file_tool_returns_error_for_missing_file(tmp_path):
    tools = create_react_tools(tmp_path, {}, [])
    read_file = tools[0]
    result = read_file.invoke({"file_path": "nonexistent.ts"})
    assert "not found" in result.lower() or "error" in result.lower()


def test_search_code_tool_finds_matches(tmp_path):
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "agent.ts").write_text("export function createAgent() {\n  tool.call();\n}")
    (tmp_path / "src" / "utils.ts").write_text("export function helper() { return 42; }")

    repo_map = {
        "files": {
            "src/agent.ts": {"definitions": ["createAgent"], "references": ["call"], "category": "source"},
            "src/utils.ts": {"definitions": ["helper"], "references": [], "category": "source"},
        }
    }
    tools = create_react_tools(tmp_path, repo_map, [])
    search_code = tools[1]
    result = search_code.invoke({"query": "createAgent"})
    assert "src/agent.ts" in result
    assert "createAgent" in result


def test_search_code_tool_searches_actual_source_without_symbol_match(tmp_path):
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "agent.ts").write_text(
        "export const runtime = { transport: 'stdio' };\n",
        encoding="utf-8",
    )

    repo_map = {
        "files": {
            "src/agent.ts": {"definitions": [], "references": [], "category": "source"},
        }
    }
    tools = create_react_tools(tmp_path, repo_map, [])
    search_code = tools[1]
    result = search_code.invoke({"query": "transport"})
    assert "src/agent.ts:1" in result
    assert "transport" in result


def test_search_code_tool_includes_evidence_shape(tmp_path):
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "agent.ts").write_text(
        "export function createAgent() { return true; }\n",
        encoding="utf-8",
    )

    repo_map = {"files": {"src/agent.ts": {"definitions": [], "references": [], "category": "source"}}}
    tools = create_react_tools(tmp_path, repo_map, [])
    search_code = tools[1]

    result = search_code.invoke({"query": "createAgent"})

    assert "content_hash=sha256:" in result
    assert "line_start=1" in result
    assert "line_end=1" in result
    assert "content_excerpt=" in result


def test_list_symbols_tool_returns_definitions(tmp_path):
    repo_map = {
        "files": {
            "src/agent.ts": {
                "definitions": ["Agent", "createAgent"],
                "references": ["tool", "call"],
                "category": "source",
            },
        }
    }
    tools = create_react_tools(tmp_path, repo_map, [])
    list_symbols = tools[2]
    result = list_symbols.invoke({"file_path": "src/agent.ts"})
    assert "Agent" in result
    assert "createAgent" in result
    assert "source" in result


def test_get_structure_map_tool_returns_overview(tmp_path):
    repo_map = {
        "files": {
            "src/agent.ts": {"definitions": ["Agent"], "references": [], "category": "source"},
            "Dockerfile": {"definitions": [], "references": [], "category": "critical_config"},
        },
        "definition_ranks": {"src/agent.ts::Agent": 0.9},
    }
    tools = create_react_tools(tmp_path, repo_map, [])
    get_structure_map = tools[3]
    result = get_structure_map.invoke({})
    assert "src/agent.ts" in result
    assert "Dockerfile" in result
    assert "Agent" in result


def test_read_file_truncates_large_files(tmp_path):
    (tmp_path / "large.ts").write_text("x" * 60000)
    tools = create_react_tools(tmp_path, {}, [])
    read_file = tools[0]
    result = read_file.invoke({"file_path": "large.ts"})
    assert "truncated" in result.lower()


def test_path_traversal_blocked(tmp_path):
    (tmp_path / "secret.txt").write_text("password123")
    tools = create_react_tools(tmp_path, {}, [])
    read_file = tools[0]
    result = read_file.invoke({"file_path": "../secret.txt"})
    assert "traversal" in result.lower() or "error" in result.lower()
