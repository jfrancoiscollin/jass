# L3 — programme de transfert F6 → cible T : E1 / E2 / E3 — preregistration

> **Date : 30 août 2026**
> **Statut : preregistration uniquement — DRAFT soumis à revue avant merge.**
> Avant merge, ce document n'autorise aucun code, aucun job, aucune instrumentation et aucune partie. Après merge, il autorise **uniquement** les interventions et gates E1/E2/E3 décrits ci-dessous, chacun sous son propre GO explicite JFC.
> **Le merge n'est pas une permission de lancer quoi que ce soit.** E1, E2 et E3 exigent chacun un GO distinct après publication des faits machine (`nproc`, rate mesuré, ETA chiffrée, disque libre, checks ISA/hot-path) et de la check-list pré-lancement.
> Aucun bloc n'autorise un bake, une promotion, un Pool2 v4 ni une réinterprétation d'un terminal immuable. E3 n'autorise **aucune partie de force** : si sa projection et son coût runtime sont établis, une preregistration de force séparée sera obligatoire.

---

## 1. Contexte terminal immuable

Rien de ce qui suit ne réécrit ces acquis :

- `CURRICULUM` reste champion de production ;
- CURRICULUM SHA256 : `319d174f4b548b1655aad4bb30d4c6dc86c08dd715c9c23f8b19ba1937dc0be1` ;
- T3-A `F6_ONLY` SHA256 : `16e5db8fd78849bba12b158eee5c1da4ab170129d8aeac1b91ab7a40ad9d0bb2` ;
- D1 scellé SHA256 : `e91a55500713154f50be74db5d699b64d7684e1c078725d09e1d15e713549b49` ;
- RF1/F6 SHA256 : `0d26ba50b668160b3da3e247cd4e1bd709c2cb7989b3b5877b9ea7deb34db58b` ;
- ordre F6 SHA256 : `cc4837e6829d937f7330f7bc71280f3ec0bed3f431e57b2664c651e1d763db4e` ;
- verdict offline : `F6_TRANSFER_ESTABLISHED_D1_NOT_ADDITIVE` ;
- R0-v4 : `R0_V4_PRODUCTION_LEAF_CONTRACT_ESTABLISHED`, job `cpx62-1685`, attempt `20260830T083226Z-0ead13cb` ;
- Pool1 PRIMARY v4 : job `cpx62-1686`, attempt `20260830T104034Z-0ead13cb`, `6000` parties, exit `0`, verdict `T3_F6_RUNTIME_STRENGTH_NOT_SUPPORTED` ;
- reçu terminal Pool1 : `cpx62-1689`, attempt `20260830T114717Z-ea643d77` ;
- O1 cache exact, Gates A/B/C : job `cpx62-1700`, attempt `20260830T172656Z-ac3e9415`, exit `0`, `O1_GATE_A_PASS`, `O1_GATES_BC_PASS_NONTERMINAL`, `GATE_D__NOT_RUN`.

Chiffres terminaux exacts :

```text
wins T3-A       = 1167
draws           = 180
wins CURRICULUM = 4653
score T3-A      = 0.2095
Elo T3-CURR     = -230.6871387863655
paired CI95     = [0.20033333333333334 ; 0.21866666666666668]
P(score>0.5)    = 0.0
POOL2_AUTHORIZED = FALSE
```

```text
pairwise q200 : T0 = 0.6082147602129492   T3-A = 0.7831693588009130   q1000 = 0.9361726861780656
top-hit       : T0 = 0.5540686274509804   T3-A = 0.6836764705882353
A-T0 pairwise = +0.17495459858796386  CI95 [+0.16940747096694114 ; +0.18047508706277157]
```

Diagnostic technique HOME `home-1688` :

```text
wall_ratio_t3_over_curriculum = 37.154452
nps_ratio_t3_over_curriculum  = 0.053152
```

Ces ratios motivent le présent programme ; ils ne constituent pas un verdict de force.

---

## 2. Décomposition du handicap runtime

Sur une même fenêtre de recherche, `wall = nodes / nps`. Les ratios de `1688` impliquent donc :

```text
nodes_ratio = wall_ratio * nps_ratio
            = 37.154452 * 0.053152
            = 1.974833

per_node_cost_ratio = 1 / nps_ratio = 18.8140
```

Interprétation gelée :

| Effet observé/déduit | Facteur | Nature |
|---|---:|---|
| coût par nœud T3-A vs CURRICULUM | `18.8140x` | coût d'évaluation ; l'ingénierie exacte peut l'attaquer |
| expansion de l'arbre à profondeur égale | `1.974833x` | interaction évaluation/search ; une optimisation **exacte de coût seulement** ne change pas ce nombre de nœuds |
| wall total à profondeur égale | `37.154452x` | produit des deux effets |

`1.974833x` est **déduit**, pas encore mesuré directement sur CPX62. E1 doit publier le compteur `nodes` direct. Il est interdit de le présenter comme une mesure avant ce gate.

Pool1 a donc établi une seule chose : **T3-A est très inférieur à CURRICULUM à `0,1 s/coup`**. Il n'isole pas la valeur causale de l'information F6, puisque coût par nœud et expansion de l'arbre y sont confondus.

O1 reste strictement technique. Son cache exact peut réduire des recomputations, mais Gates A/B/C exigent précisément que score, arbre, nodes et search behavior restent identiques. O1 ne peut donc pas supprimer l'expansion `nodes_ratio`; son Gate D ne mesure que le coût du chemin exact effectivement exécuté.

---

## 3. Questions du programme

1. **E1 — attribution de coût.** Où part le coût de `extract_f6` entre F1..F5/MLP/base et quel est le `nodes_ratio` direct sur CPX62 ?
2. **E2 — valeur causale de l'information F6.** À nœuds égaux, quelle part de la performance T3-A reste après correction du handicap d'expansion de l'arbre, calibré par un doublement de nœuds CURRICULUM ?
3. **E3 — projection dans la classe PatternEval de production.** Si E2 établit une valeur informationnelle positive, peut-on transférer ce signal dans un PatternEval où `extract_f6` n'est jamais appelé en partie ? Le coût total de recherche **doit être mesuré**, jamais supposé égal à CURRICULUM.

E2 est le verrou causal de E3.

---

## 4. E1 — attribution du coût (`0` partie, `0` fit)

### 4.1 Intervention gelée

Instrumentation additive, désactivée par défaut, de `residual_features::extract_f6` :

1. chronomètre et compteurs exclusifs pour `F1 CAPTURE_GEOMETRY`, `F2 RESPONSE_FRONTIER`, `F3 PROMOTION_RACE`, `F4 STRUCTURE_GRAPH`, `F5 KING_GEOMETRY_PLUS`, MLP seul et `base_->evaluate` seul ;
2. par famille : temps, appels `generate_legal_moves`, constructions de position enfant ;
3. interdiction de modifier feature, ordre, normalisation, arrondi, POV, poids, MLP, base, movegen ou search ;
4. `threads=1`, contrat R0-v4 inchangé ;
5. E1 **mesure seulement** : aucune optimisation, ablation, approximation ou refactor n'est autorisé.

### 4.2 Support gelé

- corpus exact `r0-corpus.fen`, `4096` positions, authentifié par `cpx62-1685` ;
- racines : fonction `stratified` de `jobs/tools/t3_f6_search_profile.py`, `order_seed=2026092505`, premières `32` par phase, `128` racines ;
- depth exact `9`, mêmes unités que Gate D O1 ;
- aucun label, teacher score, fresh ou cohorte de fit.

### 4.3 Gate E1

- instrumentation ON vs OFF : les **66 features** doivent être égales bit-à-bit sur `4096/4096` et le score T3 entier exactement égal ;
- somme des temps exclusifs cohérente avec le total instrumenté, écart publié ;
- `nodes_ratio_E1 = sum(nodes_T3_A) / sum(nodes_CURRICULUM)` sur les `128` racines depth-9, publié avec les deux sommes ;
- bootstrap racines `100000`, seed `2026100105`, CI95 de `nodes_ratio_E1` ;
- host, CPU, `nproc`, flags de build et executable SHA publiés.

Tout mismatch d'exactitude donne `E1_INSTRUMENTATION_NOT_EXACT` et STOP.

### 4.4 Publication requise

Table par famille : `ns/eval`, part du coût, movegen/eval, child-build/eval. Publier aussi coût MLP, coût base, NPS, nodes, wall et ratios T3/CURRICULUM.

### 4.5 Décision E1 — uniquement pour une future preregistration

- si une seule famille concentre `>=60%` du coût `extract_f6`, une ablation `F6 \ {famille}` devient **preregistrable dans un document séparé** ;
- sinon aucune ablation n'est autorisée par E1.

Aucun fit, tuning, calibration, feature selection ou model selection n'est permis sur `1638/1639/1640`.

### 4.6 Verdicts E1

```text
E1_COST_ATTRIBUTED
E1_INSTRUMENTATION_NOT_EXACT
E1_TECHNICAL_FAILED
```

---

## 5. E2 — attribution causale à nœuds égaux

### 5.1 Principe

Pool1 fixe le temps ; E2 fixe les nœuds. E2 ne cherche pas à refaire Pool1. Il cherche à estimer séparément :

- la performance brute de T3-A à même budget de nœuds (`C1`) ;
- la valeur Elo d'un doublement de nœuds pour CURRICULUM sur le même harnais (`C2`) ;
- l'intégrité symétrique du harnais (`C3`) ;
- puis la valeur informationnelle F6 corrigée de l'expansion `nodes_ratio_E1`.

**Correction méthodologique importante :** le gate E3 ne porte pas sur `Elo(C1)>0`. Sous l'hypothèse « F6 n'apporte aucune information utile mais modifie l'arbre », C1 est attendu négatif d'environ `log2(nodes_ratio_E1)` doublement(s). Le bon contraste causal est donc `delta_info` défini au §5.6.

### 5.2 Pool frais et seeds gelés maintenant

Générer exactement `30000` candidates légales target-blind :

```text
min_ply=8
max_ply=32
min_pieces=20
generation_seed=2026100101
```

Exclure R0-v4, Pool1 v4, tous les pools de force/corpus scientifiques publiés au moment du lancement et toute identité canonique déjà consommée ; la liste d'exclusion peut seulement **croître** pour ajouter une cohorte publiée, jamais rétrécir. Dédupliquer board+STM et équivalence rotate180+colour-swap.

Sélectionner exactement `1350` openings par ordre `SHA256("2026100102:" + canonical_identity)` :

- premières `750` -> C1 ;
- suivantes `400` -> C2 ;
- dernières `200` -> C3.

Chaque opening est joué dans les deux couleurs : `1500 + 800 + 400 = 2700` parties. Replays de sélection byte-identiques, overlap inter-cellules `0`, overlap interdit `0`. Ordre d'exécution gelé par seed `2026100104`.

### 5.3 Contrat moteur gelé

- bytes T3-A/CURRICULUM inchangés, aucun refit/retune/calibration/D1/retrait de feature ;
- 66 features F6 inchangées ; normalisation, rounding, clamp et POV inchangés ;
- search/order/pruning/TT/qsearch/TB inchangés ;
- `threads=1`, book OFF, EGDB identique des deux côtés, engine/state/TT frais par partie ;
- limite en **nœuds par coup**, `movetime` désarmé ;
- O1 cache exact fixé **ON pour T3-A uniquement si O1 est terminalement clos et son exactitude A/B/C reste authentifiée** ; sinon E2 n'est pas lançable. Le mode O1 exact est publié et ne peut varier entre parties.

### 5.4 Timeout et garde technique

Le bras T3-A reste beaucoup plus lent par nœud. Donc :

- `--game-timeout` calibré sur un sizer du bras lent avant lancement ;
- `game skipped` publié et exigé `=0` dans chaque cellule ;
- timeout de shard = au moins `1.3x` le temps sain mesuré ;
- progress monitor committé environ toutes les 10 min ;
- PIDs explicites et `wait "${pids[@]}"`, jamais `wait` nu ;
- résultats/progress dans `$W`, hors arbre git ;
- aucun timeout/skipped n'est transformé en draw.

### 5.5 Cellules gelées

| Cellule | Bras | Budget | Parties | Rôle |
|---|---|---|---:|---|
| **C1** | T3-A vs CURRICULUM | `20000` vs `20000` nodes/coup | `1500` | score brut à nœuds égaux |
| **C2** | CURRICULUM-hi vs CURRICULUM-lo | `20000` vs `10000` nodes/coup | `800` | Elo par doublement |
| **C3** | CURRICULUM-A vs CURRICULUM-B | `20000` vs `20000` nodes/coup | `400` | garde déterministe du harnais |

Pour C3, les deux bras sont byte-identiques. Avec état frais et `threads=1`, chaque paire d'opening doit être complémentaire du point de vue de l'identité des bras (ou deux draws). Exiger :

```text
aggregate_score_arm_A == 0.5 exactement
paired_complementarity_failures == 0
game_skipped == 0
```

Tout écart rend E2 `E2_INCONCLUSIVE_HARNESS`, jamais neutre.

### 5.6 Estimands et bootstrap conjoints — gelés

Score de cellule : `(wins + 0.5*draws)/n`. Conversion Elo :

```text
Elo(p) = 400 * log10(p / (1-p))
```

avec `p` strictement dans `(0,1)` ; si une cellule ou plus de 2.5% des replicates bootstrap atteint `0` ou `1`, le readout devient `E2_INCONCLUSIVE_HARNESS`.

Définitions :

```text
elo_c1       = Elo(score_C1)
slope_c2     = Elo(score_C2_hi_arm)          # 20k vs 10k = 1 doublement exact
r_nodes      = nodes_ratio_E1                 # ratio de sommes sur 128 racines
h0_c1        = -log2(r_nodes) * slope_c2
delta_info   = elo_c1 - h0_c1
             = elo_c1 + log2(r_nodes) * slope_c2
```

`delta_info` est l'estimand primaire E2 : gain d'information attribuable à T3-A **au-delà** du handicap d'expansion de l'arbre calibré sur CURRICULUM.

Bootstrap primaire : `200000` replicates, seed unique `2026100103`. À chaque replicate :

1. resampler avec remise les `750` paires d'openings C1 ;
2. resampler avec remise les `400` paires C2 ;
3. resampler avec remise les `128` racines E1 et recalculer `r_nodes = sum(T3 nodes)/sum(CURR nodes)` ;
4. calculer `elo_c1`, `slope_c2`, `h0_c1`, `delta_info` ;
5. CI95 percentile `[2.5%,97.5%]`.

Les trois resamplings utilisent des sous-flux déterministes dérivés dans l'ordre C1/C2/E1 du même PRNG seed ; aucun bootstrap post-hoc alternatif n'est autorisé.

Diagnostics obligatoires : profondeur/effective depth, nodes effectifs, eval calls et wall par bras.

### 5.7 Gate E2 et kill switch correct

Préconditions de lecture causale :

- E1=`E1_COST_ATTRIBUTED` avec `r_nodes>0` fini ;
- C3 exact ;
- `game_skipped=0` partout ;
- C2 doit mesurer le bon sens du budget : **borne basse CI95 de `slope_c2` > 0**. Sinon calibration insuffisante -> `E2_INCONCLUSIVE_HARNESS`.

Verdict primaire :

```text
E2_F6_INFORMATION_VALUE_ESTABLISHED
```

si et seulement si la **borne basse CI95 de `delta_info` est strictement > 0**.

Sinon, si le harnais est sain mais cette borne n'est pas >0 :

```text
E2_F6_INFORMATION_VALUE_NOT_ESTABLISHED
```

et E3 est fermé par **politique de programme** : il n'existe pas alors de preuve causale suffisante justifiant un nouveau fit de transfert F6. Cette règle n'affirme pas qu'une distillation ne pourrait jamais régulariser un teacher ; elle interdit simplement ce repêchage non identifié dans ce programme.

`CI95(elo_c1)` entièrement >0 est publié séparément comme signal plus fort de supériorité T3-A brute à nœuds égaux, mais **n'est pas requis pour E3**.

Autres verdicts :

```text
E2_INCONCLUSIVE_HARNESS
E2_TECHNICAL_FAILED
```

E2 n'autorise jamais bake, promotion ni Pool2 v4.

### 5.8 Budget Elo pour toute future route F6 in-play

Si une future optimisation exacte conserve F6 en partie, l'information positive à défendre est `delta_info`, tandis que le péage total inclut **à la fois** coût par nœud restant et expansion `r_nodes` :

```text
required_gain ~= slope_c2 * log2(r_nodes * per_node_cost_ratio_after_optimization)
```

Cette formule est un diagnostic de décision d'ingénierie, jamais un gate de force de ce document.

---

## 6. E3 — projection F6 vers PatternEval, F6 absent au runtime

E3 est autorisé uniquement si :

```text
E2_F6_INFORMATION_VALUE_ESTABLISHED
```

et sous un GO explicite distinct.

### 6.1 Principe exact

F6 sert uniquement comme **labeler statique offline**. En runtime, le candidat E3 utilise la même classe PatternEval de production ; `extract_f6` n'est jamais appelé.

Cela supprime **par construction le coût d'extraction F6**, mais **ne garantit pas `wall_ratio=1`** : de nouveaux poids peuvent modifier ordering, cutoffs, reductions et nombre de nœuds. Le coût search total doit donc être mesuré par E3-R avant que le modèle puisse être qualifié de candidat.

### 6.2 Fit gelé

Corpus de fit : corpus courant du champion, byte-identique, hash publié, volume inchangé. La cohorte `1638/1639/1640` reste interdite.

Seule modification de training : préférence de chaque paire de siblings fournie par le **score statique production entier de T3-A gelé** (SHA §1), sans recherche teacher. Pour un tie T3 exact, la paire n'apporte aucune contrainte et est comptée/publiée ; aucun tie-break arbitraire n'est injecté.

Recette gelée :

```text
--exact-fold
--prior-mean <CURRICULUM>
--prior-decay 0
--lbfgs-gtol 1e-4
--l2 1e-5
```

Aucun sweep, aucun `decay>0`, aucun balayage de lambda, aucun changement de classe de modèle, aucune nouvelle feature runtime.

### 6.3 Holdout de fidélité réellement frais — pas de leakage du fit

Le fit peut conserver **tout son corpus historique** ; la fidélité est évaluée sur un holdout neuf, jamais vu par le fit.

Générer target-blind `20000` parents légaux, puis sélectionner exactement `4000`, `1000` par phase, par hash canonique :

```text
generation_seed = 2026100201
selection_seed  = 2026100202
```

Avant toute lecture T3/CURRICULUM/student : exclure le corpus de fit du champion, `1638/1639/1640`, M3/M5/1612, R0-v4 et tous les pools de force/scientifiques publiés ; overlap canonique exigé `0`. Tous les siblings légaux d'un parent sélectionné restent dans le même cluster.

Aucun q50/q200/q1000, WDL, score de search ou label profond n'est généré. Le seul teacher du holdout est le T3-A statique gelé après sélection/scellement des identités.

### 6.4 Gate E3-P — fidélité de projection

Sur les paires strictement ordonnées par T3-A dans le holdout :

```text
agreement = 1.0  si signe(model_i-model_j) == signe(T3_i-T3_j)
          = 0.5  si model_i == model_j
          = 0.0  sinon
```

Publier pour CURRICULUM et le modèle distillé : pairwise agreement, top-hit, phases/couleurs et nombre de ties teacher/model.

Estimand primaire :

```text
fidelity_delta = agreement(distilled,T3-A) - agreement(CURRICULUM,T3-A)
```

Bootstrap par **parent cluster**, `100000` replicates, seed `2026100203`, CI95 percentile. Gate : borne basse CI95 de `fidelity_delta` strictement >0.

Verdicts :

```text
E3_PROJECTION_TRANSFERS
E3_PROJECTION_LOSS_TOTAL
E3_TECHNICAL_FAILED
```

Aucune partie n'est autorisée si le gate de fidélité échoue.

### 6.5 Gate E3-R — coût runtime obligatoire, non supposé

Seulement après `E3_PROJECTION_TRANSFERS`, profiler le modèle distillé contre CURRICULUM sur CPX62, `threads=1`, book OFF, EGDB identique, engine/state/TT frais.

Support technique : mêmes `128` racines R0-v4 que E1, `32` par phase, `order_seed=2026092505`. Ces racines sont utilisées **uniquement pour runtime**, jamais pour fit ou sélection de modèle.

Deux fenêtres gelées :

1. **depth-9** : mesurer `wall`, `nodes`, `nps`, `eval_calls`, effective/completed depth ;
2. **nodes-20000** : mesurer `wall`, `nps`, effective/completed depth, eval calls.

Ordre des bras alterné par index global : pair -> CURRICULUM puis distillé ; impair -> distillé puis CURRICULUM. Aucun warm-up spécifique à un bras.

Publier au minimum :

```text
wall_ratio_depth9
nodes_ratio_depth9
nps_ratio_depth9
wall_ratio_nodes20k
nps_ratio_nodes20k
```

et CI bootstrap racines `100000`, seed `2026100204`.

Aucun seuil de performance ne sélectionne une variante : il n'existe qu'un seul modèle E3. Le gate exige seulement une exécution saine et des ratios finis/publiés.

Verdicts :

```text
E3_RUNTIME_COST_CHARACTERIZED
E3_RUNTIME_PROFILE_FAILED
```

**Ce document s'arrête ici.** Même avec `E3_PROJECTION_TRANSFERS` + `E3_RUNTIME_COST_CHARACTERIZED`, aucune partie de force, aucun bake et aucune promotion ne sont autorisés. Un futur test de force doit preregistrer ses pools, seeds, sizing et gates dans un document séparé après lecture de E3-P/E3-R.

---

## 7. Amendement méthodologique durable

Règle proposée pour la campagne :

> **Aucun verdict offline ne peut désigner un candidat de runtime sans publier à côté de lui un profil coût mesuré sur le runtime visé.** Au minimum : `wall_ratio`, `nps_ratio`, `nodes_ratio` et protocole de mesure.

Le point important est précisément que `nps_ratio ~=1` ne suffit pas : des poids différents peuvent modifier le nombre de nœuds. Inversement, une optimisation exacte de coût peut améliorer NPS sans changer l'arbre.

---

## 8. Interdictions communes

- aucune promotion, aucun bake, aucun Pool2 v4 ;
- aucune réinterprétation de `1685`, `1686`, `1688`, `1689`, `1700` ;
- aucune utilisation de `1638/1639/1640` pour fit/tuning/calibration/feature/model selection ;
- aucun NNUE, aucune nouvelle classe runtime ;
- aucun D1 dans E1/E2/E3 ;
- aucun retrait/approximation F6 en E1/E2 ;
- aucun changement search en E1/E2/E3 ;
- aucun sweep opportuniste ;
- aucun `decay>0`, aucun balayage de lambda ;
- E1 mesure, E2 attribue, E3 change uniquement la cible d'un PatternEval puis mesure sa fidélité et son coût ;
- aucun lancement par simple merge : GO distinct obligatoire par bloc.

---

## 9. Check-list pré-lancement par bloc

| Point | E1 | E2 | E3 |
|---|---|---|---|
| `nproc`/CPU/host publiés | requis | requis | requis |
| rate mesuré sur la box | requis | requis sur bras lent | requis |
| ETA = volume/rate + overhead | requis | requis | requis |
| sizing léger et justifié | requis | requis | requis |
| `df` + auto-clean stale | requis | requis | requis |
| write->read smoke | requis | requis | requis |
| `bash -n` / `py_compile` | requis | requis | requis |
| guards ISA/hot-path | requis | requis | requis |
| résultats hors arbre git | requis | requis | requis |
| `n=0`/support insuffisant => abort | requis | requis | requis |
| GO explicite JFC | requis | requis séparé | requis séparé |

Pour E2 : timeout/shards/PIDs/progress et `game_skipped=0` sont obligatoires. Pour E3 : aucun job de force n'existe dans le scope.

---

## 10. Traçabilité terminale requise

Chaque terminal publie :

- code SHA et artifact/model SHA ;
- host/CPU/`nproc`/flags ;
- `threads=1` ;
- sources exactes des racines/openings/holdout et tous les seeds ;
- overlap proofs ;
- budgets ;
- compteurs de skipped/timeouts ;
- nodes, depths, eval calls, wall et NPS par bras ;
- E1 : table F1..F5 + MLP/base et `nodes_ratio_E1` ;
- E2 : C1/C2/C3, bootstrap conjoint, `h0_c1`, `delta_info` et verdict exact ;
- E3-P : fidélité CURRICULUM/student, ties, bootstrap parent-cluster ;
- E3-R : `wall/nps/nodes` ratios depth-9 et nodes-20k ;
- verdict exact pris uniquement dans les listes de ce document.

Les terminaux `1685`, `1686`, `1688`, `1689` et `1700` restent immuables et sont référencés, jamais réécrits.
