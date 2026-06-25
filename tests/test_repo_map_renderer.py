from agenttrace.agents.analysis.repo_map_renderer import render_repo_map, _count_tokens, _truncate_line


def test_render_empty_returns_empty():
    assert render_repo_map({}) == ""


def test_render_with_definition_ranks():
    definition_ranks = {
        "src/agent.py::Agent": 0.9,
        "src/agent.py::createAgent": 0.5,
        "src/utils.py::helper": 0.3,
    }
    rendered = render_repo_map(definition_ranks, max_tokens=1024)
    assert "src/agent.py" in rendered
    assert "Agent" in rendered


def test_render_special_files_first():
    definition_ranks = {"src/agent.py::Agent": 0.9}
    rendered = render_repo_map(
        definition_ranks,
        max_tokens=1024,
        special_files=["pyproject.toml", "Dockerfile"],
    )
    lines = rendered.splitlines()
    assert "pyproject.toml" in lines[0]
    assert "Dockerfile" in lines[1]


def test_render_respects_token_budget():
    definition_ranks = {f"src/file_{i}.py::symbol_{i}": 1.0 / (i + 1) for i in range(100)}
    rendered = render_repo_map(definition_ranks, max_tokens=100)
    assert _count_tokens(rendered) <= 120  # 15% 허용 오차


def test_truncate_line():
    long_line = "x" * 200
    truncated = _truncate_line(long_line)
    assert len(truncated) == 100
