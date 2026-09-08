# Tontine digitale

Application d'épargne rotative (tontine) avec encaissement et versement par
Mobile Money. Un groupe de membres cotise à chaque tour ; la cagnotte est versée
à un membre différent à chaque échéance, selon un ordre figé au démarrage.

> Projet de démonstration technique orienté FinTech : comptabilité en partie
> double, paiements idempotents, webhooks signés.

**Démo** : _à déployer_ · **API** : _à déployer_ `/docs`

---

## Ce que le projet démontre

| Sujet | Mise en œuvre |
| --- | --- |
| Comptabilité | Grand livre en partie double, aucun solde stocké, contrepassation au lieu de correction |
| Fiabilité des paiements | Clé d'idempotence en base, machine à états des transactions, rejeu inoffensif |
| Intégration opérateur | API MTN MoMo (Collection et Disbursement) sur sandbox, avec double de test |
| Sécurité | JWT accès/rafraîchissement, webhooks signés HMAC-SHA256 comparés en temps constant |
| Qualité | 45 tests Pytest (89 % de couverture) et 10 tests Vitest, lint Ruff, typage strict `mypy` et TypeScript, CI GitHub Actions |
| Exploitation | Docker Compose, migrations Alembic versionnées, healthchecks |

## Pile technique

**Back-end** — Python 3.12, FastAPI, SQLAlchemy 2.0, Alembic, PostgreSQL 16, Redis
**Front-end** — React 18, TypeScript, Vite, TanStack Query, React Router
**Outillage** — Docker Compose, Pytest, Vitest, Ruff, mypy, GitHub Actions

---

## Démarrage

### Avec Docker (recommandé)

```bash
cp .env.example .env
docker compose up --build
```

- API : http://localhost:8000 — documentation interactive sur `/docs`
- Front : http://localhost:5173

Les migrations sont appliquées automatiquement au démarrage de l'API.

### Sans Docker

Il faut un PostgreSQL 16 et un Redis accessibles en local.

```bash
# Back-end
cd backend
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
export DATABASE_URL=postgresql+psycopg://tontine:tontine@localhost:5432/tontine
alembic upgrade head
uvicorn app.main:app --reload

# Front-end
cd frontend
npm install
npm run dev
```

### Tests

```bash
# Back-end — nécessite une base tontine_test
createdb tontine_test
cd backend && pytest              # 45 tests, 89 % de couverture

# Front-end
cd frontend && npm run test       # 10 tests
```

Les tests back-end tournent sur un vrai PostgreSQL, pas sur SQLite : les types
`ENUM` et `JSONB` ainsi que le comportement transactionnel doivent être ceux de
la production. Chaque test s'exécute dans un point de sauvegarde annulé à la
fin, si bien qu'aucun état ne fuit d'un test à l'autre.

---

## Le grand livre en partie double

C'est le cœur du projet. Trois règles, tenues par
[`app/services/ledger.py`](backend/app/services/ledger.py) et par lui seul :

1. **Toute transaction porte au moins deux écritures équilibrées.** La somme des
   débits égale la somme des crédits, sinon l'écriture est refusée.
2. **Aucun solde n'est stocké.** Un solde se calcule à partir des écritures, ce
   qui rend impossible la divergence entre un champ `balance` et l'historique.
3. **Une écriture n'est jamais modifiée.** Une erreur se corrige par
   contrepassation : une transaction miroir qui annule la première tout en
   laissant sa trace.

Encaisser une cotisation de 5 000 F donne ceci :

| Compte | Sens | Montant |
| --- | --- | --- |
| Clearing MTN MoMo (actif) | Débit | 5 000 |
| Cagnotte du groupe (passif) | Crédit | 5 000 |

Le versement au bénéficiaire inverse exactement ces deux écritures.

Les montants sont des entiers en unité mineure. Le franc CFA n'ayant pas de
sous-unité, `5000` se lit « 5 000 F » — mais le choix de l'entier reste valable
si l'application s'étend à une monnaie à décimales.

## L'idempotence des paiements

Un utilisateur sur un réseau instable appuiera deux fois sur « Payer ». Un
opérateur rejouera son callback. Les deux cas doivent rester sans effet.

- Chaque transaction porte une `idempotency_key` sous contrainte d'unicité —
  `contribution:<id>` pour une cotisation, `payout:<cycle_id>` pour un versement.
  Une seconde tentative retrouve la transaction d'origine au lieu d'en créer une.
- Deux requêtes concurrentes sont arbitrées par la base : celle qui perd la
  course sur la contrainte d'unicité récupère la transaction gagnante.
- L'identifiant de la transaction sert de `X-Reference-Id` à l'appel MTN, ce qui
  rend l'appel opérateur lui-même rejouable.
- Les callbacks sont journalisés dans `webhook_events` avec une contrainte
  d'unicité sur `(provider, event_id)` : un rejeu répond `duplicate` sans
  reproduire l'effet métier.

## Machine à états d'une transaction

```
pending ──▶ processing ──▶ success ──▶ reversed
   │             │
   └──▶ failed ◀─┘
```

Les transitions autorisées sont déclarées dans `ALLOWED_TRANSITIONS` ; toute
autre tentative lève `InvalidTransition`. Une transaction `failed` est
terminale : on n'y revient pas, on en crée une nouvelle.

## Modèle de données

```
users ─┬─ memberships ─┬─ tontine_groups
       │               └─ cycles ── contributions ──▶ transactions
       │                                                   │
accounts ◀───────── ledger_entries ────────────────────────┘

webhook_events   (journal des callbacks opérateur)
```

- `tontine_groups` — les paramètres : montant, fréquence, date de départ
- `memberships` — l'appartenance et le rang de passage, unique par groupe
- `cycles` — un tour, avec son bénéficiaire et son échéance
- `contributions` — ce qu'un membre doit pour un cycle, unique par couple
- `accounts` / `ledger_entries` / `transactions` — le grand livre

## API

| Méthode | Route | Rôle |
| --- | --- | --- |
| `POST` | `/api/v1/auth/register` | Inscription |
| `POST` | `/api/v1/auth/login` | Connexion |
| `POST` | `/api/v1/auth/refresh` | Renouvellement du jeton d'accès |
| `GET` | `/api/v1/auth/me` | Profil courant |
| `POST` | `/api/v1/groups` | Créer une tontine |
| `GET` | `/api/v1/groups` | Ses tontines, paginées |
| `POST` | `/api/v1/groups/{id}/members` | Inviter un membre (brouillon seulement) |
| `POST` | `/api/v1/groups/{id}/activate` | Démarrer et engendrer les cycles |
| `GET` | `/api/v1/groups/{id}/cycles` | Échéances et cotisations |
| `GET` | `/api/v1/groups/{id}/balance` | Solde de la cagnotte |
| `POST` | `/api/v1/contributions/{id}/pay` | Payer sa cotisation |
| `POST` | `/api/v1/cycles/{id}/payout` | Verser la cagnotte |
| `POST` | `/api/v1/webhooks/momo` | Callback opérateur |

La documentation OpenAPI complète est engendrée sur `/docs`.

## Design

Le produit tient sur **un système et deux thèmes**. La structure, la typographie
et les formes sont communes ; seule la couleur bascule, ce qui évite que
l'interface se réorganise sous les doigts au changement de thème.

Le thème **clair est le défaut** — l'application s'utilise dehors, en plein
jour. Le sombre suit `prefers-color-scheme`, et l'écran Profil permet de forcer
l'un ou l'autre.

Tout est déclaré dans [`frontend/src/styles/tokens.css`](frontend/src/styles/tokens.css) :

| | Clair | Sombre |
| --- | --- | --- |
| Fond | `#F2F3EC` craie | `#12100E` nuit |
| Accent d'action | `#C2EE3E` lime | `#E0AC55` laiton |
| Emphase | `#14523A` vert forêt | `#E0AC55` laiton |
| Urgence | `#EE5B22` | `#E8734A` |

La règle qui rend la bascule cohérente : **l'accent qui mène est celui qui se
lit sur le fond**. Le lime est illisible en texte sur la craie mais parfait en
aplat ; le laiton fonctionne des deux façons sur la nuit.

Deux principes tiennent le reste :

- **Les montants ne sont jamais colorés.** La couleur porte le statut, pas la
  valeur — un chiffre orange se lirait « j'ai perdu de l'argent ».
- **Aucune ombre, dans aucun thème.** En clair la hiérarchie vient du trait, en
  sombre elle vient du fond.

Typographie : **Space Grotesk** pour les montants et les titres, toujours en
chiffres tabulaires ; **Archivo** pour l'interface. Cible tactile principale de
56 px, jamais moins de 44 px ailleurs.

La barre de tours segmentée ([`TourBar.tsx`](frontend/src/components/TourBar.tsx))
est la signature du produit : on y lit d'un coup d'œil ce qui est acquis, ce qui
se collecte, et où se trouve son propre tour.

Les maquettes sources vivent dans [`design/`](design/) et se republient en
canvas à la demande.

## Mobile Money

Le client vit dans [`app/services/momo.py`](backend/app/services/momo.py).
Sans `MOMO_SUBSCRIPTION_KEY` configurée, l'API bascule automatiquement sur
`FakeMoMoClient` : le développement local ne dépend pas d'un compte MTN.

Pour brancher le sandbox réel : créer un compte sur
[momodeveloper.mtn.com](https://momodeveloper.mtn.com), souscrire aux produits
*Collection* et *Disbursement*, puis renseigner les clés dans `.env`.

## Déploiement

Le projet se déploie en deux services — l'API et le front — plus une base
PostgreSQL. Les images de production sont distinctes de celles du
développement : construction en plusieurs étapes, utilisateur sans privilèges,
aucun outil de compilation dans l'image finale, migrations appliquées au
démarrage.

### Fly.io (recommandé)

Les machines s'arrêtent d'elles-mêmes sans trafic, ce qui garde la
démonstration gratuite. Une carte bancaire est demandée à l'inscription, même
sans facturation.

```bash
# 1. L'API et sa base
cd backend
fly launch --no-deploy --copy-config
fly postgres create --name tontine-db
fly postgres attach tontine-db          # renseigne DATABASE_URL

fly secrets set \
  JWT_SECRET="$(openssl rand -hex 32)" \
  MOMO_CALLBACK_SECRET="$(openssl rand -hex 32)" \
  CORS_ORIGINS="https://tontine-web.fly.dev"
fly deploy

# 2. Le front, qui a besoin de l'URL de l'API à la compilation
cd ../frontend
fly launch --no-deploy --copy-config
fly deploy --build-arg VITE_API_URL=https://tontine-api.fly.dev/api/v1
```

### Render (sans carte bancaire)

Le dépôt contient un blueprint : **New → Blueprint → sélectionner le dépôt**.
Render demandera `CORS_ORIGINS` et `VITE_API_URL` — renseignez-les avec les URL
complètes, schéma compris, après le premier déploiement.

À savoir : les services gratuits s'endorment après quinze minutes sans trafic,
et la base gratuite expire au bout de 90 jours. Pour une démonstration qui doit
tenir dans la durée, Fly.io est plus sûr.

### Ce qu'il faut vérifier après un déploiement

1. `GET /health` répond `{"status": "ok"}`
2. `/docs` s'ouvre et liste les 14 routes
3. Une inscription depuis le front aboutit — sinon, `CORS_ORIGINS` ne
   correspond pas exactement à l'origine du navigateur (schéma compris, sans
   barre finale)
4. Le compte de démonstration est créé et documenté en tête de ce README

### Mobile Money en production

Sans `MOMO_SUBSCRIPTION_KEY`, l'API bascule sur le client simulé : un paiement
part mais rien ne le confirme. Pour une démonstration en ligne, deux options —
brancher le sandbox MTN et déclarer l'URL de callback
`https://<api>/api/v1/webhooks/momo`, ou laisser le client simulé et confirmer
les paiements avec
[`scripts/confirmer_paiements.py`](backend/scripts/confirmer_paiements.py).

## Reste à faire

- [ ] Limitation de débit sur l'authentification, révocation des jetons à la déconnexion
- [ ] Journal d'audit horodaté des actions d'administration
- [ ] Relances automatiques des cotisations en retard (Celery battant)
- [ ] Rapprochement quotidien entre le grand livre et le relevé opérateur
- [ ] PWA hors connexion : consultation et file de cotisations en attente
- [ ] Notifications SMS

## Licence

MIT
