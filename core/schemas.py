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


class TriageLLMOutput(BaseModel):
    """What we require directly out of the LLM, before governance runs."""

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
    governance: GovernanceBlock
    timing_ms: TimingBlock
    token_usage: TokenUsageBlock
