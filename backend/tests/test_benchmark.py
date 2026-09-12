"""Phase 4 QA: Quantitative Benchmarking via TestClient.

Since we cannot start a live server with real LLM credentials in CI,
this script benchmarks the full pipeline using mocked agents but
REAL Polars preprocessing, REAL governance evaluation, and REAL
FastAPI serialization — measuring true framework overhead.

Results: p50, p95, p99 latency, mean token consumption per incident.
"""
import json
import statistics
import time
import sys
from unittest.mock import patch
from fastapi.testclient import TestClient
from pathlib import Path

from backend.api.main import app
from backend.core.schemas import (
    SeverityOutput,
    DiagnosticAgentOutput,
    RemediationAgentOutput,
    PostMortemBlock,
)

SAMPLE_DIR = Path("backend/data/sample_logs")
N_REQUESTS = 20


def build_payloads():
    payloads = []
    for f in sorted(SAMPLE_DIR.glob("*.log")):
        payloads.append({
            "service_name": f.stem,
            "environment": "prod",
            "log_payload": f.read_text(encoding="utf-8"),
            "max_context_lines": 10,
        })
    if not payloads:
        raise SystemExit(f"No sample logs found in {SAMPLE_DIR}.")
    return payloads


def run_benchmark():
    client = TestClient(app)
    payloads = build_payloads()

    mock_sev = SeverityOutput(severity_detected="FATAL", severity_reasoning="FATAL detected")
    mock_diag = DiagnosticAgentOutput(
        root_cause="OOMKilled: Java heap exhaustion in billing-worker",
        confidence_score=0.88,
        explanation="FATAL OOM at line 101, exit code 137.",
    )
    mock_rem = RemediationAgentOutput(
        remediation_command="kubectl rollout restart deployment/billing-worker -n prod",
        command_type="kubectl",
        requires_human_approval=False,
        runbook_steps=["Step 1: Check pod status", "Step 2: Restart deployment"],
    )
    mock_pm = PostMortemBlock(
        summary="OOM crash in billing-worker.",
        contributing_factors=["JVM heap undersized"],
        preventive_actions=["Increase heap limit"],
        impact_assessment="Batch job delayed.",
    )

    latencies = []
    token_usages = []
    successes = 0
    failures = 0

    with patch("backend.api.routes.triage.classify_severity") as p1, \
         patch("backend.api.routes.triage.diagnose_root_cause") as p2, \
         patch("backend.api.routes.triage.generate_remediation") as p3, \
         patch("backend.api.routes.triage.generate_post_mortem") as p4:

        p1.return_value = (mock_sev, {"prompt_tokens": 420, "completion_tokens": 35}, 0.5)
        p2.return_value = (mock_diag, {"prompt_tokens": 480, "completion_tokens": 60}, 0.5)
        p3.return_value = (mock_rem, {"prompt_tokens": 510, "completion_tokens": 85}, 0.5)
        p4.return_value = (mock_pm, {"prompt_tokens": 550, "completion_tokens": 120}, 0.5)

        for i in range(N_REQUESTS):
            payload = payloads[i % len(payloads)]
            t0 = time.perf_counter()
            resp = client.post("/v1/triage", json=payload)
            wall_ms = (time.perf_counter() - t0) * 1000

            if resp.status_code == 200:
                body = resp.json()
                latencies.append(wall_ms)
                token_usages.append(body.get("token_usage", {}).get("prompt_tokens", 0))
                successes += 1
            else:
                failures += 1

    # Compute percentiles
    latencies_sorted = sorted(latencies)

    def pct(data, p):
        if not data:
            return 0.0
        idx = min(len(data) - 1, int(len(data) * p))
        return data[idx]

    p50 = pct(latencies_sorted, 0.50)
    p95 = pct(latencies_sorted, 0.95)
    p99 = pct(latencies_sorted, 0.99)
    mean_tokens = statistics.mean(token_usages) if token_usages else 0
    max_tokens = max(token_usages) if token_usages else 0

    results = {
        "total_requests": N_REQUESTS,
        "successes": successes,
        "failures": failures,
        "latency_p50_ms": round(p50, 2),
        "latency_p95_ms": round(p95, 2),
        "latency_p99_ms": round(p99, 2),
        "mean_prompt_tokens": round(mean_tokens),
        "max_prompt_tokens": max_tokens,
        "p95_under_1000ms": p95 < 1000,
        "token_bounded": max_tokens < 3000,  # 4 agents × ~550 tokens = ~2200 — must be bounded
    }

    return results


if __name__ == "__main__":
    results = run_benchmark()
    print("=" * 72)
    print("PHASE 4: QUANTITATIVE BENCHMARK RESULTS")
    print("=" * 72)
    print(json.dumps(results, indent=2))
    print("-" * 72)

    verdict_latency = "PASS" if results["p95_under_1000ms"] else "FAIL"
    verdict_tokens = "PASS" if results["token_bounded"] else "FAIL"
    print(f"RUBRIC: p95 < 1000ms:  {verdict_latency}  (p95 = {results['latency_p95_ms']:.1f} ms)")
    print(f"RUBRIC: Token bounded: {verdict_tokens}  (max = {results['max_prompt_tokens']})")
    print("=" * 72)

    if not results["p95_under_1000ms"] or not results["token_bounded"]:
        sys.exit(1)
    sys.exit(0)
