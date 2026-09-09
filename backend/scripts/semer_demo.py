#!/usr/bin/env python
"""Peuple la base d'une tontine de démonstration déjà entamée.

Un écran vide ne démontre rien : celui qui ouvre la démonstration doit voir une
tontine en cours, avec des tours acquis, un tour en collecte et son propre tour
à venir.

Les données passent par les services métier — jamais par des insertions
directes. Les écritures du grand livre sont donc celles qu'aurait produites une
vraie utilisation, et les soldes se recalculent à partir d'elles.

    python scripts/semer_demo.py                  # sème
    python scripts/semer_demo.py --reinitialiser  # efface puis resème
"""

import argparse
import os
import sys
from calendar import monthrange
from datetime import date, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.core.security import hash_password  # noqa: E402
from app.db.session import SessionLocal  # noqa: E402
from app.models.enums import (  # noqa: E402
    ContributionStatus,
    Frequency,
    GroupStatus,
    MembershipStatus,
)
from app.models.tontine import Contribution, Membership, TontineGroup  # noqa: E402
from app.models.user import User  # noqa: E402
from app.services import tontine  # noqa: E402
from app.services.momo import FakeMoMoClient  # noqa: E402

MOT_DE_PASSE = "demo1234"
COTISATION_MINOR = 25_000
NOM_DU_GROUPE = "Tontine des marchandes de Dantokpa"

# Le compte de démonstration est en quatrième position : son tour n'est pas
# encore venu, ce qui donne à la barre de tours ses trois états à la fois —
# acquis, en collecte, à venir.
POSITION_DEMO = 4

MEMBRES = [
    ("+22901691001", "Aïcha Sossou"),
    ("+22901691002", "Bernadette Aholou"),
    ("+22901691003", "Colette Zinsou"),
    ("+22901691004", "Léslie Tokponto"),  # le compte de démonstration
    ("+22901691005", "Étienne Dossou"),
]


def _mois_avant(reference: date, mois: int) -> date:
    """Recule de `mois` mois en ramenant le jour à la fin de mois si besoin."""
    total = reference.month - 1 - mois
    annee = reference.year + total // 12
    numero = total % 12 + 1
    return date(annee, numero, min(reference.day, monthrange(annee, numero)[1]))


def _effacer(db: Session) -> None:
    """Retire la tontine de démonstration et ses membres, rien d'autre."""
    groupe = db.execute(
        select(TontineGroup).where(TontineGroup.name == NOM_DU_GROUPE)
    ).scalar_one_or_none()
    if groupe is not None:
        # Les cycles et cotisations partent en cascade ; les écritures du grand
        # livre restent, ce qui est le comportement attendu d'une comptabilité.
        db.delete(groupe)
        db.flush()

    for telephone, _ in MEMBRES:
        utilisateur = db.execute(
            select(User).where(User.phone == telephone)
        ).scalar_one_or_none()
        if utilisateur is not None:
            db.delete(utilisateur)
    db.commit()


def _regler(db: Session, contribution: Contribution, momo: FakeMoMoClient) -> None:
    """Encaisse une cotisation de bout en bout, callback opérateur compris."""
    adhesion = db.get(Membership, contribution.membership_id)
    if adhesion is None:
        raise RuntimeError(f"Adhésion introuvable pour la cotisation {contribution.id}.")
    payeur = db.get(User, adhesion.user_id)
    if payeur is None:
        raise RuntimeError(f"Utilisateur introuvable pour l'adhésion {adhesion.id}.")
    transaction = tontine.initiate_contribution(
        db, contribution=contribution, payer=payeur, momo=momo
    )
    tontine.confirm_contribution(db, transaction, success=True)


def semer(db: Session) -> None:
    momo = FakeMoMoClient()

    utilisateurs = []
    for telephone, nom in MEMBRES:
        utilisateur = User(
            phone=telephone,
            full_name=nom,
            hashed_password=hash_password(MOT_DE_PASSE),
        )
        db.add(utilisateur)
        utilisateurs.append(utilisateur)
    db.flush()

    # Le tour en collecte doit tomber dans le futur proche : sinon le cycle
    # bascule en retard et la démonstration s'ouvre sur une alerte.
    depart = _mois_avant(date.today() + timedelta(days=10), 2)

    groupe = TontineGroup(
        name=NOM_DU_GROUPE,
        description="Cinq commerçantes cotisent chaque mois ; la cagnotte tourne.",
        contribution_minor=COTISATION_MINOR,
        currency="XOF",
        frequency=Frequency.MONTHLY,
        start_date=depart,
        status=GroupStatus.DRAFT,
        created_by_id=utilisateurs[0].id,
    )
    db.add(groupe)
    db.flush()

    for rang, utilisateur in enumerate(utilisateurs, start=1):
        db.add(
            Membership(
                group_id=groupe.id,
                user_id=utilisateur.id,
                payout_position=rang,
                is_admin=(rang == 1),
                status=MembershipStatus.ACTIVE,
            )
        )
    db.flush()
    db.refresh(groupe)

    cycles = tontine.activate_group(db, groupe)

    # Les deux premiers tours sont bouclés : tout le monde a payé, la cagnotte
    # est partie chez le bénéficiaire.
    for cycle in cycles[:2]:
        for contribution in cycle.contributions:
            _regler(db, contribution, momo)
        transaction = tontine.pay_out_cycle(db, cycle, momo)
        tontine.confirm_payout(db, transaction, cycle, success=True)

    # Le troisième est en cours : trois membres sur cinq ont réglé.
    for contribution in cycles[2].contributions[:3]:
        _regler(db, contribution, momo)

    db.commit()

    cagnotte = tontine.pot_total_minor(groupe, len(utilisateurs))
    regles = sum(
        1 for c in cycles[2].contributions if c.status == ContributionStatus.PAID
    )
    print(f"Tontine « {groupe.name} » — {len(utilisateurs)} membres")
    print(f"  cotisation      {COTISATION_MINOR:,} F / mois".replace(",", " "))
    print(f"  cagnotte        {cagnotte:,} F par tour".replace(",", " "))
    print(f"  tours versés    2 sur {len(cycles)}")
    print(f"  tour en cours   {regles} cotisations réglées sur {len(utilisateurs)}")
    print()
    print("Compte de démonstration :")
    print(f"  téléphone       {MEMBRES[POSITION_DEMO - 1][0]}")
    print(f"  mot de passe    {MOT_DE_PASSE}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--reinitialiser",
        action="store_true",
        help="effacer la tontine de démonstration existante avant de semer",
    )
    args = parser.parse_args()

    with SessionLocal() as db:
        existant = db.execute(
            select(TontineGroup).where(TontineGroup.name == NOM_DU_GROUPE)
        ).scalar_one_or_none()

        if existant is not None:
            if not args.reinitialiser:
                print(
                    "La tontine de démonstration existe déjà.\n"
                    "Relancer avec --reinitialiser pour l'effacer et la resemer.",
                    file=sys.stderr,
                )
                return 1
            _effacer(db)

        semer(db)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
