import json
from backend.agents.base_agent import call_llm_agent, AgentUnavailableError
from backend.agents.prompts import POST_MORTEM_PROMPT
from backend.core.schemas import PostMortemBlock
from backend.utils.logging_config import logger


def generate_post_mortem(
    pruned_context: str,
    service_metadata: dict,
    severity_detected: str,
    root_cause: str,
    explanation: str,
    remediation_command: str,
) -> tuple[PostMortemBlock, dict, float]:
    prompt = POST_MORTEM_PROMPT.format(
        service_name=service_metadata.get("service_name", "unknown"),
        environment=service_metadata.get("environment", "unknown"),
        severity_detected=severity_detected,
        root_cause=root_cause,
        explanation=explanation,
        remediation_command=remediation_command or "None",
        pruned_log_context=pruned_context,
    )
    try:
        return call_llm_agent(
            prompt=prompt,
            agent_name="sre-post-mortem-agent",
            role="Autonomous SRE blameless post-mortem RCA analyst",
            goal="Generate blameless post-mortem summary, contributing factors, preventive actions, and impact assessment.",
            instructions=POST_MORTEM_PROMPT,
            model_cls=PostMortemBlock,
        )
    except Exception as exc:
        logger.error(f"Post-mortem agent failed after retries: {exc}")
        raise AgentUnavailableError(str(exc)) from exc
