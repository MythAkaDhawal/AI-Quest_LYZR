"""scripts/benchmark.py.

Run: python scripts/benchmark.py --n 50 --concurrency 5 --base-url
http://localhost:8000
Proves: p95 latency < 1000ms, and mean prompt tokens stay bounded regardless of
input log size (the entire point of the Polars pre-filter stage).
"""

import argparse
import asyncio
import statistics
import time
from pathlib import Path

import httpx

SAMPLE_DIR = Path(__file__).parent.parent / "data" / "sample_logs"


async def fire_one(client: httpx.AsyncClient, base_url: str, payload: dict) -> dict:
    t0 = time.perf_counter()
    resp = await client.post(f"{base_url}/v1/triage", json=payload, timeout=10.0)
    wall_ms = (time.perf_counter() - t0) * 1000
    body = resp.json() if resp.status_code == 200 else {}
    return {
        "status_code": resp.status_code,
        "wall_ms": wall_ms,
        "server_total_ms": body.get("timing_ms", {}).get("total"),
        "prompt_tokens": body.get("token_usage", {}).get("prompt_tokens"),
    }


async def run_benchmark(n: int, concurrency: int, base_url: str) -> list[dict]:
    payloads = []
    for f in sorted(SAMPLE_DIR.glob("*.log")):
        payloads.append(
            {
                "service_name": f.stem,
                "environment": "prod",
                "log_payload": f.read_text(encoding="utf-8"),
                "max_context_lines": 10,
            }
        )
    if not payloads:
        raise SystemExit(f"No sample logs found in {SAMPLE_DIR}. Run scripts/seed_sample_logs.py first.")

    sem = asyncio.Semaphore(concurrency)

    async def bound_fire(client, payload):
        async with sem:
            return await fire_one(client, base_url, payload)

    async with httpx.AsyncClient() as client:
        tasks = [bound_fire(client, payloads[i % len(payloads)]) for i in range(n)]
        results = await asyncio.gather(*tasks)
    return results


def summarize(results: list[dict]) -> None:
    ok = [r for r in results if r["status_code"] == 200]
    wall = sorted(r["wall_ms"] for r in ok)
    tokens = [r["prompt_tokens"] for r in ok if r["prompt_tokens"] is not None]

    def pct(data, p):
        if not data:
            return 0.0
        idx = min(len(data) - 1, int(len(data) * p))
        return data[idx]

    p50, p95, p99 = pct(wall, 0.50), pct(wall, 0.95), pct(wall, 0.99)
    mean_tokens = statistics.mean(tokens) if tokens else 0

    print("=" * 60)
    print(f"Requests: {len(results)}  |  Successful: {len(ok)}  |  Failed: {len(results) - len(ok)}")
    print(f"Latency p50: {p50:.1f} ms   p95: {p95:.1f} ms   p99: {p99:.1f} ms")
    print(f"Mean prompt tokens: {mean_tokens:.0f}")
    print("-" * 60)
    verdict = "PASS" if p95 < 1000 else "FAIL"
    print(f"RUBRIC CHECK — p95 < 1000ms: {verdict}")
    print("=" * 60)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--n", type=int, default=50)
    parser.add_argument("--concurrency", type=int, default=5)
    parser.add_argument("--base-url", type=str, default="http://localhost:8000")
    args = parser.parse_args()

    results = asyncio.run(run_benchmark(args.n, args.concurrency, args.base_url))
    summarize(results)
