# CTX2 — census d'activation et attribution des paramètres de self-play

Date : 2026-08-17
Statut : protocole préenregistré avant lecture du census.

## Question

Le self-play fournit-il effectivement des positions qui activent chacun des
éléments de `CTX2_PHASE_TACTICAL_30`, et avec quelle fréquence ? Quels réglages
de génération déplacent sélectivement cette couverture ?

Une dimension CTX2 brute est le produit d'un signal de plateau par un poids de
phase. Un zéro brut est donc ambigu : le signal peut être absent, ou sa banque
de phase peut simplement avoir un poids nul. Le census rapporte deux niveaux :

- les 30 canaux bruts (`tempo_mid_*` et `tempo_end_*`) réellement donnés au
  mapper conditionnel ;
- les 15 signaux sous-jacents, reconstruits exactement par
  `base = tempo_mid + tempo_end`.

## Population du census

Source immuable : le flux général UNIFORM de 40 M de positions du job
`home-1044-l3-pure-hard-replay-large-source-v1`, tentative
`20260729T070032Z-477da64d`. Il s'agit de self-play général post-correctif,
ouvertures appariées, RNG séparés, parent TURNOVER, recherche d8 / label d4,
`random-open-plies=8`, `explore-eps=8`, décroissance à 60 plies, sans TOPK ni
teacher externe.

L'échantillon est choisi avant toute lecture du contexte : les 50 000
`opening_id` aux plus petits hashes SplitMix64, seed `2026081701`, avec les deux
parties couleur inversée de chaque ouverture. Il contient donc exactement
100 000 parties complètes. Aucune position isolée n'est échantillonnée.

## Mesures

Pour chaque canal brut et chaque signal de base :

- pourcentage et compte de positions actives, au seuil exact et au seuil
  matériel `|x| > 1e-6` ;
- pourcentage de parties contenant au moins une activation ;
- fréquences positive et négative ;
- moyenne absolue, RMS, extrema et quantiles des valeurs actives ;
- prévalence par strate fixe de phase tempo ;
- canaux morts et rares (`< 0,1 %` des positions).

Le rapport publie aussi le rang effectif, les corrélations et l'erreur maximale
de recomposition `mid = wmg × base`, `end = (1-wmg) × base`. Une erreur de
recomposition supérieure à `1e-5` invalide le résultat.

Le verdict `JASS_CONTEXT2_ACTIVATION_CENSUS100K_READY` certifie uniquement que
la mesure est complète et reproductible. Il ne signifie ni que la fréquence
optimale est connue, ni que davantage d'activation améliore la cible ou la
force.

## Étape suivante : attribution causale des paramètres

Après audit du census, une sonde appariée garde le champion CURRICULUM, le
binaire, les budgets, les graines d'ouverture et le volume de positions fixes.
Une seule variable change par cellule :

| cellule | différence contre BASE | mécanisme principalement sondé |
|---|---|---|
| BASEBIS | autre graine | bruit graine-à-graine |
| ROP16 | `random-open-plies 8 → 16` | diversité d'ouverture / centre / ailes |
| EPS16 | `explore-eps 8 → 16` | largeur d'exploration globale |
| DECAY120 | décroissance `60 → 120` | exploration plus tardive |
| NODECAY | décroissance désactivée | borne haute, avec garde de distribution |
| TOPK3M30 | top-3, marge 30 | diversité locale près du meilleur coup |
| DEPTH10 | profondeur de jeu `8 → 10` | qualité tactique de trajectoire |

Toutes les cellules utilisent `--split-selfplay-rngs` et les mêmes graines que
BASE ; BASEBIS estime le bruit. Pour chaque couple paramètre × signal, on
rapporte le déplacement en points de pourcentage de la fréquence d'activation,
le changement d'intensité et sa taille relative au bruit BASE/BASEBIS.

Cette matrice est diagnostique. Une cellule qui active davantage un signal ne
peut être retenue qu'après gardes WDL, taux de nulles et diversité, puis un test
d'apprentissage séparé. Aucune force, promotion ou continuation automatique ne
fait partie du census.
