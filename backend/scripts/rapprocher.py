#!/usr/bin/env python
"""Rapproche le grand livre du relevé de l'opérateur.

C'est la tâche quotidienne. Elle rattrape les callbacks perdus en appliquant le
verdict de l'opérateur, et signale — sans jamais les corriger — les succès que
l'opérateur dément.

    python scripts/rapprocher.py            # rattrape et signale
    python scripts/rapprocher.py --constat  # signale seulement, ne touche à rien
"""

import argparse
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.api.deps import get_momo_client  # noqa: E402
from app.db.session import SessionLocal  # noqa: E402
from app.models.enums import DivergenceKind  # noqa: E402
from app.services import rapprochement  # noqa: E402

LIBELLES = {
    DivergenceKind.UNCONFIRMED: "verdict rattrapé",
    DivergenceKind.DISPUTED_SUCCESS: "SUCCÈS DÉMENTI",
    DivergenceKind.UNKNOWN_AT_OPERATOR: "INCONNUE DE L'OPÉRATEUR",
    DivergenceKind.OPERATOR_SILENT: "opérateur sans verdict",
}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--constat",
        action="store_true",
        help="ne rien appliquer, se contenter de journaliser les écarts",
    )
    args = parser.parse_args()

    with SessionLocal() as db:
        run = rapprochement.rapprocher(db, get_momo_client(), appliquer=not args.constat)
        ecarts = list(run.divergences)

    print(f"Rapprochement {run.id}")
    print(f"  transactions examinées  {run.examined}")
    print(f"  écarts constatés        {len(ecarts)}")
    print(f"  écarts résolus          {sum(1 for e in ecarts if e.resolved)}")

    graves = [
        e
        for e in ecarts
        if e.kind
        in (DivergenceKind.DISPUTED_SUCCESS, DivergenceKind.UNKNOWN_AT_OPERATOR)
    ]
    if ecarts:
        print()
        for ecart in ecarts:
            marque = "!" if ecart in graves else " "
            print(
                f" {marque} {LIBELLES[ecart.kind]:24} "
                f"local={ecart.local_status:10} opérateur={ecart.operator_status or '—'}"
            )

    # Un succès démenti demande une décision humaine : le code de sortie le dit,
    # pour qu'une tâche planifiée puisse alerter.
    return 2 if graves else 0


if __name__ == "__main__":
    raise SystemExit(main())
