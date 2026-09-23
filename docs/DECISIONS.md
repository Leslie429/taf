# JOURNAL DES DÉCISIONS — Tontine digitale

> **Les décisions de conception sont expliquées en prose dans le [`README.md`](../README.md)** —
> c'est voulu, et c'est ce qui en fait une pièce de portfolio lisible. Ce fichier ne les recopie pas :
> il les **indexe** et consigne les arbitrages qui n'ont pas de place dans le README.

## Décisions de conception — où elles sont expliquées

| Décision | Section du README |
|---|---|
| Comptabilité en partie double | [Le grand livre en partie double](../README.md#le-grand-livre-en-partie-double) |
| Idempotence des paiements | [L'idempotence des paiements](../README.md#lidempotence-des-paiements) |
| **Un callback n'est pas une preuve** | [Un callback n'est pas une preuve](../README.md#un-callback-nest-pas-une-preuve) |
| Limitation de débit à deux seaux | [Limitation de débit](../README.md#limitation-de-débit) |
| Révocation par `tokens_valid_from` | [Révocation des jetons](../README.md#révocation-des-jetons) |
| Machine à états d'une transaction | [Machine à états d'une transaction](../README.md#machine-à-états-dune-transaction) |
| Rapprochement comme chemin de règlement | [Le rapprochement](../README.md#le-rapprochement) |
| Boucles asyncio plutôt que Celery/Redis | [Ce qui tourne tout seul](../README.md#ce-qui-tourne-tout-seul) |
| Frontière double ↔ rapprochement | [La frontière à ne pas franchir](../README.md#la-frontière-à-ne-pas-franchir) |
| Session dédiée pour tracer un refus | [Dans quelle transaction ?](../README.md#dans-quelle-transaction-) |
| Trois partis pris du journal d'audit | [Trois partis pris](../README.md#trois-partis-pris) |
| Anti-harcèlement par contrainte d'unicité | [Ce qui empêche le harcèlement](../README.md#ce-qui-empêche-le-harcèlement) |

---

## DEC-101 — La feuille de route se classe par ce qui se démontre

* **Date :** 2026-09-09
* **Contexte :** projet de démonstration technique orienté FinTech, destiné à être montré, pas exploité.
* **Décision :** ordonner les travaux par **valeur démontrable par heure investie** — déploiement,
  sandbox MoMo réel, durcissement auth d'abord ; le rapprochement ensuite, parce que c'est lui qui
  distingue vraiment sur le sujet Mobile Money.
* **Conséquence :** les 9 étapes sont terminées. Un travail qui n'améliore pas la démonstration ou la
  crédibilité technique passe après.
* **Statut :** active

## DEC-102 — Rien de personnel dans ce dépôt public

* **Date :** 2026-09-23
* **Contexte :** l'auto-mémoire locale du projet contient 6 entrées, dont **4 strictement personnelles**,
  sans aucun rapport avec le code.
* **Problème :** la mise sous système de règles prévoit de versionner l'état du projet. Le dépôt `taf`
  est **public**.
* **Règles en présence :** sécurité et vie privée (niveau **1** de `PRESERVATION.md` §6) **vs**
  préférence d'organisation documentaire (niveau 6).
* **Décision :** seules les **2 mémoires techniques** ont été consolidées ici. Les 4 autres restent en
  mémoire locale, hors de tout dépôt, et n'y entreront jamais. Leur contenu n'est pas décrit ici.
* **Conséquence :** `autoMemoryDirectory` n'est **pas** redirigé pour ce projet.
* **Statut :** active — conforme à la consigne utilisateur du 2026-09-23

## DEC-103 — Le README reste la documentation de référence

* **Date :** 2026-09-23
* **Contexte :** la structure standard prévoit `PROJECT_OVERVIEW`, `ARCHITECTURE`, `ROADMAP`,
  `TEST_PLAN`, `DEPLOYMENT`, `SECURITY`, `CHANGELOG`. Le `README.md` (835 lignes) couvre **déjà**
  tous ces rôles, en prose, et cette prose fait partie de la valeur du projet.
* **Décision :** ces fichiers **ne sont pas créés**. Le README est référencé
  ([`DOCUMENT_MAP.md`](DOCUMENT_MAP.md)) et mis à jour à sa place. Seuls `PROJECT_STATE.md`,
  `BACKLOG.md`, `DECISIONS.md` et `DOCUMENT_MAP.md` sont ajoutés — ils comblent un manque réel.
* **Raison :** `PRESERVATION.md` §2 — ne jamais écraser ni dupliquer pour « normaliser ». Créer sept
  fichiers redondants aurait dégradé le projet, pas amélioré son suivi.
* **Conséquence :** un fait documenté dans le README se corrige **dans le README**, jamais par un
  document parallèle qui divergerait.
* **Statut :** active
