# RÈGLES PROJET — Tontine digitale (`taf`)

> **Ce fichier COMPLÈTE les règles globales, il ne les remplace pas.**
> Règles globales : `~/dev-standards/rules/` — MASTER_ENGINEERING_SYSTEM, PRESERVATION, STATUSES,
> DEFINITION_OF_DONE, EVIDENCE_POLICY.
> **La documentation de référence est le [`README.md`](README.md) (835 lignes).** Il fait autorité sur
> l'architecture, les partis pris, le déploiement et l'exploitation : le lire avant d'agir, et le
> **mettre à jour** plutôt que créer un document parallèle. Carte : [`docs/DOCUMENT_MAP.md`](docs/DOCUMENT_MAP.md).

## Identité

* **Projet :** tontine digitale — épargne rotative avec Mobile Money
* **Nature :** **projet de démonstration technique** orienté FinTech, pas un produit exploité.
  Cela dicte l'ordre des travaux : ce qui se **démontre** prime sur ce qui polit.
* **Dépôt :** `github.com/Leslie429/taf` — **public**, branche `main`, licence MIT
* **Stack :** FastAPI + SQLAlchemy + Alembic + PostgreSQL (Neon) · React + TypeScript + Vite + TanStack Query
* **Production :** front `https://tontine-web-7208.onrender.com` · API `https://tontine-api-jhph.onrender.com`

## ⚠️ Dépôt public

Tout ce qui est écrit ici est public. Aucune donnée personnelle, aucun identifiant, aucun secret.
Les mémoires personnelles restent hors du dépôt — `docs/DECISIONS.md` → `DEC-102`.

---

## 🚫 Les frontières à ne jamais franchir

Ces invariants tiennent la crédibilité du projet. Les « simplifier » le vide de son intérêt.

1. **Un callback n'est pas une preuve.** MTN ne signe pas ses callbacks. Un callback non signé n'est
   qu'un indice « il s'est passé quelque chose sur cette référence » : l'API **réinterroge l'opérateur**
   avec ses propres identifiants et applique *sa* réponse. Ne jamais refaire confiance au corps du
   callback — c'est la seule chose qui tient la sécurité du webhook.
   → README, [« Un callback n'est pas une preuve »](README.md#un-callback-nest-pas-une-preuve)
2. **Le rapprochement refuse les transactions du double.** Le test
   `test_une_transaction_du_double_nest_pas_confrontee` parle de fraude : **ne pas le renverser**.
3. **La tâche de fond `double` ne touche qu'aux transactions dont le provider consigné est `fake`.**
4. **Pas de Redis.** Retiré le 2026-09-12 : déclaré dans `docker-compose`, `pyproject`, `config.py`,
   `.env.example` et le README, utilisé par **zéro ligne**. Ne pas le réintroduire sans besoin réel.
5. **Pas de Celery.** L'ordonnanceur, ce sont des boucles asyncio lancées par le `lifespan` FastAPI
   (`app/services/ordonnanceur.py`). Un intervalle à 0 désactive une boucle.
6. **Ne jamais inventer une API non lue.** Moov est enregistré mais branché sur le double : son API
   n'a pas été lue, et cela est assumé et écrit. Même règle pour tout nouvel opérateur.

## Deux pièges de conception déjà payés

* **Journal d'audit :** une action réussie et sa trace partagent la transaction de la requête, mais un
  **refus** part dans une session à lui (`get_audit_session`) — sinon le rollback qui accompagne le 403
  effacerait la trace.
* **Relances :** l'anti-harcèlement est une **contrainte d'unicité** sur
  `relance:contribution:<id>:<jour>`, pas une condition dans le code. L'insertion va dans un
  `begin_nested()` (refusée hors savepoint, elle mettrait la session en échec) et **ne pas appeler
  `expunge` après** : le rollback du savepoint a déjà retiré l'objet.

---

## Tests

```bash
cd backend  && .venv/bin/pytest          # nécessite la base tontine_test
cd frontend && npx vitest run
```

* **Base de test :** `tontine_test` doit appartenir au rôle `tontine`, sinon toute la suite échoue en
  `permission denied for schema public` (défaut PostgreSQL 15+) :
  `psql -d tontine_test -c "ALTER DATABASE tontine_test OWNER TO tontine;"`
* Une tâche n'est pas terminée sans suite verte **et** vérification du périmètre. Voir
  `~/dev-standards/rules/DEFINITION_OF_DONE.md`.

## Exploitation — pièges Render déjà rencontrés

* Les variables saisies dans « Secret Files » deviennent des **fichiers dans `/etc/secrets/`**, pas des
  variables d'environnement.
* Le terminal distant est payant : les scripts d'exploitation se lancent **depuis le poste**, avec
  `DATABASE_URL` pointant sur Neon.
* `/health` expose `operators` et `momo_env` (**noms seulement**) pour diagnostiquer une clé absente,
  **mais n'interroge pas la base** — alors que Render s'en sert comme `healthCheckPath`. Une base morte
  laisserait le service déclaré sain. → `OPS-101` au backlog.
* Offre gratuite : le service **dort après 15 min** sans trafic (réveil à froid mesuré à **43,7 s** le
  2026-09-23). Les boucles de fond ne tournent donc que lorsqu'un visiteur l'a réveillé.
* **Migrations Alembic :** toujours sur la chaîne **directe** Neon, jamais `-pooler`.
* **Rotation du mot de passe Neon :** le rôle applicatif est `neondb_owner`, via le bouton « Connect ».
  « Credentials » dans la console Neon désigne des clés S3 et jetons d'API Gateway — **sans rapport**.

## Mobile Money

* Sans `MOMO_SUBSCRIPTION_KEY`, l'API bascule sur le client simulé et la tâche `double` rend le verdict.
* Sur Render, **ne pas compter sur le callback** pour confirmer un versement : un versement accepté par
  MTN le 2026-09-11 n'a jamais donné lieu à callback, cause non élucidée (**ne pas l'affirmer**).
  Le rapprochement est le chemin de règlement, ce qui rend sa planification nécessaire.
* L'en-tête `X-Callback-Url` est obligatoire **à chaque appel** : MTN n'enregistre qu'un *hôte* au
  provisionnement, sans chemin.

## Git

Identité du dépôt : `Leslie Tokponto <tokpontoleslie7@gmail.com>` (locale, déjà posée).
Messages de commit en français, descriptifs du **pourquoi**. Dépôt public : relire le diff complet.

## État courant

[`docs/PROJECT_STATE.md`](docs/PROJECT_STATE.md) — il fait foi.
