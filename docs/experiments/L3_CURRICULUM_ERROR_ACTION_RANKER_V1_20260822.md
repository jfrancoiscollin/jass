# L3 — correcteur d’action appris sur erreurs fraîches de CURRICULUM

Date : 22 août 2026

Statut : protocole séquentiel préenregistré ; aucune règle de production ni promotion

## Motivation

Les atlas 1486/1487 et 1489 ferment le refit local de PatternEval : ni une
direction PJTW globale, ni une direction conditionnelle phase/rois/tactique ne
se réplique. Le screen 1490 ferme également l’extrapolation fixe de la pente
des scores racine d8→d9 : les douze règles aggravent fortement le regret.

La prochaine hypothèse est différente. CURRICULUM reste byte-identique et son
score d9 reste l’ancre. Un petit ranker apprend seulement, au niveau des coups
légaux d’une même racine, si la trajectoire complète d6–d9 contient une
correction résiduelle reproductible. Aucun coefficient PatternEval n’est
modifié et le moteur doit rester strictement inchangé lorsque le ranker
s’abstient.

## Source fraîche

La première étape rejoue CURRICULUM contre lui-même sur deux pools de 384
ouvertures, couleurs appariées, native 0,1 s, soit 1 536 parties intégralement
dumpées. Les seeds sont nouveaux et les deux pools sont certifiés disjoints des
pools 1468, 1454 et 1464. Toutes les décisions, et pas seulement les défaites,
sont scellées par composantes `opening_id ↔ exact_state` avant tout calcul de
regret. Le même champion byte-identique sert de teacher d10 et de juge d12.

Le mode `ACTION_SOURCE_ONLY=1` publie sélection, transitions et seize shards de
regret, mais interdit explicitement l’agrégation des buckets PatternEval. Il ne
fait aucun fit, aucune partie de force, aucun frozen et aucune promotion.

## Écran ranker conditionnel

Une PR séparée, figée avant lecture de cette source, doit :

1. apparier sans remise erreurs ≥50 cp et contrôles ≤10 cp dans des ouvertures
   distinctes ;
2. recalculer les traces racine d6–d9 et juger exactement tous les coups sous
   la symétrie `rot180 + colour-swap` ;
3. ajuster sur `discovery` seulement un ridge pairwise résiduel fortement
   régularisé, avec features et caps préenregistrés ;
4. sélectionner seuil d’intervention et régularisation uniquement dans un
   inner-fit, puis évaluer une seule configuration sur inner-validation ;
5. ne lire `confirm` que si tous les gates internes passent ;
6. battre des contrôles sham à cibles permutées et ne pas dégrader les
   contrôles appariés.

Un PASS OOF autorise seulement l’implémentation bornée du ranker dans la
recherche et une validation hors échantillon. Les deux gates de force frais ne
sont autorisés qu’après cette validation. Aucun résultat ne promeut
automatiquement le modèle.
