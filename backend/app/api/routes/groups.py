from uuid import UUID

from fastapi import APIRouter, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.api.deps import CurrentUser, DbSession
from app.models.enums import AccountKind, GroupStatus, MembershipStatus
from app.models.tontine import Cycle, Membership, TontineGroup
from app.models.user import User
from app.schemas.tontine import (
    BalanceOut,
    CycleOut,
    GroupCreate,
    GroupOut,
    MemberAdd,
    MemberOut,
)
from app.services import ledger, tontine

router = APIRouter(prefix="/groups", tags=["groupes"])


def _membership_or_403(db: DbSession, group_id: UUID, user: User) -> Membership:
    membership = db.execute(
        select(Membership).where(
            Membership.group_id == group_id,
            Membership.user_id == user.id,
            Membership.status == MembershipStatus.ACTIVE,
        )
    ).scalar_one_or_none()
    if membership is None:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Vous n'êtes pas membre de ce groupe.")
    return membership


def _admin_or_403(db: DbSession, group_id: UUID, user: User) -> Membership:
    membership = _membership_or_403(db, group_id, user)
    if not membership.is_admin:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Action réservée à l'administrateur.")
    return membership


@router.post("", response_model=GroupOut, status_code=status.HTTP_201_CREATED)
def create_group(payload: GroupCreate, db: DbSession, user: CurrentUser) -> TontineGroup:
    group = TontineGroup(**payload.model_dump(), created_by_id=user.id)
    db.add(group)
    db.flush()

    # Le créateur devient membre et administrateur, en première position.
    db.add(Membership(group_id=group.id, user_id=user.id, payout_position=1, is_admin=True))
    db.commit()
    db.refresh(group)
    return group


@router.get("", response_model=list[GroupOut])
def list_my_groups(
    db: DbSession,
    user: CurrentUser,
    limit: int = Query(default=20, le=100),
    offset: int = Query(default=0, ge=0),
) -> list[TontineGroup]:
    stmt = (
        select(TontineGroup)
        .join(Membership, Membership.group_id == TontineGroup.id)
        .where(Membership.user_id == user.id, Membership.status == MembershipStatus.ACTIVE)
        .order_by(TontineGroup.created_at.desc())
        .limit(limit)
        .offset(offset)
    )
    return list(db.execute(stmt).scalars().all())


@router.get("/{group_id}", response_model=GroupOut)
def get_group(group_id: UUID, db: DbSession, user: CurrentUser) -> TontineGroup:
    _membership_or_403(db, group_id, user)
    group = db.get(TontineGroup, group_id)
    if group is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Groupe introuvable.")
    return group


@router.post("/{group_id}/members", response_model=MemberOut, status_code=status.HTTP_201_CREATED)
def add_member(
    group_id: UUID, payload: MemberAdd, db: DbSession, user: CurrentUser
) -> Membership:
    _admin_or_403(db, group_id, user)
    group = db.get(TontineGroup, group_id)
    if group is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Groupe introuvable.")
    if group.status != GroupStatus.DRAFT:
        raise HTTPException(
            status.HTTP_409_CONFLICT, "L'ordre de passage est figé : le groupe a démarré."
        )

    invitee = db.execute(select(User).where(User.phone == payload.phone)).scalar_one_or_none()
    if invitee is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Aucun compte pour ce numéro.")

    position = payload.payout_position or tontine.next_payout_position(db, group_id)
    membership = Membership(group_id=group_id, user_id=invitee.id, payout_position=position)
    db.add(membership)
    db.commit()
    db.refresh(membership)
    return membership


@router.get("/{group_id}/members", response_model=list[MemberOut])
def list_members(group_id: UUID, db: DbSession, user: CurrentUser) -> list[Membership]:
    _membership_or_403(db, group_id, user)
    stmt = (
        select(Membership)
        .where(Membership.group_id == group_id)
        .order_by(Membership.payout_position)
    )
    return list(db.execute(stmt).scalars().all())


@router.post("/{group_id}/activate", response_model=list[CycleOut])
def activate(group_id: UUID, db: DbSession, user: CurrentUser) -> list[Cycle]:
    _admin_or_403(db, group_id, user)
    group = db.get(TontineGroup, group_id)
    if group is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Groupe introuvable.")

    try:
        cycles = tontine.activate_group(db, group)
    except tontine.TontineError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc

    db.commit()
    return cycles


@router.get("/{group_id}/cycles", response_model=list[CycleOut])
def list_cycles(group_id: UUID, db: DbSession, user: CurrentUser) -> list[Cycle]:
    _membership_or_403(db, group_id, user)
    stmt = (
        select(Cycle)
        .where(Cycle.group_id == group_id)
        .options(selectinload(Cycle.contributions))
        .order_by(Cycle.index)
    )
    return list(db.execute(stmt).scalars().all())


@router.get("/{group_id}/balance", response_model=BalanceOut)
def group_balance(group_id: UUID, db: DbSession, user: CurrentUser) -> BalanceOut:
    _membership_or_403(db, group_id, user)
    group = db.get(TontineGroup, group_id)
    if group is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Groupe introuvable.")

    account = ledger.get_or_create_account(
        db, AccountKind.GROUP_POT, group.id, f"Cagnotte — {group.name}", group.currency
    )
    db.commit()
    return BalanceOut(
        account_id=account.id,
        balance_minor=ledger.balance_minor(db, account.id),
        currency=group.currency,
    )
