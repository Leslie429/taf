from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict

from app.models.enums import NotificationKind, NotificationStatus


class NotificationOut(BaseModel):
    """Une relance adressée au membre.

    `status` dit ce qu'il en est de l'acheminement, pas de la cotisation :
    `failed` signale un SMS qui n'est pas parti, pas un paiement refusé.
    """

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    kind: NotificationKind
    status: NotificationStatus
    body: str
    contribution_id: UUID | None
    created_at: datetime
    sent_at: datetime | None
