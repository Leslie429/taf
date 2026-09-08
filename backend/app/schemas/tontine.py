from datetime import date
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.models.enums import (
    ContributionStatus,
    CycleStatus,
    Frequency,
    GroupStatus,
)


class GroupCreate(BaseModel):
    name: str = Field(min_length=2, max_length=120)
    description: str | None = Field(default=None, max_length=500)
    # En XOF il n'y a pas de sous-unité : 5000 signifie 5 000 francs.
    contribution_minor: int = Field(gt=0, examples=[5000])
    frequency: Frequency
    start_date: date


class MemberAdd(BaseModel):
    phone: str
    payout_position: int | None = Field(default=None, gt=0)


class MemberOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    user_id: UUID
    payout_position: int
    is_admin: bool


class GroupOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    description: str | None
    contribution_minor: int
    currency: str
    frequency: Frequency
    start_date: date
    status: GroupStatus


class ContributionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    membership_id: UUID
    amount_minor: int
    status: ContributionStatus
    transaction_id: UUID | None


class CycleOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    index: int
    beneficiary_membership_id: UUID
    due_date: date
    status: CycleStatus
    contributions: list[ContributionOut] = []


class BalanceOut(BaseModel):
    account_id: UUID
    balance_minor: int
    currency: str
