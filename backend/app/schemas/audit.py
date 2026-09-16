from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict

from app.models.enums import AuditAction, AuditOutcome


class AuditEventOut(BaseModel):
    """Une ligne du journal d'audit.

    `actor_phone` est recopié au moment des faits : il reste lisible même si
    le compte a disparu depuis, auquel cas `actor_id` vaut `null`.
    """

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    occurred_at: datetime
    actor_id: UUID | None
    actor_phone: str
    action: AuditAction
    outcome: AuditOutcome
    target_type: str
    target_id: UUID | None
    ip: str
    details: dict[str, Any]
