from unittest.mock import patch
import pytest

from agents.triage_agent import classify_severity, diagnose
from agents.diagnostic_agent import diagnose_root_cause
from agents.remediation_agent import generate_remediation
from agents.post_mortem_agent import generate_post_mortem
from agents.base_agent import AgentUnavailableError
from backend.core.schemas import (
    SeverityOutput,
    DiagnosticAgentOutput,
    RemediationAgentOutput,
    PostMortemBlock,
    TriageLLMOutput,
)


@patch("agents.triage_agent.call_llm_agent")
def test_classify_severity_mocked(mock_call_llm):
    expected_output = SeverityOutput(
        severity_detected="FATAL",
        severity_reasoning="Fatal out of memory error detected in crash logs."
    )
    mock_call_llm.return_value = (expected_output, {"prompt_tokens": 50, "completion_tokens": 15}, 25.0)

    service_metadata = {"service_name": "checkout-api", "environment": "prod"}
    output, usage, latency = classify_severity("Out of Memory panic", service_metadata)

    assert output.severity_detected == "FATAL"
    assert "out of memory" in output.severity_reasoning.lower()
    assert usage["prompt_tokens"] == 50
    assert latency == 25.0
    mock_call_llm.assert_called_once()


@patch("agents.diagnostic_agent.call_llm_agent")
def test_diagnose_root_cause_mocked(mock_call_llm):
    expected_output = DiagnosticAgentOutput(
        root_cause="Java Heap Space OutOfMemoryError",
        confidence_score=0.96,
        explanation="JVM heap exhausted due to memory leak in session handler."
    )
    mock_call_llm.return_value = (expected_output, {"prompt_tokens": 110, "completion_tokens": 25}, 42.0)

    service_metadata = {"service_name": "auth-service", "environment": "prod"}
    output, usage, latency = diagnose_root_cause(
        pruned_context="java.lang.OutOfMemoryError: Java heap space",
        service_metadata=service_metadata,
        severity_detected="FATAL",
    )

    assert output.root_cause == "Java Heap Space OutOfMemoryError"
    assert output.confidence_score == 0.96
    assert usage["prompt_tokens"] == 110
    assert latency == 42.0
    mock_call_llm.assert_called_once()


@patch("agents.remediation_agent.call_llm_agent")
def test_generate_remediation_mocked(mock_call_llm):
    expected_output = RemediationAgentOutput(
        remediation_command="kubectl rollout restart deployment/auth-service -n prod",
        command_type="kubectl",
        requires_human_approval=False,
        runbook_steps=["Verify pod status", "Issue rollout restart", "Check rollout status"]
    )
    mock_call_llm.return_value = (expected_output, {"prompt_tokens": 85, "completion_tokens": 35}, 30.5)

    service_metadata = {"service_name": "auth-service", "environment": "prod"}
    output, usage, latency = generate_remediation(
        pruned_context="java.lang.OutOfMemoryError",
        service_metadata=service_metadata,
        root_cause="Java Heap Space OutOfMemoryError",
        explanation="JVM heap exhausted",
    )

    assert output.remediation_command == "kubectl rollout restart deployment/auth-service -n prod"
    assert output.command_type == "kubectl"
    assert output.requires_human_approval is False
    assert len(output.runbook_steps) == 3
    mock_call_llm.assert_called_once()


@patch("agents.post_mortem_agent.call_llm_agent")
def test_generate_post_mortem_mocked(mock_call_llm):
    expected_output = PostMortemBlock(
        summary="Auth service crashed due to heap exhaustion.",
        contributing_factors=["Session leak", "High traffic spike"],
        preventive_actions=["Increase JVM heap limit", "Fix session leak in handler"],
        impact_assessment="5 minutes of intermittent 500 responses."
    )
    mock_call_llm.return_value = (expected_output, {"prompt_tokens": 140, "completion_tokens": 60}, 55.0)

    service_metadata = {"service_name": "auth-service", "environment": "prod"}
    output, usage, latency = generate_post_mortem(
        pruned_context="java.lang.OutOfMemoryError",
        service_metadata=service_metadata,
        severity_detected="FATAL",
        root_cause="Java Heap Space OutOfMemoryError",
        explanation="JVM heap exhausted",
        remediation_command="kubectl rollout restart deployment/auth-service -n prod",
    )

    assert output.summary == "Auth service crashed due to heap exhaustion."
    assert "Session leak" in output.contributing_factors
    assert len(output.preventive_actions) == 2
    mock_call_llm.assert_called_once()


@patch("agents.triage_agent.call_llm_agent")
def test_diagnose_unified_mocked(mock_call_llm):
    expected_output = TriageLLMOutput(
        severity_detected="FATAL",
        root_cause="Database Connection Timeout",
        confidence_score=0.88,
        explanation="Postgres pool exhausted",
        remediation_command="systemctl restart postgresql",
        command_type="shell",
        requires_human_approval=False,
    )
    mock_call_llm.return_value = (expected_output, {"prompt_tokens": 95, "completion_tokens": 30}, 38.0)

    output, usage, latency = diagnose("connection timed out", {"service_name": "db-api"})
    assert output.severity_detected == "FATAL"
    assert output.root_cause == "Database Connection Timeout"
    assert output.command_type == "shell"
    mock_call_llm.assert_called_once()


@patch("agents.triage_agent.call_llm_agent", side_effect=RuntimeError("API Network Error"))
def test_agent_raises_unavailable_on_llm_failure(mock_call_llm):
    with pytest.raises(AgentUnavailableError) as exc_info:
        classify_severity("context log", {"service_name": "test-service"})
    assert "API Network Error" in str(exc_info.value)
