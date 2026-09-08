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
import uuid
from dataclasses import dataclass
from typing import Any, Protocol

import httpx

from app.core.config import settings


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
            headers={"Ocp-Apim-Subscription-Key": settings.momo_subscription_key},
        )
        if response.status_code >= 400:
            raise MoMoError(f"Authentification {product} refusée : {response.text}")

        token = str(response.json()["access_token"])
        self._tokens[product] = token
        return token

    def _headers(self, product: str, reference: uuid.UUID) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self._token(product)}",
            "X-Reference-Id": str(reference),
            "X-Target-Environment": settings.momo_target_environment,
            "Ocp-Apim-Subscription-Key": settings.momo_subscription_key,
            "Content-Type": "application/json",
        }

    def request_to_pay(
        self, *, reference: uuid.UUID, amount_minor: int, payer_phone: str, note: str
    ) -> MoMoResult:
        payload = {
            "amount": str(amount_minor),
            "currency": settings.currency,
            "externalId": str(reference),
            "payer": {"partyIdType": "MSISDN", "partyId": payer_phone.lstrip("+")},
            "payerMessage": note[:160],
            "payeeNote": note[:160],
        }
        response = self._client.post(
            "/collection/v1_0/requesttopay",
            json=payload,
            headers=self._headers("collection", reference),
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
            "currency": settings.currency,
            "externalId": str(reference),
            "payee": {"partyIdType": "MSISDN", "partyId": payee_phone.lstrip("+")},
            "payerMessage": note[:160],
            "payeeNote": note[:160],
        }
        response = self._client.post(
            "/disbursement/v1_0/transfer",
            json=payload,
            headers=self._headers("disbursement", reference),
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


def verify_signature(raw_body: bytes, received_signature: str) -> bool:
    """Vérifie la signature HMAC d'un callback, en temps constant."""
    expected = hmac.new(
        settings.momo_callback_secret.encode(), raw_body, hashlib.sha256
    ).hexdigest()
    return hmac.compare_digest(expected, received_signature)
