"""Limitation de débit et révocation des jetons.

Ce sont les deux réponses aux questions qu'on pose toujours à une API qui
manipule de l'argent : que se passe-t-il si j'essaie mille mots de passe, et
que vaut un jeton volé après une déconnexion ?
"""

from datetime import UTC, datetime, timedelta

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.security import jeton_encore_valide
from app.models.rate_limit import RateLimitCounter
from app.services import limitation

API = "/api/v1"


def _connexion(client: TestClient, telephone: str, mot_de_passe: str):
    return client.post(f"{API}/auth/login", json={"phone": telephone, "password": mot_de_passe})


def test_les_echecs_repetes_sur_un_numero_finissent_bloques(client: TestClient, make_user):
    utilisateur = make_user("Cible")

    for _ in range(settings.login_max_par_numero):
        assert _connexion(client, utilisateur.phone, "mauvais").status_code == 401

    refus = _connexion(client, utilisateur.phone, "mauvais")
    assert refus.status_code == 429
    assert refus.headers["Retry-After"] == str(settings.login_fenetre_secondes)


def test_le_bon_mot_de_passe_ne_sauve_pas_dun_numero_bloque(client: TestClient, make_user):
    # Sinon la limite ne servirait à rien : il suffirait de tomber juste au
    # millième essai.
    utilisateur = make_user("Cible")
    for _ in range(settings.login_max_par_numero + 1):
        _connexion(client, utilisateur.phone, "mauvais")

    assert _connexion(client, utilisateur.phone, "motdepasse123").status_code == 429


def test_le_blocage_dun_numero_nempeche_pas_les_autres(client: TestClient, make_user):
    bloque = make_user("Bloque")
    autre = make_user("Autre")
    for _ in range(settings.login_max_par_numero + 1):
        _connexion(client, bloque.phone, "mauvais")

    # L'adresse est la même pour les deux : c'est bien le seau par numéro qui
    # a mordu, et lui seul.
    assert _connexion(client, autre.phone, "motdepasse123").status_code == 200


def test_linscription_est_limitee_par_adresse(client: TestClient):
    for index in range(settings.register_max_par_adresse):
        reponse = client.post(
            f"{API}/auth/register",
            json={
                "phone": f"+2290199000{index:02d}",
                "full_name": "Nouveau",
                "password": "motdepasse",
            },
        )
        assert reponse.status_code == 201

    debordement = client.post(
        f"{API}/auth/register",
        json={"phone": "+22901990099", "full_name": "Trop", "password": "motdepasse"},
    )
    assert debordement.status_code == 429


def test_une_tentative_refusee_reste_comptee(client: TestClient, db: Session, make_user):
    # Sans le commit du compteur, le rollback de la requête refusée effacerait
    # la trace de la tentative qui l'a motivée.
    utilisateur = make_user("Cible")
    _connexion(client, utilisateur.phone, "mauvais")

    compteur = db.execute(
        select(RateLimitCounter).where(
            RateLimitCounter.bucket == f"login:phone:{utilisateur.phone}"
        )
    ).scalar_one()
    assert compteur.count == 1


def test_la_deconnexion_invalide_le_jeton_dacces(client: TestClient, make_user):
    utilisateur = make_user("Partant")
    jetons = _connexion(client, utilisateur.phone, "motdepasse123").json()
    entetes = {"Authorization": f"Bearer {jetons['access_token']}"}

    assert client.get(f"{API}/auth/me", headers=entetes).status_code == 200
    assert client.post(f"{API}/auth/logout", headers=entetes).status_code == 204
    assert client.get(f"{API}/auth/me", headers=entetes).status_code == 401


def test_la_deconnexion_invalide_le_rafraichissement(client: TestClient, make_user):
    # C'est le jeton qui compte : sans lui, une session volée survivrait
    # trente jours à la déconnexion.
    utilisateur = make_user("Partant")
    jetons = _connexion(client, utilisateur.phone, "motdepasse123").json()
    entetes = {"Authorization": f"Bearer {jetons['access_token']}"}
    client.post(f"{API}/auth/logout", headers=entetes)

    reponse = client.post(
        f"{API}/auth/refresh", json={"refresh_token": jetons["refresh_token"]}
    )
    assert reponse.status_code == 401


def test_un_jeton_est_valide_sans_deconnexion_anterieure():
    assert jeton_encore_valide(None, datetime(2020, 1, 1, tzinfo=UTC)) is True


def test_un_jeton_emis_avant_la_deconnexion_est_refuse():
    coupure = datetime.now(UTC)
    assert jeton_encore_valide(coupure, coupure - timedelta(seconds=1)) is False


def test_un_jeton_emis_apres_la_deconnexion_est_accepte():
    coupure = datetime.now(UTC)
    assert jeton_encore_valide(coupure, coupure + timedelta(seconds=1)) is True


def test_la_purge_efface_les_fenetres_perimees(db: Session):
    vieille = datetime.now(UTC) - timedelta(days=2)
    db.add(RateLimitCounter(bucket="vieux", window_start=vieille, count=9))
    db.add(RateLimitCounter(bucket="recent", window_start=datetime.now(UTC), count=1))
    db.flush()

    assert limitation.purger(db) == 1
    restants = db.execute(select(RateLimitCounter.bucket)).scalars().all()
    assert list(restants) == ["recent"]
