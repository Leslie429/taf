# --- Étape de construction : les dépendances dans un environnement isolé ---
FROM python:3.12-slim AS builder

ENV PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# Les dépendances sont installées avant le code : le cache Docker survit à
# toute modification applicative.
COPY pyproject.toml ./
RUN pip install --upgrade pip && pip install .

# --- Étape d'exécution : ni compilateur, ni cache, ni root ---
FROM python:3.12-slim AS runtime

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PATH="/opt/venv/bin:$PATH"

# Un utilisateur sans privilèges : une faille dans l'application ne donne pas
# la main sur le conteneur.
RUN useradd --create-home --uid 1000 tontine

WORKDIR /app

COPY --from=builder /opt/venv /opt/venv
COPY --chown=tontine:tontine . .

USER tontine

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request, sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=4).status == 200 else 1)"

# Les migrations passent au démarrage : un déploiement ne doit jamais tourner
# sur un schéma en retard.
CMD ["sh", "-c", "alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 2"]
