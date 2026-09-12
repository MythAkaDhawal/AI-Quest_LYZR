import json
from pathlib import Path

DATA_DIR = Path(__file__).parent.parent / "data" / "sample_logs"
DATA_DIR.mkdir(parents=True, exist_ok=True)


def generate_crash_sample() -> str:
    lines = [
        "2026-09-08T02:14:00Z INFO checkout-api server starting up v2.4.1",
        "2026-09-08T02:14:01Z INFO checkout-api healthcheck ok, database connected",
        "2026-09-08T02:14:02Z DEBUG checkout-api processing request_id=req-94812 user_id=88311",
        "2026-09-08T02:14:02Z INFO checkout-api order total calculated: $149.99",
        "2026-09-08T02:14:03Z FATAL checkout-api java.lang.NullPointerException at com.checkout.PaymentProcessor.charge(PaymentProcessor.java:118)",
        "    at com.checkout.PaymentProcessor.processOrder(PaymentProcessor.java:84)",
        "    at com.checkout.CheckoutController.handleCheckout(CheckoutController.java:45)",
        "2026-09-08T02:14:03Z ERROR checkout-api HTTP 500 Internal Server Error returned to client",
        "2026-09-08T02:14:04Z INFO checkout-api gracefully shutting down worker thread-4",
    ]
    return "\n".join(lines)


def generate_oom_sample() -> str:
    lines = []
    for i in range(100):
        lines.append(f"2026-09-08T03:00:{i%60:02d}Z INFO billing-worker batch job step {i} completed ok")
    lines.append("2026-09-08T03:01:45Z FATAL billing-worker java.lang.OutOfMemoryError: Java heap space")
    lines.append("2026-09-08T03:01:45Z ERROR billing-worker Container killed by OS OOM Killer (exit code 137)")
    for i in range(20):
        lines.append(f"2026-09-08T03:02:{i%60:02d}Z WARN billing-worker retry buffer step {i}")
    return "\n".join(lines)


def generate_disk_full_sample() -> str:
    lines = []
    for i in range(500):
        lines.append(f"2026-09-08T04:10:{i%60:02d}Z DEBUG auth-service token verified for user_{i}")
    lines.append("2026-09-08T04:15:00Z ERROR auth-service [IOError] No space left on device: '/var/log/auth.log'")
    for i in range(100):
        lines.append(f"2026-09-08T04:15:{i%60:02d}Z WARN auth-service write fallback queue full")
    return "\n".join(lines)


def seed():
    crash_log = generate_crash_sample()
    (DATA_DIR / "crash_sample.log").write_text(crash_log, encoding="utf-8")

    oom_log = generate_oom_sample()
    (DATA_DIR / "oom_sample.log").write_text(oom_log, encoding="utf-8")

    disk_log = generate_disk_full_sample()
    (DATA_DIR / "disk_full_sample.log").write_text(disk_log, encoding="utf-8")

    req_payload = {
        "service_name": "checkout-api",
        "environment": "prod",
        "log_payload": crash_log,
        "max_context_lines": 10,
    }
    (DATA_DIR / "crash_sample_request.json").write_text(json.dumps(req_payload, indent=2), encoding="utf-8")

    print(f"Successfully seeded sample logs into {DATA_DIR}")


if __name__ == "__main__":
    seed()
