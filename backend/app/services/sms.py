"""L'envoi d'un SMS, et le double qui en tient lieu.

Même dispositif que pour Mobile Money : un protocole, un client réel, un
double qui accepte tout. Sans identifiants configurés, c'est le double qui
tourne — le développement local et la démonstration n'exigent pas de compte
chez un opérateur, et rien ne part chez personne.

**Ce qui est écrit ici d'après la documentation publique de Twilio n'a jamais
été exercé contre le vrai service** : je n'ai pas de compte. L'API est stable
et documentée, la requête est conforme à ce qu'elle décrit, et le client est
testé contre un transport simulé — mais tant qu'un vrai envoi n'a pas abouti,
c'est du code vraisemblable, pas du code éprouvé. La couture est ici : un
autre fournisseur s'enregistre en implémentant `SmsClient`, et rien d'autre ne
bouge.
"""

from typing import Protocol

import httpx

from app.core.config import settings

PROVIDER_DOUBLE = "fake"
PROVIDER_TWILIO = "twilio"


class SmsError(RuntimeError):
    """L'envoi n'a pas abouti. Le message reste à retenter."""


class SmsClient(Protocol):
    def provider(self) -> str: ...

    def envoyer(self, *, destinataire: str, texte: str) -> str:
        """Envoie le message et renvoie la référence donnée par l'opérateur.

        Lève `SmsError` si l'envoi n'aboutit pas.
        """
        ...


class FakeSmsClient:
    """Double : accepte tout et mémorise les envois.

    Il ne prétend pas avoir envoyé quoi que ce soit — la notification qui le
    consigne porte `provider = "fake"`, ce qui dit en clair que rien n'est
    parti.
    """

    def __init__(self) -> None:
        self.envois: list[tuple[str, str]] = []

    def provider(self) -> str:
        return PROVIDER_DOUBLE

    def envoyer(self, *, destinataire: str, texte: str) -> str:
        self.envois.append((destinataire, texte))
        return f"fake-{len(self.envois)}"


class TwilioSmsClient:
    """Client Twilio, écrit d'après l'API publique — voir l'entête du module.

    Un seul appel : `POST /2010-04-01/Accounts/{sid}/Messages.json`, en
    formulaire, authentifié en Basic avec le SID du compte et son jeton.
    """

    def __init__(self, client: httpx.Client | None = None) -> None:
        self._client = client or httpx.Client(
            base_url="https://api.twilio.com", timeout=15.0
        )

    def provider(self) -> str:
        return PROVIDER_TWILIO

    def envoyer(self, *, destinataire: str, texte: str) -> str:
        try:
            reponse = self._client.post(
                f"/2010-04-01/Accounts/{settings.twilio_account_sid}/Messages.json",
                data={
                    "From": settings.twilio_from,
                    "To": destinataire,
                    "Body": texte,
                },
                auth=(settings.twilio_account_sid, settings.twilio_auth_token),
            )
        except httpx.HTTPError as exc:
            raise SmsError(f"Twilio injoignable : {exc}") from exc

        if reponse.status_code >= 400:
            # Le corps porte le motif ; il est court et sans secret.
            raise SmsError(f"Twilio a refusé ({reponse.status_code}) : {reponse.text[:200]}")

        identifiant = reponse.json().get("sid")
        if not identifiant:
            raise SmsError("Twilio n'a pas renvoyé d'identifiant de message.")
        return str(identifiant)


def client_sms() -> SmsClient:
    """Le client réel si les identifiants sont là, le double sinon.

    Comme pour Mobile Money : une clé oubliée ne fait pas échouer l'envoi, elle
    le fait partir chez le double — et `provider` le dit.
    """
    if settings.twilio_account_sid and settings.twilio_auth_token and settings.twilio_from:
        return TwilioSmsClient()
    return FakeSmsClient()
