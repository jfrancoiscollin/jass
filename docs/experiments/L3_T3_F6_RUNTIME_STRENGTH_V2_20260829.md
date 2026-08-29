# L3 — T3/F6 Runtime Strength v2 — contrat relatif

Date de préenregistrement : 29 août 2026. Statut : **préenregistré avant toute
génération du corpus R0-v2, avant toute lecture T0/T3 sur ce corpus et avant
toute génération ou partie des nouveaux pools de force**.

## 0. Question nouvelle et séparation d'avec v1

Le runtime v1 est terminal et reste inchangé :

- job `cpx62-1647-l3-t3-f6-runtime-r0-terminal-readout-v1` ;
- attempt `20260829T120556Z-362d1a09` ;
- code `362d1a09bdb0633ef783f4e4048721d8ae6ee980` ;
- verdict `R0_PRODUCTION_LEAF_CONTRACT_NOT_ESTABLISHED` ;
- conclusion
  `FROZEN_CURRICULUM_FAILS_PREREGISTERED_COLOUR_IMAGE_EXACTNESS` ;
- failure gate `rotate180_colour_swap_t0_and_t3_exact` ;
- zéro partie native/Q00, fit, retune, calibration, bake ou promotion.

V1 exigeait `drift(T0)=0` et `drift(T3)=0`. Il a établi que F6 et le résiduel
sont invariants mais que le CURRICULUM de production gelé a un drift couleur
non nul. V2 ne réinterprète, ne corrige et ne remplace pas ce résultat. Elle
pose une question causale différente :

> Le résiduel F6 gelé introduit-il une asymétrie supplémentaire, ou T3-A
> conserve-t-il exactement le drift déjà présent dans CURRICULUM ?

Si le contrat relatif est établi, la question terminale devient :

> T3-A/F6 apporte-t-il réellement de la force de jeu lorsqu'il remplace
> CURRICULUM comme unique évaluation statique de feuille ?

Contraste de force unique :

```text
T3_A_F6 vs CURRICULUM
```

## 1. Upstream et bytes immuables

Terminal deep-fresh :

- job `cpx62-1640-l3-t3-rf1-joint-ab-terminal-readout-v1` ;
- attempt `20260829T090656Z-bbb2bfe4` ;
- verdict `F6_TRANSFER_ESTABLISHED_D1_NOT_ADDITIVE` ;
- T3-A pairwise `0.783169358800913`, top-hit `0.6836764705882353` ;
- T0 pairwise `0.6082147602129492`, top-hit `0.5540686274509804` ;
- A−T0 `+0.17495459858796386`, CI95
  `[0.16940747096694114, 0.18047508706277157]` ;
- A−D1 `+0.04968993301341747`, CI95
  `[0.0442287889012635, 0.05512097787563297]` ;
- B−A `-0.004942934833288572`, CI95
  `[-0.008393666858675503, -0.0014982551019841386]`.

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

T3-A reste exactement :

```text
66 -> 256 -> 128 -> 64 -> 1
residual_F6_parent(p) = MLP(normalize(F6_parent(p)))
T3_child_float(p)     = T0_child_int(p) - residual_F6_parent(p)
T3_child_engine(p)    = clamp_20000(llround(T3_child_float(p)))
```

Les features source restent binary32, puis sont promues en binary64. La
normalisation, les trois ReLU, la sortie et la soustraction sont binary64.
`scale=1.0 cp`, sans intercept ou calibration.

## 2. Interdictions

V2 interdit tout refit, retune, symétrisation, changement de CURRICULUM,
modification/suppression/approximation de F1..F5, retrait de F2, changement de
poids ou normalisation T3-A, D1, troisième bras, calibration, scale tuning,
quantification nouvelle ou tuning search. Aucun résultat consommé ne peut
choisir une feature, une tolérance, une optimisation ou un seuil.

Une optimisation strictement équivalente est admissible uniquement avant R0-v2,
si elle est décrite par le code mergé, conserve toutes les parités et ne change
aucune sémantique. Après le PASS R0-v2, aucun code ni byte ne change jusqu'au
verdict final.

## 3. Cohortes et pools consommés

Seules les identités board+STM servent aux exclusions. Labels, scores,
métriques et sous-groupes sont interdits :

- historiques A/B/C `1570/1578/1587` ;
- confirmations M2/M3/M5 `1593/1599/1609` ;
- Q1 `1617-v7`, T2 fresh `1628c`, RF1 fresh `1633`, T3 fresh `1638` ;
- leurs teachers/readouts, notamment `1634/1635e`, `1639/1640` ;
- R0-v1 `1644/1645/1646/1647` ;
- tous les pools de force historiques certifiés cités dans v1 : context30
  `1360/1361`, champion D `1348/1351`, reverse-seed `1108`, turnover
  `0984bis`, big `1154/1183`, volume8m `1004`, succession `0995`, context2
  `1375/1377`, context3 `1419` et `1428`, replay `1451/1454`, RGSC `1562`,
  TB-policy `1568/1569`, DSSD `1584` ;
- tout autre pool/confirmation authentifiable présent au lancement.

L'ajout d'une identité d'exclusion est conservateur. L'impossibilité
d'authentifier une source produit un abort technique, jamais son retrait.

## 4. R0-v2 target-blind

R0-v2 ne joue aucune partie et ne lit aucun label profond.

### 4.1 Nouveau corpus

Générer exactement `40000` positions candidates par trajectoires légales sans
score : `min_ply=8`, `max_ply=160`, `min_pieces=9`, graine
`2026091701`. Sélectionner exactement `4096` positions non terminales :

- P0 30..40 pièces : `1024` ;
- P1 20..29 pièces : `1024` ;
- P2 12..19 pièces : `1024` ;
- P3 9..11 pièces : `1024`.

Avant toute évaluation, dédupliquer sous board+STM exact puis sous l'involution
valide rotate180+colour-swap `C`, et exclure toute la section 3. R0-v1 est
authentifié depuis le job failed `1644`, attempt
`20260829T112915Z-362d1a09`, fichier `artefacts/r0-corpus.fen`.

Ordre de sélection :
`sha256("2026091702:" + canonical_board_stm)`. Graine contextes/permutations
`2026091703`. Graine d'ordre benchmark `2026091704`. Le FEN et le reçu
d'exclusions sont hashés avant tout read T0/T3/parité/coût. Overlap interdit
exigé : `0`. Compteurs exigés : score/WDL/deep-label reads `0`.

### 4.2 Gate 1 — position, transposition et état de recherche

Sur les `4096` positions, les évaluations répétées sur objets reparsés/copiés,
en ordre direct, inverse et permuté doivent donner F6, résiduel et T3 identiques
bit à bit. Le probe réexécute aussi :

- au moins une transposition explicite issue de deux chemins et deux parents
  légaux distincts, board+STM final exact, F6 et T3 exacts ;
- évaluation directe identique avec TT froide, préremplie et search states
  distincts sur un sous-ensemble target-blind de `64` positions, `16`/phase ;
- mutation des bytes q-score/WDL d'un conteneur sans mutation board+STM ;
- aucune entrée parent, historique, ordre ou TT dans l'API leaf.

Tout mismatch donne `R0_V2_POSITION_TRANSPOSITION_CONTRACT_FAILED` et STOP.

### 4.3 Gate 2 — invariance F6/résiduel

Pour chaque `x` des `4096`, construire `C(x)` par rotation FMJD
`s -> 51-s`, échange des couleurs, flip STM et conservation du halfmove clock.
Exiger :

- égalité bit à bit des `66` binary32 F6 entre `x` et `C(x)` ;
- égalité bit à bit du résiduel binary64 entre `x` et `C(x)`.

Mismatch count exigé `0`. Sinon
`R0_V2_F6_RESIDUAL_INVARIANCE_FAILED` et STOP.

### 4.4 Gate 3 — drift relatif

Tous les scores sont en POV du side-to-move de leur position. Comme `C`
échange couleurs **et** STM, la valeur transformée cohérente doit être
préservée ; il n'y a aucune négation additionnelle dans les définitions :

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

Gate principal runtime, fixé avant score :

- `extra_engine(x) == 0` pour les `4096` positions ;
- exact engine mismatch count `0` ;
- `max(abs(extra_float)) <= 1e-10 cp` ;
- aucune valeur non finie et aucune saturation.

Le seuil float est une tolérance d'arrondi binary64, pas une calibration. Le
drift T0 peut être arbitrairement non nul : **aucun seuil ne porte sur sa
magnitude**.

Publier, séparément pour `abs(d0_engine)` et `abs(d3_engine)`, minimum, moyenne,
p50/p95/p99, maximum et nonzero count ; publier aussi max extra float/engine.
Les percentiles utilisent la convention NumPy Type 7 : index `(n-1)*p` et
interpolation linéaire.

Tout extra drift hors contrat donne `R0_V2_ADDITIONAL_SYMMETRY_DRIFT_DETECTED`
et STOP.

### 4.5 Gate 4 — perspective negamax et priorités terminales

Après le gate relatif :

1. sur une racine quiet depth-1, avec TT fraîche, le score search doit être
   exactement `max_child(-E3(child))` ;
2. la conversion child STM vers parent POV est exactement une négation, sans
   adaptation couleur cachée ;
3. sur témoins terminaux et EGDB, ON et OFF gardent la même classe/résolution,
   et les priorités terminal/TB restent avant l'appel leaf ;
4. coups légaux, résultat root et conventions W/D/L restent ceux du moteur.

Tout mismatch donne `R0_V2_NEGAMAX_OR_TERMINAL_PRECEDENCE_FAILED` et STOP.

### 4.6 Gate 5 — parité Python/native

Références : extracteur RF1 au SHA de la section 1, artefact T3-A brut, et
CURRICULUM brut. Sur les `4096` lignes :

- F6 binary32 : `66` coordonnées, ordre SHA exact, égalité bit à bit ;
- F6 normalisé binary64 : égalité bit à bit Python/native ;
- résiduel MLP :
  `abs(native-python) <= 1e-8 cp + 1e-12*abs(python)` ;
- T0 entier : égalité exacte avec le chemin OFF de référence v1
  `362d1a09bdb0633ef783f4e4048721d8ae6ee980` ;
- T3 float : même tolérance que le résiduel ;
- T3 engine : égalité exacte avec `llround` ties-away-from-zero et clamp ;
- replay natif : égalité bit à bit ;
- non-finite/saturation : `0`.

Une transformation d'unité non déjà figée donne
`T3_F6_RUNTIME_CALIBRATION_REQUIRED` et STOP. Aucun multiplicateur ne peut être
choisi à partir d'Elo.

### 4.7 Gate 6 — contrat dormant OFF/ON

Un même executable sert aux deux bras. Env absent = OFF CURRICULUM exact. Env
`JASS_T3_F6_MODEL=<artifact>` = ON. Env vide, artefact partiel ou SHA/schema/
shape/order/provenance incorrect est refusé, sans fallback.

OFF doit être identique au code v1 `362d1a09...` sur les `4096` evals et sur
`64` racines (`16`/phase) Q00 depth 9 pour bestmove, score, depth et nodes. ON
remplace uniquement la static leaf eval. Il ne change jamais ordering, TT,
pruning, alpha/beta, aspiration, extensions/réductions, coups légaux, EGDB,
livre ou adjudication.

Tout mismatch donne `R0_V2_DORMANT_OR_OFF_REGRESSION_FAILED` et STOP.

### 4.8 Gate 7 — coût diagnostic

Après exactitude : deux warmups puis `32` passages complets dans l'ordre
`2026091704`, plus un passage instrumenté. Publier :

- µs/eval T0 et T3, ratio ;
- coût normalisation+MLP/résiduel ;
- F1/F2/F3/F4/F5 µs/eval ;
- movegen calls et response enumerations F2 ;
- coûts par phase et bins branching `1`, `2..4`, `5..8`, `9+` ;
- sur `128` racines, `32`/phase, native `0.1 s/move`, TT fraîche : eval calls,
  nodes, depth et NPS par bras.

Ce profil ne déclenche aucune suppression, approximation ou optimisation
post-hoc. Un rapport incomplet donne `R0_V2_RUNTIME_PROFILE_INCOMPLETE`.

### 4.9 Verdict R0-v2

Tous les gates 1..7, l'authentification des bytes et les exclusions doivent
PASS pour publier :

```text
R0_RELATIVE_PRODUCTION_LEAF_CONTRACT_ESTABLISHED
```

Ce verdict autorise uniquement Pool1 avec les exacts bytes executable/T3/T0
publiés par R0-v2. Tout autre verdict est terminal R0-v2 et interdit la force.

## 5. Force causale

Le PRIMARY tourne sur CPX62 uniquement, native `0.1 s/move`. Même executable,
CURRICULUM, T3, search Q00 63 paramètres, TT `16 MiB`, EGDB, book OFF, un
thread et `maxplies=160`. Seule différence : env T3 présent côté candidat et
absent côté contrôle. Une paire de couleurs inversées par ouverture.

Une erreur loader/search, timeout, coup illégal ou résultat synthétique rend la
cellule technique et exclut toute interprétation. Il faut exactement
`6000/6000` parties réelles, zéro erreur candidat/contrôle. Une partie en erreur
n'est jamais transformée en draw.

Q00 depth 9 est un diagnostic non bloquant sur les mêmes pools. Il peut tourner
sur HOME seulement si cela ne perturbe pas le benchmark Scan Home indépendant.
Son absence ou son retard ne bloque pas la décision CPX. HOME ne sauve jamais
un résultat CPX négatif.

### 5.1 Pool1

- `30000` candidats légaux quiet : `min_ply=8`, `max_ply=32`,
  `min_pieces=20` ;
- génération seed `2026091801` ;
- sélection canonique seed `2026091802` ;
- exactement `3000` ouvertures / `6000` parties native ;
- bootstrap cluster ouverture `200000`, seed native `2026091803` ;
- seed Q00 diagnostic `2026091804`.

Pool1 exclut section 3 et le corpus R0-v2. Décision utilisant uniquement le
point native exact :

- `score_rate <= 0.5` :
  `T3_F6_RUNTIME_STRENGTH_NOT_SUPPORTED`, STOP ;
- `score_rate > 0.5` : exactement Pool2 autorisé.

### 5.2 Pool2 conditionnel

Les seeds sont réservées ici avant Pool1 :

- mêmes paramètres et `30000` candidats ;
- génération seed `2026091901` ;
- sélection canonique seed `2026091902` ;
- exactement `3000` ouvertures / `6000` parties native ;
- bootstrap native `2026091903` ;
- seed Q00 diagnostic `2026091904` ;
- chained native `200000`, seed `2026092001` ;
- chained Q00 diagnostic seed `2026092002`.

Pool2 exclut aussi Pool1. Aucun changement de code, artefact, search ou
optimisation n'est autorisé entre les pools. Le chained bootstrap rééchantillonne
séparément `3000` clusters avec remise dans chaque pool, pondère chaque moyenne
de pool par `1/2`, et répète `200000` fois.

## 6. Readout obligatoire

Pour chaque vue exécutée : W/D/L T3, score rate, Elo
`400*log10(p/(1-p))`, CI95 score empirique et Elo transformé, CI95 percentile
paired-opening bootstrap, `P(score>0.5)`, score par couleur, erreurs par arm et
side, depth/nodes/NPS/eval calls. Authentifier les SHA T3, T0, executable,
pool, résultats, code, search/TT/EGDB/book/maxplies, overlaps et le profil R0-v2.

Après Pool2, publier le chained native et le Q00 disponible.

## 7. Verdict terminal

```text
T3_F6_RUNTIME_STRENGTH_SUPPORTED
```

si et seulement si Pool1 native `>0.5`, Pool2 native `>0.5`, borne basse CI95
du chained native `>0.5`, zéro asymétrie technique et mêmes bytes/sémantiques.

Si Pool2 native `<=0.5` :
`T3_F6_RUNTIME_STRENGTH_NOT_SUPPORTED`.

Si les deux pools sont positifs mais chained CI95 low `<=0.5` :
`T3_F6_RUNTIME_STRENGTH_INCONCLUSIVE`.

Il n'existe ni Pool3 ni tuning. Q00 ne sauve jamais le PRIMARY.

## 8. Interprétation et arrêt

- Q00 positif mais native non supporté : signal F6 conservé, coût wall-clock
  incompatible ; seule une future optimisation/compression sémantiquement
  exacte ou distillation runtime preregistrée est recevable.
- Q00 et native non supportés : diagnostiquer ranking sibling vers
  value/alpha-beta avant tout training.
- force robuste : STOP au verdict, sans bake ni promotion.

Les pannes techniques seules peuvent être corrigées par patch minimal, test,
PR/CI/merge et nouvel ID versionné. Dès qu'un corpus/pool est créé, un retry
technique réutilise ses bytes. La science, les tolérances et les seeds ne
changent jamais après résultat.
