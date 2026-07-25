# L3 — première divergence interne Scan/Jass (0960, préenregistré)

## Preuve de départ

0957 a certifié l’identité de l’évaluation statique sur 600/600 positions.
0958 n’a pas récupéré la conversion en alignant les grandes familles de
recherche. 0959 a ensuite exécuté réellement le verification pruning et la
réentrée sous menace de Scan, sans effet causal : le verdict est
`SCAN_INTERNAL_NODE_SEMANTICS_REQUIRED`.

0960 ne teste donc pas une nouvelle heuristique. Il observe les deux moteurs
sur les mêmes 48 racines afin de trouver le premier événement où leurs arbres
cessent d’être équivalents.

## Instrumentation commune

Le binaire Jass exact et une compilation diagnostique du source Scan gelé
`7aae17e7…` émettent, pour chaque tentative d’aspiration et chaque profondeur
de 1 à 12 :

- la liste et l’ordre des coups racine ;
- la fenêtre `alpha/beta` avant chaque coup ;
- le score renvoyé par le sous-arbre ;
- le meilleur score courant, le cutoff et le résultat final.

Scan est construit depuis le bundle et un patch versionné dont le SHA est
publié. L’instrumentation est passive, activée uniquement par variable
d’environnement. Jass utilise les poids Scan exacts et le bras
`SCAN_VERIFY_THREAT` de 0959. TT, historique et état de partie sont remis à
zéro entre les sentinelles.

Le raccourci natif de Scan lorsqu’un seul coup est légal est également tracé
comme une tentative synthétique à chaque profondeur. Cela rend le contrat
total sans changer la décision du moteur.

## Règle de localisation

Pour chaque racine, le readout sélectionne la dernière tentative de fenêtre
de chaque profondeur et classe le premier désaccord :

1. ensemble des coups : `ROOT_LEGAL_MOVE_IDENTITY_DIVERGENCE` ;
2. ordre des coups : `ROOT_ORDERING_SELECTIVITY_DIVERGENCE` ;
3. fenêtres : `ASPIRATION_OR_WINDOW_SEMANTICS_DIVERGENCE` ;
4. score d’un enfant : `RECURSIVE_NODE_SCORE_SEMANTICS_DIVERGENCE` ;
5. extraction du résultat : `ROOT_RESULT_EXTRACTION_DIVERGENCE`.

Si les racines restent identiques, le verdict est
`ROOT_TRACE_PARITY_INTERNAL_NODE_TRACE_REQUIRED` et la prochaine expérience
instrumentera le premier enfant récursif. Aucune correction n’est appliquée
dans 0960.

## Garde-fous

- HOME uniquement, 48 sentinelles immuables de 0958.
- Runtime, source, poids et paramètres gelés par SHA/préfixe.
- Aucun entraînement, aucune promotion, aucune continuation automatique.
- `artefacts/` et `metadata.json` locaux préservés.
