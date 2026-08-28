# L3 — Teacher distillation roadmap

> **Mis à jour : 28 août 2026**
> **Statut : roadmap active après verdict terminal T2 deep fresh.**
>
> Situation courante : [`L3_CURRENT.md`](L3_CURRENT.md). Prereg T2 terminale : [`experiments/L3_T2_PHASE_SPECIALIST_DEEP_FRESH_V1_20260828.md`](experiments/L3_T2_PHASE_SPECIALIST_DEEP_FRESH_V1_20260828.md), merge SHA `53f8d84991c8a69b690e7a2534fd290bbaad073f`.

---

## 1. Verdict qui change la roadmap

La campagne T2 phase-specialist est terminée avec :

```text
T2_PHASE_SPECIALIST_DEEP_SIGNAL_NOT_ESTABLISHED
```

Le support est pleinement établi, mais T2 échoue contre D1 sur le deep fresh q200 :

- T2 pairwise `0.7018589740` ;
- D1 pairwise `0.7338846504` ;
- T2−D1 mean `-0.0320256764`, CI95 `[-0.0373919611 ; -0.0266215498]` ;
- T2 top-hit `0.6434769819` vs D1 `0.6492131196` ; CI95 du delta top-hit traverse zéro ;
- T2−D1 est positif uniquement en P0 et négatif en P1/P2/P3 ;
- T2−D1 est négatif dans les deux couleurs.

T2 bat cependant T0 de `+0.0927905664` pairwise avec CI95 `[+0.0863858115 ; +0.0992239313]`.

La conclusion n'est donc pas « T2 n'apprend rien ». Elle est plus précise : **la capacité non linéaire state-only, les 200 bits bruts du plateau et les quatre experts de phase absorbent un signal important, mais pas assez pour dépasser D1 et pas de manière homogène hors P0.**

---

## 2. Références terminales T2

### Freeze

`cpx62-1627-l3-t2-phase-specialist-train-freeze-v1`, attempt `20260828T165619Z-a3ba045f`, Jass SHA `a3ba045facccd9bcbd01e9c872c045ac7c899f66`.

- verdict `T2_PHASE_SPECIALIST_FROZEN` ;
- T2 SHA256 `80de2d003c139c0fd8371e17175889a31f97792c5fd042a2a7338ca9dbc83c4d` ;
- 326 inputs state-only ; shared trunk `326->256->128` ; quatre heads `128->64->1` ;
- `434323` paires d'entraînement ;
- Q1 label/score reads = `0`.

### Cohort fresh

`cpx62-1628c-l3-t2-phase-specialist-fresh-select-v3`, attempt `20260828T182726Z-a3ba045f`.

- 8000 parents exactement, 2000 par phase ;
- seed `2026090610` ; target-blind ;
- selected SHA256 `d1f9fc41e3cb2f738011f78acc82848d025a608d8656702297b170a4e12daad1` ;
- exclusions DSSD A/B, Rich-D C, M1/M2/M3/M5, Q1 identities et force pools ;
- aucun teacher/T2/D1 score lu avant sélection.

### Teacher

`cpx62-1629-l3-t2-phase-specialist-teacher-v1`, attempt `20260828T193226Z-a3ba045f`.

- 76165 siblings ;
- q1000/q50/q200 = `1000/50000/200000` nœuds exacts ;
- q1000 diagnostic seulement ;
- book OFF, un thread, Engine/TT/search-state frais par sibling et budget ;
- aucun post-freeze fit/refit/calibration.

### Readout terminal

`cpx62-1630-l3-t2-phase-specialist-readout-v1`, attempt `20260828T194826Z-a3ba045f`.

- bootstrap parent-cluster `200000`, seed `2026090611` ;
- exit `0` ;
- verdict terminal `T2_PHASE_SPECIALIST_DEEP_SIGNAL_NOT_ESTABLISHED` ;
- runtime/Elo/strength/bake/promotion = `0`.

---

## 3. Support et métriques de référence

Support PASS :

- 8000 sélectionnés ;
- 6799 parents acceptés ;
- 195036 paires stables ;
- P0/P1/P2/P3 = `1795/1885/1857/1262` ;
- black/white = `3461/3338` ;
- stable pairs dans les huit cellules phase×couleur ;
- zero forbidden overlap ;
- T2 bytes unchanged ;
- zero post-freeze fit/refit/calibration.

| Modèle | Pairwise q200 | Top-hit |
|---|---:|---:|
| T0 | 0.6090684076 | 0.5461342354 |
| D1 | **0.7338846504** | 0.6492131196 |
| Rich-D | 0.7317405703 | **0.6608324754** |
| T2 | 0.7018589740 | 0.6434769819 |
| q1000 | **0.9374100334** | **0.8608741482** |

T2−D1 pairwise : mean `-0.0320256764`, CI95 `[-0.0373919611 ; -0.0266215498]`.

T2−D1 top-hit : mean `-0.0057361377`, CI95 `[-0.0173554935 ; +0.0058832181]`.

T2−T0 pairwise : mean `+0.0927905664`, CI95 `[+0.0863858115 ; +0.0992239313]`.

T2−Rich-D diagnostic : mean `-0.0298815962`, CI95 `[-0.0351834672 ; -0.0245653270]`.

q1000−T2 headroom : mean `+0.2355510594`, CI95 `[+0.2304987327 ; +0.2406365748]`.

---

## 4. Diagnostic par phase : la spécialisation n'a pas résolu le problème

Pairwise T2−D1 :

- P0 `+0.0186385392` ;
- P1 `-0.0388096009` ;
- P2 `-0.0592457989` ;
- P3 `-0.0539011136`.

Le head P0 fonctionne dans le sens attendu, mais le défaut des phases intermédiaires/tardives persiste et s'amplifie. La simple séparation en quatre heads hard-routed ne constitue donc pas la « formule magique » recherchée.

La lecture couleur est également défavorable : black `-0.0275639495`, white `-0.0366518108` contre D1.

---

## 5. Ce que T2 ferme scientifiquement

T2 testait explicitement une hypothèse de capacité/representation :

> Peut-on dépasser D1 sans nouvelles observables, uniquement avec 120 extras existants + plateau brut + T0 + STM + phase et un réseau plus expressif spécialisé par phase ?

Le deep fresh répond : **pas avec cette architecture preregistrée**.

Ce résultat ferme pour l'instant les variantes post-hoc suivantes sur ce cohort :

- agrandir les heads ou le trunk après lecture ;
- repondérer P1/P2/P3 ;
- changer les phases ;
- réentraîner avec le cohort 1628c ;
- ajouter une calibration apprise sur 1630 ;
- sélectionner de nouvelles features à partir des labels 1628c/1629.

Q1 et 1628c sont désormais des cohorts consommés.

---

## 6. Ce qui reste ouvert : observables manquantes

Le point le plus important est le headroom teacher : q1000 atteint `0.93741` pairwise alors que T2 est à `0.70186` et D1 à `0.73388`.

Le signal existe donc clairement. La prochaine hypothèse à tester n'est plus prioritairement « plus de capacité sur les mêmes entrées », mais :

> **des observables statiques importantes pour le ranking des siblings ne sont probablement pas explicitement accessibles ou facilement reconstructibles par le student actuel.**

Cela ne prouve pas qu'elles sont absolument absentes du board brut ; cela prouve que le protocole T2 ne les extrait pas de façon suffisamment sample-efficient/généralisable pour battre D1.

---

## 7. Prochaine campagne recommandée — residual feature discovery

Aucune continuation automatique n'est autorisée par T2. La prochaine campagne doit faire l'objet d'une preregistration séparée.

### Objectif

Identifier, **hors Q1 et hors 1628c**, quelles familles d'observables expliquent les erreurs q1000/q200 que D1/T2 commettent encore.

### Design recommandé

1. Constituer un nouveau corpus de développement disjoint ou réutiliser uniquement des corpus TRAIN autorisés antérieurs.
2. Geler D1, Rich-D et T2 comme baselines diagnostiques sans refit sur les cohorts consommés.
3. Construire une taxonomie d'erreurs teacher : D1 faux/T2 faux, D1 vrai/T2 faux, T2 vrai/D1 faux, q1000 correct et statiques faux.
4. Tester des familles d'observables une à une avec contrôle négatif et split parent-cluster.
5. Ne retenir une famille que si son gain OOS est stable par phase et couleur.
6. Preregistrer ensuite un T3/student final avec feature set gelé avant un **nouveau** deep-fresh q200 cohort.

### Familles prioritaires à examiner

Sans les lancer ici, les familles scientifiquement plausibles sont :

- géométrie de capture multi-coup et contraintes de continuation ;
- mobilité/forced-move structure plus riche que les 120 extras ;
- motifs de tempo, opposition et races de promotion ;
- accessibilité/contrôle des cases et structures de blocage ;
- distances/chemins vers promotion et interactions de rois ;
- features de stabilité tactique calculables statiquement ou par calcul borné explicitement preregistré ;
- représentations locales/convolutionnelles du plateau si l'objectif est de tester l'inductive bias plutôt que seulement la largeur MLP.

La feature discovery doit être mesurée sur des données autorisées, jamais sur Q1/1628c.

---

## 8. Voies historiques encore utiles comme références

### D1

D1 reste la meilleure référence statique pairwise deep-fresh parmi les modèles évalués ici (`0.73388`). Son utilisation runtime passée n'a pas établi un gain de force ; cela reste distinct de son intérêt diagnostique offline.

### Rich-D

Rich-D reste très proche de D1 globalement (`0.73174`) et meilleur que T2, avec un profil de phase différent. Il reste un diagnostic historique, pas un candidat de promotion.

### A6-G0

Le secondary PASS Q1 de A6-G0 reste une preuve qu'un petit transfert vers PatternEval est possible. Il ne change pas le verdict T2 et n'autorise aucun runtime automatique.

### q1000

q1000 reste le teacher court dominant et la meilleure boussole de headroom, mais imitation q1000 ≠ précision q200 ≠ Elo.

---

## 9. Gate proposé pour une future feature-discovery campaign

Avant tout nouveau T3, demander au minimum :

- amélioration OOS contre D1 sur un corpus de développement non consommé ;
- gain pairwise positif dans P0/P1/P2/P3 et les deux couleurs ;
- ablation prouvant que la nouvelle famille de features apporte le gain ;
- absence de q50/q200/WDL/Q1/1628c leakage dans les inputs ;
- feature set et architecture gelés avant le prochain deep fresh ;
- nouveau cohort deep-fresh entièrement disjoint ;
- même séparation stricte entre deep accuracy et future force/Elo.

Les seuils numériques exacts devront être preregistrés avant lecture du nouveau holdout.

---

## 10. Règles verrouillées après T2

1. `CURRICULUM` reste champion.
2. Q1 et T2-1628c sont consommés et interdits au tuning/feature selection/calibration.
3. `T2_PHASE_SPECIALIST_DEEP_SIGNAL_NOT_ESTABLISHED` ferme T2-PMoE exact pour runtime/Elo dans cette campagne.
4. Aucun retune post-hoc de l'architecture, des phases, des poids de cellules ou des seeds.
5. Aucun runtime, Elo, strength, bake ou promotion n'est autorisé par T2.
6. q1000 imitation, q200 accuracy et Elo restent trois niveaux distincts.
7. Toute nouvelle feature/architecture doit être conçue et sélectionnée hors cohorts consommés.
8. Toute future force test nécessite d'abord un deep-fresh PASS puis une prereg runtime/strength distincte.

---

## 11. Principe directeur

La question L3 devient maintenant :

> **Quelles observables ou quels inductive biases permettent de capturer le ~23.6 pp de headroom q1000 restant et de dépasser D1 sur un nouveau q200 fresh, sans fuite depuis les cohorts de validation consommés ?**

T2 a rempli son rôle : il a testé proprement l'hypothèse « plus de capacité + plateau brut + phase experts ». Le résultat négatif évite de poursuivre aveuglément cette branche et déplace la priorité vers l'autopsie résiduelle et la recherche contrôlée de features manquantes.
