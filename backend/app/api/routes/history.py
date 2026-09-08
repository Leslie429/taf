from operator import attrgetter

from fastapi import APIRouter, Query
from sqlalchemy import select

from app.api.deps import CurrentUser, DbSession
from app.models.ledger import Transaction
from app.models.tontine import Contribution, Cycle, Membership, TontineGroup
from app.schemas.history import HistoryItem

router = APIRouter(prefix="/me", tags=["historique"])


@router.get("/transactions", response_model=list[HistoryItem])
def my_transactions(
    db: DbSession,
    user: CurrentUser,
    limit: int = Query(default=30, le=100),
    offset: int = Query(default=0, ge=0),
) -> list[HistoryItem]:
    """Les mouvements de l'utilisateur : ses cotisations et ses versements reçus."""
    membership_ids = list(
        db.execute(
            select(Membership.id).where(Membership.user_id == user.id)
        ).scalars().all()
    )
    if not membership_ids:
        return []

    # Ce que l'utilisateur a versé.
    sorties = [
        HistoryItem(
            id=transaction.id,
            reference=transaction.reference,
            type=transaction.type,
            status=transaction.status,
            amount_minor=transaction.amount_minor,
            currency=transaction.currency,
            created_at=transaction.created_at,
            direction="out",
            group_id=group.id,
            group_name=group.name,
            cycle_index=cycle.index,
        )
        for transaction, cycle, group in db.execute(
            select(Transaction, Cycle, TontineGroup)
            .join(Contribution, Contribution.transaction_id == Transaction.id)
            .join(Cycle, Cycle.id == Contribution.cycle_id)
            .join(TontineGroup, TontineGroup.id == Cycle.group_id)
            .where(Contribution.membership_id.in_(membership_ids))
        ).all()
    ]

    # Ce que l'utilisateur a reçu. Le versement n'a pas de clé étrangère vers le
    # cycle : on reconstruit sa clé d'idempotence plutôt que de la découper, ce
    # qui reste juste même si le format évolue d'un seul côté.
    cycles_beneficiaires = db.execute(
        select(Cycle, TontineGroup)
        .join(TontineGroup, TontineGroup.id == Cycle.group_id)
        .where(Cycle.beneficiary_membership_id.in_(membership_ids))
    ).all()
    par_cle = {f"payout:{cycle.id}": (cycle, group) for cycle, group in cycles_beneficiaires}

    entrees: list[HistoryItem] = []
    if par_cle:
        for transaction in db.execute(
            select(Transaction).where(Transaction.idempotency_key.in_(par_cle))
        ).scalars().all():
            cycle, group = par_cle[transaction.idempotency_key]
            entrees.append(
                HistoryItem(
                    id=transaction.id,
                    reference=transaction.reference,
                    type=transaction.type,
                    status=transaction.status,
                    amount_minor=transaction.amount_minor,
                    currency=transaction.currency,
                    created_at=transaction.created_at,
                    direction="in",
                    group_id=group.id,
                    group_name=group.name,
                    cycle_index=cycle.index,
                )
            )

    # Les deux sources sont fusionnées en mémoire : à ce volume c'est sans
    # conséquence, mais au-delà de quelques milliers de lignes par personne il
    # faudra une UNION paginée en base.
    tout = sorted(sorties + entrees, key=attrgetter("created_at"), reverse=True)
    return tout[offset : offset + limit]
