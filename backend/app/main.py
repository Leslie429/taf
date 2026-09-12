import asyncio
import logging
import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.deps import get_operateurs
from app.api.routes import admin, auth, groups, history, payments
from app.core.config import settings
from app.services import ordonnanceur

# Uvicorn ne configure que ses propres journaux. Sans cette ligne, tout ce que
# l'application consigne — à commencer par les échecs de l'ordonnanceur, qui
# tourne sans personne pour le regarder — n'arrive nulle part. Sur un hébergeur
# dont le terminal distant est payant, le journal est le seul témoin.
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s %(name)s  %(message)s",
)


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    """Les tâches de fond vivent exactement le temps de l'application.

    Le réseau d'opérateurs est relu à chaque passe plutôt que capturé ici :
    c'est la configuration du moment qui doit décider, pas celle du démarrage.
    """
    taches: list[asyncio.Task[None] | None] = [
        ordonnanceur.demarrer(
            "double",
            settings.double_intervalle_secondes,
            ordonnanceur.passe_du_double,
        ),
        ordonnanceur.demarrer(
            "rapprochement",
            settings.rapprochement_intervalle_secondes,
            lambda: ordonnanceur.passe_de_rapprochement(get_operateurs()),
        ),
    ]
    try:
        yield
    finally:
        await ordonnanceur.arreter(taches)


app = FastAPI(
    title=settings.app_name,
    version="0.1.0",
    description="API de tontine digitale avec encaissement et versement Mobile Money.",
    # La documentation reste ouverte : c'est un projet de démonstration, et
    # `/docs` est ce qu'un recruteur ouvrira en premier.
    docs_url="/docs",
    redoc_url=None,
    lifespan=lifespan,
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
        # Quel commit tourne réellement. Sans lui, un correctif déployé et un
        # correctif en attente de déploiement produisent les mêmes symptômes,
        # et le diagnostic tourne en rond. L'hébergeur renseigne la variable.
        "commit": (
            os.environ.get("RENDER_GIT_COMMIT") or os.environ.get("GIT_COMMIT") or "inconnu"
        )[:7],
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
