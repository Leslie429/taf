"""Les relances des cotisations en retard.

Ce qu'une relance automatique doit garantir : partir quand il le faut, ne
jamais partir deux fois pour la même chose le même jour, et s'arrêter d'elle-
même quand elle n'apprend plus rien à personne.
"""

from datetime import date, timedelta

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.enums import (
    ContributionStatus,
    CycleStatus,
    Frequency,
    NotificationStatus,
)
from app.models.notification import Notification
from app.models.tontine import Membership, TontineGroup
from app.services import relances, tontine
from app.services.sms import FakeSmsClient, SmsError

API = "/api/v1"


@pytest.fixture
def tontine_en_retard(db: Session, make_user):
    """Une tontine dont le premier tour est échu et impayé.

    Départ il y a trois jours, cadence hebdomadaire : le tour 1 est en retard
    de trois jours, le tour 2 n'est pas encore dû. Un seul tour en retard, ce
    qui rend les comptes lisibles.
    """
    membres = [make_user(f"M{index}") for index in range(2)]
    groupe = TontineGroup(
        name="Dantokpa",
        contribution_minor=5000,
        frequency=Frequency.WEEKLY,
        start_date=date.today() - timedelta(days=3),
        created_by_id=membres[0].id,
    )
    db.add(groupe)
    db.flush()
    for position, membre in enumerate(membres, start=1):
        db.add(Membership(group_id=groupe.id, user_id=membre.id, payout_position=position))
    db.flush()
    db.refresh(groupe)

    cycles = tontine.activate_group(db, groupe)
    assert cycles[0].due_date == date.today() - timedelta(days=3)
    assert cycles[1].due_date > date.today()
    return groupe, cycles[0], membres


def _notifications(db: Session) -> list[Notification]:
    return list(
        db.execute(select(Notification).order_by(Notification.created_at)).scalars().all()
    )


class TestReperage:
    def test_une_cotisation_echue_et_impayee_est_relancee(
        self, db: Session, tontine_en_retard
    ):
        _, _, membres = tontine_en_retard

        assert relances.reperer(db) == 2

        inscrites = _notifications(db)
        assert {n.user_id for n in inscrites} == {m.id for m in membres}
        assert all(n.status == NotificationStatus.PENDING for n in inscrites)

    def test_le_tour_passe_en_retard(self, db: Session, tontine_en_retard):
        # Que la relance parte ou non, l'état du tour doit le dire : c'est ce
        # que lit la barre de tours du front.
        _, cycle, _ = tontine_en_retard
        relances.reperer(db)

        db.refresh(cycle)
        assert cycle.status == CycleStatus.LATE

    def test_une_cotisation_a_jour_nest_pas_relancee(self, db: Session, make_user):
        membres = [make_user(f"M{index}") for index in range(2)]
        groupe = TontineGroup(
            name="À jour",
            contribution_minor=5000,
            frequency=Frequency.WEEKLY,
            # L'échéance est dans le futur.
            start_date=date.today() + timedelta(days=7),
            created_by_id=membres[0].id,
        )
        db.add(groupe)
        db.flush()
        for position, membre in enumerate(membres, start=1):
            db.add(Membership(group_id=groupe.id, user_id=membre.id, payout_position=position))
        db.flush()
        db.refresh(groupe)
        tontine.activate_group(db, groupe)

        assert relances.reperer(db) == 0

    def test_une_cotisation_deja_payee_nest_pas_relancee(
        self, db: Session, tontine_en_retard
    ):
        _, cycle, _ = tontine_en_retard
        cycle.contributions[0].status = ContributionStatus.PAID
        db.flush()

        assert relances.reperer(db) == 1

    def test_le_message_dit_le_montant_la_tontine_et_le_retard(
        self, db: Session, tontine_en_retard
    ):
        relances.reperer(db)
        corps = _notifications(db)[0].body

        assert "Dantokpa" in corps
        assert "5000 F" in corps
        assert "3 jours" in corps


class TestLeHarcelement:
    def test_deux_passes_le_meme_jour_ne_relancent_quune_fois(
        self, db: Session, tontine_en_retard
    ):
        # L'ordonnanceur repasse toutes les heures : sans ce garde-fou, un
        # membre recevrait vingt-quatre SMS par jour.
        assert relances.reperer(db) == 2
        assert relances.reperer(db) == 0
        assert len(_notifications(db)) == 2

    def test_le_lendemain_relance_a_nouveau(self, db: Session, tontine_en_retard):
        relances.reperer(db, aujourdhui=date.today() - timedelta(days=1))
        assert relances.reperer(db) == 2
        assert len(_notifications(db)) == 4

    def test_les_relances_sarretent_apres_cinq_passages(
        self, db: Session, tontine_en_retard
    ):
        # Passé cinq relances, le retard est installé : c'est une conversation
        # qu'il faut, pas un SMS de plus.
        #
        # L'échéance est à J-3 : seules les journées postérieures produisent
        # une relance, d'où ces cinq jours-là et pas un recul quelconque.
        cinq_jours = [
            date.today() + timedelta(days=decalage)
            for decalage in range(-2, relances.RELANCES_MAX_PAR_COTISATION - 2)
        ]
        assert len(cinq_jours) == relances.RELANCES_MAX_PAR_COTISATION
        for jour in cinq_jours:
            assert relances.reperer(db, aujourdhui=jour) == 2

        avant = len(_notifications(db))
        assert relances.reperer(db, aujourdhui=cinq_jours[-1] + timedelta(days=1)) == 0
        assert len(_notifications(db)) == avant

    def test_un_doublon_nemporte_pas_les_relances_deja_inscrites(
        self, db: Session, tontine_en_retard
    ):
        _, cycle, _ = tontine_en_retard
        # Une seule des deux cotisations a déjà sa relance du jour.
        premiere = cycle.contributions[0]
        db.add(
            Notification(
                user_id=db.get(Membership, premiere.membership_id).user_id,
                kind="contribution.late",
                dedupe_key=f"relance:contribution:{premiere.id}:{date.today().isoformat()}",
                destination="+22900000000",
                body="déjà dit",
                contribution_id=premiere.id,
            )
        )
        db.flush()

        # La seconde doit passer malgré le heurt sur la première.
        assert relances.reperer(db) == 1


class TestAcheminement:
    def test_les_relances_en_attente_partent(self, db: Session, tontine_en_retard):
        relances.reperer(db)
        canal = FakeSmsClient()

        assert relances.acheminer(db, canal) == (2, 0)
        assert len(canal.envois) == 2
        assert all(n.status == NotificationStatus.SENT for n in _notifications(db))
        assert all(n.sent_at is not None for n in _notifications(db))

    def test_un_envoi_qui_echoue_laisse_son_motif(self, db: Session, tontine_en_retard):
        relances.reperer(db)

        class CanalEnPanne:
            def provider(self) -> str:
                return "panne"

            def envoyer(self, *, destinataire: str, texte: str) -> str:
                raise SmsError("Opérateur injoignable")

        assert relances.acheminer(db, CanalEnPanne()) == (0, 2)
        for notification in _notifications(db):
            assert notification.status == NotificationStatus.FAILED
            assert notification.last_error == "Opérateur injoignable"
            assert notification.attempts == 1

    def test_une_relance_deja_partie_ne_repart_pas(self, db: Session, tontine_en_retard):
        relances.reperer(db)
        canal = FakeSmsClient()
        relances.acheminer(db, canal)

        assert relances.acheminer(db, canal) == (0, 0)
        assert len(canal.envois) == 2


class TestConsultation:
    def test_le_membre_lit_ses_relances(
        self, client, db: Session, tontine_en_retard, auth_as
    ):
        _, _, membres = tontine_en_retard
        relances.reperer(db)
        auth_as(membres[0])

        lues = client.get(f"{API}/me/notifications").json()
        assert len(lues) == 1
        assert lues[0]["kind"] == "contribution.late"
        assert lues[0]["status"] == "pending"

    def test_un_membre_ne_voit_pas_les_relances_dun_autre(
        self, client, db: Session, tontine_en_retard, auth_as, make_user
    ):
        relances.reperer(db)
        auth_as(make_user("Étranger"))

        assert client.get(f"{API}/me/notifications").json() == []
