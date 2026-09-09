#!/usr/bin/env python
"""Efface les fenêtres de limitation périmées.

La table `rate_limit_counters` gagne une ligne par seau et par fenêtre. Sous
une attaque par force brute, elle grossit vite et pour rien : passé la fenêtre,
un compteur ne sert plus à rien.

    python scripts/purger_limites.py            # efface au-delà d'un jour
    python scripts/purger_limites.py --jours 7
"""

import argparse
import os
import sys
from datetime import UTC, datetime, timedelta

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.db.session import SessionLocal  # noqa: E402
from app.services import limitation  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--jours", type=int, default=1, help="âge au-delà duquel effacer")
    args = parser.parse_args()

    seuil = datetime.now(UTC) - timedelta(days=args.jours)
    with SessionLocal() as db:
        efface = limitation.purger(db, avant=seuil)

    print(f"{efface} fenêtre(s) effacée(s), antérieures au {seuil:%Y-%m-%d %H:%M} UTC.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
