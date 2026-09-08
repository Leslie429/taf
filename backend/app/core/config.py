from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Configuration de l'application, lue depuis l'environnement."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_name: str = "Tontine API"
    environment: str = "development"

    # Origines autorisées à appeler l'API, séparées par des virgules.
    # En production, c'est le domaine du front — jamais "*", puisque
    # les requêtes portent des identifiants.
    cors_origins: str = "http://localhost:5173"

    database_url: str = "postgresql+psycopg://tontine:tontine@localhost:5432/tontine"
    redis_url: str = "redis://localhost:6379/0"

    # Auth
    jwt_secret: str = "dev-secret-a-changer-en-production"
    jwt_algorithm: str = "HS256"
    access_token_ttl_minutes: int = 15
    refresh_token_ttl_days: int = 30

    # MTN MoMo sandbox — https://momodeveloper.mtn.com
    momo_base_url: str = "https://sandbox.momodeveloper.mtn.com"
    momo_subscription_key: str = ""
    momo_api_user: str = ""
    momo_api_key: str = ""
    momo_target_environment: str = "sandbox"
    momo_callback_secret: str = "dev-webhook-secret"

    # La monnaie de la zone UEMOA n'a pas de sous-unité : 1 XOF = 1 unité mineure.
    currency: str = "XOF"


    @property
    def cors_origin_list(self) -> list[str]:
        """Les origines autorisées, normalisées.

        Une origine sans schéma est complétée en `https://` : plusieurs
        plateformes n'exposent que le nom d'hôte, et une origine mal formée est
        rejetée par le navigateur sans le moindre message d'erreur utile.
        """
        origines: list[str] = []
        for brute in self.cors_origins.split(","):
            origine = brute.strip().rstrip("/")
            if not origine:
                continue
            if "://" not in origine:
                origine = f"https://{origine}"
            origines.append(origine)
        return origines


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
