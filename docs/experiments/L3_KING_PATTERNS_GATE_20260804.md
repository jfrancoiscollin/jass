# `--king-patterns` — porte jouée, axe clos

Verdict du 4 août 2026, `cpx62-1172`. Ferme la condition de réouverture de la
porte `0409`, restée ouverte faute d'avoir jamais été jouée au scale.

## La question

`--king-patterns` fait entrer les dames dans l'**occupation** des patterns :
`pb = bm | bk` au lieu de `pb = bm`. Une case occupée par une dame cesse d'être
vide aux yeux du pattern, comme chez Scan.

⚠️ **Ce n'est pas une question de capacité.** `n_pat` est **inchangé**
(`4 251 528`), `n_ext = 120` des deux côtés. Ce qui change est **le sens d'une
case occupée**, pas le nombre de poids disponibles.

## Le verdict

`cpx62-1172`, pool `big3000` (3000 ouvertures, disjoint des pools de porte
antérieurs), estimateur à vues **additionnées**, `n = 12 000`, EGDB présente :

```text
KING 5722W 651D 5627L contre TIGHT
taux = 0,5040   IC95 = [0,4953 ; 0,5127]
Elo  = +2,75    IC95 = [−3,3 ; +8,8]
A_FLAT_VS_B_NO_ESTABLISHED_GAIN
```

**L'intervalle contient zéro : aucun gain établi.**

✅ **Et ce n'est PAS un manque de puissance — c'est une borne.** La borne haute
`+8,8` **exclut** un gain de l'ordre de ceux que la campagne a encaissés :

| gain acquis | Elo |
|---|---|
| fold exact | `+15,12` |
| tolérance `1e-4` | `+18,05` |
| dose `l2` | `+11,31` |
| **`--king-patterns`** | **`< +8,8` (borne haute)** |

## Deux instruments indépendants disent la même chose

Les deux bras viennent du **même job** (`cpx62-1156`), même corpus, même parent,
`--exact-fold`, `--lbfgs-gtol 1e-4`, tous deux arrêtés sur `PGTOL` — `653` et
`820` itérations. Leurs pertes en holdout sont **à égalité au millionième** :

```text
TIGHT  0,441695
KING   0,441699
```

Le holdout ne prédit pas la force — mesuré quatre fois dans ce projet — mais
quand il est plat **et** que la porte rend `+2,75 ± 6`, les deux instruments
concordent sur « il n'y a rien là ».

## Ce que la porte a exigé du template, et le garde qui en est sorti

La porte n'était pas jouable jusqu'ici, et **ce n'était pas un problème de
mesure** : un modèle `--king-patterns` exige un moteur compilé
`-DJASS_KING_PATTERNS`, alors que `l3-model-gate-v1.sh` ne produisait **qu'un
binaire** pour les deux bras.

`ARM_A_CMAKE_EXTRA` / `ARM_B_CMAKE_EXTRA` lèvent le blocage. Tant qu'ils sont
égaux — le cas de toutes les portes antérieures — un seul build est produit et
les deux bras le partagent, chemin inchangé.

⚠️ **Deux binaires sont un second facteur potentiel.** Le template le
**vérifie** au lieu de l'affirmer : chaque binaire doit charger son modèle *et*
**refuser celui de l'autre**. Si les deux se chargeaient des deux côtés, la
distinction annoncée ne serait pas dans les artefacts et la porte mesurerait une
seule géométrie sous deux binaires — un second facteur gratuit. Le garde a tiré
correctement sur ce run :

```text
builds PAR BRAS : A [-DJASS_KING_PATTERNS=ON] · B []
distinction par bras ✓ (chaque binaire refuse le modèle de l'autre)
```

Le refus vient du chargeur lui-même (`scan_eval.cpp`), qui compare le bit king
de l'en-tête auto-descriptif au `KING_AWARE_PATTERNS` du build.

## ⚠️ Ce que ce verdict n'établit pas

- **Il porte sur la recette du 2 août** (`warm`, `l2 = 3e-5`), pas sur L2LOW.
  Les deux bras sont appariés entre eux, donc le facteur est propre ; mais si
  quelqu'un voulait rouvrir, il faudrait rejouer sur la recette courante.
- **Il ne dit rien de Scan**, chez qui l'occupation king-aware coexiste avec une
  géométrie et une recherche entièrement différentes. Que ça ne paie pas ici ne
  dit pas que ça ne paie pas là-bas.
- **Il ne dit rien de `32cf`** ni d'aucune autre géométrie.

## Conséquence

⛔ **Ne pas rejouer `--king-patterns` sur la géométrie 8cf** sans un argument
neuf. La condition de réouverture de `0409` est consommée : la porte a été
jouée, au scale, à un facteur, avec la puissance nécessaire pour borner l'effet
sous tout gain déjà encaissé.

✅ Le verdict **débloque `--hier-l2`** (backlog §3.1), dont le dépôt attendait ce
résultat.

## Trace

- porte : `r2:jass-data/runs/cpx62-1172-l3-king-patterns-gate-v1`
- refit deux bras : `r2:jass-data/runs/cpx62-1156-l3-king-patterns-refit-v2/20260802T123526Z-9bb0f63d`
- pool de 3000 ouvertures : `r2:jass-data/runs/cpx62-1154-l3-big-opening-pool-v1/20260802T120251Z-9b57e0aa`
