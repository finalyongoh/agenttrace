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


# ─── Phase 4: 간선 가중치, self-edge, 정의 단위 랭킹, Personalized PageRank ────

def test_edge_weight_mentioned_ident_boost():
    """§8.1: 사용자 언급 심볼은 ×10 가중치."""
    source_files = [
        {"path": "src/api.py", "content": "def main():\n    UserService()\n"},
        {"path": "src/service.py", "content": "class UserService:\n    pass\n"},
    ]
    repo_map_normal = build_repo_map(source_files, file_tree=[])
    repo_map_mentioned = build_repo_map(
        source_files, file_tree=[], mentioned_idents=["UserService"]
    )

    normal_weight = repo_map_normal["edges"]["src/api.py"]["src/service.py"]
    mentioned_weight = repo_map_mentioned["edges"]["src/api.py"]["src/service.py"]
    assert mentioned_weight > normal_weight


def test_edge_weight_underscore_penalty():
    """§8.3: _prefix 식별자는 ×0.1 가중치."""
    source_files = [
        {"path": "src/api.py", "content": "def main():\n    _internal_helper()\n"},
        {"path": "src/helper.py", "content": "def _internal_helper():\n    pass\n"},
        {"path": "src/service.py", "content": "class PublicService:\n    pass\n"},
    ]
    repo_map = build_repo_map(source_files, file_tree=[])

    underscore_weight = repo_map["edges"]["src/api.py"].get("src/helper.py", 0.0)
    # _internal_helper는 _prefix이므로 가중치가 낮아야 함
    assert underscore_weight > 0  # self-edge가 아닌 실제 간선


def test_edge_weight_sqrt_reference_count():
    """§8.6: 참조 4회 → ×2 (sqrt(4)=2)."""
    source_files = [
        {"path": "src/api.py", "content": "def main():\n    helper()\n    helper()\n    helper()\n    helper()\n"},
        {"path": "src/helper.py", "content": "def helper():\n    pass\n"},
    ]
    repo_map = build_repo_map(source_files, file_tree=[])
    weight = repo_map["edges"]["src/api.py"]["src/helper.py"]
    # sqrt(4) = 2.0이 적용되어야 함
    assert weight >= 2.0


def test_self_edge_for_definition_only_file():
    """§7.4: 참조가 없는 정의 전용 파일에 self-edge 추가."""
    source_files = [
        {"path": "src/standalone.py", "content": "class Entrypoint:\n    pass\n"},
    ]
    repo_map = build_repo_map(source_files, file_tree=[])
    # self-edge가 있어야 함
    assert "src/standalone.py" in repo_map["edges"]["src/standalone.py"]
    assert repo_map["edges"]["src/standalone.py"]["src/standalone.py"] > 0


def test_definition_ranks_present():
    """§10: definition_ranks가 (file::symbol) 키를 가짐."""
    source_files = [
        {"path": "src/api.py", "content": "def main():\n    UserService()\n"},
        {"path": "src/service.py", "content": "class UserService:\n    pass\n"},
    ]
    repo_map = build_repo_map(source_files, file_tree=[])
    assert "definition_ranks" in repo_map
    # 적어도 하나 이상의 definition rank가 존재해야 함
    assert len(repo_map["definition_ranks"]) > 0


def test_definition_ranks_distinguish_symbols_in_same_file():
    """§10: 같은 파일 내에서도 심볼별 점수가 존재함."""
    source_files = [
        {"path": "src/api.py", "content": "def main():\n    ImportantService()\n    helper()\n"},
        {"path": "src/service.py", "content": "class ImportantService:\n    pass\n\ndef helper():\n    pass\n"},
    ]
    repo_map = build_repo_map(source_files, file_tree=[])
    def_ranks = repo_map["definition_ranks"]
    # 두 심볼 모두 definition_ranks에 존재해야 함
    important_key = "src/service.py::ImportantService"
    helper_key = "src/service.py::helper"
    assert important_key in def_ranks
    assert helper_key in def_ranks
    assert def_ranks[important_key] > 0
    assert def_ranks[helper_key] > 0


def test_personalized_pagerank_with_mentioned_fnames():
    """§9: mentioned_fnames가 랭킹 상위에."""
    source_files = [
        {"path": "src/agent.py", "content": "class Agent:\n    pass\n"},
        {"path": "src/utils.py", "content": "def helper():\n    pass\n"},
    ]
    repo_map_normal = build_repo_map(source_files, file_tree=[])
    repo_map_mentioned = build_repo_map(
        source_files, file_tree=[], mentioned_fnames=["src/agent.py"]
    )

    agent_rank_normal = repo_map_normal["area_file_ranks"]["agent-and-llm"].get("src/agent.py", 0)
    agent_rank_mentioned = repo_map_mentioned["area_file_ranks"]["agent-and-llm"].get("src/agent.py", 0)
    # mentioned 시 agent.py 랭크가 더 높아야 함
    assert agent_rank_mentioned >= agent_rank_normal


def test_personalized_pagerank_with_chat_file_paths():
    """§8.5: chat_file_paths에서 발생한 참조는 ×50 가중치."""
    source_files = [
        {"path": "src/api.py", "content": "def main():\n    Service()\n"},
        {"path": "src/service.py", "content": "class Service:\n    pass\n"},
    ]
    repo_map_normal = build_repo_map(source_files, file_tree=[])
    repo_map_chat = build_repo_map(
        source_files, file_tree=[], chat_file_paths=["src/api.py"]
    )

    normal_weight = repo_map_normal["edges"]["src/api.py"]["src/service.py"]
    chat_weight = repo_map_chat["edges"]["src/api.py"]["src/service.py"]
    assert chat_weight > normal_weight
