# L3-PURE — renforcement direct C0 A-G3 vs P1-0842 G4

## Motif

M0 a produit un triangle non transitif : P1 semblait meilleur contre Gen2, mais perdait directement contre C0. Le parent généraliste reste donc non résolu.

Ce job ne répète pas le triangle. Il augmente uniquement la puissance statistique de la confrontation qui départage effectivement les deux parents.

## Sources immuables

- C0 A-G3 : `ccx33-0790-l3-pure-c0-a-v1`
- P1-0842 G4 : `cpx62-0842-l3-p1-frozen-v1`
- même binaire 8cf pour les deux modèles ;
- aucune modification de modèle, aucun fit et aucun autojeu.

## Ouvertures

M0 utilisait les 305 positions nettoyées de `data/dilf_combinations.fen`.
Le renforcement génère 768 positions synthétiques, légales, calmes et
uniques par trajectoires aléatoires déterministes depuis la position initiale
(`seed=271828`, plies 8–32, au moins 20 pièces). Le runner prouve l'absence de
recouvrement exact avec DILF et publie le hash et le manifeste du pool.

Chaque vue comprend 768 paires color-swapped, soit 1 536 parties. Les deux vues primaires totalisent 3 072 parties.

## Vues primaires

1. Q00 commun à profondeur 9 ;
2. Q00 commun à 0,3 seconde par coup.

P1 est toujours le bras A dans les rapports. Les deux camps utilisent exactement les mêmes 63 paramètres Q00 dans chaque vue.

## Décision

Un parent n’est recommandé que si :

- les deux estimations ponctuelles sont du même côté de 50 % ;
- l’intervalle combiné franchit 50 % avec une marge pratique de 0,5 point ;
- chaque vue contient au moins 1 000 parties complètes.

Sinon : `M0_DIRECT_REINFORCEMENT_PARENT_UNRESOLVED`.

Même avec un parent recommandé :

```text
m1_authorized=false
promotion_authorized=false
automatic_next_job=null
```

La décision reste soumise à revue humaine.
