"""La configuration de production a ses propres pièges."""

from app.core.config import Settings


def test_les_origines_cors_se_decoupent_sur_la_virgule():
    settings = Settings(cors_origins="https://tontine.fly.dev, http://localhost:5173")
    assert settings.cors_origin_list == ["https://tontine.fly.dev", "http://localhost:5173"]


def test_une_liste_dorigines_vide_ne_produit_pas_de_chaine_vide():
    # Une origine vide dans la liste autoriserait des requêtes inattendues.
    settings = Settings(cors_origins="https://tontine.fly.dev,,  ,")
    assert settings.cors_origin_list == ["https://tontine.fly.dev"]


def test_une_origine_unique_reste_une_liste():
    assert Settings(cors_origins="https://a.dev").cors_origin_list == ["https://a.dev"]


def test_une_origine_sans_schema_est_completee_en_https():
    # Plusieurs plateformes n'exposent que le nom d'hôte.
    settings = Settings(cors_origins="tontine-web.onrender.com")
    assert settings.cors_origin_list == ["https://tontine-web.onrender.com"]


def test_la_barre_finale_est_retiree():
    # Le navigateur compare les origines caractère par caractère.
    settings = Settings(cors_origins="https://tontine.fly.dev/")
    assert settings.cors_origin_list == ["https://tontine.fly.dev"]


def test_le_schema_explicite_est_respecte():
    settings = Settings(cors_origins="http://localhost:5173")
    assert settings.cors_origin_list == ["http://localhost:5173"]
