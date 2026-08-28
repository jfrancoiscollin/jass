# L3 — Joint T+D fresh q200 confirmation v1

> Date: 28 août 2026
> Statut: preregistration **avant toute nouvelle sélection/lecture q200**.
> Champion inchangé: `CURRICULUM`.

## 0. Question scientifique

Le screen M3 `cpx62-1614-l3-transfer-capacity-joint-screen-v2` puis le readout read-only `cpx62-1615-l3-transfer-capacity-joint-readout-publish-v1`, attempt `20260828T100556Z-d8241edc`, ont établi sur un DEV M3 gelé contre `micro1000`:

- T0/CURRICULUM pairwise `0.6142493326`;
- D1 pairwise `0.6569985012`;
- meilleur PatternEval pur G0 = `A6_MARGIN_L2_1E5`, pairwise `0.6197133624`, anchor RMS `9.8879cp`, p99 `35cp`, raw candidate SHA256 `271733adb8441630e1bae77b85951c05caa452107d3e8af4782f577347be06ed`;
- B0 production-linear non-anchored float `0.6264144537`, int32 `0.6262528687`, donc quantization loss seulement `0.0001615849`;
- B1 nonlinear same-observable probe `0.6532855604`;
- C0 minimal joint stack T0+D1+phase+colour `0.6726851201`, soit `+0.0156777066` vs D1, bootstrap CI95 `[0.0140120978; 0.0172939908]`;
- C1 residual D-on-T `0.6185354316`;
- C2 full linear joint static `0.6314341249`.

Le résultat structurants est donc:

```text
C0 > D1 > T0
```

sur le teacher `micro1000`, tandis que B1 montre que les observables PatternEval contiennent plus de signal que l'architecture linéaire de production n'en exploite.

Cette nouvelle expérience demande si ces deux conclusions survivent à un **cohort entièrement fresh** avec cible deep q200, jamais vu pendant le screen.

## 1. Hypothèses gelées avant le fresh

### Hypothèse primaire H1

Le joint minimal C0 conserve une information complémentaire réelle sur deep q200:

```text
C0 pairwise > D1 pairwise
```

sur un cohort fresh target-blind.

### Hypothèses secondaires diagnostiques

- `A6-G0` > T0 contre q200: une meilleure recette pure PatternEval transfère mieux que M4/T1.
- B1 > T0 contre q200: la capacité non linéaire sur les observables PatternEval se généralise au deep teacher.
- C0 > B1 et C0 > A6-G0 sont rapportés mais ne sont pas des gates autonomes.
- `micro1000` est calculé sur les mêmes siblings comme diagnostic de headroom et de stabilité, jamais comme cible finale.

**Seule H1/C0 décide si une branche joint-evaluator est scientifiquement autorisée pour une future étude runtime.** Les secondaires ne peuvent pas sauver un échec H1.

## 2. Anti-leakage et données interdites

Avant la sélection fresh:

- C0, B1 et A6-G0 doivent être gelés en bytes/paramètres et SHA.
- Aucun parent/label/sibling du nouveau cohort ne peut être lu pendant reconstruction/freeze des candidats.
- M5/1612 restent interdits pour fit, calibration ou sélection de candidats.
- M3 TRAIN/DEV peut uniquement être utilisé pour **rejouer exactement** les candidats déjà sélectionnés par le screen 1614; aucun nouveau hyperparamètre, architecture ou arm n'est autorisé.
- Le cohort fresh doit être disjoint de M1, M2, M3, M5, 1614/1615 et de tous les pools de force connus.

Aucun retuning après la première lecture fresh.

## 3. Stage F0 — freeze exact des candidats, sans fresh labels

### 3.1 T0

Byte-identical `CURRICULUM`:

```text
raw SHA256 = 319d174f4b548b1655aad4bb30d4c6dc86c08dd715c9c23f8b19ba1937dc0be1
```

### 3.2 D1

Exact sealed DSSD policy utilisée par 1614/1615:

```text
policy SHA256 = e91a55500713154f50be74db5d699b64d7684e1c078725d09e1d15e713549b49
```

Zero refit.

### 3.3 A6-G0 — meilleur PatternEval pur

Réutiliser l'artefact sérialisé exact du screen 1614:

```text
arm = A6_MARGIN_L2_1E5
anchor regime = G0
raw candidate SHA256 = 271733adb8441630e1bae77b85951c05caa452107d3e8af4782f577347be06ed
screen DEV pairwise vs q1000 = 0.6197133623717859
anchor RMS = 9.88787196519 cp
anchor p99 = 35.0 cp
changed int32 coefficients = 445
```

Ne pas refitter A6-G0.

### 3.4 B1 — nonlinear same-observable

Rejouer exactement l'implémentation déterministe de 1614, code SHA `d8241edc680eb50f324b2440fbde2bdadad29178`, sur le même M3 TRAIN split seed `2026090401`, sans nouvelle sélection d'hyperparamètres.

Contrat figé par 1614:

- same-observable only; aucun D/search/q50/q200/WDL input;
- ReLU;
- hidden width 64;
- Adam lr `1e-3`;
- pair family top+adjacent;
- train-only normalization;
- seed `2026090402`;
- parameter count `875601`.

Le freeze doit sérialiser poids + normalisation + schema dans un artefact immuable et publier SHA256. Avant d'autoriser F1, le replay doit reproduire les métriques DEV 1614 à tolérance déterministe explicite préfixée par l'implémentation. Si le replay ne reproduit pas le modèle, arrêt **TECHNIQUE**, pas scientifique.

### 3.5 C0 — primary joint stack

Rejouer exactement le fit C0 de 1614 sur M3 TRAIN, sans retune:

Inputs sibling uniquement:

- scalar T0;
- scalar D1 sealed;
- phase one-hot P0/P1/P2/P3;
- parent colour.

Pairwise logistic, L2 `1e-6`, même split `2026090401`. Sérialiser coefficients/intercept/schema + provenance et publier SHA256.

Le replay doit reproduire le DEV 1614:

```text
pairwise = 0.6726851201348883
top_hit = 0.3072860585550941
```

à la tolérance déterministe gelée avant F1. Sinon arrêt technique.

### F0 gate

F1 n'est autorisé que si:

- T0 SHA exact;
- D1 SHA exact;
- A6-G0 SHA exact;
- B1 artifact frozen + replay PASS;
- C0 artifact frozen + replay PASS;
- zero fresh labels/parents read;
- zero refit après ces bytes.

## 4. Stage F1 — fresh target-blind selection

Réutiliser les mécaniques robustes du selector M5, mais avec ce nouveau seed et exclusions élargies.

Sélection exactement:

```text
4000 parents
1000 P0 (30..40 pieces)
1000 P1 (20..29)
1000 P2 (12..19)
1000 P3 (9..11)
selection seed = 2026090420
legal moves = 2..16
```

Source: fresh CURRICULUM play / catalog fresh généré indépendamment selon le selector existant, avec sélection faite **avant** tout teacher score.

Exclusions obligatoires:

- all M1/M2/M3/M5 canonical parents;
- all fresh cohorts DSSD/Rich-D/micro-search déjà utilisés;
- all established force-pool exact states;
- exact duplicate and rotate180/colour-swap canonical duplicate.

F1 publie selected-parent manifest + canonical hashes + overlap proofs.

Avant F2, exiger:

- exactly 4000 selected;
- exactly 1000/phase;
- zero known-overlap;
- `target_blind=true`;
- q50/q200/q1000 scores read = 0;
- candidate scores read = 0 pendant sélection.

## 5. Stage F2 — teacher deep + micro1000 diagnostic

Pour chaque sibling de chaque parent F1:

- book OFF;
- 1 thread/search;
- fresh Engine/search state/TT per sibling and per budget;
- exact node limits;
- q50k stability screen;
- q200k final target;
- q1000 exact diagnostic under frozen B*=1000 semantics;
- exact terminal/TB W>D>L precedence unchanged.

Parent-POV convention identique DSSD/M5.

Stable non-terminal pair gardée seulement si:

```text
sign(d50) == sign(d200)
d50 != 0
d200 != 0
abs(d50) >= 10 cp
abs(d200) >= 30 cp
```

Target final = q200 ranking.

Aucun modèle n'est refitté/calibré après lecture q50/q200/q1000.

## 6. Stage F3 — common fresh readout

Sur exactement les mêmes accepted parent clusters/stable q200 pairs, scorer:

1. T0/CURRICULUM;
2. sealed D1;
3. frozen A6-G0;
4. frozen B1;
5. frozen C0;
6. exact micro1000 diagnostic.

Publier pour chaque signal:

- global pairwise vs q200;
- global top-hit vs q200;
- P0/P1/P2/P3 pairwise/top-hit;
- black/white parent pairwise/top-hit;
- stable pair / accepted parent counts;
- disagreement matrices C0 vs D1, C0 vs B1, C0 vs A6-G0;
- micro1000 headroom.

Bootstrap parent-cluster:

```text
samples = 100000
seed = 2026090421
```

Publier CI95 + P(delta>0) au minimum pour:

- C0-D1 pairwise/top-hit;
- C0-T0 pairwise/top-hit;
- A6-G0-T0 pairwise/top-hit;
- B1-T0 pairwise/top-hit;
- B1-D1 pairwise/top-hit;
- C0-B1 pairwise/top-hit.

## 7. Support gate

Avant toute interprétation de H1:

- selected parents = exactly 4000;
- accepted stable parents >= 3000;
- accepted each phase >= 600;
- accepted each parent colour >= 1200;
- stable pairs > 0 in each phase and colour;
- exact candidate bytes unchanged from F0;
- deterministic scoring replay PASS;
- no technical asymmetry.

Si support fail:

```text
JOINT_TD_FRESH_SUPPORT_NOT_ESTABLISHED
```

Terminal pour ce cohort, aucun seuil abaissé.

## 8. Primary PASS gate — H1 only

Verdict `JOINT_TD_FRESH_CONFIRMATION_ESTABLISHED` exige simultanément:

1. support gate PASS;
2. `C0-D1` pairwise parent-bootstrap CI95 low > 0;
3. `C0-D1` top-hit parent-bootstrap CI95 low > 0;
4. C0-D1 pairwise point delta > 0 dans chacune des phases P0/P1/P2/P3;
5. C0-D1 pairwise point delta > 0 pour black et white parents;
6. `C0-T0` pairwise CI95 low > 0;
7. frozen C0/D1/T0 bytes/parameters unchanged and replayable.

Sinon, support étant suffisant:

```text
JOINT_TD_FRESH_CONFIRMATION_NOT_ESTABLISHED
```

Ce gate est volontairement robuste: un global +1pp qui disparaît dans une phase/couleur ou en top-hit n'autorise pas une nouvelle architecture runtime.

## 9. Secondary readout, no rescue

A6-G0 et B1 sont diagnostiques:

- rapporter leurs gains/pertes q200 exacts;
- calculer pour chacun un `R_1000` fresh contre le même q200 target:

```text
R_1000(M) = (A_M - A_T0) / (A_micro1000 - A_T0)
```

si le dénominateur est positif;
- calculer C0 `R_1000` également.

Mais:

- A6/B1 positive ne peut pas changer un H1 FAIL en PASS;
- aucune sélection post-hoc entre A6/B1/C0;
- aucune promotion et aucun Elo dans F0-F3.

## 10. Décision après fresh

### Si primary PASS

Une branche **joint evaluator** devient scientifiquement autorisée. La prochaine étape doit être une prereg séparée qui mesure:

1. implémentation runtime exacte de C0;
2. coût CPU/NPS/latence;
3. same-executable OFF/ON;
4. fresh paired native-0.1s Elo pools;
5. aucune promotion automatique avant réplication robuste.

### Si primary FAIL mais B1 fresh est fort

Priorité architecture PatternEval/nonlinear, pas runtime joint.

### Si primary FAIL et B1/A6 restent faibles

Passer à découverte ciblée de nouvelles observables à partir des erreurs résiduelles micro1000.

## 11. Interdictions

Pendant F0-F3:

```text
selfplay = 0
strength games = 0
promotion = 0
new tuning = 0
D1 refit = 0
C0/B1 refit after fresh read = 0
new q200 cohort beyond exact F1 = 0
```

Les échecs techniques peuvent être réparés mécaniquement avec IDs versionnés, sans changer candidats, seeds, support, budgets, stable-pair rule ou PASS gate.

## 12. Job policy

Expected next IDs: `cpx62-1616+`.

Ordre préféré:

1. F0 candidate-freeze/replay;
2. F1 fresh selection;
3. F2 teacher + q1000 diagnostic;
4. F3 readout;
5. stop au verdict fresh; aucune force automatique.
