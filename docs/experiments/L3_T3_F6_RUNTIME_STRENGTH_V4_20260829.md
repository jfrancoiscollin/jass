# L3 — T3-A/F6 Runtime Strength v4 — transparence du wrapper à résidu nul

Date de préenregistrement : 29 août 2026. Statut : **préenregistré avant la
construction du corpus R0-v4, avant toute lecture T0/ZERO/T3 sur ce corpus et
avant toute génération ou partie des pools de force v4**.

## 0. Nouvelle question et chaîne terminale immuable

V4 ne modifie, ne répare et ne réinterprète aucun terminal antérieur.

- V1, job `cpx62-1647-l3-t3-f6-runtime-r0-terminal-readout-v1`, verdict
  `R0_PRODUCTION_LEAF_CONTRACT_NOT_ESTABLISHED` : CURRICULUM lui-même ne
  satisfait pas le contrat absolu rotate180+colour-swap. F6 et le résiduel
  étaient invariants. Zéro partie.
- V2, job terminal `cpx62-1649-l3-t3-f6-runtime-r0-v2-terminal-readout`,
  attempt `20260829T133232Z-f559baed`, code
  `f559baede4047f47abe13724b16d1ad669c5f36f`, verdict
  `R0_V2_NEGAMAX_OR_TERMINAL_PRECEDENCE_FAILED` : position/transposition,
  F6/résiduel, drift relatif, terminal et tablebase passent ; extra drift
  engine mismatch `0`, maximum engine `0 cp`, maximum float
  `1.1368683772161603e-13 cp`. Le témoin direct depth 1 échoue. Zéro partie.
- Autopsie, jobs `cpx62-1650-l3-t3-f6-negamax-autopsy-v1` et readout
  authentifié `cpx62-1651-l3-t3-f6-negamax-autopsy-readout-v1`, attempt
  `20260829T142315Z-2a4d1519`, code
  `2a4d151956eab0c74674b812ca75bb2d6386d875`, verdict exact
  `QUIESCENCE_OR_DEPTH_SEMANTICS_EXPLAINS_MISMATCH` : le premier écart est
  `qsearch_selective_sac`. Le témoin `search(depth=1)==max(-eval(child))`
  n'est pas la sémantique générique du moteur. Des contrôles synthétiques
  réellement isolés passent pour T0 et T3 ; aucun défaut POV T3 n'est établi.
- V3, job `cpx62-1652-l3-t3-f6-runtime-r0-v3`, attempt
  `20260829T152726Z-880fccbe`, code
  `880fccbec5929588e4e4120a2cf81ce5067bcd71`, et readout
  `cpx62-1653-l3-t3-f6-runtime-r0-v3-readout-v1`, verdict
  `R0_V3_RUNTIME_SUPPORT_INCONCLUSIVE` : parmi `120000` candidates et
  `119699` identités admissibles uniques, P0 ne fournit que `5` racines
  naturelles `ISOLATED_STATIC_LEAF` contre `32` requises. Les gates suivants
  ne sont pas exécutés, Pool1/Pool2 ne sont pas autorisés et aucune partie
  n'est jouée. Aucun défaut T3 n'est démontré.

V3 testait la disponibilité statistique d'une géométrie naturelle extrêmement
restrictive. V4 pose une question différente et plus directe :

> Le plumbing runtime T3 est-il exactement transparent dans le vrai search
> lorsque son résiduel vaut identiquement zéro ? Le T3-A frozen utilise-t-il
> ensuite ce même plumbing, la seule intervention spécifique étant la valeur
> statique de leaf voulue ?

Si oui, le contraste causal unique est `T3_A_F6 vs CURRICULUM`.

## 1. Upstream et bytes scientifiques immuables

Le terminal deep-fresh reste `cpx62-1640-l3-t3-rf1-joint-ab-terminal-readout-v1`,
attempt `20260829T090656Z-bbb2bfe4`, verdict
`F6_TRANSFER_ESTABLISHED_D1_NOT_ADDITIVE`.

- T0/CURRICULUM q200 pairwise : `0.6082147602129492` ;
- T3-A q200 pairwise : `0.783169358800913` ;
- T3-A−T0 : `+0.17495459858796386`, CI95
  `[0.16940747096694114, 0.18047508706277157]` ;
- T3-A−D1 : `+0.04968993301341747` ;
- T3-B−T3-A : `-0.004942934833288572`.

Identités gelées :

- T3-A JSON SHA256
  `16e5db8fd78849bba12b158eee5c1da4ab170129d8aeac1b91ab7a40ad9d0bb2` ;
- CURRICULUM `.pjtw` SHA256
  `319d174f4b548b1655aad4bb30d4c6dc86c08dd715c9c23f8b19ba1937dc0be1` ;
- RF1 SHA256
  `0d26ba50b668160b3da3e247cd4e1bd709c2cb7989b3b5877b9ea7deb34db58b` ;
- ordre F6 SHA256
  `cc4837e6829d937f7330f7bc71280f3ec0bed3f431e57b2664c651e1d763db4e`.

Contrat scientifique exact, inchangé :

```text
66 -> 256 -> 128 -> 64 -> 1
R3(p) = residual_F6_parent(p)
F3(p) = double(T0_child_int(p)) - R3(p)
E3(p) = clamp_20000(llround(F3(p)))
```

F6 est binary32, les opérations du MLP et la soustraction sont binary64 ;
`scale=1 cp`, sans intercept, calibration, symétrisation ni quantification.

## 2. Interdictions et corrections techniques

Sont interdits : model search, fit/refit, retune, calibration, nouveau training,
D1, troisième bras scientifique, suppression/modification/approximation F1..F6
ou F2, modification T3-A/CURRICULUM, changement/tuning des paramètres search,
seuil post-hoc, bake et promotion.

Le modèle ZERO défini ci-dessous est un **probe mécanique** sans données, sans
training et sans statut scientifique. Il ne peut participer à aucune partie de
force ni à un bake. Une correction de build, loader, runner, R2, path, parsing,
sérialisation, compteurs ou instrumentation est autorisée si minimale, testée,
mergée et relancée sous un nouvel ID, sans changer le protocole.

## 3. T3_ZERO : étalon mécanique gelé avant R0

T3_ZERO emprunte la même classe `t3_f6::Network`, la même API `INetwork`, le
même extracteur F6, la même architecture `66->256->128->64->1`, le même calcul
binary64, le même `evaluate_from_base`, le même rounding/clamp et la même
intégration search que T3-A. Sa construction déterministe est :

- `mean[66]=0`, `std[66]=1` ;
- `W0[66,256]=0`, `b0[256]=0` ;
- `W1[256,128]=0`, `b1[128]=0` ;
- `W2[128,64]=0`, `b2[64]=0` ;
- `W3[64,1]=0`, `b3[1]=0` ;
- tous les nombres JSON sont le littéral ASCII `0` ou `1` ; aucun NaN/Inf ;
- ordre des clés, séparateurs et newline final sont produits par un générateur
  canonique versionné, sans entrée de données.

Ainsi `RZ(p)` est mathématiquement et bitwise `+0.0` et
`EZ(p)=clamp_20000(llround(double(E0(p))-0.0))=E0(p)` pour tout score moteur
valide. L'artefact canonique, son SHA256 et le SHA du générateur sont publiés
dans le manifest d'implémentation mergé **avant toute génération R0-v4**.
Le job refuse de démarrer si le SHA ne correspond pas au constant compilé.

L'activation ZERO exige le target diagnostique v4 et son flag explicite :

```text
t3_f6_runtime_contract_v4 --zero-probe <zero-artifact>
```

`JASS_T3_F6_MODEL` conserve sans exception la politique frozen-only T3-A
existante. Le flag ZERO absent, vide ou associé à un artifact non-ZERO échoue
fermé. Le mode ZERO n'est accepté que par l'executable diagnostique v4 ; il
n'est exposé ni par le binaire production `jass`, ni comme candidat de force.

## 4. Exclusions, cutoff et identité

Seules les identités board+STM sont lues ; scores, labels, WDL, métriques,
sous-groupes et résultats profonds sont interdits pendant la sélection.

Le cutoff est le commit de merge de cette prereg. Sont exclus : historiques
A/B/C `1570/1578/1587`, M2/M3/M5 `1593/1599/1609`, Q1 `1617-v7`, T2 fresh
`1628c`, RF1 fresh `1633/1634/1635e`, T3 fresh `1638/1639/1640`, runtime v1
`1644..1647`, v2 `1648/1649`, autopsie `1650/1651`, toutes les candidates,
tous les témoins et le corpus v3 `1652/1653`, le cohort benchmark-only Scan
Home sélectionné par `home-1651-l3-scan-ceiling-selection-v1` et consommé
jusqu'au readout `home-1660-l3-scan-ceiling-readout-v1`, tous les pools de
force historiques certifiés, et toute autre cohorte scientifique
authentifiable publiée avant le cutoff. L'ajout conservateur d'une source
d'identités oubliée est permis ; l'impossibilité de l'authentifier est un abort
technique, jamais une suppression.

L'identité exacte est `(white_men,white_kings,black_men,black_kings,STM)`. La
clé canonique est le minimum lexical de cette identité et de son image
rotate180+colour-swap `C` (`s -> 51-s`, couleurs et STM échangés). Déduplication
exacte board+STM puis canonique. Tous les overlaps interdits publiés valent `0`.

## 5. R0-v4 target-blind : génération et sélection

Générer exactement `40000` positions par trajectoires légales sans score, avec
`min_ply=8`, `max_ply=160`, `min_pieces=9`, seed génération `2026092501`.
Deux replays doivent être byte-identiques. Après exclusions/déduplication,
sélectionner exactement `4096`, seed `2026092502`, par clé
`sha256("2026092502:"+canonical_identity)` :

- P0, 30..40 pièces : `1024` ;
- P1, 20..29 pièces : `1024` ;
- P2, 12..19 pièces : `1024` ;
- P3, 9..11 pièces : `1024`.

Seed de permutation/contextes `2026092503`. Le sous-ensemble search contient
exactement `512` positions, `128`/phase, premiers hash
`sha256("2026092504:"+canonical_identity)`. Ordre benchmark seed `2026092505`.
Sélection et subsets sont figés avant toute lecture E0/EZ/E3, parité ou runtime.
Le reçu publie cardinalités, quotas, seeds, SHA FEN/JNNW, exclusions, overlap
`0` et `score_reads=wdl_reads=deep_label_reads=runtime_metric_reads=0`.

Un support de phase insuffisant produit `R0_V4_RUNTIME_SUPPORT_INCONCLUSIVE`
et STOP sans relaxation. Le corpus v3 n'est jamais recyclé.

## 6. Gates R0-v4

### Gate 1 — leaf API exactness

Sur `4096/4096` positions :

```text
E0 = CURRICULUM.evaluate(p)
EZ = T3_ZERO.evaluate(p)
E3 = T3_A.evaluate(p)
```

ZERO exige `EZ==E0` entier exact, mismatch `0`, max abs diff `0`, aucune valeur
non finie et aucune saturation introduite. T3-A exige exact
`E3==clamp_20000(llround(double(E0)-R3))`, mismatch `0`. Publier comptes finis,
clamps/saturations et distributions de différences sans gate sur E3−E0.

### Gate 2 — Python/native parity complète

Sur `4096/4096`, comparer : raw F6 binary32 et ordre (exacts), normalisation
binary64 (max abs `<=1e-12`, max rel `<=1e-12`), résiduel MLP
(max abs `<=1e-8 cp`, max rel `<=1e-10`), T0 entier exact, T3
float (mêmes tolérances résiduel), puis T3 rounded/clamped entier exact. ZERO
exige `residual_zero==+0.0` bitwise et engine exact. Aucune calibration/scale.

### Gate 3 — équivalence full-search OFF/ZERO (gate technique principal)

Sur les `512` racines, exécuter le vrai search production, un thread, book OFF,
EGDB ON cache `128 MiB`, TT fraîche `16 MiB`, search state/historique frais,
même root et mêmes paramètres. Trois budgets gelés, sans sweep :

1. profondeur exacte `1`, aucune limite temps/nodes ;
2. limite exacte `1000` nodes ;
3. limite exacte `10000` nodes.

Pour chaque root/budget : A=`OFF/CURRICULUM direct`, B=`ON_ZERO/wrapper`. Exiger
exactement égaux : score, best move, completed/effective depth, PV déterministe,
nodes, eval calls, qnodes, terminal hits, TB probes/hits, TT probes/hits,
cutoffs, reductions, extensions, qsearch calls et stop reason. Aucun mismatch
est admis. L'ordre d'exécution est équilibré par seed `2026092503`, TT et state
sont recréés pour chaque bras. Le temps mural, NPS et microsecondes ne font pas
partie de l'égalité car le wrapper ZERO exécute volontairement du calcul.

Les compteurs ajoutés sont passifs. Sur `64` racines (`16`/phase, premières
clés de seed `2026092505`) chaque recherche est répétée trace OFF puis trace ON
et doit conserver exactement tous les champs ci-dessus, PV incluse. Si un
compteur s'avère non déterministe avant exécution scientifique, l'implémentation
doit le rendre déterministe ou STOP ; il n'est pas retiré post-hoc.

Tout écart donne `R0_V4_ZERO_WRAPPER_SEARCH_EQUIVALENCE_FAILED` et STOP.

### Gate 4 — negamax synthétique mécanique

Réutiliser comme unit tests les positions synthétiques déterministes de
l'autopsie : au moins une racine multicoûts, une racine à un coup et une racine
non terminale/non-TB sans prolongement qsearch. Elles ne sont pas une cohorte.
Pour T0, ZERO et T3-A, exiger sur chaque témoin applicable :

```text
search_depth1(root,arm) == max_child(-arm.evaluate(child))
```

Le score, best move, STM child, unique négation child→parent, formule native et
absence effective de prolongement doivent tous passer. Aucun quota naturel.

### Gate 5 — vraies sémantiques search T3-A

Sur les mêmes `512` racines et les mêmes trois budgets, comparer configuration,
code et traces OFF puis T3-A. Score, arbre, nodes, PV et cutoffs **peuvent et
doivent pouvoir différer**. Exiger seulement : mêmes options/budgets, même code
movegen/order/qsearch/pruning/reductions/extensions/TT/terminal/TB, et seul
branchement T3 spécifique à l'endroit de l'évaluation statique. La trace de
`64` roots prouve `leaf E0 -> residual -> E3 -> conséquences alpha-beta`
normales, jamais une branche search T3. Toute différence directe de règle donne
`R0_V4_REAL_SEARCH_SEMANTICS_FAILED`.

### Gate 6 — position/transposition

Rejouer sur le corpus : identité parent/path/sibling-order, transposition légale
explicite par deux parents/chemins, TT/search-state et conteneur q/WDL. F6,
résiduel et E3 doivent ne dépendre que de board+STM. Tout mismatch donne
`R0_V4_POSITION_CONTRACT_FAILED`.

### Gate 7 — invariance F6/résiduel

Pour chaque `p` et `C(p)`, les 66 F6 binary32 et le résiduel T3-A binary64 sont
bit-identiques. Mismatch `0`, sinon
`R0_V4_F6_RESIDUAL_INVARIANCE_FAILED`.

### Gate 8 — drift relatif

Tous les scores sont POV STM et C échange couleur et STM, sans négation
additionnelle :

```text
d0 = E0(p) - E0(C(p))
d3 = E3(p) - E3(C(p))
extra_engine = d3 - d0
extra_float = [(E0(p)-R3(p))-(E0(C(p))-R3(C(p)))] - d0
```

Exiger mismatch engine `0`, maximum absolu engine `0 cp`, maximum absolu float
`<=1e-10 cp`, aucune non-finite/saturation. Publier p50/p95/p99/max des drifts
T0/T3 (percentiles NumPy Type 7), sans seuil sur le drift absolu T0.

### Gate 9 — terminal/tablebase

Témoins déterministes : terminal puis TB avec EGDB disponible. OFF=ZERO=T3-A en
classe/score/priorité et `eval_calls=0` lorsque terminal/TB résout. Tout écart
donne `R0_V4_TERMINAL_OR_TABLEBASE_PRECEDENCE_FAILED`.

### Gate 10 — dormant contract

Le binaire production `jass` commun aux bras de force garde : OFF, absence de
`JASS_T3_F6_MODEL`, exactement CURRICULUM ; ON T3-A exige le SHA frozen. ZERO
est inaccessible dans ce binaire et n'est accepté que par le target v4 avec
`--zero-probe` et le SHA ZERO compilé. Mauvais/empty path, mauvais SHA,
base non-CURRICULUM ou flag incohérent échoue fermé. Le seul changement
fonctionnel ON est la valeur static leaf ; aucune règle search n'est modifiée.

### Gate 11 — profil runtime diagnostique

Avant force, ordre seed `2026092505`, publier par phase et si pratique par
branching : microsecondes/eval p50/p95/p99 pour T0/T3-A, ratio, coûts F1/F2/F3/
F4/F5 et MLP, movegen calls, F2 reply enumerations, NPS, nodes, effective depth
et eval calls. Profil non sélectif et sans labels profonds. Aucun retrait,
approximation ou optimisation dirigée après lecture.

## 7. Paramètres search/force gelés

Le vecteur Q00 exact de 63 paramètres, commun R0/Pool1/Pool2, est :

```text
rfp_max_depth=5,rfp_margin=100,nmp_min_depth=4,nmp_min_pieces=6,nmp_r_base=2,nmp_r_div=4,singular_min_depth=8,singular_margin=2,lmr_min_depth=3,lmr_first_full_moves=4,lmr_first_full_pv=4,lmr_first_full_nonpv=2,lmr_base=0,lmr_depth_div=6,lmr_idx_div=8,lmr_hist_div=0,lmr_formula=0,lmr_log_base=0,lmr_log_mul=40,lmr_bc_ld=100,lmr_bc_lidx=100,lmp_d1=4,lmp_d2=8,lmp_d3=14,lmp_max_depth=3,history_max=16384,hist_malus=0,hist_mode=1,prob_shift=5,hist_pure=1,hist_order_captures=0,aspiration_initial=50,use_pvs=1,razor_max_depth=4,razor_margin=200,probcut_min_depth=5,probcut_margin=150,probcut_reduction=4,ext_promotion=0,ext_forcing=0,forcing_ext_cap=0,ext_single_reply=0,use_improving=1,use_conthist=1,iid_min_depth=0,iid_reduction=2,no_reduce_forcing=0,qs_forcing_depth=0,qs_promo_depth=0,qs_threat_ext=0,qs_sacs=0,qs_sacs_depth0_only=1,multicut_min_depth=4,multicut_reduction=4,multicut_moves=8,multicut_cuts=2,tm_next_iter_pct=200,tm_min_depth=5,drawish_scaling=0,eg_pieces=40,eg_no_nmp=0,eg_no_lmp=0,eg_no_lmr=0
```

Les autres champs restent aux defaults compilés ; `scan_threat_reentry=false`.
Un thread, TT `16 MiB`, EGDB/cache `128 MiB`, book OFF, `maxplies=160`.
PRIMARY force : native `0.1 s/move`, couleurs inversées/appairées, aucune
adjudication avant `maxplies`; une game error/non-finite/timeout/protocol error
invalide le run entier. Retry technique seulement avec mêmes bytes/seed.

## 8. Décision R0-v4

`R0_V4_PRODUCTION_LEAF_CONTRACT_ESTABLISHED` est permis uniquement si les 11
gates passent, ZERO leaf/full-search est exact, T3-A emprunte le même wrapper,
parité/invariance/terminal/TB/dormance passent et le runtime est exécutable.

Sinon verdict précis et STOP, notamment :

- `R0_V4_RUNTIME_SUPPORT_INCONCLUSIVE` ;
- `R0_V4_ZERO_LEAF_EXACTNESS_FAILED` ;
- `R0_V4_PYTHON_NATIVE_PARITY_FAILED` ;
- `R0_V4_ZERO_WRAPPER_SEARCH_EQUIVALENCE_FAILED` ;
- `R0_V4_SYNTHETIC_NEGAMAX_FAILED` ;
- `R0_V4_REAL_SEARCH_SEMANTICS_FAILED` ;
- `R0_V4_POSITION_CONTRACT_FAILED` ;
- `R0_V4_F6_RESIDUAL_INVARIANCE_FAILED` ;
- `R0_V4_RELATIVE_DRIFT_FAILED` ;
- `R0_V4_TERMINAL_OR_TABLEBASE_PRECEDENCE_FAILED` ;
- `R0_V4_DORMANT_CONTRACT_FAILED` ;
- `R0_V4_RUNTIME_TECHNICAL_FAILED`.

Aucune force sans le verdict PASS exact.

## 9. Pool1 — contraste causal PRIMARY

Après PASS seulement, générer `30000` candidates légales, `min_ply=8`,
`max_ply=32`, `min_pieces=20`, seed `2026092601`. Exclure toutes les sources de
la section 4 et R0-v4, dédupliquer/canonicaliser puis sélectionner exactement
`3000` openings par seed `2026092602`. Replays byte-identiques, overlap `0`.

Jouer sur CPX62 exactement `6000` games, deux couleurs par opening, même
executable/search/TT/EGDB/paramètres/book. Seule différence : OFF CURRICULUM vs
ON frozen T3-A. Bootstrap paired opening-cluster `200000`, seed `2026092603` ;
ordre/Q00 diagnostic optionnel seed `2026092604`. Publier W/D/L, score, Elo et
CI95, paired CI95, `P(score>0.5)`, côtés, erreurs, nodes/depth/NPS/eval calls,
ratio runtime et SHAs artifact/executable/code/pool.

Si point estimate native `<=0.5` :
`T3_F6_RUNTIME_STRENGTH_NOT_SUPPORTED`, STOP. Si `>0.5`, autoriser exactement
Pool2. Un Q00 Home éventuel est diagnostic et ne change jamais cette règle.

## 10. Pool2 et verdict final

Seeds réservées avant Pool1 : génération `2026092701`, sélection `2026092702`,
bootstrap `2026092703`, ordre/Q00 `2026092704`. Nouveau pool frais/disjoint de
`3000` openings et `6000` games, mêmes bytes et sémantiques ; aucune optimisation
entre pools. Bootstrap chaîné Pool1+Pool2 `200000`, seed `2026092801` ; Q00
chaîné diagnostic seed `2026092802`.

Verdict :

- `T3_F6_RUNTIME_STRENGTH_SUPPORTED` si Pool1 `>0.5`, Pool2 `>0.5`, borne
  basse CI95 chaînée `>0.5`, aucune asymétrie/erreur et mêmes bytes/sémantiques ;
- `T3_F6_RUNTIME_STRENGTH_INCONCLUSIVE` si les deux points sont positifs mais
  la borne basse chaînée est `<=0.5` ;
- `T3_F6_RUNTIME_STRENGTH_NOT_SUPPORTED` si Pool2 `<=0.5`.

Aucun Pool3. Aucun bake. Aucune promotion automatique.

Si Q00 est positif mais PRIMARY native non positif, l'interprétation est
`STATIC_SIGNAL_VALID_RUNTIME_COST_DOMINATES`; la suite devra être une
optimisation exactement équivalente ou une compression/distillation séparément
préenregistrée. Si Q00 et native échouent, étudier ranking versus
alpha-beta/value/search sans retune post-hoc.

## 11. Traçabilité terminale

Chaque terminal publie jobs, attempts, code/artifact/executable/pool SHAs,
gates, compteurs, coûts, scores et décision. Mettre à jour
`docs/L3_CURRENT.md`, `docs/L3_TEACHER_DISTILLATION_ROADMAP.md`,
`docs/L3_SCIENTIFIC_SYNTHESIS_20260829.md` et créer
`docs/experiments/L3_T3_F6_RUNTIME_STRENGTH_V4_RESULTS_20260829.md`.

La chaîne V1 → V2 → autopsie → V3 → V4 reste explicite ; aucun terminal
historique n'est effacé. Le benchmark Scan Home reste benchmark-only et ne
participe à aucune décision runtime/force.
