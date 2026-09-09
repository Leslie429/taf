"""Le choix de l'opérateur, numéro par numéro.

Une tontine béninoise réunit des membres chez plusieurs opérateurs. Le
versement doit partir chez celui du bénéficiaire, qui n'est pas forcément celui
des cotisants.
"""

from app.services.momo import FakeMoMoClient
from app.services.operateurs import Operateurs, analyser_prefixes, normaliser


def _reseau(prefixes: dict[str, tuple[str, ...]], defaut: str = "mtn_momo") -> Operateurs:
    return Operateurs(
        clients={"mtn_momo": FakeMoMoClient(), "moov": FakeMoMoClient()},
        prefixes=prefixes,
        defaut=defaut,
    )


def test_la_declaration_se_lit_en_table_de_prefixes():
    assert analyser_prefixes("mtn_momo:22951,22961;moov:22994") == {
        "mtn_momo": ("22951", "22961"),
        "moov": ("22994",),
    }


def test_le_plus_a_signe_est_ignore_dans_les_prefixes():
    assert analyser_prefixes("moov:+22994") == {"moov": ("22994",)}


def test_une_declaration_illisible_est_ignoree():
    # Un réglage mal saisi ne doit pas empêcher l'application de démarrer.
    assert analyser_prefixes("nimportequoi") == {}
    assert analyser_prefixes("") == {}
    assert analyser_prefixes("moov:;mtn_momo:22951") == {"mtn_momo": ("22951",)}


def test_un_numero_se_ramene_a_ses_chiffres():
    assert normaliser("+229 01 69 19 50") == "22901691950"


def test_le_numero_designe_son_operateur():
    reseau = _reseau({"mtn_momo": ("22951",), "moov": ("22994",)})
    assert reseau.code_pour_numero("+22994000001") == "moov"
    assert reseau.code_pour_numero("+22951000001") == "mtn_momo"


def test_le_prefixe_le_plus_long_lemporte():
    # Les plages se chevauchent en longueur : « 22961 » doit primer sur « 2296 ».
    reseau = _reseau({"mtn_momo": ("2296",), "moov": ("22961",)})
    assert reseau.code_pour_numero("+22961000001") == "moov"
    assert reseau.code_pour_numero("+22962000001") == "mtn_momo"


def test_un_numero_inconnu_retombe_sur_le_defaut():
    reseau = _reseau({"moov": ("22994",)}, defaut="mtn_momo")
    assert reseau.code_pour_numero("+33612345678") == "mtn_momo"


def test_sans_table_tout_part_chez_le_defaut():
    # C'est l'état d'un déploiement qui n'a pas encore réglé ses plages.
    reseau = _reseau({}, defaut="mtn_momo")
    assert reseau.code_pour_numero("+22994000001") == "mtn_momo"


def test_le_client_suit_loperateur_resolu():
    reseau = _reseau({"moov": ("22994",)})
    assert reseau.pour_numero("+22994000001") is reseau.clients["moov"]
    assert reseau.pour_numero("+22951000001") is reseau.clients["mtn_momo"]


def test_le_rapprochement_retrouve_le_client_par_son_code():
    # Le rapprochement part d'une transaction, sans plus disposer du numéro.
    reseau = _reseau({})
    assert reseau.pour_code("moov") is reseau.clients["moov"]
    assert reseau.pour_code("inexistant") is None
