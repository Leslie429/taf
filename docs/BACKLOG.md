# BACKLOG — Tontine digitale

> Consolide la section « Reste à faire » du [`README.md`](../README.md) et les points ouverts relevés
> en exploitation. Statuts : `~/dev-standards/rules/STATUSES.md`.
> La feuille de route initiale (9 étapes) est **terminée** — voir `DECISIONS.md` → `DEC-101`.

## Tâches actives

| ID | Nom | Priorité | Statut | Bloqué par |
|---|---|---|---|---|
| `DEMO-101` | Réinitialiser la tontine de démonstration | HAUTE | `NOT_STARTED` | — |
| `OPS-101` | `/health` ne vérifie pas la base alors que Render s'en sert comme `healthCheckPath` | MOYENNE | `NOT_STARTED` | — |
| `MOMO-101` | Débloquer le produit Collection du sandbox MTN | MOYENNE | `BLOCKED` | **externe — MTN** |
| `SMS-101` | Brancher un vrai fournisseur SMS et exercer l'envoi | MOYENNE | `BLOCKED` | compte fournisseur à ouvrir |
| `RELANCE-101` | Relances par palier (J+1, J+3, J+7) plutôt que quotidiennes | BASSE | `NOT_STARTED` | — |
| `TEST-101` | Couverture de `ordonnanceur.py` à 70 % — la plus basse du projet | BASSE | `NOT_STARTED` | — |

## Fiches détaillées

### `DEMO-101` — Réinitialiser la démonstration
* **Constat :** 4 tours versés sur 5 au 2026-09-16 ; le tour 5 n'est pas dû avant le **2026-11-19**.
* **Effet :** un visiteur ne voit ni cotisation à régler, ni relance. **Comportement correct, pas un bug** —
  mais la vitrine est vide, ce qui va à l'encontre de la raison d'être du projet : se démontrer.
* **Correctif :** `semer_demo.py --reinitialiser` pour redonner un tour en collecte et une cotisation due.
* **Critères d'acceptation :** une cotisation à régler visible sur la démo en ligne ; une relance
  déclenchable ; les invariants du rapprochement et du double inchangés ; suites vertes.

### `OPS-101` — `/health` ne sonde pas la base
* **Constat `VÉRIFIÉ` le 2026-09-23 :** `/health` renvoie `operators` et `momo_env` (noms seulement),
  sans aucune requête base. Render l'utilise comme `healthCheckPath`.
* **Risque :** base injoignable → service déclaré **sain**, aucune alerte, pannes silencieuses.
* **Piste :** un `SELECT 1` borné en temps, avec un statut dégradé distinct, sans allonger le réveil à froid.

### `MOMO-101` — Collection saturé côté MTN
* **Cause :** plafond Azure de 25 000 abonnements sur le produit Collection du sandbox.
* **Tentatives :** ticket ouvert sur le forum MTN — **sans réponse à ce jour**.
* **Impact :** l'encaissement reste sur le double ; le versement, lui, est réel et prouvé.
* **Action nécessaire :** relance côté MTN, ou changement d'opérateur d'encaissement. **Hors de portée ici.**

### `SMS-101` — Canal SMS jamais exercé
* **État :** protocole, double et client Twilio écrits et **testés par transport simulé**. Jamais
  confrontés au vrai service, faute de compte. Le README l'écrit franchement — **ne pas maquiller ce point**.

## Bugs corrigés

| ID | Bug | Correction | Date |
|---|---|---|---|
| BUG-101 | Page blanche en production (boucle de rendu de `OfflineBar`, React n° 185) | instantané stable de la file + test qui rend le bandeau | 2026-09-24 |

## Dette technique

| ID | Élément | Décision |
|---|---|---|
| `DEBT-101` | Couverture `ordonnanceur.py` à 70 % — les boucles asyncio sont peu testées | Acceptée : les chemins critiques (frontière double / rapprochement) **sont** couverts par des tests nommés. Revisiter si une boucle est modifiée. |

## Terminé — feuille de route du 2026-09-09

| # | Étape | Date |
|---|---|---|
| 1 | Déploiement + démo peuplée (Fly, puis migration Render le 2026-09-10) | 2026-09-10 |
| 2 | Sandbox MTN MoMo — versement réel accepté et confirmé | 2026-09-11 |
| 3 | Durcissement auth : limitation de débit à deux seaux, révocation par `tokens_valid_from` | 2026-09-12 |
| 4 | Rapprochement quotidien (`scripts/rapprocher.py`) | 2026-09-11 |
| 5 | Multi-opérateur par préfixe de numéro | 2026-09-12 |
| 6 | PWA hors connexion — service worker écrit à la main, sans dépendance ajoutée | 2026-09-12 |
| 7 | Tâches de fond dans le conteneur (`ordonnanceur.py`) — la démo se termine seule | 2026-09-12 |
| 8 | Journal d'audit — 5 actions qui engagent de l'argent ou déplacent un droit | 2026-09-16 |
| 9 | Relances + SMS + purge des compteurs | 2026-09-16 |
