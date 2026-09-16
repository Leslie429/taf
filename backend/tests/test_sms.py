"""Le canal d'envoi des SMS.

Le client Twilio est écrit d'après l'API publique et n'a jamais été exercé
contre le vrai service — voir l'entête de `app/services/sms.py`. Ces tests le
confrontent à un transport simulé : ils vérifient la forme de la requête et la
façon dont les refus sont traités, pas que Twilio l'accepterait.
"""

import httpx
import pytest

from app.services.sms import (
    PROVIDER_DOUBLE,
    PROVIDER_TWILIO,
    FakeSmsClient,
    SmsError,
    TwilioSmsClient,
    client_sms,
)


def _transport(gestionnaire) -> httpx.Client:
    return httpx.Client(
        base_url="https://api.twilio.com",
        transport=httpx.MockTransport(gestionnaire),
    )


class TestLeDouble:
    def test_il_accepte_tout_et_se_nomme(self):
        canal = FakeSmsClient()
        reference = canal.envoyer(destinataire="+22997000000", texte="bonjour")

        assert canal.provider() == PROVIDER_DOUBLE
        assert canal.envois == [("+22997000000", "bonjour")]
        assert reference.startswith("fake-")

    def test_sans_identifiants_cest_le_double_qui_tourne(self, monkeypatch):
        # Une clé oubliée ne doit pas faire échouer l'envoi : elle le fait
        # partir chez le double, et `provider` le dit.
        monkeypatch.setattr("app.core.config.settings.twilio_account_sid", "")
        assert client_sms().provider() == PROVIDER_DOUBLE

    def test_avec_les_trois_identifiants_cest_le_client_reel(self, monkeypatch):
        for reglage, valeur in (
            ("twilio_account_sid", "AC123"),
            ("twilio_auth_token", "secret"),
            ("twilio_from", "+15550000000"),
        ):
            monkeypatch.setattr(f"app.core.config.settings.{reglage}", valeur)
        assert client_sms().provider() == PROVIDER_TWILIO

    def test_deux_identifiants_sur_trois_ne_suffisent_pas(self, monkeypatch):
        # Un envoi partirait en 401 : autant rester sur le double.
        monkeypatch.setattr("app.core.config.settings.twilio_account_sid", "AC123")
        monkeypatch.setattr("app.core.config.settings.twilio_auth_token", "secret")
        monkeypatch.setattr("app.core.config.settings.twilio_from", "")
        assert client_sms().provider() == PROVIDER_DOUBLE


class TestLeClientTwilio:
    @pytest.fixture(autouse=True)
    def identifiants(self, monkeypatch):
        monkeypatch.setattr("app.core.config.settings.twilio_account_sid", "AC123")
        monkeypatch.setattr("app.core.config.settings.twilio_auth_token", "secret")
        monkeypatch.setattr("app.core.config.settings.twilio_from", "+15550000000")

    def test_la_requete_porte_le_message_et_lauthentification(self):
        vues: list[httpx.Request] = []

        def gestionnaire(requete: httpx.Request) -> httpx.Response:
            vues.append(requete)
            return httpx.Response(201, json={"sid": "SM999", "status": "queued"})

        reference = TwilioSmsClient(_transport(gestionnaire)).envoyer(
            destinataire="+22997000000", texte="Votre cotisation est en retard."
        )

        assert reference == "SM999"
        requete = vues[0]
        assert requete.url.path == "/2010-04-01/Accounts/AC123/Messages.json"
        assert b"To=%2B22997000000" in requete.content
        assert b"From=%2B15550000000" in requete.content
        assert requete.headers["authorization"].startswith("Basic ")

    def test_un_refus_de_loperateur_leve_avec_son_motif(self):
        def gestionnaire(_: httpx.Request) -> httpx.Response:
            return httpx.Response(400, json={"message": "Numéro invalide", "code": 21211})

        with pytest.raises(SmsError, match="400"):
            TwilioSmsClient(_transport(gestionnaire)).envoyer(
                destinataire="pas-un-numero", texte="x"
            )

    def test_un_operateur_injoignable_leve_aussi(self):
        def gestionnaire(_: httpx.Request) -> httpx.Response:
            raise httpx.ConnectError("réseau coupé")

        with pytest.raises(SmsError, match="injoignable"):
            TwilioSmsClient(_transport(gestionnaire)).envoyer(
                destinataire="+22997000000", texte="x"
            )

    def test_une_reponse_sans_identifiant_nest_pas_un_succes(self):
        # Un 200 sans `sid` ne prouve rien : on ne saurait pas quoi retenir.
        def gestionnaire(_: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json={"status": "queued"})

        with pytest.raises(SmsError, match="identifiant"):
            TwilioSmsClient(_transport(gestionnaire)).envoyer(
                destinataire="+22997000000", texte="x"
            )
