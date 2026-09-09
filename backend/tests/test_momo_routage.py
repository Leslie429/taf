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
