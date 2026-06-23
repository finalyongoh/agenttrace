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


def test_critical_config_whitelist():
    from agenttrace.agents.analysis.github_provider import _is_critical_config

    # 패키지/빌드 매니페스트
    assert _is_critical_config("pyproject.toml") is True
    assert _is_critical_config("package.json") is True
    assert _is_critical_config("go.mod") is True
    assert _is_critical_config("Cargo.toml") is True
    assert _is_critical_config("requirements.txt") is True

    # 컨테이너/배포
    assert _is_critical_config("Dockerfile") is True
    assert _is_critical_config("docker-compose.yml") is True
    assert _is_critical_config("docker-compose.yaml") is True

    # CI/CD (.github/workflows 하위 yml/yaml)
    assert _is_critical_config(".github/workflows/ci.yml") is True
    assert _is_critical_config(".github/workflows/deploy.yaml") is True

    # API/DB 스키마
    assert _is_critical_config("openapi.yaml") is True
    assert _is_critical_config("schema.sql") is True

    # 프로젝트 설정
    assert _is_critical_config("tsconfig.json") is True
    assert _is_critical_config(".env.example") is True

    # 일반 소스 파일은 해당 안 됨
    assert _is_critical_config("src/main.py") is False
    assert _is_critical_config("README.md") is False
    assert _is_critical_config("docs/guide.md") is False


def test_select_blobs_guarantees_critical_configs():
    """파일 수가 MAX_FILES를 초과해도 중요 설정 파일은 항상 포함된다."""
    from agenttrace.agents.analysis.github_provider import MAX_FILES, _select_blobs

    # MAX_FILES개의 일반 소스 파일 + 설정 파일 여러 개
    blobs = [{"path": f"src/module_{i}.py", "size": 100} for i in range(MAX_FILES)]
    blobs += [
        {"path": "pyproject.toml", "size": 200},
        {"path": "Dockerfile", "size": 300},
        {"path": ".github/workflows/ci.yml", "size": 400},
    ]

    selected = _select_blobs(blobs)

    selected_paths = {b["path"] for b in selected}
    assert len(selected) <= MAX_FILES
    assert "pyproject.toml" in selected_paths
    assert "Dockerfile" in selected_paths
    assert ".github/workflows/ci.yml" in selected_paths


def test_select_blobs_no_truncation_when_under_limit():
    """파일 수가 MAX_FILES 이하이면 전부 포함된다."""
    from agenttrace.agents.analysis.github_provider import _select_blobs

    blobs = [
        {"path": "src/a.py", "size": 100},
        {"path": "README.md", "size": 50},
        {"path": "pyproject.toml", "size": 80},
    ]
    selected = _select_blobs(blobs)
    assert len(selected) == 3


