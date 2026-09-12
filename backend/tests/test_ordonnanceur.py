"""Ce que l'application entreprend d'elle-même.

Deux gestes périodiques qui ne doivent jamais se rencontrer : le rapprochement
applique le verdict d'un opérateur réel, le verdict du double tranche ce que le
client simulé laisse en suspens. La frontière entre les deux est ce que ces
tests protègent en premier — la franchir ferait passer pour encaissé de
l'argent qui n'a jamais bougé.
"""

import asyncio
from datetime import UTC, datetime

import pytest
from sqlalchemy.orm import Session

from app.models.enums import ContributionStatus, Frequency, TransactionStatus
from app.models.ledger import Transaction
from app.models.tontine import Membership, TontineGroup
from app.services import ordonnanceur, tontine
from app.services.momo import PROVIDER_DOUBLE, PROVIDER_MTN


@pytest.fixture
def cotisation_en_cours(db: Session, make_user, reseau):
    """Une cotisation partie chez l'opérateur, sans verdict reçu.

    Le réseau de test est tout entier le double : la transaction est donc
    consignée « fake », ce qui est exactement le cas de la démonstration.
    """
    membres = [make_user(f"M{index}") for index in range(2)]
    groupe = TontineGroup(
        name="Ordonnanceur",
        contribution_minor=2500,
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
        db, contribution=contribution, payer=payeur, reseau=reseau
    )
    db.flush()
    return contribution, transaction


class TestVerdictDuDouble:
    def test_une_cotisation_du_double_finit_par_aboutir(
        self, db: Session, cotisation_en_cours
    ):
        # Sans cela, l'écran d'attente de la démonstration tourne sans fin :
        # le client simulé n'émet aucun callback.
        contribution, transaction = cotisation_en_cours
        assert transaction.provider == PROVIDER_DOUBLE
        assert transaction.status == TransactionStatus.PROCESSING

        assert ordonnanceur.trancher_les_transactions_du_double(db) == 1

        db.refresh(transaction)
        db.refresh(contribution)
        assert transaction.status == TransactionStatus.SUCCESS
        assert contribution.status == ContributionStatus.PAID

    def test_une_transaction_partie_chez_un_vrai_operateur_est_epargnee(
        self, db: Session, cotisation_en_cours
    ):
        # La garde essentielle. MTN seul peut dire si son encaissement a
        # abouti ; le trancher ici inventerait de l'argent au grand livre.
        contribution, transaction = cotisation_en_cours
        transaction.provider = PROVIDER_MTN
        db.flush()

        assert ordonnanceur.trancher_les_transactions_du_double(db) == 0

        db.refresh(transaction)
        db.refresh(contribution)
        assert transaction.status == TransactionStatus.PROCESSING
        assert contribution.status == ContributionStatus.PROCESSING

    def test_une_transaction_deja_tranchee_nest_pas_retouchee(
        self, db: Session, cotisation_en_cours
    ):
        _, transaction = cotisation_en_cours
        ordonnanceur.trancher_les_transactions_du_double(db)

        # Une seconde passe ne trouve plus rien : le rejeu est inoffensif.
        assert ordonnanceur.trancher_les_transactions_du_double(db) == 0
        db.refresh(transaction)
        assert transaction.status == TransactionStatus.SUCCESS

    def test_un_refus_laisse_la_cotisation_due(self, db: Session, cotisation_en_cours):
        contribution, transaction = cotisation_en_cours

        assert ordonnanceur.trancher_les_transactions_du_double(db, succes=False) == 1

        db.refresh(transaction)
        db.refresh(contribution)
        assert transaction.status == TransactionStatus.FAILED
        # La dette reste : c'est le paiement qui a échoué, pas la cotisation.
        assert contribution.status == ContributionStatus.DUE

    def test_une_transaction_jamais_partie_nest_pas_tranchee(
        self, db: Session, cotisation_en_cours
    ):
        # `pending` : l'appel à l'opérateur n'a pas abouti. Il n'y a pas de
        # verdict à rendre pour une demande qui n'a jamais été formulée.
        _, transaction = cotisation_en_cours
        transaction.status = TransactionStatus.PENDING
        db.flush()

        assert ordonnanceur.trancher_les_transactions_du_double(db) == 0
        assert db.get(Transaction, transaction.id).status == TransactionStatus.PENDING


class TestBoucle:
    @pytest.mark.asyncio
    async def test_un_intervalle_nul_ne_lance_rien(self):
        # C'est le réglage des tests, et de tout contexte où l'application ne
        # doit rien entreprendre d'elle-même.
        assert ordonnanceur.demarrer("rien", 0, lambda: None) is None

    @pytest.mark.asyncio
    async def test_la_boucle_repete_son_geste(self):
        tours: list[int] = []
        tache = ordonnanceur.demarrer("compter", 0.01, lambda: tours.append(1))
        assert tache is not None
        await asyncio.sleep(0.05)
        await ordonnanceur.arreter([tache])

        assert len(tours) >= 2

    @pytest.mark.asyncio
    async def test_une_passe_en_echec_nemporte_pas_la_boucle(self):
        # Une base momentanément injoignable ne doit pas arrêter les
        # confirmations pour de bon.
        tours: list[int] = []

        def geste() -> None:
            tours.append(1)
            raise RuntimeError("base injoignable")

        tache = ordonnanceur.demarrer("casser", 0.01, geste)
        assert tache is not None
        await asyncio.sleep(0.05)
        await ordonnanceur.arreter([tache])

        assert len(tours) >= 2

    @pytest.mark.asyncio
    async def test_larret_attend_la_fin_des_boucles(self):
        tache = ordonnanceur.demarrer("dormir", 0.01, lambda: None)
        await ordonnanceur.arreter([tache, None])

        assert tache is not None
        assert tache.done()
