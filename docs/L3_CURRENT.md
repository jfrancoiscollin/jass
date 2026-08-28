# L3 — état courant et registre de décision

> **Mis à jour : 28 août 2026**
> **Source de vérité active : ce document.**
>
> Ce fichier est volontairement court. L'ancien `L3_CURRENT.md` était devenu un journal de plus de 220 kB et mélangeait état courant et historique. L'historique reste accessible dans Git, dans [`PROJECT_RESULTS.md`](PROJECT_RESULTS.md) et dans les protocoles/verdicts sous `docs/experiments/` et `archives/l3/`.
>
> **Roadmap scientifique active :** [`L3_TEACHER_DISTILLATION_ROADMAP.md`](L3_TEACHER_DISTILLATION_ROADMAP.md).

---

## 1. Champion de production

### `CURRICULUM` — champion courant

`CURRICULUM` reste le champion tant qu'un candidat n'a pas passé un gate de force preregistré et une réplication suffisante.

Identité immuable :

- raw/decompressed `.pjtw` SHA256 :
  `319d174f4b548b1655aad4bb30d4c6dc86c08dd715c9c23f8b19ba1937dc0be1`
- source R2 :
  `r2:jass-data/runs/cpx62-1341-jass-megacorpus-arm-d-fit-v1/20260814T191555Z-18c38a33/artefacts/D-c-prior-then-current.pjtw.gz`

Recette :

- pretrain `MEGA_FULL_4M`, puis recenter `CURRENT_2M` ;
- `CONTEXT_30`, alpha `0.30` ;
- `--exact-fold --tempo-stage` ;
- prior mean C, prior decay 0 ;
- L2 `1e-5`, `gtol=1e-4`, `maxcor=20`.

Promotion initiale contre L2LOW : environ `+7.7 Elo` Q00 et `+8.7 Elo` native 0.1s sur 24k parties.

**Aucun candidat post-CURRICULUM n'est actuellement promu.**

---

## 2. État scientifique en une phrase

La principale découverte récente est que **l'information décisionnelle manquante n'est pas principalement un problème de capacité du side-head statique : elle est produite par un lookahead très court.**

La chaîne observée est approximativement :

```text
T0 / CURRICULUM     ~60–61 % pairwise vs deep
D1 statique         ~72–73 %
Rich-D statique     ~73 %
micro-search 1000n  ~93–94 %
micro-search 5000n  ~95–96 %
```

Le problème prioritaire est donc maintenant double :

> **combien de ce signal micro-search pouvons-nous compresser dans un PatternEval statique, et quelle fraction supplémentaire devient exploitable si l'on apprend directement un évaluateur conjoint `T+D` au lieu de forcer toute l'information à rentrer dans `T` ?**

---

## 3. Pistes récemment fermées ou reclassées

### 3.1 Self-play / corpus / compounding

Les nombreuses variantes de corpus, replay, volume, coverage, context, horizontal multi-seed et boucles de self-play n'ont pas établi un opérateur d'amélioration robuste au-dessus de la lignée `CURRICULUM`.

Elles restent utiles comme historique, mais **ne sont plus la priorité compute**.

### 3.2 DSSD statique — information réelle

DSSD a établi un signal décisionnel fort et reproductible :

- Phase A `cpx62-1575-l3-deep-sibling-phase-a-v1` :
  `D1=0.72047` pairwise vs `T=0.59218`, soit `+12.83 pp` ;
- Phase B fresh `cpx62-1581-l3-deep-sibling-phase-b-readout-v2` :
  `D1=0.72604` vs `T=0.61406`, soit `+11.20 pp`, CI largement positive.

Conclusion : `D1` capture de l'information non présente dans le scalar T.

### 3.3 DSSD au runtime — fermé pour le move-ordering

`cpx62-1584-l3-dssd-move-ordering-force-pool1-v1` :

- native score `0.4944167` ;
- environ `-3.88 Elo` ;
- verdict `DSSD_MOVE_ORDERING_NOT_SUPPORTED`.

Le coût runtime annule le petit gain de qualité d'ordre. **Le mécanisme D1→move-ordering est fermé.** Cela ne ferme pas une future intégration causale différente où `D` participe à un évaluateur conjoint `T+D` ; cette hypothèse doit être testée séparément et preregistrée.

### 3.4 Rich-D statique — fermé

`cpx62-1590-l3-rich-d-r1-phase-c-readout-v2` :

- T `0.60944` ;
- D1 `0.72994` ;
- Rich-D `0.73225` ;
- q5k `0.95693`.

Rich-D ne gagne que `+0.23 pp` sur D1, avec CI traversant zéro et régressions de phase/couleur.

Verdict : `RICH_D_TEACHER_SIGNAL_NOT_ESTABLISHED`.

**Interprétation : élargir les features statiques de D sans lookahead ne récupère pas le signal q5k.**

---

## 4. Micro-search teacher — résultat majeur

Protocole : [`experiments/L3_MICRO_SEARCH_TEACHER_TO_T_V1_20260827.md`](experiments/L3_MICRO_SEARCH_TEACHER_TO_T_V1_20260827.md).

### M1 — courbe de budget

`cpx62-1591-l3-micro-search-budget-curve-m1-v1`

Budget sélectionné :

```text
B* = 1000 nœuds
```

Sur le cohort exploratoire :

- pairwise `0.93264` ;
- top-hit `0.86162` ;
- headroom récupéré `H=0.8930` ;
- ~20 % des nœuds du 5k.

### M2 — confirmation fresh

`cpx62-1598-l3-micro-search-m2-teacher-readout-v5`

Verdict :

```text
MICRO_SEARCH_TEACHER_SIGNAL_ESTABLISHED
```

Fresh :

- D1 pairwise `0.72822` ;
- micro1000 `0.93507` ;
- q5k `0.95684` ;
- micro1000 − D1 = `+20.69 pp` ;
- CI95 `[+19.998 ; +21.373] pp` ;
- toutes phases et couleurs positives.

**Conclusion : la majorité du signal manquant est créée par ~1000 nœuds de recherche.**

---

## 5. M3/M4 — distillation full PatternEval

### M3 — scale teacher/design

Sélection M3 : `cpx62-1599-l3-micro-search-m3-scale-select-v1`.

Teacher/design final : `cpx62-1607-l3-micro-search-m3-teacher-design-v6`.

Résultat final :

- 100 000 parents ;
- 928 639 siblings ;
- 828 639 contraintes top-vs-rest ;
- représentation **full production PatternEval**, pas seulement 120 extras ;
- preuve d'équivalence exacte entre design rows et scoring production ;
- zéro mismatch de score sur 928 639 rows.

Les retries 1600–1606 étaient techniques uniquement ; ils n'ont pas changé la science.

### M4 — T1 gelé

`cpx62-1608-l3-micro-search-m4-pattern-distill-v1`

Verdict technique/scientifique de construction : PASS, marker `MICRO_SEARCH_M4_T1_FROZEN`.

T1 :

- raw SHA256 : `25aa82567f38b9e2ad5d792d478c9e98c09d4bff9beabaa367038f55a4a98306` ;
- vrai `.pjtw` production, pas de side-head ;
- 828 639 contraintes fit ;
- 4 251 528 pattern buckets, 114 916 actifs ;
- 452 coefficients int32 modifiés ;
- L2 résiduel `1e-5` ;
- L-BFGS-B convergé (`status=0`) ;
- residual scale final `0.5222358257` ;
- anchor 500k : RMS `9.388 cp`, p99 `35 cp` ;
- serialize/reload PASS ;
- `D` absent à l'inférence ;
- micro-search absent à l'inférence.

**T1 n'est pas un champion. Il devait d'abord passer M5 puis M6.**

---

## 6. M5 — transfert deep fresh : verdict terminal négatif mais informatif

Sélection :

`cpx62-1609-l3-micro-search-m5-fresh-select-v1`

- exactement 4000 parents ;
- 1000 par P0/P1/P2/P3 ;
- seed `2026090220` ;
- target-blind ;
- zéro teacher score/label lu pendant la sélection.

Confirmation :

`cpx62-1610-l3-micro-search-m5-deep-transfer-v1`

Verdict :

```text
MICRO_SEARCH_TO_T_TRANSFER_NOT_ESTABLISHED
```

Support :

- accepted parents `3423` ;
- stable pairs `97342` ;
- black `1673`, white `1750` ;
- P0 `896`, P1 `945`, P2 `951`, P3 `631`.

Global :

| métrique | T0 | T1 | delta |
|---|---:|---:|---:|
| pairwise | 0.6002060 | 0.6025015 | **+0.0022955** |
| top-hit | 0.5259519 | 0.5261710 | +0.0002191 |

Pairwise T1−T0 bootstrap parent-cluster 100k :

- mean `+0.0022955140` = **+0.2296 pp** ;
- CI95 `[+0.0011948 ; +0.0033755]` ;
- `P(delta>0)=0.99998`.

Top-hit :

- CI95 `[-0.0031649 ; +0.0036274]` ;
- non établi.

Par phase :

- P0 `−0.0017280` ;
- P1 `+0.0018483` ;
- P2 `+0.0037324` ;
- P3 `+0.0065130`.

Par couleur :

- black `+0.0014838` ;
- white `+0.0030715`.

Gates :

- pairwise CI low > 0 : PASS ;
- top-hit CI low > 0 : **FAIL** ;
- deux couleurs positives : PASS ;
- toutes phases positives : **FAIL** à cause de P0 ;
- anchor/reload : PASS ;
- D/micro-search absents : PASS.

### Interprétation

La première distillation **transfère réellement une petite quantité d'information** : le gain global pairwise est très probablement réel. Mais la recette M4 ne transfère pas encore assez de signal pour satisfaire le contrat robuste.

Donc :

- **pas de M6 Elo pour T1** ;
- **pas de promotion de T1** ;
- `CURRICULUM` reste champion ;
- la bonne prochaine question est le **rendement de transfert**, puis la capacité de `T` seul versus une représentation conjointe `T+D`.

---

## 7. Expérience active suivante

### Diagnostic de rendement de transfert

Sur exactement le cohort/labels M5, comparer sur les mêmes paires :

```text
T0 / CURRICULUM
D1 sealed
micro-search 1000n
T1 frozen
```

Publier pairwise/top-hit globaux, par phase/couleur, asymétries d'erreur et :

```text
R_D    = (A_T1 - A_T0) / (A_D1   - A_T0)
R_1000 = (A_T1 - A_T0) / (A_1000 - A_T0)
```

`R_1000` devient la métrique principale de compression teacher→PatternEval.

Ce diagnostic est read-only et **ne change pas rétroactivement le verdict M5**.

---

## 8. Roadmap active

La séquence décidée est :

```text
1. Évaluer précisément le transfert d'information
   T0 / D1 / q1000 / T1
        ↓
2. Optimiser la recette de transfert PatternEval
   objectif principal : max R_1000
        ↓
3. Mesurer la capacité d'absorption des features PatternEval actuelles
        ↓
4. Tester un modèle conjoint T+D sur les mêmes labels fresh
   stack minimal -> joint full-features -> residual D-on-T si justifié
        ↓
5. Ajouter des features seulement si les plafonds de T et du joint le justifient
        ↓
6. Relancer une campagne teacher optimisé -> T2
   ou student conjoint si celui-ci est scientifiquement supérieur
        ↓
7. Tester from-scratch / multi-entry / multi-seed
   pour mesurer la convergence vers un optimum
```

Détails, métriques et règles : [`L3_TEACHER_DISTILLATION_ROADMAP.md`](L3_TEACHER_DISTILLATION_ROADMAP.md).

---

## 9. Règles de décision courantes

1. **Technique ≠ science.** Un retry mécanique ne change jamais le protocole.
2. **Fresh reste fresh.** Aucun tuning sur un cohort servant de confirmation.
3. **Pairwise pp ≠ Elo.** Ne jamais convertir un gain de ranking en Elo sans force gate.
4. **Teacher micro-search offline uniquement.** Le micro-search crée l'information et n'est pas embarqué dans le runtime du student. Un éventuel `D` runtime dans un modèle conjoint est une hypothèse séparée qui exige son propre gate de coût/force.
5. **Pas de feature creep.** Ajouter des features seulement après preuve d'un plafond avec les observables et représentations actuelles.
6. **Pas de promotion sur loss/pairwise seul.** Un champion doit gagner le gate de force preregistré.
7. **Pas de M6 pour T1 après le FAIL M5.** Toute force future doit porter sur un nouveau candidat validé par une nouvelle confirmation fresh.
8. **Objectif scientifique prioritaire :** construire un opérateur reproductible `teacher court -> student` qui améliore la force, avec `PatternEval` pur si la compression fonctionne ou un joint compact `T+D` si sa supériorité est démontrée.

---

## 10. Résumé opérationnel

### Champion

```text
CURRICULUM
```

### Candidat expérimental

```text
T1 — artefact valide, transfert global faible mais positif, NON PROMU
```

### Dernier verdict

```text
MICRO_SEARCH_TO_T_TRANSFER_NOT_ESTABLISHED
```

### Next step

```text
mesurer R_D et surtout R_1000 sur le cohort M5,
puis DOE de transfert PatternEval,
puis probe de capacité et modèle conjoint T+D avant tout ajout majeur de features.
```
