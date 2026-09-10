"""Parcours bout en bout à travers l'API HTTP."""

from datetime import date

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

API = "/api/v1"


def test_inscription_puis_acces_au_profil(client: TestClient):
    response = client.post(
        f"{API}/auth/register",
        json={"phone": "+22997000001", "full_name": "Leslie", "password": "motdepasse123"},
    )
    assert response.status_code == 201
    tokens = response.json()

    me = client.get(f"{API}/auth/me", headers={"Authorization": f"Bearer {tokens['access_token']}"})
    assert me.status_code == 200
    assert me.json()["phone"] == "+22997000001"


def test_numero_deja_inscrit_est_refuse(client: TestClient):
    payload = {"phone": "+22997000002", "full_name": "Doublon", "password": "motdepasse123"}
    assert client.post(f"{API}/auth/register", json=payload).status_code == 201
    assert client.post(f"{API}/auth/register", json=payload).status_code == 409


def test_mot_de_passe_faux_ne_dit_pas_si_le_compte_existe(client: TestClient):
    client.post(
        f"{API}/auth/register",
        json={"phone": "+22997000003", "full_name": "X", "password": "motdepasse123"},
    )
    connu = client.post(
        f"{API}/auth/login", json={"phone": "+22997000003", "password": "faux"}
    )
    inconnu = client.post(
        f"{API}/auth/login", json={"phone": "+22999999999", "password": "faux"}
    )
    assert connu.status_code == inconnu.status_code == 401
    assert connu.json()["detail"] == inconnu.json()["detail"]


def test_sans_jeton_laccess_est_refuse(client: TestClient):
    assert client.get(f"{API}/groups").status_code == 401


def test_creation_de_groupe_et_ajout_de_membre(
    client: TestClient, db: Session, make_user, auth_as
):
    createur = make_user("Créatrice")
    invite = make_user("Invité")
    auth_as(createur)

    created = client.post(
        f"{API}/groups",
        json={
            "name": "Tontine des couturières",
            "contribution_minor": 10000,
            "frequency": "monthly",
            "start_date": str(date(2026, 3, 1)),
        },
    )
    assert created.status_code == 201
    group_id = created.json()["id"]

    added = client.post(
        f"{API}/groups/{group_id}/members", json={"phone": invite.phone}
    )
    assert added.status_code == 201
    assert added.json()["payout_position"] == 2

    members = client.get(f"{API}/groups/{group_id}/members")
    assert [m["payout_position"] for m in members.json()] == [1, 2]


def test_non_membre_ne_voit_pas_le_groupe(client: TestClient, make_user, auth_as):
    proprietaire = make_user("Propriétaire")
    intrus = make_user("Intrus")
    auth_as(proprietaire)

    group_id = client.post(
        f"{API}/groups",
        json={
            "name": "Privée",
            "contribution_minor": 2000,
            "frequency": "weekly",
            "start_date": str(date(2026, 3, 1)),
        },
    ).json()["id"]

    auth_as(intrus)
    assert client.get(f"{API}/groups/{group_id}").status_code == 403


def test_activation_expose_les_cycles(client: TestClient, make_user, auth_as):
    createur = make_user("Admin")
    invite = make_user("Membre")
    auth_as(createur)

    group_id = client.post(
        f"{API}/groups",
        json={
            "name": "Duo",
            "contribution_minor": 5000,
            "frequency": "weekly",
            "start_date": str(date(2026, 3, 2)),
        },
    ).json()["id"]
    client.post(f"{API}/groups/{group_id}/members", json={"phone": invite.phone})

    activated = client.post(f"{API}/groups/{group_id}/activate")
    assert activated.status_code == 200
    cycles = activated.json()
    assert len(cycles) == 2
    assert [c["due_date"] for c in cycles] == ["2026-03-02", "2026-03-09"]

    # Un groupe démarré n'accepte plus de nouveau membre : l'ordre est figé.
    tardif = client.post(f"{API}/groups/{group_id}/members", json={"phone": invite.phone})
    assert tardif.status_code == 409


def test_la_sante_dit_qui_traite_les_paiements(client: TestClient):
    # Sans ce témoin, une clé d'opérateur oubliée ne se voit qu'au premier
    # paiement parti chez le double — c'est-à-dire trop tard.
    corps = client.get("/health").json()
    assert corps["status"] == "ok"
    assert set(corps["operators"]) == {"collection", "disbursement"}


def test_la_sante_ne_revele_aucune_cle(client: TestClient):
    from app.core.config import settings

    brut = client.get("/health").text
    for secret in (settings.jwt_secret, settings.momo_callback_secret):
        assert secret not in brut


def test_la_sante_liste_les_noms_momo_sans_les_valeurs(client: TestClient, monkeypatch):
    # Une variable absente, vide, ou écrite sous un nom fautif se ressemblent
    # toutes de l'extérieur. Le témoin les distingue.
    monkeypatch.setenv("MOMO_DISBURSEMENT_KEY", "une-cle-secrete")
    monkeypatch.setenv("MOMO_COLLECTION_KEY", "   ")

    corps = client.get("/health").json()

    assert corps["momo_env"]["MOMO_DISBURSEMENT_KEY"] is True
    assert corps["momo_env"]["MOMO_COLLECTION_KEY"] is False
    assert "une-cle-secrete" not in client.get("/health").text
