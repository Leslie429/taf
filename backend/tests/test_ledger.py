"""Ces tests protègent les invariants comptables. Si l'un d'eux casse,
c'est de l'argent qui se crée ou disparaît."""

import pytest
from sqlalchemy.orm import Session

from app.models.enums import (
    AccountKind,
    EntryDirection,
    TransactionStatus,
    TransactionType,
)
from app.services import ledger


@pytest.fixture
def accounts(db: Session):
    pot = ledger.get_or_create_account(db, AccountKind.GROUP_POT, None, "Cagnotte test")
    clearing = ledger.get_or_create_account(db, AccountKind.MOMO_CLEARING, None, "Clearing")
    return pot, clearing


def _balanced(pot_id, clearing_id, amount: int) -> list[ledger.Posting]:
    return [
        ledger.Posting(clearing_id, EntryDirection.DEBIT, amount),
        ledger.Posting(pot_id, EntryDirection.CREDIT, amount),
    ]


def test_transaction_equilibree_est_acceptee(db: Session, accounts):
    pot, clearing = accounts
    tx = ledger.post_transaction(
        db,
        idempotency_key="k1",
        tx_type=TransactionType.CONTRIBUTION,
        amount_minor=5000,
        postings=_balanced(pot.id, clearing.id, 5000),
    )
    assert tx.status == TransactionStatus.PENDING
    assert len(tx.entries) == 2
    assert sum(e.amount_minor for e in tx.entries) == 10000


def test_transaction_desequilibree_est_refusee(db: Session, accounts):
    pot, clearing = accounts
    with pytest.raises(ledger.UnbalancedTransaction):
        ledger.post_transaction(
            db,
            idempotency_key="k2",
            tx_type=TransactionType.CONTRIBUTION,
            amount_minor=5000,
            postings=[
                ledger.Posting(clearing.id, EntryDirection.DEBIT, 5000),
                ledger.Posting(pot.id, EntryDirection.CREDIT, 4000),
            ],
        )


def test_ecriture_unique_est_refusee(db: Session, accounts):
    pot, _ = accounts
    with pytest.raises(ledger.UnbalancedTransaction):
        ledger.post_transaction(
            db,
            idempotency_key="k3",
            tx_type=TransactionType.CONTRIBUTION,
            amount_minor=5000,
            postings=[ledger.Posting(pot.id, EntryDirection.CREDIT, 5000)],
        )


def test_meme_cle_idempotence_ne_cree_pas_deux_transactions(db: Session, accounts):
    pot, clearing = accounts
    first = ledger.post_transaction(
        db,
        idempotency_key="paiement-42",
        tx_type=TransactionType.CONTRIBUTION,
        amount_minor=5000,
        postings=_balanced(pot.id, clearing.id, 5000),
    )
    second = ledger.post_transaction(
        db,
        idempotency_key="paiement-42",
        tx_type=TransactionType.CONTRIBUTION,
        amount_minor=5000,
        postings=_balanced(pot.id, clearing.id, 5000),
    )
    assert first.id == second.id


def test_solde_ignore_les_transactions_non_abouties(db: Session, accounts):
    pot, clearing = accounts
    tx = ledger.post_transaction(
        db,
        idempotency_key="k4",
        tx_type=TransactionType.CONTRIBUTION,
        amount_minor=5000,
        postings=_balanced(pot.id, clearing.id, 5000),
    )
    assert ledger.balance_minor(db, pot.id) == 0

    ledger.transition(db, tx, TransactionStatus.PROCESSING)
    assert ledger.balance_minor(db, pot.id) == 0

    ledger.transition(db, tx, TransactionStatus.SUCCESS)
    assert ledger.balance_minor(db, pot.id) == 5000
    # Le clearing est un compte d'actif : son solde en convention crédit-débit
    # est l'opposé de celui de la cagnotte.
    assert ledger.balance_minor(db, clearing.id) == -5000


def test_transition_interdite_leve_une_erreur(db: Session, accounts):
    pot, clearing = accounts
    tx = ledger.post_transaction(
        db,
        idempotency_key="k5",
        tx_type=TransactionType.CONTRIBUTION,
        amount_minor=1000,
        postings=_balanced(pot.id, clearing.id, 1000),
    )
    with pytest.raises(ledger.InvalidTransition):
        # On ne saute pas l'étape `processing`.
        ledger.transition(db, tx, TransactionStatus.SUCCESS)


def test_contrepassation_ramene_le_solde_a_zero(db: Session, accounts):
    pot, clearing = accounts
    tx = ledger.post_transaction(
        db,
        idempotency_key="k6",
        tx_type=TransactionType.CONTRIBUTION,
        amount_minor=7500,
        postings=_balanced(pot.id, clearing.id, 7500),
    )
    ledger.transition(db, tx, TransactionStatus.PROCESSING)
    ledger.transition(db, tx, TransactionStatus.SUCCESS)
    assert ledger.balance_minor(db, pot.id) == 7500

    ledger.reverse(db, tx, "erreur opérateur")

    assert tx.status == TransactionStatus.REVERSED
    assert ledger.balance_minor(db, pot.id) == 0


def _essai(db: Session, accounts, cle: str, statut: TransactionStatus):
    pot, clearing = accounts
    tx = ledger.post_transaction(
        db,
        idempotency_key=cle,
        tx_type=TransactionType.PAYOUT,
        amount_minor=1000,
        postings=_balanced(pot.id, clearing.id, 1000),
    )
    if statut != TransactionStatus.PENDING:
        ledger.transition(db, tx, TransactionStatus.PROCESSING)
        if statut != TransactionStatus.PROCESSING:
            ledger.transition(db, tx, statut)
    db.flush()
    return tx


def test_le_premier_essai_porte_le_rang_un(db: Session):
    assert ledger.next_attempt_key(db, "payout:abc") == "payout:abc:1"


def test_un_essai_en_cours_est_renvoye_tel_quel(db: Session, accounts):
    # Deux clics sur « Verser » ne doivent pas produire deux versements.
    _essai(db, accounts, "payout:abc:1", TransactionStatus.PROCESSING)
    assert ledger.next_attempt_key(db, "payout:abc") == "payout:abc:1"


def test_un_essai_reussi_est_renvoye_tel_quel(db: Session, accounts):
    _essai(db, accounts, "payout:abc:1", TransactionStatus.SUCCESS)
    assert ledger.next_attempt_key(db, "payout:abc") == "payout:abc:1"


def test_un_echec_ouvre_un_essai_suivant(db: Session, accounts):
    # Un refus de l'opérateur ne doit pas figer l'opération pour toujours.
    _essai(db, accounts, "payout:abc:1", TransactionStatus.FAILED)
    assert ledger.next_attempt_key(db, "payout:abc") == "payout:abc:2"


def test_les_echecs_saccumulent_sans_se_marcher_dessus(db: Session, accounts):
    _essai(db, accounts, "payout:abc:1", TransactionStatus.FAILED)
    _essai(db, accounts, "payout:abc:2", TransactionStatus.FAILED)
    assert ledger.next_attempt_key(db, "payout:abc") == "payout:abc:3"


def test_les_essais_dune_autre_operation_ne_comptent_pas(db: Session, accounts):
    # Le préfixe doit isoler : un cycle voisin ne décale pas nos rangs.
    _essai(db, accounts, "payout:xyz:1", TransactionStatus.FAILED)
    assert ledger.next_attempt_key(db, "payout:abc") == "payout:abc:1"
