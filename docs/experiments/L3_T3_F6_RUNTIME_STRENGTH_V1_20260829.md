# L3 — T3/F6 Runtime Strength v1

Date de préenregistrement : 29 août 2026. Statut : **préenregistré avant toute
partie de force T3-A, avant toute génération des pools de force et avant toute
lecture d'un résultat runtime T3-A**.

## 0. Question et frontière scientifique

Question terminale :

> Le gain massif de T3-A/F6 sur q200 devient-il réellement de l'Elo lorsque
> T3-A remplace CURRICULUM comme unique évaluation statique de feuille dans la
> recherche de production ?

Contraste causal unique :

```text
T3_A_F6 vs CURRICULUM
```

Il n'y a aucun nouveau model search, aucun refit ou retuning de T3-A, aucun
D1, aucun retrait de F2 ou d'une autre composante F6, aucune approximation et
aucune promotion automatique. Une optimisation n'est admissible que si elle
reproduit exactement le contrat numérique gelé.

La campagne comporte deux portes séquentielles :

1. `R0_PRODUCTION_LEAF_CONTRACT`, sans partie de force ;
2. `R1_CAUSAL_STRENGTH_GATE`, autorisé seulement si R0 passe.

R1 comporte Pool1 puis, conditionnellement, exactement une réplication Pool2.
Pool2 n'est ni généré ni joué si le point natif de Pool1 est inférieur ou égal
à `0.5`.

## 1. Upstream immuable et artefacts

Verdict terminal T3 :

- job `cpx62-1640-l3-t3-rf1-joint-ab-terminal-readout-v1` ;
- attempt `20260829T090656Z-bbb2bfe4` ;
- code scientifique `bbb2bfe460ece89bef0ec30e2d52ed4b0ff847ea` ;
- verdict `F6_TRANSFER_ESTABLISHED_D1_NOT_ADDITIVE` ;
- support PASS : `8000` sélectionnés, `6800` acceptés,
  P0/P1/P2/P3 `1783/1860/1877/1280`, black/white `3490/3310`, zéro
  overlap interdit, replay déterministe, zéro fit post-freeze.

Identités binaires gelées :

- T3-A JSON brut SHA256
  `16e5db8fd78849bba12b158eee5c1da4ab170129d8aeac1b91ab7a40ad9d0bb2` ;
- CURRICULUM `.pjtw` brut SHA256
  `319d174f4b548b1655aad4bb30d4c6dc86c08dd715c9c23f8b19ba1937dc0be1` ;
- RF1/F6 SHA256
  `0d26ba50b668160b3da3e247cd4e1bd709c2cb7989b3b5877b9ea7deb34db58b` ;
- ordre des 66 coordonnées F6 SHA256
  `cc4837e6829d937f7330f7bc71280f3ec0bed3f431e57b2664c651e1d763db4e` ;
- commit du contrat extracteur RF1
  `e5c4a0d6e88e99c06819100c4b5dbc697bbe3a53`.

L'artefact est exactement le réseau float64 sérialisé :

```text
66 -> 256 -> 128 -> 64 -> 1
ReLU après les trois couches cachées, sortie linéaire
```

Pour toute position enfant `p`, le parent scientifique est déduit sans entrée
externe comme `opposite(p.side_to_move())`. Le contrat est :

```text
residual_F6_parent(p) = MLP(normalize(F6_parent(p)))
T3_child_float(p)     = T0_child_int(p) - residual_F6_parent(p)
```

Aucun paramètre, moyenne, écart-type ou poids n'est recalculé.

## 2. Cohortes consommées et rôle autorisé

Les données suivantes sont consommées. Seules leurs identités canoniques
board+STM peuvent être lues pour exclusion ; aucun label, score, métrique,
résultat ou sous-groupe ne peut intervenir dans R0/R1 :

- TRAIN historiques A/B/C : sélections `1570`, `1578`, `1587` ;
- micro-search confirmations M2/M3/M5 : sélections `1593`, `1599`, `1609` ;
- Q1 : `cpx62-1617-l3-joint-td-q1-select-v7`, attempt
  `20260828T114236Z-2034c5c9` ;
- T2 fresh : `cpx62-1628c-l3-t2-phase-specialist-fresh-select-v3`, attempt
  `20260828T182726Z-a3ba045f` ;
- RF1 fresh : `cpx62-1633-l3-residual-feature-fresh-select-v1`, attempt
  `20260829T032756Z-e5c4a0d6` ;
- T3 fresh : `cpx62-1638-l3-t3-rf1-joint-ab-fresh-select-v1`, attempt
  `20260829T084038Z-bbb2bfe4` ;
- leurs teachers/readouts associés, notamment RF1 `1634/1635e` et T3
  `1639/1640`.

Les métriques terminales déjà observées, y compris les résultats q200 et
q1000, sont uniquement la motivation de cette campagne. Elles sont interdites
pour une calibration de score, un choix de scale, une sélection de feature,
un seuil, une optimisation dirigée par résultat ou un choix de sous-ensemble
F6.

## 3. Phase R0 — contrat de leaf evaluator de production

R0 ne lit aucun label profond et ne joue aucune partie de force.

### 3.1 Corpus target-blind R0

Le corpus R0 contient exactement `4096` positions légales et non terminales,
`1024` par phase :

- P0 : 30..40 pièces ;
- P1 : 20..29 pièces ;
- P2 : 12..19 pièces ;
- P3 : 9..11 pièces.

Source : `40000` positions candidates issues de trajectoires légales aléatoires
sans score, `min_ply=8`, `max_ply=160`, `min_pieces=9`, graine de génération
`2026090901`. La sélection se fait uniquement par
`sha256("2026090902:" + canonical_board_stm)` après déduplication exacte et
rotate180+colour-swap, et après les exclusions de la section 6. Aucun score
T0/T3, q-score, WDL, résultat de partie ou label n'est lu pour sélectionner le
corpus. Le corpus et son reçu d'overlap sont hashés avant toute mesure R0.

Graine de permutation des répétitions/contextes R0 : `2026090903`.
Graine d'ordre des microbenchmarks : `2026090904`.

### 3.2 Invariance positionnelle, perspective et sûreté TT

Le chemin production doit prouver que F6, le résiduel et le score final ne
dépendent que du board+STM pertinent. Les tests obligatoires sont :

1. même `Position` évaluée avant/après des positions sans rapport et dans des
   ordres de siblings différents : 66 floats, résiduel float64 et score T3
   identiques bit à bit entre répétitions ;
2. au moins une transposition explicite obtenue par deux séquences légales
   distinctes : board+STM final identique, F6 et score identiques ;
3. même child construit depuis deux objets parent distincts : résultat exact
   identique ;
4. TT froid, TT prérempli et search state distincts : l'évaluation directe de
   la même position reste identique ;
5. mutation des bytes score/WDL/q-score d'un conteneur de test sans modifier le
   board+STM : F6 et T3 restent identiques ;
6. image rotate180+colour-swap avec STM/couleurs transformés : les 66 features
   parent-POV, le résiduel, `T0_child` et `T3_child` sont identiques ;
7. contrat negamax : le score transmis au parent pour un child est exactement
   `-T3_child`, sans seconde inversion ni dépendance à l'identité du parent.

Toute dépendance au parent, au chemin, à l'ordre, au TT, au search state ou à
un q-score produit `T3_F6_NOT_TRANSPOSITION_SAFE`. La campagne s'arrête avant
la force ; aucune feature n'est modifiée et aucun réentraînement n'est permis.

### 3.3 Implémentation native dormante et fail-closed

Le même executable est utilisé pour les deux bras. Par défaut, en l'absence de
`JASS_T3_F6_MODEL`, le chemin OFF conserve exactement CURRICULUM. Le chemin ON
n'existe que si le processus candidat reçoit explicitement :

```text
JASS_T3_F6_MODEL=<t3-a-f6-only.json>
```

Le loader ON doit refuser de démarrer si le fichier, son SHA256, son schéma,
son arm, sa largeur, son ordre d'inputs, son architecture, sa provenance, sa
normalisation ou une shape de paramètre dérive. Un env vide ou un artefact
partiel est une erreur, jamais un fallback silencieux.

ON remplace uniquement `INetwork::evaluate(Position)` par :

```text
round_cp(T0_child - residual_F6_parent)
```

Le fast path/accumulateur exact de CURRICULUM doit être conservé sous le
wrapper : le coût causal ne doit pas inclure une recomputation accidentelle de
T0. T3-A n'intervient jamais dans le move ordering, la TT, le pruning, les
paramètres alpha/beta, les coups légaux, l'EGDB, le livre ou l'adjudication.
Les priorités terminales et tablebase existantes restent avant l'évaluation de
feuille.

L'OFF fonctionnel est comparé au code de ce préenregistrement : sur les `4096`
positions, eval CURRICULUM entière identique ; sur `64` racines R0 (`16` par
phase) à Q00 profondeur 9 avec TT frais, bestmove, score, profondeur et nodes
identiques. Le champ diagnostic `eval_calls` peut être ajouté mais ne doit pas
modifier la recherche.

### 3.4 Conversion numérique figée avant résultats

Le résiduel est appris dans la même coordonnée centipawn que
`T0_parent=-T0_child`, avec coefficient T0 exactement `1`. Il n'existe donc ni
multiplicateur, ni intercept, ni calibration runtime. La représentation moteur
figée est :

- calcul de normalisation, couches et résiduel en IEEE-754 binary64 ;
- features source conservées en IEEE-754 binary32 puis promues en binary64,
  comme dans le pipeline Python/RFFD gelé ;
- `scale = 1.0 cp` exactement ;
- arrondi symétrique au centipawn le plus proche, demi-entiers à l'extérieur de
  zéro (`std::llround`) ;
- clamp de sûreté moteur `[-20000, 20000]`, avec **zéro saturation exigée sur
  le corpus R0**.

Ce choix est une conversion de type, pas une calibration. Il est fixé ici
avant tout score runtime. Si la parité montre que les unités ne permettent pas
ce mapping direct ou qu'une autre échelle serait nécessaire, verdict
`T3_F6_RUNTIME_CALIBRATION_REQUIRED` et STOP avant force. Aucun multiplicateur
ne peut être choisi à partir de résultats Elo.

### 3.5 Parité Python/native préenregistrée

Référence feature : l'extracteur au commit
`e5c4a0d6e88e99c06819100c4b5dbc697bbe3a53`, compilé séparément. Référence
score : le JSON T3-A gelé chargé par le code Python
`jobs/tools/t3_rf1_joint_ab.py`, sans refit.

Sur les `4096` positions, les tolérances fixées avant lecture sont :

- F6 : largeur `66`, ordre SHA exact et égalité bit à bit des 66 binary32 ;
- résiduel : `abs(native-python) <= 1e-8 cp + 1e-12*abs(python)` pour chaque
  ligne ;
- T3 float avant arrondi : même tolérance ;
- score moteur entier : égalité exacte sur 100 % des lignes avec la règle
  d'arrondi ci-dessus ;
- replay natif : égalité bit à bit ;
- valeurs non finies et saturations : zéro.

Un dépassement est une panne de parité. Les poids et la normalisation ne sont
jamais modifiés pour la réparer.

### 3.6 Profil de coût R0

Après les checks d'exactitude, sans labels et sans seuil de sélection :

- deux warmups puis `32` passages complets des `4096` positions, dans l'ordre
  fixé par `2026090904` ;
- mesure de `µs/eval` CURRICULUM, `µs/eval` T3-A et ratio ;
- un passage instrumenté séparé donnant F1/F2/F3/F4/F5 en nanosecondes,
  nombre de movegens, réponses F2 énumérées et statistiques par phase et bins
  de branching `1`, `2..4`, `5..8`, `9+` ;
- `128` racines (`32` par phase) sous native `0.1 s/move`, un thread, TT frais,
  pour nodes, profondeur complétée/effective, NPS et eval calls par bras.

L'instrumentation fine n'est pas active dans le binaire de force. Le simple
compteur `eval_calls` est permis dans les deux bras. Le profil est diagnostic :
aucune feature ne peut être supprimée ou approximée après sa lecture et aucun
seuil de coût ne bloque à lui seul R1.

### 3.7 Gate R0

`R0_PRODUCTION_LEAF_CONTRACT_PASS` exige tous les contrôles 3.2 à 3.6,
l'authentification exacte des artefacts, OFF inchangé, zéro intervention hors
leaf eval, profil complet et absence de panne. Sinon :

- invariance/TT : `T3_F6_NOT_TRANSPOSITION_SAFE` ;
- unités : `T3_F6_RUNTIME_CALIBRATION_REQUIRED` ;
- autre échec exact/native : `T3_F6_RUNTIME_R0_TECHNICAL_FAILURE`.

Aucun de ces verdicts n'autorise une partie de force.

## 4. Phase R1 — contraste causal de force

R1 réutilise exactement les bytes R0. Aucun changement de code, artefact,
normalisation, scale, feature ou optimisation n'est permis entre R0, Pool1 et
Pool2. Le binaire force est publié par Pool1 et réutilisé byte-identique par
Pool2.

Contrat commun :

- un seul executable et son SHA256 pour les deux bras ;
- le même fichier CURRICULUM brut des deux côtés ;
- candidat A : env `JASS_T3_F6_MODEL` explicitement défini ;
- contrôle B : env absent ;
- même Q00 complet de 63 paramètres, mêmes TT, EGDB, livre OFF, un thread,
  mêmes règles et même `maxplies=160` ;
- couleurs inversées/appairées, une paire par ouverture ;
- native `0.1 s/move` primaire ; Q00 profondeur `9` diagnostic sur le même
  pool ;
- `3000` ouvertures et `6000` parties par vue ;
- bootstrap par cluster ouverture appariée, `200000` tirages.

Toute erreur moteur, timeout de recherche, coup illégal, erreur de chargement ou
partie synthétiquement transformée en nulle produit un échec technique de la
cellule ; elle n'entre pas dans W/D/L. Une cellule de force interprétable exige
`6000/6000` résultats réels, zéro erreur candidate et zéro erreur contrôle.

## 5. Graines et décisions figées

### Pool1

- candidats : `30000` ; génération légale quiet conventionnelle
  `min_ply=8`, `max_ply=32`, `min_pieces=20` ;
- graine génération `2026091001` ;
- sélection canonique SHA : `2026091002` ;
- bootstrap native `2026091003` ;
- bootstrap Q00 `2026091004`.

Après publication complète des deux vues, la décision utilise exclusivement le
point natif exact :

- si `native score_rate <= 0.5` : STOP,
  `T3_F6_RUNTIME_STRENGTH_NOT_SUPPORTED` ;
- si `native score_rate > 0.5` : exactement une réplication Pool2 est
  autorisée.

Q00 ne peut pas modifier cette décision.

### Pool2 conditionnel

Pool2 n'est généré qu'après un Pool1 natif strictement positif et exclut aussi
Pool1.

- candidats : `30000`, mêmes bornes et même sélection ;
- graine génération `2026091101` ;
- sélection canonique SHA : `2026091102` ;
- bootstrap native `2026091103` ;
- bootstrap Q00 `2026091104` ;
- bootstrap chaîné natif Pool1+Pool2 `2026091201` ;
- bootstrap chaîné Q00 diagnostic `2026091202`.

Le bootstrap chaîné rééchantillonne séparément `3000` clusters avec remise
dans chaque pool, donne un poids `1/2` à chaque moyenne de pool, et répète
`200000` fois. Les deux pools doivent conserver chacun exactement `3000`
ouvertures/`6000` parties.

## 6. Exclusions des pools

Chaque pool et le corpus R0 sont dédupliqués sous board+STM exact et
rotate180+colour-swap. Les overlaps canoniques doivent être nuls avec :

1. toutes les identités de cohortes de la section 2 ;
2. les pools historiques déjà certifiés : context30 `1360/1361`, champion D
   `1348/1351`, reverse-seed `1108`, turnover `0984bis`, big pools
   `1154/1183`, volume8m `1004`, succession `0995`, context2
   `1375/1377`, context3 `1419` Pool1/2 et `1428` Pool1/2, replay DOE `1451`
   Pool1/2, replay promotion `1454` Pool1/2, RGSC `1562`, TB-policy
   `1568/1569`, DSSD-policy `1584` ;
3. tout autre pool de force ou de confirmation présent dans le reçu upstream
   au moment de l'exécution ; son ajout est une extension d'exclusion, jamais
   une modification scientifique ;
4. Pool1 pour Pool2.

Seuls les FEN/fingerprints/TSV d'identité sont récupérés. L'incapacité à
authentifier une exclusion est un abort technique, pas une permission de la
retirer.

## 7. Readout obligatoire

Pour chaque pool et chaque vue, publier :

- W/D/L du point de vue T3-A et score rate exact ;
- Elo point estimate `400*log10(p/(1-p))` ;
- CI95 score non apparié selon la variance empirique W/D/L, et transformation
  logit de ses bornes en CI95 Elo ;
- CI95 percentile du bootstrap ouverture appariée ;
- `P(score_rate > 0.5)` bootstrap ;
- score et erreurs par couleur/side ;
- moyenne et distribution des profondeurs, nodes, NPS et eval calls par bras ;
- profil/coût T3/F6 R0 authentifié ;
- SHA256 T3-A, CURRICULUM, executable, pools et résultats bruts ;
- code SHA, paramètres de recherche, TT/EGDB/maxplies, provenance et overlaps.

Le readout Pool2 publie en plus le bootstrap chaîné natif et Q00.

## 8. Verdict terminal

Après Pool2 :

`T3_F6_RUNTIME_STRENGTH_SUPPORTED` uniquement si :

1. Pool1 native `>0.5` ;
2. Pool2 native `>0.5` ;
3. borne basse CI95 du bootstrap chaîné natif `>0.5` ;
4. zéro asymétrie/panne technique ;
5. T3-A, CURRICULUM, executable et semantics runtime byte-identiques entre
   les deux pools.

Si Pool2 native `<=0.5` :

```text
T3_F6_RUNTIME_STRENGTH_NOT_SUPPORTED
```

Si les deux points natifs sont positifs mais que la borne basse chaînée est
`<=0.5` :

```text
T3_F6_RUNTIME_STRENGTH_INCONCLUSIVE
```

Q00 ne sauve jamais un échec natif.

## 9. Interprétation conditionnelle figée

- Q00 fortement positif mais native non supporté : le signal statique F6 reste
  établi ; le coût runtime empêche sa conversion wall-clock. Une suite ne peut
  être qu'une optimisation/compression sémantiquement exacte ou une nouvelle
  distillation runtime préenregistrée. Aucun retrait post-hoc de F2/F6.
- Q00 et native tous deux non supportés malgré q200 : diagnostiquer une
  incompatibilité ranking sibling vers sémantique value/alpha-beta avant tout
  nouveau training.
- force native robuste : STOP au verdict. Aucun bake, aucune promotion et
  aucune activation par défaut sans autorisation utilisateur explicite.

## 10. Réparations techniques et interdits

Une panne build, import, loader, sérialisation, C++ parity, runner, R2, path,
GitOps ou shell peut être réparée avec patch minimal, test ciblé, PR/CI/merge et
nouvel ID de job. Un retry technique réutilise les bytes et, dès qu'un pool est
généré ou un résultat lu, le même pool immuable.

Sont interdits après ce préenregistrement :

- refit, retune, nouvelle architecture ou nouvelle seed de modèle ;
- D1 ou autre input additionnel ;
- calibration/scale choisi après résultat ;
- suppression, sélection ou approximation de F1/F2/F3/F4/F5 ;
- changement de code ou optimisation entre Pool1 et Pool2 ;
- réutilisation des labels/scores/métriques consommés ;
- troisième pool ;
- bake ou promotion automatique.

