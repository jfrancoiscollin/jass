# L3 — état courant et registre de décision

> **Mis à jour : 28 août 2026**
> **Source de vérité active : ce document.**
>
> L'historique détaillé reste dans Git, [`PROJECT_RESULTS.md`](PROJECT_RESULTS.md), les protocoles sous `docs/experiments/` et les archives L3. La roadmap active est [`L3_TEACHER_DISTILLATION_ROADMAP.md`](L3_TEACHER_DISTILLATION_ROADMAP.md).

---

## 1. Champion de production

### `CURRICULUM` — champion courant

Aucun candidat post-CURRICULUM n'est promu.

Identité immuable :

- raw/decompressed `.pjtw` SHA256 : `319d174f4b548b1655aad4bb30d4c6dc86c08dd715c9c23f8b19ba1937dc0be1` ;
- source R2 : `r2:jass-data/runs/cpx62-1341-jass-megacorpus-arm-d-fit-v1/20260814T191555Z-18c38a33/artefacts/D-c-prior-then-current.pjtw.gz`.

`T1` reste un artefact expérimental non promu. Aucun M6/Elo n'a été lancé après le FAIL M5.

---

## 2. État scientifique en une phrase

Nous savons désormais que le goulot est **multi-factoriel** :

1. la première recette de distillation vers PatternEval était nettement sous-optimale ;
2. l'architecture linéaire/anchor de PatternEval limite fortement l'absorption du teacher ;
3. la quantification int32 n'est presque pas le problème ;
4. `T` et `D` portent une information complémentaire exploitable ;
5. même le meilleur joint statique reste très loin du teacher q1000, donc des observables statiques importantes manquent encore.

La priorité n'est donc plus « forcer D dans T ». Elle devient :

> **construire un student statique plus expressif, probablement conjoint T+D, tout en découvrant les observables qui expliquent le résidu q1000 encore inaccessible.**

---

## 3. Chaîne de preuves amont

Ordres de grandeur contre deep q200 sur cohorts fresh indépendants :

```text
T0 / CURRICULUM     ~60–61 %
D1 statique         ~72–73 %
Rich-D statique     ~73 %
micro-search 1000n  ~93–94 %
micro-search 5000n  ~95–96 %
```

Résultats structurants :

- M1 `cpx62-1591...` : `B*=1000` ;
- M2 final `cpx62-1598...` : `MICRO_SEARCH_TEACHER_SIGNAL_ESTABLISHED` ;
- M3 final `cpx62-1607...` : 100000 parents, 928639 siblings, 828639 contraintes, design PatternEval exact ;
- M4 `cpx62-1608...` : T1 gelé, SHA256 `25aa82567f38b9e2ad5d792d478c9e98c09d4bff9beabaa367038f55a4a98306` ;
- M5 `cpx62-1610...` : `MICRO_SEARCH_TO_T_TRANSFER_NOT_ESTABLISHED` ;
- diagnostic post-M5 `cpx62-1612...` : sur le même cohort deep, T0 `0.6002060`, D1 `0.7323419`, micro1000 `0.9375946`, T1 `0.6025015`, soit `R_1000≈0.0068`.

**Conclusion M5/1612 :** l'information existe, mais T1 n'en a absorbé qu'environ 0,7 % de l'incrément q1000 disponible contre deep q200.

---

## 4. Screen terminal Transfer / Capacity / Joint T+D

Preregistration : [`experiments/L3_TRANSFER_CAPACITY_JOINT_V1_20260828.md`](experiments/L3_TRANSFER_CAPACITY_JOINT_V1_20260828.md), merge SHA `78b2da436f990b6db870c7c1f7b3ee7a7d12b130`.

Implémentation : Jass SHA `d8241edc680eb50f324b2440fbde2bdadad29178`.

Screen scientifique réussi :

- job `cpx62-1614-l3-transfer-capacity-joint-screen-v2` ;
- attempt `20260828T092856Z-d8241edc` ;
- verdict `TRANSFER_CAPACITY_JOINT_SCREEN_READY` ;
- readout compact immuable : `cpx62-1615-l3-transfer-capacity-joint-readout-publish-v1`, attempt `20260828T100556Z-d8241edc` ;
- verdict `TRANSFER_CAPACITY_JOINT_SCREEN_READOUT_READY`.

Anti-leakage : M3 uniquement pour TRAIN/DEV ; M5/1612 fit reads `0`, model-selection reads `0`, nouveaux q200 labels `0`, selfplay `0`, strength `0`, promotion `false`.

Split parent-cluster seed `2026090401` :

- TRAIN `80161` parents ;
- DEV `19839` parents ;
- overlap parent `0` ; overlap canonique `0` ;
- métriques pairwise calculées sur `19503` parents DEV contribuant `854040` paires.

### Important : cible de ce screen

Ici `micro1000 = 1.0` par construction car **q1000 est la cible TRAIN/DEV**. Ce screen mesure la capacité à **imiter le teacher q1000**, pas une accuracy absolue contre q200. Il ne remplace donc pas une future confirmation deep fresh.

Baselines DEV :

| Modèle | Pairwise vs q1000 | Top-hit |
|---|---:|---:|
| T0 | 0.6142493 | 0.2675315 |
| D1 scellé | 0.6569985 | 0.2362201 |
| q1000 cible | 1.0000000 | 1.0000000 |

---

## 5. Stage A — le DOE de transfert aide réellement

L'arm gagnant est le même sous les trois anchors :

```text
A6_MARGIN_L2_1E5
```

C'est le top-vs-rest pondéré par marge teacher avec L2 `1e-5`.

| Guard | Pairwise | Top-hit | Scale | RMS / p99 anchor |
|---|---:|---:|---:|---:|
| G0 (12/35) | 0.6197134 | 0.2733767 | 0.39172 | 9.89 / 35 cp |
| G1 (20/60) | 0.6229890 | 0.2746176 | 0.66589 | 16.82 / 60 cp |
| G2 (35/100) | 0.6262529 | 0.2764404 | 1.00000 | 25.44 / 91 cp |

Référence A0/M4 : G0 `0.6158687`, G1 `0.6168534`, G2 `0.6171719`.

Donc le DOE améliore vraiment la recette. Sous le guard production-like G0, A6 gagne environ **+0,3845 pp sur A0** et **+0,5464 pp sur T0**. Sous G2, le gain atteint **+1,2004 pp sur T0**.

Mais même G2 ne récupère qu'environ **3,1 %** du gap T0→q1000 de ce DEV. La recette seule ne suffit donc pas.

---

## 6. Stage B — architecture oui, quantification non

### B0 — plafond linéaire sans anchor

Arm source : A6.

- float64 : pairwise `0.6264145`, top-hit `0.2765728` ;
- int32 production : `0.6262529`, top-hit `0.2764404` ;
- perte de quantification pairwise : seulement `0.0001616` = **0,0162 pp**.

Bootstrap B0-float − T0 : mean `+0.0121664`, CI95 `[+0.0113805 ; +0.0129581]`.

**Conclusion : la quantification int32 est négligeable.** Relâcher l'anchor aide un peu, mais le plafond linéaire reste bas.

### B1 — probe non linéaire sur les mêmes observables

Probe offline déterministe, sans D ni aucun score de recherche comme input : embeddings des patterns actifs + 120 extras, MLP 64, 875601 paramètres, seed `2026090402`.

Résultat :

- pairwise `0.6532856` ;
- top-hit `0.2666769` ;
- delta pairwise vs T0 bootstrap mean `+0.0390372`, CI95 `[+0.0366240 ; +0.0414446]`.

B1 récupère environ **10,1 %** du gap T0→q1000, contre ~3,15 % pour B0.

**Conclusion : les mêmes observables contiennent beaucoup plus de signal que le PatternEval linéaire actuel ne sait en exploiter. L'architecture/objectif est un vrai goulot.**

---

## 7. Stage C — T et D sont réellement complémentaires

Résultats DEV :

| Joint | Description | Pairwise | Top-hit |
|---|---|---:|---:|
| C0 | stack minimal T0 + D1 + phase + couleur | **0.6726851** | **0.3072861** |
| C1 | residual D-on-T | 0.6185354 | 0.2680100 |
| C2 | full linear PatternEval + D features | 0.6314341 | 0.2824181 |

Le meilleur est **C0**, de loin.

Bootstrap C0 − D1 :

- pairwise mean `+0.0156777` = **+1,568 pp** ;
- CI95 `[+0.0140121 ; +0.0172940]` ;
- `P>0 = 1.0`.

Bootstrap C0 − T0 : mean `+0.0584368`, CI95 `[+0.0568690 ; +0.0600014]`.

C0 dépasse aussi B1 d'environ **+1,94 pp** pairwise.

**Conclusion forte : T et D portent une information complémentaire.** Le joint ne doit plus être considéré comme une piste secondaire ; il devient une architecture student de premier rang à confirmer sur deep fresh.

En revanche C0 ne récupère qu'environ **15,1 %** du gap T0→q1000 de ce DEV. Même le joint statique reste donc très loin du teacher.

---

## 8. Classification terminale du bottleneck

Les quatre lectures preregistrées se combinent ainsi :

1. **Transfer recipe : oui.** A6 bat clairement A0 sous tous les guards.
2. **PatternEval architecture/anchor : oui.** B1 >> B0 ; un modèle non linéaire sur les mêmes observables absorbe beaucoup plus de q1000.
3. **Quantization int32 : non.** Perte ~0,016 pp seulement.
4. **Joint complementarity : oui, nettement.** C0 bat D1 de ~+1,57 pp avec CI très positive.
5. **Missing static observables : encore oui.** B1 et même C0 restent très loin de q1000.

Il n'y a donc pas un seul « trou » : **la meilleure voie combine une architecture student plus expressive, l'exploitation conjointe de T+D, et une découverte ciblée de nouvelles observables à partir du résidu q1000.**

---

## 9. Roadmap active après ce screen

Aucun nouveau q200 fresh n'est lancé dans cette étape.

Ordre recommandé :

```text
1. Preregister une confirmation deep fresh séparée
   - candidat PatternEval pur = A6 sous G0 (guard production-like)
   - candidat joint = architecture C0 rendue sérialisable/runtime-capable
   - candidats gelés AVANT lecture q200
        ↓
2. Fresh q200 réservé seed 2026090420
   - 4000 parents, 1000/phase
   - q50/q200 stable contract inchangé
   - micro1000 diagnostic sur les mêmes siblings
        ↓
3. En parallèle, analyser les erreurs q1000 résiduelles
   après B1/C0 pour proposer de nouvelles observables ciblées
        ↓
4. Si un candidat joint confirme sur q200
   mesurer son coût runtime puis seulement ensuite faire un gate Elo
        ↓
5. Construire T2/J2 avec le pipeline sélectionné
   puis tester composition/from-scratch/multi-seed
```

La future confirmation doit faire l'objet d'un **nouveau document de preregistration** avant toute génération/lecture de labels fresh.

---

## 10. Règles de décision courantes

1. Technique ≠ science.
2. Fresh reste fresh ; aucun tuning sur le futur cohort q200.
3. q1000 imitation ≠ deep accuracy ≠ Elo.
4. Aucun candidat n'est promu sur ce screen offline.
5. Le micro-search reste teacher offline.
6. Un éventuel `D` au runtime doit être jugé comme composant d'un évaluateur joint, pas réouvrir le move-ordering DSSD déjà fermé.
7. Les nouvelles features doivent viser les erreurs résiduelles non capturées par B1/C0, pas être ajoutées par intuition seule.
8. `CURRICULUM` reste champion tant qu'un nouveau candidat n'a pas passé confirmation fresh puis force robuste.

---

## 11. Résumé opérationnel

```text
Champion                = CURRICULUM
T1                      = non promu, M5 FAIL
Meilleur pure-T offline = A6_MARGIN_L2_1E5
Meilleur joint offline  = C0 (T0 + D1 + phase + couleur)
Quantization bottleneck = NON
Architecture bottleneck = OUI
T+D complementarity     = OUI
Missing observables     = OUI
Fresh q200 suivant      = NON LANCÉ
```
