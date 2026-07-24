# L3-PURE M0 — revue du parent M1

Date : 24 juillet 2026.

## Sources

- triangle certifié : `home-0934-finalize-m0-triangle-v2` ;
- couverture : `home-0935-l3-pure-m0-coverage-v3` ;
- candidat C0 : `ccx33-0790-l3-pure-c0-a-v1`, G3 ;
- candidat P1 : `cpx62-0842-l3-p1-frozen-v1`, G4.

## Lecture

| Vue | C0 vs Gen2 | P1 vs Gen2 | P1 vs C0 |
|---|---:|---:|---:|
| historique d9 | 0,4992 | 0,5150 | 0,4900 |
| Q00 commun d9 | 0,5167 | 0,5183 | 0,4975 |
| native 0,3 s | 0,5100 | 0,5100 | 0,4675 |

La règle automatique ne tranche pas, car l’IC95 natif direct de P1 contre C0
est `[0,4276 ; 0,5074]`. La revue humaine est toutefois requise par le verdict
et retient C0 : P1 n’est supérieur dans aucune confrontation directe, les deux
parents sont identiques contre Gen2 dans la vue primaire et l’avantage de
couverture P1 (`10,06 %` contre `9,48 %`) est faible et purement diagnostique.

Le choix C0 permet en outre un bras replay exact : les corpus G1–G3 constituent
les 1,5 million de records historiques préenregistrés. Tous les bras M1
généreront sous Q00 complet ; le fingerprint historique partiel de C0 n’est pas
prolongé.

## Décision

```text
M1_PARENT=C0_A_G3
M1_PARENT_JOB=ccx33-0790-l3-pure-c0-a-v1
M1_PARENT_ARTIFACT=g3.pjtw.gz
M1_SCREEN_AUTHORIZED=true
PROMOTION_AUTHORIZED=false
AUTOMATIC_NEXT_JOB=null
```
