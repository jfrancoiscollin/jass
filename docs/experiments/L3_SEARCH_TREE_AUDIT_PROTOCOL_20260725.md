# L3 — audit causal de la recherche Scan/Jass (0958, préenregistré)

## Preuve de départ

Le run 0957 a porté algébriquement les poids bruts de Scan 3.1 dans Jass.
L’évaluation statique est identique sur 600/600 positions, avec un écart
maximal nul. Pourtant :

- Scan natif d10 et d12 convertit 100 % des jauges `p3_mince` et `p4_egal` ;
- Jass d10 avec ces mêmes poids convertit 41,67 % / 37,33 % ;
- Jass d12 avec ces mêmes poids convertit 42,67 % / 38,33 %.

Le volume d’entraînement et les poids ne peuvent donc pas expliquer le gap
principal. Le facteur causal restant est la recherche ou ses conventions de
profondeur/terminal.

## Différences de recherche observées dans le source Scan gelé

Scan 3.1 (`7aae17e7…`) :

1. étend automatiquement tout nœud à réponse unique ;
2. poursuit récursivement ses sacrifices sélectifs en quiescence ;
3. applique une LMR spécifique (dès d2, seuils PV/non-PV et réduction 1/2) ;
4. utilise un pruning de vérification réduit qui n’est pas le mélange
   RFP/NMP/razoring/ProbCut/MultiCut de Q00.

0958 teste ces familles sans modifier les poids.

## Matrice d’intervention

Toutes les cellules utilisent :

- les poids Scan exacts certifiés par 0957 ;
- le même défenseur Gen2 Q00 d10 ;
- les mêmes 300 + 300 positions corrigées ;
- une recherche attaquante d10 ;
- aucune table Scan et aucun oracle dans Jass.

| Bras | Intervention cumulative |
|---|---|
| `Q00` | témoin 0957 réutilisé |
| `NO_FORWARD` | désactive RFP, NMP, razoring, ProbCut et MultiCut Jass |
| `SCAN_EXT_QS` | ajoute l’extension réponse unique et les sacrifices récursifs Scan |
| `SCAN_LMR` | ajoute la forme LMR exacte de Scan 3.1 |
| `FULL_WIDTH` | supprime LMR/LMP/PVS/aspiration, conserve extension et qsearch Scan |

En parallèle, 48 sentinelles sont sélectionnées avant lecture des traces :
8 échecs et 4 contrôles gagnants par couleur avantagée et par strate. Chaque
sentinelle est analysée à d8/d10/d12 par Scan natif et les cinq bras Jass.
TT, historique et état de partie sont remis à zéro avant chaque racine.

## Règle de décision

Le readout ne promeut rien.

1. Si la borne basse Wilson 95 % d’un bras atteint 80 % sur les deux strates :
   `SEARCH_ALIGNMENT_RECOVERS_CONVERSION`.
2. Sinon, le premier bras cumulatif qui améliore Q00 d’au moins 10 points,
   avec intervalle apparié 95 % strictement positif sur les deux strates,
   localise la famille dominante :
   - `JASS_FORWARD_PRUNING_DOMINANT`
   - `SCAN_EXTENSION_QUIESCENCE_DOMINANT`
   - `SCAN_LMR_SHAPE_DOMINANT`
   - `SELECTIVE_MAIN_SEARCH_DOMINANT`
3. Sinon :
   `MISSING_SCAN_SEARCH_MECHANISM_OR_DEPTH_SEMANTICS`.
   La suite sera l’instrumentation du pruning de vérification Scan et des
   conventions de profondeur/terminal, après revue humaine.

Les taux de correspondance de coups et les PV sont des preuves explicatives ;
la décision causale repose sur la conversion appariée complète.

## Garde-fous

- HOME uniquement.
- Poids, jauges, runtime et sources gelés par SHA.
- Aucune donnée d’entraînement créée.
- Aucune promotion ou continuation automatique.
- `artefacts/` et `metadata.json` locaux préservés.
