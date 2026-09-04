# L3 — état courant et registre de décision

> **Mis à jour : 5 septembre 2026**
> **Source de vérité active : ce document.**
>
> Résultats acquis / portes closes : [`PROJECT_RESULTS.md`](PROJECT_RESULTS.md).  
> Plan normatif : [`L3_PURE_PLAN.md`](L3_PURE_PLAN.md).  
> T3 terminal : [`experiments/L3_T3_RF1_JOINT_AB_V1_20260829.md`](experiments/L3_T3_RF1_JOINT_AB_V1_20260829.md).  
> Runtime v4 : [prereg](experiments/L3_T3_F6_RUNTIME_STRENGTH_V4_20260829.md) · [terminal Pool1](experiments/L3_T3_F6_RUNTIME_STRENGTH_V4_RESULTS_20260829.md).  
> O1 exact cache : [prereg](experiments/L3_T3_F6_RUNTIME_EXACT_CACHE_O1_20260830.md) · [terminal](experiments/L3_T3_F6_RUNTIME_EXACT_CACHE_O1_RESULTS_20260830.md).  
> Programme suivant : [E1/E2/E3](experiments/L3_F6_TRANSFER_PROGRAM_E1_E3_20260830.md) · [amendment O1 terminal](experiments/L3_F6_TRANSFER_PROGRAM_E1_E3_O1_TERMINAL_AMENDMENT_20260830.md).

---

## 0. Programme decision-information — reprise du 5 septembre

Le [plan de la PR #771](experiments/L3_DECISION_INFORMATION_IMPLEMENTATION_PLAN_V1_20260903.md) distingue l'instrumentation passive A, le diagnostic/confirmation B et les étapes d'apprentissage ultérieures sous leurs critères propres.

Le diagnostic historique `cpx62-1769-l3-decision-math-adaptive-shadow-b1-v1`, tentative `20260904T221533Z-db6e6a5c`, est terminé avec exit `0` et `B1_HISTORICAL_SHADOW_COMPLETE`. Le readout 1770 a authentifié **41,81% d'économie simulée**, **96,425% de choix de ligne identiques**, regret brut moyen **95,749** et **32 parents sur 8 000** à regret >=100 ; p95 nul. [Reçu et limites B1](experiments/L3_ADAPTIVE_SHADOW_B1_RESULTS_20260905.md). Le diagnostic historique 1771 décompose cette queue de regrets avant le gel de B2. La suite de la branche enseignant reste `B2_PREREGISTER_CONFIRMATION_ONLY`; aucun enseignant adaptatif réel n'est encore confirmé.

Les diagnostics 1771 et 1772 sont terminés. 80 divergences sont des ex æquo q200 et 206 ont un écart numérique positif ; 222 références sont éliminées à q5, 64 à q50. L'invariance de l'allocation à q200 est vérifiée. 1772 reproduit les reçus précédents et ne trouve aucune observation q200 inadmissible selon ses contrôles. Il distingue **26 changements de famille de signal** et **six écarts >=100 à l'échelle d'évaluation**. Sur les seules 6 678 paires non exactes admissibles dont les deux scores sont compatibles avec l'évaluation, moyenne numérique **0,6012**, p95 nul, maximum 467 ; ce n'est pas une moyenne de perte en cp sur l'ensemble des 8 000 parents. Les familles de score et les preuves TB/PV restent séparées. [Reçus, strates et limites B1](experiments/L3_ADAPTIVE_SHADOW_B1_RESULTS_20260905.md). **B2 reste à préenregistrer et confirmer ; aucun critère de confirmation n'est acquis.**

`SearchDecisionTrace` A1/A2 est intégré via la [PR #773](https://github.com/jfrancoiscollin/jass/pull/773), commit `107be69832111354cd61504aff208458979f26e9` : identité OFF/ON à profondeur/nœuds déterministes, 27 444 assertions natives, revue indépendante sans P1/P2, CI native/Python/WASM verte. A3 exporteur/readout est la suite indépendante. `CURRICULUM` reste champion. Les sections suivantes conservent les reçus et restrictions des programmes antérieurs ; elles ne constituent pas un état de lancement actualisé de la PR #771.

---

## 1. Champion et artefacts gelés

### `CURRICULUM` reste le champion de production

Aucun candidat T3 n'est promu ou baké. T3-A/F6 reste un artefact scientifique frozen et son activation runtime reste explicite.

```text
CURRICULUM SHA256 = 319d174f4b548b1655aad4bb30d4c6dc86c08dd715c9c23f8b19ba1937dc0be1
T3-A F6_ONLY      = 16e5db8fd78849bba12b158eee5c1da4ab170129d8aeac1b91ab7a40ad9d0bb2
T3-B JOINT_D1_F6  = 227e954bbe98412594641be255c7edd5f69261aaf7fca4092537ef66f6cf668f
D1 sealed         = e91a55500713154f50be74db5d699b64d7684e1c078725d09e1d15e713549b49
RF1/F6            = 0d26ba50b668160b3da3e247cd4e1bd709c2cb7989b3b5877b9ea7deb34db58b
F6 order          = cc4837e6829d937f7330f7bc71280f3ec0bed3f431e57b2664c651e1d763db4e
```

Toutes les décisions ci-dessous conservent ces bytes sauf autorisation scientifique séparée explicite.

---

## 2. Terminaux immuables qui pilotent la suite

### 2.1 Offline T3

```text
VERDICT = F6_TRANSFER_ESTABLISHED_D1_NOT_ADDITIVE
```

Sur le fresh T3 consommé :

```text
T0 pairwise      = 0.6082147602129492
T3-A pairwise    = 0.7831693588009130
A - T0           = +0.17495459858796386
CI95 A - T0      = [+0.16940747096694114 ; +0.18047508706277157]
T3-B - T3-A      = -0.004942934833288572
```

Interprétation durable : les **66 features F6** transfèrent fortement offline ; le scalaire D1 scellé n'est pas additif au-dessus de F6 dans le bras joint preregistré. La cohorte `1638/1639/1640` est consommée et interdite à tout fit, tuning, calibration, feature/model selection post-hoc.

### 2.2 Contrat runtime R0-v4

```text
R0_V4_PRODUCTION_LEAF_CONTRACT_ESTABLISHED
```

Job `cpx62-1685-l3-t3-f6-runtime-r0-v4`, attempt `20260830T083226Z-0ead13cb`, exit `0`.

### 2.3 Pool1 v4 — force au temps fermée

Job `cpx62-1686-l3-t3-f6-runtime-strength-pool1-v4`, attempt `20260830T104034Z-0ead13cb`, `6000` parties. Reçu terminal `cpx62-1689-l3-t3-f6-runtime-pool1-terminal-receipt-v1`.

```text
VERDICT = T3_F6_RUNTIME_STRENGTH_NOT_SUPPORTED
W / D / L T3-A = 1167 / 180 / 4653
score           = 0.2095
Elo             = -230.6871387863655
paired CI95     = [0.20033333333333334 ; 0.21866666666666668]
POOL2_AUTHORIZED = FALSE
```

Ce terminal ne peut être réinterprété : **aucun Pool2 v4, bake ou promotion**.

---

## 3. O1 exact cache — terminal technique

### 3.1 Verdict

```text
VERDICT = O1_EXACT_CACHE_ESTABLISHED
```

Reçu terminal read-only :

```text
job     = cpx62-1705-l3-t3-f6-o1-terminal-receipt-v1
attempt = 20260830T195143Z-53bddb24
code    = 53bddb24a2d144af39df486d8c3e53b7d196cf65
exit    = 0
```

Le reçu authentifie A/B/C/D PASS, `STRENGTH_GAMES__0`, `PROMOTION_AUTHORIZED__FALSE`, `BAKE__FALSE`.

### 3.2 Exactitude établie

O1 conserve exactement : modèle T3-A, 66 features F6, poids, normalisation, calcul binary64, rounding/clamp, POV, movegen, qsearch, pruning, ordering, TT et terminal/TB.

Cache gelé : `65536` entrées direct-mapped, clé board complète + STM, sérialisation canonique 33 octets little-endian, FNV-1a 64-bit / low 16 bits, bit `valid`, égalité de clé complète obligatoire, résiduel raw `double` uniquement. Activation O1 `threads=1`; cache/Network neuf par root×budget, aucun warm-up ou reuse inter-root.

Gate B : `4096` feuilles, mismatch résiduel/score/replay/flush `0`, saturation/nonfinite `0`, hits réels présents.

Gate C : `64` racines × quatre budgets (`depth1`, `depth9`, `nodes1000`, `nodes10000`) = `256` paires OFF/ON, contrat `same_result` complet exact, mismatch `0`.

### 3.3 Gate D CPX62

Source : `cpx62-1704-l3-t3-f6-o1-gate-d-preflight-auth-fix-v1`, attempt `20260830T193038Z-53bddb24`, exit `0`.

```text
roots                       = 128 (32 / phase)
searches                    = 256
threads                     = 1
depth                       = 9
primary timing              = search-only
OFF/ON search mismatches    = 0
nodes OFF == nodes ON       = true
eval calls OFF == ON        = true
cache hit-rate              = 0.322842
wall ratio ON / OFF         = 0.691964
NPS ratio ON / OFF          = 1.445162
strength_games              = 0
scientific_decision         = false
```

O1 économise donc environ **30,8 % de wall** dans la fenêtre mesurée et augmente le NPS d'environ **44,5 %**, à arbre strictement identique.

### 3.4 Boundary O1

O1 **ne** démontre **pas** que T3-A est compétitif contre CURRICULUM. Gate D compare T3-A cache OFF à T3-A cache ON ; il ne mesure pas `nodes(T3-A)/nodes(CURRICULUM)`.

Le diagnostic HOME `1688` (`wall_ratio=37.154452`, `nps_ratio=0.053152`) reste un diagnostic d'une autre box/build. Il est interdit de multiplier naïvement ce rate HOME par le gain O1 CPX62.

Aucune O2 n'est implicitement autorisée.

---

## 4. Programme E1 / E2 / E3 — preregistration mergée

La preregistration a été publiée byte-identique via **PR #735**, merge `f6c3c4928625d0628945eb66d7289dce24c6f551`. Le draft original **#733** a été fermé comme supersédé uniquement parce que l'action Ready-for-review du connecteur échouait ; le contenu scientifique final est celui du SHA `11e3cfd72a2b2315e0290f500aa6a1ffeedbe4b2` mergé par #735.

**Le merge n'est pas un GO d'exécution.** E1, E2 et E3 exigent chacun leur GO explicite distinct après les faits machine, rate comparable, sizing/ETA, disque et checks pré-lancement.

### 4.1 E1 — prochaine porte, mais pas encore autorisée à tourner

Question : où part le coût F6 et quel est le ratio direct de nœuds T3-A / CURRICULUM sur CPX62 ?

Contrat principal :

```text
games = 0
fit = 0
cache O1 pour attribution primaire = OFF
leaf exactness support = 4096 R0-v4
search support = 128 roots, 32/phase, depth 9
nodes_ratio_E1 = sum(nodes_T3_A) / sum(nodes_CURRICULUM)
bootstrap roots = 100000, seed 2026100105
```

Instrumentation additive F1..F5 + MLP + base : temps exclusif, movegen/eval et child-build/eval. Les 66 features et le score T3 doivent rester bit-à-bit/exactement identiques instrumentation OFF/ON.

Si une seule famille représente `>=60 %` du coût, cela rend seulement une ablation **preregistrable dans un document futur séparé** ; E1 n'autorise aucune ablation ni fit.

### 4.2 E2 — verrouillé jusqu'à E1 + GO E2

E2 est un A/B à **nœuds égaux**, pas un replay de Pool1 à temps égal.

Cellules gelées :

```text
C1: T3-A vs CURRICULUM, 20k vs 20k nodes/coup, 1500 games
C2: CURRICULUM-hi vs CURRICULUM-lo, 20k vs 10k, 800 games
C3: CURRICULUM vs byte-identical CURRICULUM, 20k vs 20k, 400 games
```

Pool frais target-blind, seeds/volumes gelés dans le prereg. C3 exige score agrégé exactement `0.5`, complémentarité appariée parfaite et `game_skipped=0`.

Estimand de programme preregistré :

```text
delta_info = Elo(C1) + log2(nodes_ratio_E1) * slope(C2)
```

Important : `C1` est le contraste expérimental direct. `delta_info` est une **décomposition mécanistique locale preregistrée** (réponse log2 aux nœuds + séparabilité approximative), pas une identification non-paramétrique du « pur effet information ». Son gate peut ouvrir E3 ; il ne prouve jamais à lui seul que T3-A est plus fort et n'autorise aucune promotion/bake/Pool2.

E3 n'est ouvert que si la borne basse CI95 de `delta_info` est strictement positive et toutes les gardes E2 passent.

### 4.3 E3 — verrouillé jusqu'au verdict E2 + GO E3

E3 utiliserait F6 uniquement comme **labeler statique offline** pour un unique PatternEval ; `extract_f6` n'est jamais une feature runtime du modèle distillé.

POV teacher gelé :

```text
S_T3(parent, child) = -T3_A.evaluate(child)
```

Le corpus de fit ne peut pas être choisi au moment du job : il doit être l'artefact byte-exact unique consommé par le **dernier stage de fit ayant produit CURRICULUM**. Sa provenance job/attempt, URI, SHA256, volume et recette doivent être authentifiés avant tout fit ; ambiguïté = `E3_TECHNICAL_FAILED` fail-closed.

Le holdout fidélité est neuf, target-blind, disjoint et sans q50/q200/q1000/search teacher. La projection doit améliorer la fidélité à T3-A avec CI bootstrap parent-cluster >0 avant toute caractérisation runtime.

Même si projection + coût runtime passent, **ce document s'arrête avant toute partie de force**. Une force ultérieure exige une nouvelle preregistration.

---

## 5. Interdictions et données consommées

1. `CURRICULUM` reste champion ; aucune promotion automatique.
2. Aucun nouveau model search, retune/refit/calibration T3-A, D1, retrait/approximation F6 ou changement search n'est autorisé par O1/E1/E2.
3. La cohorte `1638/1639/1640` reste interdite à fit/tuning/calibration/feature/model selection.
4. Pool1 v4 ne peut jamais devenir un corpus de sélection d'une optimisation.
5. Les terminaux v1/v2/v3, R0-v4, Pool1, O1 sont référencés mais jamais réécrits.
6. Aucun seuil post-hoc, sweep opportuniste ou transport de rate entre boxes/modèles.
7. Aucun E2/E3 sans le verdict/gate upstream requis et son GO explicite séparé.
8. Aucun strength test optimisé sans preregistration dédiée, fresh disjoint et GO séparé.

---

## 6. État opérationnel exact

```text
champion = CURRICULUM
offline_T3 = F6_TRANSFER_ESTABLISHED_D1_NOT_ADDITIVE
runtime_v4 = T3_F6_RUNTIME_STRENGTH_NOT_SUPPORTED
Pool2_v4 = FORBIDDEN
O1 = O1_EXACT_CACHE_ESTABLISHED
O1_strength_games = 0
transfer_prereg = MERGED_PR_735
E1 = NOT_STARTED
E2 = LOCKED_BEHIND_E1
E3 = LOCKED_BEHIND_E2
next_stage = E1_COST_ATTRIBUTION_PENDING_EXPLICIT_GO
```

Aucun job E1/E2/E3 n'a été lancé au moment de cette mise à jour. La prochaine action compute exige les 12 checks permanents et un **GO JFC explicite** conforme au prereg E1.
