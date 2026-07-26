# L3-PURE — facteur de distribution d10/d12 à volume constant

Date de préenregistrement : 26 juillet 2026, avant le résultat du bras d12
`home-0973` et avant toute partie de son évaluation `home-0974`.

## Déclencheur strict

Ce bras n'est autorisé que si l'évaluation indépendante
`home-0974-l3-pure-d12-causal-independent-eval-v1` :

- termine sans incident et avec tous ses garde-fous valides ;
- conclut `D12_PLATEAU_OR_REGRESSION_REVIEW` ;
- recommande explicitement d'arrêter l'escalade de profondeur unique et de
  tester le facteur de distribution.

Un résultat d12 positif, directionnel ou non interprétable interdit ce bras et
route respectivement vers une confirmation ou un diagnostic.

## Question causale

À parent, architecture, recherche, objectif, volume, split et optimisation
constants, remplacer un corpus monoprofondeur par une distribution
**5/6 d10 + 1/6 d12** crée-t-il une pente de force reproductible ?

Le ratio 5:1 vient de l'ancienne hypothèse Scan-style : d10 conserve le volume
et la décisivité, tandis qu'une minorité d12 enrichit les trajectoires plus
précises. Ce ratio est une hypothèse à tester, pas un résultat acquis.

| Facteur | contrôles purs | bras MIX |
|---|---:|---:|
| parent et warm-start | F2M | F2M |
| positions de fit | 2 000 000 | 2 000 000 |
| d10 | 2M dans D10 | 1 666 667 |
| d12 | 2M dans D12 | 333 333 |
| architecture | 8cf | 8cf |
| recherche | Q00 | Q00 |
| objectif | WDL terminal pur | WDL terminal pur |
| split | JSM par ouverture | identique |
| fit | L-BFGS, L2 3e-5 | identique |

Les deux sources certifiées viennent du même parent F2M et des mêmes seeds de
producteurs. `tools/selfplay_frontier.py mix` effectue un échantillonnage exact,
uniforme et déterministe (`seed=271828`), conserve l'alignement JNNW/JSM et
préserve les identifiants d'ouverture communs entre d10 et d12. Le split
ultérieur place donc toutes les occurrences d'une même ouverture dans le même
fold, même si elles viennent de profondeurs différentes. Les identifiants de
partie sont, eux, renommés par source.

Sont interdits dans ce bras : nouvelle génération, augmentation de volume,
replay historique, fenêtre glissante, oracle, teacher, TOP3, reweight V2,
changement de géométrie, changement de régularisation et mélange avec
L3-IMBALANCE2.

## Exécution réservée

Si et seulement si le déclencheur est satisfait :

1. `home-0975-l3-pure-d10-d12-mix5to1-train-v1` authentifie les résultats
   complets d10 et d12, reconstruit exactement le mix 2M, vérifie les SHA et le
   recouvrement des identifiants d'ouverture, puis fitte depuis F2M ;
2. le job archive les deux sidecars sources, le manifeste du mix, le split, le
   rapport optimiseur, la loss holdout, la RAM et le modèle ;
3. `home-0976-l3-pure-d10-d12-mix5to1-independent-eval-v1` utilise un nouveau
   pool indépendant et compare MIX à D10, D12, F2M et Gen2 dans les vues Q00
   d9 et native, puis répète conversion P3/P4 à défenseur fixe et couverture.

Le test primaire est MIX contre les deux bras purs D10 et D12. Une conclusion
forte demande une borne basse à 95 % au-dessus de 50 % contre les deux contrôles
dans les deux vues, sans régression des garde-fous. Un signal directionnel
demande une confirmation indépendante. Un nouveau plateau ferme le facteur
profondeur/distribution ; le facteur suivant devra être préenregistré
séparément (replay/turnover ou volume), jamais ajouté à ce bras.

Aucune promotion ni continuation n'est automatique.
