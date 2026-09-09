"""Le rapprochement confronte le grand livre au relevé de l'opérateur.

Deux exigences le gouvernent : réparer ce qui est réparable sans intervention,
et ne jamais corriger en silence ce qui met en cause un succès déjà comptabilisé.
"""

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.models.enums import (
    ContributionStatus,
    DivergenceKind,
    Frequency,
    TransactionStatus,
)
from app.models.ledger import Transaction
from app.models.reconciliation import Divergence
from app.models.tontine import Membership, TontineGroup
from app.services import ledger, rapprochement, tontine
from app.services.momo import PROVIDER_DOUBLE, PROVIDER_MTN, FakeMoMoClient


@pytest.fixture
def cotisation_en_cours(db: Session, make_user, momo: FakeMoMoClient):
    """Une cotisation partie chez l'opérateur, sans verdict reçu."""
    membres = [make_user(f"M{index}") for index in range(2)]
    groupe = TontineGroup(
        name="Rapprochement",
        contribution_minor=3000,
        frequency=Frequency.WEEKLY,
        start_date=datetime.now(UTC).date(),
        created_by_id=membres[0].id,
    )
    db.add(groupe)
    db.flush()
    for position, membre in enumerate(membres, start=1):
        db.add(Membership(group_id=groupe.id, user_id=membre.id, payout_position=position))
    db.flush()
    db.refresh(groupe)

    cycles = tontine.activate_group(db, groupe)
    contribution = cycles[0].contributions[0]
    adhesion = db.get(Membership, contribution.membership_id)
    payeur = next(m for m in membres if m.id == adhesion.user_id)
    transaction = tontine.initiate_contribution(
        db, contribution=contribution, payer=payeur, momo=momo
    )
    # Le double répond aux interrogations de statut, mais la transaction est
    # attribuée à l'opérateur réel : c'est lui qu'un rapprochement confronte.
    transaction.provider = PROVIDER_MTN
    db.flush()
    return contribution, transaction


def _vieillir(db: Session, transaction: Transaction, minutes: int = 60) -> None:
    """Antidate la transaction : le délai de grâce protège les envois récents."""
    db.execute(
        update(Transaction)
        .where(Transaction.id == transaction.id)
        .values(updated_at=datetime.now(UTC) - timedelta(minutes=minutes))
    )
    db.expire(transaction)


def _dire(momo: FakeMoMoClient, statut: str) -> None:
    momo.status = lambda **_: {"status": statut}  # type: ignore[method-assign]


def test_un_callback_perdu_est_rattrape(db: Session, momo, cotisation_en_cours):
    contribution, transaction = cotisation_en_cours
    _vieillir(db, transaction)
    _dire(momo, "SUCCESSFUL")

    run = rapprochement.rapprocher(db, momo)

    ecart = db.execute(select(Divergence).where(Divergence.run_id == run.id)).scalar_one()
    assert ecart.kind == DivergenceKind.UNCONFIRMED
    assert ecart.resolved is True
    db.refresh(contribution)
    assert contribution.status == ContributionStatus.PAID


def test_un_echec_tardif_est_rattrape_aussi(db: Session, momo, cotisation_en_cours):
    contribution, transaction = cotisation_en_cours
    _vieillir(db, transaction)
    _dire(momo, "FAILED")

    rapprochement.rapprocher(db, momo)

    db.refresh(transaction)
    assert transaction.status == TransactionStatus.FAILED
    db.refresh(contribution)
    # Le callback remet la cotisation à régler : un échec n'est pas une dette
    # éteinte.
    assert contribution.status == ContributionStatus.DUE


def test_un_operateur_muet_ne_fait_rien_changer(db: Session, momo, cotisation_en_cours):
    contribution, transaction = cotisation_en_cours
    _vieillir(db, transaction)
    _dire(momo, "PENDING")

    run = rapprochement.rapprocher(db, momo)

    ecart = db.execute(select(Divergence).where(Divergence.run_id == run.id)).scalar_one()
    assert ecart.kind == DivergenceKind.OPERATOR_SILENT
    assert ecart.resolved is False
    db.refresh(transaction)
    assert transaction.status == TransactionStatus.PROCESSING


def test_une_reference_inconnue_de_loperateur_est_signalee(
    db: Session, momo, cotisation_en_cours
):
    # Le cas où nous croyons avoir envoyé quelque chose dont l'opérateur n'a
    # aucune trace.
    _, transaction = cotisation_en_cours
    _vieillir(db, transaction)
    _dire(momo, "")

    run = rapprochement.rapprocher(db, momo)

    ecart = db.execute(select(Divergence).where(Divergence.run_id == run.id)).scalar_one()
    assert ecart.kind == DivergenceKind.UNKNOWN_AT_OPERATOR
    assert ecart.resolved is False


def test_un_succes_dementi_nest_jamais_corrige_en_silence(
    db: Session, momo, cotisation_en_cours
):
    # Le cas grave : de l'argent au grand livre sans contrepartie opérateur.
    # Une contrepassation est une décision, pas un effet de bord.
    _, transaction = cotisation_en_cours
    ledger.transition(db, transaction, TransactionStatus.SUCCESS)
    db.flush()
    _dire(momo, "FAILED")

    run = rapprochement.rapprocher(db, momo)

    ecart = db.execute(select(Divergence).where(Divergence.run_id == run.id)).scalar_one()
    assert ecart.kind == DivergenceKind.DISPUTED_SUCCESS
    assert ecart.resolved is False
    db.refresh(transaction)
    assert transaction.status == TransactionStatus.SUCCESS


def test_une_transaction_recente_echappe_au_rapprochement(db: Session, momo, cotisation_en_cours):
    # L'opérateur a le droit de mettre quelques minutes à trancher.
    _, transaction = cotisation_en_cours
    _dire(momo, "SUCCESSFUL")

    run = rapprochement.rapprocher(db, momo)

    assert run.examined == 0
    assert db.execute(select(Divergence).where(Divergence.run_id == run.id)).all() == []


def test_le_mode_constat_ne_touche_a_rien(db: Session, momo, cotisation_en_cours):
    contribution, transaction = cotisation_en_cours
    _vieillir(db, transaction)
    _dire(momo, "SUCCESSFUL")

    run = rapprochement.rapprocher(db, momo, appliquer=False)

    ecart = db.execute(select(Divergence).where(Divergence.run_id == run.id)).scalar_one()
    assert ecart.kind == DivergenceKind.UNCONFIRMED
    assert ecart.resolved is False
    db.refresh(contribution)
    assert contribution.status == ContributionStatus.PROCESSING


def test_un_ecart_garde_les_deux_etats_du_moment(db: Session, momo, cotisation_en_cours):
    # Un écart se relit des mois plus tard, quand les statuts ont bougé.
    _, transaction = cotisation_en_cours
    _vieillir(db, transaction)
    _dire(momo, "SUCCESSFUL")

    run = rapprochement.rapprocher(db, momo)

    ecart = db.execute(select(Divergence).where(Divergence.run_id == run.id)).scalar_one()
    assert ecart.local_status == TransactionStatus.PROCESSING
    assert ecart.operator_status == "SUCCESSFUL"
    assert ecart.transaction_id == transaction.id


def test_le_journal_retient_la_serie(db: Session, momo, cotisation_en_cours):
    _, transaction = cotisation_en_cours
    _vieillir(db, transaction)
    _dire(momo, "PENDING")

    run = rapprochement.rapprocher(db, momo)

    assert rapprochement.dernier_rapprochement(db).id == run.id
    assert len(rapprochement.ecarts_non_resolus(db, run.id)) == 1
    assert run.finished_at is not None


def test_la_consultation_est_refusee_au_simple_membre(client, make_user, auth_as):
    # `Membership.is_admin` n'administre qu'une tontine ; le rapprochement
    # expose l'état de toutes.
    auth_as(make_user("Membre"))
    assert client.get("/api/v1/admin/reconciliation").status_code == 403


def test_lequipe_consulte_le_dernier_rapprochement(
    client, db: Session, make_user, auth_as, momo, cotisation_en_cours
):
    _, transaction = cotisation_en_cours
    _vieillir(db, transaction)
    _dire(momo, "SUCCESSFUL")
    run = rapprochement.rapprocher(db, momo)

    membre = make_user("Equipe")
    membre.is_staff = True
    db.flush()
    auth_as(membre)

    corps = client.get("/api/v1/admin/reconciliation").json()
    assert corps["id"] == str(run.id)
    assert corps["examined"] == 1
    assert corps["divergences"][0]["kind"] == "unconfirmed"


def test_sans_rapprochement_la_consultation_repond_404(client, db: Session, make_user, auth_as):
    membre = make_user("Equipe")
    membre.is_staff = True
    db.flush()
    auth_as(membre)
    assert client.get("/api/v1/admin/reconciliation").status_code == 404


def test_une_transaction_du_double_nest_pas_confrontee(
    db: Session, momo, cotisation_en_cours
):
    # Le double n'a pas de relevé. La confronter au vrai opérateur la ferait
    # passer pour un succès sans contrepartie — c'est-à-dire pour une fraude.
    _, transaction = cotisation_en_cours
    transaction.provider = PROVIDER_DOUBLE
    _vieillir(db, transaction)
    _dire(momo, "SUCCESSFUL")

    run = rapprochement.rapprocher(db, momo)

    assert run.examined == 0
    assert db.execute(select(Divergence).where(Divergence.run_id == run.id)).all() == []
