# L3 — T3-A/F6 Runtime Strength v3 — contrat leaf/search corrigé

Date de préenregistrement : 29 août 2026. Statut : **préenregistré avant toute
génération du corpus R0-v3, avant toute lecture T0/T3 sur ce corpus et avant
toute génération ou partie des pools de force v3**.

## 0. Nouvelle question et chaîne terminale immuable

V3 ne modifie ni ne réinterprète rétroactivement les campagnes antérieures.

### Runtime v1

- job `cpx62-1647-l3-t3-f6-runtime-r0-terminal-readout-v1` ;
- attempt `20260829T120556Z-362d1a09` ;
- code `362d1a09bdb0633ef783f4e4048721d8ae6ee980` ;
- verdict `R0_PRODUCTION_LEAF_CONTRACT_NOT_ESTABLISHED` ;
- cause
  `FROZEN_CURRICULUM_FAILS_PREREGISTERED_COLOUR_IMAGE_EXACTNESS` ;
- zéro partie native/Q00.

V1 a correctement rejeté son contrat absolu : CURRICULUM a un drift couleur
non nul. Ce résultat reste terminal.

### Runtime v2

- job source `cpx62-1648-l3-t3-f6-runtime-r0-v2`, attempt
  `20260829T132226Z-f559baed` ;
- readout terminal `cpx62-1649-l3-t3-f6-runtime-r0-v2-terminal-readout`,
  attempt `20260829T133232Z-f559baed` ;
- code `f559baede4047f47abe13724b16d1ad669c5f36f` ;
- verdict `R0_V2_NEGAMAX_OR_TERMINAL_PRECEDENCE_FAILED` ;
- zéro partie native/Q00.

V2 a établi position/transposition, invariance F6/résiduel, drift relatif,
priorité terminale et priorité tablebase. En particulier : mismatch extra
drift engine `0`, maximum extra drift engine `0 cp`, maximum extra drift float
`1.1368683772161603e-13 cp`. Son unique FAIL était le témoin
`search(root,depth=1) == max(-eval(child))`.

### Autopsie negamax

- job `cpx62-1650-l3-t3-f6-negamax-autopsy-v1`, attempt
  `20260829T141312Z-2a4d1519` ;
- readout authentifié `cpx62-1651-l3-t3-f6-negamax-autopsy-readout-v1`,
  attempt `20260829T142315Z-2a4d1519` ;
- code `2a4d151956eab0c74674b812ca75bb2d6386d875` ;
- verdict exact `QUIESCENCE_OR_DEPTH_SEMANTICS_EXPLAINS_MISMATCH` ;
- artefact `negamax-autopsy.json` sous le résultat 1650 ;
- `strength_games=0`, `force_authorized=false`, `v3_executed=false`.

L'autopsie prouve que T0 et T3 échouent tous deux au témoin direct sur la
racine v2. Le premier écart se situe dans la quiescence, précisément
`qsearch_selective_sac`. Sur des positions mécaniques réellement isolées, le
contrat direct passe pour T0 **et** T3. Aucun défaut POV/signe spécifique T3
n'est observé.

Le vrai chemin est :

```text
search(root, depth=1)
  -> root move
  -> negamax(child, depth=0, ply=1)
  -> draw / TB / TT / terminal
  -> quiescence
  -> capture forcée, menace, forcing/promotion, sacrifice sélectif ou stand-pat
  -> retour réel child STM
  -> exactement une négation au root
```

V3 pose donc une nouvelle question :

> T3-A respecte-t-il exactement le contrat leaf/POV lorsque la leaf est
> réellement isolée, et son activation conserve-t-elle toutes les sémantiques
> de search/quiescence/terminal/TB sauf la source de l'évaluation statique ?

Si oui, le contraste causal unique est :

```text
T3_A_F6 vs CURRICULUM
```

## 1. Upstream et bytes immuables

Terminal deep-fresh : job
`cpx62-1640-l3-t3-rf1-joint-ab-terminal-readout-v1`, attempt
`20260829T090656Z-bbb2bfe4`, verdict
`F6_TRANSFER_ESTABLISHED_D1_NOT_ADDITIVE`.

- T3-A q200 pairwise `0.783169358800913` ;
- T0 q200 pairwise `0.6082147602129492` ;
- T3-A−T0 `+0.17495459858796386`, CI95
  `[0.16940747096694114, 0.18047508706277157]`.

Identités gelées :

- T3-A JSON SHA256
  `16e5db8fd78849bba12b158eee5c1da4ab170129d8aeac1b91ab7a40ad9d0bb2` ;
- CURRICULUM `.pjtw` SHA256
  `319d174f4b548b1655aad4bb30d4c6dc86c08dd715c9c23f8b19ba1937dc0be1` ;
- RF1 SHA256
  `0d26ba50b668160b3da3e247cd4e1bd709c2cb7989b3b5877b9ea7deb34db58b` ;
- ordre F6 SHA256
  `cc4837e6829d937f7330f7bc71280f3ec0bed3f431e57b2664c651e1d763db4e` ;
- extracteur RF1 de référence
  `e5c4a0d6e88e99c06819100c4b5dbc697bbe3a53`.

Contrat exact :

```text
66 -> 256 -> 128 -> 64 -> 1
residual_F6_parent(p) = MLP(normalize(F6_parent(p)))
T3_child_float(p)     = T0_child_int(p) - residual_F6_parent(p)
T3_child_engine(p)    = clamp_20000(llround(T3_child_float(p)))
```

F6 source est binary32 puis promu en binary64. Normalisation, MLP, ReLU,
sortie et soustraction sont binary64. `scale=1.0 cp`, sans intercept ni
calibration. L'artefact reste strictement byte-identique.

## 2. Interdictions et corrections techniques

Sont interdits : fit/refit, retune, calibration, nouveau model search,
symétrisation, modification T3-A/CURRICULUM/F6, retrait ou approximation F2,
suppression de feature, D1, troisième bras, quantification nouvelle, changement
de search ou de ses paramètres, seuil choisi sur résultat, bake et promotion.

Une correction de build, runner, path, parsing, sérialisation ou instrumentation
est autorisée si elle est minimale, testée, mergée et relancée sous un nouvel ID.
Elle ne peut changer aucune science préenregistrée. Une fois R0-v3 PASS, les
bytes executable/T3/T0 et les sémantiques restent identiques jusqu'au verdict
final. Aucune optimisation n'est autorisée entre Pool1 et Pool2.

## 3. Exclusions et canonicalisation

Seules les identités board+STM sont lues dans les sources consommées ; labels,
scores, WDL, métriques et sous-groupes sont interdits.

Exclusions obligatoires :

- historiques A/B/C `1570/1578/1587` ;
- confirmations M2/M3/M5 `1593/1599/1609` ;
- Q1 `1617-v7`, T2 fresh `1628c`, RF1 fresh `1633`, T3 fresh `1638` ;
- leurs teachers/readouts, notamment `1634/1635e`, `1639/1640` ;
- R0-v1 `1644/1645/1646/1647` ;
- R0-v2 `1648/1649` ;
- toutes les racines, children et positions synthétiques sérialisées dans
  `negamax-autopsy.json` 1650, conservativement, même si elles ne constituent
  pas une cohorte scientifique ;
- tous les pools de force historiques certifiés : context30 `1360/1361`,
  champion D `1348/1351`, reverse-seed `1108`, turnover `0984bis`, big
  `1154/1183`, volume8m `1004`, succession `0995`, context2 `1375/1377`,
  context3 `1419/1428`, replay `1451/1454`, RGSC `1562`, TB-policy
  `1568/1569`, DSSD `1584` ;
- tout autre pool ou confirmation authentifiable présent au lancement.

L'ajout conservateur d'une identité connue est permis. L'impossibilité
d'authentifier une source provoque un abort technique, jamais son retrait.

L'identité exacte est `(white_men, white_kings, black_men, black_kings, STM)`.
La clé canonique est le minimum lexical entre cette identité et son image
rotate180+colour-swap `C` (`square s -> 51-s`, couleurs et STM échangés).
Halfmove, q-score/WDL et historique ne servent pas à l'identité ; les positions
générées ont un historique vide et un halfmove compatible avec les gates. Les
sorties publient les SHA256 du corpus/pool et un overlap interdit exact `0`.

## 4. R0-v3 target-blind

R0-v3 ne joue aucune partie et ne lit aucun label profond.

### 4.1 Génération et sélection gelées

Générer exactement `120000` positions candidates par trajectoires légales,
sans score, avec `min_ply=8`, `max_ply=160`, `min_pieces=9`, seed
`2026092101`. Deux générations indépendantes avec les mêmes paramètres doivent
être byte-identiques.

Après exclusions et déduplication canonique, sélectionner exactement `4096`
positions :

- P0 30..40 pièces : `1024` ;
- P1 20..29 pièces : `1024` ;
- P2 12..19 pièces : `1024` ;
- P3 9..11 pièces : `1024`.

La sélection intervient avant toute lecture T0, T3, parité ou runtime. Clé
générale : `sha256("2026092102:" + canonical_board_stm)`. Seed de permutation
des contextes/corpus : `2026092103`. Seed d'ordre benchmark : `2026092104`.

Pour garantir que le sous-gate 4A est réellement testé sans sélectionner sur
un score, chaque phase réserve ses `32` premiers témoins satisfaisant le
prédicat mécanique isolé de 4A, ordonnés par
`sha256("2026092105:" + canonical_board_stm)`. Les `992` autres positions de
la phase sont les premières clés générales hors témoins déjà réservés. Si une
phase contient moins de `32` témoins isolés parmi les candidates admissibles,
la sélection s'arrête avec
`R0_V3_RUNTIME_SUPPORT_INCONCLUSIVE`; aucun critère, quota ou seed ne change.

Le sous-ensemble 4B contient exactement `256` racines, `64`/phase : les
`32` témoins isolés de la phase et les `32` premières positions non isolées par
`sha256("2026092106:" + canonical_board_stm)`. Un support non isolé insuffisant
donne le même verdict inconclusif, sans substitution post-hoc.

Le reçu publie : cardinalités candidates/uniques/exclues, quotas, seeds,
canonicalisation, SHA FEN/JNNW, identités des 128/256 témoins, overlaps, et
`score_reads=wdl_reads=deep_label_reads=runtime_metric_reads=0`.

### 4.2 Gate 1 — position et transposition

Sur les `4096` positions, les objets reparsés/copiés, les ordres direct,
inverse et seed `2026092103` doivent donner F6, résiduel et T3 bit-identiques.
Le probe exige aussi :

- indépendance à l'identité du parent, au chemin et à l'ordre des siblings ;
- une transposition explicite atteinte par deux parents et chemins légaux
  distincts, board+STM, F6 et T3 exacts ;
- indépendance à TT froide/préremplie et à deux search states sur `64`
  positions (`16`/phase) fixées par la seed de contexte ;
- indépendance aux bytes q-score/WDL du conteneur ;
- aucune entrée parent, historique, sibling, TT ou q-score dans l'API leaf.

Tout mismatch donne `R0_V3_POSITION_CONTRACT_FAILED` et STOP.

### 4.3 Gate 2 — invariance F6/résiduel

Pour chaque `x`, construire `C(x)` selon la section 3. Exiger égalité bit à bit
des `66` F6 binary32 et du résiduel binary64. Tous les mismatch counts valent
exactement `0`. Sinon `R0_V3_F6_RESIDUAL_INVARIANCE_FAILED` et STOP.

### 4.4 Gate 3 — drift relatif

Tous les scores sont POV STM. Comme `C` échange couleurs et STM, il n'y a pas
de négation supplémentaire :

```text
E0(x) = T0_child_int(x)
R(x)  = residual_F6_parent(x)
F3(x) = double(E0(x)) - R(x)
E3(x) = clamp_20000(llround(F3(x)))

d0_engine(x)    = E0(x) - E0(C(x))
d3_engine(x)    = E3(x) - E3(C(x))
extra_engine(x) = d3_engine(x) - d0_engine(x)

d0_float(x)     = double(E0(x)) - double(E0(C(x)))
d3_float(x)     = F3(x) - F3(C(x))
extra_float(x)  = d3_float(x) - d0_float(x)
```

Gate gelé identique à v2 :

- `extra_engine(x) == 0` partout ;
- mismatch count engine `0` ;
- max extra drift engine `0 cp` ;
- `max(abs(extra_float)) <= 1e-10 cp` ;
- aucune valeur non finie ni saturation.

Le drift absolu T0/T3 est publié (min, moyenne, p50/p95/p99, max, nonzero),
mais n'a aucun seuil. Percentiles NumPy Type 7. Tout écart supplémentaire donne
`R0_V3_RELATIVE_DRIFT_FAILED` et STOP.

### 4.5 Gate 4A — contrat static leaf réellement isolé

Le prédicat isolé est calculé sans T0/T3, avec exactement le code de movegen,
TB et les paramètres search de la section 5. Pour une racine, **tous** ses
children doivent satisfaire simultanément :

- root et child non terminaux, liste légale non vide ;
- `probe_endgame(child) == Unknown`, EGDB disponible ;
- `halfmove_clock < 50`, historique vide et aucun hash child dans le chemin ;
- `any(reply.is_capture()) == false` sur la liste complète ;
- `has_any_capture(child, opposite(STM)) == false` ;
- `scan_add_sacs(child)` vide ;
- aucun reply ne satisfait les prédicats forcing-capture ou promotion de la
  qsearch ;
- budgets `qs_forcing_depth=0`, `qs_promo_depth=0`, `qs_threat_ext=0`,
  `scan_threat_reentry=0` et `qs_sacs=0`, exactement comme le search force ;
- TT fraîche sans hit/cutoff, un thread, aucun node/time/stop limit ;
- aucun terminal, TB, draw/path, extension, sacrifice ou saturation dans la
  trace effective.

La vérification porte sur exactement `128` racines, `32`/phase. Pour chaque
racine et chaque bras, avec une TT fraîche de `16 MiB`, profondeur exacte 1 et
paramètres force :

```text
search_depth1(root,T0) == max_child(-T0_engine(child))
search_depth1(root,T3) == max_child(-T3_engine(child))
```

Pour chaque root move, la trace exige : `child_return == evaluator(child)` et
`root_negated_return == -child_return`. Le child est STM POV, il existe
exactement une négation vers le parent, la formule native T3 et le rounding/
clamp sont exacts. Tous les `128/128` témoins et tous leurs moves doivent passer
pour les deux bras. Sinon `R0_V3_ISOLATED_NEGAMAX_CONTRACT_FAILED` et STOP.

### 4.6 Gate 4B — sémantiques réelles et trace passive

Sur les `256` racines preregistrées, chaque bras est exécuté deux fois avec
des TT fraîches identiques : trace absente puis trace passive présente. Les
deux exécutions doivent être exactement identiques pour : score, best move,
depth/effective/completed depth, stop/abort, nodes, eval calls, PV et compteurs
de search exposés. Le code sans trace garde un pointeur nul. Tout mismatch
d'instrumentation est un FAIL.

La trace sérialise pour chaque root move et chaque appel leaf effectivement
atteint : position board+STM, étage (negamax/qsearch), profondeur/ply,
alpha/beta, score STM, source T0 ou T3, retours child/root, terminal/TB/TT/draw,
captures, menace, sacrifices et nombre de branches qsearch. Elle vérifie :

- chaque leaf score égale un appel direct du même evaluator sur la même
  position STM ;
- chaque retour root est exactement l'unique négation du retour réel child ;
- terminal, TB, draw puis TT précèdent l'évaluation conformément au code ;
- les mêmes paramètres et le même code qsearch/order/pruning/extension sont
  utilisés OFF et ON ;
- aucune branche spécifique T3 ne contourne le search normal.

Il n'est **pas** exigé que `child_return == static_eval(child)` lorsque la
qsearch continue. Il n'est pas non plus exigé que T0 et T3 visitent exactement
les mêmes branches : leurs valeurs différentes peuvent légitimement modifier
fenêtres, cutoffs et PV. L'invariance causale exigée porte sur le code, les
paramètres, les règles d'éligibilité et la source unique de l'eval ; au sein de
chaque bras, trace OFF/ON est strictement neutre.

Tout défaut donne `R0_V3_REAL_SEARCH_SEMANTICS_FAILED` et STOP.

### 4.7 Gate 5 — terminal et tablebase

Réutiliser les témoins mécaniques fixés avant résultat : terminal
`W:W:B1` (blanc au trait sans coup) et TB `W:WK12,K28:BK7`. À profondeur 2,
TT fraîche, paramètres force :

- ON/OFF ont même classe et même score ;
- terminal : `eval_calls=0` dans les deux bras ;
- EGDB disponible, classe TB non Unknown, ON/OFF même résultat et
  `eval_calls=0` ;
- la trace confirme la priorité terminal/TB avant leaf.

Sinon `R0_V3_TERMINAL_OR_TABLEBASE_PRECEDENCE_FAILED` et STOP.

### 4.8 Gate 6 — parité Python/native complète

Sur les `4096` lignes, références RF1/T3/CURRICULUM brutes :

- F6 binary32 : `4096*66` coordonnées, ordre SHA exact, égalité bit à bit ;
- F6 normalisé binary64 : égalité bit à bit Python/native ;
- résiduel MLP :
  `abs(native-python) <= 1e-8 cp + 1e-12*abs(python)` ;
- T0 entier : égalité exacte avec le chemin OFF v1 `362d1a09...` ;
- T3 float : même tolérance que le résiduel ;
- T3 engine : égalité exacte avec `llround` ties-away-from-zero et clamp 20000 ;
- replay natif bit-identique ; non-finite/saturation `0` ;
- `scale_cp == 1.0`.

Une transformation d'unité non déjà figée produit
`T3_F6_RUNTIME_CALIBRATION_REQUIRED` et STOP. Tout autre mismatch produit
`R0_V3_PYTHON_NATIVE_PARITY_FAILED` et STOP. Aucune calibration n'est ouverte
par v3.

### 4.9 Gate 7 — dormant OFF/ON

Un même executable sert aux deux bras :

- env absente : CURRICULUM OFF exact ;
- `JASS_T3_F6_MODEL=<artefact frozen>` : T3 ON ;
- env vide, fichier partiel ou SHA/schema/shape/order/provenance incorrect :
  refus fail-closed, aucun fallback.

OFF est comparé au binaire de référence v1 sur `4096` static evals et `64`
racines Q00 depth 9 (`16`/phase) pour bestmove, score, depth et nodes. ON ne
remplace que `eval_leaf`. Les hashes/configurations confirment l'identité de
movegen, ordering, TT, pruning, alpha/beta, aspiration, extensions/réductions,
EGDB, livre et limites. Des cutoffs indirectement différents après changement
de valeur sont l'effet causal recherché, pas une violation.

Tout mismatch donne `R0_V3_DORMANT_OR_OFF_REGRESSION_FAILED` et STOP.

### 4.10 Gate 8 — profil runtime diagnostique

Après exactitude : deux warmups puis `32` passages des `4096` positions dans
l'ordre seed `2026092104`, plus un passage instrumenté. Publier :

- µs/eval T0/T3 et ratio ;
- F1/F2/F3/F4/F5 µs/eval ;
- normalisation+MLP/résiduel µs/eval ;
- movegen calls et response enumerations F2 ;
- phase et bins branching `1`, `2..4`, `5..8`, `9+` ;
- sur `128` racines (`32`/phase), native `0.1 s/move`, TT fraîche : eval calls,
  nodes, depth et NPS par bras.

Le profil est diagnostique : aucune feature, approximation ou optimisation ne
peut être choisie après lecture. Un rapport incomplet donne
`R0_V3_RUNTIME_SUPPORT_INCONCLUSIVE` et STOP.

### 4.11 Verdict R0-v3

Tous les gates 1..8, bytes, exclusions, cardinalités et traces doivent passer
pour publier :

```text
R0_V3_PRODUCTION_LEAF_CONTRACT_ESTABLISHED
```

Ce verdict autorise uniquement Pool1 avec l'executable gzip exact de R0-v3.
Tout autre verdict est terminal R0-v3 et interdit toute partie de force/Q00.

## 5. Contrat search/force commun

PRIMARY sur CPX62 uniquement : native `0.1 s/move`, même executable,
CURRICULUM, T3, search Q00 de `63` paramètres déjà standardisé, TT `16 MiB`,
EGDB et cache `128 MiB`, livre OFF, un thread, `maxplies=160`.

Le vecteur Q00 exact de `63` paramètres est gelé byte pour byte :

```text
rfp_max_depth=5,rfp_margin=100,nmp_min_depth=4,nmp_min_pieces=6,nmp_r_base=2,nmp_r_div=4,singular_min_depth=8,singular_margin=2,lmr_min_depth=3,lmr_first_full_moves=4,lmr_first_full_pv=4,lmr_first_full_nonpv=2,lmr_base=0,lmr_depth_div=6,lmr_idx_div=8,lmr_hist_div=0,lmr_formula=0,lmr_log_base=0,lmr_log_mul=40,lmr_bc_ld=100,lmr_bc_lidx=100,lmp_d1=4,lmp_d2=8,lmp_d3=14,lmp_max_depth=3,history_max=16384,hist_malus=0,hist_mode=1,prob_shift=5,hist_pure=1,hist_order_captures=0,aspiration_initial=50,use_pvs=1,razor_max_depth=4,razor_margin=200,probcut_min_depth=5,probcut_margin=150,probcut_reduction=4,ext_promotion=0,ext_forcing=0,forcing_ext_cap=0,ext_single_reply=0,use_improving=1,use_conthist=1,iid_min_depth=0,iid_reduction=2,no_reduce_forcing=0,qs_forcing_depth=0,qs_promo_depth=0,qs_threat_ext=0,qs_sacs=0,qs_sacs_depth0_only=1,multicut_min_depth=4,multicut_reduction=4,multicut_moves=8,multicut_cuts=2,tm_next_iter_pct=200,tm_min_depth=5,drawish_scaling=0,eg_pieces=40,eg_no_nmp=0,eg_no_lmp=0,eg_no_lmr=0
```

Les autres champs de `SearchParams`, dont `scan_threat_reentry`, restent à
leur valeur de production par défaut ; la sérialisation du contrat publie aussi
leur valeur effective. Aucun paramètre implicite ne peut varier entre R0-v3,
Pool1 et Pool2.

Une paire inverse les couleurs sur chaque ouverture. Il faut exactement
`6000/6000` parties réelles par pool. Loader/search timeout, coup illégal,
résultat synthétique, résultat manquant ou erreur d'un bras rend le job
technique : aucune partie en erreur n'est convertie en draw, et aucun résultat
partiel n'est interprété. Adjudication autre que terminal/TB/règle FMJD et
`maxplies=160` : interdite. Book : OFF. Retry technique : mêmes bytes de pool.

## 6. Pool1

Générer `30000` candidates légales quiet, `min_ply=8`, `max_ply=32`,
`min_pieces=20`, seed `2026092201`. Dédupliquer/exclure selon section 3 et le
corpus R0-v3. Sélection canonique seed `2026092202`, exactement `3000`
ouvertures/`6000` parties.

Bootstrap paired opening-cluster : `200000`, seed `2026092203`. Chaque
ouverture est un cluster de ses deux couleurs. Q00 diagnostic HOME depth 9 sur
les mêmes bytes, seed d'ordre `2026092204`, uniquement si cela ne perturbe pas
le benchmark Scan Home indépendant. Son absence/retard ne bloque pas CPX.

Décision preregistrée utilisant uniquement le point native exact :

- `score_rate <= 0.5` :
  `T3_F6_RUNTIME_STRENGTH_NOT_SUPPORTED`, STOP ;
- `score_rate > 0.5` : exactement Pool2 autorisé.

Q00 ne sauve jamais un PRIMARY négatif.

## 7. Pool2 conditionnel

Seeds réservées avant tout résultat Pool1 :

- mêmes `30000` candidates et paramètres ; génération `2026092301` ;
- sélection `2026092302` ;
- exactement `3000` ouvertures / `6000` native ;
- bootstrap native `200000`, seed `2026092303` ;
- Q00 HOME depth 9, seed `2026092304` ;
- chained native `200000`, seed `2026092401` ;
- chained Q00 diagnostic seed `2026092402`.

Pool2 exclut aussi Pool1. Code, executable, artefacts, search, TT, EGDB,
runtime et paramètres restent byte/sémantiquement identiques. Le chained
bootstrap rééchantillonne séparément avec remise les `3000` clusters de chaque
pool, pondère leurs moyennes par `1/2`, et répète `200000` fois. Aucun Pool3.

## 8. Readout et verdict final

Publier par pool : W/D/L T3, score rate, Elo
`400*log10(p/(1-p))`, CI95 score empirique et Elo transformé, CI95 percentile
paired bootstrap, `P(score>0.5)`, score par couleur, erreurs par bras/side,
depth, nodes, NPS, eval calls et coût T3/F6. Authentifier SHA T3, T0,
executable, code, pool, résultats, paramètres, TT/EGDB/book/maxplies, provenance
et overlaps.

Verdict :

```text
T3_F6_RUNTIME_STRENGTH_SUPPORTED
```

si et seulement si Pool1 native `>0.5`, Pool2 native `>0.5`, borne basse CI95
du chained native `>0.5`, zéro asymétrie technique, mêmes bytes et mêmes
sémantiques.

- Pool2 native `<=0.5` : `T3_F6_RUNTIME_STRENGTH_NOT_SUPPORTED` ;
- deux points positifs mais chained CI95 low `<=0.5` :
  `T3_F6_RUNTIME_STRENGTH_INCONCLUSIVE`.

Q00 ne peut jamais sauver CPX. Q00 clairement positif mais PRIMARY non supporté
autorise seulement l'interprétation
`STATIC_SIGNAL_TRANSFERS_BUT_RUNTIME_COST_DOMINATES` et une future branche
d'optimisation exacte/cache/reuse ou distillation runtime séparément
préenregistrée. Q00 et PRIMARY négatifs motivent une analyse ranking-versus-
search/value avant tout training.

## 9. Arrêt et documentation

Après un terminal R0-v3 ou force, mettre à jour `docs/L3_CURRENT.md`,
`docs/L3_TEACHER_DISTILLATION_ROADMAP.md`,
`docs/L3_SCIENTIFIC_SYNTHESIS_20260829.md` et un memo résultats v3 dédié. La
chaîne v1 → v2 → autopsie → v3 doit rester explicite. Aucun ancien verdict
n'est effacé. Aucun bake ni promotion n'est autorisé.
