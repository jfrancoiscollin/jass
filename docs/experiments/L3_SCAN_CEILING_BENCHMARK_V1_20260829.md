# L3 — JASS / T3-A / SEARCH vs SCAN DEEP — benchmark ceiling v1

Date de préenregistrement : 29 août 2026. Statut : **préenregistré avant toute
génération de score Scan ou Jass sur le nouveau cohort**. La compilation et le
smoke technique ne produisent aucune métrique scientifique du cohort.

## 0. Question, portée et séparation HOME / CPX62

Cette campagne mesure, sur un cohort entièrement neuf et target-blind, la
distance de plusieurs évaluateurs et budgets de recherche Jass à une référence
empirique Scan profonde. Elle doit répondre quantitativement à trois questions :

1. T3-A est-il proche du plafond pratique accessible par Scan profond ?
2. Jass q200k est-il lui-même proche de Scan profond ?
3. Le headroom principal restant relève-t-il du student/distillation, de la
   profondeur de recherche, ou de la recherche/sémantique Jass par rapport à
   Scan ?

Les termes normatifs sont `external_deep_reference`,
`practical_scan_ceiling` et `scan_convergence`. Scan profond n'est jamais
appelé « vérité parfaite » ni optimum mathématique.

La campagne est **strictement benchmark-only** :

```text
SCAN_BENCHMARK_ONLY=true
fits=0
refits=0
calibrations=0
feature_selections=0
model_selections=0
strength_games=0
bakes=0
promotions=0
```

Tous les jobs scientifiques réels portent le préfixe `home-` et s'exécutent
uniquement sur HOME. Un micro-smoke local sans cohort est permis. CPX62 garde
sans interruption sa campagne T3-A runtime/strength ; aucun job HOME ne peut
attendre, modifier, annuler ou réordonner un job CPX62. La présente campagne ne
choisit ni feature, ni scale runtime, ni calibration, et ne peut influencer le
contraste de force T3-A en cours.

Avant le premier job HOME, le control-plane doit prouver qu'aucun `home-*`
n'est `pending`, `claimed` ou réellement `running`. Une entrée ancienne dont
le timeout dur est dépassé peut uniquement être archivée par une mutation Git
auditée ; elle ne peut être réutilisée comme attempt. Aucun doublon de job ou
de cohort n'est permis.

### 0.1 Amendement technique pré-score — contrat de nœuds observables

Cet amendement est figé après le smoke sentinelle `home-1648` et avant toute
sélection du cohort ou génération d'un score scientifique. Au moment de cette
découverte : `parents_scientifiques=0`, `scores_scientifiques=0`, `fits=0`.
Elle ne change aucun budget nominal, seed, artifact, cohort, subset, référence,
métrique, bootstrap ou seuil de verdict. Elle corrige uniquement deux
affirmations techniquement impossibles avec les moteurs inchangés :

1. Scan officiel demande exactement `N` par `level nodes=N`, mais son compteur
   final consommé n'est pas exposé et son dernier snapshot progressif peut
   franchir `N` avant le prochain poll interne de 16 nœuds ;
2. Jass en `NodeLimitMode::Exact` s'arrête exactement à `N` lorsqu'il rencontre
   le plafond, mais une ligne forcée peut finir les `MAX_PLY=64` complets avant `N`.

Les règles source-derived et fail-closed correspondantes sont détaillées aux
§1, §2 et §6. Aucun algorithme Scan ou Jass n'est modifié pour fabriquer un
compteur égal à `N`.

### 0.2 Amendement technique pré-score — preuve de POV sous symétrie

Cet amendement est figé après le smoke sentinelle `home-1649` et avant toute
sélection du cohort ou génération d'un score scientifique. À cette découverte :
`parents_scientifiques=0`, `scores_scientifiques=0`, `fits=0`. Il ne change
aucun budget, seed, artifact, cohort, subset, score scientifique, métrique,
bootstrap ou seuil de verdict.

Le smoke initial exigeait à tort l'égalité numérique entre deux recherches à
budget fini sur des boards liés par rotation 180° et échange des couleurs.
Cette égalité n'est pas une propriété de Scan ou Jass inchangés : leur ordre de
génération/recherche n'est pas invariant sous cette transformation, donc deux
recherches déterministes demandées à `N` peuvent couper des branches différentes.
Ce phénomène ne constitue ni une ambiguïté de board/STM, ni une erreur de POV.

La preuve fail-closed est remplacée par les invariants techniquement valides :

1. identité exacte de chaque enfant transformé entre les générateurs Jass et
   Scan officiels ;
2. égalité exacte du score statique T0 en POV parent sur toutes les paires
   sentinelles rotation/couleur-swap ;
3. publication par chaque ligne Jass et Scan des scores enfant et parent, avec
   assertion exacte `parent_score == -child_score` ;
4. utilité exacte parent sur les terminaux/tablebases et replay déterministe de
   chaque board+STM avec état frais.

L'égalité cross-symmetry des scores de recherche à budget fini n'est donc pas
requise et aucune tolérance de score n'est introduite. Aucun algorithme moteur
n'est modifié ; Jass ajoute seulement un champ de reçu diagnostique.

## 1. Provenance Scan immuable

Moteur officiel retenu : **Scan 3.1** de Fabien Letouzey, moteur de dames
internationales 10x10 parlant Hub v2, via le miroir public maintenu par Rein
Halbersma :

- dépôt : `https://github.com/rhalbersma/scan` ;
- release annoncée par les sources : `Scan 3.1` ;
- tag Git : aucun tag publié dans ce dépôt ;
- commit exact :
  `7aae17e7b7bfc47744601afb1ee7655e18983ce5` ;
- arbre Git exact :
  `023eace16a90ec543b6b6174c79cfc42488a356e` ;
- date upstream du commit : `2019-07-06T18:54:41Z` ;
- `src/Makefile` blob :
  `7598768214fd8b3120067b65702de4756e9d8b83` ;
- protocole Hub blob :
  `a65b0943bb4e026b2d54df5b9c638e3d80de92ca`.

Le preflight clone ou extrait exactement ce commit sur HOME, vérifie l'arbre
propre, puis compile les sources inchangées avec le Makefile officiel. Contrat
de compilation upstream :

```text
CXX=g++
CXXFLAGS=-pthread -std=c++14 -fno-rtti -O2 -mpopcnt -flto -DNDEBUG
LDFLAGS=-pthread -O2 -flto
```

Il est interdit de patcher, instrumenter ou modifier un algorithme Scan. Le
manifest preflight publie avant le cohort : URL, release, commit, arbre,
commande de compilation, Makefile brut et SHA256, version complète du
compilateur, flags effectifs, OS/kernel, sortie CPU complète (`lscpu` ou
équivalent), nombre de CPU logiques, SHA256 du binaire HOME et preuve que le
répertoire source est propre. Le binaire ainsi compilé, et non un ancien
binaire précompilé, est utilisé byte-identique par tous les shards.

Options Hub figées :

```text
variant=normal
book=false
book-ply=4
book-margin=4
ponder=false
threads=1
tt-size=24
bb-size=0
```

Scan tourne donc sans livre et sans tablebase (`bb-size=0`). Un processus Scan
par shard est permis, mais chaque sibling/budget reçoit `new-game` avant
`pos`, ce qui efface la TT selon le protocole officiel. Le mode est toujours
`go analyze`, jamais `go think` : il recherche aussi un enfant à coup légal
unique et désactive tout comportement de jeu non pertinent. Le budget est
envoyé exactement par `level nodes=N`. À un thread et après la profondeur 1,
`Search_Local::inc_node()` du commit épinglé pose le stop root dès
`m_node >= N`, puis le thread n'observe ce stop qu'au prochain `poll()`, exécuté
tous les `16` nœuds (`m_node & 15 == 0`). Le protocole stock ne réémet pas le
compteur final lors de l'abort : ses lignes `info nodes=` sont des snapshots
progressifs, pas le total consommé. Le manifest publie donc séparément :

```text
requested_nodes = N
scan_node_poll_quantum = 16
last_info_snapshot_upper_bound = ceil(N / 16) * 16
last_info_nodes = dernier snapshot info complet, jamais appelé consommation finale
```

À nos budgets, l'upper bound vaut `1008` pour `1k`, `5008` pour `5k`, puis
exactement `N` pour `50k`, `200k`, `1M`, `2M` et `5M`. Un snapshot nul ou
supérieur à cette borne, l'absence d'`info`, un replay non déterministe ou une
autre dérive est un abort technique. Cette borne fixée par le source n'est ni
une marge empirique, ni un budget adapté par position : la commande reste
exactement `nodes=N`. Aucune conversion temps/profondeur n'est admise.

Un enfant terminal n'est pas envoyé à Scan, conformément au protocole Hub : il
reçoit le score terminal natif exact, du point de vue parent (`+100.00` pour un
gain immédiat, signe opposé si applicable), `nodes=0`, et le même score à tous
les budgets. Côté Jass, un enfant terminal ou résolu par l'EGDB de production
reçoit également la priorité exacte existante et `nodes=0`. Ces lignes restent
présentes à tous les budgets et sont marquées `terminal_exact` ou `tb_exact` ;
elles ne sont jamais remplacées par une recherche artificielle.

## 2. Artifacts Jass gelés et sémantique de recherche

Artifacts bruts obligatoires :

| signal | SHA256 exact |
|---|---|
| T0 / CURRICULUM | `319d174f4b548b1655aad4bb30d4c6dc86c08dd715c9c23f8b19ba1937dc0be1` |
| sealed D1 | `e91a55500713154f50be74db5d699b64d7684e1c078725d09e1d15e713549b49` |
| frozen RF1/F6 | `0d26ba50b668160b3da3e247cd4e1bd709c2cb7989b3b5877b9ea7deb34db58b` |
| frozen T3-A | `16e5db8fd78849bba12b158eee5c1da4ab170129d8aeac1b91ab7a40ad9d0bb2` |

RF1 est techniquement disponible sous forme gelée et doit être lu sans refit.
Une impossibilité de charger/authentifier un artifact est une panne technique,
jamais une autorisation de l'omettre, le reconstruire ou le réentraîner.

Les signaux statiques sont calculés sur tous les siblings : T0, D1, RF1 et
T3-A. D1/RF1/T3-A utilisent leurs extracteurs et normalisations gelés ; aucune
moyenne, écart-type, feature ou pondération n'est recalculé. Tous les scores
sont exprimés du point de vue du parent. Pour un enfant non terminal, cela
implique l'inversion negamax exacte du score enfant ; le smoke vérifie ce signe.

Les recherches Jass utilisent CURRICULUM comme évaluation de production,
Q00/paramètres de production inchangés, livre OFF, un thread par recherche,
TT de taille `16 MiB`, EGDB de production authentifiée et même priorité
terminal/tablebase que le teacher T3 gelé. Chaque sibling et chaque budget
construit un nouvel `Engine` : TT, historique, search state et compteurs frais.
`NodeLimitMode::Exact` est obligatoire. Une ligne effectivement recherchée est
acceptée sous exactement un des deux statuts :

- `requested_nodes_reached` : stop `nodes`, itération avortée et
  `reported_nodes == N` ;
- `max_depth_exhausted` : `0 < reported_nodes < N`, stop `none`, profondeur
  complète et effective `64`, itération non avortée.

Tout dépassement de `N`, toute sous-consommation sous un autre statut ou tout
replay divergent est un abort technique. Les lignes terminales/EGDB directes
restent à zéro comme défini au §1. Le signal `JassNk` désigne toujours la
recherche de production lancée avec la cap demandée `N`, et le readout publie
séparément les comptes/nœuds des lignes `max_depth_exhausted`.

Budgets Jass sur tous les parents :

```text
Jass1k   = 1,000 nodes
Jass5k   = 5,000 nodes
Jass50k  = 50,000 nodes
Jass200k = 200,000 nodes
```

Sur DEEP512, ajouter `Jass1M = 1,000,000 nodes`. Aucun écran q50/q200,
stabilité, marge cp, accept/reject ou sélection de parent n'est exécuté. Les
budgets ne changent jamais après lecture d'un score.

## 3. Nouveau cohort target-blind de 2 000 parents

Le cohort final contient exactement `2000` parents, avec exactement :

| phase | pièces | parents |
|---|---:|---:|
| P0 | 30..40 | 500 |
| P1 | 20..29 | 500 |
| P2 | 12..19 | 500 |
| P3 | 9..11 | 500 |

Chaque parent est légal, non terminal, et possède `2..16` coups légaux. La
génération source produit exactement `16` shards de `50,000` candidats issus
de trajectoires légales aléatoires, sans évaluation, label ou résultat utilisé
pour les choisir :

```text
source_seed_base = 2026091310
source_seed(shard i) = 2026091310 + i, i in [0,15]
selection_seed = 2026091301
min_ply = 8
max_ply = 160
min_pieces = 9
```

Après validation et exclusions, chaque phase est triée par ordre croissant de
`sha256("2026091301:" + canonical_board_stm)` ; les 500 premières identités
forment la phase. Le volume source et les seeds sont fixes : un support
insuffisant est un abort technique, pas une permission de générer davantage,
changer une seed, relâcher une exclusion ou remplacer un parent lent.

`canonical_board_stm` est le minimum byte-lexicographique entre board+STM exact
et son rotate180+colour-swap avec STM/couleurs transformés, selon le contrat
canonique Jass existant. La déduplication board+STM exacte et la déduplication
canonique sont toutes deux obligatoires. Le reçu publie comptes avant/après,
quotas, overlaps et SHA256 des 2000 lignes ordonnées.

### 3.1 Exclusions identity-only obligatoires

Seules les identités board+STM peuvent être lues ; aucun score/label/métrique
historique ne participe à la sélection. Les sources gelées minimales sont :

- TRAIN-A `cpx62-1570` ; TRAIN-B / confirmation DSSD `cpx62-1578` ;
  TRAIN-C / Rich-D fresh `cpx62-1587` ;
- M1 `1591`, dont les identités sont le même cohort Rich-D `1587`, puis M2
  `1593`, M3 `1599`, M5 `1609` ;
- Q1 `1617`, T2 fresh `1628c`, RF1 fresh `1633`, T3 fresh `1638` ;
- pools de force context30 `1360/1361`, champion D `1348/1351`, reverse-seed
  `1108`, turnover `0984bis`, big `1154/1183`, volume8m `1004`, succession
  `0995`, context2 `1375/1377`, context3 `1419` Pool1/2 et `1428` Pool1/2,
  replay DOE `1451` Pool1/2, replay promotion `1454` Pool1/2, RGSC `1562`,
  TB-policy `1568/1569`, DSSD-policy `1584` ;
- tout autre pool force/confirmation connu dans le reçu upstream ;
- tout corpus R0 ou pool runtime T3-A créé avant l'instant où la sélection
  HOME fige son snapshot d'exclusion.

Les URI/fichiers exacts des `10` sources d'identités et `24` sources de force
du contrat runtime T3/F6 sont importés byte-identiques. Au début de la
sélection, le job capture l'heure UTC, le SHA du control-plane, ses états et la
liste des artifacts runtime T3-A existants. Tout R0/Pool1/Pool2 déjà matérialisé
est ajouté identity-only. Un artifact créé après ce cutoff n'altère pas le
cohort HOME déjà hashé. Toute source attendue absente ou non authentifiable
fait échouer la sélection.

## 4. Sous-ensembles imbriqués, avant tout score

Après fixation des 2000 parents et avant tout score :

```text
subset_hash_seed = 2026091302
```

Dans chaque phase, trier les 500 parents par
`sha256("2026091302:" + canonical_board_stm)`. Les 128 premiers forment la
strate de phase DEEP512 ; ses 64 premiers forment la strate ULTRA256. On obtient
exactement :

- DEEP512 : `512` parents, `128` par phase ;
- ULTRA256 : `256` parents, `64` par phase, sous-ensemble strict de DEEP512.

La sélection n'utilise aucun score. Les deux listes ordonnées, leur inclusion,
leurs quotas et SHA256 sont publiés avant le scoring.

## 5. Ladder Scan figée

Chaque sibling reçoit un score à chaque budget applicable :

| scope | budgets Scan demandés exacts |
|---|---|
| BASE2000 | 1k, 5k, 50k, 200k |
| DEEP512 additionnel | 1M, 2M |
| ULTRA256 additionnel | 5M |

Soit exactement `1,000`, `5,000`, `50,000`, `200,000`, `1,000,000`,
`2,000,000` et `5,000,000` comme valeurs `N` envoyées au moteur. Les abscisses
de convergence et l'équivalent descriptif utilisent ces budgets demandés
immuables, jamais le snapshot progressif. Le score retenu est le dernier `info`
complet avant `done`, conservé comme token décimal exact Scan et comme entier
en centièmes de pion ; aucune conversion float n'intervient dans les égalités.
Le score enfant Scan est inversé une seule fois vers le point de vue parent.

Références préenregistrées :

- BASE2000 : Scan200k, uniquement pour la table large descriptive ;
- DEEP512 principale : Scan2M = `external_deep_reference` secondaire mais plus
  puissant statistiquement ;
- ULTRA256 principale de plafond : Scan5M = `external_deep_reference`, avec
  Scan2M comme estimateur du `practical_scan_ceiling`.

La `scan_convergence` publie directement Scan1M vs Scan2M sur DEEP512, puis
Scan1M vs Scan5M et Scan2M vs Scan5M sur ULTRA256. Aucun budget ne peut être
ajouté, supprimé ou déplacé après lecture.

## 6. Smoke technique obligatoire, sans métrique scientifique

Avant sélection/scoring complet, quelques positions sentinelles fixes et
étrangères au cohort vérifient :

1. parsing board/STM Jass vers les 51 caractères Scan et round-trip exact ;
2. identité de tous les coups légaux, captures multiples, promotion et enfant
   obtenu ;
3. correspondance un-à-un entre sibling Jass et child Scan ;
4. signe enfant/parent explicite sur chaque ligne, égalité T0 parent-POV sur les
   paires couleur-swap et utilités terminales/tablebases exactes ;
5. `level nodes=N`, `go analyze`, preuve du stop interne source à N avec poll
   16 nœuds, snapshots `info` sous la borne source-derived fixée au §1 ;
6. replay déterministe après `new-game`, incluant score/PV/nœuds ;
7. enfants terminal, coup forcé non terminal, tablebase Jass et absence de
   recherche terminale Scan ;
8. `book=false`, `threads=1`, `bb-size=0` et toutes les options déclarées ;
9. binaire/source/CPU/compilateur authentifiés.

Le smoke publie seulement PASS/FAIL et des transcripts techniques ; aucune
accuracy, corrélation ou table du benchmark final. Une ambiguïté de conversion,
une dérive du contrat de nœuds amendé, une non-détermination ou un score POV incohérent produit
`SCAN_MAPPING_TECHNICAL_STOP`. Le mapping doit être réparé et retesté avant le
cohort, sans modifier Scan.

## 7. Identités siblings et contrat pairwise/top-hit

Tous les coups légaux sémantiques de chaque parent sont énumérés dans l'ordre
canonique `(from, to, sorted_captured_squares, promotes, canonical_child)`.
L'identité sibling est le SHA256 de l'identité parent canonique, de ce tuple et
du board+STM enfant. Deux représentations textuelles du même coup sémantique ne
créent pas deux siblings ; deux coups sémantiques distincts restent distincts.

Pour chaque parent, tous les unordered sibling pairs sont énumérés. Pour une
référence Scan donnée :

- scores référence distincts : pair primaire comparable ;
- scores référence exactement identiques : pair exclu du pairwise primaire ;
- aucune marge cp, aucun epsilon et aucun threshold post-hoc ;
- prédiction de sens correcte : `1`, incorrecte : `0`, score signal exactement
  lié sur un pair référence distinct : `0.5`.

Pour le top-hit primaire, le choix du signal est son score maximal, ties signal
résolus par la plus petite identité sibling canonique. Le top-hit vaut `1` si
ce choix appartient au top-tie set exact Scan, sinon `0`.

Un diagnostic strict tie-broken applique, à chaque égalité de score référence
ou signal, la seule plus petite identité sibling canonique. Il inclut alors
tous les pairs et un unique top référence. Il est toujours étiqueté
`diagnostic_strict_canonical_tiebreak`, jamais substitué au primaire.

## 8. Métriques, strates et incertitude

Pour chaque scope/référence, publier pour T0, D1, RF1, T3-A, Jass1k, Jass5k,
Jass50k, Jass200k, Jass1M lorsqu'il existe, et chaque budget Scan inférieur à
la référence :

- pairwise accuracy primaire et strict diagnostic ;
- top-hit primaire et strict diagnostic ;
- Kendall tau-b et Spearman rho de rang sibling si définis ;
- nombre de parents, siblings, pairs totaux/comparables/tied et parents
  admissibles par métrique ;
- résultats globalement et par P0/P1/P2/P3, parent black/white, branching et
  nombre de pièces.

L'accuracy pairwise globale est pondérée par les pairs comparables ; le top-hit
est une moyenne par parent. Kendall/Spearman sont calculés par parent avec
gestion standard des ties, puis macro-moyennés sur les parents où les deux
rangs ont une variance non nulle ; les `NA` et leurs effectifs sont publiés.

Strates fixes :

```text
branching: 2..4 | 5..8 | 9..12 | 13..16
pieces:    9..11 | 12..15 | 16..19 | 20..24 | 25..29 | 30..34 | 35..40
colour:    black parent STM | white parent STM
```

Bootstrap par cluster parent :

```text
bootstrap_samples = 200000
bootstrap_seed = 2026091303
RNG = numpy.random.Generator(numpy.random.PCG64(seed))
CI = percentile [2.5%, 97.5%]
```

Dans chaque scope/strate, rééchantillonner les parents avec remise et emporter
tous leurs siblings/pairs. Chaque réplication recalcule les ratios avec leurs
dénominateurs réels. Les deltas utilisent le même tirage apparié. Les
réplications à dénominateur nul sont `NA`, comptées et exclues des quantiles.
Tous les points et CI95 utilisent ce contrat ; aucun changement de seed,
méthode ou nombre d'échantillons après score.

## 9. Analyses principales préenregistrées

### 9.1 Bottleneck sur DEEP512 / Scan2M

Soit `A(M)` l'accuracy pairwise primaire de M contre Scan2M. Publier avec CI
appariés :

- récupération T3-A depuis T0 : `A(T3-A)-A(T0)` et, descriptivement,
  `(A(T3-A)-A(T0))/(1-A(T0))` si dénominateur positif ;
- headroom student vers teacher/search : `A(Jass200k)-A(T3-A)` ;
- gap Jass q200k vers la référence : `1-A(Jass200k)` ;
- gain de profondeur Jass : `A(Jass1M)-A(Jass200k)` et gap
  `1-A(Jass1M)` ;
- comparaison même budget : `A(Scan200k)-A(Jass200k)` et
  `A(Scan1M)-A(Jass1M)`.

Le `1-A` est un taux de désaccord descriptif avec la référence, pas une preuve
d'optimalité. Les nombres bruts/CI priment sur toute étiquette.

### 9.2 Équivalent descriptif en nœuds Scan

Sur ULTRA256 contre Scan5M, construire la courbe Scan aux abscisses
`[1k,5k,50k,200k,1M,2M]`. Pour assurer une inversion unique sans sélectionner
des points après coup, appliquer une régression isotone non décroissante PAVA,
poids égaux aux nombres de pairs comparables. Inverser ensuite par interpolation
linéaire en `log10(nodes)`.

Chaque signal est positionné par son accuracy contre Scan5M :

- sous le premier niveau : `<1k`, sans extrapolation ;
- au-dessus du dernier : `>2M`, sans extrapolation ;
- plateau isotone : intervalle de nœuds complet et milieu géométrique ;
- sinon : `SCAN_NODE_EQUIVALENT` interpolé.

Le bootstrap joint refait PAVA et l'inversion à chaque tirage ; publier CI95
des réplications finies et proportions `<1k`, `>2M` et plateau. Cette quantité
est uniquement un pouvoir de ranking équivalent sur ce cohort, jamais une
égalité de force moteur.

### 9.3 Practical headroom recovery sur ULTRA256

Définir exactement :

```text
A_ceiling = accuracy(Scan2M, Scan5M)
Recovery(M) = (A_M - A_T0) / (A_ceiling - A_T0)
```

Publier point et CI95 bootstrap apparié pour D1, RF1, T3-A, Jass1k, Jass50k,
Jass200k et Jass1M. Si le dénominateur est `<=0`, résultat `NA`. La valeur
n'est pas clampée : `<0` ou `>1` reste visible. Scan5M comparé à lui-même
n'entre jamais dans le dénominateur.

### 9.4 Désaccords Jass / Scan, agrégés uniquement

Sur ULTRA256, construire uniquement des comptes/taux et ventilations agrégées,
sans publier FEN, diagramme, identifiant individuel ou liste de positions :

1. choix top Scan5M et Jass200k différents ;
2. T3-A choisit le même sibling que Jass200k, hors top-tie set Scan5M ;
3. T3-A appartient au top-tie set Scan5M, Jass200k non ;
4. Jass200k appartient au top-tie set Scan5M, T3-A non.

Les catégories 2..4 sont rapportées comme sous-catégories définies ci-dessus
et peuvent ne pas partitionner toute la catégorie 1. Elles ne peuvent motiver
ni fit, ni feature selection, ni patch moteur dans cette campagne. Une suite
scientifique éventuelle exige une nouvelle prereg séparée.

## 10. Seuils de verdict et lecture roadmap fixés avant scores

Le verdict terminal de distance q200 utilise exclusivement DEEP512 contre
Scan2M et le CI95 bootstrap de `A(Jass200k)` :

1. si borne basse `>= 0.95` :
   `JASS_Q200_NEAR_SCAN_PRACTICAL_CEILING` ;
2. sinon, si borne haute `< 0.85` :
   `JASS_SEARCH_LARGE_HEADROOM_TO_SCAN_ESTABLISHED` ;
3. sinon, si borne haute `< 0.95` :
   `JASS_SEARCH_HEADROOM_TO_SCAN_ESTABLISHED` ;
4. sinon : `JASS_Q200_SCAN_DISTANCE_INCONCLUSIVE`.

La recommandation de prochain investissement est une lecture secondaire fixe :

- `STUDENT_DISTILLATION_PRIMARY` si le verdict q200 est NEAR et la borne basse
  de `A(Jass200k)-A(T3-A)` est `>0.02` ;
- `SEARCH_DEPTH_PRIMARY` si q200 n'est pas NEAR, que la borne basse de
  `A(Jass1M)-A(Jass200k)` est `>0`, que le point gagne au moins `0.02`, et que
  Jass1M ferme au moins `30%` du gap q200, soit
  `(A(Jass1M)-A(Jass200k))/(1-A(Jass200k)) >= 0.30` ;
- `JASS_SEARCH_SEMANTICS_PRIMARY` si la borne haute de A(Jass1M) est `<0.90`
  et la borne haute du gain `A(Jass1M)-A(Jass200k)` est `<=0.02` ;
- sinon `MIXED_OR_INCONCLUSIVE_HEADROOM`.

Ces règles ne déclenchent aucune action, aucun training et aucune promotion.
La convergence Scan et les deltas mêmes-budgets doivent accompagner le label,
car ils peuvent révéler une référence encore mobile ou une combinaison de
bottlenecks.

## 11. Pipeline shardé, immutable et reprenable

Ordre logique obligatoire, avec un manifest SHA256 et `16` shards déterministes
par stage de score (`parent_index mod 16`). L'implémentation est figée ici,
avant le premier score du cohort, en jobs HOME séparés pour rendre chaque
frontière de reprise authentifiable :

1. `home-...-scan-ceiling-preflight-v1` : build officiel + smoke seulement ;
2. `home-...-scan-ceiling-selection-v1` : candidats, exclusions, 2000 parents,
   DEEP512/ULTRA256, zéro score ;
3. `home-...-scan-ceiling-static-v1` : T0/D1/RF1/T3-A, première lecture qui
   consomme définitivement cohort et scores ;
4. `home-...-scan-ceiling-jass-base-v1` : Jass 1k/5k/50k/200k ;
5. `home-...-scan-ceiling-scan-base-v1` : Scan 1k/5k/50k/200k ;
6. `home-...-scan-ceiling-jass-deep-v1` : Jass1M sur DEEP512 ;
7. `home-...-scan-ceiling-scan-deep-v1` : Scan1M/2M sur DEEP512 ;
8. `home-...-scan-ceiling-scan-ultra-v1` : Scan5M sur ULTRA256 ;
9. `home-...-scan-ceiling-readout-v1` : analyses et memo terminal.

Cette décomposition opérationnelle ne change aucun cohort, signal, budget,
référence, seed, bootstrap, seuil ou ordre de lecture scientifique. HOME reste
mono-mission : un seul de ces jobs est actif à la fois, indépendamment de
CPX62. Chaque stage à `16` shards limite la concurrence à `15` workers afin de
laisser au moins un CPU logique de marge ; le seizième shard est exécuté dans
une seconde vague avec exactement les mêmes paramètres.

Un stage aval authentifie chaque manifest/cohort/binaire/artifact upstream.
Chaque shard écrit un fichier temporaire puis le renomme atomiquement, publie
nombre de lignes et SHA256, et devient immutable. En cas de panne, le run en
échec publie les shards complets ; le retry avec un nouvel ID télécharge,
authentifie et reprend uniquement les shards manquants. Un shard complet n'est
jamais recalculé ou fusionné avec des bytes différents. Aucun parent n'est
remplacé parce qu'il est lent. Toute réparation technique exige patch minimal,
test ciblé, PR/CI/merge et nouvel ID de job.

Avant le full, le preflight publie débits réels Jass/Scan, nombre de searches,
NPS et ETA calculée pour chaque stage. Le runner conserve au moins un CPU de
marge et respecte la mémoire/charge observée ; le nombre de workers ne change
pas les recherches, qui restent toutes mono-thread.

## 12. Quarantaine benchmark-only et readout terminal

Dès la première lecture d'un score du cohort, ses 2000 identités, tous leurs
siblings et tous les scores/labels deviennent consommés définitivement. Les
manifests portent :

```text
benchmark_only=true
training_allowed=false
tuning_allowed=false
calibration_allowed=false
model_selection_allowed=false
runtime_scale_selection_allowed=false
```

Ils sont interdits dans tout futur training, tuning, feature/model selection,
calibration, teacher selection ou promotion, y compris T3-A et sa campagne
runtime courante. Seule leur liste d'identités peut servir à une exclusion
future. Le readout échoue si ces guards ou le reçu de consommation manquent.

Un memo scientifique séparé,
`docs/experiments/L3_SCAN_CEILING_BENCHMARK_V1_RESULTS_20260829.md`, publie :

- provenance Scan complète, CPU/threads/options/tablebase, binaire SHA ;
- SHA du cohort, subsets, exclusions et artifacts Jass ;
- ladders/nœuds réels, replay et manifests de shards ;
- tables pairwise/top-hit/corrélations, CI95 et toutes les strates ;
- convergence Scan ;
- équivalents Scan-nodes ;
- practical headroom recovery ;
- gaps T3-A, Jass q200k/q1M et diagnostics de désaccord agrégés ;
- verdict descriptif et implication roadmap selon les règles ci-dessus ;
- confirmation explicite `fits=0`, `strength_games=0`, `promotion=false`.

Le readout est terminal et non promotionnel. Aucune continuation automatique
n'est autorisée.
