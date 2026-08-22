# CURRICULUM — écran conditionnel discovery-only après 1486

Le global residual atlas 1486 est fermé : sa direction n'a pas répliqué sur le
confirm scellé. Ce confirm est désormais consommé et ne peut être consulté par
une nouvelle sélection.

L'écran conditionnel ouvre uniquement les 195 paires du split discovery,
dont 160 erreurs restent exactes et informatives après les reclassifications
scellées par 1486. Il retire ensuite les paires forcées, à orientation exacte
négative ou dont erreur et contrôle ne partagent pas le même stratum
phase×présence-de-rois×capture. Les paires, openings et transpositions exactes
restent atomiques dans un split interne 75/25.

La famille d'hypothèses est fixée avant calcul : global, phase, tactique,
présence de rois, phase×tactique, phase×rois et le stratum complet. La direction
de chaque hypothèse est construite seulement sur inner-fit. Inner-validation
ne sert qu'à décider si la dépense d'une nouvelle campagne est justifiée.
La géométrie PatternEval n'est jamais supposée par le script : le wrapper lui
transmet le `TOTAL_BUCKETS` relu dans le `patterns.py` 8cf produit et authentifié.

Même positif, cet écran n'autorise aucun refit. Il scelle une seule population
et une seule direction qui doivent ensuite être confirmées par une campagne
entièrement fraîche de pertes CURRICULUM, sans overlap opening ou état exact, avec contrôles appariés,
IC95, permutation et réplication des coordonnées préenregistrés.

Aucun modèle, self-play, partie de force, frozen ou promotion n'est produit par
cet écran.
