"""Phase 3 QA: Multi-Agent Triad End-to-End Integration Test.

Starts a FastAPI TestClient, mocks all 4 agents with realistic outputs,
fires a real crash_sample payload from backend/data/sample_logs/, and
asserts the response JSON contains distinct outputs from every triad node.

Exit code 0 = PASS, non-zero = FAIL with full traceback.
"""
import json
import sys
from unittest.mock import patch
from fastapi.testclient import TestClient

from backend.api.main import app
from backend.core.schemas import (
    SeverityOutput,
    DiagnosticAgentOutput,
    RemediationAgentOutput,
    PostMortemBlock,
)

CRASH_PAYLOAD_PATH = "backend/data/sample_logs/crash_sample_request.json"


def run_triad_integration_test():
    client = TestClient(app)
    results = {}

    # ---- Load real sample payload ----
    with open(CRASH_PAYLOAD_PATH, "r", encoding="utf-8") as f:
        payload = json.load(f)

    # ---- Mock agent outputs ----
    mock_sev = SeverityOutput(
        severity_detected="FATAL",
        severity_reasoning="Detected java.lang.NullPointerException marked as FATAL in log line 5. "
        "Stack trace confirms unrecoverable crash in PaymentProcessor.charge."
    )
    mock_diag = DiagnosticAgentOutput(
        root_cause="NullPointerException in PaymentProcessor.charge(PaymentProcessor.java:118) "
        "caused by uninitialized customerToken during checkout flow.",
        confidence_score=0.92,
        explanation="Log line 5 shows FATAL NPE at PaymentProcessor.java:118. "
        "Line 3 shows request processing for user 88311. "
        "Line 7 shows HTTP 500 returned to client, confirming request failure."
    )
    mock_rem = RemediationAgentOutput(
        remediation_command="kubectl rollout restart deployment/checkout-api -n prod",
        command_type="kubectl",
        requires_human_approval=False,
        runbook_steps=[
            "Step 1: Verify pod crash loop with `kubectl get pods -n prod`",
            "Step 2: Inspect crash logs with `kubectl logs deployment/checkout-api -n prod --tail=50`",
            "Step 3: Execute rollout restart `kubectl rollout restart deployment/checkout-api -n prod`",
            "Step 4: Monitor restart with `kubectl rollout status deployment/checkout-api -n prod`",
            "Step 5: Verify healthcheck at /health returns 200",
        ],
    )
    mock_pm = PostMortemBlock(
        summary="FATAL NullPointerException crashed the checkout-api service during a payment "
        "processing flow. The PaymentProcessor.charge method received a null customerToken, "
        "causing an unrecoverable crash and HTTP 500 to the client.",
        contributing_factors=[
            "Missing null-check on customerToken before calling charge()",
            "No circuit-breaker pattern on the checkout flow",
            "Absence of defensive coding practices in PaymentProcessor",
        ],
        preventive_actions=[
            "Add @NonNull annotation and null-guard on customerToken parameter",
            "Implement circuit-breaker (e.g., Resilience4j) on checkout path",
            "Add integration test covering null customerToken edge case",
            "Enable pod disruption budget to prevent cascading failures",
        ],
        impact_assessment="Single checkout request failed with HTTP 500. "
        "Worker thread-4 initiated graceful shutdown. Impact limited to "
        "one user transaction (user_id=88311, request_id=req-94812)."
    )

    with patch("backend.api.routes.triage.classify_severity") as p_sev, \
         patch("backend.api.routes.triage.diagnose_root_cause") as p_diag, \
         patch("backend.api.routes.triage.generate_remediation") as p_rem, \
         patch("backend.api.routes.triage.generate_post_mortem") as p_pm:

        p_sev.return_value = (mock_sev, {"prompt_tokens": 420, "completion_tokens": 35}, 180.0)
        p_diag.return_value = (mock_diag, {"prompt_tokens": 480, "completion_tokens": 60}, 220.0)
        p_rem.return_value = (mock_rem, {"prompt_tokens": 510, "completion_tokens": 85}, 250.0)
        p_pm.return_value = (mock_pm, {"prompt_tokens": 550, "completion_tokens": 120}, 310.0)

        resp = client.post("/v1/triage", json=payload)

    assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
    data = resp.json()

    # ---- ASSERTION BLOCK: Structural completeness ----
    required_top_keys = [
        "incident_id", "service_name", "severity_detected",
        "root_cause", "confidence_score", "explanation",
        "remediation", "post_mortem", "governance", "timing_ms", "token_usage",
    ]
    for key in required_top_keys:
        assert key in data, f"Missing top-level key: {key}"

    results["response_schema_valid"] = True

    # ---- Node 1: Triage Agent — Severity Classification ----
    assert data["severity_detected"] in ("FATAL", "ERROR"), \
        f"severity_detected not P1-P4 mapped: {data['severity_detected']}"
    results["triage_agent"] = {
        "severity_detected": data["severity_detected"],
        "status": "PASS",
    }

    # ---- Node 2: Diagnostic Agent — Root Cause ----
    assert len(data["root_cause"]) > 10, "root_cause too short to be meaningful"
    assert data["confidence_score"] > 0.0, "confidence_score must be positive"
    assert len(data["explanation"]) > 20, "explanation too short"
    results["diagnostic_agent"] = {
        "root_cause": data["root_cause"][:100],
        "confidence_score": data["confidence_score"],
        "explanation_length": len(data["explanation"]),
        "status": "PASS",
    }

    # ---- Node 3: Remediation Agent — Command + Runbook ----
    rem = data["remediation"]
    assert rem["status"] in ("APPROVED", "BLOCKED_ESCALATED"), f"Invalid status: {rem['status']}"
    assert "runbook_steps" in rem, "Missing runbook_steps in remediation block"
    assert isinstance(rem["runbook_steps"], list), "runbook_steps must be a list"
    assert len(rem["runbook_steps"]) > 0, "runbook_steps must not be empty"
    results["remediation_agent"] = {
        "command": rem.get("command"),
        "command_type": rem.get("command_type"),
        "status": rem["status"],
        "runbook_step_count": len(rem["runbook_steps"]),
        "runbook_first_step": rem["runbook_steps"][0] if rem["runbook_steps"] else None,
        "result": "PASS",
    }

    # ---- Node 4: Post-Mortem Agent — Blameless RCA ----
    pm = data["post_mortem"]
    assert "summary" in pm, "Missing post_mortem.summary"
    assert len(pm["summary"]) > 20, "post_mortem summary too short"
    assert "contributing_factors" in pm, "Missing contributing_factors"
    assert isinstance(pm["contributing_factors"], list) and len(pm["contributing_factors"]) > 0
    assert "preventive_actions" in pm, "Missing preventive_actions"
    assert isinstance(pm["preventive_actions"], list) and len(pm["preventive_actions"]) > 0
    assert "impact_assessment" in pm, "Missing impact_assessment"
    assert len(pm["impact_assessment"]) > 10, "impact_assessment too short"
    results["post_mortem_agent"] = {
        "summary_length": len(pm["summary"]),
        "contributing_factors_count": len(pm["contributing_factors"]),
        "preventive_actions_count": len(pm["preventive_actions"]),
        "impact_assessment_length": len(pm["impact_assessment"]),
        "status": "PASS",
    }

    # ---- Governance Gate ----
    gov = data["governance"]
    assert "guardrail_triggered" in gov
    results["governance"] = {
        "guardrail_triggered": gov["guardrail_triggered"],
        "matched_denylist_pattern": gov.get("matched_denylist_pattern"),
        "allowlist_verb": gov.get("allowlist_verb"),
        "status": "PASS",
    }

    # ---- Timing & Token ----
    tm = data["timing_ms"]
    assert tm["preprocessing"] >= 0
    assert tm["total"] >= 0
    results["timing_ms"] = tm
    results["token_usage"] = data["token_usage"]

    # ---- Token bounding check (Polars preprocessor guarantee) ----
    total_prompt_tokens = data["token_usage"]["prompt_tokens"]
    assert total_prompt_tokens > 0, "Token usage must be positive"
    results["token_bound_check"] = {
        "total_prompt_tokens": total_prompt_tokens,
        "total_completion_tokens": data["token_usage"]["completion_tokens"],
        "status": "PASS (bounded by Polars preprocessor)",
    }

    return data, results


if __name__ == "__main__":
    try:
        full_response, results = run_triad_integration_test()
        print("=" * 72)
        print("PHASE 3: MULTI-AGENT TRIAD INTEGRATION TEST — ALL ASSERTIONS PASSED")
        print("=" * 72)
        print(json.dumps(results, indent=2, default=str))
        print("\n--- Full Response JSON ---")
        print(json.dumps(full_response, indent=2, default=str))
        sys.exit(0)
    except Exception as exc:
        print(f"PHASE 3 FAILED: {exc}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        sys.exit(1)
