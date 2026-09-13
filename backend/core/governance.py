import re
from pathlib import Path
import yaml
from backend.core.schemas import TriageLLMOutput, RemediationAgentOutput, RemediationBlock, GovernanceBlock

GOVERNANCE_CONFIG_PATH = Path(__file__).parent / "governance.yaml"


def load_governance_rules(config_path: Path = GOVERNANCE_CONFIG_PATH) -> tuple[dict[str, list[str]], list[re.Pattern]]:
    if not config_path.is_file():
        raise FileNotFoundError(f"Governance configuration file missing at: {config_path}")
    try:
        with open(config_path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)
    except Exception as exc:
        raise RuntimeError(f"Failed to parse governance configuration file '{config_path}': {exc}") from exc

    allowlist = data.get("allowlist_prefixes", {})
    denylist_raw = data.get("denylist_patterns", [])
    compiled_denylist = [re.compile(pattern, re.IGNORECASE) for pattern in denylist_raw]
    return allowlist, compiled_denylist


# Load rules at runtime from governance.yaml
ALLOWLIST_PREFIXES, DENYLIST_PATTERNS = load_governance_rules()



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
