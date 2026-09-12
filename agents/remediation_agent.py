import json
from agents.base_agent import call_llm_agent, AgentUnavailableError
from agents.prompts import REMEDIATION_PROMPT
from backend.core.schemas import RemediationAgentOutput
from backend.utils.logging_config import logger


def generate_remediation(
    pruned_context: str,
    service_metadata: dict,
    root_cause: str,
    explanation: str,
) -> tuple[RemediationAgentOutput, dict, float]:
    prompt = REMEDIATION_PROMPT.format(
        root_cause=root_cause,
        explanation=explanation,
        pruned_log_context=pruned_context,
        service_metadata_json=json.dumps(service_metadata),
    )
    try:
        return call_llm_agent(
            prompt=prompt,
            agent_name="sre-remediation-agent",
            role="Autonomous SRE runbook and CLI remediation generator",
            goal="Propose safe CLI remediation command, command_type, human approval flag, and runbook steps.",
            instructions=REMEDIATION_PROMPT,
            model_cls=RemediationAgentOutput,
        )
    except Exception as exc:
        logger.error(f"Remediation agent failed after retries: {exc}")
        raise AgentUnavailableError(str(exc)) from exc
