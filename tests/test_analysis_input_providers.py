import pytest

from agenttrace.agents.analysis.input_providers import (
    AnalysisInputAssembler,
    GitingestInputProvider,
    ProvidedInputProvider,
)
from agenttrace.agents.analysis.schemas.input import AnalysisInputRequest


def _request(source_files=None, external_enabled=False):
    return AnalysisInputRequest.model_validate(
        {
            "analysis_id": "00000000-0000-0000-0000-000000000001",
            "repository": {
                "full_name": "owner/repo",
                "github_url": "https://github.com/owner/repo",
            },
            "snapshot": {"snapshot_id": "snap-1"},
            "readme_text": "# Repo",
            "file_tree": ["README.md", "src/server.py"],
            "source_files": source_files or [],
            "external_ingest": {"enabled": external_enabled, "provider": "gitingest"},
        }
    )


def test_assembler_prefers_provided_source_files():
    req = _request(
        source_files=[{"path": "src/server.py", "content": "print('x')"}],
        external_enabled=True,
    )
    assembled = AnalysisInputAssembler(
        ProvidedInputProvider(),
        GitingestInputProvider(fetch_text=lambda _: pytest.fail("not called")),
    ).assemble(req)

    assert assembled.analysis_mode == "normal"
    assert assembled.source_files[0].path == "src/server.py"


def test_assembler_records_limited_mode_when_gitingest_fails():
    req = _request(external_enabled=True)
    assembled = AnalysisInputAssembler(
        ProvidedInputProvider(),
        GitingestInputProvider(
            fetch_text=lambda _: (_ for _ in ()).throw(RuntimeError("boom"))
        ),
    ).assemble(req)

    assert assembled.analysis_mode == "limited"
    assert "gitingest_file_content" in assembled.missing_inputs
    assert assembled.input_manifest["external_ingest_error"] == "boom"


def test_file_path_scoring():
    from agenttrace.agents.analysis.github_provider import _score_file_path

    # Business logic paths get a high weight
    assert _score_file_path("src/core/agent.py") == 100
    assert _score_file_path("lib/utils.ts") == 100
    # Docs get negative points
    assert _score_file_path("README.md") == -50
    assert _score_file_path("docs/index.mdx") == -50
    # Configuration files get a slight penalty
    assert _score_file_path("package.json") == -20
    # Normal files default to 0
    assert _score_file_path("config.py") == 0

