# TURNOVER — promotion au rang de champion général

Enregistrement immuable. Promotion décidée par revue humaine de JFC le
27 juillet 2026, après la porte `home-0996`.

## Identités

```text
nouveau champion  TURNOVER  b2c79b3617c41087191fee04d9aee0e1929ea63ad621c2efeaebc14ae53a7c16
                  r2:jass-data/runs/home-0977-l3-pure-turnover1to1-train-v1/
                     20260726T071254Z-336bb984/artefacts/turnover1to1.pjtw.gz

champion précédent F2M     be675b6c1c6360a0a9aa5977ed492284bc8dcc1861ee47bc2e3139046ed769f2
                  r2:jass-data/runs/home-0944-l3-pure-m1-train-resume-v3/
                     20260724T052619Z-faddc80a/artefacts/f2m.pjtw.gz

référence figée   GEN2 (gen2-mmto), inchangée, garde-fou historique externe
```

## Comment TURNOVER a été construit

Parent F2M, **2 000 000 records à volume constant** dont 1 000 000 de l'époque
F2M et 1 000 000 de l'époque M2, mix seed `141421`, identifiants d'ouverture
namespacés par source. Split par ouverture seed `577215`
(1 800 796 / 199 204). Fit L-BFGS logistic `L2=3e-5`, warm-start depuis F2M,
convergé en 204 itérations, loss holdout `0,444060`. Profondeur de jeu d8,
géométrie 8cf, fingerprint Q00 à 63 paramètres, labels WDL terminaux.

Aucun teacher, aucun oracle, aucune frontière mobile, aucun MMTO. Le seul
facteur qui distingue TURNOVER de `M2` est **la composition temporelle du
corpus**, à budget strictement identique.

## Preuve de force

Porte de succession `home-0996`, pool `eb129db1…` (1500 ouvertures, disjoint de
quinze pools), estimateur à vues additionnées, `n=6000` par matchup :

| cellule | n | score | Elo | IC95 | |
|---|---:|---:|---:|---|---|
| primaire vs F2M | 6000 | 51,98 % | +13,73 | `[50,72 ; 53,23]` | **établie** |
| garde vs Gen2 | 6000 | 58,83 % | +62,03 | `[57,60 ; 60,07]` | aucune régression |
| conversion P3 | 300 | 98,00 % | — | — | plancher OK |
| conversion P4 | 300 | 99,00 % | — | — | plancher OK |

Cinq garde-fous sur cinq. Les deux vues concordent à `0,09 pp` (Q00 `51,93 %`,
native `52,02 %`).

Consolidation sur **quatre pools indépendants**, huit mesures positives sur
huit :

```text
0978  q00 n=1000 52,10 %    native n=1000 51,15 %
0980  q00 n=2000 50,35 %    native n=2000 50,90 %
0993  q00 n=2500 52,72 %    native n=2500 51,24 %
0996  q00 n=3000 51,93 %    native n=3000 52,02 %
--------------------------------------------------------------
CUMUL n=17 000    51,62 %   8642-266-8092   +11,24 Elo
                  IC95 [50,87 ; 52,36]
SPRT  H0=0 H1=+5  LLR=+6,26 -> ACCEPT_H1
SPRT  H0=0 H1=+8  LLR=+8,30 -> ACCEPT_H1
```

`home-0993` et `home-0996` mesurent tous deux `51,98 %`, sur deux pools
disjoints et à deux tailles d'échantillon différentes.

## Ce que cette promotion n'établit pas

À borner explicitement, pour que le résultat ne soit pas sur-cité plus tard.

- **Rien sur Scan.** TURNOVER n'a pas été mesuré contre Scan. Le déficit connu
  de la lignée au movetime (`−128 à −155 Elo` pour `gen2-mmto`) n'est pas
  adressé par cette promotion. La calibration est préparée et séquencée après.
- **Rien sur la répétabilité de la recette.** TURNOVER est **une seule
  génération**. Palier ou pente reste indécidé ; c'est l'objet de G2.
- **Rien au-delà de d8 ni hors 8cf.** La profondeur est close et négative
  (d12 en régression établie) ; 32cf reste fermé faute de couverture.
- **La couverture reste le facteur limitant** : ~208 900 buckets visités sur
  2 125 768, soit ~9,8 %, et le fit tourne à ~4,3 observations par paramètre
  libre.

## Réversibilité

La promotion est **purement documentaire**, conformément au précédent de F2M
(commit `3db4506f`). Aucun artefact de l'object store n'a été modifié ; le
modèle F2M reste immuable sous son préfixe daté. Un `git revert` du commit de
bake restaure intégralement l'état antérieur.

## Trace

- porte : `r2:jass-data/runs/home-0996-l3-pure-turnover-succession-gate-v1/20260727T055721Z-e913d66d`
- préflight : `r2:jass-data/runs/home-0995-l3-pure-turnover-succession-preflight-v2/20260727T054246Z-f20e59d0`
- procédure suivie : [`L3_TURNOVER_BAKE_PROCEDURE_20260727.md`](L3_TURNOVER_BAKE_PROCEDURE_20260727.md)
