import json
from backend.agents.base_agent import call_llm_agent, AgentUnavailableError
from backend.agents.prompts import DIAGNOSTIC_PROMPT
from backend.core.schemas import DiagnosticAgentOutput
from backend.utils.logging_config import logger


def diagnose_root_cause(
    pruned_context: str, service_metadata: dict, severity_detected: str = "FATAL"
) -> tuple[DiagnosticAgentOutput, dict, float]:
    prompt = DIAGNOSTIC_PROMPT.format(
        severity_detected=severity_detected,
        pruned_log_context=pruned_context,
        service_metadata_json=json.dumps(service_metadata),
    )
    try:
        return call_llm_agent(
            prompt=prompt,
            agent_name="sre-diagnostic-agent",
            role="Autonomous SRE root cause diagnosis engine",
            goal="Identify root cause, confidence score, and explanation for incident context.",
            instructions=DIAGNOSTIC_PROMPT,
            model_cls=DiagnosticAgentOutput,
        )
    except Exception as exc:
        logger.error(f"Diagnostic agent failed after retries: {exc}")
        raise AgentUnavailableError(str(exc)) from exc
