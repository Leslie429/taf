"""Le webhook est la surface la plus exposée : signature, rejeu, verdicts."""

import hashlib
import hmac
import json
from datetime import date
from uuid import uuid4

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.enums import ContributionStatus, Frequency, TransactionStatus
from app.models.tontine import Membership, TontineGroup
from app.services import tontine
from app.services.momo import FakeMoMoClient

API = "/api/v1"


def _signed(payload: dict) -> tuple[str, dict[str, str]]:
    body = json.dumps(payload)
    signature = hmac.new(
        settings.momo_callback_secret.encode(), body.encode(), hashlib.sha256
    ).hexdigest()
    return body, {"X-Callback-Signature": signature, "Content-Type": "application/json"}


def _contribution_en_cours(db: Session, make_user, reseau):
    membres = [make_user(f"M{i}") for i in range(2)]
    group = TontineGroup(
        name="Webhook",
        contribution_minor=3000,
        frequency=Frequency.WEEKLY,
        start_date=date(2026, 5, 4),
        created_by_id=membres[0].id,
    )
    db.add(group)
    db.flush()
    for position, membre in enumerate(membres, start=1):
        db.add(Membership(group_id=group.id, user_id=membre.id, payout_position=position))
    db.flush()
    db.refresh(group)

    cycles = tontine.activate_group(db, group)
    contribution = cycles[0].contributions[0]
    membership = db.get(Membership, contribution.membership_id)
    payeur = next(m for m in membres if m.id == membership.user_id)
    tx = tontine.initiate_contribution(db, contribution=contribution, payer=payeur, reseau=reseau)
    db.flush()
    return contribution, tx


def test_signature_invalide_est_rejetee(client: TestClient):
    response = client.post(
        f"{API}/webhooks/momo",
        content=json.dumps({"externalId": "peu-importe", "status": "SUCCESSFUL"}),
        headers={"X-Callback-Signature": "faux", "Content-Type": "application/json"},
    )
    assert response.status_code == 401


def test_callback_reussi_solde_la_cotisation(
    client: TestClient, db: Session, make_user, momo: FakeMoMoClient, reseau
):
    contribution, tx = _contribution_en_cours(db, make_user, reseau)
    body, headers = _signed({"externalId": str(tx.id), "status": "SUCCESSFUL"})

    response = client.post(f"{API}/webhooks/momo", content=body, headers=headers)

    assert response.status_code == 202
    assert response.json()["status"] == "processed"
    db.refresh(contribution)
    assert contribution.status == ContributionStatus.PAID


def test_callback_rejoue_reste_sans_effet(
    client: TestClient, db: Session, make_user, momo: FakeMoMoClient, reseau
):
    contribution, tx = _contribution_en_cours(db, make_user, reseau)
    body, headers = _signed({"externalId": str(tx.id), "status": "SUCCESSFUL"})

    premier = client.post(f"{API}/webhooks/momo", content=body, headers=headers)
    second = client.post(f"{API}/webhooks/momo", content=body, headers=headers)

    assert premier.json()["status"] == "processed"
    assert second.json()["status"] == "duplicate"
    db.refresh(tx)
    assert tx.status == TransactionStatus.SUCCESS


def test_callback_en_echec_laisse_la_cotisation_due(
    client: TestClient, db: Session, make_user, momo: FakeMoMoClient, reseau
):
    contribution, tx = _contribution_en_cours(db, make_user, reseau)
    body, headers = _signed({"externalId": str(tx.id), "status": "FAILED"})

    client.post(f"{API}/webhooks/momo", content=body, headers=headers)

    db.refresh(contribution)
    assert contribution.status == ContributionStatus.DUE


def _operateur_reel(monkeypatch):
    """Fait croire à la route qu'un opérateur réel est configuré."""
    from app.core.config import Settings

    monkeypatch.setattr(
        "app.api.routes.payments.settings", Settings(momo_collection_key="cle")
    )


def test_un_callback_non_signe_est_rejete_sans_operateur_reel(client: TestClient):
    # En développement, seul le double nous appelle : rien ne justifie l'absence
    # de signature.
    reponse = client.post(
        f"{API}/webhooks/momo",
        content=json.dumps({"externalId": str(uuid4()), "status": "SUCCESSFUL"}),
        headers={"Content-Type": "application/json"},
    )
    assert reponse.status_code == 401


def test_un_callback_non_signe_fait_foi_de_lavis_de_loperateur(
    client: TestClient, db: Session, make_user, momo: FakeMoMoClient, reseau, monkeypatch
):
    # MTN ne signe pas : son appel n'est qu'un indice. Le corps annonce un
    # échec, l'opérateur interrogé dit le contraire — c'est lui qui tranche.
    _operateur_reel(monkeypatch)
    contribution, tx = _contribution_en_cours(db, make_user, reseau)
    monkeypatch.setattr(momo, "status", lambda **_: {"status": "SUCCESSFUL"})

    reponse = client.post(
        f"{API}/webhooks/momo",
        content=json.dumps({"externalId": str(tx.id), "status": "FAILED"}),
        headers={"Content-Type": "application/json"},
    )

    assert reponse.status_code == 202
    assert reponse.json()["status"] == "processed"
    db.refresh(contribution)
    assert contribution.status == ContributionStatus.PAID


def test_un_corps_forge_ne_peut_pas_fabriquer_un_succes(
    client: TestClient, db: Session, make_user, momo: FakeMoMoClient, reseau, monkeypatch
):
    # C'est la propriété qui remplace la signature : au pire, un faux callback
    # nous fait interroger l'opérateur pour rien.
    _operateur_reel(monkeypatch)
    contribution, tx = _contribution_en_cours(db, make_user, reseau)
    monkeypatch.setattr(momo, "status", lambda **_: {"status": "FAILED"})

    client.post(
        f"{API}/webhooks/momo",
        content=json.dumps({"externalId": str(tx.id), "status": "SUCCESSFUL"}),
        headers={"Content-Type": "application/json"},
    )

    db.refresh(contribution)
    assert contribution.status == ContributionStatus.DUE
    db.refresh(tx)
    assert tx.status == TransactionStatus.FAILED


def test_un_operateur_indecis_ne_change_rien(
    client: TestClient, db: Session, make_user, momo: FakeMoMoClient, reseau, monkeypatch
):
    # Transaction encore en cours chez l'opérateur : on n'invente pas de verdict.
    _operateur_reel(monkeypatch)
    contribution, tx = _contribution_en_cours(db, make_user, reseau)
    monkeypatch.setattr(momo, "status", lambda **_: {"status": "PENDING"})

    reponse = client.post(
        f"{API}/webhooks/momo",
        content=json.dumps({"externalId": str(tx.id), "status": "SUCCESSFUL"}),
        headers={"Content-Type": "application/json"},
    )

    assert reponse.json()["status"] == "unverified"
    db.refresh(contribution)
    assert contribution.status == ContributionStatus.PROCESSING
