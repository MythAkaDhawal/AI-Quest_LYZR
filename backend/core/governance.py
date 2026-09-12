import re
from backend.core.schemas import TriageLLMOutput, RemediationAgentOutput, RemediationBlock, GovernanceBlock

# --- Layer 1: CLOSED-SET ALLOWLIST (the actual mathematical guarantee) -------------
ALLOWLIST_PREFIXES: dict[str, list[str]] = {
    "kubectl": [
        "kubectl rollout restart",
        "kubectl scale",
        "kubectl describe",
        "kubectl logs",
        "kubectl get",
        "kubectl top",
        "kubectl rollout status",
        "kubectl rollout undo",
    ],
    "shell": [
        "systemctl restart",
        "systemctl status",
        "systemctl reload",
        "journalctl",
        "df -h",
        "free -m",
        "netstat",
        "ps aux",
        "kill -HUP",
        "curl -I",
        "tail -n",
    ],
    "sql": [
        "SELECT",
        "EXPLAIN",
        "SHOW",
        "ANALYZE",
    ],
    "http": ["GET ", "POST /health", "POST /restart-worker"],
    "none": [""],
}

# --- Layer 2: DENYLIST (defense-in-depth belt-and-suspenders) ---------------------
DENYLIST_PATTERNS = [
    re.compile(p, re.IGNORECASE)
    for p in [
        r"\brm\s+-rf\b",
        r"\bmkfs\.",
        r"\bdd\s+if=",
        r"\bshutdown\b",
        r"\breboot\b",
        r"\binit\s+0\b",
        r":\(\)\s*\{\s*:\|\:&\s*\}\s*;\s*:",  # fork bomb
        r"\bDROP\s+(TABLE|DATABASE|SCHEMA)\b",
        r"\bTRUNCATE\b",
        r"\bDELETE\s+FROM\s+\w+(?!\s+WHERE)",  # unWHEREd delete
        r"\bkubectl\s+delete\s+(ns|namespace|pv|persistentvolume)\b",
        r"\bchmod\s+-R\s+777\s+/",
        r"\bchown\s+-R\b.*\s+/\s*$",
        r"\bdocker\s+system\s+prune\s+-a\s+-f\b",
        r"\bterraform\s+destroy\b",
        r"\biptables\s+-F\b",
        r"\bufw\s+disable\b",
    ]
]


def evaluate_governance(
    llm_output: TriageLLMOutput | RemediationAgentOutput,
) -> tuple[RemediationBlock, GovernanceBlock]:
    cmd = (llm_output.remediation_command or "").strip()
    ctype = llm_output.command_type
    runbook_steps = getattr(llm_output, "runbook_steps", [])

    if ctype == "none" or not cmd:
        return (
            RemediationBlock(command=None, command_type="none", status="APPROVED", runbook_steps=runbook_steps),
            GovernanceBlock(guardrail_triggered=False),
        )

    # Denylist check runs first — an unsafe command is unsafe even if it
    # coincidentally matches an allowlist prefix string.
    for pattern in DENYLIST_PATTERNS:
        if pattern.search(cmd):
            return (
                RemediationBlock(
                    command=None,
                    command_type=ctype,
                    status="BLOCKED_ESCALATED",
                    block_reason=f"Denylist match: destructive pattern '{pattern.pattern}' detected. Escalated to on-call.",
                    runbook_steps=runbook_steps,
                ),
                GovernanceBlock(guardrail_triggered=True, matched_denylist_pattern=pattern.pattern),
            )

    matched_verb = next(
        (verb for verb in ALLOWLIST_PREFIXES.get(ctype, []) if cmd.startswith(verb)),
        None,
    )
    if matched_verb is None or llm_output.requires_human_approval:
        return (
            RemediationBlock(
                command=None,
                command_type=ctype,
                status="BLOCKED_ESCALATED",
                block_reason="Command did not match an approved allowlist verb, or the agent flagged requires_human_approval. Escalated to on-call.",
                runbook_steps=runbook_steps,
            ),
            GovernanceBlock(guardrail_triggered=True),
        )

    return (
        RemediationBlock(command=cmd, command_type=ctype, status="APPROVED", runbook_steps=runbook_steps),
        GovernanceBlock(guardrail_triggered=False, allowlist_verb=matched_verb),
    )
