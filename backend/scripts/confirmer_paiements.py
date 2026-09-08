#!/usr/bin/env python
"""Joue le rôle de l'opérateur en développement local.

Sans clé sandbox MTN, l'API bascule sur un client simulé : une demande de
paiement part bien, mais aucun callback ne vient jamais la confirmer — l'écran
d'attente tournerait indéfiniment.

Ce script envoie les callbacks manquants, signés comme le ferait l'opérateur,
pour toutes les transactions restées « en cours ».

    python scripts/confirmer_paiements.py           # confirme
    python scripts/confirmer_paiements.py --echec   # simule un refus
"""

import argparse
import hashlib
import hmac
import json
import os
import sys

import httpx
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.core.config import settings  # noqa: E402
from app.models.enums import TransactionStatus  # noqa: E402
from app.models.ledger import Transaction  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--echec", action="store_true", help="simuler un refus de l'opérateur")
    parser.add_argument("--api", default="http://127.0.0.1:8000", help="racine de l'API")
    args = parser.parse_args()

    engine = create_engine(settings.database_url, future=True)
    with Session(engine) as db:
        en_cours = list(
            db.execute(
                select(Transaction).where(Transaction.status == TransactionStatus.PROCESSING)
            ).scalars().all()
        )

    if not en_cours:
        print("Aucune transaction en attente.")
        return 0

    statut = "FAILED" if args.echec else "SUCCESSFUL"
    client = httpx.Client(timeout=15)

    for transaction in en_cours:
        body = json.dumps({"externalId": str(transaction.id), "status": statut})
        signature = hmac.new(
            settings.momo_callback_secret.encode(), body.encode(), hashlib.sha256
        ).hexdigest()
        response = client.post(
            f"{args.api}/api/v1/webhooks/momo",
            content=body,
            headers={"X-Callback-Signature": signature, "Content-Type": "application/json"},
        )
        verdict = response.json().get("status", response.text)
        print(f"{transaction.reference}  {transaction.amount_minor} F  →  {statut} ({verdict})")

    print(f"\n{len(en_cours)} transaction(s) traitée(s).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
