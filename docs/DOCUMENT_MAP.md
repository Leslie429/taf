# CARTE DE LA DOCUMENTATION — Tontine digitale

> `PRESERVATION.md` §2 : un document existant qui remplit déjà un rôle est **référencé**, pas dupliqué.
> Le [`README.md`](../README.md) couvre à lui seul la majorité de la structure standard — d'où le petit
> nombre de fichiers dans `docs/`. Arbitrage : `DECISIONS.md` → `DEC-103`.

| Rôle standard | Où il se trouve | Créé ici ? |
|---|---|---|
| `PROJECT_OVERVIEW` | README — [Ce que le projet démontre](../README.md#ce-que-le-projet-démontre), [Pile technique](../README.md#pile-technique) | non |
| `ARCHITECTURE` | README — grand livre, idempotence, machine à états, rapprochement, ordonnanceur, journal d'audit, [Modèle de données](../README.md#modèle-de-données), [API](../README.md#api) | non |
| `ROADMAP` | Terminée. Historique dans `BACKLOG.md` → « Terminé — feuille de route du 2026-09-09 » | non |
| `TEST_PLAN` | README — [Tests](../README.md#tests) · commandes dans [`../CLAUDE.md`](../CLAUDE.md) · résultats mesurés dans `PROJECT_STATE.md` | non |
| `DEPLOYMENT` | README — déploiement Render, rotation du mot de passe Neon, vérifications post-déploiement, peuplement de la démo | non |
| `SECURITY` | README — durcissement auth, limitation de débit, révocation des jetons, webhook non signé | non |
| `CHANGELOG` | `git log` — messages en français, descriptifs du pourquoi | non |
| `PROJECT_STATE` | **manquait** → [`PROJECT_STATE.md`](PROJECT_STATE.md) | **oui** |
| `BACKLOG` | partiel (README « Reste à faire ») → [`BACKLOG.md`](BACKLOG.md), consolidé | **oui** |
| `DECISIONS` | en prose dans le README → [`DECISIONS.md`](DECISIONS.md), qui l'**indexe** sans le recopier | **oui** |
| Règles projet | **manquait** → [`../CLAUDE.md`](../CLAUDE.md) | **oui** |

## Autres éléments du dépôt

| Élément | Rôle |
|---|---|
| `Makefile` · `docker-compose.yml` | démarrage local |
| `render.yaml` | blueprint de déploiement Render |
| `.github/workflows/ci.yml` | intégration continue |
| `design/` | éléments visuels |
| `.env.example` | **noms** de variables uniquement — le `.env` réel est gitignoré |
| `backend/scripts/` | `rapprocher.py`, `semer_demo.py`, `confirmer_paiements.py`, `purger_limites.py` |

## Ce qui n'est pas dans ce dépôt

Quatre entrées de mémoire locale sans rapport avec le code restent hors dépôt —
`DECISIONS.md` → `DEC-102`. Ne pas les y faire entrer, ni décrire leur contenu ici.
