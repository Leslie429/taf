"""Schéma initial : utilisateurs, tontines, grand livre.

Revision ID: 0001
Revises:
"""
from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _enum(name: str, *values: str) -> postgresql.ENUM:
    # create_type=False : les types sont créés explicitement en tête d'upgrade,
    # sinon PostgreSQL tente de les recréer à chaque colonne qui les référence.
    return postgresql.ENUM(*values, name=name, create_type=False)


ENUMS: dict[str, tuple[str, ...]] = {
    "group_status": ("draft", "active", "completed", "cancelled"),
    "frequency": ("weekly", "biweekly", "monthly"),
    "membership_status": ("active", "left", "excluded"),
    "cycle_status": ("pending", "funded", "paid_out", "late"),
    "contribution_status": ("due", "processing", "paid", "failed"),
    "transaction_type": ("contribution", "payout", "reversal"),
    "transaction_status": ("pending", "processing", "success", "failed", "reversed"),
    "account_kind": ("user_wallet", "group_pot", "momo_clearing", "fees"),
    "entry_direction": ("debit", "credit"),
}

TS = sa.DateTime(timezone=True)


def upgrade() -> None:
    for name, values in ENUMS.items():
        postgresql.ENUM(*values, name=name).create(op.get_bind(), checkfirst=True)

    op.create_table(
        "users",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("phone", sa.String(20), nullable=False),
        sa.Column("full_name", sa.String(120), nullable=False),
        sa.Column("hashed_password", sa.String(255), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", TS, nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", TS, nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_users_phone", "users", ["phone"], unique=True)

    op.create_table(
        "tontine_groups",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("description", sa.String(500)),
        sa.Column("contribution_minor", sa.BigInteger(), nullable=False),
        sa.Column("currency", sa.String(3), nullable=False, server_default="XOF"),
        sa.Column("frequency", _enum("frequency", *ENUMS["frequency"]), nullable=False),
        sa.Column("start_date", sa.Date(), nullable=False),
        sa.Column(
            "status",
            _enum("group_status", *ENUMS["group_status"]),
            nullable=False,
            server_default="draft",
        ),
        sa.Column("created_by_id", sa.Uuid(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("created_at", TS, nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", TS, nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint("contribution_minor > 0", name="ck_group_contribution_positive"),
    )
    op.create_index("ix_tontine_groups_status", "tontine_groups", ["status"])

    op.create_table(
        "memberships",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "group_id",
            sa.Uuid(),
            sa.ForeignKey("tontine_groups.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("user_id", sa.Uuid(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("payout_position", sa.Integer(), nullable=False),
        sa.Column("is_admin", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column(
            "status",
            _enum("membership_status", *ENUMS["membership_status"]),
            nullable=False,
            server_default="active",
        ),
        sa.Column("created_at", TS, nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", TS, nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("group_id", "user_id", name="uq_membership_group_user"),
        sa.UniqueConstraint("group_id", "payout_position", name="uq_membership_group_position"),
        sa.CheckConstraint("payout_position > 0", name="ck_membership_position_positive"),
    )
    op.create_index("ix_memberships_group_id", "memberships", ["group_id"])
    op.create_index("ix_memberships_user_id", "memberships", ["user_id"])

    op.create_table(
        "cycles",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "group_id",
            sa.Uuid(),
            sa.ForeignKey("tontine_groups.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("index", sa.Integer(), nullable=False),
        sa.Column(
            "beneficiary_membership_id",
            sa.Uuid(),
            sa.ForeignKey("memberships.id"),
            nullable=False,
        ),
        sa.Column("due_date", sa.Date(), nullable=False),
        sa.Column(
            "status",
            _enum("cycle_status", *ENUMS["cycle_status"]),
            nullable=False,
            server_default="pending",
        ),
        sa.Column("created_at", TS, nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", TS, nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("group_id", "index", name="uq_cycle_group_index"),
    )
    op.create_index("ix_cycles_group_id", "cycles", ["group_id"])
    op.create_index("ix_cycles_due_date", "cycles", ["due_date"])
    op.create_index("ix_cycles_status", "cycles", ["status"])

    op.create_table(
        "accounts",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("kind", _enum("account_kind", *ENUMS["account_kind"]), nullable=False),
        sa.Column("owner_id", sa.Uuid()),
        sa.Column("currency", sa.String(3), nullable=False, server_default="XOF"),
        sa.Column("label", sa.String(120), nullable=False),
        sa.Column("created_at", TS, nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", TS, nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("kind", "owner_id", name="uq_account_kind_owner"),
    )
    op.create_index("ix_accounts_owner_id", "accounts", ["owner_id"])

    op.create_table(
        "transactions",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("reference", sa.String(40), nullable=False),
        sa.Column("idempotency_key", sa.String(80), nullable=False),
        sa.Column("type", _enum("transaction_type", *ENUMS["transaction_type"]), nullable=False),
        sa.Column(
            "status",
            _enum("transaction_status", *ENUMS["transaction_status"]),
            nullable=False,
            server_default="pending",
        ),
        sa.Column("amount_minor", sa.BigInteger(), nullable=False),
        sa.Column("currency", sa.String(3), nullable=False, server_default="XOF"),
        sa.Column("provider", sa.String(30)),
        sa.Column("external_id", sa.String(120)),
        sa.Column("failure_reason", sa.String(255)),
        sa.Column("created_at", TS, nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", TS, nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("idempotency_key", name="uq_transaction_idempotency"),
        sa.CheckConstraint("amount_minor > 0", name="ck_transaction_amount_positive"),
    )
    op.create_index("ix_transactions_reference", "transactions", ["reference"], unique=True)
    op.create_index("ix_transactions_status", "transactions", ["status"])
    op.create_index(
        "ix_transaction_external", "transactions", ["provider", "external_id"], unique=True
    )

    op.create_table(
        "ledger_entries",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "transaction_id",
            sa.Uuid(),
            sa.ForeignKey("transactions.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("account_id", sa.Uuid(), sa.ForeignKey("accounts.id"), nullable=False),
        sa.Column(
            "direction", _enum("entry_direction", *ENUMS["entry_direction"]), nullable=False
        ),
        sa.Column("amount_minor", sa.BigInteger(), nullable=False),
        sa.Column("created_at", TS, nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", TS, nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint("amount_minor > 0", name="ck_entry_amount_positive"),
    )
    op.create_index("ix_ledger_entries_transaction_id", "ledger_entries", ["transaction_id"])
    op.create_index("ix_ledger_entries_account_id", "ledger_entries", ["account_id"])
    op.create_index("ix_entry_account_created", "ledger_entries", ["account_id", "created_at"])

    op.create_table(
        "contributions",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "cycle_id", sa.Uuid(), sa.ForeignKey("cycles.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("membership_id", sa.Uuid(), sa.ForeignKey("memberships.id"), nullable=False),
        sa.Column("amount_minor", sa.BigInteger(), nullable=False),
        sa.Column(
            "status",
            _enum("contribution_status", *ENUMS["contribution_status"]),
            nullable=False,
            server_default="due",
        ),
        sa.Column("transaction_id", sa.Uuid(), sa.ForeignKey("transactions.id")),
        sa.Column("created_at", TS, nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", TS, nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("cycle_id", "membership_id", name="uq_contribution_cycle_member"),
    )
    op.create_index("ix_contributions_cycle_id", "contributions", ["cycle_id"])
    op.create_index("ix_contributions_membership_id", "contributions", ["membership_id"])
    op.create_index("ix_contributions_status", "contributions", ["status"])

    op.create_table(
        "webhook_events",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("provider", sa.String(30), nullable=False),
        sa.Column("event_id", sa.String(120), nullable=False),
        sa.Column("signature_valid", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("payload", postgresql.JSONB(), nullable=False),
        sa.Column("processed", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("last_error", sa.String(500)),
        sa.Column("created_at", TS, nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", TS, nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("provider", "event_id", name="uq_webhook_provider_event"),
    )
    op.create_index("ix_webhook_events_processed", "webhook_events", ["processed"])


def downgrade() -> None:
    for table in (
        "webhook_events",
        "contributions",
        "ledger_entries",
        "transactions",
        "accounts",
        "cycles",
        "memberships",
        "tontine_groups",
        "users",
    ):
        op.drop_table(table)

    for name in ENUMS:
        postgresql.ENUM(name=name).drop(op.get_bind(), checkfirst=True)
