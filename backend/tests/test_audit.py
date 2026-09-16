"""Le journal d'audit.

Ce qu'un journal doit garantir tient en trois points, et c'est ce que ces
tests vérifient : une action qui aboutit laisse une trace, une action annulée
n'en laisse pas, et un refus en laisse une que rien n'efface.
"""

from datetime import date
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import settings
from app.models.audit import AuditEvent
from app.models.enums import AuditAction, AuditOutcome
from app.services import audit

API = "/api/v1"


def _creer_groupe(client: TestClient, nom: str = "Tontine") -> str:
    return client.post(
        f"{API}/groups",
        json={
            "name": nom,
            "contribution_minor": 5000,
            "frequency": "monthly",
            "start_date": str(date(2026, 4, 1)),
        },
    ).json()["id"]


def _evenements(db: Session, action: AuditAction | None = None) -> list[AuditEvent]:
    stmt = select(AuditEvent).order_by(AuditEvent.occurred_at)
    if action is not None:
        stmt = stmt.where(AuditEvent.action == action)
    return list(db.execute(stmt).scalars().all())


class TestCeQuiEstConsigne:
    def test_la_creation_dune_tontine_laisse_une_trace(
        self, client: TestClient, db: Session, make_user, auth_as
    ):
        createur = make_user("Créatrice")
        auth_as(createur)
        group_id = _creer_groupe(client, "Tontine des couturières")

        trace = _evenements(db, AuditAction.GROUP_CREATED)
        assert len(trace) == 1
        assert trace[0].actor_id == createur.id
        assert str(trace[0].target_id) == group_id
        assert trace[0].outcome == AuditOutcome.ALLOWED
        assert trace[0].details["name"] == "Tontine des couturières"

    def test_lajout_dun_membre_retient_qui_et_a_quelle_place(
        self, client: TestClient, db: Session, make_user, auth_as
    ):
        # Qui touchera la cagnotte, et dans quel ordre : c'est exactement ce
        # qu'on veut pouvoir relire six mois plus tard.
        createur = make_user("Admin")
        invite = make_user("Invité")
        auth_as(createur)
        group_id = _creer_groupe(client)
        client.post(f"{API}/groups/{group_id}/members", json={"phone": invite.phone})

        trace = _evenements(db, AuditAction.MEMBER_ADDED)
        assert len(trace) == 1
        assert trace[0].details["member_user_id"] == str(invite.id)
        assert trace[0].details["payout_position"] == 2

    def test_lactivation_est_consignee(
        self, client: TestClient, db: Session, make_user, auth_as
    ):
        createur = make_user("Admin")
        invite = make_user("Membre")
        auth_as(createur)
        group_id = _creer_groupe(client)
        client.post(f"{API}/groups/{group_id}/members", json={"phone": invite.phone})
        assert client.post(f"{API}/groups/{group_id}/activate").status_code == 200

        trace = _evenements(db, AuditAction.GROUP_ACTIVATED)
        assert len(trace) == 1
        # L'ordre de passage se fige à cet instant : le nombre de tours créés
        # dit combien de membres il engageait.
        assert trace[0].details["cycles"] == 2

    def test_le_numero_de_lacteur_est_recopie_dans_la_trace(
        self, client: TestClient, db: Session, make_user, auth_as
    ):
        # Un compte peut disparaître ; la ligne doit rester lisible.
        createur = make_user("Créatrice")
        auth_as(createur)
        _creer_groupe(client)

        assert _evenements(db)[0].actor_phone == createur.phone


class TestCeQuiNestPasConsigne:
    def test_une_lecture_ne_laisse_aucune_trace(
        self, client: TestClient, db: Session, make_user, auth_as
    ):
        # Journaliser les consultations noierait les actions dans le bruit.
        createur = make_user("Créatrice")
        auth_as(createur)
        group_id = _creer_groupe(client)
        avant = len(_evenements(db))

        client.get(f"{API}/groups/{group_id}")
        client.get(f"{API}/groups/{group_id}/members")
        client.get(f"{API}/groups")

        assert len(_evenements(db)) == avant

    def test_une_action_qui_echoue_ne_laisse_pas_de_trace_de_succes(
        self, client: TestClient, db: Session, make_user, auth_as
    ):
        # Le membre n'existe pas : la route répond 404 et la transaction est
        # défaite. Une trace d'ajout serait un mensonge.
        createur = make_user("Admin")
        auth_as(createur)
        group_id = _creer_groupe(client)

        refus = client.post(f"{API}/groups/{group_id}/members", json={"phone": "+22900000000"})
        assert refus.status_code == 404
        assert _evenements(db, AuditAction.MEMBER_ADDED) == []


class TestLesRefus:
    def test_un_non_administrateur_qui_tente_dactiver_est_consigne(
        self, client: TestClient, db: Session, make_user, auth_as
    ):
        createur = make_user("Admin")
        intrus = make_user("Intrus")
        auth_as(createur)
        group_id = _creer_groupe(client)
        client.post(f"{API}/groups/{group_id}/members", json={"phone": intrus.phone})

        auth_as(intrus)
        assert client.post(f"{API}/groups/{group_id}/activate").status_code == 403

        trace = _evenements(db, AuditAction.GROUP_ACTIVATED)
        assert len(trace) == 1
        assert trace[0].outcome == AuditOutcome.DENIED
        assert trace[0].actor_id == intrus.id
        assert trace[0].details["motif"] == "Action réservée à l'administrateur."

    def test_un_non_membre_qui_tente_un_versement_est_consigne(
        self, client: TestClient, db: Session, make_user, auth_as
    ):
        # L'action la plus lourde de l'application : une tentative vaut d'être
        # retenue même — surtout — quand elle échoue.
        createur = make_user("Admin")
        intrus = make_user("Intrus")
        auth_as(createur)
        group_id = _creer_groupe(client)
        client.post(f"{API}/groups/{group_id}/members", json={"phone": intrus.phone})
        cycles = client.post(f"{API}/groups/{group_id}/activate").json()

        auth_as(intrus)
        assert client.post(f"{API}/cycles/{cycles[0]['id']}/payout").status_code == 403

        trace = _evenements(db, AuditAction.CYCLE_PAID_OUT)
        assert len(trace) == 1
        assert trace[0].outcome == AuditOutcome.DENIED
        assert str(trace[0].target_id) == cycles[0]["id"]

    def test_un_refus_survit_a_lannulation_de_la_requete(self, db: Session):
        """Le point qui justifie une session à part.

        On consigne un refus dans une session indépendante, puis on défait
        celle de la « requête » comme le ferait l'exception. Le refus doit
        rester : c'est précisément le genre de fait qu'un journal existe pour
        retenir, et l'écrire dans la session de la requête reviendrait à ne
        rien écrire du tout.

        L'acteur est laissé vide à dessein : les comptes du test vivent dans
        une transaction que les autres connexions ne voient pas. C'est un
        marqueur sur la cible qui sert à retrouver la ligne.
        """
        marqueur = uuid4()
        moteur = create_engine(settings.database_url, future=True)
        Fabrique = sessionmaker(bind=moteur, future=True)

        try:
            with Fabrique() as journal:
                audit.consigner_refus(
                    journal,
                    acteur=None,
                    action=AuditAction.CYCLE_PAID_OUT,
                    motif="Action réservée à l'administrateur.",
                    cible_type="cycle",
                    cible_id=marqueur,
                )

            db.rollback()

            with Fabrique() as lecture:
                trouve = list(
                    lecture.execute(
                        select(AuditEvent).where(AuditEvent.target_id == marqueur)
                    ).scalars().all()
                )
            assert len(trouve) == 1
            assert trouve[0].outcome == AuditOutcome.DENIED
        finally:
            # Cette ligne a été validée pour de bon, hors de la transaction du
            # test : à lui de la ranger.
            with Fabrique() as menage:
                menage.execute(
                    AuditEvent.__table__.delete().where(AuditEvent.target_id == marqueur)
                )
                menage.commit()
            moteur.dispose()


class TestConsultation:
    @pytest.fixture
    def equipe(self, db: Session, make_user, auth_as):
        membre = make_user("Équipe")
        membre.is_staff = True
        db.flush()
        auth_as(membre)
        return membre

    def test_le_journal_est_refuse_au_simple_membre(
        self, client: TestClient, make_user, auth_as
    ):
        auth_as(make_user("Membre"))
        assert client.get(f"{API}/admin/audit").status_code == 403

    def test_lequipe_lit_le_journal_du_plus_recent_au_plus_ancien(
        self, client: TestClient, equipe
    ):
        _creer_groupe(client, "Première")
        _creer_groupe(client, "Seconde")

        lignes = client.get(f"{API}/admin/audit").json()
        assert [ligne["details"]["name"] for ligne in lignes[:2]] == ["Seconde", "Première"]

    def test_le_journal_se_filtre_par_action_et_par_issue(
        self, client: TestClient, equipe, make_user, auth_as
    ):
        _creer_groupe(client, "Filtrée")

        creations = client.get(
            f"{API}/admin/audit", params={"action": "group.created"}
        ).json()
        assert creations and all(ligne["action"] == "group.created" for ligne in creations)

        refuses = client.get(f"{API}/admin/audit", params={"outcome": "denied"}).json()
        assert refuses == []

    def test_le_journal_ne_sexpose_quen_lecture(self, client: TestClient):
        """Un journal qui se modifie ne prouve rien.

        Vérifié sur le contrat lui-même plutôt que par des appels : une route
        absente répond 404, ce qu'une faute de frappe dans l'URL produirait
        aussi. L'OpenAPI, lui, dit exactement ce qui existe.
        """
        chemins = client.get("/openapi.json").json()["paths"]

        assert set(chemins["/api/v1/admin/audit"]) == {"get"}
        assert not [c for c in chemins if c.startswith("/api/v1/admin/audit/")]
