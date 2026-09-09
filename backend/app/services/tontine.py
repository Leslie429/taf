"""Logique métier de la tontine.

Un groupe passe de `draft` à `active` : à ce moment on fige l'ordre de passage et
on engendre tous les cycles à venir, un par membre. Chaque cycle porte autant de
cotisations qu'il y a de membres, et désigne un bénéficiaire.
"""

from calendar import monthrange
from datetime import date, timedelta
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.enums import (
    AccountKind,
    ContributionStatus,
    CycleStatus,
    EntryDirection,
    Frequency,
    GroupStatus,
    MembershipStatus,
    TransactionStatus,
    TransactionType,
)
from app.models.ledger import Transaction
from app.models.tontine import Contribution, Cycle, Membership, TontineGroup
from app.models.user import User
from app.services import ledger
from app.services.momo import MoMoClient

PROVIDER = "mtn_momo"


class TontineError(Exception):
    pass


def _next_due_date(start: date, frequency: Frequency, index: int) -> date:
    if frequency == Frequency.WEEKLY:
        return start + timedelta(weeks=index)
    if frequency == Frequency.BIWEEKLY:
        return start + timedelta(weeks=2 * index)

    # Mensuel : on avance de `index` mois en gardant le jour, ramené à la fin de
    # mois quand il n'existe pas (le 31 en février, par exemple).
    month_total = start.month - 1 + index
    year = start.year + month_total // 12
    month = month_total % 12 + 1
    return date(year, month, min(start.day, monthrange(year, month)[1]))


def activate_group(db: Session, group: TontineGroup) -> list[Cycle]:
    """Démarre la tontine : engendre un cycle par membre actif."""
    if group.status != GroupStatus.DRAFT:
        raise TontineError("Seul un groupe en brouillon peut être activé.")

    members = sorted(
        (m for m in group.memberships if m.status == MembershipStatus.ACTIVE),
        key=lambda m: m.payout_position,
    )
    if len(members) < 2:
        raise TontineError("Une tontine exige au moins deux membres.")

    ledger.get_or_create_account(
        db, AccountKind.GROUP_POT, group.id, f"Cagnotte — {group.name}", group.currency
    )

    cycles: list[Cycle] = []
    for index, beneficiary in enumerate(members):
        cycle = Cycle(
            group_id=group.id,
            index=index,
            beneficiary_membership_id=beneficiary.id,
            due_date=_next_due_date(group.start_date, group.frequency, index),
            status=CycleStatus.PENDING,
        )
        cycle.contributions = [
            Contribution(
                membership_id=member.id,
                amount_minor=group.contribution_minor,
                status=ContributionStatus.DUE,
            )
            for member in members
        ]
        db.add(cycle)
        cycles.append(cycle)

    group.status = GroupStatus.ACTIVE
    db.flush()
    return cycles


def pot_total_minor(group: TontineGroup, member_count: int) -> int:
    """Ce que touche le bénéficiaire d'un cycle."""
    return group.contribution_minor * member_count


def initiate_contribution(
    db: Session,
    *,
    contribution: Contribution,
    payer: User,
    momo: MoMoClient,
) -> Transaction:
    """Démarre l'encaissement d'une cotisation par Mobile Money.

    Le mouvement comptable est enregistré avant l'appel à l'opérateur, en
    `pending` : si le réseau tombe entre les deux, la trace existe et le
    rapprochement pourra conclure.
    """
    if contribution.status == ContributionStatus.PAID:
        raise TontineError("Cette cotisation est déjà réglée.")

    cycle = contribution.cycle
    group = cycle.group

    clearing = ledger.get_or_create_account(
        db, AccountKind.MOMO_CLEARING, None, "Clearing MTN MoMo", group.currency
    )
    pot = ledger.get_or_create_account(
        db, AccountKind.GROUP_POT, group.id, f"Cagnotte — {group.name}", group.currency
    )

    transaction = ledger.post_transaction(
        db,
        # Une cotisation donnée ne peut être encaissée qu'une fois, quel que soit
        # le nombre de fois où le membre appuie sur le bouton — mais un refus de
        # l'opérateur doit pouvoir être retenté.
        idempotency_key=ledger.next_attempt_key(db, f"contribution:{contribution.id}"),
        tx_type=TransactionType.CONTRIBUTION,
        amount_minor=contribution.amount_minor,
        postings=[
            # L'argent entre chez l'opérateur : un actif augmente au débit.
            ledger.Posting(clearing.id, EntryDirection.DEBIT, contribution.amount_minor),
            # La cagnotte doit désormais cette somme au groupe : passif au crédit.
            ledger.Posting(pot.id, EntryDirection.CREDIT, contribution.amount_minor),
        ],
        currency=group.currency,
        provider=PROVIDER,
    )

    if transaction.status != TransactionStatus.PENDING:
        # Rejeu : on renvoie la transaction déjà engagée sans rappeler l'opérateur.
        return transaction

    contribution.transaction_id = transaction.id
    contribution.status = ContributionStatus.PROCESSING

    result = momo.request_to_pay(
        reference=transaction.id,
        amount_minor=contribution.amount_minor,
        payer_phone=payer.phone,
        note=f"Cotisation {group.name} — cycle {cycle.index + 1}",
    )
    transaction.external_id = result.external_id

    if result.accepted:
        ledger.transition(db, transaction, TransactionStatus.PROCESSING)
    else:
        ledger.transition(
            db, transaction, TransactionStatus.FAILED, failure_reason="Refus de l'opérateur"
        )
        contribution.status = ContributionStatus.FAILED

    db.flush()
    return transaction


def confirm_contribution(db: Session, transaction: Transaction, *, success: bool) -> None:
    """Applique le verdict de l'opérateur, reçu par callback."""
    if transaction.status != TransactionStatus.PROCESSING:
        # Callback en double, ou transaction déjà tranchée : rien à faire.
        return

    contribution = db.execute(
        select(Contribution).where(Contribution.transaction_id == transaction.id)
    ).scalar_one_or_none()

    if success:
        ledger.transition(db, transaction, TransactionStatus.SUCCESS)
        if contribution is not None:
            contribution.status = ContributionStatus.PAID
            _refresh_cycle_status(db, contribution.cycle)
    else:
        ledger.transition(
            db, transaction, TransactionStatus.FAILED, failure_reason="Paiement refusé"
        )
        if contribution is not None:
            contribution.status = ContributionStatus.DUE

    db.flush()


def _refresh_cycle_status(db: Session, cycle: Cycle) -> None:
    if all(c.status == ContributionStatus.PAID for c in cycle.contributions):
        cycle.status = CycleStatus.FUNDED
    elif cycle.due_date < date.today():
        cycle.status = CycleStatus.LATE
    db.flush()


def pay_out_cycle(db: Session, cycle: Cycle, momo: MoMoClient) -> Transaction:
    """Verse la cagnotte au bénéficiaire du cycle."""
    if cycle.status != CycleStatus.FUNDED:
        raise TontineError("Le cycle n'est pas intégralement financé.")

    group = cycle.group
    beneficiary_membership = db.get(Membership, cycle.beneficiary_membership_id)
    if beneficiary_membership is None:
        raise TontineError("Bénéficiaire introuvable.")
    beneficiary = db.get(User, beneficiary_membership.user_id)
    if beneficiary is None:
        raise TontineError("Utilisateur bénéficiaire introuvable.")

    amount = sum(c.amount_minor for c in cycle.contributions)

    pot = ledger.get_or_create_account(
        db, AccountKind.GROUP_POT, group.id, f"Cagnotte — {group.name}", group.currency
    )
    clearing = ledger.get_or_create_account(
        db, AccountKind.MOMO_CLEARING, None, "Clearing MTN MoMo", group.currency
    )

    available = ledger.balance_minor(db, pot.id)
    if available < amount:
        raise TontineError(
            f"Cagnotte insuffisante : {available} disponible pour {amount} à verser."
        )

    transaction = ledger.post_transaction(
        db,
        idempotency_key=ledger.next_attempt_key(db, f"payout:{cycle.id}"),
        tx_type=TransactionType.PAYOUT,
        amount_minor=amount,
        postings=[
            # La dette envers le groupe s'éteint : passif au débit.
            ledger.Posting(pot.id, EntryDirection.DEBIT, amount),
            # Les fonds quittent l'opérateur : actif au crédit.
            ledger.Posting(clearing.id, EntryDirection.CREDIT, amount),
        ],
        currency=group.currency,
        provider=PROVIDER,
    )

    if transaction.status != TransactionStatus.PENDING:
        return transaction

    result = momo.transfer(
        reference=transaction.id,
        amount_minor=amount,
        payee_phone=beneficiary.phone,
        note=f"Versement {group.name} — cycle {cycle.index + 1}",
    )
    transaction.external_id = result.external_id

    if result.accepted:
        ledger.transition(db, transaction, TransactionStatus.PROCESSING)
    else:
        ledger.transition(
            db, transaction, TransactionStatus.FAILED, failure_reason="Versement refusé"
        )

    db.flush()
    return transaction


def confirm_payout(db: Session, transaction: Transaction, cycle: Cycle, *, success: bool) -> None:
    if transaction.status != TransactionStatus.PROCESSING:
        return

    if success:
        ledger.transition(db, transaction, TransactionStatus.SUCCESS)
        cycle.status = CycleStatus.PAID_OUT
        _close_group_if_done(db, cycle.group)
    else:
        ledger.transition(
            db, transaction, TransactionStatus.FAILED, failure_reason="Versement échoué"
        )
    db.flush()


def _close_group_if_done(db: Session, group: TontineGroup) -> None:
    if all(c.status == CycleStatus.PAID_OUT for c in group.cycles):
        group.status = GroupStatus.COMPLETED
        db.flush()


def next_payout_position(db: Session, group_id: UUID) -> int:
    positions = db.execute(
        select(Membership.payout_position).where(Membership.group_id == group_id)
    ).scalars().all()
    return max(positions, default=0) + 1


def new_idempotency_key() -> str:
    return uuid4().hex
