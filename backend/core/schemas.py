from __future__ import annotations

from typing import Literal
from uuid import UUID, uuid4
from pydantic import BaseModel, Field

Environment = Literal["dev", "staging", "prod"]
Severity = Literal["FATAL", "ERROR"]
CommandType = Literal["shell", "kubectl", "sql", "http", "none"]
RemediationStatus = Literal["APPROVED", "BLOCKED_ESCALATED"]


class IncidentRequest(BaseModel):
    service_name: str = Field(min_length=1, max_length=128)
    environment: Environment
    log_payload: str = Field(min_length=1, max_length=2_000_000)
    max_context_lines: int = Field(default=10, ge=1, le=50)


class SeverityOutput(BaseModel):
    """Output from Triage Agent (Severity Classification)."""

    severity_detected: Severity
    severity_reasoning: str = Field(default="Standard severity classification from log signatures.", max_length=500)


class DiagnosticAgentOutput(BaseModel):
    """Output from Diagnostic Agent (Root Cause Diagnosis)."""

    root_cause: str = Field(max_length=280)
    confidence_score: float = Field(ge=0.0, le=1.0)
    explanation: str = Field(max_length=500)


class RemediationAgentOutput(BaseModel):
    """Output from Remediation Agent (Runbook & Command Generation)."""

    remediation_command: str
    command_type: CommandType
    requires_human_approval: bool
    runbook_steps: list[str] = Field(default_factory=list)


class PostMortemBlock(BaseModel):
    """Output from Post-Mortem Agent (Blameless RCA Report)."""

    summary: str = Field(default="", max_length=500)
    contributing_factors: list[str] = Field(default_factory=list)
    preventive_actions: list[str] = Field(default_factory=list)
    impact_assessment: str = Field(default="", max_length=500)


class TriageLLMOutput(BaseModel):
    """Unified LLM output schema before governance runs."""

    severity_detected: Severity
    root_cause: str = Field(max_length=280)
    confidence_score: float = Field(ge=0.0, le=1.0)
    explanation: str = Field(max_length=500)
    remediation_command: str
    command_type: CommandType
    requires_human_approval: bool


class RemediationBlock(BaseModel):
    command: str | None
    command_type: CommandType
    status: RemediationStatus
    block_reason: str | None = None
    runbook_steps: list[str] = Field(default_factory=list)


class GovernanceBlock(BaseModel):
    guardrail_triggered: bool
    matched_denylist_pattern: str | None = None
    allowlist_verb: str | None = None


class TimingBlock(BaseModel):
    preprocessing: float
    inference: float
    governance: float
    total: float


class TokenUsageBlock(BaseModel):
    prompt_tokens: int
    completion_tokens: int


class TriageResponse(BaseModel):
    incident_id: UUID = Field(default_factory=uuid4)
    service_name: str
    severity_detected: Severity
    root_cause: str
    confidence_score: float
    explanation: str
    remediation: RemediationBlock
    post_mortem: PostMortemBlock
    governance: GovernanceBlock
    timing_ms: TimingBlock
    token_usage: TokenUsageBlock
