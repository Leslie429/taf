from typing import Any
from uuid import UUID

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    ForeignKey,
    Index,
    String,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDMixin
from app.db.types import pg_enum
from app.models.enums import (
    AccountKind,
    EntryDirection,
    TransactionStatus,
    TransactionType,
)


class Account(Base, UUIDMixin, TimestampMixin):
    """Un compte du grand livre. Le solde n'est jamais stocké : il se calcule
    à partir des écritures, ce qui rend toute divergence impossible."""

    __tablename__ = "accounts"
    __table_args__ = (
        UniqueConstraint("kind", "owner_id", name="uq_account_kind_owner"),
    )

    kind: Mapped[AccountKind] = mapped_column(pg_enum(AccountKind, "account_kind"))
    # NULL pour les comptes globaux de la plateforme (clearing, commissions).
    owner_id: Mapped[UUID | None] = mapped_column(nullable=True, index=True)
    currency: Mapped[str] = mapped_column(String(3), default="XOF")
    label: Mapped[str] = mapped_column(String(120))


class Transaction(Base, UUIDMixin, TimestampMixin):
    """Un mouvement financier, toujours composé d'au moins deux écritures équilibrées."""

    __tablename__ = "transactions"
    __table_args__ = (
        # Rejouer la même requête ne crée jamais un second débit.
        UniqueConstraint("idempotency_key", name="uq_transaction_idempotency"),
        CheckConstraint("amount_minor > 0", name="ck_transaction_amount_positive"),
        Index("ix_transaction_external", "provider", "external_id", unique=True),
    )

    reference: Mapped[str] = mapped_column(String(40), unique=True, index=True)
    idempotency_key: Mapped[str] = mapped_column(String(80))

    type: Mapped[TransactionType] = mapped_column(pg_enum(TransactionType, "transaction_type"))
    status: Mapped[TransactionStatus] = mapped_column(
        pg_enum(TransactionStatus, "transaction_status"),
        default=TransactionStatus.PENDING,
        index=True,
    )

    amount_minor: Mapped[int] = mapped_column(BigInteger)
    currency: Mapped[str] = mapped_column(String(3), default="XOF")

    provider: Mapped[str | None] = mapped_column(String(30), nullable=True)
    external_id: Mapped[str | None] = mapped_column(String(120), nullable=True)
    failure_reason: Mapped[str | None] = mapped_column(String(255), nullable=True)

    entries: Mapped[list["LedgerEntry"]] = relationship(
        back_populates="transaction", cascade="all, delete-orphan"
    )


class LedgerEntry(Base, UUIDMixin, TimestampMixin):
    """Une écriture. Immuable : on ne modifie jamais une ligne, on contrepasse."""

    __tablename__ = "ledger_entries"
    __table_args__ = (
        CheckConstraint("amount_minor > 0", name="ck_entry_amount_positive"),
        Index("ix_entry_account_created", "account_id", "created_at"),
    )

    transaction_id: Mapped[UUID] = mapped_column(
        ForeignKey("transactions.id", ondelete="CASCADE"), index=True
    )
    account_id: Mapped[UUID] = mapped_column(ForeignKey("accounts.id"), index=True)
    direction: Mapped[EntryDirection] = mapped_column(pg_enum(EntryDirection, "entry_direction"))
    amount_minor: Mapped[int] = mapped_column(BigInteger)

    transaction: Mapped[Transaction] = relationship(back_populates="entries")


class WebhookEvent(Base, UUIDMixin, TimestampMixin):
    """Journal des callbacks opérateur. La contrainte d'unicité rend le rejeu inoffensif."""

    __tablename__ = "webhook_events"
    __table_args__ = (
        UniqueConstraint("provider", "event_id", name="uq_webhook_provider_event"),
    )

    provider: Mapped[str] = mapped_column(String(30))
    event_id: Mapped[str] = mapped_column(String(120))
    signature_valid: Mapped[bool] = mapped_column(default=False)
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB)
    processed: Mapped[bool] = mapped_column(default=False, index=True)
    attempts: Mapped[int] = mapped_column(default=0)
    last_error: Mapped[str | None] = mapped_column(String(500), nullable=True)
