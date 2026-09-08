"""Grand livre en partie double.

Règles tenues par ce module, et par lui seul :
  1. Toute transaction porte au moins deux écritures, et la somme des débits
     est strictement égale à la somme des crédits.
  2. Un solde n'est jamais stocké : il est dérivé des écritures.
  3. Une écriture n'est jamais modifiée ni supprimée ; on contrepasse.
  4. Une clé d'idempotence rejouée renvoie la transaction d'origine.
"""

from dataclasses import dataclass
from uuid import UUID, uuid4

from sqlalchemy import case, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.enums import (
    AccountKind,
    EntryDirection,
    TransactionStatus,
    TransactionType,
)
from app.models.ledger import Account, LedgerEntry, Transaction

# Transitions autorisées de la machine à états. Toute autre tentative lève une erreur.
ALLOWED_TRANSITIONS: dict[TransactionStatus, set[TransactionStatus]] = {
    TransactionStatus.PENDING: {TransactionStatus.PROCESSING, TransactionStatus.FAILED},
    TransactionStatus.PROCESSING: {TransactionStatus.SUCCESS, TransactionStatus.FAILED},
    TransactionStatus.SUCCESS: {TransactionStatus.REVERSED},
    TransactionStatus.FAILED: set(),
    TransactionStatus.REVERSED: set(),
}


class LedgerError(Exception):
    """Erreur métier du grand livre."""


class UnbalancedTransaction(LedgerError):
    pass


class InvalidTransition(LedgerError):
    pass


@dataclass(frozen=True)
class Posting:
    """Une écriture à passer : un compte, un sens, un montant."""

    account_id: UUID
    direction: EntryDirection
    amount_minor: int


def _reference() -> str:
    return f"TXN-{uuid4().hex[:16].upper()}"


def get_or_create_account(
    db: Session, kind: AccountKind, owner_id: UUID | None, label: str, currency: str = "XOF"
) -> Account:
    stmt = select(Account).where(Account.kind == kind, Account.owner_id == owner_id)
    account = db.execute(stmt).scalar_one_or_none()
    if account is not None:
        return account

    account = Account(kind=kind, owner_id=owner_id, label=label, currency=currency)
    db.add(account)
    db.flush()
    return account


def balance_minor(db: Session, account_id: UUID) -> int:
    """Solde du compte, en unités mineures, calculé comme crédits moins débits.

    La convention retenue rend positifs les comptes de passif (portefeuille d'un
    membre, cagnotte d'un groupe) : un crédit augmente ce que la plateforme doit.
    Un compte d'actif comme le clearing opérateur ressort donc négatif, ce qui est
    la lecture normale en partie double.

    Seules les écritures rattachées à une transaction réussie sont comptées : une
    transaction en cours n'engage pas encore le solde disponible. Une transaction
    contrepassée reste comptée — elle a bien eu lieu, et c'est son écriture miroir
    qui l'annule ; l'exclure retrancherait le montant deux fois.
    """
    signed = case(
        (LedgerEntry.direction == EntryDirection.CREDIT, LedgerEntry.amount_minor),
        else_=-LedgerEntry.amount_minor,
    )
    stmt = (
        select(func.coalesce(func.sum(signed), 0))
        .join(Transaction, Transaction.id == LedgerEntry.transaction_id)
        .where(
            LedgerEntry.account_id == account_id,
            Transaction.status.in_((TransactionStatus.SUCCESS, TransactionStatus.REVERSED)),
        )
    )
    return int(db.execute(stmt).scalar_one())


def post_transaction(
    db: Session,
    *,
    idempotency_key: str,
    tx_type: TransactionType,
    amount_minor: int,
    postings: list[Posting],
    currency: str = "XOF",
    provider: str | None = None,
    external_id: str | None = None,
) -> Transaction:
    """Enregistre une transaction équilibrée, ou renvoie celle déjà créée
    pour cette clé d'idempotence."""

    existing = db.execute(
        select(Transaction).where(Transaction.idempotency_key == idempotency_key)
    ).scalar_one_or_none()
    if existing is not None:
        return existing

    if amount_minor <= 0:
        raise LedgerError("Le montant doit être strictement positif.")

    debits = sum(p.amount_minor for p in postings if p.direction == EntryDirection.DEBIT)
    credits = sum(p.amount_minor for p in postings if p.direction == EntryDirection.CREDIT)
    if len(postings) < 2:
        raise UnbalancedTransaction("Une transaction exige au moins deux écritures.")
    if debits != credits:
        raise UnbalancedTransaction(
            f"Écritures déséquilibrées : {debits} au débit contre {credits} au crédit."
        )

    transaction = Transaction(
        reference=_reference(),
        idempotency_key=idempotency_key,
        type=tx_type,
        status=TransactionStatus.PENDING,
        amount_minor=amount_minor,
        currency=currency,
        provider=provider,
        external_id=external_id,
    )
    transaction.entries = [
        LedgerEntry(
            account_id=p.account_id, direction=p.direction, amount_minor=p.amount_minor
        )
        for p in postings
    ]
    db.add(transaction)

    try:
        db.flush()
    except IntegrityError:
        # Course entre deux requêtes concurrentes portant la même clé :
        # la contrainte d'unicité a tranché, on renvoie la gagnante.
        db.rollback()
        return db.execute(
            select(Transaction).where(Transaction.idempotency_key == idempotency_key)
        ).scalar_one()

    return transaction


def transition(
    db: Session,
    transaction: Transaction,
    new_status: TransactionStatus,
    *,
    failure_reason: str | None = None,
) -> Transaction:
    """Fait avancer la transaction dans sa machine à états."""
    if new_status not in ALLOWED_TRANSITIONS[transaction.status]:
        raise InvalidTransition(
            f"Transition interdite : {transaction.status} -> {new_status}."
        )

    transaction.status = new_status
    if failure_reason is not None:
        transaction.failure_reason = failure_reason
    db.flush()
    return transaction


def reverse(db: Session, transaction: Transaction, reason: str) -> Transaction:
    """Contrepasse une transaction réussie : mêmes écritures, sens inversés."""
    mirrored = [
        Posting(
            account_id=entry.account_id,
            direction=(
                EntryDirection.CREDIT
                if entry.direction == EntryDirection.DEBIT
                else EntryDirection.DEBIT
            ),
            amount_minor=entry.amount_minor,
        )
        for entry in transaction.entries
    ]

    reversal = post_transaction(
        db,
        idempotency_key=f"reversal:{transaction.id}",
        tx_type=TransactionType.REVERSAL,
        amount_minor=transaction.amount_minor,
        postings=mirrored,
        currency=transaction.currency,
    )
    transition(db, reversal, TransactionStatus.PROCESSING)
    transition(db, reversal, TransactionStatus.SUCCESS)
    transition(db, transaction, TransactionStatus.REVERSED, failure_reason=reason)
    return reversal
