import asyncio
import time
from uuid import uuid4

from fastapi import APIRouter, HTTPException, status
from backend.core.schemas import (
    IncidentRequest,
    TriageResponse,
    RemediationBlock,
    GovernanceBlock,
    TimingBlock,
    TokenUsageBlock,
    PostMortemBlock,
)
from backend.core.preprocessor import preprocess
from backend.core.governance import evaluate_governance
from backend.agents.triage_agent import classify_severity, AgentUnavailableError
from backend.agents.diagnostic_agent import diagnose_root_cause
from backend.agents.remediation_agent import generate_remediation
from backend.agents.post_mortem_agent import generate_post_mortem
from backend.utils.notifications import notify_on_call
from backend.utils.logging_config import logger

router = APIRouter(prefix="/v1", tags=["triage"])


@router.post("/triage", response_model=TriageResponse, status_code=status.HTTP_200_OK)
async def triage_incident(req: IncidentRequest) -> TriageResponse:
    t_start = time.perf_counter()

    # Stage 1: Pre-processing (Polars)
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
            remediation=RemediationBlock(
                command=None,
                command_type="none",
                status="APPROVED",
                runbook_steps=["No action required. All system metrics and log anchors report normal operational state."],
            ),
            post_mortem=PostMortemBlock(
                summary="No error anchor identified.",
                contributing_factors=["Input log dump did not match error/fatal criteria."],
                preventive_actions=["Maintain normal operational logging."],
                impact_assessment="Zero impact detected.",
            ),
            governance=GovernanceBlock(guardrail_triggered=False),
            timing_ms=TimingBlock(
                preprocessing=round(prep_ms, 2),
                inference=0.0,
                governance=0.0,
                total=round(t_total, 2),
            ),
            token_usage=TokenUsageBlock(prompt_tokens=0, completion_tokens=0),
        )

    # Stage 2: Multi-Agent Triad Sequential Execution
    try:
        # Agent 1: Triage Agent (Severity Classification)
        severity_out, usage1, t_sev = classify_severity(context_str, service_metadata)

        # Agent 2: Diagnostic Agent (Root Cause Analysis)
        diag_out, usage2, t_diag = diagnose_root_cause(
            context_str, service_metadata, severity_detected=severity_out.severity_detected
        )

        # Agent 3: Remediation Agent (Runbook & Command Generation)
        rem_out, usage3, t_rem = generate_remediation(
            context_str,
            service_metadata,
            root_cause=diag_out.root_cause,
            explanation=diag_out.explanation,
        )

        # Agent 4: Post-Mortem Agent (Blameless RCA Report)
        post_mortem_out, usage4, t_pm = generate_post_mortem(
            context_str,
            service_metadata,
            severity_detected=severity_out.severity_detected,
            root_cause=diag_out.root_cause,
            explanation=diag_out.explanation,
            remediation_command=rem_out.remediation_command,
        )

        inf_ms = t_sev + t_diag + t_rem + t_pm
        prompt_tokens = usage1.get("prompt_tokens", 0) + usage2.get("prompt_tokens", 0) + usage3.get("prompt_tokens", 0) + usage4.get("prompt_tokens", 0)
        completion_tokens = usage1.get("completion_tokens", 0) + usage2.get("completion_tokens", 0) + usage3.get("completion_tokens", 0) + usage4.get("completion_tokens", 0)

    except AgentUnavailableError as exc:
        logger.error(f"Agent triad unavailable during triage for {req.service_name}: {exc}")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Triage agent triad unavailable or failed to generate valid JSON output.",
        ) from exc

    # Stage 3: Governance Guardrails
    t_gov_start = time.perf_counter()
    remediation_block, governance_block = evaluate_governance(rem_out)
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
        severity_detected=severity_out.severity_detected,
        root_cause=diag_out.root_cause,
        confidence_score=diag_out.confidence_score,
        explanation=diag_out.explanation,
        remediation=remediation_block,
        post_mortem=post_mortem_out,
        governance=governance_block,
        timing_ms=TimingBlock(
            preprocessing=round(prep_ms, 2),
            inference=round(inf_ms, 2),
            governance=round(gov_ms, 2),
            total=round(t_total, 2),
        ),
        token_usage=TokenUsageBlock(
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
        ),
    )
