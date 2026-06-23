from agenttrace.agents.analysis.repo_map import build_repo_map
from agenttrace.agents.analysis.nodes.build_repo_map import build_repo_map_node


def test_build_repo_map_extracts_symbols_and_ranks_agent_file():
    source_files = [
        {
            "path": "packages/tools-ai-sdk/src/agents/context7.ts",
            "content": "export function createContext7Agent() { return callTool(); }\nfunction callTool() {}\n",
        },
        {
            "path": "packages/web/src/theme.ts",
            "content": "export const colors = { primary: 'blue' };\n",
        },
    ]

    repo_map = build_repo_map(source_files, file_tree=[])

    agent_path = "packages/tools-ai-sdk/src/agents/context7.ts"
    theme_path = "packages/web/src/theme.ts"
    assert agent_path in repo_map["files"]
    assert "createContext7Agent" in repo_map["files"][agent_path]["definitions"]
    assert (
        repo_map["area_file_ranks"]["agent-and-llm"][agent_path]
        > repo_map["area_file_ranks"]["agent-and-llm"].get(theme_path, 0)
    )


def test_build_repo_map_node_adds_repo_map_to_state():
    state = {
        "run_id": "run-1",
        "source_files": [
            {"path": "src/agent.ts", "content": "export function createAgent() { return tool(); }"},
        ],
        "file_tree": [{"path": "src/agent.ts"}],
    }

    result = build_repo_map_node(state)

    assert "repo_map" in result
    assert result["repo_map"]["files"]["src/agent.ts"]["definitions"] == ["createAgent"]


def test_build_repo_map_node_reads_local_files_when_state_content_is_stripped(tmp_path):
    repo_dir = tmp_path / "repo"
    (repo_dir / "src").mkdir(parents=True)
    (repo_dir / "src" / "index.ts").write_text("import './agent';\n", encoding="utf-8")
    (repo_dir / "src" / "agent.ts").write_text(
        "export function createAgent() { return true; }\n",
        encoding="utf-8",
    )
    state = {
        "run_id": "run-1",
        "local_repo_dir": str(repo_dir),
        "source_files": [
            {"path": "src/index.ts", "content": ""},
            {"path": "src/agent.ts", "content": ""},
        ],
        "file_tree": [{"path": "src/index.ts"}, {"path": "src/agent.ts"}],
    }

    result = build_repo_map_node(state)

    assert result["repo_map"]["files"]["src/agent.ts"]["definitions"] == ["createAgent"]
    assert result["repo_map"]["edges"]["src/index.ts"]["src/agent.ts"] > 0


def test_build_repo_map_adds_relative_import_edges():
    source_files = [
        {
            "path": "src/index.ts",
            "content": "import './agent';\nexport function main() { return true; }\n",
        },
        {
            "path": "src/agent.ts",
            "content": "export function createAgent() { return true; }\n",
        },
    ]

    repo_map = build_repo_map(source_files, file_tree=[])

    assert repo_map["edges"]["src/index.ts"]["src/agent.ts"] > 0
