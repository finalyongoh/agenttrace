from pathlib import Path

from agenttrace.agents.analysis.gitingest import (
    build_gitingest_url,
    parse_gitingest_output,
)


def test_parse_gitingest_output_extracts_source_files():
    raw = Path("tests/fixtures/gitingest_superpowers.txt").read_text()
    files = parse_gitingest_output(raw)

    assert [f.path for f in files] == ["README.md", "pyproject.toml", "src/server.py"]
    assert "register_tool" in files[2].content
    assert files[2].content_hash.startswith("sha256:")


def test_parse_gitingest_output_includes_empty_files():
    raw = """Repository: owner/repo

Files:
empty.py

================================================
FILE: empty.py
================================================
"""

    files = parse_gitingest_output(raw)

    assert len(files) == 1
    assert files[0].path == "empty.py"
    assert files[0].content == ""
    assert files[0].content_hash.startswith("sha256:")


def test_build_gitingest_url_uses_repository_path_form():
    assert (
        build_gitingest_url("https://github.com/owner/repo/")
        == "https://gitingest.com/owner/repo"
    )
    assert (
        build_gitingest_url(
            "https://github.com/owner/repo/",
            base_url="https://gitingest.example/base/",
        )
        == "https://gitingest.example/base/owner/repo"
    )
