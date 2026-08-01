# EXACT — promotion au rang de champion général

Enregistrement immuable. Promotion décidée par revue humaine de JFC le
1er août 2026, après la porte `cpx62-1129`.

## Identités

```text
nouveau champion  EXACT     d84a7fc7c3127d135d3cc150406055b9506daaa881af2959cd3721f6be66eb0a
                  r2:jass-data/runs/cpx62-1117-l3-exact-fold-refit-v1/
                     20260731T235446Z-970f14de/artefacts/exact.pjtw.gz

champion précédent TURNOVER b2c79b3617c41087191fee04d9aee0e1929ea63ad621c2efeaebc14ae53a7c16
                  r2:jass-data/runs/home-0977-l3-pure-turnover1to1-train-v1/
                     20260726T071254Z-336bb984/artefacts/turnover1to1.pjtw.gz

référence figée   GEN2 (gen2-mmto), inchangée, garde-fou historique externe
```

Les empreintes sont celles du `.pjtw` **décompressé**, comme pour F2M et
TURNOVER.

## Comment EXACT a été construit

**Aucune donnée neuve, aucune capacité neuve.** EXACT est un refit du même
corpus que TURNOVER, sous la même recette, avec un seul changement : la
contrainte de symétrie imposée au fit.

La seule symétrie exacte du damier est **`rot180 ∘ colour-swap`**. Jusqu'au
1er août la campagne fittait sous `--color-fold`, c'est-à-dire qu'elle imposait
**`cs` seule**, qui n'est pas une symétrie — les pions ont une direction. Le
modèle obéissait donc exactement (`0,0000 %`) à une contrainte fausse pendant
que la vraie était violée à **25,8 %**. `--exact-fold` échange l'une contre
l'autre.

Ce n'est **pas** un gain de capacité : les deux folds donnent le même
`TB ≈ 2,13 M`. Seul change **ce qui est mutualisé** entre buckets.

La réflexion gauche-droite, elle, n'est pas non plus une symétrie, contrairement
à ce qu'affirmait le docstring de `symmetry.py` : un miroir L-D envoie les cases
sombres sur les claires et **casse 36 des 81 adjacences diagonales**. Un fold LR
avait été construit sur cette affirmation ; il a été tué en vol après une
question de JFC, et le critère est désormais épinglé par un test
(`pattern_jass/tools/test_symmetry_geometry.py`) : *toute transformation pliée
doit préserver l'adjacence diagonale*. Le fold exact épuise donc le sujet.

## Preuve de force

Porte `cpx62-1129`, pool `home-1004` (1500 ouvertures), estimateur à vues
**additionnées** (compteurs bruts sommés), `n=6000`, **base de finales EGDB
présente** :

| vue | n | score | Elo | IC95 du taux |
|---|---:|---:|---:|---|
| `q00` (profondeur 9 fixe) | 3000 | 52,60 % | +18,08 | `[50,87 ; 54,33]` |
| `native` (movetime 0,1) | 3000 | 51,75 % | +12,17 | `[50,01 ; 53,49]` |
| **sommé** | **6000** | **52,175 %** | **+15,12** | `[50,95 ; 53,40]` |

`2964W 333D 2703L`. Les deux vues concordent (`0,85 pp`) et **les deux bornes
basses sont au-dessus de 50 %**.

Les trois mesures de la campagne fold sont cohérentes entre elles :

```text
cpx62-1118  EXACT vs CONTROL (son propre contrôle)  n=6000  +17,10  IC95 [+9,2 ; +25,0]
cpx62-1121  EXACT vs TURNOVER, SANS EGDB            n=6000  +13,32  IC95 [+5,5 ; +21,2]
cpx62-1129  EXACT vs TURNOVER, AVEC EGDB            n=6000  +15,12  IC95 [+6,6 ; +23,7]
```

L'objection qui bloquait la succession est levée : le gain n'était pas un
artefact du réglage sans tablebase.

## Ce que cette promotion n'établit pas

À borner explicitement, pour que le résultat ne soit pas sur-cité plus tard.
**Cette promotion est moins garnie que celle de TURNOVER**, qui exigeait cinq
garde-fous sur cinq. Ce qui manque, nommément :

- **Aucune garde Gen2.** EXACT n'a pas été mesuré contre `gen2-mmto`. Rien
  n'exclut une régression contre la référence historique figée.
- **Aucune cellule de conversion P3/P4.** Le plancher de conversion à défenseur
  figé n'a pas été rejoué.
- **Un seul pool.** `1121` et `1129` partagent le pool `home-1004` ; ils
  diffèrent par la présence d'EGDB, pas par les ouvertures. Il n'y a donc pas de
  consolidation multi-pools comme les quatre pools de TURNOVER.
- **Aucune couverture par bucket recomptée.** Le fold change ce qui est
  mutualisé, donc l'ancien chiffre de couverture ne se transporte pas tel quel.
- **Rien sur Scan.** Le déficit connu de la lignée au movetime n'est pas adressé.
- **Rien au-delà de d8 ni hors 8cf.**

Ces cellules restent jouables après coup : elles confirmeraient ou infirmeraient
la promotion sans rien avoir à re-générer.

## Conséquence pour la suite

**Tout nouveau fit L3 doit utiliser `--exact-fold`.** Un fit sous `--color-fold`
repart de la contrainte fausse et perd le gain.

## Réversibilité

La promotion est **purement documentaire**, conformément aux précédents F2M
(`3db4506f`) et TURNOVER (`54c9dc39`). Aucun artefact de l'object store n'est
modifié ; TURNOVER reste immuable sous son préfixe daté et restaurable. Un
`git revert` du commit de bake restaure intégralement l'état antérieur.

## Trace

- porte de succession avec EGDB : `r2:jass-data/runs/cpx62-1129-l3-exact-vs-turnover-gate-egdb-v1/20260801T081526Z-0b43c61f`
- porte sans EGDB : `r2:jass-data/runs/cpx62-1121-l3-exact-vs-turnover-gate-v1`
- refit deux bras (CONTROL / EXACT) : `r2:jass-data/runs/cpx62-1117-l3-exact-fold-refit-v1/20260731T235446Z-970f14de`
- pose de la base de finales sur cpx62 : `r2:jass-data/runs/cpx62-1128-install-egdb-wld-v1/20260801T075929Z-f0e0c976`
- analyse du fold : [`L3_EXACT_FOLD_20260801.md`](L3_EXACT_FOLD_20260801.md)
