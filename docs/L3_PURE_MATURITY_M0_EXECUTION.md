# L3-PURE-MATURITY — protocole exécutable M0

> **Version 1.1 — 24 juillet 2026**  
> **Statut :** M0 terminé sur HOME ; revue humaine terminée, parent M1 = C0 A-G3.

## 1. Question

Deux modèles généralistes entièrement autonomes sont disponibles :

- C0 A-G3, qui a atteint une parité pratique de `0,497` contre `gen2-mmto` dans le protocole historique `0795` ;
- P1-0842 G4, entraîné avec Q00 et les 63 paramètres de recherche explicitement épinglés, mais jamais mesuré directement contre Gen2.

M0 choisit le parent immuable de l’expérience de maturité M1 sans produire aucune donnée d’entraînement.

## 2. Sources immuables

| Modèle | Job | Artefact |
|---|---|---|
| C0 pur | `ccx33-0790-l3-pure-c0-a-v1` | `g3.pjtw.gz` |
| baseline propre | `cpx62-0842-l3-p1-frozen-v1` | `g4.pjtw.gz` |
| champion historique | bundle T1-bis figé | `gen2.pjtw.gz` |

Les manifests, inventaires et checksums sont vérifiés avant lecture.

## 3. M0-A — audit de couverture

Le job `cpx62-l3-pure-m0-coverage` télécharge les corpus d’autojeu C0 G1–G3 et P1 G1–G4 et mesure, par génération puis en cumul :

- buckets 8cf visités ;
- buckets avec au moins 10 et 100 visites ;
- fraction `ge_100` ;
- Gini et concentration des visites ;
- volume de records réellement analysé.

La couverture est diagnostique. Elle ne peut jamais sélectionner seule le parent.

## 4. M0-B — triangle de force

Le job `cpx62-l3-pure-m0-triangle` joue trois confrontations :

1. C0 A-G3 contre `gen2-mmto` ;
2. P1-0842 G4 contre `gen2-mmto` ;
3. P1-0842 G4 contre C0 A-G3.

Chaque confrontation utilise 300 ouvertures appariées avec couleurs inversées, soit 600 parties, dans trois vues :

- **historique :** d9, recherche partagée `qs_forcing_depth=6,qs_promo_depth=6`, afin de reproduire l’échelle `0795` ;
- **Q00 commun :** d9, fingerprint Q00 complet partagé ;
- **native equal-time :** `0,3 s/coup`, chaque modèle avec son fingerprint publié.

La vue native est primaire pour choisir le parent ; les vues historique et Q00 vérifient la robustesse de la lecture.

## 5. Règle préenregistrée

M0 peut publier :

```text
M0_RECOMMEND_C0_A_G3
M0_RECOMMEND_0842_G4
M0_PARENT_UNRESOLVED_MORE_N_OR_REVIEW
```

Une recommandation claire exige soit une supériorité directe dont l’IC est entièrement du bon côté de 0,5, soit un écart d’au moins 0,02 contre Gen2 accompagné de directions directes cohérentes. À défaut, le parent reste non résolu.

M0 ne promeut rien et ne lance rien automatiquement.

## 6. Restitution R2 et GitOps

Chaque job publie dans R2 :

- sources vérifiées ;
- rapports détaillés ;
- verdict agrégé ;
- `RESULTS.txt` ;
- `JASS_CONTROL_SUMMARY.json` ;
- logs.

Le statut `jass-control` expose des marqueurs lisibles : verdict, parent recommandé, Elo natifs principaux, couverture cumulée et `M1_AUTHORIZED__FALSE`.

## 7. Étape suivante M1

Après revue de M0, une PR séparée préparera depuis le même parent :

- `F500` : 500 000 records frais ;
- `F2M` : 2 millions de records frais dans un même fit ;
- `R2M` : 500 000 records frais plus 1,5 million de records historiques de la même lignée.

Avant cette PR : sélection humaine du parent, calibration du coût, validation du split/replay et go explicite.

```text
m1_authorized=false
promotion_authorized=false
automatic_next_job=null
```

## 8. Verdict HOME et revue humaine

Le triangle certifié `home-0934` réutilise sans replay les neuf sorties complètes
de `home-0932`. En natif, C0 et P1 obtiennent chacun `0,510` contre Gen2
(`+6,95 Elo`). P1 contre C0 obtient `0,4675`, soit `−22,62 Elo`, avec IC95
`[0,4276 ; 0,5074]`. Les vues commune Q00 et historique ne montrent aucun
avantage P1 : respectivement `0,4975` et `0,4900`.

L’audit `home-0935` mesure une couverture cumulative de `9,48 %` pour C0 contre
`10,06 %` pour P1. Ce gain de `0,58` point est diagnostique, malgré quatre
corpus P1 contre trois corpus C0, et ne compense pas l’absence de gain de force.

La règle automatique reste correctement `M0_PARENT_UNRESOLVED_MORE_N_OR_REVIEW`.
La revue humaine choisit néanmoins **C0 A-G3** pour l’écran non promotable M1 :
la vue primaire l’avantage directement, les deux vues secondaires sont
cohérentes avec l’absence d’avantage P1, les deux parents sont égaux contre
Gen2 en natif, et les trois corpus C0 fournissent exactement les 1,5 million de
records historiques requis par `R2M`.

```text
human_review_parent=C0_A_G3
m1_screen_authorized=true
promotion_authorized=false
automatic_next_job=null
```
