from unittest.mock import patch
from fastapi.testclient import TestClient
from api.main import app
from core.schemas import TriageLLMOutput

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


def test_triage_endpoint_with_mocked_llm_approved():
    mock_llm_output = TriageLLMOutput(
        severity_detected="FATAL",
        root_cause="NullPointerException in PaymentProcessor.charge",
        confidence_score=0.95,
        explanation="Line 4 shows a FATAL NullPointerException",
        remediation_command="kubectl rollout restart deployment/checkout-api -n prod",
        command_type="kubectl",
        requires_human_approval=False,
    )

    with patch("api.routes.triage.diagnose") as mock_diagnose:
        mock_diagnose.return_value = (
            mock_llm_output,
            {"prompt_tokens": 150, "completion_tokens": 40},
            120.5,
        )

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
        assert data["governance"]["guardrail_triggered"] is False
        assert data["token_usage"]["prompt_tokens"] == 150


def test_triage_endpoint_with_mocked_llm_blocked():
    mock_llm_output = TriageLLMOutput(
        severity_detected="ERROR",
        root_cause="Database locks",
        confidence_score=0.85,
        explanation="Stale database connections",
        remediation_command="TRUNCATE TABLE locks;",
        command_type="sql",
        requires_human_approval=False,
    )

    with patch("api.routes.triage.diagnose") as mock_diagnose:
        mock_diagnose.return_value = (
            mock_llm_output,
            {"prompt_tokens": 200, "completion_tokens": 50},
            100.0,
        )

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
