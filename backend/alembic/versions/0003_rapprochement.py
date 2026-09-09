"""Journal des rapprochements entre le grand livre et le relevé opérateur.

Revision ID: 0003
Revises: 0002
"""
from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TS = sa.DateTime(timezone=True)
DIVERGENCE_KIND = (
    "unconfirmed",
    "disputed_success",
    "unknown_at_operator",
    "operator_silent",
)


def upgrade() -> None:
    # Membre de l'équipe de la plateforme : le rapprochement expose l'état de
    # toutes les tontines, pas seulement celles où l'on cotise.
    op.add_column(
        "users",
        sa.Column("is_staff", sa.Boolean(), nullable=False, server_default=sa.false()),
    )

    postgresql.ENUM(*DIVERGENCE_KIND, name="divergence_kind").create(
        op.get_bind(), checkfirst=True
    )

    op.create_table(
        "reconciliation_runs",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("started_at", TS, nullable=False, server_default=sa.func.now()),
        sa.Column("finished_at", TS, nullable=True),
        sa.Column("examined", sa.Integer(), nullable=False, server_default="0"),
    )

    op.create_table(
        "reconciliation_divergences",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "run_id",
            sa.Uuid(),
            sa.ForeignKey("reconciliation_runs.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "transaction_id", sa.Uuid(), sa.ForeignKey("transactions.id"), nullable=False
        ),
        # create_type=False : le type vient d'être créé ci-dessus, et 0001 a
        # déjà créé transaction_status.
        sa.Column(
            "kind",
            postgresql.ENUM(*DIVERGENCE_KIND, name="divergence_kind", create_type=False),
            nullable=False,
        ),
        sa.Column(
            "local_status",
            postgresql.ENUM(name="transaction_status", create_type=False),
            nullable=False,
        ),
        sa.Column("operator_status", sa.String(40), nullable=False, server_default=""),
        sa.Column("resolved", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("note", sa.String(300), nullable=True),
        sa.Column("created_at", TS, nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", TS, nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_divergence_run", "reconciliation_divergences", ["run_id"])
    op.create_index("ix_divergence_transaction", "reconciliation_divergences", ["transaction_id"])
    op.create_index("ix_divergence_kind", "reconciliation_divergences", ["kind"])


def downgrade() -> None:
    op.drop_column("users", "is_staff")
    op.drop_table("reconciliation_divergences")
    op.drop_table("reconciliation_runs")
    postgresql.ENUM(name="divergence_kind").drop(op.get_bind(), checkfirst=True)
