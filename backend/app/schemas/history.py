from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel

from app.models.enums import TransactionStatus, TransactionType


class HistoryItem(BaseModel):
    """Un mouvement vu du côté de l'utilisateur, pas du grand livre.

    `direction` traduit le sens pour la personne : « out » quand elle cotise,
    « in » quand elle encaisse la cagnotte de son tour.
    """

    id: UUID
    reference: str
    type: TransactionType
    status: TransactionStatus
    amount_minor: int
    currency: str
    created_at: datetime
    direction: Literal["in", "out"]
    group_id: UUID
    group_name: str
    cycle_index: int
