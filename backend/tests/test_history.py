"""L'historique croise deux sources : ce qu'on verse et ce qu'on reçoit."""

from datetime import date

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.models.enums import Frequency
from app.models.tontine import Membership, TontineGroup
from app.services import tontine
from app.services.momo import FakeMoMoClient

API = "/api/v1"


@pytest.fixture
def tontine_reglee(db: Session, make_user, momo: FakeMoMoClient):
    """Une tontine à deux membres dont le premier tour est réglé et versé."""
    beneficiaire = make_user("Bénéficiaire")
    autre = make_user("Autre")

    group = TontineGroup(
        name="Historique",
        contribution_minor=4000,
        frequency=Frequency.MONTHLY,
        start_date=date(2026, 4, 1),
        created_by_id=beneficiaire.id,
    )
    db.add(group)
    db.flush()
    for position, membre in enumerate((beneficiaire, autre), start=1):
        db.add(Membership(group_id=group.id, user_id=membre.id, payout_position=position))
    db.flush()
    db.refresh(group)

    cycles = tontine.activate_group(db, group)
    cycle = cycles[0]

    for contribution in cycle.contributions:
        membership = db.get(Membership, contribution.membership_id)
        payeur = beneficiaire if membership.user_id == beneficiaire.id else autre
        transaction = tontine.initiate_contribution(
            db, contribution=contribution, payer=payeur, momo=momo
        )
        tontine.confirm_contribution(db, transaction, success=True)

    payout = tontine.pay_out_cycle(db, cycle, momo)
    tontine.confirm_payout(db, payout, cycle, success=True)
    db.flush()

    return {"beneficiaire": beneficiaire, "autre": autre, "group": group}


def test_le_beneficiaire_voit_sa_cotisation_et_son_versement(
    client: TestClient, tontine_reglee, auth_as
):
    auth_as(tontine_reglee["beneficiaire"])

    lignes = client.get(f"{API}/me/transactions").json()

    assert {ligne["direction"] for ligne in lignes} == {"in", "out"}
    entree = next(ligne for ligne in lignes if ligne["direction"] == "in")
    sortie = next(ligne for ligne in lignes if ligne["direction"] == "out")
    assert entree["amount_minor"] == 8000
    assert sortie["amount_minor"] == 4000
    assert entree["group_name"] == "Historique"


def test_lautre_membre_ne_voit_que_sa_cotisation(client: TestClient, tontine_reglee, auth_as):
    auth_as(tontine_reglee["autre"])

    lignes = client.get(f"{API}/me/transactions").json()

    # Le versement est allé au bénéficiaire du tour, pas à lui.
    assert [ligne["direction"] for ligne in lignes] == ["out"]
    assert lignes[0]["amount_minor"] == 4000


def test_historique_vide_pour_qui_na_aucune_tontine(client: TestClient, make_user, auth_as):
    auth_as(make_user("Solitaire"))
    assert client.get(f"{API}/me/transactions").json() == []


def test_historique_exige_un_jeton(client: TestClient):
    assert client.get(f"{API}/me/transactions").status_code == 401
