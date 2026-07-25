# L3 — sémantique interne Scan/Jass (0959, préenregistré)

## Preuve de départ

0957 a certifié l’égalité statique Scan/Jass sur 600/600 positions, mais Scan
natif d10/d12 convertit 100 % des deux jauges tandis que les mêmes poids dans
Jass restent autour de 38–43 %. 0958 a ensuite testé les grandes familles de
recherche Jass/Scan. Aucun bras n’a produit un gain apparié robuste :

- Q00 d10 : 41,67 % / 37,33 % ;
- `SCAN_LMR` d10 : 33,67 % / 36,67 % ;
- `FULL_WIDTH` d10 : 40,33 % / 39,00 %.

Le meilleur taux de correspondance avec le coup racine Scan n’atteint que
72,92 % à d12. Le verdict préenregistré de 0958 est donc
`MISSING_SCAN_SEARCH_MECHANISM_OR_DEPTH_SEMANTICS`.

## Écarts source-à-source encore absents

Deux mécanismes précis restent non identiques :

1. **Verification pruning Scan.** Sur un nœud non-PV de profondeur au moins
   trois, Scan recherche le même nœud à 40 % de profondeur, avec une fenêtre
   `beta + 10 × depth`. Un fail-high vérifié coupe après retrait de la marge.
2. **Réentrée sous menace.** À la première feuille calme sous menace, Scan
   réentre dans la recherche principale sur le même nœud à profondeur 1 et
   `ply+1`. Le port Jass existant énumère les réponses dans la quiescence ;
   cela n’est pas strictement équivalent pour la TT, les fenêtres et les
   extensions.

Les deux mécanismes sont ajoutés derrière des options désactivées par défaut.

## Matrice causale

Les poids Scan exacts, le défenseur Gen2 Q00 d10, les 300 + 300 positions
corrigées et les 48 sentinelles de 0958 restent immuables.

| Bras | Intervention cumulative |
|---|---|
| `SCAN_CORE` | bras `SCAN_LMR` de 0958, sans les deux nouveaux mécanismes |
| `SCAN_VERIFY` | ajoute le verification pruning exact |
| `SCAN_VERIFY_THREAT` | remplace aussi l’émulation de menace par la réentrée exacte |

La conversion complète est mesurée à d10 et d12. Les mêmes racines sont
rejouées à d8/d10/d12 contre Scan natif avec compteurs passifs : nombre de
probes de vérification, cutoffs vérifiés et réentrées sous menace.

## Règle de décision

1. Borne basse Wilson 95 % ≥ 80 % sur les deux strates :
   `SCAN_NODE_SEMANTICS_RECOVERS_CONVERSION`.
2. Sinon, gain apparié ≥ 10 points avec IC95 strictement positif sur les deux
   strates :
   - `SCAN_VERIFICATION_PRUNING_DOMINANT`, ou
   - `SCAN_THREAT_NODE_SEMANTICS_DOMINANT`.
3. Sinon : `SCAN_INTERNAL_NODE_SEMANTICS_REQUIRED`. La suite instrumentera
   Scan natif à l’intérieur de l’arbre (bornes TT, fenêtres et retours
   terminaux) avant toute nouvelle intervention.

## Garde-fous

- HOME uniquement.
- Aucune donnée d’entraînement.
- Aucune promotion ni continuation automatique.
- Poids, jauges, Scan, sources et résultats 0958 gelés par SHA/préfixe.
- `artefacts/` et `metadata.json` locaux préservés.
