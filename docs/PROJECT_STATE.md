# PROJECT STATE — Tontine digitale

> **SOURCE DE VÉRITÉ** sur l'état réel du projet (règle 12 du MASTER ENGINEERING SYSTEM).
> Le [`README.md`](../README.md) reste la référence sur *comment ça marche* ; ce fichier dit
> *où ça en est*. Statuts : `~/dev-standards/rules/STATUSES.md`.

**Dernière mise à jour :** 2026-09-24 — incident de production corrigé (voir « Incident du 2026-09-24 »).

## Projet

| | |
|---|---|
| Nom | Tontine digitale — épargne rotative avec Mobile Money |
| Nature | **Projet de démonstration technique** orienté FinTech — pas un produit exploité |
| Dépôt | `github.com/Leslie429/taf` — **public**, `main`, MIT |
| Stack | FastAPI · SQLAlchemy · Alembic · PostgreSQL (Neon) · React · TypeScript · Vite |
| Hébergement | Render (front + API), base Neon |

## État global

* **Statut :** **fonctionnellement complet et déployé.** La feuille de route convenue le 2026-09-09
  est terminée dans ses 9 étapes. Le README déclare « Reste à faire : rien de déclaré ».
* **Progression :** 9 / 9 étapes de la feuille de route → `DONE`
* **Parité code ↔ production :** `VÉRIFIÉ` — `/health` annonce le commit `281b682`, identique au
  `HEAD` local. Rien n'attend d'être déployé.

## Tests — `VÉRIFIÉ` le 2026-09-23 (suites réellement exécutées)

| Suite | Commande | Résultat | Couverture |
|---|---|---|---|
| Backend | `.venv/bin/pytest` | **175 réussis, 0 échec, 0 ignoré** (code de sortie 0) | **93 %** (1 489 lignes, 100 non couvertes) |
| Frontend | `npx vitest run` | **33 réussis** sur 5 fichiers, 0 échec (code de sortie 0) | — |

Modules les moins couverts : `ordonnanceur.py` **70 %** · `momo.py` 85 % · `tontine.py` 90 % ·
`rapprochement.py` 92 %.

## Production — `VÉRIFIÉ` le 2026-09-23

| Contrôle | Résultat |
|---|---|
| API `GET /health` | **HTTP 200** — `status: ok`, `environment: production`, `commit: 281b682` |
| Front `GET /` | **HTTP 200**, `text/html` |
| Réveil à froid Render | **43,7 s** pour l'API, 12,9 s pour le front (offre gratuite, sommeil après 15 min) |
| Opérateurs configurés | encaissement `fake` (**double**) · versement `mtn_momo` (**réel**) |
| Variables MoMo | 5 présentes : `MOMO_API_KEY`, `MOMO_API_USER`, `MOMO_CALLBACK_SECRET`, `MOMO_CALLBACK_URL`, `MOMO_DISBURSEMENT_KEY` |

⚠️ `/health` **n'interroge pas la base** alors que Render s'en sert comme `healthCheckPath` : une base
morte laisserait le service déclaré sain. → `OPS-101`.

## Ce qui a été prouvé en conditions réelles

* **Versement Mobile Money réel** accepté et confirmé par MTN (sandbox, produit Disbursement).
* **Rapprochement** : a rattrapé une divergence **réelle**, non fabriquée — local `processing`,
  opérateur `SUCCESSFUL`, verdict appliqué, cycle passé à `paid_out`. C'est la démonstration la plus
  parlante du sujet.
* **Ordonnanceur en production** : une passe de rapprochement a tourné d'elle-même ~10 min après le
  démarrage du service, conforme aux 600 s configurées.
* **Journal d'audit en production** : une ligne `reconciliation.launched` réellement écrite.

## Ce qui n'a jamais été exercé — à dire tel quel

* **Encaissement Mobile Money réel** : le produit Collection du sandbox MTN est saturé côté MTN
  (plafond Azure de 25 000 abonnements). Ticket ouvert sur leur forum, **sans réponse à ce jour**.
  L'encaissement reste sur le double.
* **Envoi SMS réel** : protocole, double et client Twilio écrits et testés par transport simulé, mais
  **jamais exercés contre le vrai service** (pas de compte). Le README le dit franchement.
* **API Moov** : opérateur enregistré, branché sur le double, son API n'a pas été lue —
  volontairement non inventée.

## Tâche actuelle

Aucune. Le projet est en état stable et démontrable.

## Problèmes ouverts

Voir [`BACKLOG.md`](BACKLOG.md). Le seul point à effet visible : la tontine de démonstration arrive en
fin de vie (`DEMO-101`).

## Prochaine tâche

`DEMO-101` — réinitialiser la démonstration. 4 tours versés sur 5 au 2026-09-16, et le tour 5 n'est
pas dû avant le **2026-11-19** : **aucune relance ne s'affiche d'ici là** — comportement correct, pas un
bug, mais un visiteur ne verra donc ni cotisation à régler, ni relance. `semer_demo.py --reinitialiser`
lui redonne un tour en collecte.

## Dernier checkpoint

**2026-09-23** — mise sous système de règles : `CLAUDE.md` et `docs/` créés, README préservé comme
référence, suites de tests et production réellement mesurées. Aucun code métier touché.

## Notes importantes

* Les invariants à ne pas franchir sont dans [`../CLAUDE.md`](../CLAUDE.md) — les lire avant toute
  modification du webhook, du rapprochement ou de l'ordonnanceur.
* Le mot de passe Neon a été tourné le 2026-09-15 par Leslie ; l'ancienne chaîne dort dans les secrets
  Fly d'une app suspendue, inaccessible et sans effet.
* La base de test locale `tontine_test` doit appartenir au rôle `tontine`, sinon la suite backend
  échoue entièrement.

## Incident du 2026-09-24 — page blanche en production (`BUG-101`)

* **Constat :** le front en production restait blanc pour tout visiteur. Erreur React n° 185
  (« Maximum update depth exceeded ») dans `OfflineBar`. Le contrôle du 2026-09-23 ne vérifiait
  que le code HTTP 200 du front, pas son rendu.
* **Cause racine :** `useQueue` passait `readQueue` à `useSyncExternalStore` ; `readQueue` rend un
  tableau neuf à chaque appel, React y voyait un changement à chaque rendu et bouclait.
* **Correction :** instantané stable (`queueSnapshot`), remplacé à chaque écriture, y compris
  quand la persistance échoue ; instantané serveur constant.
* **Test de régression :** `src/components/OfflineBar.test.tsx` rend réellement le bandeau ; il
  **échoue** sur l'ancien code (même erreur) et passe sur le nouveau. Suite front : 37 réussis.
* **Suites de l'incident (2026-09-24) :**
  * `OPS-102` — contrôle de rendu réel : `frontend/scripts/verifier-production.mjs` + workflow
    `.github/workflows/production.yml`. Vérifié à la main contre la production (4/4 en 18 s) et
    contre la version d'avant le correctif compilée en local : **échec détecté** (React n° 185,
    racine vide, code 1). Premier passage dans GitHub Actions : run `36012082887` ✅ (commit `b0df215`, après la CI ; bundle inchangé donc contrôle de la version en ligne, 4/4).
  * `BUG-102` — nom du compte de démonstration « Léslie » → « Leslie » : script de démo corrigé,
    migration `0007` testée sur base jetable (seule la ligne visée change, descente, `alembic check`).
    Appliquée en production par `alembic upgrade head` au démarrage du conteneur Render :
    `GET /api/v1/auth/me` du compte de démonstration renvoie « Leslie Tokponto » (`VÉRIFIÉ` le 2026-09-24).
