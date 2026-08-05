# L3 — état courant et registre de décision

> **Mis à jour : 5 août 2026**
> **Source de vérité active : ce document.** L’historique consolidé reste dans
> [`PROJECT_RESULTS.md`](PROJECT_RESULTS.md), les verdicts immuables sous
> [`archives/l3/`](archives/l3/), le contrat généraliste dans
> [`L3_PURE_PLAN.md`](L3_PURE_PLAN.md) et la séparation des rôles dans
> [`L3_LINEAGE_ROLES_AND_MATURITY.md`](L3_LINEAGE_ROLES_AND_MATURITY.md).
>
> **Statut scientifique :** `c0_pure_at_gen2_practical_parity;
> c0_retire_frontier_v1_flat; c1_q1_no_lead; c2_x1_no_lead;
> c3_mf_no_lead; 32cf_no_go_data_limited; pure_maturity_experiment_open;
> imbalance2_p1_v2_no_clear_lead; imbalance2_p2_no_clear_improvement_or_unstable;
> imbalance2_stop_before_p3_redesign; d0_causal_profile_ready; d1_rc4_no_go;
> d1x_rc4_autopsy_ready; top3_causal_conversion_matrix_ready;
> l3_pure_top3_causal_conversion_ready;
> top3_specialist_recipe_failure_localized_factors_confounded;
> conversion_2x2_cap_discovery_complete_three_caps;
> conversion_2x2_finalizer_home_ready;
> pure_maturity_m0_complete_parent_c0_selected_for_m1;
> f2m_general_champion; m2_d8_plateau; d10_plateau;
> d12_q00_regression; depth_mix_trigger_blocked;
> turnover_1to1_effect_confirmed; replay25_dose_closed;
> turnover_l2_1e4_rejected; turnover_l2_1e5_not_replicated;
> l2_factor_closed_on_3e5; views_agree_no_view_effect;
> screens_underpowered_below_17_elo;
> replay_dose_axis_closed_optimum_50;
> turnover50_promoted_general_champion;
> exact_fold_promoted_general_champion;
> onpolicy_single_factor_flat_coverage_is_the_binding_constraint;
> coverage_knob_is_random_open_plies_plateau_at_24;
> coverage_is_not_the_lever_refuted_by_gate;
> conversion_benchmark_of_july_is_unusable;
> scan_blind_spot_exact_gen2_differential_measured;
> quiescence_q01_reopen_closed_current_engine;
> lbfgs_gtol_1e3_was_stopping_short_exact_and_prior_underconverged;
> lbfgs_gtol_axis_closed_1e5_unreachable;
> priortight_promoted_general_champion;
> l2low_promoted_general_champion;
> l2_reopened_under_prior_mean_and_closed_by_plateau_1e5_to_3e6;
> king_patterns_gate_played_flat_upper_bound_8_8_elo;
> king_aware_gate_blocked_on_per_arm_build;
> fresh12m_corpus_generated_endgame_content_34x_higher;
> draw_labelling_defect_not_visible_in_published_corpora_claim_retracted;
> post_epsilon_contamination_measured_19_75_percent;
> signal_factory_charter_opened;
> volume_axis_did_NOT_replicate_on_a_second_pool_chained_p_gt_0_is_80_6_percent;
> single_pool_posteriors_are_inflated_by_the_pool_draw_measured_3_45_to_0_32;
> bake_criterion_p_gt_0_over_95_percent_on_chained_pools_first_application_REFUSED;
> gates_now_report_a_flat_prior_posterior_alongside_the_ci;
> label_noise_24_percent_against_tablebase_replicated_two_corpora;
> m1_signal_report_validated_against_engine_counters_exactly`.

## 0quater. 5 août 2026 — ⛔ LE VOLUME NE BRIDE PAS, ET LES ÉTIQUETTES SI

### ⚖️ `cpx62-1179` — la porte du volume est PLATE

```
n=12000   VOL12M 5718W 683D 5599L contre L2LOW
taux = 0,5050   Elo = +3,45   IC95 = [−2,6 ; +9,5]
VERDICT  A_FLAT_VS_B_NO_ESTABLISHED_GAIN
```

Les deux vues concordent, ce qui écarte un artefact de cadence :

| vue | n | W-D-L | Elo | IC95 |
|---|---:|---|---:|---|
| q00 (d9 fixe) | 6 000 | 2854-340-2806 | +2,78 | [−5,8 ; +11,3] |
| native (mt 0,1) | 6 000 | 2864-343-2793 | +4,11 | [−4,4 ; +12,7] |
| **total** | **12 000** | 5718-683-5599 | **+3,45** | **[−2,6 ; +9,5]** |

⛔ **La borne haute `+9,5` est SOUS TOUS les gains encaissés** : fold exact
`+17,10` `[+9,2 ; +25,0]`, PRIORTIGHT `+18,05` `[+12,0 ; +24,1]`, L2LOW
`+11,31` `[+6,4 ; +16,3]`. Un gain de l'ordre de ceux qu'on sait produire est
exclu.

⚠️ **Et ce n'était PAS un test à un seul facteur** — corrigé avant que le job
ne rende. **Deux leviers ont bougé ensemble** : le volume (2 M → 12 M, soit
**4,3 → 42,14 observations par paramètre libre**) *et* la teneur en finales
(0,52 % → 12,19 %, **23×**). **Les deux ensemble ne rendent rien.** La
confusion ne sauve rien ici : elle élargit le négatif.

⚠️ **RECTIFICATIF DU 5 AOÛT — j'avais écrit « la famine de données est RÉFUTÉE »
et « axe clos ». C'est une sur-lecture du cadre fréquentiste, et JFC a eu raison
de la refuser.** « L'IC contient zéro » jette l'information que porte la
**position de la masse**. Lecture bayésienne du même jeu de parties, prior plat
sur le taux :

| seuil | `P(Elo > seuil)` |
|---|---:|
| **0** | **86,8 %** |
| 3 | 55,8 % |
| 5 | 30,7 % |
| 10 | **1,7 %** |
| 17 | 0,0 % |

✅ **Ce que les données disent vraiment : un effet POSITIF est probable (87 %),
un effet GRAND est presque exclu (1,7 % au-delà de +10).** C'est une borne
supérieure, pas une porte close.

⛔ **L'AXE DU VOLUME N'EST DONC PAS CLOS**, et le mécanisme avancé par JFC tient
debout : à 8-13 % de buckets visités et avec une éval encore faible, le
générateur ne produit peut-être pas encore des parties assez informatives pour
que le volume rende ce qu'il pourrait. **Préchauffage**, pas plafond. Le chiffre
honnête à retenir est : *au niveau d'éval ACTUEL et avec le générateur ACTUEL,
6× de données valent ~+3,5 Elo, avec 87 % de chances d'être positif et moins de
2 % d'être au-delà de +10.*

⚠️ **Sur la comparaison des deux vues** : `q00` et `native` **ne sont pas deux
pools indépendants**. Elles partagent les 3 000 ouvertures **et** les deux
modèles ; seule la cadence change. Leur concordance dit que l'effet est robuste
au contrôle de temps, elle **ne double pas** l'évidence. La vraie réplication
indépendante est celle que `home-1312` rendra possible.

✅ **DÉCISION DE MÉTHODE, appliquée à partir du 5 août** : toute porte rapporte
désormais **`P(Elo > 0/3/5/10/17)` sous prior plat, À CÔTÉ de l'IC95**. Le
verdict reste fréquentiste pour ne pas casser la comparabilité avec les portes
antérieures, mais le posterior est ce qu'on lit. Et pour un second pool disjoint,
**le posterior du premier devient le prior du second** — c'est exactement la mise
à jour séquentielle, et elle donne un `P(>0)` courant au lieu de deux verdicts
qu'il faudrait recoller à la main.

### ⛓️ `cpx62-1184` — LE VOLUME NE RÉPLIQUE PAS, et le critère de bake REFUSE

Première application de bout en bout du critère fixé par JFC (`P(Elo>0) > 95 %`
sur pools chaînés). Le même couple VOL12M vs L2LOW, rejoué sur le pool
d'ouvertures **neuf et disjoint** `big3000b` (`cpx62-1183`), avec le posterior
de `cpx62-1179` en prior :

| | n | Elo | P(Elo>0) |
|---|---:|---:|---:|
| pool 1 (`big3000`) | 12 000 | **+3,45** | **86,8 %** |
| pool 2 (`big3000b`) | 12 000 | **+0,32** | **54,1 %** |
| **⛓️ combiné** | **24 000** | **+1,89** | **80,6 %** |

`accord des pools : z = −0,72 → COHERENTS` — la garde d'hétérogénéité ne se
déclenche pas, donc le chaînage est légitime et le combiné est la bonne
estimation.

```
critere de bake (P(Elo>0)>95 % sur pools chaines) : NON REMPLI — P(elo>0)=0.8064
```

⛔ **LEÇON DE MÉTHODE, ET ELLE COÛTE CHER À OUBLIER : un posterior sur UN SEUL
POOL est gonflé par le tirage du pool.** `+3,45` à 86,8 % s'est révélé être
`+1,89` à 80,6 % une fois répliqué. Ce n'est pas une contradiction — les deux
pools sont statistiquement compatibles — c'est la variance inter-pool qui
n'était pas dans l'intervalle. **Aucun verdict à un seul pool ne doit plus être
présenté comme une estimation de l'effet.**

⚠️ **Et ça vaut pour `C2`** : son `+3,04` à 83,8 % (`cpx62-1182`) vient d'un seul
pool, exactement comme le `+3,45` qui vient de se dégonfler de moitié. Rien ne
dit qu'il y échappera.

Par vue sur le pool 2 : `q00 +2,84` (74,2 %), `native −2,20` (30,7 %).

**L'axe du volume n'est pas clos** — 80,6 % restent du bon côté — mais la
meilleure estimation est désormais **~+2 Elo, incertitude couvrant zéro**, et
`P(Elo>10) = 0,0 %`.

### ✅ `cpx62-1180` — M1 est validé contre les compteurs du moteur, à l'unité près

Première fiche signalétique du projet, sur le pool JSM2 de `home-1311`.
Confrontation avec `LABELHYG`/`WDLDIST` agrégés sur les 12 shards **du même
corpus** :

| | moteur | M1 |
|---|---:|---:|
| records | 12 000 000 | **12 000 000** ✓ |
| nulles | 2 181 722 (18,18 %) | **2 181 722 (18,18 %)** ✓ |
| gains / pertes | 4 929 463 / 4 888 815 | **identiques** ✓ |
| contamination, compte brut | 2 615 928 | **2 615 928** ✓ |
| contamination, part | 19,75 % *(dénom. candidats)* | 21,80 % *(dénom. records gardés)* |

Concordance **exacte sur chaque compte brut**, et l'écart de part est
précisément celui pour lequel la charte a été corrigée : même numérateur, deux
dénominateurs. Réconciliation des parties, non anticipée et pourtant exacte :

```
393 959 parties jouées − 19 141 au ply-cap = 374 818 = parties vues par M1   (écart : 0)
```

Le **contrôle croisé des POV a passé sur les 12 000 000 de records** — pas un
échantillon, tous.

⚠️ **Piège de lecture** : la couverture de M1 sort à **8,117 %** contre 13,396 %
au certificat de `home-1310`. **Ce n'est pas une régression** : M1 mesure en
**fold exact**, le certificat en **fold couleur**. Le rapport porte lui-même
l'avertissement. Ces deux chiffres ne se comparent jamais.

### 🎯 Le bruit d'étiquetage réplique sur deux corpus indépendants

| corpus | in_range | **désaccord** | inversions |
|---|---:|---:|---:|
| `home-1310` (12 M) | 1 971 484 | **24,23 %** | 0,51 % |
| `home-1311` (12 M, graine distincte) | 1 967 602 | **24,12 %** | 0,52 % |

Décomposition sur `home-1310` : **90,2 % de tout le désaccord est une étiquette
DÉCISIVE posée sur une position THÉORIQUEMENT NULLE** (431 032 positions). Les
vraies inversions gain↔perte sont à **0,51 %** : le bruit n'est pas du hasard,
c'est **un biais directionnel unique**. `--tb-relabel` corrigerait **477 627
étiquettes = 3,98 % du corpus entier**, et il est **à zéro depuis toujours**.

**Par élimination, la qualité des étiquettes devient l'hypothèse principale**,
et la cellule C2 de M3 (`--tb-relabel`) cesse d'être une cellule parmi quatre.

## 0ter. Nuit du 4 au 5 août 2026 — le premier corpus du moteur réparé

### Le corpus `home-1310` — 12 M de positions, 100 % fraîches, jouées par L2LOW à d8

Terminé le 4 août à **22h30 FR**, `exit 0`, **3h06**. Publié sous
`r2:jass-data/runs/home-1310-claude-fresh12m-l2low-gen-at-c7f27ff9-v1/20260804T172424Z-c7f27ff9`.
C'est le premier corpus de la campagne généré par le moteur d'après `9c1d1e8e`,
et à ce volume.

**⚠️ Deux facteurs bougent d'un coup, et c'est assumé** : le volume (12 M contre
2 M) *et* la **teneur en finales**. Aucun verdict de force ne pourra donc
attribuer un écart à l'un plutôt qu'à l'autre — ce corpus sert à **nourrir**,
pas à **trancher**.

**1. ⛔ RECTIFICATIF DU 5 AOÛT — « l'étiquetage des nulles est réparé » ÉTAIT FAUX**

> Cette section affirmait que `home-1310` faisait passer les nulles de **4,8 %**
> à **18,26 %**, « facteur 3,8× récupéré ». **La mesure directe sur les fichiers
> réfute la prémisse** : TURNOVER **et ses trois sources** sont déjà à ~21 % de
> nulles. Il n'y avait rien à réparer sur ces corpus, et le nouveau en a
> légèrement **moins**, pas plus.

| corpus | n | **nulles** | 3-7 pièces |
|---|---:|---:|---:|
| TURNOVER 2 M *(parent de L2LOW)* | 2 000 000 | **21,41 %** | 0,52 % |
| ↳ source `f2m-common` | 500 000 | 21,17 % | 0,50 % |
| ↳ source `f2m-extra` | 1 500 000 | 20,88 % | 0,51 % |
| ↳ source `m2-d8` | 2 000 000 | 21,85 % | 0,51 % |
| VOL8M 12 M *(home-1004)* | 12 000 000 | 18,67 % | 12,19 % |
| `home-1310` 12 M | 12 000 000 | **18,24 %** | **17,51 %** |

Méthode contrôlée : sur `home-1310` la mesure indépendante donne **18,24 %** là
où le canari du job avait imprimé **18,2586 %** — même chiffre, donc le lecteur
est bon.

✅ **Ce que `home-1310` change RÉELLEMENT, et c'est plus intéressant : la TENEUR
EN FINALES.** `0,52 % → 12,19 % → 17,51 %` de positions à 3-7 pièces, soit un
**facteur 34** entre TURNOVER et `home-1310`. **Toute la lignée jusqu'à L2LOW
s'est entraînée sur un corpus quasi dépourvu de finales**, pendant qu'on mesure
par ailleurs que Scan nous bat par la qualité d'évaluation.

Signature qui désigne le mécanisme : les 10 320 positions basses de TURNOVER
sont **toutes exactement à 7 pièces**, aucune en dessous — un plancher net, là
où `home-1310` s'étale sur 3, 4, 5, 6, 7. C'est la marque du `terminate-at-TB`,
qui coupe la partie dès l'entrée dans la base. Hypothèse cohérente avec tout ce
qu'on mesure, pas encore prouvée : TURNOVER a été généré **avec** une base qui
répond jusqu'à 6 pièces, `home-1310` **sans**.

Les autres compteurs de `home-1310` restent valides : gains 41,09 %, pertes
40,65 %, **biais de camp 0,44 %** (harnais symétrique), canari WDL vert sur les
12 shards.

**2. Volume et couverture**

| | TURNOVER (2 M) | `home-1310` (12 M) |
|---|---|---|
| buckets visités | 208 914 (**9,8 %**) | **284 771 (13,40 %)** |
| buckets ≥ 100 visites | — | 66 625 |
| **observations / paramètre libre** | **4,3** | **42,14** |
| gini de concentration | — | 0,916 |
| heuristique de capacité | — | `data_limited_more_capacity_not_justified` |

**×9,8 sur les observations par paramètre libre.** Noter que la couverture ne
progresse que de 9,8 à 13,4 % pour **6× le volume** : cohérent avec l'acquis du
1er août, la couverture n'est pas le levier et ne doit pas être lue comme un
progrès.

**3. Hygiène d'étiquetage — les compteurs du générateur, agrégés sur 12 shards**

| compteur | valeur | lecture |
|---|---|---|
| échantillons candidats | 13 226 109 | → 12 000 000 gardés |
| **contaminés (post-epsilon)** | **2 611 826 = 19,75 %** | cible de `--drop-post-eps`, **toujours off** |
| parties au plafond de plies | 18 879 / 393 304 = **4,80 %** | coûtent 1 226 109 échantillons (**9,27 %**) |
| `dropped_post_eps` / `tb_relabel` / `adjudicated` | **0 / 0 / 0** | tous les boutons d'hygiène sont fermés |
| événements epsilon | 960 103 / 52 894 174 plies = 1,82 % | dont **694 589 (72,3 %) ont changé le meilleur coup** |
| parties contenant ≥ 1 epsilon | 361 490 / 393 304 = **91,9 %** | |

⚠️ **Un cinquième du corpus porte une étiquette qui parle d'une partie détournée
après lui.** C'est le plus gros chiffre du tableau, et c'est la cellule C1 du
jalon M3 de [`L3_SIGNAL_FACTORY_CHARTER_20260804.md`](experiments/L3_SIGNAL_FACTORY_CHARTER_20260804.md).

### ⏱️ Ancre de débit ré-ancrée sur HOME — l'ancienne était optimiste de 37 %

ETA annoncée **1h30**, réalisée **3h06 = 2,07×**. Cause unique : **ancre de
débit transportée sans être re-mesurée** — check-list point 2, la faute même de
0665.

- ancre utilisée : 9 804 pos/min/shard (`home-1003`/`1004`)
- **mesuré : 6 210 pos/min/shard**, 74 500/min au total sur 12 producteurs — **−37 %**
- génération 17h46 → 20h27 UTC = **2h41** ; le reste (build, fetch, mix, split,
  couverture, pool d'éval) = 25 min
- dispersion des shards : **5 minutes sur 12**, aucun traînard

> **✅ NOUVELLE ANCRE HOME À UTILISER** : `--gen-data-wdl` **d8**, étiquetage d4,
> joueur L2LOW, 12 producteurs → **6 210 pos KEPT/min/shard**, **74 500/min au
> total**. L'ancre `home-1003`/`1004` à 9 804 pos/min/shard date d'un autre
> modèle et ne doit plus servir à sizer.

## 0bis. Nuit du 2 au 3 août 2026 — la tolérance du solveur

Travail mené en autonomie sur mandat de JFC. **Le résultat de la nuit n'est pas
un gain de méthode d'évaluation : c'est la découverte que le solveur s'arrêtait
trop tôt depuis le début de la campagne.**

Sous `--lbfgs-gtol 1e-3` — la valeur de toute la campagne — L-BFGS s'arrêtait à
**141** itérations pour la recette EXACT et **169** pour la recette PRIOR. Les
mêmes recettes, sur les mêmes données, en prennent **653** et **904** sous
`1e-4`. `success=True` était rendu dans les deux cas : `scipy` rapporte le succès
aussi bien sur convergence du gradient que sur `max_iter`, ce qui a masqué le
problème pendant des semaines. **Le signal fiable est l'asymétrie du compte
d'itérations entre bras appariés, pas le rapport `‖∇‖∞/gtol`** — les bras
convergés atterrissent à `0,88` et `0,97` de cette surface, parce que le solveur
s'arrête naturellement juste après le seuil.

| ce qui change | cellule | pool | n | Elo | IC95 |
|---|---|---|---:|---:|---|
| tolérance, sur `warm` | `cpx62-1157` | `home-1004` | 6000 | `+15,99` | `[+7,4 ; +24,6]` |
| tolérance, sur `prior` | `cpx62-1163` | `big3000` | 12000 | `+18,05` | `[+12,0 ; +24,1]` |
| prior à `1e-4`, consolidé | deux pools | 18 000 | `+8,48` | `[+3,5 ; +13,4]` |

Deux mesures indépendantes de la tolérance, sur deux recettes et deux pools,
tombent à `+15,99` et `+18,05`. Le prior survit au resserrement (`+8,48` contre
`+6,66` à `1e-3`, intervalles recouvrants) : les deux corrections sont
**distinctes et cumulatives**.

⚠️ `cpx62-1158` (`+12,05`) opposait **deux facteurs à la fois** (continuation
`warm`→`prior` ET tolérance) ; il ne doit pas être lu comme la mesure d'un
bouton. `cpx62-1163` le remplace, à un facteur et à double puissance.

✅ **`1e-5` N'EST PAS ATTEIGNABLE — l'axe de tolérance est CLOS à `1e-4`**
(`home-1210`, 3 août). Le bras `1e-5` s'arrête sur le critère de **fonction**, pas
de gradient : `CONVERGENCE: REL_REDUCTION_OF_F_<=_FACTR*EPSMCH` après **1048**
itérations, à `‖∇‖∞ = 1,448e-4` — soit **pire** que les `8,68e-5` que le bras
`1e-4` atteint en `801` itérations. L-BFGS-B bute sur le plancher de réduction
relative de `f` avant de pouvoir satisfaire le test de gradient. Le seul bouton
qui irait plus loin est `ftol` (défaut scipy `2,22e-9`), **non exposé** par
`train_stream.py` ; à ce stade on poursuivrait du bruit numérique.

✅ **Le garde fail-closed a fonctionné du premier coup** : le job a refusé de
publier et n'a lancé aucune porte sur un fit qui ne s'était pas arrêté sur le
gradient. `success=True` était pourtant rendu — c'est exactement le piège que le
durcissement visait.

⚠️ **LES FITS NE SONT PAS COMPARABLES D'UNE BOX À L'AUTRE.** Le bras `1e-4` de
`home-1210` **ne reproduit pas** le contrôle de `cpx62-1159` : `801` itérations,
`‖∇‖∞ 8,683e-5`, holdout `0,441615` contre `653`, `9,711e-5`, `0,441695`. La
cause est imprimée dans le log — HOME a tourné la pile **`historical`**
(numpy 1.26.4 / scipy 1.14.1), cpx62 la pile **`current`** (numpy 2.5.1 /
scipy 1.18.0). **Ce n'est pas du non-déterminisme**, mais cela veut dire qu'un
bras fitté sur une box ne se compare pas à un bras fitté sur l'autre. Toutes les
conclusions de la nuit reposent sur des **bras appariés dans un même job**, ce
qui est la bonne conception ; il faut qu'elle le reste.

⚠️ Le fit du champion candidat (`cpx62-1159`, bras `exact`) a convergé sur le
gradient à **904 itérations sous un plafond de 1000** — 9,6 % de marge. Le
plafond a été porté à 5000 depuis (`7025b63f`), mais le modèle lui-même a été
produit sous l'ancien. Il est convergé ; la marge était mince.

**Contrôle non prévu qui tient** : TIGHT produit par `cpx62-1156` et le bras
`control` de `cpx62-1159` — deux jobs, deux dates, même recette — sont
**byte-identiques** (`9c550a9b…`).

⛔ **La porte king-aware n'est pas jouable telle quelle** : un modèle
`--king-patterns` exige un moteur compilé `-DJASS_KING_PATTERNS`, et
`l3-model-gate-v1.sh` ne produit **qu'un seul build** pour les deux bras. Il faut
un build **par bras**, comme `l3-succession-guards-v1.sh` le fait déjà pour
opposer 8cf et 32cf. ✅ Aucun risque silencieux : `scan_eval.cpp:370` refuse un
modèle dont le bit king de l'en-tête contredit le build.

## 0. État au soir du 1er août 2026

Résumé de journée. Un seul gain, trois familles fermées, une question ouverte
sur le moteur.

### 0.1 Le champion, et il est solide

**EXACT est le champion général courant**, promu le 1er août sur go explicite de
JFC après `cpx62-1129`, puis **solidifié 3/3** dans la soirée :

| garde | résultat | repère |
|---|---|---|
| primaire, deux pools disjoints | **`+13,09 Elo`** IC95 `[+6,9 ; +19,3]`, `n = 12 000` | `1129` + `1135` |
| non-régression Gen2 | **`+68,21 Elo`**, `59,69 %`, deux vues positives | TURNOVER : `+62,03` |
| conversion P3/P4 | **à égalité avec TURNOVER** : `−1,83 pp`, IC95 `[−5,51 ; +1,85]`, McNemar `z = −0,98`, 600 positions appariées | repère de juillet **invalide**, cf. §0.4 |

Les trois « ce que cette promotion n'établit pas » de l'enregistrement du matin
sont donc **levés**. Détail : [`experiments/L3_EXACT_PROMOTION_20260801.md`](experiments/L3_EXACT_PROMOTION_20260801.md).

### 0.2 Le seul gain de la journée ne vient d'aucune donnée neuve

`--exact-fold` vaut `+15,12 Elo` contre TURNOVER avec EGDB, et `+17,10` contre
son propre contrôle. **Aucune donnée neuve, aucune capacité neuve** : même
corpus, même recette, `TB` identique. La campagne imposait exactement `cs`
seule — qui n'est **pas** une symétrie du damier — pendant que la seule exacte,
`rot180 ∘ cs`, était violée à `25,8 %`. Le gain est une **correction de
méthode à corpus constant**, et c'est la seule chose qui a payé aujourd'hui.

### 0.3 Trois familles fermées, toutes du côté « produire plus »

| famille | mesure | verdict |
|---|---|---|
| autojeu on-policy à recette constante | `1127`/`1130` : `−4,05 Elo` IC95 `[−12,6 ; +4,5]` | **PLAT** — pas de régression, mais borne haute excluant un gain de l'ordre du fold |
| couverture achetée par les ouvertures | `1131`→`1134` : `+2,83 %` de buckets, **`−9,27 Elo`** IC95 `[−17,9 ; −0,7]` | **RÉGRESSION ÉTABLIE** — couverture et force en sens opposé |
| exploration structurée (top-k) | `1131` : `−2,14 %` de couverture, `+16,4 %` de nulles | **fermée**, négative des deux côtés |

⚠️ **Correction d'une inférence à moi** : à `1130` j'ai inscrit la couverture
comme « le mécanisme mesuré » du plat on-policy. Le `−3,9 %` était mesuré ; son
**rôle causal ne l'était pas**. La chaîne `1131`→`1134` l'a testé dans le sens
qu'il prédisait et l'a **falsifié**. Le plat on-policy reste un fait ; son
explication est **rouverte**.

⛔ **Un compte de buckets est un diagnostic, pas un critère de sélection** — au
même rang que la loss holdout. Trois familles ont fermé sur ce motif
(hard-replay v1 `−648 Elo`, VOL8M `−14,95`, celle-ci).

### 0.4 La question ouverte, et elle peut être la plus importante

La cellule de conversion a trouvé autre chose que ce qu'elle cherchait. À
**modèle constant** (TURNOVER inchangé), défenseur figé des deux côtés, jauges
et pool épinglés par hash, mesure déterministe à profondeur fixe :

```text
                                  n_win   n_draw   n_loss
TURNOVER, moteur du 27 juillet      591       0        9      -> 0,98 / 0,99
TURNOVER, moteur d'aujourd'hui      457      33      110      -> 0,7633 / 0,7600
```

**`−22,3 pp` sur le même modèle.** La seule chose qui a bougé est le moteur de
l'attaquant — neuf commits sur `src/`.

**Zéro nulle sur 600 positions n'est pas un résultat plausible** : c'est
l'empreinte du bug corrigé par `9c1d1e8e` (avant lui, `search()` rendait un coup
nul sur **toute** racine nulle par répétition ou horloge). ⛔ **Le repère
`0,98`/`0,99` de `home-0996` ne doit plus être cité comme plancher.** Ce qui
reste indécidé est *combien* des 110 défaites d'aujourd'hui sont réelles.

**TRANCHÉ le 1er août au soir (`cpx62-1142`) : aucune régression du moteur.**
L'archéologie à `e913d66d` était une impasse — ce moteur ne sait pas jouer une
racine nulle, donc il ne peut pas reproduire sa propre mesure, et `1139` a tenu
80 min sans rendre. *(J'avais affirmé à tort que la conversion échappait aux deux
bugs : c'est vrai du bug movetime, **faux du bug racine-nulle**, qui ne dépend
pas de la profondeur.)* Le bisect est donc reparti de **`9c1d1e8e` lui-même**, le
premier commit qui sait jouer le test :

```text
TURNOVER, attaquant figé à 9c1d1e8e   p3 = 0,7633 (W229 D19 L52)   p4 = 0,7600 (W228 D14 L58)
TURNOVER, moteur d'aujourd'hui        p3 = 0,7633 (W229 D19 L52)   p4 = 0,7600 (W228 D14 L58)
```

**Identiques à la position près.** Les huit commits postérieurs à `9c1d1e8e` sont
donc **prouvés neutres** pour cette mesure — bit à bit, pas « probablement ». La
totalité des `−22,3 pp` s'explique par `9c1d1e8e` lui-même, c'est-à-dire **par la
CORRECTION du bug**, pas par une régression.

⛔ **Le `0,98`/`0,99` de `home-0996` est un ARTEFACT et ne doit plus jamais être
cité comme plancher.** Le moteur d'alors rendait un coup nul sur toute racine
nulle par répétition : les nulles n'étaient pas enregistrables (`0` sur 600) et
se retrouvaient comptées gagnées. **Le plancher honnête vaut ~`0,76`** pour
TURNOVER comme pour EXACT, lesquels restent indistinguables entre eux. Tout
`CONV_FLOOR` doit être recalibré là-dessus ; celui de `1137` (`0,95`) était hérité
du chiffre faux, ce qui rendait son verdict `RED` mécanique et sans contenu.

✅ **Bénéfice collatéral : le harnais de conversion est parfaitement
déterministe.** Deux builds distincts à cinq semaines d'écart, deux exécutions
séparées, compteurs identiques à l'unité. Toute mesure future sur cette cellule
part d'une base sûre.

### 0.5 Quiescence Q01 rejouée : porte refermée

La cellule décisive `Q01_SACS` de `home-0812` a été rejouée seule contre `Q00`
avec le moteur courant et le champion EXACT, selon la règle préenregistrée dans
[`experiments/L3_QUIESCENCE_REOPEN_PREREGISTRATION_20260802.md`](experiments/L3_QUIESCENCE_REOPEN_PREREGISTRATION_20260802.md).
Le bug racine-nulle antérieur à `9c1d1e8e` constituait le motif de réouverture,
**pas une cause tenue pour acquise**.

| vue | mesure Q01 vs Q00 | décision préenregistrée |
|---|---|---|
| force native, co-primaire | `0,508333`, IC97,5 `[0,488435 ; 0,528231]`, `n = 3000` | **plate** |
| conversion P3/P4 appariée, co-primaire | `+1,1667 pp`, IC97,5 `[−1,0000 ; +3,3333]`, `n = 600` | **plate** |
| profondeur 9, diagnostic seul | `0,529333`, IC97,5 `[0,509398 ; 0,549268]`, `n = 3000` | mouvement positif, **non décisif** |

Les deux co-primaires franchissent leur nul ; conformément au contrat,
**`QUIESCENCE_CLOSE_CONFIRMED`**. Le signal à profondeur 9 ne peut pas rouvrir
`0812`, puisqu'il avait été explicitement relégué au rang diagnostique avant de
voir les chiffres. Aucune promotion et aucune continuation automatique.

Les `7200` observations de
`home-1200-l3-quiescence-q01-reopen-v1` étaient complètes ; ce job a échoué
après calcul sur la seule sérialisation JSON d'un `numpy.bool_`. Le readout
`home-1202-codex-quiescence-q01-readout-at-ddec2fc6-v2` les a relues depuis le
`result_uri` immuable, vérifié leurs checksums et publié le verdict sans rejouer
une partie :
`r2:jass-data/runs/home-1202-codex-quiescence-q01-readout-at-ddec2fc6-v2/20260802T125117Z-ddec2fc6`.

### 0.6 Deux leçons de méthode, à garder

1. **Une porte appariée ne peut pas voir ce qui frappe ses deux bras.** Toutes
   les portes de la journée partageaient un binaire : leurs verdicts tiennent,
   et tiendraient tout autant si le moteur avait perdu 20 points dans l'absolu.
   La cellule à défenseur figé est le seul instrument qui voit une dérive
   **absolue**.
2. **Protéger la moitié d'un instrument ne protège rien.** La cellule figeait le
   défenseur et laissait l'attaquant suivre `develop`. Chaque choix se défend
   seul ; ensemble ils rendent tout chiffre de conversion incomparable dans le
   temps. `ATTACKER_CODE_SHA` existe désormais, mais la règle est antérieure au
   correctif : **une série temporelle exige que TOUT l'instrument soit épinglé.**

### 0.7 Outillage produit aujourd'hui

- `l3-succession-guards-v1.sh` — les deux gardes de succession pour un
  challengeur quelconque (binaire 32cf pour Gen2, défenseur figé, mode
  conversion seule) ;
- `l3-coverage-knob-probe-v1.sh` — sonde de couverture, aucune partie de porte ;
- `l3_bucket_visits.py --fold exact` — la couverture comptée dans l'espace que
  le fit optimise réellement ;
- `install-egdb-wld-v1.sh` — base WLD 2-7 posée sur cpx62 (`/root/egdb_extracted/app`).

## 1. Architecture du programme

### 1.1 `L3-PURE` — voie généraliste

`L3-PURE` est la seule lignée destinée à produire une évaluation généraliste
entièrement autonome et, si les gates de force sont franchis, un successeur à
`gen2-mmto`.

Le bras pur C0 A-G3 a été entraîné uniquement par autojeu, pendant trois
générations de 500 000 records. Il a obtenu un score de **0,497 contre
`gen2-mmto`**, soit une parité pratique dans le protocole `0795`. C’est un
résultat majeur : il démontre qu’une lignée linéaire sans teacher peut rejoindre
le champion historique avec un volume encore faible au regard de la géométrie
8cf. Il ne prouve ni une supériorité, ni un plafond.

Une extension de maturité contrôlée est donc scientifiquement ouverte. Elle doit
séparer trois effets : générations supplémentaires, volume par fit et mémoire
explicite par replay/cumul. Répéter seulement des générations de 500 000 records
frais ne constitue pas automatiquement un entraînement cumulatif.

### 1.2 `L3-IMBALANCE2` — laboratoire spécialiste

`L3-IMBALANCE2` et `L3-IMBALANCE2-ROLE-V2` sont des expériences spécialisées sur
les positions à exactement deux hommes d’écart. Elles ne sont pas candidates au
remplacement généraliste de `L3-PURE` ou de `gen2-mmto`.

La mention « référence V2 » signifie uniquement **référence interne du track
spécialiste**. Ses pools, pondérations et gates mesurent conversion et résilience
dans ce domaine borné ; ils ne fournissent pas un Elo généraliste.

Au mieux, un spécialiste confirmé pourrait devenir plus tard un sidecar, un
expert appelé par un routeur ou une composante de méta-évaluation combinée avec
`L3-PURE`. Une telle combinaison exigerait une expérience séparée, une activation
bornée, une garde de débit et une non-régression généraliste.

## 2. Recette générale propre

La recette générale Q00 reste figée pour les comparaisons propres :

- géométrie `8cf` ;
- 63 paramètres de recherche explicitement épinglés ;
- exploration `8 / 8 % / 60` ;
- labels WDL terminaux, ply-caps exclus ;
- fit logistic, `L2=3e-5` ;
- aucun teacher, aucune frontière mobile, aucun MMTO dans le train ;
- classe d’évaluation linéaire et interprétable.

Le benchmark M0 HOME est terminé. Sa revue humaine retient **C0 A-G3** comme
parent immuable de M1. La génération M1 utilise néanmoins le fingerprint Q00
complet : l’ancien fingerprint C0 reste une propriété historique du parent, pas
une configuration héritée par les nouveaux bras.

## 3. Campagnes et diagnostics publiés

| Track | Campagne | Job | Résultat durable |
|---|---|---|---|
| généraliste | C0 pur A-G3 | `ccx33-0790` + gate `0795` | **0,497 vs Gen2, parité pratique** |
| généraliste | frontière mobile C0 | `cpx62-0791` + gate `0795` | retirée, conversion −0,023 |
| généraliste propre | baseline Q00 | `cpx62-0842` | G1–G4 saine, `+7 Elo` natif vs Gen2 |
| maturité M0 | triangle C0/P1/Gen2 + couverture | `home-0934` / `home-0935` | **parent C0 retenu pour M1** |
| maturité M1 | F500/F2M/R2M + confirmation | `home-0963` / `home-0964` | **F2M champion L3-PURE** |
| champion général | F2M vs Gen2, moteur réparé symétrique | `home-0965` | **F2M nouveau champion général** |
| maturité M2 | 2M frais depuis F2M | `home-0966bis` | relance après séparation des builds test/EGDB, sans promotion automatique |
| maturité M2 | readout d8 frais | `home-0970bis` | **plateau : 50,60/49,05 % vs F2M Q00/native** |
| causal profondeur | d10 frais, volume constant | `home-0971` / `home-0972` | **plateau : 48,80/51,00 % vs F2M** |
| causal profondeur | d12 frais, volume constant | `home-0973` / `home-0974bis` | **régression Q00 établie : 45,85 %, −28,9 Elo vs F2M** |
| causal temporel | turnover 1M F2M + 1M M2 frais | `home-0977` / `home-0978` | **signal positif dans 4/4 vues ; confirmation indépendante requise** |
| confirmation temporelle | même modèle TURNOVER, nouveau pool haut-N | `home-0979` / relance `home-0980` | **effet confirmé contre M2 ; pas de supériorité établie sur F2M** |
| dose mémoire | 500k époque F2M + 1,5M époque M2 | `home-0981→0983` | **dose 25/75 close : mieux que M2, moins bien que TURNOVER 50/50** |
| régularisation | écran L2 `{1e-5, 3e-5, 1e-4}` à corpus fixe | `home-0984bis`/`0985` / relance `0987` | **`1e-4` rejeté (régression native établie) ; `1e-5` directionnel** |
| régularisation | confirmation indépendante de `L2_1E5` | `home-0988` / `home-0989` | **non répliquée, vues inversées : facteur L2 clos sur `3e-5`** |
| méthodologie | accord des vues + puissance, 65 cellules déjà publiées | analyse locale, aucune partie neuve | **vues équivalentes (`p≈0,88`) ; écrans `n=1000` aveugles sous ~17 Elo** |
| dose mémoire | dose 75 % + readout à vues additionnées, `n=5000` | `home-0991→0993` | **axe clos, optimum intérieur à 50 % ; `TURNOVER` bat F2M, `+13,8 Elo` établi** |
| champion général | porte de succession, garde Gen2, conversion P3/P4 | `home-0995` / `home-0996` | **TURNOVER promu champion général** : `+13,73 Elo` sur `n=6000`, 5/5 gardes vertes |
| champion général | succession fold exact, avec EGDB | `cpx62-1129` | **EXACT promu champion général** : `+15,12 Elo` sur `n=6000`, deux vues positives ; gardes Gen2/conversion NON jouées |
| autojeu on-policy | un seul facteur, ratio 1:1 tenu, avec EGDB | `cpx62-1127` / `cpx62-1130` | **PLAT** : `−4,05 Elo`, IC95 `[−12,6 ; +4,5]` — pas de régression, pas de gain ; couverture `−3,9 %` à volume égal |
| couverture | sondes de boutons + dose-réponse, aucune partie de porte | `cpx62-1131` / `cpx62-1132` | **`--random-open-plies` est le bouton** : `+7,11 %` de buckets à `rop=24`, plateau au-delà ; top-k **négatif** (`−2,14 %`) ; aucun Elo établi |
| couverture → force | corpus complet à `rop=24`, un seul facteur, porte avec EGDB | `cpx62-1133` / `cpx62-1134` | ⛔ **RÉFUTÉ** : `+2,83 %` de buckets et **`−9,27 Elo`** IC95 `[−17,9 ; −0,7]` — régression établie. **La couverture n'est pas un proxy de qualité** |
| spécialiste | imbalance2 V1 | `ccx33-0847` | P1 near-flat |
| spécialiste | role-aware V2 | `ccx33-0852` | crédit plus propre, pas de lead établi |
| spécialiste | comparaison V1/V2 | `0853→0857` | `V2_NO_CLEAR_LEAD_AT_P1` |
| spécialiste | role-aware V2 P2 | `ccx33-0859` | G5–G8 complets, aucune promotion |
| spécialiste | consolidation P2 | `ccx33-0870` | arrêt avant P3 |
| spécialiste | diagnostic causal | `cpx62-0871` | `D0_CAUSAL_PROFILE_READY` |
| spécialiste | représentation RC4 | `cpx62-0872` | **`D1_RC4_NO_GO`** |
| spécialiste | autopsie RC4 | `cpx62-0874` | **`D1X_RC4_AUTOPSY_READY`** |
| causal conversion | matrice TOP3 stable | `cpx62-0908` + salvage `0920` | **`SALVAGE_CAUSAL_CONVERSION_MATRIX_READY`** |
| causal conversion | miroir L3-PURE | `cpx62-0921` | **`L3_PURE_CAUSAL_CONVERSION_MATRIX_READY`** |
| autopsie recette | 0842 vs 0890bis, matrices 0908/0921 | analyse locale reproductible | **`TOP3_SPECIALIST_RECIPE_FAILURE_LOCALIZED_FACTORS_CONFOUNDED`** |
| ablation recette | `0922bis` G1, départ standard/TOP3 × reweight off/on | 4 modèles entraînés; matrice interrompue par 1 ply-cap | **reprise eval-only `0922quater` préparée** |

## 4. Couverture et maturité de `L3-PURE`

Les audits publiés montrent que 8cf reste sous-alimentée :

- 300 000 records : environ **5,9 %** de buckets visités ;
- 1,5 million de records agrégés dans X1 : environ **9,0 %** ;
- buckets avec au moins 100 visites : **1,0 %** ;
- Gini des visites : environ **0,85**.

Le passage de 300 k à 1,5 M a accru la couverture de manière sous-linéaire. Cela
ferme 32cf à court terme, mais ne ferme pas une expérience de maturité sur 8cf.
Il faut néanmoins distinguer volume total généré et volume réellement présent
dans un même fit.

Le plan actif est décrit dans
[`L3_LINEAGE_ROLES_AND_MATURITY.md`](L3_LINEAGE_ROLES_AND_MATURITY.md) :

1. M0 : terminé ; C0 A-G3 est le parent immuable retenu ;
2. M1 : comparer 500 k frais, 2 M frais et 2 M avec
   mémoire historique explicite ;
3. mesurer Elo, conversion, couverture, holdout et coût ;
4. arrêter après deux étapes sans pente de force positive.

Aucune campagne longue ou promotion n’est autorisée automatiquement.

## 5. Track spécialiste — verdicts actuels

### 5.1 P2 G4→G8

`ccx33-0870` a produit `P2_NO_CLEAR_IMPROVEMENT_OR_UNSTABLE` : delta macro
`+0,0053`, IC95 `[−0,0426 ; +0,0526]`, 9/18 strates non dégradées. P3 à recette
identique reste interdit.

### 5.2 D0 causal

`cpx62-0871` a analysé 30 sentinelles et 360 recherches :

- `REPRESENTATION_OR_OBJECTIVE_CANDIDATE` : 7/30 ;
- `SEARCH_AND_EVAL_MIXED` : 23/30 ;
- cas purement search-horizon : 0/30 ;
- cas training-credit/distribution : 0/30.

### 5.3 D1-A RC4 — verdict final `D1_RC4_NO_GO`

RC4 a ajouté quatre extras spécialisés, sans gain : delta macro `+0,003038`,
IC95 `[−0,043403 ; +0,049913]`, 9/18 strates non dégradées, 0/7 sentinelles
corrigées, débit `0,935302` et garde généraliste `0,4140625`.

```text
D1_RC4_NO_GO
RC4_CLOSED_DO_NOT_REPEAT_IDENTICALLY
d1b_authorized=false
training_continuation_authorized=false
promotion_authorized=false
automatic_next_job=null
```

Mémo immuable :
[`archives/l3/D1_RC4_NO_GO_20260720.md`](archives/l3/D1_RC4_NO_GO_20260720.md).

### 5.4 D1-X — autopsie RC4 terminée

`cpx62-0874` est terminé avec exit code 0. Le verdict est
`D1X_RC4_AUTOPSY_READY` et la classification est :

```text
RC4_ACTIVE_BUT_NONCAUSAL_FOR_CONVERSION
```

Le rapport complet est publié dans R2 :

```text
r2:jass-data/runs/cpx62-0874-l3-imbalance2-d1x-autopsy/20260720T220921Z-a7301ac6
```

D1-X recommande seulement la conception humaine d’un pilote search-only séparé
`S1_ROLE_STABILITY_EXTENSION`. Il n’autorise ni implémentation automatique, ni
entraînement, ni promotion.

### 5.5 Matrice causale de conversion TOP3 stable

`cpx62-0908` a joué les 2 688 parties prévues sur les 384 mêmes positions +2
stables. Son gate technique strict a échoué sur un unique cap à 400 plies.
`cpx62-0920` n’a rejoué aucune partie : il a authentifié le tar brut, adjugé
uniquement cette partie nulle, puis calculé la matrice et 10 000 bootstraps.
Le gate zéro-cap original reste explicitement `FAILED`.

W/D/L du point de vue du camp +2 :

```text
Scan/Scan 382/0/2    Scan/G4 384/0/0    G4/Scan 7/0/377
G0/G0     342/0/42   G4/G0   210/0/174  G0/G4   356/0/28
G4/G4     270/1/113
```

Le résultat causal principal est négatif pour l’apprentissage de conversion de
G4 : effet d’attaque `G4/G0 − G0/G0 = −0,6875`, IC95
`[−0,8021 ; −0,5677]`. L’effet joint G4 est aussi négatif
(`−0,3724`, IC95 `[−0,4818 ; −0,2656]`). Scan domine G4 dans les deux rôles :
attaque `+0,5911` et défense `+1,3724`, avec IC95 entièrement positifs.

Cela ferme l’interprétation « G4 a appris une conversion seulement masquée par
le harnais ». Sur ce domaine borné, la politique issue de l’autojeu G4 a
dégradé le rôle attaquant par rapport à G0. Le fait que Scan partage une classe
d’évaluation linéaire ne suffit donc pas : sa fonction apprise et sa
co-adaptation recherche/évaluation restent causalement différentes.

Le miroir `cpx62-0921` remplace uniquement le G4 spécialiste 0890bis par le G4
généraliste pur de `0842`. Il a terminé strictement les 2 688 parties, sans
erreur ni cap :

```text
Scan/Scan 382/0/2    Scan/G4 384/0/0    G4/Scan 78/0/306
G0/G0     342/0/42   G4/G0   374/0/10   G0/G4   202/0/182
G4/G4     345/0/39
```

Contrairement au spécialiste, G4 pur améliore causalement les deux rôles :
attaque `+0,1667`, IC95 `[+0,0990 ; +0,2344]`, et défense `+0,7292`, IC95
`[+0,6146 ; +0,8438]`. Leur combinaison G4/G4 est proche de G0/G0
(`+0,0156`, IC95 `[−0,0625 ; +0,0990]`) parce que l’attaquant et le défenseur
sont renforcés simultanément. Scan reste supérieur, surtout en défense.

La conclusion est donc localisée : l’architecture linéaire et le self-play WDL
sans oracle peuvent apprendre la conversion. C’est la recette spécialiste
0890bis qui a détruit le rôle attaquant ; elle ne doit pas être prolongée ni
servir de preuve d’un échec général de L3-PURE.

### 5.6 Autopsie de la recette 0890bis

L’autopsie des manifests, profils, poids G4 et résultats bruts appariés localise
le problème dans le bundle de recette 0890bis, sans pouvoir encore séparer ses
trois facteurs : départ exclusivement TOP3, volume `2 M/gen` et pondération
role-aware `1/2/4`.

Le corpus réel n’est pas majoritairement TOP3 : en G4, **72,59 %** des records
ont au plus 14 pièces et seulement **0,081 %** en ont au moins 30. Avant
resampling, seulement **5,765 %** du fit reste dans le domaine exact
`±2 hommes, dames égales` ; après resampling, cette part atteint **8,038 %**.
Les 94,235 % hors domaine sont conservés comme anchors.

Les matrices 0908/0921 sont exactement appariées sur les 2 688 lignes et les
contrôles G0/G0 et Scan/Scan sont identiques à 384/384. Remplacer seulement le
G4 spécialiste par le G4 pur améliore 171 positions et en dégrade 7 en attaque
contre G0 ; en défense contre G0, 171 s’améliorent et 17 se dégradent.

Verdict :

```text
TOP3_SPECIALIST_RECIPE_FAILURE_LOCALIZED_FACTORS_CONFOUNDED
0890bis_continuation_authorized=false
automatic_next_job=null
```

La seule ablation propre restante est un `2 × 2` départ standard/TOP3 ×
reweighting off/on, à volume identique. Ses quatre modèles G1 sont acquis ;
le verdict causal complet reste ouvert. Mémo immuable :
[`archives/l3/TOP3_SPECIALIST_RECIPE_AUTOPSY_20260723.md`](archives/l3/TOP3_SPECIALIST_RECIPE_AUTOPSY_20260723.md).

### 5.7 Écran G1 `2 × 2` — modèles acquis, reprise d’évaluation

`cpx62-0922bis-l3-conversion-2x2-g1-screen-v1` a entraîné les quatre modèles. Les
cellules off/on partagent exactement le même self-play et le même split :
500 000 records standard alimentent `standard_off/standard_on`, et 500 000
records TOP3 alimentent `top3_off/top3_on`.

Le gate devait jouer un contrôle G0/G0 commun et trois bras par candidat sur les 384
positions stables de 0921, soit 4 992 parties, puis 128 parties équilibrées par
candidat. `0922bis` s’est arrêté après un unique cap déterministe à 400 plis
dans `standard_off/g0_g4` ; ce résultat technique ne constitue pas un verdict
sur les modèles.

La première reprise `0922ter` a vérifié les modèles mais a échoué avant toute
partie : le build d’évaluation n’avait pas réémis la géométrie `8cf`.
`0922quater` a rétabli cette étape, puis a authentifié un second cap
déterministe à 400 plis dans `top3_off/g4_g0`, shard 12, position `62faf1...`.
Le premier reste `standard_off/g0_g4`, shard 10, position `9bc75f...`.

`home-0928` a réutilisé les quatre modèles vérifiés de `0922bis`, sans
réentraînement. Il a validé les deux caps connus puis a échoué fermé sur un
troisième shard technique dans `top3_off/g4_g4`, après 3 733/4 992 lignes.

`home-0928quater` a importé le tar brut vérifié de `home-0928`, réutilisé chaque
bras complet et joué uniquement les bras manquants. La matrice est complète :
4 992 lignes et exactement trois ply-caps propres à 400 plis, dans
`standard_off/g0_g4`, `top3_off/g4_g0` et `top3_off/g4_g4`. Aucun bras
`top3_on` ne contient d’anomalie et aucune erreur moteur n’a été observée.

`home-0928quinquies` a réutilisé cette matrice sans rejouer une ligne, exigé
les trois identités authentifiées, puis joué la garde équilibrée de 512
parties. Les quatre gardes passent. Le résultat final est :

```text
CONVERSION_2X2_G1_SCREEN_READY
technical_status=derived_complete_3_ply_caps
promotion_authorized=false
continuation_authorized=false
automatic_next_job=null
```

Les effets causaux sont nets. Par rapport au départ standard, le départ TOP3
exclusif dégrade l’attaque de `−0,5352` (IC95
`[−0,6055 ; −0,4674]`), la défense de `−0,6367`
(`[−0,7201 ; −0,5534]`) et l’effet joint de `−0,2383`
(`[−0,3125 ; −0,1654]`). Le reweight role-aware V2 dégrade aussi l’attaque
de `−0,2513`, la défense de `−0,1003` et l’effet joint de `−0,1315`,
avec des IC95 entièrement négatifs. Son interaction avec TOP3 est elle-même
négative.

La cellule propre `standard_off` conserve les gains causaux de L3-PURE :
attaque `+0,1719`, défense `+0,6536`, effet joint `+0,0104`. La recette à
retenir pour la maturité généraliste est donc **départ standard, sans reweight
V2**. TOP3 exclusif et le reweight V2 sont fermés pour cette continuation.
Cela attribue causalement l’échec 0890bis à la recette spécialiste et non à
l’architecture linéaire ni au principe d’autojeu WDL.

## 6. Prochaines actions séparées

### Généraliste `L3-PURE`

1. champion général courant : **L2LOW**, promu le 4 août 2026 sur go explicite
   de JFC — même recette que PRIORTIGHT, `--l2` porté de `3e-5` à **`1e-5`**.
   Consolidé **`+11,31 Elo`** IC95 `[+6,4 ; +16,3]` sur `n = 18 000` et deux
   pools disjoints (`cpx62-1165` + `cpx62-1170`), trois gardes vertes
   (`cpx62-1171` : Gen2 `+84,31`, conversion `0,7500` / `0,7667`).
   ⛔ **`l2` n'est plus un rétrécissement vers zéro depuis qu'il y a un prior :
   c'est la force du rappel VERS LE PARENT.** `3e-5` n'était pas un mauvais
   réglage, c'était un **bon réglage transporté hors de son domaine** — clos en
   juillet sur un ridge centré sur zéro, réutilisé tel quel une fois le ridge
   recentré sur le parent, où il sur-pondère le parent que la moitié mémoire du
   mélange 1:1 réinjecte déjà comme donnée. ✅ **Axe clos par PLATEAU** :
   `1e-5` et `3e-6` sont indiscernables (`z = 0,39`), bornes de la dose
   `1e-4 : −15,65` et `3e-6 : +14,25`. ⚠️ Chiffre **biaisé vers le haut**, la
   réplication tombant de `+12,54` à `+8,86` — troisième fois d'affilée. Bornes :
   [`experiments/L3_L2LOW_PROMOTION_20260804.md`](experiments/L3_L2LOW_PROMOTION_20260804.md).
   **Tout nouveau fit L3 utilise donc `--exact-fold` ET `--prior-mean … --prior-decay 0`
   ET `--lbfgs-gtol 1e-4` ET `--l2 1e-5`** ;
1ter. champion précédent : **PRIORTIGHT**, promu le 3 août 2026 sur go
   explicite de JFC — même recette que PRIOR, tolérance du solveur portée de
   `1e-3` à `1e-4`. Porte de succession contre le champion assis, **un seul
   facteur**, pool `big3000` disjoint, `n=12 000` : **`+18,05 Elo`** IC95
   `[+12,0 ; +24,1]` (`cpx62-1163`). Trois gardes vertes et **au-dessus des trois
   champions précédents** : Gen2 `+86,09`, conversion `0,8067` / `0,7800`
   (`cpx62-1162`). ⛔ **EXACT et PRIOR étaient SOUS-CONVERGÉS** : `141` et `169`
   itérations sous `gtol=1e-3` là où les mêmes recettes en prennent `653` et
   `904` sous `1e-4`, avec `success=True` rendu dans les deux cas. Bornes :
   [`experiments/L3_PRIORTIGHT_PROMOTION_20260803.md`](experiments/L3_PRIORTIGHT_PROMOTION_20260803.md).
   **Tout nouveau fit L3 utilise donc `--exact-fold` ET `--prior-mean … --prior-decay 0`
   ET `--lbfgs-gtol 1e-4`** ;
1bis. champion précédent : **PRIOR**, promu le 2 août 2026 et resté champion
   moins de vingt-quatre heures — `--prior-mean <parent> --prior-decay 0`,
   consolidé `+6,66 Elo` IC95 `[+0,44 ; +12,88]` sur `n=12 000` et deux pools
   disjoints, trois gardes vertes (`+70,01` contre Gen2). ⚠️ Chiffre **biaisé
   vers le haut** (découverte + réplication) ; borne basse `+0,44`. ⚠️ **Et
   mesuré sur un fit sous-convergé** : le prior re-mesuré à `1e-4` vaut `+8,48`
   IC95 `[+3,5 ; +13,4]` sur `n = 18 000` — c'est ce chiffre-là qu'il faut citer.
   Bornes :
   [`experiments/L3_PRIOR_PROMOTION_20260802.md`](experiments/L3_PRIOR_PROMOTION_20260802.md) ;
1bis. champion précédent : **EXACT**, promu le 1er août 2026 après la porte
   `cpx62-1129` (`+15,12 Elo` sur `n=6000`, **avec EGDB**) ; TURNOVER — champion
   du 27 juillet au 1er août après `home-0996` — devient le champion précédent,
   archivé dans l'object store et restaurable ; F2M reste le champion d'avant ;
   Gen2-mmto reste la référence historique figée. ⚠️ Cette succession est **moins
   garnie** que celle de TURNOVER : garde Gen2, conversion P3/P4 et second pool
   indépendant n'ont **pas** été jouées. Bornes explicites :
   [`experiments/L3_EXACT_PROMOTION_20260801.md`](experiments/L3_EXACT_PROMOTION_20260801.md) ;
1bis. **tout nouveau fit L3 utilise `--exact-fold`** : `--color-fold` impose une
   contrainte fausse (`cs` seule) et perd le gain ;
2. facteur L2 **clos** : `1e-4` rejeté, `1e-5` non répliqué, `L2=3e-5` retenu ;
3. croisement replay `0/25 %` au L2 retenu : c'est le prochain bras à
   préenregistrer ;
4. traiter les losses holdout, normes de gradient et amplitudes de poids comme
   des diagnostics, jamais comme des critères de sélection ;
5. mesurer séparément force, conversion, couverture et convergence ;
6. ne pas rouvrir la profondeur seule : d8, d10 et d12 sont clos, et le mix
   d10/d12 reste interdit faute de garde-fous tous verts ;
7. ne pas passer à 32cf tant que la couverture 8cf reste insuffisante ;
8. **calibration contre Scan débloquée** : `home-1001` a rendu
   `SCAN_HARNESS_SOUND_ANCHOR_AT_OR_ABOVE_FLOOR`. Le `0,050` de
   `home-0997/0998` était un artefact moteur — `search()` rendait un coup nul
   sur toute racine nulle par répétition ou horloge, et le client HUB lisait
   ça comme un abandon. Corrigé (`9c1d1e8e`), TURNOVER passe à `0,200`
   (`−241 Elo`) à `mt0.3` et gen2-mmto à `0,188` (`−255`), les deux planchers
   historiques tenus. Les deux modèles sont indiscernables contre Scan à
   `n=40`, ce qui n'établit rien : `home-0996` les sépare de ~`62 Elo` en
   tête-à-tête, invisible à cette taille. Protocole et suites :
   [`L3_SCAN_ANCHOR_REPRODUCTION_20260727.md`](experiments/L3_SCAN_ANCHOR_REPRODUCTION_20260727.md).
9. **position réelle contre Scan mesurée** (`home-1002`, `n=1000` par cellule
   de profondeur, `n=200` par cellule de cadence) : notre `d9` vaut le **`d3`
   de Scan** (`0,490`, IC95 `[0,459 ; 0,521]`), soit **six plies de
   handicap** ; à armes égales `d9/d9` = `−242 Elo`, `d11/d11` = `−218`,
   `mt0.2/mt0.2` = `−170`. Nos plies valent autant que les siens
   (`+2,2 à 3,7 pp/ply` contre `−2,6`), donc l'écart est un **décalage fixe**
   et non un écart qui se creuse. Donner dix fois moins de temps à Scan ne
   rapporte rien (`+2,2 pp`, `z=+0,5`) : **le résidu est de la marge
   d'évaluation, pas de la vitesse** — on fait mieux à temps égal qu'à
   profondeur égale.
   [`L3_SCAN_CALIBRATION_MATRIX_20260727.md`](experiments/L3_SCAN_CALIBRATION_MATRIX_20260727.md).
10. **`−128 à −155 Elo` contre Scan = plancher contaminé**, pas une valeur :
    mesuré à travers le coup nul. À ne plus citer comme référence.
11. **G2** reste ouvert et prêt (`home-0999`→`1001` de la chaîne G2 sont à
    renuméroter, les numéros ayant servi ici).
12. **Axe volume — VOL8M rendu, et il PERD** (`home-1008`, 09h44→10h19 FR le
    28 juillet 2026). 12 M records (8 M frais `d9` + 4 M mémoire), fit convergé
    (`home-1006`), couverture `13,5 %` contre `9,8 %`, densité **41,7 contre
    4,3 observations par paramètre libre**, holdout `0,440449` contre
    `0,444060` — et contre TURNOVER sur un pool neuf de 1500 ouvertures :
    **`0,4785`, `−14,95 Elo`, IC95 `[−23,5 ; −6,4]`, `n = 6000`**, vues
    additionnées (`q00` `1360-142-1498` = `−16,0` ; `native` `1352-176-1472` =
    `−13,9`). L'intervalle **exclut zéro** : ce n'est pas un plat, c'est une
    perte établie. **Quatrième confirmation que la loss holdout ne prédit pas
    la force** — et la première où elle pointe franchement à l'envers.
13. ⚠️ **Le verdict préenregistré `VOLUME8M_BELOW_TURNOVER_VOLUME_AXIS_CLOSED`
    dit plus que ce que le run mesure.** VOL8M s'écarte de la recette TURNOVER
    sur **quatre** facteurs déclarés, pas un : volume `12 M` vs `2 M`, ratio
    frais/mémoire `67/33` vs `50/50`, profondeur de jeu `9` vs `8`, et
    l'étiquetage de la moitié mémoire (point 15). **Ce run ne sépare pas
    « le volume n'aide pas » du reste.** L'axe est clos *au sens du contrat
    préenregistré* ; scientifiquement il reste à trancher par un 12 M dont tout
    le corpus vient du moteur réparé.
15. 🔬 **Défaut d'étiquetage pré-`9c1d1e8e` — mécanisme mesuré, et RECTIFICATION
    de ce que j'en avais écrit le 28 juillet.**
    *Mécanisme exact.* Avant `9c1d1e8e`, `search()` renvoyait un coup **nul** dès
    que la racine répétait une position déjà vue. En self-play `--gen-data-wdl`,
    `Engine::apply_move` rejette ce coup (il n'est pas dans la liste légale), la
    boucle de jeu **casse**, `hit_ply_cap` reste vrai, et `--drop-plycap` — actif
    dans toute la chaîne L3-PURE — **jette la partie entière**. Les répétitions
    arrivent dans les positions de manœuvre : ce sont donc **les nulles qui
    disparaissaient du corpus**.
    *Mesure directe* (binaire pré-fix contre post-fix, mêmes graine, parent,
    profondeur `d8` et options, 3000 records, `--drop-plycap`) :

    | | défaites | **nulles** | victoires |
    |---|---:|---:|---:|
    | moteur cassé | 47,8 % | **4,8 %** | 47,4 % |
    | moteur réparé | 39,5 % | **20,3 %** | 40,2 % |

    Facteur **4,2** sur les nulles. Le corpus cassé est décisif à 97,6 %.
    *Ce que j'avais écrit et qui est FAUX, dans les deux sens.* (a) Le défaut
    ne « compte pas les nulles en défaites » — il **supprime les parties**, et
    l'étiquette des parties gardées reste correcte. (b) Surtout, il **n'est pas
    propre à VOL8M** : `M1` (`home-0944`, 24 juillet), `M2` (`home-0966bis`,
    25 juillet) et **TURNOVER lui-même** (`home-0977`, 26 juillet,
    `new_generation_performed=false`, corpus = 1 M `fresh_m2` + 1 M
    `parent_f2m`) précèdent tous le correctif du 27 juillet 16h10 FR. **VOL8M
    est à 67 % post-correctif ; TURNOVER est à 100 % pré-correctif.** VOL8M a
    donc *moins* du défaut, pas plus — mon « un tiers du corpus mal étiqueté
    explique les −15 Elo » ne tient pas.
    *Le confond qui reste, formulé correctement.* VOL8M mélange **deux
    calibrations de nulles incompatibles** (8 M à ~20 %, 4 M à ~5 %) là où
    TURNOVER en a une seule, homogène quoique fausse ; et la porte est jouée par
    le moteur réparé. C'est testable, et ce n'est pas ce qui a été testé.
16. 🛡️ **Garde anti-récidive : `jobs/tools/assert_corpus_wdl.py`.** Les gardes
    de l'époque portaient toutes sur le **code** (`grep root_is_drawn`) : elles
    vérifient une cause connue et n'auraient rien vu si la cause avait été
    autre. Le nouveau canari porte sur les **données** — il refuse tout corpus
    dont la part de nulles sort de `[0,10 ; 0,60]` ou dont les victoires et
    défaites s'écartent de plus de 10 points. Validé sur les deux corpus réels :
    rejette le cassé (`rc=6`, 4,8 %), accepte le réparé (20,3 %). Câblé dans
    `l3-pure-explore-topk-v1.sh` ; **à propager** — sur 23 templates qui
    appellent `--gen-data-wdl`, 2 seulement avaient la garde de code.
14. **Conséquence immédiate pour le run top-k** : le volume n'ayant pas payé,
    aucun champion n'est baké, et le parent du self-play top-k reste
    **TURNOVER**.

### Porte de promotion TOPK3 close — TURNOVER conservé

`home-1040-l3-pure-topk3-promotion-gate-v5` est le replay autoritatif complet
du gate TOPK3. Sur 10 000 parties primaires fraîches et appariées, TOPK3 fait
`4496-449-5055`, soit `0,47205` et `-19,44 Elo` contre TURNOVER. Les deux vues
régressent séparément : Q00 `0,4716` (`-19,76 Elo`, IC90
`[0,460240 ; 0,482960]`) et natif `0,4725` (`-19,13 Elo`, IC90
`[0,461164 ; 0,483836]`).

TOPK3 conserve la parité externe contre Gen2 (`0,578667`, `+55,12 Elo`),
mais reste en dessous de TURNOVER sur la même garde (`0,597667`,
`+68,75 Elo`). La conversion corrigée vaut `0,763333` sur P3 pour les deux
bras et `0,743333` contre `0,760000` sur P4. Le verdict scellé est
`TOPK3_PROMOTION_NOT_RECOMMENDED_POINT_ESTIMATE` : **TOPK3 n'est pas baké,
TURNOVER reste champion**.

Les runs `1028`, `1033`, `1036` et `1037` n'ont aucune valeur de verdict :
le premier a échoué sur le défenseur de conversion pré-correctif, les trois
autres avant science. Détails et artefact autoritatif :
[`experiments/L3_TOPK3_PROMOTION_GATE_20260729.md`](experiments/L3_TOPK3_PROMOTION_GATE_20260729.md).

La suite « qualité du signal » utilise donc le protocole TURNOVER/UNIFORM
distinct : `home-1042` est uniquement le préflight du catalogue hard-replay.
Il doit publier exactement 1 M de records déterministes avant d'autoriser un
fit ; aucune réduction post-hoc de dose ni continuation automatique.

`home-1042` termine avec
**`L3_PURE_HARD_REPLAY_CATALOGUE_INSUFFICIENT`**. Le corpus UNIFORM de 2 M
contient 325 233 records signal, mais `one-per-game` ramène la capacité à
30 205 parties, la déduplication à 29 454 positions et le miroir couleur à
**58 908 records**. Le mining répété est bit-identique ; ce n'est pas une
panne. `training_authorized=false` et aucun fit n'est lancé. À rendement
constant, la dose de 1 M demanderait environ 34 M records historiques
comparables. Une réouverture doit donc préenregistrer une source post-correctif
plus large ou un DOE de dose distinct, sans mélange pré-correctif ni réduction
post-hoc. Détails :
[`experiments/L3_HARD_REPLAY_PREFLIGHT_20260729.md`](experiments/L3_HARD_REPLAY_PREFLIGHT_20260729.md).

La source UNIFORM 40 M a ensuite permis d'exécuter le DOE causal complet.
`home-1076` établit une régression massive de `HARD_REPLAY` contre
`UNIFORM_REPLAY` : Q00 `96-12-4892` (0,0204, -672,57 Elo), native
`126-12-4862` (0,0264, -626,71 Elo), soit `222-24-9754` sur 10 000 parties,
0,0234 et **-648,20 Elo** additionnés. Le verdict est
`L3_PURE_HARD_REPLAY_BELOW_UNIFORM_REPLAY`.

Les modèles et entrées sont authentifiés et les deux optimiseurs convergent.
Le bras outcome-conditioned déplace toutefois le prior WDL assemblé à
51,29 % wins contre 31,52 % losses STM (asymétrie 19,77 points), contre
42,55 % / 42,19 % pour le contrôle. La couverture progresse de 194 334 à
210 436 buckets, mais le signal de valeur s'effondre. La recette v1
`50 % fresh + 50 % failed_conversion` avec cibles historiques conservées est
donc close. La suite utilise les positions hard comme **reverse seeds
zero-target appariés**, puis régénère les WDL par self-play. Détails :
[`experiments/L3_HARD_REPLAY_READOUT_20260730.md`](experiments/L3_HARD_REPLAY_READOUT_20260730.md).

### Bake search du 31 juillet — overshoot `go movetime` corrigé

Le défaut ouvert depuis le 7 juillet est résolu et **baké** (`16f8c151`). La
bitbase 3-dames-contre-1 était construite par rétro-analyse **dans `negamax`**,
sous un `call_once` que la sonde de deadline ne peut pas interrompre : 5,15 s
volées à l'horloge, `go movetime 100` rendu après **5558 ms (55×)**.

Ce n'était pas qu'un bug de temps. Le moteur rendait `depth=3 score=164` — il se
croyait gagnant — là où la version corrigée atteint `depth=20 score=0`. Mais
`call_once` ne se déclenche qu'**une fois par processus** : seul le premier coup
qui descend dans une telle finale est touché, tout le reste du processus est
chaud (`go` #1 = 3861 ms depth 3, #2 = 85 ms depth 17, #3 = 40 ms depth 18).

Après correctif : `55,58× → 1,01×`. Déterminisme intact (`go depth 4` rend les
mêmes `nodes=4314` et `bestmove 46-41`). Coût déplacé au handshake HUB, amorti à
~43 ms par partie sur un shard de porte.

✅ **Contamination historique mesurée, et faible.** Exposition maximale : 2 moteurs
par shard × 12-16 shards = **≤ ~32 coups par cellule** sur 3000-5000 parties. Et
le canal « nulles fabriquées » n'a jamais tiré : `game skipped` compté à **0** sur
`home-1040`, `1008`, `1091`, `1108` et `1102`. **Aucun verdict n'est remis en
cause et aucun ne demande d'être rejoué.** Procédure, mesures et
rollback :
[`experiments/L3_MOVETIME_ENDGAME_BAKE_20260731.md`](experiments/L3_MOVETIME_ENDGAME_BAKE_20260731.md).

### 🟢 Fold exact — +17,1 Elo, premier gain établi de la campagne (`cpx62-1117/1118`, 1er août)

**À corpus, parent, hyperparamètres, pile numérique et machine identiques**,
plier le fit sur la symétrie **exacte** du damier au lieu d'une symétrie
**approximative** vaut **+17,10 Elo**, IC95 `[+9,2 ; +25,0]` sur **6000 parties**
(2546 W / 1203 D / 2251 L, taux 0,5246, IC95 `[0,5133 ; 0,5359]`).
Aucun changement de moteur, aucune feature, aucun volume : la sortie reste un
`.pjtw` 8cf standard.

**Le défaut était à l'envers.** `symmetry.py` dit lui-même que la symétrie exacte
est `rot180∘cs` et que `cs` seule est *approximative*. Mesuré sur TURNOVER,
entraîné en `--color-fold` : `cs` seule satisfaite à **0,0000 %** près, `rot180∘cs`
violée à **25,8 %**. On imposait structurellement la contrainte fausse et on
laissait la vraie s'apprendre — un quart de l'énergie des poids affirmait qu'une
configuration vaut différemment selon le bout du plateau d'où on la regarde.
C'est exactement la signature diffuse que l'atlas `cpx62-1114` avait relevée.

⚠️ **Ce n'est pas un gain de capacité** : `--color-fold` atteignait déjà
`TB = 2 125 768`. Les deux folds mutualisent le même NOMBRE de configurations ;
ce qui change est **ce qu'ils mutualisent**. `--exact-fold` plie sur
`{id, rot180∘cs}` → 2 125 764 poids, exactement le compte de Scan (qui est
**4 patterns**, vérifié dans son source, contre nos 8 — donc 2× sa capacité).

⚠️ **Deux réserves sur le chiffre** : EGDB était absent de la box, donc cet Elo
n'est **pas comparable en absolu** aux portes antérieures (la comparaison interne
entre les deux bras, elle, tient — même binaire) ; et le holdout n'a pas servi
d'arbitre (écart 0,0004, et la perte ne prédit pas la force ici).

**Passe on-policy : −9,15 Elo, MAIS le protocole change DEUX facteurs.**
`cpx62-1119`/`1120` : le modèle exact rejoue 2M positions, refit sous
`--exact-fold`, porte contre son parent → **−9,15 Elo**, IC95 `[−16,9 ; −1,4]`.
⚠️ **Ne pas lire « l'on-policy dégrade »** : le corpus de TURNOVER est un
**mélange 1:1 mémoire/frais** (c'est le sens de « turnover »), et ma passe est
passée à **100 % frais**. J'ai donc changé le générateur *et* la composition —
exactement l'écart « frais/mémoire » que §5.2 reproche déjà à VOL8M. Énoncé
correct : *remplacer le mélange 50/50 par du frais pur d'un seul modèle coûte
9,15 Elo*. Le mécanisme « plus fort → plus de nulles » est en revanche **réfuté
par mesure** (on-policy 18,06 % de nulles contre 21,41 % pour TURNOVER : plus
décisif, pas moins). **Expérience correcte à faire** : 1M frais d'EXACT mélangé
1:1 avec la moitié mémoire, un seul facteur qui bouge.

### Self-play on-policy à un seul facteur : PLAT — `cpx62-1127`/`1130`, 1er août

L'expérience corrigée a été faite. `cpx62-1127` reconstruit le corpus de
TURNOVER en ne changeant **qu'une chose** : le générateur de la moitié fraîche.
Moitié mémoire **byte-identique et vérifiée par hash**, `label_depth=4`,
`play_depth=8`, `max_plies=260`, graine `1618033`, ratio **1:1 asserté depuis le
manifeste de mélange** (1 000 000 / 1 000 000). `cpx62-1130` porte le modèle
obtenu contre son parent EXACT, avec EGDB :

| vue | n | score | Elo |
|---|---:|---:|---:|
| `q00` | 3000 | 48,75 % | −8,69 |
| `native` | 3000 | 50,08 % | +0,58 |
| **sommé** | **6000** | **49,42 %** | **−4,05**, IC95 `[−12,6 ; +4,5]` |

`A_FLAT_VS_B_NO_ESTABLISHED_GAIN`. **Deux lectures, toutes deux importantes :**

1. **La régression de `1120` ne se reproduit pas.** À un seul facteur, l'intervalle
   contient zéro. « L'on-policy dégrade » était bien un artefact du protocole à
   deux facteurs, et l'intuition de JFC — *au pire on devrait être aussi bons* —
   est **vérifiée**.
2. **Mais il n'y a aucun gain non plus.** La borne haute est `+4,5 Elo` : un gain
   de l'ordre de celui du fold (`+15`) est **exclu**. Une génération d'autojeu
   par un champion plus fort ne fait pas monter le modèle suivant.

**Mécanisme mesuré, pas supposé.** Les deux fits sont comparables ligne à ligne
(même volume, même recette, même fold) :

| | EXACT (corpus TURNOVER) | MIXFRESH (moitié fraîche on-policy) |
|---|---:|---:|
| records | 2 000 000 | 2 000 000 |
| **buckets visités (≥1)** | **130 086** | **124 948** |
| nulles | 21,4 % | 19,2 % |

À volume strictement égal, le corpus on-policy visite **5 138 buckets de moins
(−3,9 %)**. Le générateur plus fort joue **plus étroit** : il échange de la
couverture contre de la qualité d'étiquette — et à ce stade de la campagne, **la
couverture est précisément la ressource rare** (~4,3 observations par paramètre
libre). Cela explique le plat sans invoquer quoi que ce soit d'invérifié.

Le mécanisme « plus fort → plus de nulles → moins de signal » est **réfuté une
seconde fois** : 19,2 % de nulles contre 21,4 %, donc **plus** décisif.

**Conséquence de programme** : faire tourner l'autojeu à recette constante
n'est pas une voie de progression tant que la couverture est le facteur
limitant. Ce qui a payé ce jour-là, c'est le fold — une correction de méthode à
données constantes, pas un tour de manège supplémentaire.

### La couverture s'achète par les OUVERTURES — `cpx62-1131`/`1132`, 1er août

Deux sondes qui ne jouent **aucune partie de porte** et ne fittent **rien** :
même volume (500 000 records par cellule), on compte les buckets atteints dans
le fold exact. Bruit graine-à-graine mesuré par une cellule réplique :
**0,16 %**, donc seuil de significativité **0,32 %**.

`cpx62-1131` — cinq réglages contre la recette courante :

| cellule | buckets | Δ | nulles | Δ nulles |
|---|---:|---:|---:|---:|
| `ROP16` (`--random-open-plies 16`) | 86 778 | **+4,72 %** | 0,164 | −5,9 % |
| `NODECAY` (eps sans décroissance) | 85 068 | +2,66 % | **0,024** | **−86,4 %** ⚠️ |
| `EPS16` (`--explore-eps 16`) | 84 126 | +1,52 % | 0,152 | −13,0 % |
| `BASE` / `BASEBIS` | 82 867 / 82 999 | 0 / +0,16 % | 0,174 | — |
| `TOPK` (top-3, marge 30) | 81 093 | **−2,14 %** | 0,203 | +16,4 % |

**L'exploration structurée fait l'inverse de l'intuition** : rester près du
meilleur coup **rétrécit** la distribution (−2,14 % de couverture, +16,4 % de
nulles). Piste fermée.

⚠️ **Trou de garde trouvé et bouché.** `NODECAY` a effondré les nulles d'un
facteur 7 **et est passé** : le canari du registre surveille `|win − loss|`, or
des bourdes aléatoires se répartissent des deux côtés (skew 0,0048, aussi propre
que BASE). **Un corpus peut être détruit symétriquement.** Une garde de
distribution sur le taux de nulles a été ajoutée (`d8a4182e`) ; rejouée sur ces
chiffres elle marque `NODECAY` à −86,4 % et laisse tout le reste propre.

`cpx62-1132` — dose-réponse sur `--random-open-plies`, **et contrôle de
déterminisme** : `ROP16` rejoué à graine identique **reproduit 86 778 buckets à
l'unité**, comme `BASE` et `BASEBIS`. La sonde est déterministe.

| `rop` | buckets | Δ vs 8 | pas | `ge_100` | ouvertures |
|---:|---:|---:|---:|---:|---:|
| 8 | 82 867 | — | — | 6 807 | 8 226 |
| 16 | 86 778 | +4,72 % | +4,72 % | 7 135 | 8 985 |
| **24** | **88 760** | **+7,11 %** | +2,28 % | **7 280** | 9 906 |
| 32 | 88 999 | +7,40 % | **+0,27 %** | 7 274 | 11 245 |

**La courbe plafonne à 24.** Le pas 24→32 vaut `+0,27 %`, **sous le seuil de
0,32 %** : `ROP32` n'est pas distinguable de `ROP24`. Le verdict automatique dit
`COVERAGE_KNOB_FOUND_ROP32` parce qu'il classe chaque cellule contre `BASE`, pas
contre sa voisine ; **la lecture actionnable est `rop=24`**, et le choix est
argumenté ici plutôt que subi. Deux confirmations : `ge_10` et `ge_100` sont
**plus hauts** à 24 qu'à 32 (34 018 / 7 280 contre 33 972 / 7 274), donc au-delà
de 24 les ouvertures supplémentaires (9 906 → 11 245) ne touchent plus de
nouveaux buckets — elles dupliquent ; et la longueur des parties baisse
(2 206 611 → 2 112 305 plies), signe que l'on démarre de plus en plus loin dans
des ouvertures artificielles.

**Le corpus qui en découle** (`cpx62-1133`) : recette TURNOVER figée, moitié
mémoire byte-identique, mélange 1:1 vérifié, **seul `rop` passe de 8 à 24**.
Ouvertures de la moitié fraîche **19 853 contre 16 396** (`+21 %`), et couverture
du corpus 2 M complet **128 482 buckets contre 124 948** pour MIXFRESH — soit
`+2,83 %`, pas `+7,11 %` : le gain se dilue parce que la moitié mémoire, qui est
la moitié du corpus, ne bouge pas. On reste **sous** les `130 086` du corpus
TURNOVER d'origine.

⚠️ **Le holdout de `1133` tombe à `0,400335`** contre `0,449827` (MIXFRESH) et
`0,442898` (EXACT). **Ce chiffre ne veut rien dire ici** : le holdout est tiré du
corpus lui-même, et un corpus dont les parties démarrent 24 plies plus loin dans
une ouverture aléatoire est intrinsèquement moins entropique (nulles `18,1 %`
contre `19,2 %` et `21,4 %`). Comparer des holdouts **entre corpus différents**
n'a pas de sens, et la perte ne prédit pas la force — quatre fois mesuré. Ne rien
en attendre avant la porte.

**Ce que ces sondes n'établissent pas : rien en Elo.** `+7,11 %` de couverture
peut valoir quelques Elo ou zéro. **C'est une porte qui tranche, pas une sonde de
couverture** — et elle a tranché contre.

### ⛔ La couverture N'EST PAS le levier — `cpx62-1134`, 1er août

Porte `ROP24` contre `EXACT`, avec EGDB, `n=6000`, même pool et même adversaire
que `cpx62-1130` :

| vue | n | score | Elo |
|---|---:|---:|---:|
| `q00` | 3000 | 49,27 % | −5,10 |
| `native` | 3000 | 48,07 % | −13,44 |
| **sommé** | **6000** | **48,67 %** | **−9,27**, IC95 `[−17,9 ; −0,7]` |

`A_BELOW_B`. **La borne haute est sous zéro : régression ÉTABLIE.** Et la
comparaison qui compte est celle-ci, à adversaire, pool et taille identiques :

```text
rop = 8   (cpx62-1130)   −4,05 Elo   couverture 124 948
rop = 24  (cpx62-1134)   −9,27 Elo   couverture 128 482   (+2,83 %)
```

**La couverture monte, la force descend.** Des buckets atteints depuis des
ouvertures aléatoires profondes ne sont visités par **aucune partie réelle** :
on gonfle un compteur en diluant la masse sur la distribution réellement jouée.

⚠️ **Correction d'une inférence à moi.** À `cpx62-1130` j'ai écrit que la
couverture était « le mécanisme mesuré » du plat on-policy. Le `−3,9 %` était
mesuré ; **son rôle causal ne l'était pas** — c'était un corrélat promu en cause.
La chaîne `1131`→`1134` a testé l'inférence directement, dans le sens qu'elle
prédisait, et l'a **falsifiée**. Le plat on-policy reste un fait ; son
explication est rouverte.

**Conséquence de méthode** : le compte de buckets rejoint la loss holdout au rang
de **diagnostic** — il décrit un corpus, il ne le sélectionne pas. Trois familles
ont maintenant été fermées par le même motif (hard-replay v1 `−648 Elo`,
VOL8M `−14,95`, et celle-ci) : **plus de données/de couverture n'achète pas de la
force**, et c'est la troisième fois que le projet le paie pour le réapprendre.

**Contre le champion réel** (`cpx62-1121`) : EXACT bat **TURNOVER** de
**+13,32 Elo**, IC95 `[+5,5 ; +21,2]`, n=6000 — borne basse au-dessus de zéro,
gain établi. Les trois mesures sont cohérentes (+17,1 vs CONTROL, +13,3 vs
TURNOVER, l'écart correspondant à un CONTROL marginalement plus faible).

**Objection EGDB levée** (`cpx62-1129`, 1er août). `cpx62-1128` a posé la base
WLD 2-7 sur cpx62 (158 fichiers, 4,8 Go, `max_pieces=7`, invariant du self-check
vert), et la porte rejouée **avec** la base rend **+15,12 Elo**, IC95
`[+6,6 ; +23,7]`, `n=6000` — `q00` `52,60 %` et `native` `51,75 %`, **les deux
bornes basses au-dessus de 50 %**. Le gain n'était donc pas un artefact du
réglage sans tablebase.

**PROMU CHAMPION GÉNÉRAL le 1er août 2026**, sur go explicite de JFC. La
promotion est purement documentaire et réversible par `git revert`. Elle est
**moins garnie** que celle de TURNOVER — ni garde Gen2, ni conversion P3/P4, ni
second pool indépendant — et l'enregistrement le borne nommément :
[`experiments/L3_EXACT_PROMOTION_20260801.md`](experiments/L3_EXACT_PROMOTION_20260801.md).

Détail complet, protocole et limites :
[`experiments/L3_EXACT_FOLD_20260801.md`](experiments/L3_EXACT_FOLD_20260801.md).

### Atlas de points aveugles jugé par Scan — `cpx62-1114`, 1er août

Première mesure de la campagne qui demande **où** la marge se perd, après quatre
confirmations que la perte en holdout ne prédit pas la force. 4 988 997 positions,
88 101 parties, 2 326 839 désaccords jugés, 27 min sur cpx62. Champion TURNOVER,
`d8` en jeu, `d10` au jugement, Scan en **juge** (`bb-size=0`, sans livre).

Quatre résultats :

1. **96,7 % de la perte est dans le jeu `calme`.** Les captures forcées font 23 %
   du corpus et **3,3 %** de la perte : quand la prise est forcée, on ne se
   trompe pratiquement jamais.
2. **87 % de la perte est avant la finale** (ouverture 39,3 % + milieu 47,5 % ;
   finales 13,2 %). L'effort « features de finale » ne vise pas là où ça part.
3. **Aucun point chaud.** Par masse ça paraît concentré (3 buckets = 50 %), mais
   les buckets de tête sont simplement les plus **peuplés** et leur coût *par
   position* est parmi les plus **bas** (0,064 pour le premier, qui pèse 30,6 %).
   Le bucket le plus cher par position (0,349) ne fait que 1 777 positions. La
   perte est **diffuse** : une erreur systématique de faible amplitude, étalée
   sur tout le jeu positionnel calme.
4. **0 conversion ratée sur 141 213 désaccords saturés** — la conversion n'est
   pas notre problème. *(Limite : le dénominateur est « désaccords saturés », pas
   « positions saturées » ; cf. la note d'expérience.)*

⚠️ **Cet atlas n'a pas de contrôle et ne conclut donc rien sur la capacité.** Un
profil diffus dans le jeu calme peut être propre au modèle mesuré ou constituer
un fond commun aux évaluations linéaires comparées à Scan. **Le témoin Gen2,
même protocole et même budget, est requis avant toute lecture.** Son
différentiel localisera les écarts de profil sous les géométries 8cf/32cf ; il
ne séparera pas un effet de classe linéaire, puisque les deux bras restent
linéaires. Rapport à l'arbitrage 32cf, dont la prémisse de clôture (« 8cf
sous-alimenté ») a été falsifiée par `home-1004` : cet atlas est le premier
élément neuf, mais il **ne tranche pas** sans le témoin. Décision à JFC.

Détail, tableaux et limites :
[`experiments/L3_SCAN_BLIND_SPOT_ATLAS_20260801.md`](experiments/L3_SCAN_BLIND_SPOT_ATLAS_20260801.md).

**Témoin EXACT/Gen2 terminé sur HOME — `home-1143quater/1144bis/1145`.** Les
deux atlas et le différentiel ont été mesurés au SHA moteur
`31dc371cb027bc83e25c8bedcd02fa7891775454`, avec le même binaire Scan, les
mêmes profondeurs, seeds et budgets. `n_ext = 120` reste constant ; seul
`n_pat` passe de `4 251 528` (EXACT, 8cf) à `17 006 112` (Gen2, 32cf).

| bras | positions (ordinaires) | désaccords jugés | taux de désaccord | coût ordinaire / position | conversions ratées |
|---|---:|---:|---:|---:|---:|
| EXACT | 1 108 434 (1 075 109) | 513 784 | 0,463522 | **0,069273** | 0 / 33 325 |
| Gen2 | 776 034 (748 785) | 376 820 | 0,485572 | 0,073977 | 0 / 27 249 |
| Δ EXACT − Gen2 | — | — | **−0,022050** | **−0,004704** | 0 |

Le volume diffère parce que le protocole dimensionne chaque shard en **temps**,
pas en nombre de parties ; les comparaisons portent donc sur des taux. EXACT a
un coût ordinaire inférieur de `0,004704` par position, soit `−6,36 %` relatif
à Gen2, et désaccorde Scan `−2,205 pp` moins souvent.

Le profil n'est toutefois pas une domination uniforme. EXACT est meilleur en
ouverture (`Δ coût/position = −0,014957`) et sans dame (`−0,016277`), mais plus
cher dans les finales 7–12 pièces (`+0,014960`) et lorsque des dames subsistent
(un seul côté `+0,029604`, deux côtés `+0,088758`). Le jeu calme concentre
toujours presque toute la masse de coût dans les deux bras ; EXACT y réduit
néanmoins le coût par position de `0,005652`. Les extrêmes clairsemés — notamment
`en_avance_3+`, seulement 865 positions ordinaires côté Gen2 — ne doivent pas
porter une décision seuls. Aucun bras ne rate une conversion dans cet
instrument ; cela ne remplace pas le benchmark P3/P4 corrigé du §0.4.

**Portée du résultat :** géométrie/profil **oui** ; attribution aux features
**non** (tenues constantes) ; classe linéaire/non-linéaire **non** (deux bras
linéaires) ; ablation causale des poids **non** (poids et trajectoires propres à
chaque modèle). C'est un différentiel descriptif, pas un échantillon iid et pas
une autorisation de promotion.

**Décision de programme.** Ce témoin ferme le soupçon opérationnel selon lequel
le passage à 8cf aurait créé un point aveugle global qui justifierait un retour
à Gen2/32cf : sur leurs trajectoires respectives, EXACT est meilleur sur les
deux métriques globales. **Aucun retour 32cf, aucune nouvelle feature et aucune
repondération des buckets de l'atlas n'en découlent.** Les finales avec dames
restent un jeu d'audit, pas une cible d'entraînement établie. Une attribution
causale à la géométrie exigerait un corpus de positions fixe et apparié ; elle
n'est pas nécessaire pour la décision courante.

La suite prioritaire reste le facteur unique de régularisation déjà engagé :
centrer le ridge sur le parent avec `--prior-mean <parent> --prior-decay 0`, à
géométrie, features et corpus constants. La force contre EXACT décide d'abord ;
l'atlas ne sert qu'en audit secondaire si le bras paie, notamment dans les
finales avec dames. `--hier-l2` appartient à la même famille mais ne vient
qu'ensuite, dans une expérience séparée.

Incident d'exécution sans résultat scientifique : `home-1144` a été arrêté
après que 5 des 16 arbitres 32cf ont dépassé le timeout d'initialisation de 60 s
sous contention. `home-1144bis` a conservé exactement le même SHA et le même
protocole, avec les seuls démarrages espacés de 10 s ; les 16 shards ont alors
terminé sans `ABORT`.

Résultats immuables :

- EXACT : `r2:jass-data/runs/home-1143quater-l3-scan-blind-spot-atlas-exact-v1/20260801T211028Z-31dc371c` ;
- Gen2 : `r2:jass-data/runs/home-1144bis-l3-scan-blind-spot-atlas-gen2-v1/20260801T215804Z-05949b14` ;
- différentiel : `r2:jass-data/runs/home-1145-l3-scan-blind-spot-differential-v1/20260801T223342Z-05949b14`
  (`differential.json` SHA-256
  `332bfebccec36c9c06e2b80590d1128a10a66dd097414bad5accf8cc685d8590`).

Préréglage, invariants et limites :
[`experiments/L3_SCAN_BLIND_SPOT_DIFFERENTIAL_PROTOCOL_20260801.md`](experiments/L3_SCAN_BLIND_SPOT_DIFFERENTIAL_PROTOCOL_20260801.md).

### Reverse-seed, poids d'échec et BLEND50 — quatre verdicts du 30-31 juillet

Suite directe de la clôture hard-replay : les positions d'échec de conversion
sont réutilisées comme **reverse seeds zero-target appariés**, dont le WDL est
régénéré par self-play au lieu d'être hérité. Tous les chiffres ci-dessous sont
en **vues additionnées, `n = 6000`**, sur pool neuf apparié.

| Axe | Bras / readout | W-N-D traitement | Taux | Elo | IC95 Elo | Verdict |
|---|---|---|---:|---:|---|---|
| Reverse-seed 2M | `cpx62-1086` / `home-1091` | 2957-302-2741 | 0,5180 | **+12,51** | `[+3,95 ; +21,10]` | `ABOVE_MATCHED_CONTROL_IC95` |
| Poids d'échec ×2 | `home-1096` / `home-1102` | 2709-325-2966 | 0,4786 | **−14,89** | `[−23,46 ; −6,34]` | `FAILED_X2_BELOW_UNWEIGHTED` |
| BLEND50 statique | `cpx62-1104` / `home-1105` | 2789-324-2887 | 0,4918 | −5,68 | `[−14,23 ; +2,88]` | `BLEND50_VS_TURNOVER_INCONCLUSIVE` |
| Reverse-seed 4M | `cpx62-1106` / `home-1108` | 2712-295-2993 | 0,4766 | **−16,28** | `[−24,88 ; −7,71]` | `SCALE4M_BELOW_MATCHED_CONTROL` |

**Poids d'échec ×2 : négatif établi.** Pondérer deux fois les positions d'échec
de conversion coûte `−14,9 Elo`, IC95 entièrement négatif. Ne pas répéter.

**BLEND50 : `INCONCLUSIVE`, pas « négatif ».** L'IC95 traverse zéro. À
`n = 6000` vues additionnées nous n'établissons qu'un effet de l'ordre de
`±8,5 Elo` : le clore est une **décision de programme**, pas une réfutation.
Un effet réel de quelques Elo resterait invisible à cette puissance.

**L'inversion 2M → 4M, et une réserve sur sa lecture.** Le positif à 2M et le
négatif à 4M ont des IC95 disjoints, l'inversion est donc réelle sur
l'estimateur additionné. Mais **les deux résultats ne pèsent pas pareil vue par
vue** : à 2M seule la Q00 exclut zéro (`+17,85`, IC95 `[+5,7 ; +30,0]`), la
native le traverse (`+7,18`, IC95 `[−4,9 ; +19,3]`) ; à 4M **les deux vues**
l'excluent négativement (`−13,32` et `−19,24`). Avant de chercher un mécanisme
d'inversion lié à l'échelle, l'hypothèse la moins chère reste qu'un positif
porté par une seule vue n'a pas survécu à la réplication — exactement ce que
[`experiments/L3_VIEW_AGREEMENT_AND_POWER_20260726.md`](experiments/L3_VIEW_AGREEMENT_AND_POWER_20260726.md)
dit de nos écrans. L'axe reverse-seed **à cette échelle** est clos ; la
tendance 2M n'est pas reproduite.

**Diagnostic `cpx62-1110` — échec technique, aucun résultat scientifique
perdu.** Le diagnostic read-only de l'inversion est tombé en phase `compare`
après onze minutes, `rc=2`, **après** avoir produit ses vingt-quatre atlas.
Cause : dérive de schéma entre deux générations de certificats. Le readout 2M
`home-1091`, écrit le 30 juillet, n'a pas de `protocol.records_per_arm` ; le
readout 4M `home-1108`, écrit le lendemain, l'a ; et
`l3_reverse_seed_scale_diagnostic.py` l'exigeait des deux. Les tests du tool ne
l'ont pas vu parce que leur fixture fabrique un readout qui possède toujours le
champ. Le volume par bras est de toute façon porté par le certificat **source**
(`cpx62-1086.design.records_per_arm = 2000000`), déjà validé par le même tool.
Corrigé : le champ du readout n'est plus exigé, seulement vérifié quand il est
présent. Deux tests de régression ajoutés, et les quatre validations rejouées
sur les certificats réels. Le job est re-lançable tel quel.

⚠️ **Le log de l'étape `compare` part dans `$W/compare.log`, qui n'est pas
publié** : l'échec était invisible depuis R2 et il a fallu rejouer les
validations localement pour le localiser. À corriger dans le template.

### Spécialiste `L3-IMBALANCE2`

1. ne pas prolonger 0890bis ;
2. considérer le DOE `2 × 2` comme terminé : TOP3 exclusif et reweight V2
   sont causalement défavorables ;
3. ne pas réutiliser RC4 ;
4. ne pas relancer P3 à recette V2 identique ;
5. ne jamais présenter un résultat spécialiste comme un remplacement généraliste.

## 7. Artefacts de référence

- C0 pur : jobs `ccx33-0790-l3-pure-c0-a-v1` et gate `0795` ;
- baseline générale propre : `cpx62-0842` ;
- triangle M0 certifié :
  `r2:jass-data/runs/home-0934-finalize-m0-triangle-v2/20260724T020401Z-922930bc` ;
- couverture M0 :
  `r2:jass-data/runs/home-0935-l3-pure-m0-coverage-v3/20260724T020913Z-952f46d0` ;
- P1 V2 : `r2:jass-data/runs/ccx33-0852-l3-imbalance2-role-v2-p1/20260720T073236Z-61839d1d` ;
- P2 V2 : `r2:jass-data/runs/ccx33-0859-l3-imbalance2-role-v2-p2/20260720T105918Z-a0d2f238` ;
- consolidation : `r2:jass-data/runs/ccx33-0870-l3-imbalance2-p2-consolidate/20260720T175742Z-0e657bba` ;
- D0 : `r2:jass-data/runs/cpx62-0871-l3-imbalance2-d0-diagnostic/20260720T193310Z-bced44e7` ;
- D1-RC4 : `r2:jass-data/runs/cpx62-0872-l3-imbalance2-d1-rc4/20260720T202210Z-fa68634c` ;
- D1-X : `r2:jass-data/runs/cpx62-0874-l3-imbalance2-d1x-autopsy/20260720T220921Z-a7301ac6` ;
- matrice TOP3 0908 salvagée : `r2:jass-data/runs/cpx62-0920-salvage-0908-stable-top3-matrix-v1/20260723T133448Z-2ed34499`.
- miroir causal L3-PURE : `r2:jass-data/runs/cpx62-0921-l3-pure-top3-stable-conversion-matrix-v1/20260723T134611Z-fbf0c93e`.
- autopsie 0842/0890bis :
  [`archives/l3/TOP3_SPECIALIST_RECIPE_AUTOPSY_20260723.md`](archives/l3/TOP3_SPECIALIST_RECIPE_AUTOPSY_20260723.md).

Le préflight HOME M1 `home-0936-l3-pure-m1-preflight-v1` est vert
(`M1_PREFLIGHT_READY`). L’entraînement préenregistré suivant est
`home-0937-l3-pure-m1-train-v1`; il conserve une tranche fraîche commune
byte-identique entre F500/F2M/R2M et refuse toute convergence au plafond.
L’évaluation à défenseur fixe et de force générale reste un job séparé, lancé
seulement après publication vérifiée des trois modèles.

`home-0937` a produit et publié les sources fraîches ainsi que les trois
assemblages, puis s’est arrêté proprement parce que F500 atteignait le plafond
L-BFGS de 60 itérations. Le diagnostic `home-0938` classe explicitement la
cause `MAXITER` (ni OOM, ni timeout). La reprise `home-0939` réutilise les
sources 0937 vérifiées par inventaire/checksum, porte le budget à 200 et exige
désormais le statut `success` réel de SciPy avec rapport d’optimiseur ; elle ne
régénère donc aucune position et ne relâche pas le critère de convergence.
`home-0940/0941` montre que 0939 atteint 200 itérations avec un gradient infini
encore élevé (`2.170022328647e-02`). La reprise V2 `home-0942` conserve donc
les tolérances SciPy, augmente l’historique de courbure L-BFGS de 5 à 20
(dimension 8cf prunée compatible HOME) et autorise jusqu’à 1000 itérations,
toujours avec `success=true` obligatoire.
Le résultat 0943 est finalement `5.008773068760e-04` à 1000 itérations :
la courbure renforcée réduit le gradient d’un facteur 43. Comme les poids PJTW
sont quantifiés au millième, `home-0944` préenregistre `gtol=1e-3`, conserve
`maxcor=20/maxiter=1000` et exige toujours une terminaison SciPy réussie. Les
checkpoints sont désormais publiés même si un bras ultérieur échoue.
`home-0944` est terminé avec succès : F500, F2M et R2M ont tous convergé et
sont publiés. `home-0945` est l’évaluation non promotable préenregistrée :
force Q00 et native contre C0, ancrage Q00 contre Gen2, puis conversion P1–P4
contre le même défenseur Gen2 fixe.

Correctif du 25 juillet 2026 : les volets conversion de `home-0945` et
`home-0949` sont supersédés. Le gauge FEN historique a été produit avec les
pions et dames noirs intervertis lors de l’export JNNW → FEN. Les poids
entraînés, les ablations et le triangle de force M0 ne sont pas invalidés.
`home-0954` fournit le gauge JNNW stable corrigé ; `home-0955` rejoue C0, P1,
F500, F2M, R2M, AB_MAT, AB_KING et AB_EXTRAS sur exactement ces mêmes
positions et le même défenseur Gen2.

Les SHA, inventaires et checksums restent dans les manifests R2 et les statuts
GitOps. Aucun résultat volumineux n’est re-committé dans Git.

Le diagnostic causal `home-0961ter` clôt ensuite le faux plafond de
conversion : avec les poids Scan exacts et le défenseur Gen2 historique
inchangé, la réparation de légalité/terminaison fait passer `p3_mince` de
38,00 % à 99,00 % et `p4_egal` de 35,33 % à 98,00 %. L’ordre racine Scan
n’ajoute plus que +1,00 et +2,01 points. Le moteur, et non l’architecture
linéaire, était la cause dominante du déficit mesuré.

La reprise M1 doit donc d’abord rejouer sur le moteur réparé les poids déjà
produits C0/P1/F500/F2M/R2M et les ablations, appariés à la matrice 0955 et
avec un défenseur historique figé. Une nouvelle génération de données n’est
autorisée qu’après ce readout : si les poids existants restent sous le
plancher de conversion, la branche suivante sera une réplication
Scan-faithful propre ; sinon la revue portera sur le candidat M1 et sa force
générale. Aucune promotion ni continuation n’est automatique.

`home-0962` confirme que le moteur réparé convertit avec tous les poids M1 :
F500 atteint 98,00/99,33 %, F2M 97,33/98,33 % et R2M 99,67/97,33 % sur
`p3_mince/p4_egal`, sans erreur. `home-0963` rejoue ensuite la force sur 400
parties par vue et mesure les corpus exacts. F2M obtient 60,00 % Q00 et
60,25 % native contre C0, puis 91,00 % Q00 contre Gen2. Sa couverture 8cf
dépasse aussi C0 de 3 043 buckets visités et de 3 834 buckets vus au moins
100 fois. R2M est positif mais moins fort ; F500 reste sous la couverture du
parent. La règle préenregistrée sélectionne donc F2M pour une confirmation
indépendante, sans le promouvoir.

La confirmation suivante emploie 500 nouvelles ouvertures synthétiques
appariées, sans recouvrement avec DILF ni les pools synthétiques antérieurs,
soit 1 000 parties dans chaque vue. F2M doit avoir la borne basse à 95 % au
dessus de 50 % contre C0 en Q00 et native, et ne pas présenter de régression
établie contre R2M. Un succès ouvre seulement une revue humaine de promotion.

`home-0964` confirme F2M sur 1 000 parties indépendantes par vue : `60,35 %`
Q00 et `59,95 %` native contre C0, avec les deux bornes basses à 95 % au-dessus
de `57 %`. F2M et R2M restent statistiquement équivalents en confrontation
directe. Après autorisation humaine explicite, **F2M devient le champion de la
lignée L3-PURE et le parent prévu de M2**. Gen2-mmto reste provisoirement le
champion général historique.

Le protocole suivant rejoue F2M 8cf contre Gen2-mmto 32cf en construisant les
deux moteurs depuis le même SHA réparé. Il emploie un nouveau pool indépendant
et exige une borne basse à 95 % au-dessus de 50 % en Q00 et native pour
recommander F2M comme champion général. Détails :
[`experiments/L3_F2M_PROMOTION_AND_GEN2_REPAIRED_BENCH_20260725.md`](experiments/L3_F2M_PROMOTION_AND_GEN2_REPAIRED_BENCH_20260725.md).

`home-0965` passe ce gate : F2M marque `57,25 %` en Q00
(`562-21-417`, IC95 `[54,22 ; 60,28]`) et `58,60 %` en cadence native
(`580-12-408`, IC95 `[55,57 ; 61,63]`). Après revue humaine explicite,
**F2M remplace Gen2-mmto comme champion général**. Gen2 reste la
référence historique figée. *(F2M a lui-même été remplacé par TURNOVER le
27 juillet 2026, cf. `home-0996`.)*

M2 repart de F2M avec 2 millions de positions entièrement fraîches, toujours
en 8cf/Q00 et WDL pur, sans replay, oracle, TOP3 ni reweight. L'entraînement
n'autorise qu'une évaluation séparée ; aucune promotion ou continuation M3
n'est automatique. Protocole :
[`experiments/L3_PURE_M2_PROTOCOL_20260725.md`](experiments/L3_PURE_M2_PROTOCOL_20260725.md).

`home-0966bis` termine l'entraînement M2 : 2 000 000 de positions fraîches,
convergence en 236 itérations, log-loss holdout `0,444311`, modèle SHA-256
`75ace3c0…`. L'écran indépendant `home-0967` est préenregistré avant les
matchs : force M2/F2M, garde-fou Gen2, conversion P3/P4 et couverture exacte.

`home-0967` s'est arrete avant tout match au controle du pool d'ouvertures.
La relance `home-0970` garde exactement les bras, budgets et seed
preenregistres, mais selectionne deterministiquement 500 ouvertures uniques
et disjointes depuis 2 000 candidates. Les builds de 0967 avaient passe ;
aucun verdict scientifique partiel n'est reutilise.

Le claim `home-0970` sur snapshot de controle stale a ete rejete par le
garde-fou SHA avant tout match. `home-0970bis` est le run autoritatif.

`home-0970bis` termine avec le verdict
`M2_PLATEAU_OR_REGRESSION_REVIEW`. M2 marque 50,60 % Q00 et 49,05 % native
contre F2M : aucune pente de force n'est établie. Les garde-fous passent :
56,30/58,80 % contre Gen2, conversion P3/P4 à 99,00/98,67 %, et couverture
utile en hausse de 2 075 buckets visités et 352 buckets vus au moins 100
fois. La recette d8/2M n'est donc pas poursuivie à l'identique. Le prochain
bras causal conserve F2M, 8cf, WDL pur, 2M, seeds, exploration, split et fit,
et change seulement la profondeur de jeu de d8 à d10. Protocole :
[`experiments/L3_PURE_D10_CAUSAL_PROTOCOL_20260726.md`](experiments/L3_PURE_D10_CAUSAL_PROTOCOL_20260726.md).

`home-0971` termine le bras d10 : exactement 2 000 000 positions fraîches,
split par ouverture 1 802 842/197 158, convergence en 16 itérations,
log-loss holdout `0,443257`, modèle SHA-256 `18930613…`. L'entraînement
n'autorise qu'une évaluation. Le readout indépendant `home-0972` compare D10
à M2 d8, F2M et Gen2 dans les deux vues, puis vérifie conversion et couverture
sur un pool seed 314159 préflighté, unique et disjoint (SHA-256 `e41ae387…`).

`home-0972` conclut `D10_PLATEAU_OR_REGRESSION_REVIEW`, avec tous les
garde-fous valides. D10 fait 47,50/50,70 % contre M2 d8 et 48,80/51,00 %
contre F2M en Q00/native. La conversion reste à 99,33/98,67 %, mais la
couverture recule de 4 864 buckets visités face à M2. Le prochain bras causal
est donc d12 pur à 2M, toujours depuis F2M avec les mêmes seeds ; seul le
facteur profondeur change. Protocole :
[`experiments/L3_PURE_D12_CAUSAL_PROTOCOL_20260726.md`](experiments/L3_PURE_D12_CAUSAL_PROTOCOL_20260726.md).

`home-0974bis` conclut `D12_PLATEAU_OR_REGRESSION_REVIEW`. D12 fait
48,50/49,05 % contre D10 et 45,85/46,95 % contre F2M en Q00/native. La
régression Q00 contre F2M est établie (IC95 supérieur 48,91 %), alors que la
loss holdout tombe à 0,427862 et que P3/P4 restent à 99 %. La profondeur
monoprofondeur améliore donc le fit offline sans transférer en force. Le mix
d10/d12 `0975/0976` reste interdit : son déclencheur exigeait tous les
garde-fous verts.

Le facteur suivant est le turnover temporel à volume constant : 1M positions
de l'époque F2M + 1M positions fraîches de M2, même parent, d8, 8cf, Q00, WDL,
split et fit. Le corpus a été reconstruit deux fois bit-identique, avec des IDs
d'ouverture namespacés par source ; SHA JNNW `9b7db67a…`, JSM `acf3bbf4…`.
Sa couverture diagnostique est 210 381 buckets visités et 28 160 à fréquence
≥100. Protocole :
[`experiments/L3_PURE_TURNOVER_PROTOCOL_20260726.md`](experiments/L3_PURE_TURNOVER_PROTOCOL_20260726.md).

`home-0977` converge en 204 itérations (loss holdout `0,444060`) et produit le
modèle `b2c79b36…`. `home-0978` conclut
`TURNOVER_DIRECTIONAL_CONFIRMATION_REVIEW`, avec tous les garde-fous verts.
TURNOVER fait 52,20/51,05 % contre M2 et 52,10/51,15 % contre F2M en
Q00/native, soit quatre estimations positives, mais aucune borne basse à 95 %
au-dessus de 50 %. P3/P4 restent à 98/99 % et la couverture dépasse les deux
contrôles.

La seule suite autorisée est la confirmation indépendante du même
modèle sur 1 000 nouvelles ouvertures appariées, soit 2 000 parties par cellule
contre M2 et F2M dans les deux vues. Le readout consolide ensuite 3 000 parties
par cellule. `home-0979` a échoué techniquement avant la première partie sur une
déclaration Bash incompatible avec `set -u`; `home-0980` est la relance propre
avec protocole et pool inchangés. Protocole :
[`experiments/L3_PURE_TURNOVER_CONFIRMATION_PROTOCOL_20260726.md`](experiments/L3_PURE_TURNOVER_CONFIRMATION_PROTOCOL_20260726.md).

`home-0980` termine avec
`TURNOVER_EFFECT_CONFIRMED_HUMAN_REVIEW`. Sur le pool frais, TURNOVER marque
53,775 % Q00 (`1056-39-905`, +26,28 Elo, IC95 `[51,61 ; 55,94]`) et 53,20 %
natif (`1047-34-919`, +22,27 Elo, IC95 `[51,03 ; 55,37]`) contre M2 : la
supériorité est établie dans les deux vues. Face à F2M, les scores sont
50,35/50,90 % ; aucune régression n'est établie, mais aucune supériorité non
plus. Le cumul des deux pools confirme l'effet contre M2 à 53,25 % Q00 et
52,483 % natif sur 3 000 parties par cellule. TURNOVER n'est donc pas promu.

Ce résultat clôt la recette M2 100 % fraîche telle quelle et identifie la
mémoire temporelle comme levier causal. Le test suivant garde F2M, 2M records,
d8, 8cf/Q00, WDL et `L2=3e-5`, mais dose le replay à 25 % : 500k positions de
l'époque F2M et 1,5M de l'époque M2. Le préflight reproductible `home-0981`
doit précéder le fit `home-0982` et le readout `home-0983`. Protocole :
[`experiments/L3_PURE_REPLAY25_PROTOCOL_20260726.md`](experiments/L3_PURE_REPLAY25_PROTOCOL_20260726.md).

Le premier claim `home-0981` est arrêté avant calcul par son garde-fou SHA :
le préfixe court était correct, mais pas le SHA complet épinglé. La relance
`home-0981bis` exécute correctement mix, split, build, tests, mini-fit,
couverture et pool indépendant, puis expose au dernier certificat un écart de
schéma : le nombre de records de couverture est publié sous
`corpus.total_records`, pas à la racine. Aucun verdict scientifique n'est tiré
de ces échecs techniques. `home-0981ter` corrige uniquement ce chemin de champ
et constitue la relance autoritative du même préflight.

`home-0981ter` conclut `REPLAY25_PREFLIGHT_READY`. Le mix bit-reproductible
contient exactement 500 000 records époque F2M et 1 500 000 époque M2
(JNNW `29c5b99d…`, JSM `5ea8c5a6…`) ; le split par ouverture est
1 799 835/200 165. NumPy 1.26.4, SciPy 1.14.1, build, tests, mini-fit et pool
indépendant passent. La couverture compte 209 626 buckets visités et 28 166
à fréquence ≥100. Le split culmine à 920 180 KiB de RSS. Le certificat autorise
uniquement le fit `home-0982`, sans promotion ni continuation automatique.

`home-0982` termine avec `REPLAY25_TRAINING_SCREEN_READY`. Son L-BFGS converge
en 156 itérations (`gradient_inf_norm=0,0008835 < gtol=0,001`), avec une loss
holdout de 0,444145 et 1 414 848 KiB de RSS. Le modèle exact est
`289047ff33c93f518ec8c853fb1c1ac8f7e3a4e52299277b314f0ac712022950`.
Le readout `home-0983` conclut `REPLAY25_DOSE_CLOSED_REVIEW`. Sur 1 000 parties
indépendantes par cellule, REPLAY25 marque 51,25/53,90 % contre M2 en
Q00/native, mais seulement 46,90/49,00 % contre TURNOVER 50/50. La régression
Q00 face à TURNOVER est établie : IC95 `[43,83 ; 49,97]`. Face à F2M, il reste
plat à 50,05/49,65 % ; la garde Gen2 reste positive à 56,95/58,35 %.

La conversion reste saturée (97,67 % sur P3 et 99,33 % sur P4). La couverture
est supérieure à M2 (209 626 contre 206 565 buckets visités), mais légèrement
inférieure à TURNOVER (210 381). Le dosage 25/75 améliore donc bien le modèle
100 % frais sans rejoindre le dosage 50/50 et sans dépasser F2M. Le résultat
complet est publié sous :
`r2:jass-data/runs/home-0983-l3-pure-replay25-independent-eval-v1/20260726T112309Z-42b9af7e`.
Il conserve `promotion_authorized=false` et `automatic_next_job=null`.

La branche conditionnelle figée avant ce verdict est donc ouverte. Le facteur
suivant est l'écran L2 `{1e-5, 3e-5, 1e-4}` sur l'unique corpus TURNOVER 50/50,
sans nouvelle génération ni changement de replay. Le préflight
`home-0984` s'est fermé avant tout split, build ou fit : le résumé compact des
cellules de force publie `n` et W/D/L, mais pas le booléen brut `complete`.
`home-0984bis` corrige uniquement ce contrat en exigeant `n=1000` et
`W+D+L=1000` dans chacune des huit cellules. Un test exécute désormais le
contrat sur le schéma réel et vérifie aussi qu'une cellule tronquée ferme le
job. Ce préflight authentifie ensuite le corpus, le split, le contrôle
`L2=3e-5`, l'environnement SciPy et le nouveau pool indépendant avant tout fit.
Protocole :
[`experiments/L3_PURE_TURNOVER_L2_SCREEN_PROTOCOL_20260726.md`](experiments/L3_PURE_TURNOVER_L2_SCREEN_PROTOCOL_20260726.md).

`home-0984bis` termine avec `TURNOVER_L2_PREFLIGHT_READY`. Le split TURNOVER
est reconstruit deux fois à l'identique (1 800 796 train / 199 204 holdout),
NumPy 1.26.4 et SciPy 1.14.1 sont isolés, les deux mini-fits passent et le pic
du split reste à 919 896 KiB. Le nouveau pool indépendant contient 500
ouvertures, seed `1836313`, SHA-256 `e7b89a5e…`, sans recouvrement. Le
certificat autorise uniquement `home-0985`, qui fitte `L2=1e-5` et `L2=1e-4`
en parallèle face au contrôle immuable `L2=3e-5`.

`home-0985` termine avec `TURNOVER_L2_TRAINING_SCREEN_READY`. Les deux bras
convergent réellement sur le corpus TURNOVER certifié (2 000 000 records,
split 1 800 796 / 199 204, seed `577215`), sans nouvelle génération ni entrée
teacher :

| bras | L2 | itérations | `gradient_inf_norm` | loss holdout | modèle SHA-256 |
|---|---:|---:|---:|---:|---|
| `L2_1E5` | `1e-5` | 375 | `0,00092379` | `0,444361` | `27cf9bed…` |
| `L2_3E5_CONTROL` | `3e-5` | 204 | — | `0,444060` | `b2c79b36…` |
| `L2_1E4` | `1e-4` | 170 | `0,00074504` | `0,446187` | `0b710b80…` |

Les deux optimiseurs sortent en `CONVERGENCE: NORM_OF_PROJECTED_GRADIENT_<=_PGTOL`
sous `gtol=1e-3`, avec des pics de 1 411 344 et 1 431 056 KiB de RSS, conformes
au budget HOME de deux optimiseurs concurrents. Le classement des losses place
le contrôle `3e-5` devant `1e-5` puis `1e-4`, mais **ces losses sont des
diagnostics et ne sélectionnent rien** : seule la force mesurée sur le pool
indépendant décide. Le résultat conserve `promotion_authorized=false` et
`automatic_next_job=null`. Prefixe immuable :
`r2:jass-data/runs/home-0985-l3-pure-turnover-l2-train-v1/20260726T123823Z-ad067a4b`.

Le readout `home-0986` est donc le seul job autorisé par ce certificat. Il
compare d'abord chaque candidat au contrôle TURNOVER sur le pool indépendant
`1836313` (500 ouvertures, SHA-256 `e7b89a5e…`), en Q00 d9 et en cadence
native ; les cellules de garde F2M/Gen2 et P3/P4 ne s'ouvrent que pour les
candidats dont les deux estimations ponctuelles dépassent 50 %. Si aucun ne
franchit ce filtre préenregistré, `L2=3e-5` est retenu et le facteur L2 est
clos.

`home-0986` s'est arrêté techniquement à l'étape
`build-guard-and-fixed-defender-engines`, après avoir pourtant construit les
deux moteurs 32cf sans erreur. Le témoin `--perft 1` du roi-capture est le test
de non-régression de `5f5a7e7b` (déduplication des chaînes de capture) ; le
template l'appliquait aussi au défenseur figé `J32FIXED`, antérieur de 47
commits à ce correctif, donc incapable de le satisfaire par construction. Le
périmètre du témoin est ramené à celui du template éprouvé de `home-0983`.
**Aucun verdict scientifique n'est tiré de cet échec** et ses cellules
primaires ne sont pas réutilisées : `home-0987` refait le readout entier à
entrées, pool et règle de décision inchangés.

`home-0987` termine avec `TURNOVER_L2_SCREEN_DIRECTIONAL_CONFIRMATION_REVIEW`,
douze étapes complètes et tous les garde-fous verts. Cellules primaires contre
le contrôle `L2=3e-5`, 1 000 parties chacune :

| bras | Q00 d9 | natif mt0,1 |
|---|---|---|
| `L2_1E5` | **50,15 %** (490-23-487, +1,0 Elo, IC95 `[47,09 ; 53,21]`) | **51,45 %** (507-15-478, +10,1 Elo, IC95 `[48,38 ; 54,52]`) |
| `L2_1E4` | 47,45 % (469-11-520, −17,7 Elo) | 46,40 % (456-16-528, −25,1 Elo, IC95 `[43,33 ; 49,47]`) |

`L2_1E4` est **rejeté** : sa régression native est établie. `L2_1E5` sort les
deux estimations ponctuelles au-dessus de 50 %, mais **aucune borne basse ne
franchit 50 %** : le résultat est donc directionnel, pas un lead confirmé
(`confirmed_leads=[]`).

Les cellules de garde, ouvertes pour `L2_1E5` seul, ne montrent aucune
régression : `52,60 / 51,60 %` contre F2M et `60,80 / 58,05 %` contre Gen2 en
Q00/natif. La conversion reste saturée et appariée au contrôle : P3 `98,33 %`
contre `98,00 %` (delta `+0,33 pp`, IC `[−1,33 ; +2,00]`) et P4 `98,33 %`
contre `99,00 %` (delta `−0,67 pp`, IC `[−2,67 ; +1,00]`). Les huit garde-fous
`L2_1E5` passent.

Contrôle de reproductibilité utile : la cellule Q00 de `L2_1E5` est identique
au bit près à celle de `home-0986` (490-23-487), la vue Q00 étant à profondeur
fixe ; seule la vue native, pilotée par `movetime`, diffère. Le harnais est
donc déterministe là où il doit l'être.

La seule suite autorisée par la règle de décision est la **confirmation
indépendante de `L2_1E5`** sur un nouveau pool, sans changer le modèle. Tant
qu'elle n'a pas eu lieu, `L2=3e-5` reste le réglage retenu, aucune promotion
n'est autorisée et le croisement replay `0/25 %` reste fermé.

Cette confirmation est préinscrite en deux jobs : le préflight `home-0988`
certifie un pool de 1 000 ouvertures, seed `2718281`, disjoint des treize pools
déjà dépensés dont celui de l'écran ; puis `home-0989` joue quatre cellules de
2 000 parties contre le contrôle et F2M, cumulées à 3 000 avec `home-0987`.
Seuls des moteurs 8cf y participent.

**Sa puissance est annoncée avant le run, et défavorable.** Établir la
supériorité à `n=2000` exige environ **52,2 %** sur la cellule fraîche et
**52,6 %** pour que le cumul Q00 franchisse le seuil, alors que `home-0987`
mesure `L2_1E5` à 50,15 % en Q00. Le résultat attendu si l'écran se reproduit
est donc `L2_1E5_DIRECTION_REPLICATED_REVIEW`, pas une confirmation. L'exercice
est exécuté parce que la règle n'autorise que lui et parce qu'un cumul à 3 000
parties tranche si le `+10 Elo` natif est réel ou s'il relève du bruit de
`movetime`, mesuré à 1,55 pp entre `home-0986` et `home-0987` sur le même
modèle. Détail :
[`experiments/L3_PURE_TURNOVER_L2_SCREEN_PROTOCOL_20260726.md`](experiments/L3_PURE_TURNOVER_L2_SCREEN_PROTOCOL_20260726.md).

`home-0988` certifie le pool `71dc575e…` (1 000 ouvertures, seed `2718281`,
recouvrement nul sur treize pools dont celui de l'écran) et `home-0989` conclut
**`L2_1E5_DIRECTION_NOT_REPLICATED_RETAIN_3E5`**. Le facteur L2 est **clos sur
`L2=3e-5`** ; le croisement replay `0/25 %` s'ouvre à ce réglage.

**Les deux vues se sont inversées entre l'écran et la confirmation**, à modèle
strictement identique et sur des pools disjoints :

| vue, contre le contrôle | `home-0987` n=1000 | `home-0989` frais n=2000 | cumul n=3000 |
|---|---|---|---|
| Q00 | 50,15 % (+1,0 Elo) | **53,02 %** (+21,1 Elo, établie) | 52,07 %, IC95 `[50,30 ; 53,84]`, établie |
| native | 51,45 % (+10,1 Elo) | **49,68 %** (−2,3 Elo) | 50,27 %, IC95 `[48,49 ; 52,04]` |

La règle exigeant les deux vues sur le frais **et** le cumul, la native ferme le
dossier. La vue Q00 étant déterministe à profondeur fixe, l'écart Q00 de 2,87 pp
entre les deux runs mesure la **variance d'échantillonnage entre pools**, pas du
bruit moteur : à `n=1000`, une lecture mono-vue de l'ordre de `±10 Elo` ne porte
pas de décision. C'est le repère méthodologique le plus réutilisable de la
campagne.

Hors question causale, `L2_1E5` établit sa supériorité **contre F2M dans les
deux vues** sur le cumul (52,42 % et 52,63 %, bornes basses 50,64 et 50,86).
Les cellules F2M sont des garde-fous de non-régression, pas un test de
promotion : le candidat et son contrôle se tiennent à égalité tout en dominant
leur parent commun. Exploiter ce constat exigerait une expérience séparée et
préenregistrée ; rien ici ne l'autorise.

### Porte de succession — recommandation acquise, promotion en attente

`home-0996` termine avec **`TURNOVER_SUCCESSION_RECOMMENDED_HUMAN_REVIEW`**,
onze étapes complètes et **cinq garde-fous sur cinq verts**, sur le pool neuf
`eb129db1…` (1500 ouvertures, disjoint de quinze pools).

| cellule | n | score | Elo | IC95 | |
|---|---:|---:|---:|---|---|
| **primaire vs F2M** | 6000 | **51,98 %** | **+13,73** | `[50,72 ; 53,23]` | **établie** |
| garde vs Gen2 | 6000 | 58,83 % | +62,03 | `[57,60 ; 60,07]` | aucune régression |
| conversion P3 | 300 | 98,00 % | — | — | plancher OK |
| conversion P4 | 300 | 99,00 % | — | — | plancher OK |

Deux faits méritent d'être relevés. D'abord **la réplication** : `home-0993`
mesurait `51,98 %` sur `n=5000` et `home-0996` mesure `51,98 %` sur `n=6000`,
sur deux pools disjoints — identiques à la deuxième décimale. Ensuite
**l'accord des vues** : `51,93 %` en Q00 contre `52,02 %` en natif, soit
`0,09 pp` d'écart, ce qui valide sur données fraîches l'étude d'accord des vues.

Consolidation de toutes les mesures du couple, **quatre pools indépendants** :

```text
0978  q00 n=1000 52,10 %   native n=1000 51,15 %
0980  q00 n=2000 50,35 %   native n=2000 50,90 %
0993  q00 n=2500 52,72 %   native n=2500 51,24 %
0996  q00 n=3000 51,93 %   native n=3000 52,02 %
------------------------------------------------------------
CUMUL n=17 000   51,62 %   8642-266-8092   +11,24 Elo
                 IC95 [50,87 ; 52,36]      demi-IC 0,745 pp
```

Huit mesures sur huit sont positives. Le **SPRT accepte H1** à `H1=+5` comme à
`H1=+8` (`LLR = +6,26` et `+8,30`) : le critère séquentiel, plus exigeant que
notre borne basse habituelle, conclut lui aussi.

**Rien n'est promu.** La porte recommande ; la succession est une promotion
délibérée réservée à une revue humaine explicite. Procédure prête et non
exécutée :
[`experiments/L3_TURNOVER_BAKE_PROCEDURE_20260727.md`](experiments/L3_TURNOVER_BAKE_PROCEDURE_20260727.md).

### Outillage et bras préparés — SPRT et TURNOVER G2

Deux chantiers préparés le 27 juillet, non lancés.

**Test séquentiel.** `jobs/tools/l3_sprt.py` + 19 tests, avec les modèles
trinomial et pentanomial. Méthodologie et réglages :
[`experiments/L3_SPRT_METHODOLOGY_20260727.md`](experiments/L3_SPRT_METHODOLOGY_20260727.md).
Mesure honnête : à hypothèses et taux d'erreur identiques, le gain typique est
**×1,8**, pas ×2-3, et il n'explose que si la vérité est loin des deux
hypothèses. Le SPRT peut même être plus lent quand la vérité tombe entre H0 et
H1, ce qui impose un plafond `n_max` obligatoire. Surtout, un SPRT `0 vs +5` est
**plus exigeant** que notre critère actuel de borne basse : l'adopter resserrera
les verdicts autant qu'il réduira les coûts. Il n'est branché sur aucun gate ;
le brancher est une décision de protocole.

**TURNOVER G2.** Le gain de `+13,77 Elo` de TURNOVER vient d'**une seule
génération**. Palier ou pente reste indécidé, et c'est la question ouverte au
meilleur rapport information/coût : la recette et les corpus existent, un seul
run répond. Protocole :
[`experiments/L3_PURE_TURNOVER_G2_PROTOCOL_20260727.md`](experiments/L3_PURE_TURNOVER_G2_PROTOCOL_20260727.md).
G2 rejoue G1 décalé d'un cran — parent TURNOVER, 1 M échantillonné de son propre
corpus plus 1 M généré depuis lui — ce qui rend la recette auto-similaire et
donne un sens à la lecture d'une pente. ETA totale ~2 h 20 à 2 h 50, ancrée sur
les durées mesurées de `home-0966bis` (génération 2 M ≈ 17 min, fit ≈ 33 min).

Rappel de cadrage pour la suite : la profondeur est **close et négative**
(d12 en régression établie), et « plus de volume frais » est exactement ce qui a
plafonné avec `M2`. Le fit tourne à **~4,3 observations par paramètre libre**
(418 070 colonnes ajustées pour 1 801 803 lignes, 208 914 buckets visités sur
2 125 768), ce qui borne mécaniquement les gains et désigne le volume à dose de
mémoire constante, puis la génération dirigée par la couverture, comme les
leviers suivants.

### Axe de dose replay clos, et succession de champion ouverte

La chaîne `home-0990→0993` a prolongé l'axe de dose au-delà de 50 %, seul point
vierge : le croisement `{0 ; 25 %}` du plan était déjà mesuré à `L2=3e-5` par
`M2`, `REPLAY25` et `TURNOVER`. Protocole complet :
[`experiments/L3_PURE_REPLAY_DOSE_AXIS_20260727.md`](experiments/L3_PURE_REPLAY_DOSE_AXIS_20260727.md).

Premier écran dimensionné par une analyse de puissance : vues **additionnées**,
2 500 parties par cellule et par vue, `n=5000` par matchup, seuil **1,386 pp
≈ 9,6 Elo**. Résultats sur le pool `17544078…` :

| matchup | n | score | Elo | IC95 | |
|---|---:|---:|---:|---|---|
| `REPLAY75` vs F2M | 5000 | 50,11 % | +0,8 | `[48,74 ; 51,48]` | non établi |
| `REPLAY75` vs `TURNOVER` | 5000 | 47,77 % | −15,5 | `[46,39 ; 49,15]` | **régression établie** |
| **`TURNOVER` vs F2M** | 5000 | **51,98 %** | **+13,8** | `[50,61 ; 53,35]` | **supériorité établie** |

**L'axe de dose est clos avec un optimum intérieur à 50 %** : la courbe monte de
0 à 50 % puis redescend. Le bras 75 % avait pourtant la meilleure loss holdout
des quatre (`0,443431`) — il ré-apprend simplement les données de son parent,
converge en 6 itérations et n'est pas distinguable de F2M en force. La loss ne
prédit toujours pas la force.

**`TURNOVER` établit sa supériorité sur le champion F2M**, dans une cellule
préenregistrée et dimensionnée pour cela. Les six mesures indépendantes de ce
couple, sur trois pools disjoints, se consolident à `51,42 %`, `+9,89 Elo`,
IC95 `[50,50 ; 52,35]` sur 11 000 parties — diagnostic de soutien, non
préenregistré. `home-0980` n'avait rien conclu parce qu'il mesurait ce même
effet très en deçà de son seuil de détection d'alors : **le signal était là, la
puissance manquait.**

Rien n'est promu. Une succession de champion est une promotion délibérée, sur go
humain explicite, et exigerait les cellules non jouées ici : garde Gen2,
conversion P3/P4 à défenseur figé, couverture par bucket, pool indépendant
supplémentaire.

### Accord des vues et puissance réelle — relecture transversale

L'inversion Q00/native a motivé une analyse rétrospective sur les **65 cellules
de force déjà publiées** (`home-0963` à `home-0989`), sans jouer une seule
partie neuve :
[`experiments/L3_VIEW_AGREEMENT_AND_POWER_20260726.md`](experiments/L3_VIEW_AGREEMENT_AND_POWER_20260726.md).

- Sur 31 matchups mesurés dans les deux vues, `r = +0,885` et
  `chi2/ddl = 0,787` (`p ≈ 0,88`) : **aucun effet de vue n'est détectable**.
  Les deux vues estiment la même force ; leur divergence est du bruit.
- La vue native **ne se reproduit pas** à entrées identiques : `1,55` et
  `1,90 pp` d'écart entre `home-0986` et `home-0987` sur les mêmes modèles et
  le même pool, quand la Q00 est identique au bit près. Son indéterminisme
  `movetime` injecte à lui seul autant de bruit que le tirage des parties.
- Exiger la supériorité **dans chaque vue séparément** double donc le plancher
  de bruit sans ajouter d'information. Additionner les vues resserre
  l'intervalle d'un facteur `√2` à compute identique.
- **Nos écrans à `n=1000` par cellule et par vue n'établissent qu'un effet de
  2,5 à 3 %, soit 17 à 21 Elo.** Les verdicts `M2_PLATEAU`, `D10_PLATEAU`,
  `REPLAY25_DOSE_CLOSED` et `L2_NOT_REPLICATED` signifient donc « aucun lead
  détectable à cette puissance », **pas** « aucun effet ». Un gain de 1 %
  (~7 Elo) exige environ 4 800 parties par cellule, vues additionnées.

Vérification importante : sur les 6 000 parties disponibles, vues additionnées,
`L2_1E5` contre son contrôle reste à 51,17 %, IC95 `[49,91 ; 52,42]`,
**non établie**. L'estimateur le plus puissant confirme la clôture du facteur L2
au lieu de la fragiliser.
