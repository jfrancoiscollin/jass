# Atlas de points aveugles jugé par Scan — TURNOVER (`cpx62-1114`, 2026-08-01)

`home-1002` avait établi que le résidu contre Scan est de la **marge
d'évaluation**, pas de la vitesse. On ne savait pas *où* elle se perd. Voici la
mesure.

**Ce job ne promeut rien, n'entraîne rien, n'ouvre aucune porte.** Scan est
**juge**, jamais source d'entraînement.

## Protocole et volume

Champion **TURNOVER** (`b2c79b36…`), runtime Scan gelé (`a634cbb4…`,
`data/eval` `0e7161c3…`, `bb-size=0`, pas de livre). À chaque coup où Jass est au
trait, Scan choisit depuis la même position à `d8` ; en cas de désaccord Scan
juge les **deux** enfants à `d10` et le coût est la différence de valeur du point
de vue du joueur au trait.

| | |
|---|---:|
| positions | **4 988 997** |
| parties | 88 101 |
| accords | 2 662 158 (53,4 %) |
| désaccords jugés | 2 326 839 |
| coûts écrêtés (plafond 1,0) | 157 052 (6,7 %) |
| coûts négatifs | 472 110 / 2 326 839 (**20,3 %**) |
| masse de coût totale | **318 785 unités-pion** |
| durée | 27 min, 16 shards, budget 25 min/shard |

Les 20,3 % de coûts négatifs sont le régime sain attendu (le juge est deux plies
plus profond que le joueur, il lui arrive de préférer notre coup). Le seuil
d'abort est à 40 %, une inversion de signe donnerait ~100 %.

## Résultat 1 — la marge se perd dans le **jeu calme**, presque pas en tactique

| famille | part de la masse | positions |
|---|---:|---:|
| `calme` | **96,7 %** | 3 709 536 |
| `capture_forcee` | **3,3 %** | 1 138 224 |

Les captures forcées représentent 23 % du corpus et **3 % de la perte**. Quand la
prise est forcée, on ne se trompe pratiquement jamais — la plupart de ces buckets
sortent à un coût de `0.000` avec un taux de désaccord sous 5 %.

## Résultat 2 — c'est l'**ouverture et le milieu**, pas la finale

| bande | part de la masse | positions |
|---|---:|---:|
| `ouverture_25+` | 39,3 % | 2 358 035 |
| `milieu_13_24` | **47,5 %** | 1 583 491 |
| `finale_7_12` | 12,0 % | 736 113 |
| `finale_tres_courte_<=6` | 1,2 % | 170 121 |

**87 % de la perte est avant la finale.** C'est contre-intuitif : l'effort
« features de finale / dames / EGDB » ne vise pas là où l'argent part.

## Résultat 3 — aucun point chaud : la perte est **diffuse**

C'est le résultat qui compte, et il demande de ne pas confondre deux lectures.

**Par masse**, ça a l'air concentré : 3 buckets font 50 % de la perte, 7 en font
80 %. **Par taux, non** : les buckets de tête sont simplement les plus *peuplés*,
et leur coût par position est parmi les plus **bas**.

| part de la masse | coût/position | n | bucket |
|---:|---:|---:|---|
| 30,6 % | **0,064** | 1 511 077 | `ouverture_25+ / sans_dame / materiel_egal / calme` |
| 16,0 % | 0,117 | 433 565 | `milieu_13_24 / sans_dame / materiel_egal / calme` |
| 14,2 % | 0,136 | 331 507 | `milieu_13_24 / sans_dame / en_retard_1_2 / calme` |
| 7,1 % | 0,099 | 225 973 | `milieu_13_24 / dames_d_un_seul_cote / en_retard_3+ / calme` |
| 5,5 % | 0,125 | 141 875 | `ouverture_25+ / sans_dame / en_retard_1_2 / calme` |

Le bucket qui coûte le plus cher **par position** (`0,349`) pèse 1 777 positions
et ne représente rien à l'échelle du corpus. Le bucket qui coûte le plus **au
total** est le plus banal de tous, et son coût unitaire est le plus faible du
classement.

**Il n'y a pas de point aveugle localisable.** La perte est proportionnelle à la
fréquence des positions : une erreur d'évaluation systématique et de faible
amplitude, étalée sur tout le jeu positionnel calme.

## Résultat 4 — la conversion n'est pas notre problème

**0 conversion ratée sur 141 213 désaccords saturés.** Chaque fois que Scan a
jugé l'un des deux coups candidats comme gain forcé, notre coup n'était jamais
celui qui jetait le gain.

⚠️ **Limite de construction à connaître** : la famille conversion contient
exactement autant de « positions » que de désaccords (141 213 = 141 213), parce
que `classify_sample` ne peut router une position vers « conversion » que si elle
porte un coût — donc seulement les désaccords. Le dénominateur est donc
« désaccords saturés », pas « positions saturées ». L'énoncé exact est : *parmi
les positions saturées où nous divergeons de Scan, nous n'avons jamais choisi le
mauvais côté*. À corriger si l'on veut un vrai taux par position.

## Ce que ça ne dit PAS — et pourquoi le témoin est indispensable

Cet atlas n'a **pas de contrôle**. Rien ici ne permet de distinguer :

- « voilà les points aveugles de **TURNOVER** », de
- « voilà où **n'importe quelle éval linéaire** diverge de Scan ».

Un profil diffus dans le jeu calme est *aussi* ce qu'on attendrait de la
différence de classe entre un modèle linéaire et Scan, indépendamment de notre
modèle. **Sans second point de mesure, aucune conclusion sur la capacité n'est
recevable.**

Le témoin naturel est **Gen2** : champion historique, hors lignée L3, déjà
utilisé comme thermomètre figé. Même protocole, même budget. Ce qui compte alors
est le **différentiel** TURNOVER − Gen2 :

- profil et amplitude **identiques** → on a mesuré la classe, pas notre modèle,
  et l'atlas ne dit rien sur 8cf ;
- TURNOVER **uniformément meilleur, même forme** → plafond de représentation, et
  la question de la capacité (32cf) redevient légitime, avec une mesure derrière ;
- **formes différentes** → il y a bien des points aveugles propres, et ils sont
  identifiés.

## Rapport à l'arbitrage 32cf

La prémisse qui avait fermé la porte 32cf — « 8cf est sous-alimenté » — a été
falsifiée par `home-1004` (13,5 % de buckets touchés, 41,7 observations/paramètre
à 12 M, et ce volume a **nui** : `home-1008`, −14,95 Elo). La porte est donc close
sur un argument qui ne tient plus.

Cet atlas est le premier élément neuf depuis. Il **ne tranche pas** l'arbitrage —
il ne le pourra qu'avec le témoin Gen2. **La décision reste à JFC.**

## Défaut d'outillage corrigé au passage

Le monitor faisait `ls "$W"/done-s* | wc -l`. Sur un motif sans correspondance
`ls` sort en 2, ce qui déclenche le trap `ERR` : **six lignes « ABORT line=72 »
ont été écrites dans le RESULTS d'un job qui a réussi**. Un abort mensonger dans
un fichier de résultats induit en erreur bien après le run — remplacé par `find`,
qui ne peut pas échouer ainsi.

## Artefacts

`r2:jass-data/runs/cpx62-1114-l3-scan-blind-spot-atlas-v1/20260731T220546Z-d1f6bb16`
— `atlas.json` (78 buckets classés, 10 sous plancher), `samples.jsonl.gz`
(61,8 Mo, les 4,99 M observations brutes).
