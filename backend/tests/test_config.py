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


def test_lurl_de_base_dun_hebergeur_manage_recoit_le_pilote_psycopg():
    # Neon, Render et consorts délivrent « postgresql:// » : sans conversion,
    # SQLAlchemy y lirait psycopg2, que le projet n'installe pas.
    settings = Settings(database_url="postgresql://u:p@ep-x.neon.tech/db?sslmode=require")
    assert settings.database_url.startswith("postgresql+psycopg://")
    assert settings.database_url.endswith("?sslmode=require")


def test_le_schema_postgres_court_est_aussi_converti():
    settings = Settings(database_url="postgres://u:p@hote/db")
    assert settings.database_url == "postgresql+psycopg://u:p@hote/db"


def test_un_pilote_deja_explicite_nest_pas_touche():
    url = "postgresql+psycopg://u:p@hote/db"
    assert Settings(database_url=url).database_url == url


def test_chaque_produit_momo_recoit_sa_propre_cle():
    # MTN délivre une clé par produit : les confondre vaut un 401.
    settings = Settings(momo_collection_key="cle-collection", momo_disbursement_key="cle-verse")
    assert settings.momo_key_for("collection") == "cle-collection"
    assert settings.momo_key_for("disbursement") == "cle-verse"


def test_la_cle_generique_sert_de_repli():
    # Un déploiement qui n'utilise qu'un produit n'a pas à renseigner les deux.
    settings = Settings(momo_subscription_key="cle-unique")
    assert settings.momo_key_for("collection") == "cle-unique"
    assert settings.momo_key_for("disbursement") == "cle-unique"


def test_la_cle_specifique_lemporte_sur_le_repli():
    settings = Settings(momo_subscription_key="repli", momo_disbursement_key="specifique")
    assert settings.momo_key_for("disbursement") == "specifique"
    assert settings.momo_key_for("collection") == "repli"


def test_sans_aucune_cle_le_produit_na_pas_de_cle():
    assert Settings().momo_key_for("collection") == ""
