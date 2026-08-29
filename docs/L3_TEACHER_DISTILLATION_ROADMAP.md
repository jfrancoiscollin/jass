# L3 — Teacher distillation roadmap

> **Mis à jour : 29 août 2026**
> **Statut : campagne T3 deep-fresh terminée. Aucun next stage autorisé.**
>
> Situation détaillée : [`L3_CURRENT.md`](L3_CURRENT.md). Prereg T3 : [`experiments/L3_T3_RF1_JOINT_AB_V1_20260829.md`](experiments/L3_T3_RF1_JOINT_AB_V1_20260829.md), merge `17a80ac8ca83cc1fc098a95ef6c0d5613ca9f5cb`.

---

## 1. Verdict qui clôt la campagne

```text
F6_TRANSFER_ESTABLISHED_D1_NOT_ADDITIVE
```

Le support est entièrement établi. La roadmap obtient deux réponses distinctes :

1. `F6_ONLY` transfère les 66 observables confirmées par RF1 vers un student résiduel T0 sur un nouveau q200 deep-fresh : `A_TRANSFER_PASS = true`.
2. Ajouter exactement le scalaire D1 scellé aux mêmes 66 entrées ne fournit pas d'effet additif reproductible : `B_ADDITIVE_PASS = false`.

Le second point est un résultat scientifique négatif. Ce n'est ni une panne technique ni un support insuffisant.

---

## 2. Chaîne de preuve RF1 → T3

RF1 avait confirmé `F6_ALL_NEW`, concaténation fixe des familles :

- F1 capture geometry ;
- F2 response frontier ;
- F3 promotion race ;
- F4 structure graph ;
- F5 king geometry plus.

Référence terminale RF1 : `cpx62-1635e-l3-residual-feature-fresh-readout-v5`, attempt `20260829T062056Z-e5c4a0d6`, verdict `RESIDUAL_FEATURE_FAMILY_CONFIRMED`.

L'effet RF1−D1 avait été reproduit sur fresh. T3 a ensuite gelé un vrai test de transfert avant toute nouvelle génération fresh :

- T3-A : F6 uniquement, `66 -> 256 -> 128 -> 64 -> 1` ;
- T3-B : F6 + un scalaire D1 scellé, `67 -> 256 -> 128 -> 64 -> 1` ;
- même T0 immuable, même learner, mêmes paires et mêmes règles d'optimisation ;
- code scientifique `bbb2bfe460ece89bef0ec30e2d52ed4b0ff847ea` ;
- 80 epochs exacts, aucun sweep, retune, early stopping ou model selection.

Artefacts :

- T0 `319d174f4b548b1655aad4bb30d4c6dc86c08dd715c9c23f8b19ba1937dc0be1` ;
- D1 `e91a55500713154f50be74db5d699b64d7684e1c078725d09e1d15e713549b49` ;
- RF1 `0d26ba50b668160b3da3e247cd4e1bd709c2cb7989b3b5877b9ea7deb34db58b` ;
- T3-A `16e5db8fd78849bba12b158eee5c1da4ab170129d8aeac1b91ab7a40ad9d0bb2` ;
- T3-B `227e954bbe98412594641be255c7edd5f69261aaf7fca4092537ef66f6cf668f`.

---

## 3. Exécution immuable

| Étape | Job / attempt |
|---|---|
| Preflight PASS | `cpx62-1636g-l3-t3-rf1-joint-ab-prereg-v4` / `20260829T081356Z-bbb2bfe4` |
| Train/freeze | `cpx62-1637-l3-t3-rf1-joint-ab-train-freeze-v1` / `20260829T082456Z-bbb2bfe4` |
| Fresh target-blind | `cpx62-1638-l3-t3-rf1-joint-ab-fresh-select-v1` / `20260829T084038Z-bbb2bfe4` |
| Teacher q1000/q50/q200 | `cpx62-1639-l3-t3-rf1-joint-ab-fresh-teacher-v1` / `20260829T085626Z-bbb2bfe4` |
| Readout terminal | `cpx62-1640-l3-t3-rf1-joint-ab-terminal-readout-v1` / `20260829T090656Z-bbb2bfe4` |

La cohorte sélectionnée contient exactement `8000` parents, `2000` par phase, sous SHA256 `5e9f80cf2c5a720b4b6d6c377954f289f0f4c48c016d926b60925d0e9636271b`. Elle a été commit/hashée avant toute lecture de T0, D1, A, B, q1000, q50 ou q200.

Le teacher a produit `75672` siblings avec book OFF, un thread et un Engine/TT/search state frais pour chaque sibling et chaque budget.

---

## 4. Support terminal

Support PASS :

- `8000` sélectionnés ;
- `6800` parents acceptés ;
- `193681` paires stables ;
- P0/P1/P2/P3 = `1783 / 1860 / 1877 / 1280` ;
- black/white = `3490 / 3310` ;
- paires stables dans les huit cellules phase×couleur ;
- zero forbidden overlap ;
- A/B/T0/D1 inchangés, replays A+B exacts, ordre F6 gardé ;
- zéro post-freeze fit/refit/calibration ;
- zéro selfplay, strength, runtime-Elo, bake ou promotion.

---

## 5. Résultat quantitatif

| Modèle | Pairwise q200 | Top-hit |
|---|---:|---:|
| T0 | 0.6082147602 | 0.5540686275 |
| D1 | 0.7334794258 | 0.6492647059 |
| T3-A `F6_ONLY` | **0.7831693588** | 0.6836764706 |
| T3-B `JOINT_D1_F6` | 0.7782264240 | **0.6883823529** |
| q1000 diagnostic | 0.9361726862 | 0.8587521008 |

Bootstrap parent-cluster `200000`, seed `2026090811` :

- A−T0 pairwise `+0.1749545986`, CI95 `[+0.1694074710 ; +0.1804750871]` ;
- A−T0 top-hit `+0.1296078431`, CI95 `[+0.1179411765 ; +0.1412990196]` ;
- B−A pairwise `-0.0049429348`, CI95 `[-0.0083936669 ; -0.0014982551]` ;
- B−A top-hit `+0.0047058824`, CI95 `[-0.0050000000 ; +0.0142647059]` ;
- A−D1 pairwise diagnostic `+0.0496899330`, CI95 `[+0.0442287889 ; +0.0551209779]` ;
- B−D1 pairwise diagnostic `+0.0447469982`, CI95 `[+0.0391807145 ; +0.0503087758]` ;
- B−T0 pairwise diagnostic `+0.1700116638`, CI95 `[+0.1644246591 ; +0.1756007159]` ;
- q1000−B pairwise headroom `+0.1579462622`, CI95 `[+0.1532519624 ; +0.1626770490]`.

A−T0 est pairwise positif dans P0/P1/P2/P3 et dans les deux couleurs. B−A est pairwise négatif dans P0/P1/P2/P3 et dans les deux couleurs.

---

## 6. Lecture scientifique

### Ce qui est établi

Les observables F6 ne sont pas seulement corrélées au teacher dans le screen RF1. Un MLP résiduel gelé, entraîné uniquement sur l'historique autorisé, les transfère avec un gain fresh massif et homogène sur T0. La feature-discovery RF1 a donc produit une représentation réellement transférable.

T3-A dépasse aussi D1 de `+4.969 pp` pairwise en diagnostic, avec CI95 strictement positive. Cette comparaison secondaire renforce l'intérêt offline de F6 mais ne remplace pas le gate primaire A−T0.

### Ce qui n'est pas établi

Le D1 scellé n'est pas additif au-dessus de F6 dans le bras joint exact. B reste bien au-dessus de D1 et T0, mais il est pairwise inférieur à A de façon statistiquement établie et uniforme par phase/couleur. Son petit gain top-hit ponctuel ne passe pas la CI95 preregistrée et ne peut pas sauver le gate.

Le protocole ne permet pas de choisir post-hoc entre explications possibles — redondance de D1, interaction de normalisation/optimisation ou inductive bias du bras joint. Les départager demanderait une nouvelle preregistration et un nouveau fresh ; aucun de ces tests n'est lancé ici.

---

## 7. Branches fermées et données consommées

La preregistration ferme explicitement :

- tout troisième bras ;
- tout retrait de F2 ou compression des 66 features ;
- tout changement d'architecture, seed, optimizer, poids de cellules ou budget teacher ;
- tout retune/calibration après lecture fresh ;
- toute réutilisation de la cohorte 1638/1639/1640 pour fit, tuning, feature selection ou model selection ;
- toute tentative de sauver B−A avec B−D1, B−T0, q1000 ou une métrique secondaire.

Q1, T2 fresh, RF1 fresh et T3 fresh restent des cohorts consommés selon leurs contrats respectifs.

---

## 8. Frontière de la roadmap

T3 établit un résultat offline de ranking sibling. Il ne prouve pas qu'un artefact est un leaf evaluator transposition-invariant, qu'il accélère la recherche ou qu'il gagne des Elo.

Une éventuelle suite future devrait être une campagne séparée avec nouvelle preregistration et nouvelles données. Deux questions resteraient alors ouvertes, sans être autorisées par ce document :

1. comment transformer le signal F6 transféré en composant de production transposition-invariant ;
2. pourquoi le scalaire D1 dégrade le pairwise du bras joint alors que D1 seul porte un signal fort.

Ces questions ne déclenchent aucun job dans la campagne présente.

---

## 9. Règles terminales

1. `CURRICULUM` reste champion de production.
2. `F6_TRANSFER_ESTABLISHED_D1_NOT_ADDITIVE` est le verdict scientifique terminal T3.
3. Aucune métrique secondaire ne transforme B−A en PASS.
4. Aucun retune ni nouveau fresh T3 n'est autorisé.
5. Aucun runtime, Elo, strength, selfplay, bake ou promotion n'a été exécuté ou autorisé.
6. `next_stage = null` pour cette campagne.

La roadmap T3 s'arrête au verdict deep-fresh.
