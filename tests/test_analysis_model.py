import sys
import types
import pytest
from fastapi import HTTPException
from agenttrace.config import get_settings
from agenttrace.models import build_openai_analysis_model
from agenttrace.shared.errors import MissingAnalysisModelError
from agenttrace.app.errors import summary_service_exception_to_http


def test_analysis_model_settings_defaults(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("AGENTTRACE_ANALYSIS_MODEL", raising=False)
    monkeypatch.delenv("AGENTTRACE_SUMMARY_MODEL", raising=False)
    
    settings = get_settings()
    assert settings.analysis_model == "gpt-4o-mini"
    assert settings.summary_model == "gpt-4o-mini"


def test_analysis_model_settings_explicit(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("AGENTTRACE_ANALYSIS_MODEL", "gpt-4o-analysis-test")
    monkeypatch.setenv("AGENTTRACE_SUMMARY_MODEL", "gpt-4o-summary-test")
    
    settings = get_settings()
    assert settings.analysis_model == "gpt-4o-analysis-test"
    assert settings.summary_model == "gpt-4o-summary-test"


def test_build_openai_analysis_model(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    captured = {}

    class FakeChatOpenAI:
        def __init__(self, **kwargs):
            captured.update(kwargs)

    monkeypatch.setenv("OPENAI_API_KEY", "test-api-key")
    monkeypatch.setenv("OPENAI_API_BASE", "https://api.custom-openai.com/v1")
    monkeypatch.setenv("AGENTTRACE_ANALYSIS_MODEL", "gpt-4o-analysis-build-test")
    
    monkeypatch.setitem(
        sys.modules,
        "langchain_openai",
        types.SimpleNamespace(ChatOpenAI=FakeChatOpenAI),
    )
    
    build_openai_analysis_model()
    
    assert captured["model"] == "gpt-4o-analysis-build-test"
    assert captured["api_key"] == "test-api-key"
    assert captured["base_url"] == "https://api.custom-openai.com/v1"
    assert captured["temperature"] == 0


def test_build_openai_analysis_model_missing_api_key(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    
    with pytest.raises(MissingAnalysisModelError) as exc_info:
        build_openai_analysis_model()
    assert "OPENAI_API_KEY is required" in str(exc_info.value)


def test_summary_service_exception_to_http_analysis_error():
    exc = MissingAnalysisModelError("test analysis error")
    http_exc = summary_service_exception_to_http(exc)
    
    assert isinstance(http_exc, HTTPException)
    assert http_exc.status_code == 500
    assert http_exc.detail["error"] == "analysis_model_not_configured"
    assert http_exc.detail["message"] == "test analysis error"
