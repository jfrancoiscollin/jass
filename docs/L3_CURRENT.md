# L3 — état courant et registre de décision

> **Mis à jour : 29 août 2026**
> **Source de vérité active : ce document.**
>
> Roadmap : [`L3_TEACHER_DISTILLATION_ROADMAP.md`](L3_TEACHER_DISTILLATION_ROADMAP.md). Protocole terminal T3 : [`experiments/L3_T3_RF1_JOINT_AB_V1_20260829.md`](experiments/L3_T3_RF1_JOINT_AB_V1_20260829.md). Runtime : [prereg v3](experiments/L3_T3_F6_RUNTIME_STRENGTH_V3_20260829.md), [résultat terminal v3](experiments/L3_T3_F6_RUNTIME_STRENGTH_V3_RESULTS_20260829.md), [autopsie negamax](experiments/L3_T3_F6_NEGAMAX_AUTOPSY_20260829.md), [terminal v2](experiments/L3_T3_F6_RUNTIME_STRENGTH_V2_RESULTS_20260829.md) et [terminal v1](experiments/L3_T3_F6_RUNTIME_STRENGTH_V1_RESULTS_20260829.md).

---

## 1. Champion de production

### `CURRICULUM` — champion courant inchangé

Aucun candidat T3 n'est promu. L'implémentation runtime T3-A reste dormante par défaut ; sa campagne s'arrête au gate R0 avant toute partie Elo/strength, bake ou promotion.

- T0/CURRICULUM raw SHA256 : `319d174f4b548b1655aad4bb30d4c6dc86c08dd715c9c23f8b19ba1937dc0be1` ;
- D1 scellé SHA256 : `e91a55500713154f50be74db5d699b64d7684e1c078725d09e1d15e713549b49` ;
- RF1/F6 SHA256 : `0d26ba50b668160b3da3e247cd4e1bd709c2cb7989b3b5877b9ea7deb34db58b` ;
- T3-A `F6_ONLY` SHA256 : `16e5db8fd78849bba12b158eee5c1da4ab170129d8aeac1b91ab7a40ad9d0bb2` ;
- T3-B `JOINT_D1_F6` SHA256 : `227e954bbe98412594641be255c7edd5f69261aaf7fca4092537ef66f6cf668f`.

T3-A et T3-B sont des artefacts scientifiques frozen, pas des réseaux de production.

### Gate runtime T3-A — R0-v3 terminal sur support mécanique

V3 a été preregistrée après l'autopsie et a corrigé le contrat leaf sans
modifier T3-A, CURRICULUM, F6 ou le search. Son verdict exact est :

```text
R0_V3_RUNTIME_SUPPORT_INCONCLUSIVE
```

Sur `120000` candidates classifiées mécaniquement avant toute lecture
T0/T3/parité/runtime, `119699` identités restent uniques après exclusions,
avec overlap interdit `0` et reads score/WDL/deep/runtime `0/0/0/0`. P0 offre
`26004` positions uniques mais seulement `5` témoins leaf isolés, contre `32`
prerequis. Le sélecteur s'est arrêté fail-closed avant de constituer les `4096`
positions et avant les gates 1–8. Parité v3, coût runtime, Pool1, Pool2, Q00 et
chained n'ont donc pas été exécutés ; strength games `0`.

R0 `cpx62-1652` / `20260829T152726Z-880fccbe`, readout `cpx62-1653` /
`20260829T153756Z-880fccbe`, code `880fccbec5929588e4e4120a2cf81ce5067bcd71`,
tous deux completed exit `0`. Ce terminal est un support insuffisant de la
recette v3, pas un défaut T3-A et pas un résultat Elo.

### Historique immuable v1/v2 et autopsie

Le terminal v1 reste immuable. La nouvelle campagne v2 a établi que T3-A
n'ajoute aucun drift de couleur au baseline, puis s'est arrêtée au gate
negamax depth-1. Son readout exact est :

```text
R0_V2_NEGAMAX_OR_TERMINAL_PRECEDENCE_FAILED
```

Sur `4096` positions target-blind, position/transposition, F6/résiduel et drift
relatif passent. T0 et T3 ont exactement la même distribution de drift :
moyenne `5.02734375 cp`, p50/p95/p99 `5/11/19.05`, max `40`, `3871`
positions non nulles. Extra drift engine : mismatch `0`, max `0 cp`; extra
float max `1.1368683772161603e-13 cp` pour une tolérance gelée `1e-10`.

Les priorités terminale et EGDB passent. Le seul FAIL est
`negamax_single_inversion=false` au témoin depth-1, score search `-51`. Le
contrat de production leaf v2 n'est donc pas entièrement établi. L'autopsie
post-terminale a maintenant localisé exactement ce FAIL :

```text
QUIESCENCE_OR_DEPTH_SEMANTICS_EXPLAINS_MISMATCH
```

T0 échoue lui aussi au témoin direct (`max(-T0_child)=0`, search d1 `-1`) ; T3
donne `+85` direct contre `-51` search. Les `9` children sont sans capture,
menace, terminal ou TB, mais génèrent chacun `1–2` sacrifices sélectifs de
quiescence. La première divergence des deux bras se situe à
`qsearch_selective_sac`. T0 diverge sur `1/9` child et T3 sur `9/9`. La formule
native/POV T3 est exacte sur `9/9` (`0` mismatch) et deux contrôles leaf
réellement isolés passent exactement avec T0 et T3. Le FAIL n'est donc pas un
défaut d'intégration T3 ; `search(depth=1)` ne correspond pas à
`max(-eval(child))` sous les paramètres de production.

Conséquence fail-closed : Pool1 et Pool2 ne sont pas autorisés, aucune partie
native ou Q00 n'a été jouée, et la question du transfert en Elo reste
indéterminée. Aucun refit, retune, calibration, bake ou promotion n'a eu lieu.
Chaîne v2 : R0 `cpx62-1648` / `20260829T132226Z-f559baed`, puis readout
terminal `cpx62-1649` / `20260829T133232Z-f559baed`, code
`f559baede4047f47abe13724b16d1ad669c5f36f`. La chaîne v1 `1644→1647`
reste un résultat terminal antérieur distinct. Autopsie : Jass PR `#707`, code
`2a4d151956eab0c74674b812ca75bb2d6386d875`, job `cpx62-1650` attempt
`20260829T141312Z-2a4d1519`, readout `cpx62-1651` attempt
`20260829T142315Z-2a4d1519`, tous deux exit `0`.

V3 a ensuite été ouverte séparément et s'est fermée sur le déficit de support
décrit ci-dessus. Aucun ancien verdict n'est réinterprété.

---

## 2. Verdict scientifique terminal

Le support preregistré est entièrement établi. Le verdict exact est :

```text
F6_TRANSFER_ESTABLISHED_D1_NOT_ADDITIVE
```

Les deux questions causales sont tranchées :

1. **Oui, les 66 features F6 confirmées dans RF1 se transfèrent.** T3-A bat T0 en pairwise et top-hit avec des CI95 strictement positives, dans P0/P1/P2/P3 et pour les deux couleurs.
2. **Non, D1 n'apporte pas de signal additif reproductible au-dessus de F6 dans le bras joint preregistré.** T3-B perd `0.4943 pp` pairwise contre T3-A ; la CI95 pairwise est entièrement négative et la CI95 top-hit traverse zéro. B−A est pairwise négatif dans les quatre phases et les deux couleurs.

Ce deuxième résultat est un verdict scientifique négatif, pas une panne technique et pas un défaut de support. Il porte sur l'ajout exact du scalaire D1 scellé au student joint gelé ; il ne constitue ni un test runtime ni une conclusion générale sur toute autre architecture future.

---

## 3. Preregistration, code et contrats immuables

- upstream RF1 terminal : `cpx62-1635e-l3-residual-feature-fresh-readout-v5`, attempt `20260829T062056Z-e5c4a0d6`, verdict `RESIDUAL_FEATURE_FAMILY_CONFIRMED`, winner `F6_ALL_NEW` ;
- prereg Jass PR `#689`, merge `17a80ac8ca83cc1fc098a95ef6c0d5613ca9f5cb` ;
- implementation Jass PR `#690`, merge/code scientifique `bbb2bfe460ece89bef0ec30e2d52ed4b0ff847ea` ;
- outil principal `jobs/tools/t3_rf1_joint_ab.py` ;
- ordre F6 SHA256 `cc4837e6829d937f7330f7bc71280f3ec0bed3f431e57b2664c651e1d763db4e` ;
- sélection seed `2026090810`, génération seed base `2026090820` ;
- bootstrap parent-cluster `200000`, seed `2026090811`.

Les bras sont restés exactement ceux de la preregistration :

- A : `66 -> 256 -> 128 -> 64 -> 1`, inputs F6 uniquement ;
- B : `67 -> 256 -> 128 -> 64 -> 1`, mêmes 66 inputs F6 plus un unique scalaire D1 scellé ;
- coefficient T0 immuable, réseau partagé entre phases et couleurs ;
- Adam NumPy déterministe, batch `4096`, exactement `80` epochs, aucun early stopping, sweep, retune ou sélection de checkpoint.

---

## 4. Chaîne terminale exécutée

| Étape | Job | Attempt | État / verdict |
|---|---|---|---|
| Preflight | `cpx62-1636g-l3-t3-rf1-joint-ab-prereg-v4` | `20260829T081356Z-bbb2bfe4` | exit `0`, `JASS_T3_RF1_JOINT_AB_PREREGISTERED` |
| Train/freeze A+B | `cpx62-1637-l3-t3-rf1-joint-ab-train-freeze-v1` | `20260829T082456Z-bbb2bfe4` | exit `0`, `T3_RF1_JOINT_AB_FROZEN` |
| Fresh selection | `cpx62-1638-l3-t3-rf1-joint-ab-fresh-select-v1` | `20260829T084038Z-bbb2bfe4` | exit `0`, `T3_FRESH_SELECTION_READY` |
| Fresh teacher | `cpx62-1639-l3-t3-rf1-joint-ab-fresh-teacher-v1` | `20260829T085626Z-bbb2bfe4` | exit `0`, `T3_FRESH_TEACHER_READY` |
| Readout terminal | `cpx62-1640-l3-t3-rf1-joint-ab-terminal-readout-v1` | `20260829T090656Z-bbb2bfe4` | exit `0`, verdict terminal |

Le readout a été mis en queue par jass-control PR `#361`, merge `39d845cce876749d0545dff900fb18d88206a6b4`.

### Incidents techniques antérieurs

Les échecs `1636/1636b/1636e` étaient exclusivement techniques : contrat d'authentification upstream puis absence de `pytest` dans le venv numérique. Les diagnostics `1636d` (`20260829T073049Z-bbb2bfe4`) et `1636f` (`20260829T080256Z-bbb2bfe4`) ont confirmé zéro fit T3, zéro fresh label/score et zéro activité runtime. Ils n'ont jamais été interprétés comme des résultats scientifiques.

---

## 5. Train/freeze A+B

Le fit autorisé utilise uniquement l'union historique A/B/C, avec priorité canonique A > B > C :

| Source | Sélection | Teacher |
|---|---|---|
| A | `cpx62-1570-l3-deep-sibling-selection-v2` / `20260826T104456Z-1493d426` | `cpx62-1574-l3-deep-sibling-teacher-v2` / `20260826T185527Z-a6da4a0b` |
| B | `cpx62-1578-l3-deep-sibling-phase-b-fresh-v2` / `20260826T203927Z-87475360` | `cpx62-1579-l3-deep-sibling-phase-b-teacher-v1` / `20260826T210539Z-87475360` |
| C | `cpx62-1587-l3-rich-d-r1-phase-c-select-v2` / `20260827T074201Z-fff1f716` | `cpx62-1588-l3-rich-d-r1-phase-c-teacher-v1` / `20260827T084459Z-fff1f716` |

- `18000` parents retenus ;
- `169045` lignes sibling ;
- `15373` parents avec paires stables ;
- `434323` paires stables avant caps ;
- `80` epochs exacts pour chacun des deux bras ;
- replay déterministe exact ;
- aucun read de labels/scores/métriques Q1, T2 fresh ou RF1 fresh.

Paires historiques par cellule phase×couleur :

| Cellule | Paires |
|---|---:|
| P0 black | 57574 |
| P0 white | 57528 |
| P1 black | 67711 |
| P1 white | 65289 |
| P2 black | 59820 |
| P2 white | 60689 |
| P3 black | 33963 |
| P3 white | 31749 |

Les deux artefacts ont été sérialisés simultanément avant toute nouvelle génération fresh.

---

## 6. Nouveau fresh target-blind et teacher

### Sélection 1638

- exactement `8000` parents, `2000` dans chacune des phases P0/P1/P2/P3 ;
- legal moves `2..16`, canonical de-dup exact plus rotate180/colour-swap ;
- sélection commit/hashée avant tout score T0/D1/A/B/q1000/q50/q200 ;
- selected JNNW SHA256 `5e9f80cf2c5a720b4b6d6c377954f289f0f4c48c016d926b60925d0e9636271b` ;
- selected TSV SHA256 `20e9df4d23c12c050c04a1e122ac05dc7609724005f878b247abb5c9d630828d` ;
- zero forbidden overlap ;
- aucun score ou label fresh lu pendant la sélection.

### Teacher 1639

- `75672` siblings ;
- `75672` recherches à chacun des budgets q1000/q50/q200 ;
- q1000 `1000` nodes, diagnostic uniquement ; q50 `50000` ; q200 `200000` target ;
- book OFF, un thread/search, Engine/TT/search state frais par sibling et budget ;
- aucun fit/refit/calibration post-freeze.

---

## 7. Support gate — PASS complet

- sélectionnés : `8000` ;
- parents acceptés : `6800` ;
- paires stables : `193681` ;
- P0/P1/P2/P3 acceptés : `1783 / 1860 / 1877 / 1280` ;
- black/white : `3490 / 3310` ;
- paire stable dans chacune des huit cellules phase×couleur ;
- zero forbidden overlap ;
- bytes A/B/T0/D1 inchangés ;
- replay A+B déterministe ;
- guard extracteur/ordre F6 ;
- zéro fit/refit/calibration post-freeze ;
- zéro selfplay, strength, runtime-Elo, bake ou promotion.

Paires stables terminales par cellule :

| Cellule | Paires |
|---|---:|
| P0 black | 27304 |
| P0 white | 26083 |
| P1 black | 31337 |
| P1 white | 29223 |
| P2 black | 26813 |
| P2 white | 25104 |
| P3 black | 13806 |
| P3 white | 14011 |

---

## 8. Métriques terminales communes

Toutes les métriques utilisent exactement les mêmes `6800` parents acceptés et `193681` paires stables.

| Modèle | Pairwise q200 | Top-hit |
|---|---:|---:|
| T0 | `0.6082147602129492` | `0.5540686274509804` |
| D1 | `0.7334794257874955` | `0.6492647058823530` |
| T3-A `F6_ONLY` | **`0.7831693588009130`** | `0.6836764705882353` |
| T3-B `JOINT_D1_F6` | `0.7782264239676245` | **`0.6883823529411764`** |
| q1000 diagnostic | `0.9361726861780656` | `0.8587521008403362` |

Le léger avantage top-hit ponctuel de B sur A ne sauve pas B : sa CI95 top-hit traverse zéro et son effet pairwise primaire est significativement négatif.

---

## 9. Deltas bootstrap preregistrés

Bootstrap parent-cluster `200000`, seed `2026090811`, CI95 percentile.

| Delta | Pairwise mean | CI95 pairwise | Top-hit mean | CI95 top-hit |
|---|---:|---:|---:|---:|
| A−T0 **primaire** | `+0.17495459858796386` | `[+0.16940747096694114 ; +0.18047508706277157]` | `+0.12960784313725490` | `[+0.11794117647058823 ; +0.14129901960784316]` |
| B−A **primaire conditionnel** | `-0.004942934833288572` | `[-0.008393666858675503 ; -0.0014982551019841386]` | `+0.004705882352941176` | `[-0.005000000000000000 ; +0.014264705882352941]` |
| A−D1 diagnostic | `+0.04968993301341747` | `[+0.04422878890126350 ; +0.05512097787563297]` | `+0.03441176470588235` | `[+0.021911764705882353 ; +0.046911764705882354]` |
| B−D1 diagnostic | `+0.04474699818012890` | `[+0.03918071454852676 ; +0.050308775759998155]` | `+0.03911764705882353` | `[+0.02661764705882353 ; +0.05161764705882353]` |
| B−T0 diagnostic | `+0.17001166375467525` | `[+0.16442465912236476 ; +0.17560071592197093]` | `+0.13431372549019607` | `[+0.12254901960784315 ; +0.14607843137254906]` |
| q1000−B diagnostic | `+0.15794626221044110` | `[+0.15325196236700175 ; +0.16267704896782212]` | `+0.17036974789915962` | `[+0.15864705882352945 ; +0.18205882352941177]` |

---

## 10. Phases et couleurs

### Pairwise par phase

| Phase | Parents | T0 | D1 | T3-A | T3-B | q1000 | A−T0 | B−A |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| P0 | 1783 | 0.6953492604 | 0.7662570337 | 0.8324988741 | 0.8294810954 | 0.9808649126 | +0.1371496138 | -0.0030177787 |
| P1 | 1860 | 0.6065044694 | 0.7629237350 | 0.7962857041 | 0.7899040213 | 0.9577563446 | +0.1897812347 | -0.0063816827 |
| P2 | 1877 | 0.5558014791 | 0.7027281069 | 0.7456824911 | 0.7414690417 | 0.9028268331 | +0.1898810119 | -0.0042134494 |
| P3 | 1280 | 0.5661835538 | 0.6901289067 | 0.7503661734 | 0.7437625148 | 0.8914526250 | +0.1841826196 | -0.0066036586 |

### Top-hit par phase

| Phase | T0 | D1 | T3-A | T3-B | q1000 |
|---|---:|---:|---:|---:|---:|
| P0 | 0.7337820153 | 0.8569826136 | 0.8491306786 | 0.8424004487 | 0.9634511124 |
| P1 | 0.5758960573 | 0.7075268817 | 0.7086021505 | 0.7182795699 | 0.9102150538 |
| P2 | 0.4111170307 | 0.4837506660 | 0.5460841769 | 0.5588705381 | 0.7575031078 |
| P3 | 0.4816406250 | 0.5179687500 | 0.6187500000 | 0.6203125000 | 0.7865997024 |

### Couleurs originales

| Couleur | Parents | T0 pair/top | D1 pair/top | T3-A pair/top | T3-B pair/top | q1000 pair/top | A−T0 pair | B−A pair |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| black | 3490 | 0.6076860122 / 0.5558739255 | 0.7329630860 / 0.6467048711 | 0.7835092231 / 0.6848137536 | 0.7774780567 / 0.6914040115 | 0.9371489940 / 0.8550757266 | +0.1758232109 | -0.0060311664 |
| white | 3310 | 0.6087722619 / 0.5521651561 | 0.7340238445 / 0.6519637462 | 0.7828110124 / 0.6824773414 | 0.7790154880 / 0.6851963746 | 0.9351432861 / 0.8626283988 | +0.1740387505 | -0.0037955245 |

A−T0 est pairwise positif partout. B−A est pairwise négatif partout.

---

## 11. Gates primaires

### `A_TRANSFER_PASS = true`

- A−T0 pairwise CI95 low > 0 : PASS ;
- A−T0 top-hit CI95 low > 0 : PASS ;
- A−T0 pairwise positif en P0/P1/P2/P3 : PASS ;
- A−T0 pairwise positif black et white : PASS ;
- replay/forbidden-input guards : PASS.

### `B_ADDITIVE_PASS = false`

- B−A pairwise CI95 low > 0 : FAIL, CI entièrement négative ;
- B−A top-hit CI95 low > 0 : FAIL, CI traversant zéro ;
- B−A pairwise positif en P0/P1/P2/P3 : FAIL dans les quatre phases ;
- B−A pairwise positif black et white : FAIL dans les deux couleurs ;
- replay/D1 identity/forbidden-input guards : PASS.

Les métriques secondaires B−D1, B−T0 et q1000−B ne peuvent pas sauver l'échec primaire B−A.

---

## 12. Décision et règles verrouillées

```text
F6 transfer = ESTABLISHED
D1 additive above F6 = NOT ESTABLISHED
terminal verdict = F6_TRANSFER_ESTABLISHED_D1_NOT_ADDITIVE
```

Conséquences :

1. RF1 puis T3 établissent une chaîne reproductible découverte → confirmation fresh → transfert des 66 observables F6.
2. Le bras joint exact n'autorise aucun retune ni troisième bras sur ce fresh consommé.
3. La cohorte 1638/1639/1640 est consommée et interdite à tout fit, tuning, calibration, feature selection ou model selection.
4. Les campagnes runtime v1/v2/v3 ont toutes terminé avant force ; aucune partie Elo/strength/Q00, aucun selfplay, bake ou promotion n'a été exécuté ou autorisé.
5. Le drift relatif est établi par v2 et l'autopsie exclut un défaut POV T3 démontré. V3 reste inconclusive faute de support mécanique (`5/32` témoins P0), avant ses gates d'évaluation.
6. Toute nouvelle recette de témoins isolés exige une preregistration séparée ; aucun relâchement post-hoc de v3 n'est permis.

La campagne T3 s'arrête ici.
