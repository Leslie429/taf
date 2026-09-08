from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict

from app.models.enums import TransactionStatus, TransactionType


class TransactionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    reference: str
    type: TransactionType
    status: TransactionStatus
    amount_minor: int
    currency: str
    external_id: str | None
    failure_reason: str | None


class MoMoCallback(BaseModel):
    """Charge utile d'un callback MTN MoMo (forme simplifiée du sandbox)."""

    externalId: str  # noqa: N815 — nom imposé par l'opérateur
    status: str
    financialTransactionId: str | None = None  # noqa: N815
    reason: dict[str, Any] | str | None = None
