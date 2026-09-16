"""Journal d'audit des actions qui engagent la plateforme.

Revision ID: 0005
Revises: 0004
"""
from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0005"
down_revision: str | None = "0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TS = sa.DateTime(timezone=True)
AUDIT_ACTION = (
    "group.created",
    "group.member_added",
    "group.activated",
    "cycle.paid_out",
    "reconciliation.launched",
)
AUDIT_OUTCOME = ("allowed", "denied")


def upgrade() -> None:
    postgresql.ENUM(*AUDIT_ACTION, name="audit_action").create(op.get_bind(), checkfirst=True)
    postgresql.ENUM(*AUDIT_OUTCOME, name="audit_outcome").create(op.get_bind(), checkfirst=True)

    op.create_table(
        "audit_events",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("occurred_at", TS, nullable=False, server_default=sa.func.now()),
        # SET NULL : la disparition d'un compte ne doit pas emporter la trace
        # de ce qu'il a fait.
        sa.Column(
            "actor_id",
            sa.Uuid(),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        # Recopié, et non seulement référencé : une ligne d'audit doit rester
        # lisible quand le compte n'existe plus.
        sa.Column("actor_phone", sa.String(20), nullable=False, server_default=""),
        # create_type=False : les deux types viennent d'être créés ci-dessus.
        sa.Column(
            "action",
            postgresql.ENUM(*AUDIT_ACTION, name="audit_action", create_type=False),
            nullable=False,
        ),
        sa.Column(
            "outcome",
            postgresql.ENUM(*AUDIT_OUTCOME, name="audit_outcome", create_type=False),
            nullable=False,
            server_default="allowed",
        ),
        sa.Column("target_type", sa.String(30), nullable=False, server_default=""),
        sa.Column("target_id", sa.Uuid(), nullable=True),
        sa.Column("ip", sa.String(45), nullable=False, server_default=""),
        sa.Column(
            "details",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default="{}",
        ),
    )
    # Un journal se lit à l'envers, du plus récent au plus ancien.
    op.create_index("ix_audit_occurred", "audit_events", ["occurred_at"])
    op.create_index("ix_audit_actor", "audit_events", ["actor_id"])
    op.create_index("ix_audit_action", "audit_events", ["action"])


def downgrade() -> None:
    op.drop_table("audit_events")
    postgresql.ENUM(name="audit_action").drop(op.get_bind(), checkfirst=True)
    postgresql.ENUM(name="audit_outcome").drop(op.get_bind(), checkfirst=True)
