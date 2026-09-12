import json
from backend.agents.base_agent import call_llm_agent, AgentUnavailableError
from backend.agents.prompts import TRIAGE_PROMPT, GOD_PROMPT
from backend.core.schemas import SeverityOutput, TriageLLMOutput
from backend.utils.logging_config import logger


def classify_severity(pruned_context: str, service_metadata: dict) -> tuple[SeverityOutput, dict, float]:
    prompt = TRIAGE_PROMPT.format(
        pruned_log_context=pruned_context,
        service_metadata_json=json.dumps(service_metadata),
    )
    try:
        return call_llm_agent(
            prompt=prompt,
            agent_name="sre-triage-severity-agent",
            role="Autonomous SRE incident severity classifier",
            goal="Classify server crash log severity as FATAL or ERROR.",
            instructions=TRIAGE_PROMPT,
            model_cls=SeverityOutput,
        )
    except Exception as exc:
        logger.error(f"Triage agent failed after retries: {exc}")
        raise AgentUnavailableError(str(exc)) from exc


def diagnose(pruned_context: str, service_metadata: dict) -> tuple[TriageLLMOutput, dict, float]:
    """Unified single-agent diagnosis for backwards-compatibility."""
    prompt = GOD_PROMPT.format(
        pruned_log_context=pruned_context,
        service_metadata_json=json.dumps(service_metadata),
    )
    try:
        return call_llm_agent(
            prompt=prompt,
            agent_name="sre-triage-agent",
            role="Autonomous SRE incident triage engine",
            goal="Diagnose root cause and propose remediation command.",
            instructions=GOD_PROMPT,
            model_cls=TriageLLMOutput,
        )
    except Exception as exc:
        logger.error(f"Triage agent failed after retries: {exc}")
        raise AgentUnavailableError(str(exc)) from exc
