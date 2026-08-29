# L3 — synthèse scientifique après RF1, T3 et runtime R0-v3

> **Date : 29 août 2026**  
> **Statut : synthèse de décision — aucun nouveau résultat scientifique dans ce document.**  
> Sources de vérité détaillées : [`L3_CURRENT.md`](L3_CURRENT.md), [`L3_TEACHER_DISTILLATION_ROADMAP.md`](L3_TEACHER_DISTILLATION_ROADMAP.md), prereg T3 [`experiments/L3_T3_RF1_JOINT_AB_V1_20260829.md`](experiments/L3_T3_RF1_JOINT_AB_V1_20260829.md), [résultat runtime v3](experiments/L3_T3_F6_RUNTIME_STRENGTH_V3_RESULTS_20260829.md), [autopsie negamax](experiments/L3_T3_F6_NEGAMAX_AUTOPSY_20260829.md), benchmark Scan [`experiments/L3_SCAN_CEILING_BENCHMARK_V1_20260829.md`](experiments/L3_SCAN_CEILING_BENCHMARK_V1_20260829.md).

---

## 1. Résumé exécutif

La campagne récente change la lecture du blocage L3.

Le problème dominant n'était pas seulement la profondeur du teacher, la taille du réseau ou la recette d'optimisation. Les expériences indiquent maintenant fortement que **la représentation statique de T0 était trop pauvre pour exposer une partie importante de l'information que la recherche profonde utilise**.

La découverte de `F6_ALL_NEW`, concaténation fixe de 66 observables mécaniques search-free, a produit une chaîne de preuve reproductible :

1. F6 améliore fortement D1 sur historique ;
2. l'effet se reproduit presque exactement sur un fresh indépendant ;
3. F6 se transfère ensuite dans un student T3 résiduel qui bat largement T0 sur un nouveau fresh q200 ;
4. ajouter D1 au-dessus de F6 n'apporte pas de signal additif reproductible ;
5. v1 n'a pas invalidé F6 : il a découvert une asymétrie déjà présente dans CURRICULUM/T0 ;
6. v2 a établi le drift relatif exact, puis l'autopsie a montré que son témoin depth-1 simplifiait indûment la quiescence ;
7. v3 s'est fermée avant ses gates d'évaluation faute de support mécanique (`5/32` témoins isolés P0), toujours sans partie de force.

Conclusion actuelle : **la distillation reste la piste principale et est plus crédible qu'avant**, mais la bonne formulation est désormais « découvrir les observables manquantes puis distiller », et non simplement « donner un teacher plus profond au même T ».

---

## 2. Ce qui est établi

### 2.1 F6 capture une information statique réelle et généralisable

RF1 a établi puis confirmé `F6_ALL_NEW`, soit :

- F1 `CAPTURE_GEOMETRY` ;
- F2 `RESPONSE_FRONTIER` ;
- F3 `PROMOTION_RACE` ;
- F4 `STRUCTURE_GRAPH` ;
- F5 `KING_GEOMETRY_PLUS`.

Historique : RF1−D1 pairwise ≈ `+0.091803`.  
Fresh indépendant : RF1−D1 pairwise `+0.0919383909`, CI95 `[+0.0874942856 ; +0.0964236386]`.

La quasi-identité de l'effet historique et fresh rend l'hypothèse d'un artefact de sélection beaucoup moins plausible.

### 2.2 La distillation vers T fonctionne quand les bons observables sont disponibles

Le terminal T3 est :

```text
F6_TRANSFER_ESTABLISHED_D1_NOT_ADDITIVE
```

Sur le fresh commun terminal :

| Modèle | Pairwise q200 | Top-hit |
|---|---:|---:|
| T0 / CURRICULUM | `0.6082147602` | `0.5540686275` |
| D1 | `0.7334794258` | `0.6492647059` |
| T3-A `F6_ONLY` | **`0.7831693588`** | `0.6836764706` |
| T3-B `JOINT_D1_F6` | `0.7782264240` | **`0.6883823529`** |
| q1000 diagnostic | `0.9361726862` | `0.8587521008` |

T3-A−T0 pairwise : `+0.1749545986`, CI95 `[+0.1694074710 ; +0.1804750871]`.  
T3-A−D1 pairwise diagnostic : `+0.0496899330`, CI95 `[+0.0442287889 ; +0.0551209779]`.

Le gain A−T0 est positif dans P0/P1/P2/P3 et dans les deux couleurs. Il ne s'agit donc pas d'un gain localisé sur une seule phase.

### 2.3 D1 n'est pas additif au-dessus de F6 dans le bras testé

T3-B−T3-A pairwise : `-0.0049429348`, CI95 `[-0.0083936669 ; -0.0014982551]`.

Le delta pairwise B−A est négatif dans les quatre phases et dans les deux couleurs. Le petit avantage top-hit ponctuel de B ne passe pas la CI95 preregistrée.

Décision : **D1 est fermé comme input additionnel de cette lignée exacte**. Ce résultat ne prouve pas que toute information historiquement captée par D1 est inutile ; il montre qu'une fois F6 disponible, le scalaire D1 scellé ne fournit pas d'information additive reproductible au student joint preregistré.

### 2.4 Les résultats runtime positifs et leur frontière

Le runtime R0 v1 a établi avant son premier assert négatif :

- indépendance à l'identité du parent ;
- indépendance au chemin ;
- indépendance à l'ordre des siblings ;
- transposition explicite via deux parents/chemins légaux distincts ;
- indépendance à la TT et au search state ;
- indépendance aux bytes q-score/WDL ;
- égalité exacte des 66 F6 sous rotate180+colour-swap ;
- égalité bit-à-bit du résiduel F6 sous cette image.

Le premier échec n'est donc pas dans F6. V2 a ensuite établi, sur `4096`
positions nouvelles, que T3 ne crée aucun drift supplémentaire : mismatch
extra engine `0`, max extra engine `0 cp`, max extra float
`1.1368683772161603e-13 cp`. Son unique FAIL depth-1 a été classé par
l'autopsie `QUIESCENCE_OR_DEPTH_SEMANTICS_EXPLAINS_MISMATCH` : T0 échoue aussi,
et la première divergence est `qsearch_selective_sac`, sans défaut POV/formule
T3 observé.

V3 a preregistré le témoin corrigé, mais le support mécanique a échoué avant
toute lecture de score : `120000` candidates, `119699` uniques admissibles,
`26004` P0 uniques et seulement `5` leaf roots isolées pour `32` requises. Son
verdict est `R0_V3_RUNTIME_SUPPORT_INCONCLUSIVE`. Ce résultat ne répond ni
positivement ni négativement au contrat leaf complet.

---

## 3. Ce qui est réfuté ou fortement dépriorisé

### 3.1 « Il suffit d'augmenter la profondeur du teacher »

Réfuté comme explication suffisante. Les teachers plus profonds contiennent un fort signal, mais les tentatives antérieures de transfert vers une représentation T pauvre n'ont pas composé ce signal de façon satisfaisante.

La profondeur du teacher reste utile comme source d'information, mais **elle ne remplace pas les observables nécessaires côté student**.

### 3.2 « Il suffit d'augmenter la capacité du réseau »

Fortement dépriorisé. T2, avec davantage de capacité, board brut et spécialistes de phase, apprenait un signal réel mais restait sous D1. L'expérience suggère que plus de paramètres ne compensent pas l'absence d'observables mécaniques pertinents.

### 3.3 « T + D1 + F6 doit forcément être meilleur que T + F6 »

Réfuté pour le bras joint preregistré. T3-B est pairwise significativement inférieur à T3-A. Aucun troisième bras ou retune post-hoc n'est autorisé sur le fresh consommé.

### 3.4 « Le fail-close runtime v1 signifie que F6/T3-A est inutilisable »

Réfuté. Le verdict terminal R0 est :

```text
R0_PRODUCTION_LEAF_CONTRACT_NOT_ESTABLISHED
FROZEN_CURRICULUM_FAILS_PREREGISTERED_COLOUR_IMAGE_EXACTNESS
```

Le composant qui casse le contrat absolu est CURRICULUM/T0. F6 et le résiduel passent l'égalité couleur exacte. Comme `T3 = T0 - residual_F6`, T3 hérite mécaniquement du drift T0.

Aucune partie de force n'a été jouée. Le résultat ne conclut donc ni gain ni perte Elo.

---

## 4. Ce qui reste inconnu

### 4.1 Le gain q200 devient-il de l'Elo ?

Toujours inconnu. Les terminaux v1, v2 et v3 totalisent `strength_games = 0`
et `q00_games = 0`. V2 a déjà répondu positivement à la question d'asymétrie
relative ; v3 n'a pas atteint son contrat leaf corrigé parce que son générateur
n'a pas fourni assez de témoins isolés P0. Aucun résultat Elo n'existe donc à
interpréter.

### 4.2 Quel est le coût runtime réel de F6 ?

Inconnu à ce stade terminal : le profil v3 était postérieur au support
mécanique et n'a pas été exécuté. F2 `RESPONSE_FRONTIER` implique notamment une
énumération bornée de réponses légales. Un scénario plausible est :

- gain net à profondeur fixe ;
- mais coût trop élevé sous wall-clock.

Si cela arrive, la conclusion correcte serait « signal statique bon mais trop cher », ce qui ouvrirait une branche d'optimisation/distillation runtime, pas un abandon de F6.

### 4.3 Où est le plafond pratique de notre teacher/search ?

Le gap q1000−T3 reste très grand : q1000 est à environ `0.936` pairwise quand T3-A est à `0.783` sur le terminal T3. Ce headroom ne dit pas encore si q200/q1000 sont proches d'un optimum pratique ou s'ils restent eux-mêmes loin d'un moteur externe profond.

C'est précisément l'objet du benchmark Scan sur Home.

---

## 5. Pistes actives à creuser

### 5.1 Frontière runtime — nouveau support seulement sous nouvelle prereg

La campagne v3 est terminale. Une suite ne peut ni augmenter post-hoc ses
`120000` candidates, ni assouplir son prédicat, ni remplacer ses quotas. Si une
nouvelle campagne cherche à obtenir davantage de témoins leaf réellement
isolés, elle doit preregistrer séparément sa géométrie de génération et ses
seeds avant tout résultat, tout en conservant les bytes T3-A/CURRICULUM/F6 et
les anciens terminaux. Aucun tel programme n'est ouvert ici.

### 5.2 Priorité parallèle — benchmark Scan ceiling sur Home

Prereg : [`experiments/L3_SCAN_CEILING_BENCHMARK_V1_20260829.md`](experiments/L3_SCAN_CEILING_BENCHMARK_V1_20260829.md), PR `#694`, merge `25eec80addf50af9f2a7619b4f1c04464f8a24ce`.

Implémentation Home : PR `#698`, merge `1b8912dac463d006d84c75f21ff86aef9d7a74dd`, puis hardening non-destructif PR `#699`, merge `63d607d6b4a9e5658037e3823656f7415d7a8704`.

Objectif : comparer T0, D1, RF1, T3-A et une ladder Jass/Scan à une référence Scan profonde sur un cohort benchmark-only, sans aucun fit/tuning.

Questions à trancher :

1. T3-A est-il déjà proche du plafond pratique Scan ?
2. Jass q200 est-il déjà proche de Scan profond ?
3. Le prochain investissement doit-il viser surtout le student, le budget de recherche, ou le search/eval Jass lui-même ?

Home est la lane naturelle pour ce benchmark ; CPX62 reste la lane de référence pour les futurs verdicts runtime wall-clock.

### 5.3 Piste suivante selon Scan — expliquer le headroom T3 → q1000/Scan

Si q200 est proche de Scan profond : priorité à une nouvelle distillation des informations encore absentes de T3.

Si q200 est loin mais q1M se rapproche de Scan : priorité au budget/search teacher.

Si même Jass q1M reste loin de Scan : priorité à l'architecture/search semantics du moteur Jass.

### 5.4 Piste secondaire — asymétrie historique de CURRICULUM

Le gate R0 a découvert que CURRICULUM n'est pas exactement invariant sous rotate180+colour-swap selon le contrat v1. Cette asymétrie préexistante mérite une autopsie séparée.

Elle ne doit pas être corrigée maintenant dans la branche T3 : modifier T0 changerait le baseline et brouillerait le contraste causal. Une future prereg séparée pourra mesurer son origine, sa magnitude et son coût éventuel.

---

## 6. Lecture actuelle de la distillation

La distillation reste la piste centrale pour trois raisons :

1. **on a maintenant une preuve de transfert massive et fresh** : T3-A gagne environ `+17.5 pp` pairwise contre T0 ;
2. **la découverte d'observables a précédé le succès de transfert** : la représentation, et pas seulement la capacité, était un goulot démontré ;
3. **il reste beaucoup de headroom** entre T3-A et les petits searches diagnostics.

La méthode à privilégier devient :

```text
search profond
→ identifier les erreurs de T
→ chercher les informations mécaniques absentes de la représentation
→ transformer ces informations en observables statiques sûrs
→ distiller dans T
→ confirmer sur fresh
→ mesurer le coût et l'Elo séparément
```

Ce schéma est mieux soutenu par les données que les approches « plus gros réseau » ou « teacher plus profond avec mêmes observables » prises isolément.

---

## 7. Registre de décision compact

| Question | État | Décision |
|---|---|---|
| F6 contient-il un signal statique réel ? | **ÉTABLI** | conserver F6 exact |
| F6 transfère-t-il vers T ? | **ÉTABLI** | T3-A devient candidat scientifique principal |
| D1 est-il additif au-dessus de F6 ? | **NON ÉTABLI / négatif** | fermer D1 comme input additionnel de cette lignée |
| T3-A est-il positionnel/transposition-safe et sans extra drift ? | **ÉTABLI par v1/v2** | conserver ces preuves sans réécrire leurs terminaux |
| Le contrat leaf complet v3 est-il établi ? | **INCONCLUSIF — support `5/32` P0** | aucun relâchement post-hoc |
| T3-A gagne-t-il de l'Elo ? | **INCONNU, 0 game** | aucun verdict de force |
| F6 est-il trop cher en wall-clock ? | **INCONNU** | profil v3 non atteint |
| q200 est-il proche d'un plafond pratique externe ? | **INCONNU** | benchmark Scan/Home en cours |
| Faut-il encore poursuivre la distillation ? | **OUI, priorité haute** | représentation-guided distillation |

---

## 8. Garde scientifique

Les cohorts Q1, T2 fresh, RF1 fresh, T3 fresh, R0-v1, R0-v2 et les positions
générées/classifiées par R0-v3 sont consommées selon leurs contrats. Elles ne
doivent pas être utilisées pour retune, calibration, feature selection ou
model selection futurs ; leurs identités peuvent servir aux exclusions.

Le benchmark Scan est benchmark-only et ne doit pas devenir une source de tuning de T3-A actuel.

`CURRICULUM` reste champion de production tant qu'un gate de force preregistré ne démontre pas le contraire. Aucun résultat décrit ici n'autorise bake ou promotion automatique.
