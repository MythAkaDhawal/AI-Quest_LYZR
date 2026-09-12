import pytest
from backend.agents.prompts import DIAGNOSTIC_PROMPT, REMEDIATION_PROMPT, POST_MORTEM_PROMPT
from backend.agents.diagnostic_agent import diagnose_root_cause
from backend.agents.remediation_agent import generate_remediation
from backend.agents.post_mortem_agent import generate_post_mortem
from backend.agents.base_agent import AgentUnavailableError


def test_prompts_formatting():
    diag_p = DIAGNOSTIC_PROMPT.format(
        severity_detected="FATAL",
        pruned_log_context="test log",
        service_metadata_json='{"service_name": "test"}',
    )
    assert "test log" in diag_p

    rem_p = REMEDIATION_PROMPT.format(
        root_cause="NullPointer",
        explanation="NPE at line 5",
        pruned_log_context="test log",
        service_metadata_json='{"service_name": "test"}',
    )
    assert "NullPointer" in rem_p

    pm_p = POST_MORTEM_PROMPT.format(
        service_name="checkout-api",
        environment="prod",
        severity_detected="FATAL",
        root_cause="NullPointer",
        explanation="NPE at line 5",
        remediation_command="kubectl rollout restart deployment/checkout-api",
        pruned_log_context="test log",
    )
    assert "checkout-api" in pm_p


def test_agents_raise_unavailable_when_no_api_key():
    with pytest.raises(AgentUnavailableError):
        diagnose_root_cause("ctx", {"service_name": "test"})

    with pytest.raises(AgentUnavailableError):
        generate_remediation("ctx", {"service_name": "test"}, "root cause", "explanation")

    with pytest.raises(AgentUnavailableError):
        generate_post_mortem("ctx", {"service_name": "test"}, "FATAL", "root cause", "explanation", "cmd")
