from backend.core.schemas import TriageLLMOutput, RemediationAgentOutput
from backend.core.governance import evaluate_governance


def test_approved_kubectl_command():
    llm_output = TriageLLMOutput(
        severity_detected="FATAL",
        root_cause="Out of memory crash",
        confidence_score=0.9,
        explanation="Pod crashed due to OOMKilled",
        remediation_command="kubectl rollout restart deployment/checkout-api -n prod",
        command_type="kubectl",
        requires_human_approval=False,
    )
    rem, gov = evaluate_governance(llm_output)
    assert rem.status == "APPROVED"
    assert rem.command == "kubectl rollout restart deployment/checkout-api -n prod"
    assert gov.guardrail_triggered is False
    assert gov.allowlist_verb == "kubectl rollout restart"


def test_approved_remediation_agent_output():
    rem_output = RemediationAgentOutput(
        remediation_command="kubectl rollout restart deployment/payment-api -n prod",
        command_type="kubectl",
        requires_human_approval=False,
        runbook_steps=["Step 1: Check metrics", "Step 2: Restart deployment"],
    )
    rem, gov = evaluate_governance(rem_output)
    assert rem.status == "APPROVED"
    assert rem.command == "kubectl rollout restart deployment/payment-api -n prod"
    assert rem.runbook_steps == ["Step 1: Check metrics", "Step 2: Restart deployment"]
    assert gov.guardrail_triggered is False


def test_blocked_denylist_rm_rf():
    llm_output = TriageLLMOutput(
        severity_detected="ERROR",
        root_cause="Disk full",
        confidence_score=0.8,
        explanation="Disk space reached 100%",
        remediation_command="rm -rf /var/log/*",
        command_type="shell",
        requires_human_approval=False,
    )
    rem, gov = evaluate_governance(llm_output)
    assert rem.status == "BLOCKED_ESCALATED"
    assert rem.command is None
    assert gov.guardrail_triggered is True
    assert gov.matched_denylist_pattern is not None


def test_blocked_denylist_sql_truncate():
    llm_output = TriageLLMOutput(
        severity_detected="ERROR",
        root_cause="Stale session locks",
        confidence_score=0.75,
        explanation="Orphaned session rows",
        remediation_command="TRUNCATE TABLE active_sessions;",
        command_type="sql",
        requires_human_approval=False,
    )
    rem, gov = evaluate_governance(llm_output)
    assert rem.status == "BLOCKED_ESCALATED"
    assert rem.command is None
    assert gov.guardrail_triggered is True


def test_blocked_unapproved_allowlist_command():
    llm_output = TriageLLMOutput(
        severity_detected="ERROR",
        root_cause="Custom script failure",
        confidence_score=0.7,
        explanation="Script crashed",
        remediation_command="python /tmp/fix_stuff.py",
        command_type="shell",
        requires_human_approval=False,
    )
    rem, gov = evaluate_governance(llm_output)
    assert rem.status == "BLOCKED_ESCALATED"
    assert rem.command is None
    assert gov.guardrail_triggered is True


def test_none_command_type():
    llm_output = TriageLLMOutput(
        severity_detected="ERROR",
        root_cause="Unknown issue",
        confidence_score=0.2,
        explanation="Insufficient context",
        remediation_command="",
        command_type="none",
        requires_human_approval=True,
    )
    rem, gov = evaluate_governance(llm_output)
    assert rem.status == "APPROVED"
    assert rem.command is None
    assert rem.command_type == "none"
    assert gov.guardrail_triggered is False
