# L3-PURE — verdict du replay `failed_conversion` 50/50

Date : 2026-07-30  
Statut : axe causal exécuté et recette v1 close  
Parent : `TURNOVER` (`home-0977`), SHA256
`b2c79b3617c41087191fee04d9aee0e1929ea63ad621c2efeaebc14ae53a7c16`

## 1. Contrat exécuté

`cpx62-1068-l3-pure-hard-replay-causal-ab-v5`, tentative
`20260730T011844Z-373da817`, a produit deux fits convergés à partir du même
parent, du même million frais, du même holdout et de la même recette :

| Bras | Replay historique | Modèle SHA256 |
|---|---|---|
| `UNIFORM_REPLAY` | 1 M records uniformes | `ff75d1b34155e5c7bcd62b499c89f8168d96de0ac877ce4ed8e4ecbb8e4e1014` |
| `HARD_REPLAY` | 1 M records `failed_conversion` | `1a0487203a2039f77f7b995bdd92fab4efae12f28500000eb498d5a90e05d594` |

Chaque corpus contient 2 M records : 1 M frais commun et 1 M replay. Le
holdout commun contient 100 440 records. Le seul facteur causal est la
politique de sélection du replay historique.

Le readout indépendant autoritatif est
`home-1076-l3-pure-hard-replay-independent-readout-v2`, tentative
`20260730T040627Z-e25a30b4`, résultat :

```text
r2:jass-data/runs/home-1076-l3-pure-hard-replay-independent-readout-v2/20260730T040627Z-e25a30b4
```

Il utilise 2 500 ouvertures fraîches, uniques et disjointes, deux couleurs,
5 000 parties Q00 d9, 5 000 parties natives à 0,1 s/coup, puis les cellules
de conversion P3/P4 contre le défenseur historique corrigé. Le certificat a
été réauthentifié par `cpx62-1077` et le diagnostic des distributions par
`cpx62-1078`.

## 2. Force indépendante

Les W/D/L sont donnés du point de vue de `HARD_REPLAY`.

| Vue | W-D-L | Score | Elo | IC90 score | IC95 score |
|---|---:|---:|---:|---:|---:|
| Q00 d9 | `96-12-4892` | 0,020400 | -672,57 | [0,017161 ; 0,023639] | [0,016541 ; 0,024259] |
| native 0,1 s | `126-12-4862` | 0,026400 | -626,71 | [0,022714 ; 0,030086] | [0,022008 ; 0,030792] |
| additionnées | `222-24-9754` | **0,023400** | **-648,20** | [0,020946 ; 0,025854] | [0,020476 ; 0,026324] |

Verdict scellé :

```text
L3_PURE_HARD_REPLAY_BELOW_UNIFORM_REPLAY
```

La régression est massive et cohérente dans les deux vues. Aucune sortie
partielle des tentatives échouées précédentes n'entre dans ce résultat.

## 3. Conversion et couverture

| Strate | HARD | UNIFORM | Delta pairé HARD−UNIFORM | IC90 | IC95 |
|---|---:|---:|---:|---:|---:|
| P3 mince | 214/300 = 0,713333 | 210/300 = 0,700000 | +0,013333 | [-0,040000 ; +0,066667] | [-0,050000 ; +0,076667] |
| P4 égal | 214/300 = 0,713333 | 227/300 = 0,756667 | -0,043333 | [-0,093333 ; +0,006667] | [-0,103333 ; +0,016667] |

La conversion n'établit pas de gain. Le P4 ponctuel est défavorable, avec des
intervalles qui recouvrent encore zéro.

| Couverture | HARD | UNIFORM | Delta HARD−UNIFORM |
|---|---:|---:|---:|
| buckets visités | 210 436 | 194 334 | +16 102 |
| fraction | 0,098993 | 0,091418 | +0,007575 |
| buckets ≥10 | 89 913 | 82 639 | +7 274 |
| buckets ≥100 | 25 026 | 23 452 | +1 574 |
| Gini | 0,875122 | 0,882834 | -0,007712 |

Le replay difficile améliore donc la couverture et la concentration, mais ce
gain géométrique ne compense pas la destruction du signal de valeur.

## 4. Diagnostic du mécanisme

Les deux optimiseurs ont convergé normalement :

| Bras | Itérations | norme gradient inf | holdout logloss, diagnostic seulement |
|---|---:|---:|---:|
| UNIFORM | 392 | 0,000738 | 0,436910 |
| HARD | 619 | 0,000743 | 0,615814 |

Il ne s'agit ni d'une inversion des modèles, ni d'un défaut de chargement, ni
d'une non-convergence. Les hashes des deux modèles sont authentifiés avant les
matches et les résultats sont cohérents entre Q00 et natif.

Le mécanisme visible est un déplacement massif du prior WDL induit par la
sélection sur l'issue terminale :

| Corpus assemblé | win STM | draw | loss STM | asymétrie W/L |
|---|---:|---:|---:|---:|
| UNIFORM 2 M | 0,425540 | 0,152605 | 0,421856 | 0,003684 |
| HARD 2 M | **0,512906** | 0,171911 | **0,315184** | **0,197722** |

Le million frais commun est équilibré (0,426233 / 0,150894 / 0,422873). Le
million hard conserve volontairement les cibles terminales originales des
positions sélectionnées. Le miroir couleur conserve lui aussi le WDL STM :
il corrige la couleur, pas le prior de cible. Le garde-fou de distribution du
bras HARD avait été rendu diagnostique précisément parce que la sélection
`failed_conversion` est outcome-conditioned ; il a donc laissé passer une
asymétrie de 19,77 points.

Le DOE établit causalement que la **recette complète**
`50 % fresh + 50 % failed_conversion avec cibles historiques conservées` est
catastrophique. Il ne sépare pas causalement l'effet du prior WDL des autres
déplacements de distribution produits par le mining. La combinaison du prior
déplacé, de la holdout dégradée et de l'effondrement dans deux vues rend
cependant ce mécanisme proximal explicite et exclut un simple incident
opérationnel.

## 5. Décision et suite

- ne pas promouvoir ni baker `HARD_REPLAY` ;
- fermer la recette v1 de replay brut outcome-conditioned ;
- ne pas augmenter sa dose et ne pas réitérer le même fit ;
- ne pas généraliser ce résultat à tout hard mining ;
- une réouverture exigerait un DOE distinct avec prior de cibles contrôlé
  (appariement WDL, pondération bornée ou nouvelle trajectoire), un seul
  facteur à la fois ;
- poursuivre avec les **reverse seeds zero-target appariés** : les positions
  difficiles servent alors de racines et un nouveau self-play régénère les WDL
  terminales, au lieu de réinjecter les cibles conditionnées.

```json
{
  "promotion_authorized": false,
  "automatic_next_job": null,
  "hard_replay_v1_closed": true,
  "next_axis": "matched_reverse_seed_selfplay",
  "external_teacher_inputs": 0
}
```
