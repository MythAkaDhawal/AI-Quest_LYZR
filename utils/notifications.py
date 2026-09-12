import logging
from uuid import UUID

logger = logging.getLogger("sre_triage.escalation")


async def notify_on_call(incident_id: UUID, service_name: str, block_reason: str) -> None:
    """Non-blocking escalation protocol.

    Logs structured WARNING for blocked/escalated remediation commands. Can be
    extended to fire real Slack/PagerDuty webhooks.
    """
    logger.warning(
        f"[ESCALATION REQUIRED] Incident ID: {incident_id} | Service: {service_name} | Reason: {block_reason}"
    )
