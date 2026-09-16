"""Journal d'audit des actions qui engagent la plateforme.

Trois partis pris.

**Rien ne s'y modifie.** Le modèle ne porte pas `updated_at` : un événement
d'audit n'a pas de seconde version. Ce qui a été consigné l'a été.

**L'acteur est recopié, pas seulement référencé.** Un compte peut être
désactivé, renommé, supprimé un jour ; une ligne d'audit doit rester lisible
après. La clé étrangère sert aux jointures, le numéro recopié sert à la
lecture — et c'est lui qui survit.

**Les refus y figurent.** Une tentative de versement par quelqu'un qui n'y a
pas droit est le genre de fait qu'un journal existe pour retenir.
"""

from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import DateTime, ForeignKey, Index, String, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, UUIDMixin
from app.db.types import pg_enum
from app.models.enums import AuditAction, AuditOutcome


class AuditEvent(Base, UUIDMixin):
    __tablename__ = "audit_events"
    __table_args__ = (
        # Un journal se lit à l'envers, du plus récent au plus ancien.
        Index("ix_audit_occurred", "occurred_at"),
        Index("ix_audit_actor", "actor_id"),
        Index("ix_audit_action", "action"),
    )

    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    # `SET NULL` plutôt que `CASCADE` : la disparition d'un compte ne doit pas
    # emporter la trace de ce qu'il a fait.
    actor_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    actor_phone: Mapped[str] = mapped_column(String(20), default="")
    action: Mapped[AuditAction] = mapped_column(pg_enum(AuditAction, "audit_action"))
    outcome: Mapped[AuditOutcome] = mapped_column(
        pg_enum(AuditOutcome, "audit_outcome"), default=AuditOutcome.ALLOWED
    )
    target_type: Mapped[str] = mapped_column(String(30), default="")
    target_id: Mapped[UUID | None] = mapped_column(nullable=True)
    ip: Mapped[str] = mapped_column(String(45), default="")
    # Le détail de l'action : montant versé, position attribuée, motif du
    # refus. Libre par nature — ce qu'il faut retenir varie d'une action à
    # l'autre, et figer des colonnes obligerait à migrer à chaque ajout.
    details: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
