import pytest
from agents.prompts import TRIAGE_PROMPT, GOD_PROMPT
from agents.triage_agent import classify_severity, diagnose, AgentUnavailableError


def test_triage_prompt_formatting():
    formatted = TRIAGE_PROMPT.format(
        pruned_log_context="test log context",
        service_metadata_json='{"service_name": "test"}',
    )
    assert "test log context" in formatted
    assert '{"service_name": "test"}' in formatted
    assert "OUTPUT SCHEMA" in formatted


def test_god_prompt_formatting():
    formatted = GOD_PROMPT.format(
        pruned_log_context="test log context",
        service_metadata_json='{"service_name": "test"}',
    )
    assert "test log context" in formatted
    assert '{"service_name": "test"}' in formatted


def test_classify_severity_raises_unavailable_when_no_api_key():
    with pytest.raises(AgentUnavailableError):
        classify_severity("test context", {"service_name": "test", "environment": "dev"})


def test_diagnose_raises_unavailable_when_no_api_key():
    with pytest.raises(AgentUnavailableError):
        diagnose("test context", {"service_name": "test", "environment": "dev"})
