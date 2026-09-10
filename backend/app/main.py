import os
from typing import Any

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.deps import get_operateurs
from app.api.routes import admin, auth, groups, history, payments
from app.core.config import settings

app = FastAPI(
    title=settings.app_name,
    version="0.1.0",
    description="API de tontine digitale avec encaissement et versement Mobile Money.",
    # La documentation reste ouverte : c'est un projet de démonstration, et
    # `/docs` est ce qu'un recruteur ouvrira en premier.
    docs_url="/docs",
    redoc_url=None,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router, prefix="/api/v1")
app.include_router(groups.router, prefix="/api/v1")
app.include_router(payments.router, prefix="/api/v1")
app.include_router(history.router, prefix="/api/v1")
app.include_router(admin.router, prefix="/api/v1")


@app.get("/health", tags=["système"])
def health() -> dict[str, Any]:
    """Santé du service, et qui traite réellement les paiements.

    Le nom de l'opérateur retenu pour chaque produit est une information
    d'exploitation, pas un secret : il dit si une clé a bien été posée, sans
    jamais en révéler la valeur. Sans ce témoin, une clé oubliée ne se voit
    qu'au premier paiement parti chez le double — c'est-à-dire trop tard.
    """
    operateurs = get_operateurs()
    return {
        "status": "ok",
        "environment": settings.environment,
        "operators": {
            produit: operateurs.pour_numero("").provider_for(produit)
            for produit in ("collection", "disbursement")
        },
        # Les noms des variables Mobile Money vues par le processus, et pour
        # chacune si elle porte une valeur. Jamais la valeur elle-même.
        #
        # Sans ce témoin, trois pannes très différentes se ressemblent : une
        # variable absente, une variable vide, et une variable écrite sous un
        # nom légèrement fautif. Aucune ne se distingue depuis l'extérieur, et
        # un hébergeur sans terminal distant ne permet pas d'aller voir.
        "momo_env": {
            nom: bool(valeur.strip())
            for nom, valeur in sorted(os.environ.items())
            if nom.startswith("MOMO_")
        },
    }
