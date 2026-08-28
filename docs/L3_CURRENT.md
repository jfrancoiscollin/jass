# L3 — état courant et registre de décision

> **Mis à jour : 28 août 2026**
> **Source de vérité active : ce document.**
>
> Roadmap active : [`L3_TEACHER_DISTILLATION_ROADMAP.md`](L3_TEACHER_DISTILLATION_ROADMAP.md). Protocole terminal T2 : [`experiments/L3_T2_PHASE_SPECIALIST_DEEP_FRESH_V1_20260828.md`](experiments/L3_T2_PHASE_SPECIALIST_DEEP_FRESH_V1_20260828.md), merge SHA `53f8d84991c8a69b690e7a2534fd290bbaad073f`.

---

## 1. Champion de production

### `CURRICULUM` — champion courant

Aucun candidat post-CURRICULUM n'est promu.

- raw/decompressed `.pjtw` SHA256 : `319d174f4b548b1655aad4bb30d4c6dc86c08dd715c9c23f8b19ba1937dc0be1` ;
- D1 scellé SHA256 : `e91a55500713154f50be74db5d699b64d7684e1c078725d09e1d15e713549b49` ;
- Rich-D historique SHA256 : `2b8b9672307c0a84b0baaaccbd4a9aff117223c706290e2dd648ef2e42083bb2` ;
- T2 phase-specialist frozen SHA256 : `80de2d003c139c0fd8371e17175889a31f97792c5fd042a2a7338ca9dbc83c4d`.

La campagne T2 s'arrête avant runtime, Elo, strength, bake et promotion.

---

## 2. Conclusion scientifique actuelle

La campagne preregistrée T2 phase-specialist est **terminale**.

Verdict exact :

```text
T2_PHASE_SPECIALIST_DEEP_SIGNAL_NOT_ESTABLISHED
```

Le support deep-fresh est pleinement établi, mais T2 ne dépasse pas D1 sur le critère primaire q200. T2 améliore très fortement T0, mais reste significativement sous D1 et même sous Rich-D en pairwise global.

La conclusion principale est donc : **ajouter le plateau brut et une spécialisation dure par phase à un student state-only ne suffit pas à absorber le signal de q1000 de manière à dépasser D1 sur q200 fresh**.

Le résultat est informatif :

1. T2 bat T0 de `+9.279 pp` pairwise avec CI95 strictement positive ;
2. T2 perd contre D1 de `-3.203 pp` pairwise avec CI95 entièrement négative ;
3. T2 ne bat D1 qu'en P0 ; P1/P2/P3 sont négatives ;
4. les deux couleurs originales sont négatives contre D1 ;
5. q1000 reste à `0.93741` pairwise, soit environ `+23.56 pp` de headroom au-dessus de T2 ;
6. le problème n'est donc pas l'absence de signal teacher, mais sa distillation statique/généralisation.

---

## 3. Prereg, implementation et freeze immuables

Prereg merge SHA : `53f8d84991c8a69b690e7a2534fd290bbaad073f`.

Jass code SHA utilisé par les jobs T2 :

`a3ba045facccd9bcbd01e9c872c045ac7c899f66`.

### 1626 — prereg/source-auth/tests

- job `cpx62-1626-l3-t2-phase-specialist-prereg-v1` ;
- attempt `20260828T164545Z-a3ba045f` ;
- implementation T2-PMoE déterministe validée avant training/fresh.

### 1627 — train/freeze

- job `cpx62-1627-l3-t2-phase-specialist-train-freeze-v1` ;
- attempt `20260828T165619Z-a3ba045f` ;
- verdict `T2_PHASE_SPECIALIST_FROZEN` ;
- T2 SHA256 `80de2d003c139c0fd8371e17175889a31f97792c5fd042a2a7338ca9dbc83c4d` ;
- `434323` paires train, `169045` lignes ;
- architecture `326 -> 256 -> 128`, quatre heads `128 -> 64 -> 1` ;
- Q1 label reads = `0`, Q1 score reads = `0` ;
- fresh labels = `0` avant freeze ;
- strength/runtime/promotion = `0`.

Comptes de paires train par cellule phase×couleur :

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

---

## 4. 1628c — cohort deep fresh immuable

Après deux échecs purement techniques de wrappers, la sélection self-contained finale est :

- job `cpx62-1628c-l3-t2-phase-specialist-fresh-select-v3` ;
- attempt `20260828T182726Z-a3ba045f` ;
- verdict `T2_PHASE_SPECIALIST_SELECTION_READY` ;
- selection seed `2026090610` ; source generation seed `2026090620` ;
- exactement `8000` parents : `2000` par P0/P1/P2/P3 ;
- target-blind `true` ;
- selected JNNW SHA256 `d1f9fc41e3cb2f738011f78acc82848d025a608d8656702297b170a4e12daad1` ;
- Q1 utilisé uniquement par identité canonique pour exclusion ; label/score reads Q1 = `0` ;
- teacher/T2/D1 score reads avant sélection = `0` ;
- assertion finale explicite : aucun parent sélectionné dans le blocklist canonique antérieur et aucun état exact dans les force pools.

Le cohort 1628c est désormais consommé et ne doit jamais servir à retuner T2 ni à sélectionner de nouvelles features/architectures.

---

## 5. 1629 — teacher deep fresh

- job `cpx62-1629-l3-t2-phase-specialist-teacher-v1` ;
- attempt `20260828T193226Z-a3ba045f` ;
- verdict `T2_PHASE_SPECIALIST_TEACHER_READY` ;
- `8000` parents, `76165` siblings émis ;
- q1000 exact `1000` nœuds, diagnostic uniquement ;
- q50 exact `50000` nœuds, stability screen ;
- q200 exact `200000` nœuds, target final ;
- book OFF, un thread/search, Engine/TT/search state frais par sibling et budget ;
- `76165` recherches à chacun des trois budgets ;
- aucun fit/refit/calibration post-freeze ;
- strength/runtime/Elo/promotion = `0`.

---

## 6. 1630 — support et readout terminal

- job `cpx62-1630-l3-t2-phase-specialist-readout-v1` ;
- attempt `20260828T194826Z-a3ba045f` ;
- control merge SHA `1a133fd0bbb7d74ef95f06c0f624a01ccca3137a` ;
- exit `0` ;
- bootstrap parent-cluster `200000`, seed `2026090611` ;
- verdict `T2_PHASE_SPECIALIST_DEEP_SIGNAL_NOT_ESTABLISHED`.

### Support gate — PASS complet

- sélectionnés : `8000` ;
- parents acceptés : `6799` ;
- stable pairs : `195036` ;
- P0/P1/P2/P3 acceptés : `1795 / 1885 / 1857 / 1262` ;
- black/white : `3461 / 3338` ;
- stable pair dans chaque cellule phase×couleur : PASS ;
- zero forbidden overlap : PASS ;
- T2 bytes unchanged : PASS ;
- zero post-freeze fit/refit/calibration : PASS.

Stable pairs par cellule :

| Cellule | Paires |
|---|---:|
| P0 black | 27335 |
| P0 white | 25192 |
| P1 black | 30162 |
| P1 white | 31047 |
| P2 black | 27925 |
| P2 white | 25582 |
| P3 black | 13795 |
| P3 white | 13998 |

---

## 7. Métriques q200 fresh terminales

Toutes les métriques utilisent exactement les mêmes `6799` parents acceptés et `195036` paires stables.

| Modèle | Pairwise q200 | Top-hit |
|---|---:|---:|
| T0 | `0.6090684076` | `0.5461342354` |
| D1 | **`0.7338846504`** | `0.6492131196` |
| Rich-D | `0.7317405703` | **`0.6608324754`** |
| T2 | `0.7018589740` | `0.6434769819` |
| q1000 | **`0.9374100334`** | **`0.8608741482`** |

### T2 vs D1 — gate primaire

Pairwise :

- delta mean `-0.0320256764` = **−3.203 pp** ;
- CI95 `[-0.0373919611 ; -0.0266215498]` ;
- `P(delta>0)=0`.

Top-hit :

- delta mean `-0.0057361377` = **−0.574 pp** ;
- CI95 `[-0.0173554935 ; +0.0058832181]` ;
- `P(delta>0)=0.16271`.

### T2 vs T0

Pairwise : mean `+0.0927905664`, CI95 `[+0.0863858115 ; +0.0992239313]`.

Top-hit : mean `+0.0973427465`, CI95 `[+0.0842770996 ; +0.1105309604]`.

### Diagnostics

T2−Rich-D pairwise : mean `-0.0298815962`, CI95 `[-0.0351834672 ; -0.0245653270]`.

q1000−T2 pairwise headroom : mean `+0.2355510594`, CI95 `[+0.2304987327 ; +0.2406365748]`.

q1000−T2 top-hit headroom : mean `+0.2173971662`, CI95 `[+0.2053610825 ; +0.2294209933]`.

---

## 8. Phase et couleur

### Pairwise T2−D1 par phase

- P0 : `+0.0186385392` ;
- P1 : `-0.0388096009` ;
- P2 : `-0.0592457989` ;
- P3 : `-0.0539011136`.

P0 est la seule phase positive.

### Pairwise T2−D1 par couleur originale

- black : `-0.0275639495` ;
- white : `-0.0366518108`.

Les deux couleurs échouent le gate de positivité.

### Détail par phase

| Phase | Parents | T0 pairwise | D1 | Rich-D | T2 | q1000 |
|---|---:|---:|---:|---:|---:|---:|
| P0 | 1795 | 0.7075495462 | 0.7716443513 | 0.8207026830 | 0.7902828905 | 0.9797421064 |
| P1 | 1885 | 0.6000528356 | 0.7547592250 | 0.7510310824 | 0.7159496242 | 0.9566205331 |
| P2 | 1857 | 0.5477782967 | 0.7085876943 | 0.6829193992 | 0.6493418954 | 0.9051518963 |
| P3 | 1262 | 0.5726472078 | 0.6862215849 | 0.6482313046 | 0.6323204713 | 0.8959722346 |

---

## 9. Gates primaires

PASS :

- support complet ;
- T2−T0 pairwise bootstrap CI95 low > 0 ;
- deterministic replay/inference contract ;
- forbidden-input contract.

FAIL :

- T2−D1 pairwise CI95 low > 0 ;
- T2−D1 top-hit CI95 low > 0 ;
- T2−D1 pairwise positif dans P0/P1/P2/P3 ;
- T2−D1 pairwise positif dans les deux couleurs.

Le verdict terminal est donc mécaniquement imposé par la prereg :

```text
T2_PHASE_SPECIALIST_DEEP_SIGNAL_NOT_ESTABLISHED
```

---

## 10. Décision et règles verrouillées

```text
T2 deep-fresh signal = NOT ESTABLISHED
Runtime/Elo          = STOP
Strength             = STOP
Bake                 = STOP
Promotion            = STOP
Champion             = CURRICULUM
```

1. Ne pas retuner T2 sur 1628c/1629/1630.
2. Ne pas modifier a posteriori phase weights, heads, architecture, features, optimizer ou training recipe.
3. Q1 et le cohort T2 1628c sont désormais des cohorts de validation consommés.
4. Le PASS T2−T0 ne suffit pas : le benchmark primaire reste D1.
5. Le headroom q1000 reste massif et justifie une nouvelle campagne de recherche, mais pas une continuation automatique de cette prereg.
6. Une future expérience doit être preregistrée séparément et utiliser des données de conception/validation disjointes.

---

## 11. Priorité scientifique suivante

T2 était le test direct de l'hypothèse « davantage de capacité state-only + plateau brut + spécialisation par phase suffit à dépasser D1 ». Cette hypothèse **n'est pas établie**.

La prochaine question scientifique devient donc :

> **Quelles observables statiques manquent pour expliquer le résidu q1000/q200 que T0, D1, Rich-D et T2 ne captent pas ?**

La voie recommandée est une campagne séparée d'**autopsie résiduelle / feature discovery hors cohorts consommés**, avant tout nouveau student ou runtime gate.
