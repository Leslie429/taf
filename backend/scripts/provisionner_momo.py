#!/usr/bin/env python
"""Crée un utilisateur d'API sur le sandbox MTN.

La clé d'abonnement ne suffit pas à appeler l'opérateur : il faut un couple
`API User` / `API Key`, obtenu en deux appels. Le premier déclare l'hôte qui
recevra les callbacks — MTN n'y enverra rien s'il ne le connaît pas.

L'identifiant de l'utilisateur est un UUID que l'on choisit soi-même : c'est
l'appelant qui le fournit, comme pour le `X-Reference-Id` des paiements.

La clé d'abonnement est lue dans l'environnement, jamais passée en argument :
un argument de ligne de commande reste dans l'historique du shell et se lit
dans la liste des processus.

    export MOMO_DISBURSEMENT_KEY=...
    python scripts/provisionner_momo.py --produit disbursement \\
        --hote tontine-api.fly.dev
"""

import argparse
import os
import sys
import uuid

import httpx

BASE_URL = "https://sandbox.momodeveloper.mtn.com"
VARIABLES = {
    "collection": ("MOMO_COLLECTION_KEY", "MOMO_SUBSCRIPTION_KEY"),
    "disbursement": ("MOMO_DISBURSEMENT_KEY", "MOMO_SUBSCRIPTION_KEY"),
}


def cle_dabonnement(produit: str) -> str:
    for variable in VARIABLES[produit]:
        valeur = os.environ.get(variable, "").strip()
        if valeur:
            return valeur
    attendues = " ou ".join(VARIABLES[produit])
    raise SystemExit(f"Aucune clé d'abonnement : renseigner {attendues} dans l'environnement.")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--produit", choices=sorted(VARIABLES), required=True)
    parser.add_argument(
        "--hote",
        required=True,
        help="hôte qui recevra les callbacks, sans schéma (ex. tontine-api.fly.dev)",
    )
    parser.add_argument("--base-url", default=BASE_URL)
    args = parser.parse_args()

    if "://" in args.hote:
        raise SystemExit("L'hôte se donne sans schéma : tontine-api.fly.dev, pas https://...")

    cle = cle_dabonnement(args.produit)
    entetes = {"Ocp-Apim-Subscription-Key": cle, "Content-Type": "application/json"}
    identifiant = str(uuid.uuid4())

    with httpx.Client(base_url=args.base_url, timeout=30.0) as client:
        creation = client.post(
            "/v1_0/apiuser",
            headers={**entetes, "X-Reference-Id": identifiant},
            json={"providerCallbackHost": args.hote},
        )
        if creation.status_code != 201:
            print(
                f"Création refusée ({creation.status_code}) : {creation.text}",
                file=sys.stderr,
            )
            return 1

        # MTN ne renvoie la clé qu'une fois : elle n'est pas relisible ensuite.
        obtention = client.post(f"/v1_0/apiuser/{identifiant}/apikey", headers=entetes)
        if obtention.status_code != 201:
            print(
                f"Clé refusée ({obtention.status_code}) : {obtention.text}",
                file=sys.stderr,
            )
            return 1
        cle_api = obtention.json()["apiKey"]

        verification = client.get(f"/v1_0/apiuser/{identifiant}", headers=entetes)

    print(f"Utilisateur d'API créé pour « {args.produit} ».")
    print(f"  hôte de callback déclaré : {verification.json().get('providerCallbackHost', '?')}")
    print()
    print("À poser dans les variables d'environnement de l'hébergeur —")
    print("la clé d'API ne sera plus jamais affichée :")
    print()
    print(f"  MOMO_API_USER = {identifiant}")
    print(f"  MOMO_API_KEY  = {cle_api}")
    print()
    print("Valeurs brutes, sans guillemets : les guillemets sont une syntaxe de")
    print("shell, pas une partie de la valeur.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
