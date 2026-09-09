from datetime import date

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
from app.services.momo import FakeMoMoClient
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
