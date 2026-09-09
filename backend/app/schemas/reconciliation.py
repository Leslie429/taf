from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict

from app.models.enums import DivergenceKind, TransactionStatus


class DivergenceOut(BaseModel):
    """Un écart constaté entre le grand livre et le relevé de l'opérateur."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    transaction_id: UUID
    kind: DivergenceKind
    local_status: TransactionStatus
    operator_status: str
    resolved: bool
    note: str | None


class ReconciliationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    started_at: datetime
    finished_at: datetime | None
    examined: int
    divergences: list[DivergenceOut]
