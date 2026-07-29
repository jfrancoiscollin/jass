# L3-PURE — porte de promotion TOPK3

Date : 2026-07-29  
Verdict autoritatif : `TOPK3_PROMOTION_NOT_RECOMMENDED_POINT_ESTIMATE`  
Champion conservé : `TURNOVER`

## Contrat

La porte `home-1040-l3-pure-topk3-promotion-gate-v5` compare le modèle TOPK3
au champion TURNOVER sur un pool frais et disjoint :

- 2 500 ouvertures appariées, deux couleurs ;
- Q00 profondeur 9 et natif 0,1 seconde par coup ;
- 10 000 parties primaires au total ;
- gardes Gen2 sur 750 ouvertures par vue et par bras, soit 6 000 parties ;
- conversion P3/P4, 300 positions par strate et par bras, contre les poids
  Gen2 historiques exécutés par le moteur réparé `9c1d1e8e…`.

La règle primaire autorisée par l'utilisateur exigeait le point estimé agrégé
strictement supérieur à `0,5`. Les IC90/IC95 restaient publiés ; une vue ou une
garde ne bloquait que sur régression établie à IC90. La conversion exigeait
`>= 0,95` pour TOPK3 et un delta `>= -0,02` face à TURNOVER.

Modèles authentifiés :

- TOPK3 :
  `3399beb1a4bffca9d363890acc9346bb49c57ff1448ecdaac424290ec4f6aa61` ;
- TURNOVER :
  `b2c79b3617c41087191fee04d9aee0e1929ea63ad621c2efeaebc14ae53a7c16`.

## Force primaire

| Vue | W-D-L TOPK3 | n | Score | Elo | IC90 score |
|---|---:|---:|---:|---:|---:|
| Q00 d9 | 2251-214-2535 | 5 000 | 0,4716 | -19,76 | [0,460240 ; 0,482960] |
| Natif 0,1 s | 2245-235-2520 | 5 000 | 0,4725 | -19,13 | [0,461164 ; 0,483836] |
| **Additionné** | **4496-449-5055** | **10 000** | **0,47205** | **-19,44** | **[0,464026 ; 0,480074]** |

Le point estimé est sous `0,5` dans les deux vues. Leur IC90 supérieur reste
également sous `0,5` : la régression face à TURNOVER est établie séparément
dans Q00 et en natif.

## Gardes

Contre Gen2, TOPK3 reste fort :

| Bras | W-D-L additionné | n | Score | Elo | IC90 score |
|---|---:|---:|---:|---:|---:|
| TOPK3 | 1663-146-1191 | 3 000 | 0,578667 | +55,12 | [0,564213 ; 0,593120] |
| TURNOVER | 1721-144-1135 | 3 000 | 0,597667 | +68,75 | [0,583313 ; 0,612021] |

Le delta TOPK3 moins TURNOVER vaut `-0,019`, IC90 conservateur
`[-0,039370 ; 0,001370]`. TOPK3 ne régresse donc pas de façon établie sous
la parité contre Gen2, mais il n'améliore pas le champion.

Conversion contre le défenseur historique réparé :

| Strate | TOPK3 | TURNOVER | Delta |
|---|---:|---:|---:|
| P3 mince | 0,763333 | 0,763333 | 0 |
| P4 égal | 0,743333 | 0,760000 | -0,016667 |

Le delta matériel P4 reste dans la tolérance, mais les deux bras sont sous le
plancher absolu préenregistré de `0,95`. Cette garde est donc rouge sans
attribuer le niveau absolu faible au seul TOPK3.

## Incidents supersédés

- `home-1028` a produit les six cellules de force, puis a échoué sur la
  conversion avec un défenseur antérieur au correctif des racines nulles :
  aucune sortie partielle n'est réutilisée ;
- `home-1033`, `home-1036` et `home-1037` ont échoué avant science. La cause
  de bootstrap a été établie par `home-1039` :
  `JASS_CONTROL_REPO_DIR` n'est pas exporté par le runner HOME actuel ;
- `home-1040` utilise le checkout documenté `/srv/jass/control`, reconstruit
  déterministement le pool d'exclusion de `1028`, puis rejoue toutes les
  cellules.

Résultat autoritatif :

`r2:jass-data/runs/home-1040-l3-pure-topk3-promotion-gate-v5/20260729T032218Z-9ba51abe`

## Décision

TOPK3 n'est pas baké. TURNOVER reste le champion général et le parent de la
suite L3-PURE. Le travail « qualité du signal » reprend avec le préflight
hard-replay `home-1042`, sur le bras historique UNIFORM authentifié de `1017`.
Ce préflight ne fait ni entraînement ni promotion et doit démontrer une
capacité exacte de 1 000 000 de records avant tout fit.

```json
{
  "promotion_authorized": false,
  "automatic_next_job": null
}
```
