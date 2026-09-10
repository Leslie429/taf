"""Le client Mobile Money se choisit produit par produit.

Un opérateur peut être joignable sur un produit et pas sur l'autre : le sandbox
MTN plafonne les abonnements à Collection alors que Disbursement s'y souscrit
normalement. L'encaissement doit alors continuer sur le double pendant que le
versement part chez l'opérateur.
"""

import uuid

import pytest

from app.api import deps
from app.core.config import Settings
from app.services.momo import (
    FakeMoMoClient,
    MtnMoMoClient,
    ProductRoutedClient,
    libelle_operateur,
)


@pytest.fixture
def cles(monkeypatch):
    """Fixe les clés d'abonnement vues par la sélection du client."""

    def appliquer(collection: str = "", disbursement: str = "") -> None:
        monkeypatch.setattr(
            deps,
            "settings",
            Settings(momo_collection_key=collection, momo_disbursement_key=disbursement),
        )

    return appliquer


def test_sans_aucune_cle_tout_passe_sur_le_double(cles):
    # Le développement local ne doit pas dépendre d'un compte MTN.
    cles()
    assert isinstance(deps.get_momo_client(), FakeMoMoClient)


def test_avec_les_deux_cles_tout_part_chez_loperateur(cles):
    cles(collection="c", disbursement="d")
    assert isinstance(deps.get_momo_client(), MtnMoMoClient)


def test_une_seule_cle_donne_un_client_route(cles):
    # C'est le cas réel : Disbursement souscrit, Collection plafonné.
    cles(disbursement="d")
    client = deps.get_momo_client()
    assert isinstance(client, ProductRoutedClient)
    assert isinstance(client.collection, FakeMoMoClient)
    assert isinstance(client.disbursement, MtnMoMoClient)


def test_le_client_route_envoie_lencaissement_au_double():
    collection, disbursement = FakeMoMoClient(), FakeMoMoClient()
    client = ProductRoutedClient(collection=collection, disbursement=disbursement)

    client.request_to_pay(
        reference=uuid.uuid4(), amount_minor=5000, payer_phone="+22901691001", note="cotisation"
    )

    assert [appel["kind"] for appel in collection.calls] == ["collect"]
    assert disbursement.calls == []


def test_le_client_route_envoie_le_versement_a_lautre():
    collection, disbursement = FakeMoMoClient(), FakeMoMoClient()
    client = ProductRoutedClient(collection=collection, disbursement=disbursement)

    client.transfer(
        reference=uuid.uuid4(), amount_minor=25000, payee_phone="+22901691004", note="versement"
    )

    assert [appel["kind"] for appel in disbursement.calls] == ["transfer"]
    assert collection.calls == []


def test_le_statut_suit_le_produit_demande():
    # Interroger le mauvais produit renverrait un verdict qui n'existe pas.
    collection = FakeMoMoClient(accept=True)
    disbursement = FakeMoMoClient(accept=False)
    client = ProductRoutedClient(collection=collection, disbursement=disbursement)

    reference = uuid.uuid4()
    assert client.status(reference=reference, product="collection")["status"] == "SUCCESSFUL"
    assert client.status(reference=reference, product="disbursement")["status"] == "FAILED"


def test_le_sandbox_recoit_des_euros(monkeypatch):
    # Le sandbox MTN refuse le XOF par un 500 INVALID_CURRENCY.
    monkeypatch.setattr(
        "app.services.momo.settings", Settings(momo_target_environment="sandbox", currency="XOF")
    )
    assert MtnMoMoClient()._devise == "EUR"


def test_la_production_recoit_la_devise_locale(monkeypatch):
    monkeypatch.setattr(
        "app.services.momo.settings", Settings(momo_target_environment="mtnbenin", currency="XOF")
    )
    assert MtnMoMoClient()._devise == "XOF"


@pytest.mark.parametrize(
    "brut, attendu",
    [
        # Constaté sur le sandbox MTN : ces caractères font échouer l'appel.
        ("Versement — cycle 3", "Versement - cycle 3"),
        ("Groupe n°1", "Groupe n 1"),
        ("Ecole (Benin)", "Ecole Benin"),
        ("L’épargne d'Aïcha", "L épargne d Aïcha"),
        ("Cotisation « mensuelle »", "Cotisation mensuelle"),
        ("Tour 3/5 — 25 000 F", "Tour 3 5 - 25 000 F"),
        # Les lettres accentuées passent : les retirer abîmerait les noms
        # béninois sur le relevé du bénéficiaire.
        ("Sègbé Adjovi", "Sègbé Adjovi"),
        ("Tontine café", "Tontine café"),
    ],
)
def test_le_libelle_est_ramene_a_ce_que_loperateur_accepte(brut, attendu):
    assert libelle_operateur(brut) == attendu


def test_le_libelle_est_tronque_a_cent_soixante():
    assert len(libelle_operateur("a" * 300)) == 160


def test_lurl_de_rappel_accompagne_les_appels_de_paiement(monkeypatch):
    # MTN n'enregistre qu'un hôte au provisionnement : sans cette URL complète,
    # le callback n'atteint jamais la route et le paiement reste en cours.
    monkeypatch.setattr(
        "app.services.momo.settings",
        Settings(momo_callback_url="https://api.test/api/v1/webhooks/momo"),
    )
    client = MtnMoMoClient()
    monkeypatch.setattr(client, "_token", lambda produit: "jeton")

    entetes = client._headers("disbursement", uuid.uuid4(), rappel=True)
    assert entetes["X-Callback-Url"] == "https://api.test/api/v1/webhooks/momo"


def test_la_consultation_de_statut_ne_demande_pas_de_rappel(monkeypatch):
    monkeypatch.setattr(
        "app.services.momo.settings",
        Settings(momo_callback_url="https://api.test/api/v1/webhooks/momo"),
    )
    client = MtnMoMoClient()
    monkeypatch.setattr(client, "_token", lambda produit: "jeton")

    assert "X-Callback-Url" not in client._headers("disbursement", uuid.uuid4())


def test_sans_url_configuree_aucun_en_tete_de_rappel(monkeypatch):
    monkeypatch.setattr("app.services.momo.settings", Settings(momo_callback_url=""))
    client = MtnMoMoClient()
    monkeypatch.setattr(client, "_token", lambda produit: "jeton")

    assert "X-Callback-Url" not in client._headers("disbursement", uuid.uuid4(), rappel=True)


def _client_simule(monkeypatch, repondre):
    """Un client MTN réel, branché sur un transport qui simule l'opérateur."""
    import httpx

    monkeypatch.setattr(
        "app.services.momo.settings",
        Settings(momo_disbursement_key="cle", momo_api_user="u", momo_api_key="p"),
    )
    transport = httpx.MockTransport(repondre)
    return MtnMoMoClient(httpx.Client(transport=transport, base_url="https://mtn.test"))


def test_un_delai_depasse_sur_le_jeton_signifie_que_rien_nest_parti(monkeypatch):
    # Constaté sur Render : le jeton a expiré, le virement n'est jamais parti,
    # et l'essai est pourtant resté « en cours » — faute de savoir à quelle
    # phase l'incident avait eu lieu.
    import httpx

    from app.services.momo import MoMoError

    def repondre(requete):
        if requete.url.path.endswith("/token/"):
            raise httpx.ReadTimeout("jeton lent", request=requete)
        return httpx.Response(202)

    client = _client_simule(monkeypatch, repondre)
    with pytest.raises(MoMoError, match="Jeton disbursement indisponible"):
        client.transfer(
            reference=uuid.uuid4(), amount_minor=1000, payee_phone="+22901691004", note="x"
        )


def test_un_delai_depasse_sur_le_virement_reste_ambigu(monkeypatch):
    # Là, l'ordre est parti : l'opérateur l'a peut-être exécuté. L'erreur doit
    # rester une erreur réseau, que l'appelant ne clôt pas.
    import httpx

    def repondre(requete):
        if requete.url.path.endswith("/token/"):
            return httpx.Response(200, json={"access_token": "jeton"})
        raise httpx.ReadTimeout("virement lent", request=requete)

    client = _client_simule(monkeypatch, repondre)
    with pytest.raises(httpx.ReadTimeout):
        client.transfer(
            reference=uuid.uuid4(), amount_minor=1000, payee_phone="+22901691004", note="x"
        )
