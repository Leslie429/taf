# Tontine digitale

Application d'épargne rotative (tontine) avec encaissement et versement par
Mobile Money. Un groupe de membres cotise à chaque tour ; la cagnotte est versée
à un membre différent à chaque échéance, selon un ordre figé au démarrage.

> Projet de démonstration technique orienté FinTech : comptabilité en partie
> double, paiements idempotents, webhooks signés.

**Démo** : <https://tontine-web-7208.onrender.com> · **API** :
<https://tontine-api-jhph.onrender.com/docs>

Le compte de démonstration entre dans une tontine déjà entamée — deux tours
versés, un en collecte, une cotisation à régler :

| | |
| --- | --- |
| Téléphone | `+22901691004` |
| Mot de passe | `demo1234` |

Les services s'endorment après quinze minutes sans trafic : le premier appel
les réveille et prend une trentaine de secondes.

---

## Ce que le projet démontre

| Sujet | Mise en œuvre |
| --- | --- |
| Comptabilité | Grand livre en partie double, aucun solde stocké, contrepassation au lieu de correction |
| Fiabilité des paiements | Clé d'idempotence en base, machine à états des transactions, rejeu inoffensif |
| Intégration opérateur | API MTN MoMo (Collection et Disbursement) sur sandbox, avec double de test |
| Sécurité | JWT accès/rafraîchissement, limitation de débit, révocation à la déconnexion, webhooks signés HMAC-SHA256 comparés en temps constant, callbacks non signés vérifiés auprès de l'opérateur |
| Qualité | 105 tests Pytest (92 % de couverture) et 10 tests Vitest, lint Ruff, typage strict `mypy` et TypeScript, CI GitHub Actions |
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
cd backend && pytest              # 105 tests, 92 % de couverture

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
  `contribution:<id>:<essai>` pour une cotisation, `payout:<cycle_id>:<essai>`
  pour un versement. Une seconde tentative retrouve la transaction d'origine au
  lieu d'en créer une.
- Le rang d'essai est ce qui réconcilie l'idempotence avec le droit de
  réessayer. Sans lui, un refus de l'opérateur — une coupure réseau, une devise
  rejetée — figerait l'opération pour toujours : la clé serait prise par
  l'échec, et toute nouvelle demande retomberait dessus. `next_attempt_key`
  n'ouvre un rang suivant que si le dernier essai a échoué ; tant qu'un essai
  est en cours ou réussi, il est renvoyé tel quel.
- **Un délai dépassé n'est pas un refus.** Un jeton refusé ou une connexion
  qui n'aboutit jamais : rien n'est parti, l'essai est clos en échec avec la
  raison donnée par l'opérateur. Mais une demande partie dont la réponse s'est
  perdue a peut-être été exécutée. La clore ouvrirait un essai suivant, sous une
  autre référence, que l'opérateur prendrait pour un second versement. Elle
  reste donc en cours, sous sa référence d'origine, et c'est le callback ou le
  rapprochement qui tranchent — en interrogeant l'opérateur sur cette référence.
- Dans aucun de ces cas l'incident ne remonte en erreur 500. Une exception non
  rattrapée annulerait la requête, et avec elle la transaction déjà inscrite au
  grand livre : la trace promise disparaîtrait au moment précis où elle sert.
- Deux requêtes concurrentes sont arbitrées par la base : celle qui perd la
  course sur la contrainte d'unicité récupère la transaction gagnante.
- L'identifiant de la transaction sert de `X-Reference-Id` à l'appel MTN, ce qui
  rend l'appel opérateur lui-même rejouable.
- Les callbacks sont journalisés dans `webhook_events` avec une contrainte
  d'unicité sur `(provider, event_id)` : un rejeu répond `duplicate` sans
  reproduire l'effet métier.

### Un callback n'est pas une preuve

Un callback signé est cru sur parole : la signature HMAC prouve qu'il vient de
qui partage le secret.

**MTN, lui, ne signe rien.** Il n'a jamais reçu ce secret et ne peut pas le
connaître — ses appels arrivaient donc en 401. Un webhook qui n'accepte que du
signé ne peut tout simplement pas parler à cet opérateur.

Un appel non signé n'est donc pas traité comme une vérité mais comme un
indice : « il s'est passé quelque chose sur cette référence ». L'API interroge
alors l'opérateur avec ses propres identifiants et applique **sa** réponse,
jamais le corps reçu.

La propriété qui remplace la signature : un callback forgé ne peut rien
fabriquer. Au pire, il fait interroger MTN pour rien. Et un opérateur injoignable
ou encore indécis ne produit aucun verdict — la transaction reste en cours et
l'opérateur rappellera.

## Durcissement de l'authentification

### Limitation de débit

Deux seaux sur `/auth/login`, comptés tous les deux à chaque tentative :
**par adresse** contre le balayage de numéros, **par numéro** contre
l'acharnement sur un seul compte. Un dépassement répond `429` avec `Retry-After`.

Le compteur vit en **PostgreSQL**, pas en mémoire : l'API tourne sur plusieurs
machines, et un compteur par processus se contournerait en insistant jusqu'à
tomber sur l'autre. L'incrément passe par un `INSERT ... ON CONFLICT DO UPDATE`
qui renvoie le total : atomique, sans lecture préalable ni verrou.

La fenêtre est fixe plutôt que glissante. Son défaut connu — jusqu'à deux fois
la limite à cheval sur deux fenêtres — est sans portée face à une attaque qui
se compte en milliers d'essais, et elle tient dans un seul entier par seau.

Une tentative refusée reste comptée : le compteur est validé avant que la
requête n'échoue, sans quoi son annulation effacerait la trace de la tentative
qui l'a motivée.

`rate_limit_counters` gagne une ligne par seau et par fenêtre.
[`scripts/purger_limites.py`](backend/scripts/purger_limites.py) efface les
fenêtres périmées ; c'est la première tâche que prendra le battant Celery.

### Révocation des jetons

`POST /auth/logout` ne noircit aucune liste : il déplace une frontière. Le
compte porte un `tokens_valid_from`, et tout jeton émis avant cet instant est
refusé — accès et rafraîchissement d'un coup.

L'intérêt est le coût : **la vérification n'ajoute aucune requête**. La ligne
de l'utilisateur est de toute façon chargée pour l'authentifier, et la date
d'émission est déjà dans le jeton. Une liste noire de `jti` aurait imposé une
lecture de plus à chaque appel authentifié.

Deux contreparties, assumées. La déconnexion vaut pour **toutes** les sessions
du compte, pas seulement le terminal courant. Et comme `iat` ne porte que des
secondes entières, l'arrondi est laissé du côté sûr : une reconnexion dans la
seconde même de la déconnexion échouerait, plutôt que de laisser survivre le
jeton avec lequel on vient de se déconnecter.

## Machine à états d'une transaction

```
pending ──▶ processing ──▶ success ──▶ reversed
   │             │
   └──▶ failed ◀─┘
```

Les transitions autorisées sont déclarées dans `ALLOWED_TRANSITIONS` ; toute
autre tentative lève `InvalidTransition`. Une transaction `failed` est
terminale : on n'y revient pas, on en crée une nouvelle.

## Le rapprochement quotidien

Un callback se perd, un réseau coupe au mauvais moment, un opérateur change
d'avis. Le grand livre finit par diverger du relevé de l'opérateur, et rien
dans l'application ne le signalera de lui-même. C'est le rôle de
[`scripts/rapprocher.py`](backend/scripts/rapprocher.py).

Deux divergences, deux traitements — et l'écart de gravité entre elles est tout
le sujet :

| Constat | Ce que ça veut dire | Traitement |
| --- | --- | --- |
| `unconfirmed` | en cours chez nous, tranché chez l'opérateur | **rattrapé** : le verdict est appliqué |
| `operator_silent` | l'opérateur n'a pas répondu, ou n'a rien tranché | signalé, rien n'est touché |
| `unknown_at_operator` | l'opérateur ignore la référence | **signalé, jamais corrigé** |
| `disputed_success` | réussi chez nous, démenti par l'opérateur | **signalé, jamais corrigé** |

Les deux derniers sont les cas graves : de l'argent figure au grand livre sans
contrepartie chez l'opérateur. La réparation est une contrepassation, et une
contrepassation est une décision — pas un effet de bord de tâche planifiée. Le
script sort en code 2 pour qu'une tâche planifiée puisse alerter.

Trois garde-fous :

- **Un délai de grâce de quinze minutes.** Une transaction qui vient de partir
  n'est pas un écart : l'opérateur a le droit de mettre un moment à trancher.
- **Le même chemin que le webhook.** `tontine.appliquer_verdict` sert aux deux.
  Deux chemins séparés finiraient par diverger — exactement l'écart qu'un
  rapprochement est censé détecter, pas produire.
- **Aucune correction silencieuse.** Chaque constat laisse une ligne dans
  `reconciliation_divergences`, résolu ou non, avec les deux états au moment du
  constat. Un écart se relit des mois plus tard, quand les statuts ont bougé.

`GET /api/v1/admin/reconciliation` expose le dernier rapprochement, réservé aux
comptes portant `is_staff` — à ne pas confondre avec `Membership.is_admin`, qui
n'administre qu'une tontine.

## Modèle de données

```
users ─┬─ memberships ─┬─ tontine_groups
       │               └─ cycles ── contributions ──▶ transactions
       │                                                   │
accounts ◀───────── ledger_entries ────────────────────────┘

webhook_events            (journal des callbacks opérateur)
reconciliation_runs ── reconciliation_divergences   (écarts constatés)
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

Le client vit dans [`app/services/momo.py`](backend/app/services/momo.py) et se
choisit **produit par produit**, dans
[`app/api/deps.py`](backend/app/api/deps.py) :

| Clés renseignées | Encaissement | Versement |
| --- | --- | --- |
| aucune | double | double |
| `MOMO_DISBURSEMENT_KEY` seule | double | MTN |
| les deux | MTN | MTN |

MTN délivre une clé d'abonnement **par produit** : souscrire à *Collection* ne
donne aucun droit sur *Disbursement*. Confondre les deux vaut un 401.

### Plusieurs opérateurs

MTN ne couvre pas tout le marché béninois. Une tontine réunit des membres chez
plusieurs opérateurs, et un versement doit partir chez celui du bénéficiaire —
qui n'est pas forcément celui des cotisants. L'opérateur ne se choisit donc pas
au démarrage mais **à chaque paiement, d'après le numéro concerné**
([`app/services/operateurs.py`](backend/app/services/operateurs.py)).

Trois décisions structurent ce choix.

**La table des préfixes est une configuration, jamais une constante du code.**
Les plages de numérotation sont attribuées par le régulateur et changent ; les
figer dans les sources garantit qu'elles seront fausses un jour sans que rien
ne le signale. Elles se règlent par `OPERATOR_PREFIXES`, au format
`mtn_momo:22951,22961;moov:22994`. Le préfixe le plus long l'emporte, les
plages se chevauchant en longueur.

**La résolution par préfixe est une approximation, et c'est assumé.** La
portabilité permet à un abonné de garder son numéro en changeant d'opérateur :
le préfixe donne alors le mauvais résultat. C'est acceptable parce que l'erreur
est visible et rattrapable — l'opérateur refuse l'appel, la transaction échoue,
et le rang d'essai permet de la relancer. Un service de production interrogerait
un annuaire de portabilité.

**Le rapprochement repart de l'opérateur consigné**, pas du numéro : une
transaction sait qui l'a traitée, et c'est celui-là qu'il faut interroger.

#### Moov Africa

`moov` est enregistré comme opérateur et son client est **le double de test**.
Ce n'est pas un oubli : je n'ai pas la documentation de l'API Moov, et
fabriquer des points d'entrée plausibles produirait du code qui a l'air de
marcher sans marcher. La couture est dans
[`app/api/deps.py`](backend/app/api/deps.py) — enregistrer un vrai client sous
ce code suffit, tout le reste du chemin est en place et éprouvé.

### Ce que le sandbox MTN autorise aujourd'hui

*Disbursement* se souscrit normalement. **Le produit *Collection* est
saturé** : Azure API Management y plafonne à 25 000 abonnements, tous
développeurs confondus, et le portail refuse toute nouvelle souscription.

```json
{"error":{"code":"ValidationError","message":"You've reached the maximum number
of Subscriptions (25000) in Product. Please delete one or more Subscription(s)
from Product to continue..."}}
```

Le message vise le compte, mais la limite porte sur le produit : un compte
vierge se fait rejeter de la même façon, et il n'y a rien à supprimer de son
côté. C'est ce qui a motivé le choix produit par produit — un opérateur
partiellement disponible est une situation d'exploitation ordinaire, pas un
accident de démonstration.

### Brancher le sandbox

1. Créer un compte sur [momodeveloper.mtn.com](https://momodeveloper.mtn.com)
   et souscrire aux produits accessibles
2. Provisionner l'utilisateur d'API — deux appels qui déclarent l'hôte de
   callback, sans quoi MTN n'enverra jamais rien :

```bash
export MOMO_DISBURSEMENT_KEY=<clé primaire du produit>
python scripts/provisionner_momo.py --produit disbursement --hote tontine-api-jhph.onrender.com
```

Le script imprime la commande `fly secrets set` à exécuter. La clé d'API n'est
renvoyée qu'une fois par MTN : elle n'est plus relisible ensuite.

## Déploiement

Le projet se déploie en deux services — l'API et le front — plus une base
PostgreSQL. Les images de production sont distinctes de celles du
développement : construction en plusieurs étapes, utilisateur sans privilèges,
aucun outil de compilation dans l'image finale, migrations appliquées au
démarrage.

### Render pour les applications, Neon pour la base

C'est le montage en place. Les deux hébergeurs sont gratuits et sans carte
bancaire, et la séparation résout leurs défauts respectifs : les services web
de Render s'endorment sans trafic, ce qui ne coûte qu'une latence au réveil,
tandis que sa base gratuite expire à 90 jours — celle de Neon non.

```bash
# 1. La base, sur https://neon.tech — projet Postgres 16, région Frankfurt.
#    Copier la chaîne de connexion DIRECTE, sans « -pooler » dans l'hôte :
#    PgBouncer en mode transaction rejette les requêtes préparées de psycopg 3,
#    et Alembic ne migre pas à travers un pooler.

# 2. Render → New → Blueprint → sélectionner ce dépôt.
#    Le blueprint demande DATABASE_URL, CORS_ORIGINS, VITE_API_URL et les MOMO_*.

# 3. Après le premier déploiement, les URL réelles sont connues : renseigner
#    CORS_ORIGINS et VITE_API_URL, puis redéployer le front — son URL d'API est
#    figée à la compilation.
```

Le préfixe de la chaîne Neon n'a pas à être converti : `postgresql://` et
`postgres://` sont ramenés à `postgresql+psycopg://` par la configuration.

Les migrations passent au démarrage du conteneur, la commande de
pré-déploiement étant réservée aux offres payantes. C'est sans risque : l'offre
gratuite ne lance qu'une instance. Le dépôt garde
[`backend/fly.toml`](backend/fly.toml), où la même migration est un
`release_command` — là, deux machines tournent, et la lancer au démarrage ferait
courir deux migrations en concurrence sur la même table de version.

### Ce qu'il faut vérifier après un déploiement

1. `GET /health` répond `ok` **et nomme l'opérateur retenu pour chaque
   produit** — `fake` y signale une clé oubliée, avant qu'un paiement ne parte
   chez le double
2. `/docs` s'ouvre et liste les 20 opérations
3. Une inscription depuis le front aboutit — sinon, `CORS_ORIGINS` ne
   correspond pas exactement à l'origine du navigateur (schéma compris, sans
   barre finale)
4. Le compte de démonstration est créé et documenté en tête de ce README

### Peupler la démonstration

Un écran vide ne démontre rien. [`scripts/semer_demo.py`](backend/scripts/semer_demo.py)
crée une tontine de cinq membres déjà entamée — deux tours versés, un tour en
collecte — pour que la page d'accueil montre la barre de tours dans ses trois
états.

Le terminal distant de Render étant réservé aux offres payantes, les scripts
d'exploitation se lancent depuis un poste, avec `DATABASE_URL` pointant sur la
base de production :

```bash
cd backend && source .venv/bin/activate
export DATABASE_URL='<chaîne Neon directe>'

python scripts/semer_demo.py                       # peupler la démonstration
python scripts/promouvoir_equipe.py +22901691004   # ouvrir l'écran de rapprochement
python scripts/rapprocher.py                       # rapprochement quotidien
python scripts/purger_limites.py                   # ménage des compteurs
```

Il n'existe volontairement aucune route pour `promouvoir_equipe` : une
élévation de privilège qui s'obtient par un appel HTTP est une élévation de
privilège de trop.

`MOMO_CALLBACK_SECRET` se choisit, il ne s'engendre pas. Tant que Collection
tourne sur le double, c'est
[`scripts/confirmer_paiements.py`](backend/scripts/confirmer_paiements.py) qui
joue l'opérateur et signe les callbacks — depuis un poste. Un secret engendré
par l'hébergeur, que personne ne connaît, rendrait ce script inutilisable et
aucune cotisation ne pourrait plus être confirmée.

Le script passe par les services métier, jamais par des insertions directes :
les écritures du grand livre sont celles qu'aurait produites une vraie
utilisation, et les soldes affichés se recalculent à partir d'elles.

### Mobile Money en production

Sans `MOMO_SUBSCRIPTION_KEY`, l'API bascule sur le client simulé : un paiement
part mais rien ne le confirme. Pour une démonstration en ligne, deux options —
brancher le sandbox MTN et déclarer l'URL de callback
`https://tontine-api-jhph.onrender.com/api/v1/webhooks/momo`, ou laisser le client simulé et confirmer
les paiements avec
[`scripts/confirmer_paiements.py`](backend/scripts/confirmer_paiements.py).

## Reste à faire

- [ ] Journal d'audit horodaté des actions d'administration
- [ ] Relances automatiques des cotisations en retard (Celery battant)
- [ ] PWA hors connexion : consultation et file de cotisations en attente
- [ ] Notifications SMS

## Licence

MIT
