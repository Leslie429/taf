"""Limitation de débit et révocation des jetons.

Revision ID: 0002
Revises: 0001
"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Tout jeton émis avant cette date est refusé. NULL signifie « jamais
    # déconnecté », ce qui vaut pour tous les comptes existants.
    op.add_column(
        "users",
        sa.Column("tokens_valid_from", sa.DateTime(timezone=True), nullable=True),
    )

    op.create_table(
        "rate_limit_counters",
        sa.Column("bucket", sa.String(length=160), nullable=False),
        sa.Column("window_start", sa.DateTime(timezone=True), nullable=False),
        sa.Column("count", sa.BigInteger(), nullable=False, server_default="0"),
        sa.PrimaryKeyConstraint("bucket", "window_start", name="pk_rate_limit"),
    )
    # Le ménage des fenêtres périmées se fait par cet index, jamais par un
    # balayage complet : la table grossit à chaque tentative refusée.
    op.create_index(
        "ix_rate_limit_window", "rate_limit_counters", ["window_start"]
    )


def downgrade() -> None:
    op.drop_index("ix_rate_limit_window", table_name="rate_limit_counters")
    op.drop_table("rate_limit_counters")
    op.drop_column("users", "tokens_valid_from")
