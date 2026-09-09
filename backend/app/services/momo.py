"""Client MTN Mobile Money (sandbox).

Portail développeur : https://momodeveloper.mtn.com
Deux produits sont utilisés :
  - Collection   : encaisser la cotisation d'un membre (requesttopay)
  - Disbursement : verser la cagnotte au bénéficiaire (transfer)

Le protocole impose un identifiant `X-Reference-Id` fourni par l'appelant. On y
place l'identifiant de notre transaction : c'est ce qui rend l'appel rejouable
sans double débit, y compris après un timeout réseau.
"""

import hashlib
import hmac
import re
import unicodedata
import uuid
from dataclasses import dataclass
from typing import Any, Protocol

import httpx

from app.core.config import settings

# La ponctuation typographique fait rejeter l'appel par MTN. Constaté sur le
# sandbox : « — » et « ° » valent un 400, l'apostrophe courbe et les parenthèses
# un 200 — que le client ne compte pas comme une acceptation, puisqu'un
# versement accepté répond 202. Les lettres accentuées, elles, passent sans
# problème : le filtre ne doit donc pas se réduire à de l'ASCII, sous peine de
# transformer « Sègbé » en « Sgb » sur le relevé du bénéficiaire.
_REMPLACEMENTS = {"—": "-", "–": "-", "‑": "-", "’": " ", "«": " ", "»": " ", "…": " "}
_INDESIRABLES = re.compile(r"[^0-9A-Za-zÀ-ÖØ-öø-ÿ .,-]")


def libelle_operateur(texte: str) -> str:
    """Ramène un libellé à ce que l'opérateur accepte, accents compris."""
    for source, cible in _REMPLACEMENTS.items():
        texte = texte.replace(source, cible)
    texte = unicodedata.normalize("NFC", texte)
    return re.sub(r"\s+", " ", _INDESIRABLES.sub(" ", texte)).strip()[:160]


class MoMoError(Exception):
    pass


@dataclass(frozen=True)
class MoMoResult:
    external_id: str
    accepted: bool
    raw: dict[str, Any]


class MoMoClient(Protocol):
    def request_to_pay(
        self, *, reference: uuid.UUID, amount_minor: int, payer_phone: str, note: str
    ) -> MoMoResult: ...

    def transfer(
        self, *, reference: uuid.UUID, amount_minor: int, payee_phone: str, note: str
    ) -> MoMoResult: ...

    def status(self, *, reference: uuid.UUID, product: str) -> dict[str, Any]: ...


class MtnMoMoClient:
    """Implémentation réelle, à brancher sur le sandbox MTN."""

    def __init__(self, client: httpx.Client | None = None) -> None:
        self._client = client or httpx.Client(base_url=settings.momo_base_url, timeout=15.0)
        self._tokens: dict[str, str] = {}

    def _token(self, product: str) -> str:
        if product in self._tokens:
            return self._tokens[product]

        response = self._client.post(
            f"/{product}/token/",
            auth=(settings.momo_api_user, settings.momo_api_key),
            headers={"Ocp-Apim-Subscription-Key": settings.momo_key_for(product)},
        )
        if response.status_code >= 400:
            raise MoMoError(f"Authentification {product} refusée : {response.text}")

        token = str(response.json()["access_token"])
        self._tokens[product] = token
        return token

    @property
    def _devise(self) -> str:
        """La devise à déclarer à l'opérateur.

        Le sandbox MTN ne connaît que l'EUR : un transfert en XOF y est refusé
        par un 500 `INVALID_CURRENCY`. La production, elle, attend bien la
        devise locale.

        La substitution s'arrête à la charge utile envoyée à MTN. Le grand
        livre reste en XOF, montants en unité mineure : une bizarrerie
        d'environnement de test n'a pas à se lire dans la comptabilité.
        """
        if settings.momo_target_environment == "sandbox":
            return "EUR"
        return settings.currency

    def _headers(
        self, product: str, reference: uuid.UUID, *, rappel: bool = False
    ) -> dict[str, str]:
        entetes = {
            "Authorization": f"Bearer {self._token(product)}",
            "X-Reference-Id": str(reference),
            "X-Target-Environment": settings.momo_target_environment,
            "Ocp-Apim-Subscription-Key": settings.momo_key_for(product),
            "Content-Type": "application/json",
        }
        # Le provisionnement n'enregistre qu'un hôte, sans chemin : MTN ne
        # rappellerait donc que la racine du domaine. L'URL complète se donne
        # ici, appel par appel. Sans elle, la demande part et rien ne revient —
        # constaté sur le sandbox, où le webhook n'était jamais atteint.
        if rappel and settings.momo_callback_url:
            entetes["X-Callback-Url"] = settings.momo_callback_url
        return entetes

    def request_to_pay(
        self, *, reference: uuid.UUID, amount_minor: int, payer_phone: str, note: str
    ) -> MoMoResult:
        payload = {
            "amount": str(amount_minor),
            "currency": self._devise,
            "externalId": str(reference),
            "payer": {"partyIdType": "MSISDN", "partyId": payer_phone.lstrip("+")},
            "payerMessage": libelle_operateur(note),
            "payeeNote": libelle_operateur(note),
        }
        response = self._client.post(
            "/collection/v1_0/requesttopay",
            json=payload,
            headers=self._headers("collection", reference, rappel=True),
        )
        # 202 : la demande est acceptée, le résultat arrivera par callback.
        return MoMoResult(
            external_id=str(reference),
            accepted=response.status_code == 202,
            raw={"status_code": response.status_code, "body": response.text},
        )

    def transfer(
        self, *, reference: uuid.UUID, amount_minor: int, payee_phone: str, note: str
    ) -> MoMoResult:
        payload = {
            "amount": str(amount_minor),
            "currency": self._devise,
            "externalId": str(reference),
            "payee": {"partyIdType": "MSISDN", "partyId": payee_phone.lstrip("+")},
            "payerMessage": libelle_operateur(note),
            "payeeNote": libelle_operateur(note),
        }
        response = self._client.post(
            "/disbursement/v1_0/transfer",
            json=payload,
            headers=self._headers("disbursement", reference, rappel=True),
        )
        return MoMoResult(
            external_id=str(reference),
            accepted=response.status_code == 202,
            raw={"status_code": response.status_code, "body": response.text},
        )

    def status(self, *, reference: uuid.UUID, product: str) -> dict[str, Any]:
        path = "requesttopay" if product == "collection" else "transfer"
        response = self._client.get(
            f"/{product}/v1_0/{path}/{reference}",
            headers=self._headers(product, reference),
        )
        return dict(response.json())


class FakeMoMoClient:
    """Double de test : accepte tout et mémorise les appels.

    Sert aussi en développement local, pour travailler sans clé sandbox.
    """

    def __init__(self, *, accept: bool = True) -> None:
        self.accept = accept
        self.calls: list[dict[str, Any]] = []

    def request_to_pay(
        self, *, reference: uuid.UUID, amount_minor: int, payer_phone: str, note: str
    ) -> MoMoResult:
        self.calls.append(
            {
                "kind": "collect",
                "reference": reference,
                "amount": amount_minor,
                "phone": payer_phone,
            }
        )
        return MoMoResult(external_id=str(reference), accepted=self.accept, raw={})

    def transfer(
        self, *, reference: uuid.UUID, amount_minor: int, payee_phone: str, note: str
    ) -> MoMoResult:
        self.calls.append(
            {
                "kind": "transfer",
                "reference": reference,
                "amount": amount_minor,
                "phone": payee_phone,
            }
        )
        return MoMoResult(external_id=str(reference), accepted=self.accept, raw={})

    def status(self, *, reference: uuid.UUID, product: str) -> dict[str, Any]:
        return {"status": "SUCCESSFUL" if self.accept else "FAILED"}


class ProductRoutedClient:
    """Un client par produit, choisi à l'appel.

    Un opérateur peut être joignable sur un produit et pas sur l'autre : le
    sandbox MTN plafonne les abonnements à Collection alors que Disbursement
    s'y souscrit normalement. Router par produit permet au versement de partir
    sur l'opérateur réel pendant que l'encaissement reste sur le double.

    C'est une situation d'exploitation ordinaire, pas un montage de fortune :
    un opérateur en panne partielle se traite exactement de la même façon.
    """

    def __init__(self, *, collection: MoMoClient, disbursement: MoMoClient) -> None:
        self.collection = collection
        self.disbursement = disbursement

    def _pour(self, product: str) -> MoMoClient:
        return self.collection if product == "collection" else self.disbursement

    def request_to_pay(
        self, *, reference: uuid.UUID, amount_minor: int, payer_phone: str, note: str
    ) -> MoMoResult:
        return self.collection.request_to_pay(
            reference=reference, amount_minor=amount_minor, payer_phone=payer_phone, note=note
        )

    def transfer(
        self, *, reference: uuid.UUID, amount_minor: int, payee_phone: str, note: str
    ) -> MoMoResult:
        return self.disbursement.transfer(
            reference=reference, amount_minor=amount_minor, payee_phone=payee_phone, note=note
        )

    def status(self, *, reference: uuid.UUID, product: str) -> dict[str, Any]:
        return self._pour(product).status(reference=reference, product=product)


def verdict(client: MoMoClient, *, reference: uuid.UUID, product: str) -> bool | None:
    """Demande à l'opérateur ce qu'il est advenu d'une référence.

    Renvoie `None` quand il n'y a rien à trancher : opérateur injoignable, ou
    transaction encore en cours chez lui. L'appelant doit alors ne rien changer
    et laisser l'opérateur rappeler.
    """
    try:
        etat = client.status(reference=reference, product=product)
    except (MoMoError, httpx.HTTPError):
        return None

    statut = str(etat.get("status", "")).upper()
    if statut in {"SUCCESSFUL", "SUCCESS"}:
        return True
    if statut in {"FAILED", "REJECTED"}:
        return False
    return None


def verify_signature(raw_body: bytes, received_signature: str) -> bool:
    """Vérifie la signature HMAC d'un callback, en temps constant."""
    expected = hmac.new(
        settings.momo_callback_secret.encode(), raw_body, hashlib.sha256
    ).hexdigest()
    return hmac.compare_digest(expected, received_signature)
