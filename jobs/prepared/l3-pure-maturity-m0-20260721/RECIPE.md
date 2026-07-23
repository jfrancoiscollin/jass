# L3-PURE-MATURITY — recette M0

## Sources immuables

- C0 pur A-G3 : `ccx33-0790-l3-pure-c0-a-v1`
- baseline propre P1 G4 : `cpx62-0842-l3-p1-frozen-v1`
- champion historique : `gen2-mmto`, bundle T1-bis figé

## Job couverture

`cpx62-l3-pure-m0-coverage` mesure C0 G1–G3 et P1 G1–G4, séparément et en cumul : couverture non nulle, seuils de visites et concentration. Cette mesure est diagnostique et ne choisit pas seule le parent.

## Job triangle

`cpx62-l3-pure-m0-triangle` joue les trois confrontations C0/Gen2, P1/Gen2 et P1/C0 sur 300 ouvertures appariées, dans trois vues : protocole historique d9, Q00 commun d9 et fingerprints de lignée à 0,3 seconde par coup.

## Restitution

Chaque job publie dans R2 les rapports complets, les sources vérifiées, les logs, `RESULTS.txt` et `JASS_CONTROL_SUMMARY.json`. Des fichiers-marqueurs rendent le verdict et les métriques principales lisibles dans `jass-control`.

## Étape M1

Les bras futurs restent `F500`, `F2M` et `R2M`. Aucun wrapper M1 n’est créé avant la completion de M0, la sélection humaine du parent et une PR séparée.

```text
m1_authorized=false
promotion_authorized=false
automatic_next_job=null
```

## Portage HOME

Les wrappers `home-0929` et `home-0930` conservent les sources, les 300
ouvertures, les trois vues et les budgets scientifiques de M0. Le triangle
réduit seulement la concurrence à six shards (`PAR_GATE=2` pour chacun des
trois matches) et la compilation à `-j4`, soit au plus douze moteurs simultanés
sur les seize CPU HOME. Les hard caps sont de 90 minutes pour la couverture et
de huit heures pour le triangle.
