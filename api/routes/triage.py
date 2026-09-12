import asyncio
import time
from uuid import uuid4

from fastapi import APIRouter, HTTPException, status
from core.schemas import (
    IncidentRequest,
    TriageResponse,
    RemediationBlock,
    GovernanceBlock,
    TimingBlock,
    TokenUsageBlock,
    TriageLLMOutput,
)
from core.preprocessor import preprocess
from core.governance import evaluate_governance
from agents.triage_agent import diagnose, AgentUnavailableError
from utils.notifications import notify_on_call
from utils.logging_config import logger

router = APIRouter(prefix="/v1", tags=["triage"])


@router.post("/triage", response_model=TriageResponse, status_code=status.HTTP_200_OK)
async def triage_incident(req: IncidentRequest) -> TriageResponse:
    t_start = time.perf_counter()

    # Stage 1: Pre-processing
    prep_res = preprocess(req.log_payload, window=req.max_context_lines)
    context_str = prep_res.get("context")
    severity_detected = prep_res.get("severity")
    prep_ms = prep_res.get("preprocessing_ms", 0.0)

    incident_id = uuid4()
    service_metadata = {
        "service_name": req.service_name,
        "environment": req.environment,
    }

    if not context_str or not severity_detected:
        t_total = (time.perf_counter() - t_start) * 1000
        return TriageResponse(
            incident_id=incident_id,
            service_name=req.service_name,
            severity_detected="ERROR",
            root_cause="No FATAL or ERROR signatures detected in input logs.",
            confidence_score=0.0,
            explanation="Deterministic preprocessor scanned log payload and found no fatal or error anchors.",
            remediation=RemediationBlock(command=None, command_type="none", status="APPROVED"),
            governance=GovernanceBlock(guardrail_triggered=False),
            timing_ms=TimingBlock(
                preprocessing=round(prep_ms, 2),
                inference=0.0,
                governance=0.0,
                total=round(t_total, 2),
            ),
            token_usage=TokenUsageBlock(prompt_tokens=0, completion_tokens=0),
        )

    # Stage 2: Agentic Reasoning
    try:
        llm_output, token_usage, inf_ms = diagnose(context_str, service_metadata)
    except AgentUnavailableError as exc:
        logger.error(f"Agent unavailable during triage for {req.service_name}: {exc}")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Triage agent unavailable or failed to generate valid JSON diagnosis.",
        ) from exc

    # Stage 3: Governance Guardrails
    t_gov_start = time.perf_counter()
    remediation_block, governance_block = evaluate_governance(llm_output)
    gov_ms = (time.perf_counter() - t_gov_start) * 1000

    # Non-blocking escalation trigger on blocked command
    if remediation_block.status == "BLOCKED_ESCALATED":
        asyncio.create_task(
            notify_on_call(
                incident_id=incident_id,
                service_name=req.service_name,
                block_reason=remediation_block.block_reason or "Guardrail triggered",
            )
        )

    t_total = (time.perf_counter() - t_start) * 1000

    return TriageResponse(
        incident_id=incident_id,
        service_name=req.service_name,
        severity_detected=llm_output.severity_detected,
        root_cause=llm_output.root_cause,
        confidence_score=llm_output.confidence_score,
        explanation=llm_output.explanation,
        remediation=remediation_block,
        governance=governance_block,
        timing_ms=TimingBlock(
            preprocessing=round(prep_ms, 2),
            inference=round(inf_ms, 2),
            governance=round(gov_ms, 2),
            total=round(t_total, 2),
        ),
        token_usage=TokenUsageBlock(
            prompt_tokens=token_usage.get("prompt_tokens", 0),
            completion_tokens=token_usage.get("completion_tokens", 0),
        ),
    )
