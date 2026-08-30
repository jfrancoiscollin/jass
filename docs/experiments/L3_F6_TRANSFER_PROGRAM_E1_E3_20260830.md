# L3 — programme de transfert F6 → cible T : E1 / E2 / E3 — preregistration

> **Date : 30 août 2026**
> **Statut : preregistration uniquement — DRAFT soumis à revue avant merge.**
> Avant merge, ce document n'autorise aucun code, aucun job, aucune instrumentation et aucune partie. Après merge, il autorise **uniquement** les interventions et gates E1/E2/E3 décrits ci-dessous, chacun sous son propre GO explicite JFC.
> **Le merge n'est pas une permission de lancer quoi que ce soit.** E1 exige un GO ; E2 et E3 exigent chacun un GO distinct, après publication des faits machine (`nproc`, rate mesuré, ETA chiffrée, disque libre, checks ISA/hot-path) et de la check-list pré-lancement en 12 points.
> Aucun de ces trois blocs ne peut autoriser un bake, une promotion, un Pool2 v4, ni réinterpréter un terminal immuable.

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

Chiffres terminaux exacts repris tels quels :

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

Diagnostic technique HOME `home-1688` (jamais un résultat de force) :

```text
wall_ratio_t3_over_curriculum = 37.154452
nps_ratio_t3_over_curriculum  = 0.053152
```

---

## 2. Observation qui motive le programme

### 2.1 Décomposition du handicap runtime

Les deux ratios publiés par `1688` se décomposent algébriquement, puisque `wall = nodes / nps` sur une même fenêtre :

```text
nodes_ratio = wall_ratio x nps_ratio = 37.154452 x 0.053152 = 1.974833
```

Le handicap n'est donc pas un seul effet mais **deux effets multiplicatifs distincts** :

| Effet | Facteur | Doublements | Nature |
|---|---:|---:|---|
| coût par nœud (`extract_f6` + MLP) | `18.8140` | `4.2337` | ingénierie |
| inflation de nœuds à profondeur égale | `1.9748` | `0.9817` | qualité d'éval pour l'élagage/l'ordre |
| **handicap total en nœuds-CURRICULUM équivalents** | **`37.1545`** | **`5.2155`** | |

`nodes_ratio = 1.9748` est **déduit algébriquement** des deux ratios publiés par `1688` (build HOME natif, depth 9) et doit être **confirmé par le compteur `nodes` direct** en E1 sur CPX62 ; il n'est pas mesuré tel quel à ce jour. Cette valeur n'avait jamais été relevée et signifie que l'éval T3-A, à profondeur égale, **coûte 1,97× plus de nœuds** que CURRICULUM : c'est un défaut d'éval, pas d'implémentation, et aucune optimisation de coût ne l'enlèvera.

### 2.2 Ce que Pool1 a et n'a pas établi

Sous l'hypothèse `H0_speed` — *toute* la perte de Pool1 est de la famine de nœuds, l'apport d'éval de F6 en jeu est nul — la pente implicite est :

```text
230.6871387863655 / 5.2155 = 44.23 Elo par doublement de nœuds-équivalents
```

Cette valeur est du bon ordre de grandeur pour le damier, donc `−230,69` est **entièrement compatible avec `H0_speed`**. Mais elle est **dérivée du même nombre qu'elle prétend expliquer** : elle ne peut pas servir à prouver `H0_speed`. Conséquence stricte :

> **Pool1 a réfuté T3-A à `0,1 s/coup`. Pool1 n'a pas mesuré la valeur en jeu de l'information F6.** Les deux effets sont confondus et aucune donnée existante ne les sépare.

### 2.3 Pourquoi O1 ne peut pas répondre à la question

O1 est établi côté équivalence (Gates A/B/C PASS) et son Gate D chiffrera le gain de coût. Mais un cache de mémoïsation est borné par `1/(1 − hit_rate)`, la TT dédoublonne déjà les transpositions, et le cycle de vie gelé par le prereg O1 vide le cache à chaque root×budget. Un gain de l'ordre de `≲2×` est donc attendu là où le handicap de coût est de `18,81×`, et O1 **n'agit pas du tout** sur l'inflation de nœuds `1,97×`. O1 reste une bonne hygiène d'ingénierie ; ce n'est pas une route de transfert.

### 2.4 Le coût est concentré, structurellement

Le §2 du prereg O1 décrit `F2 RESPONSE_FRONTIER` : pour **chaque** réponse légale, construction de la position enfant puis nouvel appel `generate_legal_moves`. C'est du `O(b²)` movegen par évaluation statique, là où l'éval pattern de production est incrémentale et quasi gratuite. À `b ≈ 10`, cet unique famille suffit à expliquer l'ordre de grandeur du `18,81×`. **Inférence, non mesurée** : c'est exactement ce que E1 doit trancher.

Corollaire structurel à retenir : F2 calcule au nœud de profondeur `d` une partie du travail que la recherche refait au nœud `d+1`. Le coût de F6 est donc en partie une **duplication du travail de la recherche**, ce qui rend la comparaison « F6 à profondeur `d` » contre « T0 à profondeur `d+1` » la bonne comparaison — et c'est celle que E2 instrumente.

---

## 3. Questions du programme

Trois questions séparées, dans cet ordre, chacune fermable indépendamment :

1. **E1 — où part le coût ?** Quelle famille `F1..F5` consomme quelle part du `18,81×`, et le `1,97×` d'inflation de nœuds se confirme-t-il sur CPX62 ?
2. **E2 — l'information F6 vaut-elle quelque chose en jeu, vitesse neutralisée ?** À **budget de nœuds égal**, l'éval T3-A gelée bat-elle CURRICULUM ?
3. **E3 — le signal survit-il à une projection dans une base à coût runtime nul ?** Quelle fraction du signal F6 subsiste quand F6 ne sert qu'à **ré-étiqueter la cible** d'un fit pattern, sans jamais être calculé en partie ?

E2 est le **verrou** : il conditionne E3 et toute suite runtime.

---

## 4. E1 — attribution du coût (technique, `0` partie, `0` fit)

### 4.1 Intervention gelée

Instrumentation **additive et désactivée par défaut** de `residual_features::extract_f6`, activée par un flag explicite :

1. un chronomètre et des compteurs **par famille** `F1 CAPTURE_GEOMETRY`, `F2 RESPONSE_FRONTIER`, `F3 PROMOTION_RACE`, `F4 STRUCTURE_GRAPH`, `F5 KING_GEOMETRY_PLUS`, plus le MLP seul, plus `base_->evaluate` seul ;
2. par famille : temps mural exclusif, nombre d'appels `generate_legal_moves`, nombre de constructions de position enfant ;
3. **interdiction absolue de modifier une valeur de feature, un ordre, une normalisation, un arrondi, un POV, le MLP, le score de base, le movegen ou le search** ;
4. `threads = 1`, contrat R0-v4 inchangé ;
5. aucune optimisation, aucun refactor, aucun sweep n'est autorisé dans E1 — E1 **mesure**, il ne corrige rien.

### 4.2 Support gelé

Corpus R0-v4 exact `r0-corpus.fen`, `4096` positions, artefact authentifié de `cpx62-1685`. Racines search : fonction `stratified` gelée de `jobs/tools/t3_f6_search_profile.py`, `order_seed = 2026092505`, `32` par phase, soit `128` racines — **identiques à celles de Gate D de O1**, afin que E1 et Gate D soient chiffrables dans le même job et sur les mêmes unités.

Aucun label, aucun score teacher, aucun fresh, aucune cohorte de fit.

### 4.3 Gate E1 — exactitude de la mesure

- **équivalence instrumentation ON vs OFF** : sur les `4096` positions, les 66 features doivent être égales bit-à-bit et le score T3 entier exactement égal. Tout écart donne `E1_INSTRUMENTATION_NOT_EXACT` et STOP : une mesure qui déplace ce qu'elle mesure est nulle et non avenue ;
- somme des temps par famille cohérente avec le temps total `extract_f6` à la résolution de l'horloge près, écart publié ;
- `nodes_ratio` **mesuré directement** à depth `9` sur les `128` racines, publié à côté de la valeur déduite `1.974833` ;
- host/`nproc`/flags de build publiés.

### 4.4 Publication requise

Table par famille : `ns/éval` exclusif, part du coût `extract_f6`, appels movegen/éval, constructions d'enfant/éval. Plus : coût MLP, coût `base_->evaluate`, `nps` des deux bras, `nodes` des deux bras, `wall_ratio` et `nps_ratio` CPX62 face aux valeurs HOME `37.154452` / `0.053152`.

### 4.5 Règle de décision **pré-déclarée** (choix du document suivant, pas un verdict scientifique)

- si **une seule famille concentre `≥ 60 %`** du coût `extract_f6` → une ablation `F6 \ {famille}` devient *preregistrable* (document séparé, jamais lancée par celui-ci) ;
- sinon → il n'existe **pas de levier de coût bon marché** dans F6, la route « student runtime » est déclarée sans issue par ce document, et E3 devient la seule route de transfert.

Dans les deux cas, aucune ablation n'est fittée dans E1, et **la cohorte `1638`/`1639`/`1640` reste interdite à tout fit, tuning, calibration, feature selection ou model selection** : une ablation comparée sur cette cohorte serait de la model selection sur données consommées.

### 4.6 Verdicts E1 autorisés

```text
E1_COST_ATTRIBUTED
E1_INSTRUMENTATION_NOT_EXACT
E1_TECHNICAL_FAILED
```

---

## 5. E2 — A/B à NŒUDS ÉGAUX (le test décisif)

### 5.1 Pourquoi ce n'est pas un rejeu de Pool1

Pool1 est un A/B à **temps** fixe (`0,1 s/coup`). E2 est un A/B à **nœuds** fixes. La question causale est différente — « l'éval décide-t-elle mieux ? » contre « le paquet éval+vitesse joue-t-il mieux ? » — donc une preregistration séparée est requise, et c'est celle-ci. E2 ne réinterprète pas Pool1 et n'autorise aucun Pool2 v4.

### 5.2 Intervention gelée

- bytes T3-A et CURRICULUM **inchangés** (SHA §1), aucun refit, retune, calibration, D1, retrait de feature ;
- search, ordering, pruning, TT, qsearch, terminal/TB **inchangés** ;
- `threads = 1`, book OFF, EGDB **identique et présente des deux côtés**, moteur/state/TT frais par partie ;
- budget **en nœuds par coup, identique pour les deux bras**, `movetime` désarmé ;
- pool d'ouvertures **frais et disjoint de celui de Pool1** (rejouer les mêmes positions de départ n'est pas une réplication) ; seed d'ouvertures pré-déclarée dans le job, publiée dans le terminal ;
- couleurs appariées, chaque ouverture jouée dans les deux sens.

### 5.3 ⚠️ Piège de protocole à neutraliser explicitement

À nœuds égaux, le bras T3-A consomme **~19× le temps mural par coup**. Le `--game-timeout` historique à `180 s` **tirerait** et fabriquerait des nulles — exactement le canal qui n'avait jamais tiré jusqu'ici. Donc, obligatoire :

- `--game-timeout` relevé et **calibré sur le bras lent** ;
- compteur `game skipped` **publié et asserté `= 0`** ; toute valeur non nulle rend la cellule `INCONCLUANT`, jamais « neutre » ;
- `timeout` par shard calibré sur le bras lent (`temps_shard_sain × ~1,3`), monitor de progress committé /~10 min, PID des shards collectés et `wait "${pids[@]}"` — jamais `wait` nu ;
- `RES`/`PROG` dans `$W`, hors arbre git, verdict-clé aussi dans le message de commit.

### 5.4 Cellules gelées

| Cellule | Bras | Budget | N | Rôle |
|---|---|---|---:|---|
| **C1** | T3-A vs CURRICULUM | `20000` nœuds/coup des deux côtés | `1500` | **primaire** : valeur en jeu de l'éval F6, vitesse neutralisée |
| **C2** | CURRICULUM vs CURRICULUM | `20000` contre `10000` nœuds/coup | `800` | **taux de change** : Elo par doublement mesuré sur notre harnais, à notre budget |
| **C3** | CURRICULUM vs CURRICULUM | `20000` des deux côtés | `400` | **garde harnais** : doit sortir ~`0,5` avec `n > 0` |

Justification de `N` : Pool1 a rendu une demi-largeur d'IC95 apparié de `0,00917` en score sur `6000` parties, soit `≈ ±6,4 Elo` au voisinage de `0,5`. En `1/sqrt(N)`, `1500` parties donnent `≈ ±12,7 Elo` et `800` parties `≈ ±17,4 Elo` — largement suffisant pour un effet qui doit dépasser plusieurs dizaines d'Elo pour être exploitable. **Sizer léger, volontairement.**

`C3` est la garde de la règle 10 : `n = 0` ou une cellule symétrique qui ne sort pas ~`0,5` signifie **job cassé**, pas « résultat neutre ».

### 5.5 Prédiction pré-déclarée sous `H0_speed`

À nœuds égaux, le facteur `18,81` de coût par nœud est neutralisé **mais le `1,97×` d'inflation de nœuds ne l'est pas** : T3-A joue encore `≈ 0,98` doublement moins profond à budget de nœuds égal. Donc, si l'apport d'éval de F6 en jeu est nul :

```text
E2 attendu sous H0_speed  ≈  −0.98 x (Elo par doublement mesuré en C2)
                          ≈  −43 Elo si C2 confirme ~44 Elo/doublement
```

Lecture pré-déclarée, `C2` fournissant la pente :

| Résultat C1 | Lecture |
|---|---|
| `C1 ≈ −0,98 × pente(C2)` | compatible avec `H0_speed`, apport d'éval nul → **programme F6 runtime clos** |
| `C1 ≈ 0` | l'apport d'éval compense tout juste l'inflation → marginal, ne justifie pas d'ingénierie |
| `C1` nettement `> 0` | apport d'éval réel **au-delà** de l'inflation → le budget Elo devient chiffrable et attaquer le coût devient rationnel |

**Diagnostic obligatoire** : profondeur moyenne atteinte par bras, `nodes` effectifs par bras, `eval_calls`, temps mural par bras. Sans la profondeur par bras, `C1` n'est pas interprétable.

### 5.6 Budget Elo — critère d'acceptation d'une route runtime

Toute route qui garderait F6 **en partie** devra satisfaire :

```text
gain_eval_mesuré(E2)  >  pente(C2) x log2(cost_ratio_atteint)
```

À titre indicatif, avec une pente de `44,23 Elo/doublement` : `1,5×` de coût → péage `26 Elo` ; `3×` → `70 Elo` ; `18,81×` → `187 Elo`. Ces péages ne sont pas des seuils de PASS : ce sont les bornes qui rendent une décision d'ingénierie défendable.

### 5.7 Verdicts E2 autorisés

```text
E2_F6_EVAL_HELPS_AT_EQUAL_NODES
E2_F6_EVAL_NEUTRAL_OR_HARMFUL_AT_EQUAL_NODES
E2_INCONCLUSIVE_HARNESS
E2_TECHNICAL_FAILED
```

### 5.8 Kill switch pré-déclaré

Si `E2` ne rend pas `E2_F6_EVAL_HELPS_AT_EQUAL_NODES` avec une borne basse d'IC95 strictement positive, alors **E3 n'est pas autorisé non plus** et le programme de transfert F6 est clos par ce document. Raison logique explicite : E3 distille les *décisions* de T3-A dans une base plus pauvre ; une projection lossy de décisions qui ne jouent pas mieux ne peut pas jouer mieux. Aucune exception, aucun repêchage post-hoc.

E2 ne peut en aucun cas autoriser un bake, une promotion ou un Pool2 v4 : c'est une mesure d'attribution, pas une porte de champion.

---

## 6. E3 — distillation dans la base pattern (coût runtime **nul**)

Autorisé **uniquement** si `E2 = E2_F6_EVAL_HELPS_AT_EQUAL_NODES`, et sous un GO explicite distinct.

### 6.1 Principe

F6 ne sert **qu'à l'entraînement**. En partie, l'évaluateur est le modèle pattern de production : `extract_f6` n'est jamais appelé, `wall_ratio = 1` par construction, aucun changement de search, aucun cache, aucune heuristique paresseuse.

Le mécanisme est **exactement le levier de CURRICULUM** — « c'est la cible qui paie, pas le volume » — appliqué au signal F6 : on ne change ni le corpus, ni la recette, ni le volume ; on change **la cible**.

### 6.2 Intervention gelée : ré-étiquetage des paires par T3-A

1. corpus de paires : **le corpus courant du champion, inchangé et byte-identique** (hash publié), aucune position nouvelle, aucun self-play nouveau, aucun search teacher nouveau ;
2. la cohorte `1638`/`1639`/`1640` est **interdite** ici comme partout ;
3. **seule modification** : la préférence de chaque paire de siblings est réordonnée par le **score de T3-A gelé** (SHA `16e5db8f…`) au lieu de la cible historique. Un seul facteur ;
4. T3-A est utilisé comme **étiqueteuse statique** : une éval statique par sibling, **aucune recherche**. C'est ce qui rend cette route abordable — les teachers précédents coûtaient `200000` nœuds par sibling (`q200`), soit plusieurs ordres de grandeur de plus par étiquette ;
5. recette de fit **gelée, telle que gravée** : `--exact-fold` + `--prior-mean <CURRICULUM> --prior-decay 0` + `--lbfgs-gtol 1e-4` + `--l2 1e-5`. Aucun sweep, aucun `decay > 0` (axe clos, `−21,22 Elo`), aucun `λ` (inerte à `decay 0`) ;
6. aucun changement de classe de modèle : pas de NNUE, pas de réseau, pas de feature runtime nouvelle.

### 6.3 Gate offline **avant toute partie** — fidélité de projection

Sur un split held-out du même corpus, seed de split pré-déclarée dans le job :

- `fidelity(M, T3-A)` = accord pairwise entre les préférences du modèle `M` et celles de T3-A ;
- calculée pour `M = pattern distillé` **et** pour `M = CURRICULUM` (le parent) ;
- **plancher relatif, sans constante magique** : `fidelity(distillé, T3-A)` doit être **strictement supérieure** à `fidelity(CURRICULUM, T3-A)`, IC95 bootstrap exclue de zéro sur la différence. Si le ré-étiquetage ne rapproche pas mesurablement le modèle de son teacher, il n'a rien transféré et **aucune partie n'est autorisée** ;
- publier aussi les itérations L-BFGS des deux bras : le signal fiable de convergence est **l'asymétrie du compte d'itérations entre bras appariés**, pas `‖∇‖∞/gtol`.

Verdict de ce gate : `E3_PROJECTION_TRANSFERS` / `E3_PROJECTION_LOSS_TOTAL`.

### 6.4 Porte de force E3

Sous `E3_PROJECTION_TRANSFERS` et GO explicite : `l3-model-gate-v1.sh` standard, contre CURRICULUM, avec `P(Elo>0)` imprimé à côté de l'IC95, `between_pool_z` sur la garde d'hétérogénéité, `PROMOTION_AUTHORIZED = false`. Le critère d'entrée en procédure de bake reste `P(Elo>0) > 95 %` **sur deux pools disjoints chaînés** — c'est une pré-condition, jamais une autorisation, et le bake reste une décision explicite de JFC.

### 6.5 Risque nommé d'avance

La base pattern encode de **l'occupation locale** de cell-sets fixes. `F2 RESPONSE_FRONTIER` est une propriété **dynamique et globale** de la structure des réponses. Prédiction explicite, à falsifier et non à défendre : **`F1`/`F3`/`F4`/`F5` se projettent correctement, `F2` se projette mal.** Si E1 montre que `F2` porte l'essentiel du coût *et* que E3 montre qu'il porte l'essentiel du signal non projetable, alors le signal F6 est structurellement hors de portée de la base pattern, et c'est un résultat négatif propre — pas un échec technique.

### 6.6 Verdicts E3 autorisés

```text
E3_PROJECTION_TRANSFERS
E3_PROJECTION_LOSS_TOTAL
E3_DISTILLED_PATTERN_GAIN_ESTABLISHED
E3_DISTILLED_PATTERN_NO_ESTABLISHED_GAIN
E3_TECHNICAL_FAILED
```

---

## 7. Amendement méthodologique proposé

Ce programme existe parce qu'un gain offline a été publié sans son coût. Règle proposée, applicable à toute la campagne :

> **Aucun verdict offline ne peut désigner un candidat sans publier, à côté de lui, son `wall_ratio` et son `nps_ratio` mesurés.** Un candidat dont le coût runtime n'est pas mesuré n'est pas un candidat : c'est une observation.

`+0,17495` pairwise sans son `37,15×` a coûté `6000` parties pour apprendre qu'un facteur `18,81` de coût par nœud ne se rattrape pas. La règle est portée dans `CLAUDE.md` par un commit **séparé et détachable** de cette PR.

---

## 8. Interdictions communes E1/E2/E3

- aucune promotion, aucun bake, aucun Pool2 v4 ;
- aucune réinterprétation des terminaux `1685`, `1686`, `1688`, `1689`, `1700` ;
- aucun usage de la cohorte `1638`/`1639`/`1640` pour un fit, tuning, calibration, feature selection ou model selection ;
- aucun nouveau modèle, aucun NNUE, aucun changement de classe ;
- aucun D1, aucun retrait ni approximation de feature F6 dans E1/E2 ;
- aucun changement de search dans E1/E2/E3 ;
- aucun sweep opportuniste, aucune sélection de variante sur Pool1 ;
- aucun `decay > 0`, aucun balayage de `λ` (axes clos) ;
- E1 ne corrige rien, E2 n'optimise rien, E3 ne change qu'une cible ;
- le merge de ce document ne lance rien.

---

## 9. Check-list pré-lancement, par bloc

| Point | E1 | E2 | E3 |
|---|---|---|---|
| `nproc` réel imprimé par le job | requis | requis | requis |
| rate **mesuré** sur la box (micro-sonde ou PROGRESS comparable) | requis | requis, **sur le bras lent** | requis |
| ETA chiffrée = volume ÷ rate + build + fit + gate | requis | requis | requis |
| sizer léger (< ~30-45 min par défaut) | attendu | `N` déjà réduit à `1500`/`800`/`400` | fit léger |
| `timeout` par shard calibré sur le bras lent | s.o. | **critique** | s.o. |
| monitor committé /~10 min + `wait "${pids[@]}"` | s.o. | requis | requis |
| garde `df` + auto-clean `cw-*` stale | requis | requis | requis |
| `RES`/`PROG` dans `$W`, verdict dans le message de commit | requis | requis | requis |
| smoke-test write→read, `bash -n`, `py_compile` | requis | requis | requis |
| `n = 0` ou `n < plancher` ⇒ ABORT/INCONCLUANT, jamais « neutre » | requis | requis | requis |
| garde-fou archi (`g_emasks`, `has_any_capture`) avant `cmake` | requis | requis | requis |
| GO explicite JFC sur ETA + sizing | requis | requis, distinct | requis, distinct |

E1 étant sur les mêmes `128` racines et le même exécutable que Gate D de O1, **les deux peuvent être chiffrés dans un seul job** ; le prereg O1 prévoit déjà la publication de la famille `F1..F5` « si disponibles », et E1 est précisément ce qui les rend disponibles.

---

## 10. Traçabilité requise

Chaque terminal du programme publie : code SHA, bytes T3-A/CURRICULUM, host/`nproc`/flags de build, `threads = 1`, source exacte des racines (`r0-corpus.fen` + `stratified` seed `2026092505` + préfixe par phase), seeds d'ouvertures et de split, budgets en nœuds, `game skipped`, profondeur et `nodes` par bras, `wall_ratio`/`nps_ratio` mesurés, compteurs par famille pour E1, fidélité de projection et itérations L-BFGS pour E3, `P(Elo>0)` à côté de l'IC95 pour toute porte de force, et le verdict exact pris dans les listes ci-dessus.

Les terminaux `1685`, `1686`, `1688`, `1689` et `1700` restent immuables et doivent être référencés, jamais réécrits.
