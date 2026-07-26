# L3-PURE — confirmation indépendante du turnover temporel 1:1

Date de préenregistrement : 26 juillet 2026, après lecture complète de
`home-0978` et avant toute partie du pool de confirmation.

## Résultat déclencheur

Le candidat TURNOVER est le modèle immuable produit par `home-0977` :

- parent et warm-start : F2M ;
- corpus : 1 000 000 positions de l’époque F2M + 1 000 000 positions fraîches
  M2 d8 ;
- modèle SHA-256 :
  `b2c79b3617c41087191fee04d9aee0e1929ea63ad621c2efeaebc14ae53a7c16` ;
- corpus SHA-256 :
  `9b7db67a87025baf9115c72512312ac13ace076cef700c54ff1862f4ab240a2d` ;
- sidecar JSM SHA-256 :
  `acf3bbf4a28e7b44a1077df06bca9658cd4b189fc4cf11ee7f56720661626682`.

`home-0978` a terminé sans incident scientifique et avec tous les garde-fous
verts :

| adversaire | Q00 d9 | cadence native |
|---|---:|---:|
| M2 frais d8 | 52,20 %, +15,3 Elo | 51,05 %, +7,3 Elo |
| F2M | 52,10 %, +14,6 Elo | 51,15 %, +8,0 Elo |

Les quatre estimations sont positives, mais aucune borne basse à 95 % ne
dépasse 50 %. Le verdict autoritaire est donc
`TURNOVER_DIRECTIONAL_CONFIRMATION_REVIEW`, et non une preuve ni une
promotion.

La conversion corrigée reste à 98 % sur P3 et 99 % sur P4. La couverture du
corpus TURNOVER atteint 210 381 buckets visités et 28 160 buckets vus au moins
100 fois, au-dessus de M2 et F2M. Ces diagnostics sont déjà déterministes pour
le modèle et ne sont pas rejoués.

## Test de confirmation

`home-0979-l3-pure-turnover-confirmation-v1` ne réentraîne rien et ne modifie
aucun paramètre. Il rejoue uniquement quatre cellules de force :

- TURNOVER contre M2, Q00 d9 ;
- TURNOVER contre M2, cadence native 0,1 s ;
- TURNOVER contre F2M, Q00 d9 ;
- TURNOVER contre F2M, cadence native 0,1 s.

Chaque cellule utilise 1 000 nouvelles ouvertures avec couleurs appariées, soit
2 000 parties par cellule. Les résultats sont ensuite additionnés aux
1 000 parties par cellule de `home-0978`, pour un readout consolidé de
3 000 parties par cellule.

Le nouveau pool est déterministe :

- seed : `11235813` ;
- 4 000 candidats ;
- SHA-256 candidats :
  `c440f5a6818aee4b226ceb968fa2753b2d2d71b6257d9a335c1f2e96efb5a51a` ;
- SHA-256 des 1 000 ouvertures retenues :
  `c34f25f0dddf8865e90a4f149bcca0f4b40ccb32d0b5e1aff5fde6a604e92251`.

Deux reconstructions de preflight sont bit-identiques. Le pool contient
1 000 lignes uniques et zéro recouvrement avec DILF, les pools historiques
renforcement/méta/F2M, les pools indépendants M2/d10/d12 et le premier pool
TURNOVER de `home-0978`.

## Verdicts préenregistrés

L’ordre est hiérarchique :

1. `TURNOVER_CHAMPION_CONFIRMATION_REVIEW_READY` si les quatre estimations du
   nouveau pool restent positives et si les quatre bornes basses consolidées
   à 95 % dépassent 50 % contre M2 et F2M.
2. `TURNOVER_EFFECT_CONFIRMED_HUMAN_REVIEW` si les deux vues restent positives
   contre M2 et si les deux bornes basses consolidées dépassent 50 % contre M2,
   sans régression établie contre F2M.
3. `TURNOVER_DIRECTION_REPLICATED_REVIEW` si les deux vues du nouveau pool
   restent positives contre M2, sans régression établie contre F2M, mais que la
   preuve consolidée reste insuffisante.
4. `TURNOVER_DIRECTION_NOT_REPLICATED_CLOSE_1TO1` dans tous les autres cas.

Les garde-fous statiques de `home-0978` sont transportés uniquement parce que
le modèle, le moteur et leurs SHA restent identiques. Les rapports de fetch,
le modèle et le pool sont tous vérifiés avant les matchs.

Même dans le premier cas, `promotion_authorized=false` et
`automatic_next_job=null`. Le résultat ouvre une revue humaine ; il ne
déclenche ni promotion ni génération M3 automatique.

## Sizing HOME

HOME fournit 16 CPU logiques et environ 15,6 Go de RAM. Le build est limité à
`-j4`, puis deux gates tournent en parallèle avec quatre shards actifs chacune.
Le pic attendu reste très inférieur à la RAM disponible. Le run exécute
8 000 parties, sans fit, sans couverture et sans conversion ; ETA publiée :
**40 à 55 minutes**.

## Incident d'exécution sans donnée scientifique

`home-0979` a authentifié les entrées, compilé le moteur et reconstruit le pool
au SHA attendu, puis a échoué avant la première partie : sous `set -u`, la
variable locale `opponent` était référencée dans la même déclaration Bash que
son initialisation. Les deux workers Q00 ont donc produit zéro résultat.

La correction sépare l'initialisation de `opponent` et celle de `pattern`, avec
un test de régression dédié. La relance propre porte l'identifiant
`home-0980-l3-pure-turnover-confirmation-v2`. Le modèle, le pool, les seuils et
les quatre cellules restent strictement inchangés ; aucune donnée de `0979`
n'est reprise.
