from datetime import date
from uuid import UUID

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    Date,
    ForeignKey,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDMixin
from app.db.types import pg_enum
from app.models.enums import (
    ContributionStatus,
    CycleStatus,
    Frequency,
    GroupStatus,
    MembershipStatus,
)


class TontineGroup(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "tontine_groups"
    __table_args__ = (
        CheckConstraint("contribution_minor > 0", name="ck_group_contribution_positive"),
    )

    name: Mapped[str] = mapped_column(String(120))
    description: Mapped[str | None] = mapped_column(String(500), nullable=True)
    contribution_minor: Mapped[int] = mapped_column(BigInteger)
    currency: Mapped[str] = mapped_column(String(3), default="XOF")
    frequency: Mapped[Frequency] = mapped_column(pg_enum(Frequency, "frequency"))
    start_date: Mapped[date] = mapped_column(Date)
    status: Mapped[GroupStatus] = mapped_column(
        pg_enum(GroupStatus, "group_status"), default=GroupStatus.DRAFT, index=True
    )
    created_by_id: Mapped[UUID] = mapped_column(ForeignKey("users.id"))

    memberships: Mapped[list["Membership"]] = relationship(
        back_populates="group", cascade="all, delete-orphan"
    )
    cycles: Mapped[list["Cycle"]] = relationship(
        back_populates="group", cascade="all, delete-orphan"
    )


class Membership(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "memberships"
    __table_args__ = (
        UniqueConstraint("group_id", "user_id", name="uq_membership_group_user"),
        # Deux membres ne peuvent pas occuper le même rang de versement.
        UniqueConstraint("group_id", "payout_position", name="uq_membership_group_position"),
        CheckConstraint("payout_position > 0", name="ck_membership_position_positive"),
    )

    group_id: Mapped[UUID] = mapped_column(
        ForeignKey("tontine_groups.id", ondelete="CASCADE"), index=True
    )
    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id"), index=True)
    payout_position: Mapped[int] = mapped_column()
    is_admin: Mapped[bool] = mapped_column(default=False)
    status: Mapped[MembershipStatus] = mapped_column(
        pg_enum(MembershipStatus, "membership_status"), default=MembershipStatus.ACTIVE
    )

    group: Mapped[TontineGroup] = relationship(back_populates="memberships")


class Cycle(Base, UUIDMixin, TimestampMixin):
    """Un tour de tontine : tout le monde cotise, un membre encaisse."""

    __tablename__ = "cycles"
    __table_args__ = (
        UniqueConstraint("group_id", "index", name="uq_cycle_group_index"),
    )

    group_id: Mapped[UUID] = mapped_column(
        ForeignKey("tontine_groups.id", ondelete="CASCADE"), index=True
    )
    index: Mapped[int] = mapped_column()
    beneficiary_membership_id: Mapped[UUID] = mapped_column(ForeignKey("memberships.id"))
    due_date: Mapped[date] = mapped_column(Date, index=True)
    status: Mapped[CycleStatus] = mapped_column(
        pg_enum(CycleStatus, "cycle_status"), default=CycleStatus.PENDING, index=True
    )

    group: Mapped[TontineGroup] = relationship(back_populates="cycles")
    contributions: Mapped[list["Contribution"]] = relationship(
        back_populates="cycle", cascade="all, delete-orphan"
    )


class Contribution(Base, UUIDMixin, TimestampMixin):
    """Ce qu'un membre doit pour un cycle donné."""

    __tablename__ = "contributions"
    __table_args__ = (
        UniqueConstraint("cycle_id", "membership_id", name="uq_contribution_cycle_member"),
    )

    cycle_id: Mapped[UUID] = mapped_column(ForeignKey("cycles.id", ondelete="CASCADE"), index=True)
    membership_id: Mapped[UUID] = mapped_column(ForeignKey("memberships.id"), index=True)
    amount_minor: Mapped[int] = mapped_column(BigInteger)
    status: Mapped[ContributionStatus] = mapped_column(
        pg_enum(ContributionStatus, "contribution_status"),
        default=ContributionStatus.DUE,
        index=True,
    )
    transaction_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("transactions.id"), nullable=True
    )

    cycle: Mapped[Cycle] = relationship(back_populates="contributions")
