"""Ce que la plateforme a dit à ses membres, et par quel canal.

Une notification est une **trace avant d'être un message**. Elle existe en base
avant de partir, y reste si l'envoi échoue, et porte une clé de
dédoublonnement qui interdit de la produire deux fois.

Cette clé est le même dispositif que celle des transactions : ce qui empêche
une relance de partir en double n'est pas la prudence du code appelant, c'est
une contrainte d'unicité que la base fait respecter.
"""

from datetime import datetime
from uuid import UUID

from sqlalchemy import DateTime, ForeignKey, Index, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UUIDMixin
from app.db.types import pg_enum
from app.models.enums import NotificationKind, NotificationStatus


class Notification(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "notifications"
    __table_args__ = (
        # Le garde-fou contre le harcèlement : une relance par cotisation et
        # par jour, quoi qu'il arrive au code qui la demande.
        UniqueConstraint("dedupe_key", name="uq_notification_dedupe"),
        Index("ix_notification_user", "user_id"),
        Index("ix_notification_status", "status"),
    )

    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    kind: Mapped[NotificationKind] = mapped_column(
        pg_enum(NotificationKind, "notification_kind")
    )
    status: Mapped[NotificationStatus] = mapped_column(
        pg_enum(NotificationStatus, "notification_status"),
        default=NotificationStatus.PENDING,
    )
    # « relance:contribution:<uuid>:2026-09-16 » — l'opération et sa journée.
    dedupe_key: Mapped[str] = mapped_column(String(120))
    # Le numéro visé, recopié : il peut changer, le message est parti sur
    # celui-là.
    destination: Mapped[str] = mapped_column(String(20), default="")
    body: Mapped[str] = mapped_column(Text, default="")
    contribution_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("contributions.id", ondelete="SET NULL"), nullable=True
    )
    sent_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    attempts: Mapped[int] = mapped_column(default=0)
    last_error: Mapped[str | None] = mapped_column(String(300), nullable=True)
