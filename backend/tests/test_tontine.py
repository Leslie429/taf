from datetime import date

import httpx
import pytest
from sqlalchemy.orm import Session

from app.models.enums import (
    ContributionStatus,
    CycleStatus,
    Frequency,
    GroupStatus,
    TransactionStatus,
)
from app.models.tontine import Membership, TontineGroup
from app.services import ledger, tontine
from app.services.momo import FakeMoMoClient, MoMoError
from app.services.operateurs import Operateurs


def _reseau(double: FakeMoMoClient) -> Operateurs:
    """Un réseau à un seul opérateur, pour un test qui pilote son double."""
    return Operateurs(clients={"fake": double, "mtn_momo": double},
                      prefixes={}, defaut="mtn_momo")


@pytest.fixture
def groupe(db: Session, make_user):
    membres = [make_user(f"Membre {i}") for i in range(3)]
    group = TontineGroup(
        name="Tontine du marché",
        contribution_minor=5000,
        frequency=Frequency.MONTHLY,
        start_date=date(2026, 1, 15),
        created_by_id=membres[0].id,
    )
    db.add(group)
    db.flush()
    for position, membre in enumerate(membres, start=1):
        db.add(
            Membership(
                group_id=group.id,
                user_id=membre.id,
                payout_position=position,
                is_admin=position == 1,
            )
        )
    db.flush()
    db.refresh(group)
    return group, membres


def test_activation_engendre_un_cycle_par_membre(db: Session, groupe):
    group, membres = groupe
    cycles = tontine.activate_group(db, group)

    assert group.status == GroupStatus.ACTIVE
    assert len(cycles) == len(membres)
    # Chaque cycle appelle une cotisation de chacun.
    assert all(len(c.contributions) == len(membres) for c in cycles)
    # Chaque membre est bénéficiaire exactement une fois.
    assert len({c.beneficiary_membership_id for c in cycles}) == len(membres)


def test_echeances_mensuelles_se_suivent(db: Session, groupe):
    group, _ = groupe
    cycles = tontine.activate_group(db, group)
    assert [c.due_date for c in cycles] == [
        date(2026, 1, 15),
        date(2026, 2, 15),
        date(2026, 3, 15),
    ]


def test_echeance_mensuelle_ramenee_en_fin_de_mois(db: Session, groupe):
    group, _ = groupe
    group.start_date = date(2026, 1, 31)
    cycles = tontine.activate_group(db, group)
    # Le 31 février n'existe pas : on retombe sur le dernier jour du mois.
    assert cycles[1].due_date == date(2026, 2, 28)


def test_groupe_a_un_seul_membre_refuse_de_demarrer(db: Session, make_user):
    createur = make_user()
    group = TontineGroup(
        name="Trop petite",
        contribution_minor=1000,
        frequency=Frequency.WEEKLY,
        start_date=date(2026, 1, 1),
        created_by_id=createur.id,
    )
    db.add(group)
    db.flush()
    db.add(Membership(group_id=group.id, user_id=createur.id, payout_position=1, is_admin=True))
    db.flush()
    db.refresh(group)

    with pytest.raises(tontine.TontineError):
        tontine.activate_group(db, group)


def test_double_clic_ne_declenche_quun_seul_appel_operateur(
    db: Session, groupe, momo: FakeMoMoClient, reseau):
    group, membres = groupe
    cycles = tontine.activate_group(db, group)
    contribution = cycles[0].contributions[0]
    payeur = next(
        m for m in membres if m.id == db.get(Membership, contribution.membership_id).user_id
    )

    first = tontine.initiate_contribution(
        db, contribution=contribution, payer=payeur, reseau=reseau
    )
    second = tontine.initiate_contribution(
        db, contribution=contribution, payer=payeur, reseau=reseau
    )

    assert first.id == second.id
    assert len(momo.calls) == 1


def test_cycle_devient_finance_quand_tout_le_monde_a_paye(
    db: Session, groupe, momo: FakeMoMoClient, reseau):
    group, membres = groupe
    cycles = tontine.activate_group(db, group)
    cycle = cycles[0]

    for contribution in cycle.contributions:
        membership = db.get(Membership, contribution.membership_id)
        payeur = next(m for m in membres if m.id == membership.user_id)
        tx = tontine.initiate_contribution(
            db, contribution=contribution, payer=payeur, reseau=reseau
        )
        tontine.confirm_contribution(db, tx, success=True)

    assert cycle.status == CycleStatus.FUNDED
    pot = ledger.get_or_create_account(
        db, ledger.AccountKind.GROUP_POT, group.id, "pot", group.currency
    )
    assert ledger.balance_minor(db, pot.id) == 5000 * len(membres)


def test_paiement_refuse_remet_la_cotisation_a_payer(db: Session, groupe):
    group, membres = groupe
    cycles = tontine.activate_group(db, group)
    contribution = cycles[0].contributions[0]
    membership = db.get(Membership, contribution.membership_id)
    payeur = next(m for m in membres if m.id == membership.user_id)

    tx = tontine.initiate_contribution(
        db, contribution=contribution, payer=payeur, reseau=_reseau(FakeMoMoClient())
    )
    tontine.confirm_contribution(db, tx, success=False)

    assert contribution.status == ContributionStatus.DUE
    assert tx.status == TransactionStatus.FAILED


def test_versement_refuse_si_le_cycle_nest_pas_finance(
    db: Session, groupe, momo: FakeMoMoClient, reseau):
    group, _ = groupe
    cycles = tontine.activate_group(db, group)
    with pytest.raises(tontine.TontineError):
        tontine.pay_out_cycle(db, cycles[0], reseau)


def test_versement_vide_la_cagnotte(db: Session, groupe, momo: FakeMoMoClient, reseau):
    group, membres = groupe
    cycles = tontine.activate_group(db, group)
    cycle = cycles[0]

    for contribution in cycle.contributions:
        membership = db.get(Membership, contribution.membership_id)
        payeur = next(m for m in membres if m.id == membership.user_id)
        tx = tontine.initiate_contribution(
            db, contribution=contribution, payer=payeur, reseau=reseau
        )
        tontine.confirm_contribution(db, tx, success=True)

    payout = tontine.pay_out_cycle(db, cycle, reseau)
    tontine.confirm_payout(db, payout, cycle, success=True)

    assert cycle.status == CycleStatus.PAID_OUT
    pot = ledger.get_or_create_account(
        db, ledger.AccountKind.GROUP_POT, group.id, "pot", group.currency
    )
    assert ledger.balance_minor(db, pot.id) == 0



def _financer(db: Session, groupe, reseau):
    """Mène le premier cycle jusqu'à « financé », prêt à être versé."""
    group, membres = groupe
    cycle = tontine.activate_group(db, group)[0]
    for contribution in cycle.contributions:
        membership = db.get(Membership, contribution.membership_id)
        payeur = next(m for m in membres if m.id == membership.user_id)
        tx = tontine.initiate_contribution(
            db, contribution=contribution, payer=payeur, reseau=reseau
        )
        tontine.confirm_contribution(db, tx, success=True)
    return group, cycle


def _lever(exc: Exception):
    def appel(**_):
        raise exc

    return appel


def test_un_jeton_refuse_clot_lessai_sans_rien_effacer(
    db: Session, groupe, momo: FakeMoMoClient, reseau
):
    # Avant ce correctif, le refus devenait une erreur 500 et l'annulation de
    # la requête effaçait la transaction : aucune trace, aucune raison.
    group, cycle = _financer(db, groupe, reseau)
    momo.transfer = _lever(MoMoError("Authentification disbursement refusée : 401"))

    tx = tontine.pay_out_cycle(db, cycle, reseau)

    assert tx.status == TransactionStatus.FAILED
    assert "401" in tx.failure_reason
    assert cycle.status == CycleStatus.FUNDED
    pot = ledger.get_or_create_account(
        db, ledger.AccountKind.GROUP_POT, group.id, "pot", group.currency
    )
    # Un versement refusé n'a rien retiré de la cagnotte.
    assert ledger.balance_minor(db, pot.id) == 15000


def test_apres_un_refus_lessai_suivant_repart_chez_loperateur(
    db: Session, groupe, momo: FakeMoMoClient, reseau
):
    _, cycle = _financer(db, groupe, reseau)
    original = momo.transfer
    momo.transfer = _lever(MoMoError("refus"))
    premier = tontine.pay_out_cycle(db, cycle, reseau)

    momo.transfer = original
    second = tontine.pay_out_cycle(db, cycle, reseau)

    assert second.id != premier.id
    assert second.status == TransactionStatus.PROCESSING


def test_une_connexion_qui_naboutit_pas_clot_la_cotisation(
    db: Session, groupe, momo: FakeMoMoClient, reseau
):
    group, membres = groupe
    contribution = tontine.activate_group(db, group)[0].contributions[0]
    membership = db.get(Membership, contribution.membership_id)
    payeur = next(m for m in membres if m.id == membership.user_id)
    momo.request_to_pay = _lever(httpx.ConnectError("injoignable"))

    tx = tontine.initiate_contribution(
        db, contribution=contribution, payer=payeur, reseau=reseau
    )

    assert tx.status == TransactionStatus.FAILED
    assert contribution.status == ContributionStatus.FAILED


def test_un_delai_depasse_ne_vaut_pas_refus(
    db: Session, groupe, momo: FakeMoMoClient, reseau
):
    # La demande est partie, la réponse s'est perdue : l'opérateur a peut-être
    # exécuté le versement. Clore l'essai en ouvrirait un second, sous une
    # autre référence — c'est-à-dire un second versement.
    _, cycle = _financer(db, groupe, reseau)
    momo.transfer = _lever(httpx.ReadTimeout("réponse perdue"))

    tx = tontine.pay_out_cycle(db, cycle, reseau)

    assert tx.status == TransactionStatus.PROCESSING
    assert tx.failure_reason is None


def test_apres_un_delai_depasse_le_second_clic_ne_reverse_pas(
    db: Session, groupe, momo: FakeMoMoClient, reseau
):
    # Le cœur du risque : un utilisateur impatient relance le versement.
    _, cycle = _financer(db, groupe, reseau)
    momo.transfer = _lever(httpx.ReadTimeout("réponse perdue"))
    premier = tontine.pay_out_cycle(db, cycle, reseau)

    appels_avant = len(momo.calls)
    second = tontine.pay_out_cycle(db, cycle, reseau)

    assert second.id == premier.id
    assert len(momo.calls) == appels_avant
