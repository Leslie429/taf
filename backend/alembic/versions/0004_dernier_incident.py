"""Nature du dernier incident d'appel sur une transaction.

Revision ID: 0004
Revises: 0003
"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0004"
down_revision: str | None = "0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Une transaction bloquée en cours doit dire pourquoi. Sans cette colonne,
    # l'explication n'existe que dans les journaux de l'hébergeur — hors de
    # portée d'un rapprochement, et parfois hors de portée tout court.
    op.add_column(
        "transactions",
        sa.Column("last_incident", sa.String(length=255), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("transactions", "last_incident")
