"""Notifications : les relances adressées aux membres.

Revision ID: 0006
Revises: 0005
"""
from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0006"
down_revision: str | None = "0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TS = sa.DateTime(timezone=True)
NOTIFICATION_KIND = ("contribution.late",)
NOTIFICATION_STATUS = ("pending", "sent", "failed")


def upgrade() -> None:
    postgresql.ENUM(*NOTIFICATION_KIND, name="notification_kind").create(
        op.get_bind(), checkfirst=True
    )
    postgresql.ENUM(*NOTIFICATION_STATUS, name="notification_status").create(
        op.get_bind(), checkfirst=True
    )

    op.create_table(
        "notifications",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "user_id",
            sa.Uuid(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        # create_type=False : les deux types viennent d'être créés ci-dessus.
        sa.Column(
            "kind",
            postgresql.ENUM(*NOTIFICATION_KIND, name="notification_kind", create_type=False),
            nullable=False,
        ),
        sa.Column(
            "status",
            postgresql.ENUM(
                *NOTIFICATION_STATUS, name="notification_status", create_type=False
            ),
            nullable=False,
            server_default="pending",
        ),
        # Le garde-fou contre le harcèlement : une relance par cotisation et
        # par jour, que la base fait respecter plutôt que le code appelant.
        sa.Column("dedupe_key", sa.String(120), nullable=False),
        sa.Column("destination", sa.String(20), nullable=False, server_default=""),
        sa.Column("body", sa.Text(), nullable=False, server_default=""),
        sa.Column(
            "contribution_id",
            sa.Uuid(),
            sa.ForeignKey("contributions.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("sent_at", TS, nullable=True),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("last_error", sa.String(300), nullable=True),
        sa.Column("created_at", TS, nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", TS, nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("dedupe_key", name="uq_notification_dedupe"),
    )
    op.create_index("ix_notification_user", "notifications", ["user_id"])
    op.create_index("ix_notification_status", "notifications", ["status"])


def downgrade() -> None:
    op.drop_table("notifications")
    postgresql.ENUM(name="notification_kind").drop(op.get_bind(), checkfirst=True)
    postgresql.ENUM(name="notification_status").drop(op.get_bind(), checkfirst=True)
