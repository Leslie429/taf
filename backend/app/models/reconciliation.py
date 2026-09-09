"""Journal des rapprochements entre le grand livre et le relevé opérateur.

Un rapprochement ne corrige pas en silence : chaque écart laisse une ligne,
qu'il ait été résolu ou non. Une comptabilité qui se répare sans trace ne vaut
pas mieux qu'une comptabilité fausse.
"""

from datetime import datetime
from uuid import UUID

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDMixin
from app.db.types import pg_enum
from app.models.enums import DivergenceKind, TransactionStatus


class ReconciliationRun(Base, UUIDMixin):
    __tablename__ = "reconciliation_runs"

    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    finished_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    examined: Mapped[int] = mapped_column(Integer, default=0)

    divergences: Mapped[list["Divergence"]] = relationship(
        back_populates="run", cascade="all, delete-orphan"
    )


class Divergence(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "reconciliation_divergences"
    __table_args__ = (
        Index("ix_divergence_run", "run_id"),
        Index("ix_divergence_transaction", "transaction_id"),
        Index("ix_divergence_kind", "kind"),
    )

    run_id: Mapped[UUID] = mapped_column(
        ForeignKey("reconciliation_runs.id", ondelete="CASCADE")
    )
    transaction_id: Mapped[UUID] = mapped_column(ForeignKey("transactions.id"))
    kind: Mapped[DivergenceKind] = mapped_column(pg_enum(DivergenceKind, "divergence_kind"))
    # L'état des deux côtés au moment du constat : un écart se relit des mois
    # plus tard, quand les statuts ont bougé.
    local_status: Mapped[TransactionStatus] = mapped_column(
        pg_enum(TransactionStatus, "transaction_status")
    )
    operator_status: Mapped[str] = mapped_column(String(40), default="")
    # Un écart résolu l'a été en appliquant le verdict de l'opérateur.
    resolved: Mapped[bool] = mapped_column(Boolean, default=False)
    note: Mapped[str | None] = mapped_column(String(300), nullable=True)

    run: Mapped[ReconciliationRun] = relationship(back_populates="divergences")
