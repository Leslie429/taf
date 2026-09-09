#!/usr/bin/env python
"""Donne ou retire l'appartenance à l'équipe de la plateforme.

`is_staff` ouvre l'écran de rapprochement, qui expose l'état de toutes les
tontines — à ne pas confondre avec `Membership.is_admin`, qui n'administre
qu'un groupe.

Il n'existe volontairement pas de route pour ça : une élévation de privilège
qui s'obtient par un appel HTTP est une élévation de privilège de trop.

    python scripts/promouvoir_equipe.py +22901691004
    python scripts/promouvoir_equipe.py +22901691004 --retirer
"""

import argparse
import os
import sys

from sqlalchemy import select

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.db.session import SessionLocal  # noqa: E402
from app.models.user import User  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("telephone", help="numéro du compte, au format international")
    parser.add_argument("--retirer", action="store_true", help="retirer l'appartenance")
    args = parser.parse_args()

    with SessionLocal() as db:
        utilisateur = db.execute(
            select(User).where(User.phone == args.telephone)
        ).scalar_one_or_none()
        if utilisateur is None:
            print(f"Aucun compte pour {args.telephone}.", file=sys.stderr)
            return 1

        utilisateur.is_staff = not args.retirer
        db.commit()
        etat = "membre de l'équipe" if utilisateur.is_staff else "simple membre"
        print(f"{utilisateur.full_name} ({utilisateur.phone}) : {etat}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
