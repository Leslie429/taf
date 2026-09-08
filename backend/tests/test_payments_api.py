"""Le chemin de l'argent, vu depuis HTTP.

Ces routes déclenchent des appels opérateur : elles méritent d'être couvertes
en intégration, pas seulement au niveau des services.
"""

import hashlib
import hmac
import json
from datetime import date

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.tontine import Membership
from app.services.momo import FakeMoMoClient

API = "/api/v1"


def _signed(payload: dict) -> tuple[str, dict[str, str]]:
    body = json.dumps(payload)
    signature = hmac.new(
        settings.momo_callback_secret.encode(), body.encode(), hashlib.sha256
    ).hexdigest()
    return body, {"X-Callback-Signature": signature, "Content-Type": "application/json"}


@pytest.fixture
def tontine_active(client: TestClient, db: Session, make_user, auth_as):
    """Une tontine à deux membres, démarrée, avec ses cycles engendrés."""
    admin = make_user("Admin")
    membre = make_user("Membre")
    auth_as(admin)

    group_id = client.post(
        f"{API}/groups",
        json={
            "name": "Paiements",
            "contribution_minor": 5000,
            "frequency": "monthly",
            "start_date": str(date(2026, 6, 1)),
        },
    ).json()["id"]
    client.post(f"{API}/groups/{group_id}/members", json={"phone": membre.phone})
    cycles = client.post(f"{API}/groups/{group_id}/activate").json()

    memberships = {
        m.user_id: m.id
        for m in db.query(Membership).filter(Membership.group_id == group_id).all()
    }
    return {
        "group_id": group_id,
        "cycles": cycles,
        "admin": admin,
        "membre": membre,
        "memberships": memberships,
    }


def _contribution_de(contexte: dict, user, cycle_index: int = 0) -> dict:
    membership_id = str(contexte["memberships"][user.id])
    cycle = contexte["cycles"][cycle_index]
    return next(c for c in cycle["contributions"] if c["membership_id"] == membership_id)


def test_paiement_de_sa_cotisation(
    client: TestClient, tontine_active, auth_as, momo: FakeMoMoClient
):
    membre = tontine_active["membre"]
    auth_as(membre)
    contribution = _contribution_de(tontine_active, membre)

    response = client.post(f"{API}/contributions/{contribution['id']}/pay")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "processing"
    assert body["amount_minor"] == 5000
    assert len(momo.calls) == 1
    assert momo.calls[0]["phone"] == membre.phone


def test_payer_la_cotisation_dun_autre_est_refuse(client: TestClient, tontine_active, auth_as):
    auth_as(tontine_active["admin"])
    contribution = _contribution_de(tontine_active, tontine_active["membre"])

    assert client.post(f"{API}/contributions/{contribution['id']}/pay").status_code == 403


def test_cotisation_inconnue_donne_404(client: TestClient, tontine_active, auth_as):
    auth_as(tontine_active["admin"])
    inconnu = "00000000-0000-0000-0000-000000000000"

    assert client.post(f"{API}/contributions/{inconnu}/pay").status_code == 404


def test_versement_refuse_tant_que_le_cycle_nest_pas_finance(
    client: TestClient, tontine_active, auth_as
):
    auth_as(tontine_active["admin"])
    cycle_id = tontine_active["cycles"][0]["id"]

    response = client.post(f"{API}/cycles/{cycle_id}/payout")

    assert response.status_code == 409
    assert "financé" in response.json()["detail"]


def test_versement_reserve_a_ladministrateur(client: TestClient, tontine_active, auth_as):
    auth_as(tontine_active["membre"])
    cycle_id = tontine_active["cycles"][0]["id"]

    assert client.post(f"{API}/cycles/{cycle_id}/payout").status_code == 403


def test_tour_complet_de_la_cotisation_au_versement(
    client: TestClient, tontine_active, auth_as, momo: FakeMoMoClient
):
    group_id = tontine_active["group_id"]
    cycle = tontine_active["cycles"][0]

    # Chaque membre règle sa part, puis l'opérateur confirme.
    for user in (tontine_active["admin"], tontine_active["membre"]):
        auth_as(user)
        contribution = _contribution_de(tontine_active, user)
        transaction = client.post(f"{API}/contributions/{contribution['id']}/pay").json()
        body, headers = _signed({"externalId": transaction["id"], "status": "SUCCESSFUL"})
        assert client.post(f"{API}/webhooks/momo", content=body, headers=headers).json() == {
            "status": "processed"
        }

    auth_as(tontine_active["admin"])
    assert client.get(f"{API}/groups/{group_id}/balance").json()["balance_minor"] == 10000
    assert client.get(f"{API}/groups/{group_id}/cycles").json()[0]["status"] == "funded"

    payout = client.post(f"{API}/cycles/{cycle['id']}/payout")
    assert payout.status_code == 200
    assert payout.json()["amount_minor"] == 10000

    body, headers = _signed({"externalId": payout.json()["id"], "status": "SUCCESSFUL"})
    client.post(f"{API}/webhooks/momo", content=body, headers=headers)

    # La cagnotte est repartie chez le bénéficiaire : le solde retombe à zéro.
    assert client.get(f"{API}/groups/{group_id}/balance").json()["balance_minor"] == 0
    assert client.get(f"{API}/groups/{group_id}/cycles").json()[0]["status"] == "paid_out"
    assert [c["kind"] for c in momo.calls] == ["collect", "collect", "transfer"]


def test_callback_avec_identifiant_non_uuid_est_refuse(client: TestClient):
    body, headers = _signed({"externalId": "pas-un-uuid", "status": "SUCCESSFUL"})

    assert client.post(f"{API}/webhooks/momo", content=body, headers=headers).status_code == 400


def test_callback_sur_transaction_inconnue_est_acquitte(client: TestClient):
    body, headers = _signed(
        {"externalId": "11111111-2222-3333-4444-555555555555", "status": "SUCCESSFUL"}
    )

    response = client.post(f"{API}/webhooks/momo", content=body, headers=headers)

    # On acquitte pour que l'opérateur cesse de réessayer, mais on le journalise.
    assert response.status_code == 202
    assert response.json()["status"] == "unknown_transaction"
