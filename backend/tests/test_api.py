from unittest.mock import patch
from fastapi.testclient import TestClient

from backend.api.main import app
from backend.core.schemas import (
    SeverityOutput,
    DiagnosticAgentOutput,
    RemediationAgentOutput,
    PostMortemBlock,
)

client = TestClient(app)


def test_health_endpoint():
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok", "service": "sre-triage-agent"}


def test_triage_no_error_logs():
    payload = {
        "service_name": "payment-api",
        "environment": "staging",
        "log_payload": "2026-09-08 INFO all systems operational\n2026-09-08 DEBUG ping pong",
        "max_context_lines": 5,
    }
    resp = client.post("/v1/triage", json=payload)
    assert resp.status_code == 200
    data = resp.json()
    assert data["service_name"] == "payment-api"
    assert data["confidence_score"] == 0.0
    assert data["remediation"]["status"] == "APPROVED"
    assert "post_mortem" in data


def test_triage_endpoint_with_mocked_triad_approved():
    mock_sev = SeverityOutput(severity_detected="FATAL", severity_reasoning="Fatal NPE crash")
    mock_diag = DiagnosticAgentOutput(
        root_cause="NullPointerException in PaymentProcessor.charge",
        confidence_score=0.95,
        explanation="Line 4 shows a FATAL NullPointerException",
    )
    mock_rem = RemediationAgentOutput(
        remediation_command="kubectl rollout restart deployment/checkout-api -n prod",
        command_type="kubectl",
        requires_human_approval=False,
        runbook_steps=["Step 1: Check pod status", "Step 2: Trigger rollout restart"],
    )
    mock_pm = PostMortemBlock(
        summary="NullPointerException crash on checkout service.",
        contributing_factors=["Unset customer token"],
        preventive_actions=["Add non-null assertion"],
        impact_assessment="Intermittent checkout failures",
    )

    with patch("backend.api.routes.triage.classify_severity") as mock_classify, \
         patch("backend.api.routes.triage.diagnose_root_cause") as mock_diagnose, \
         patch("backend.api.routes.triage.generate_remediation") as mock_remediation, \
         patch("backend.api.routes.triage.generate_post_mortem") as mock_post_mortem:

        mock_classify.return_value = (mock_sev, {"prompt_tokens": 50, "completion_tokens": 10}, 20.0)
        mock_diagnose.return_value = (mock_diag, {"prompt_tokens": 60, "completion_tokens": 15}, 30.0)
        mock_remediation.return_value = (mock_rem, {"prompt_tokens": 70, "completion_tokens": 20}, 40.0)
        mock_post_mortem.return_value = (mock_pm, {"prompt_tokens": 80, "completion_tokens": 25}, 50.0)

        payload = {
            "service_name": "checkout-api",
            "environment": "prod",
            "log_payload": "INFO start\nFATAL NullPointerException at line 2\nINFO done",
            "max_context_lines": 10,
        }
        resp = client.post("/v1/triage", json=payload)
        assert resp.status_code == 200
        data = resp.json()

        assert data["severity_detected"] == "FATAL"
        assert data["root_cause"] == "NullPointerException in PaymentProcessor.charge"
        assert data["remediation"]["status"] == "APPROVED"
        assert data["remediation"]["command"] == "kubectl rollout restart deployment/checkout-api -n prod"
        assert data["remediation"]["runbook_steps"] == ["Step 1: Check pod status", "Step 2: Trigger rollout restart"]
        assert data["post_mortem"]["summary"] == "NullPointerException crash on checkout service."
        assert data["governance"]["guardrail_triggered"] is False
        assert data["token_usage"]["prompt_tokens"] == 260


def test_triage_endpoint_with_mocked_triad_blocked():
    mock_sev = SeverityOutput(severity_detected="ERROR", severity_reasoning="Stale session locks")
    mock_diag = DiagnosticAgentOutput(
        root_cause="Database locks",
        confidence_score=0.85,
        explanation="Stale database connections",
    )
    mock_rem = RemediationAgentOutput(
        remediation_command="TRUNCATE TABLE locks;",
        command_type="sql",
        requires_human_approval=False,
        runbook_steps=["Step 1: Inspect locks"],
    )
    mock_pm = PostMortemBlock(
        summary="Database locking issue.",
        contributing_factors=["Connection pool saturation"],
        preventive_actions=["Implement query timeout"],
        impact_assessment="Database query slowdowns",
    )

    with patch("backend.api.routes.triage.classify_severity") as mock_classify, \
         patch("backend.api.routes.triage.diagnose_root_cause") as mock_diagnose, \
         patch("backend.api.routes.triage.generate_remediation") as mock_remediation, \
         patch("backend.api.routes.triage.generate_post_mortem") as mock_post_mortem:

        mock_classify.return_value = (mock_sev, {"prompt_tokens": 50, "completion_tokens": 10}, 20.0)
        mock_diagnose.return_value = (mock_diag, {"prompt_tokens": 60, "completion_tokens": 15}, 30.0)
        mock_remediation.return_value = (mock_rem, {"prompt_tokens": 70, "completion_tokens": 20}, 40.0)
        mock_post_mortem.return_value = (mock_pm, {"prompt_tokens": 80, "completion_tokens": 25}, 50.0)

        payload = {
            "service_name": "billing-api",
            "environment": "prod",
            "log_payload": "INFO start\nERROR database lock acquired\nINFO done",
            "max_context_lines": 10,
        }
        resp = client.post("/v1/triage", json=payload)
        assert resp.status_code == 200
        data = resp.json()

        assert data["remediation"]["status"] == "BLOCKED_ESCALATED"
        assert data["remediation"]["command"] is None
        assert data["governance"]["guardrail_triggered"] is True
        assert "Denylist match" in data["remediation"]["block_reason"]
