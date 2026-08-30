# L3 — synthèse scientifique après RF1, T3 et runtime v4

> **Mise à jour : 30 août 2026**  
> **Statut : synthèse de décision — aucun nouveau résultat scientifique produit par ce document.**  
> Sources de vérité détaillées : [`L3_CURRENT.md`](L3_CURRENT.md), [`L3_TEACHER_DISTILLATION_ROADMAP.md`](L3_TEACHER_DISTILLATION_ROADMAP.md), prereg T3 [`experiments/L3_T3_RF1_JOINT_AB_V1_20260829.md`](experiments/L3_T3_RF1_JOINT_AB_V1_20260829.md), [prereg runtime v4](experiments/L3_T3_F6_RUNTIME_STRENGTH_V4_20260829.md), [résultat runtime v4 + Pool1](experiments/L3_T3_F6_RUNTIME_STRENGTH_V4_RESULTS_20260829.md), [prereg O1 cache exact](experiments/L3_T3_F6_RUNTIME_EXACT_CACHE_O1_20260830.md), [résultat runtime v3](experiments/L3_T3_F6_RUNTIME_STRENGTH_V3_RESULTS_20260829.md), [autopsie negamax](experiments/L3_T3_F6_NEGAMAX_AUTOPSY_20260829.md), benchmark Scan [`experiments/L3_SCAN_CEILING_BENCHMARK_V1_RESULTS_20260829.md`](experiments/L3_SCAN_CEILING_BENCHMARK_V1_RESULTS_20260829.md).

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
7. v3 s'est fermée avant ses gates d'évaluation faute de support mécanique (`5/32` témoins isolés P0), toujours sans partie de force ;
8. v4 a établi séparément le contrat production-leaf exact (`R0_V4_PRODUCTION_LEAF_CONTRACT_ESTABLISHED`) ;
9. le Pool1 PRIMARY CPX62 a ensuite joué `6000` parties et fermé négativement la force v4 : `T3_F6_RUNTIME_STRENGTH_NOT_SUPPORTED`, score T3-A `0.2095`, environ `-230.69 Elo`, `POOL2_AUTHORIZED__FALSE`.

Conclusion actuelle : **le transfert offline de F6 est établi, mais il ne s'est pas converti en force native à `0.1 s/move` dans l'implémentation v4**. Ce n'est plus une question ouverte. `CURRICULUM` reste champion et la campagne de force v4 est fermée. La seule suite active est O1 : une optimisation runtime strictement équivalente du résiduel F6, technique uniquement, sans nouveau modèle, retune, D1, retrait de F6 ni partie de force.

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
| T3-B `JOINT_D1_F6` | `0.7782264240` | **`0.6883823529` |
| q1000 diagnostic | `0.9361726862` | `0.8587521008` |

T3-A−T0 pairwise : `+0.1749545986`, CI95 `[+0.1694074710 ; +0.1804750871]`.  
T3-A−D1 pairwise diagnostic : `+0.0496899330`, CI95 `[+0.0442287889 ; +0.0551209779]`.

Le gain A−T0 est positif dans P0/P1/P2/P3 et dans les deux couleurs. Il ne s'agit donc pas d'un gain localisé sur une seule phase.

### 2.3 D1 n'est pas additif au-dessus de F6 dans le bras testé

T3-B−T3-A pairwise : `-0.0049429348`, CI95 `[-0.0083936669 ; -0.0014982551]`.

Le delta pairwise B−A est négatif dans les quatre phases et dans les deux couleurs. Le petit avantage top-hit ponctuel de B ne passe pas la CI95 preregistrée.

Décision : **D1 est fermé comme input additionnel de cette lignée exacte**. Ce résultat ne prouve pas que toute information historiquement captée par D1 est inutile ; il montre qu'une fois F6 disponible, le scalaire D1 scellé ne fournit pas d'information additive reproductible au student joint preregistré.

### 2.4 Le contrat runtime de T3-A est établi en R0-v4

Les résultats runtime antérieurs restent immuables : v1 a établi les invariances de chemin/transposition/F6 avant son gate couleur absolu ; v2 a établi zéro extra-drift de T3 et l'autopsie a localisé son échec depth-1 dans la quiescence de production ; v3 a ensuite échoué fail-closed sur le support mécanique de son témoin isolé (`5/32` P0), sans lire les métriques de force.

V4 est une campagne distincte, preregistrée sans retune de T3-A, et son terminal R0 est :

```text
R0_V4_PRODUCTION_LEAF_CONTRACT_ESTABLISHED
```

Job `cpx62-1685-l3-t3-f6-runtime-r0-v4`, attempt `20260830T083226Z-0ead13cb`, code `0ead13cb3579ce83c1278fe21c6634096d5e8eec`, completed exit `0`.

R0 a établi le contrat production-leaf et autorisé Pool1 uniquement ; il n'était pas un résultat Elo.

### 2.5 Le verdict causal runtime v4 est négatif et terminal

Pool1 PRIMARY : `cpx62-1686-l3-t3-f6-runtime-strength-pool1-v4`, attempt `20260830T104034Z-0ead13cb`, `6000` parties, exit `0`. Reçu read-only : `cpx62-1689-l3-t3-f6-runtime-pool1-terminal-receipt-v1`, attempt `20260830T114717Z-ea643d77`.

```text
VERDICT = T3_F6_RUNTIME_STRENGTH_NOT_SUPPORTED
wins T3-A / draws / wins CURRICULUM = 1167 / 180 / 4653
score T3-A = 0.2095
Elo T3-A - CURRICULUM = -230.6871387863655
game CI95 = [0.19943856856108436 ; 0.21956143143891563]
paired CI95 = [0.20033333333333334 ; 0.21866666666666668]
P(score>0.5) = 0.0
POOL2_AUTHORIZED = FALSE
```

Le résultat est loin de la zone d'incertitude. **Pool2 v4 est interdit** ; aucun Pool3, bake ou promotion n'est autorisé. Le verdict offline F6 reste vrai dans son domaine, mais il ne peut pas être relu comme preuve de force runtime.

---

## 3. Ce qui est réfuté ou fortement dépriorisé

### 3.1 « Il suffit d'augmenter la profondeur du teacher »

Réfuté comme explication suffisante. Les teachers plus profonds contiennent un fort signal, mais les tentatives antérieures de transfert vers une représentation T pauvre n'ont pas composé ce signal de façon satisfaisante.

### 3.2 « Il suffit d'augmenter la capacité du réseau »

Fortement dépriorisé. T2, avec davantage de capacité, board brut et spécialistes de phase, apprenait un signal réel mais restait sous D1. Plus de paramètres ne compensent pas à eux seuls l'absence d'observables mécaniques pertinents.

### 3.3 « T + D1 + F6 doit forcément être meilleur que T + F6 »

Réfuté pour le bras joint preregistré. T3-B est pairwise significativement inférieur à T3-A. Aucun troisième bras ou retune post-hoc n'est autorisé sur le fresh consommé.

### 3.4 « Le fail-close d'un ancien R0 signifie que F6/T3-A est inutilisable »

Réfuté. V1/v2/v3 sont des terminaux techniques distincts. V4 a ensuite établi son propre contrat de leaf evaluator de production sans réécrire ces résultats antérieurs.

### 3.5 « Le gain offline F6 suffit à prédire la force native »

Réfuté pour l'implémentation v4 exacte. Malgré un gain offline massif et fresh, T3-A ne marque que `20.95 %` dans le Pool1 natif preregistré. Le passage offline → runtime doit donc rester une porte indépendante.

---

## 4. Ce qui reste inconnu

### 4.1 Quelle fraction de l'échec runtime vient du coût de F6 ?

Le verdict de force est connu ; son mécanisme précis ne l'est pas encore. Le diagnostic HOME post-terminal `1688` est technique uniquement mais mesure, sur un rebuild HOME natif des mêmes sources, `wall_ratio_t3_over_curriculum = 37.154452` et `nps_ratio_t3_over_curriculum = 0.053152` à depth 9. Ces chiffres rendent le coût runtime une hypothèse forte, sans pouvoir réinterpréter Pool1.

F2 `RESPONSE_FRONTIER` implique notamment des générations répétées de coups légaux après les réponses. O1 teste d'abord une transformation plus étroite et parfaitement équivalente : éviter les recomputations F6 pour une position déjà évaluée dans une recherche.

### 4.2 Où est le plafond pratique de notre teacher/search ?

Le benchmark Scan/Home est terminal et établit un large headroom de Jass vers Scan profond (`JASS_SEARCH_LARGE_HEADROOM_TO_SCAN_ESTABLISHED`). Ce résultat est benchmark-only et n'autorise aucun tuning de T3-A actuel.

Une attribution séparée des six axes search-semantics Jass/Scan s'est également terminée sur `NO_SINGLE_SEARCH_SEMANTICS_AXIS_ESTABLISHED` : aucun axe isolé preregistré n'explique à lui seul le gap selon les critères gelés. Les combinaisons post-hoc ne sont pas autorisées dans cette campagne.

---

## 5. Pistes actives à creuser

### 5.1 Priorité immédiate — O1 cache exact, technique uniquement

La campagne de force v4 est fermée. La priorité opérationnelle est désormais la preregistration `L3_T3_F6_RUNTIME_EXACT_CACHE_O1_20260830.md`.

O1 conserve exactement : T3-A, ses poids et normalisation, les 66 F6, CURRICULUM, le POV, l'arrondi et la recherche. Il ajoute un cache direct-mapped du résiduel raw avec vérification de clé complète, puis exige :

- contrats unitaires, hash/index et concurrence ;
- équivalence leaf bit-à-bit ;
- équivalence search exacte à budgets fixes ;
- seulement ensuite un profil de coût CPX62.

O1 joue **zéro partie de force** et ne peut autoriser ni Pool2 ni promotion. Tout nouveau contraste de force sur une implémentation optimisée exige une nouvelle preregistration séparée après le terminal O1.

### 5.2 Benchmark Scan et attribution search-semantics — résultats acquis, pas source de retune T3

Le benchmark Scan a établi un large headroom vers la référence profonde. L'attribution single-axis suivante n'a établi aucun axe isolé. Ces résultats orientent la recherche future, mais restent séparés du contraste causal T3-A/F6 clos.

### 5.3 Piste future après O1 — seulement sous nouvelle preregistration

Si O1 établit une optimisation exacte et un profil suffisamment prometteur, un **nouveau fresh de force** peut être preregistré séparément. Le Pool1 v4 consommé ne peut pas servir de pool de confirmation ou de sélection.

Si O1 est trop peu efficace, une optimisation O2 exacte — par exemple un refactor strictement équivalent de F2 — doit elle aussi être preregistrée séparément ; aucun sweep opportuniste de cache/refactor n'est permis.

### 5.4 Piste secondaire — asymétrie historique de CURRICULUM

Le gate R0 v1 a découvert que CURRICULUM n'est pas exactement invariant sous rotate180+colour-swap selon le contrat v1. Cette asymétrie préexistante mérite une autopsie séparée, mais modifier T0 maintenant brouillerait les contrastes déjà gelés.

---

## 6. Lecture actuelle de la distillation

La distillation reste scientifiquement informative, avec une leçon plus précise qu'avant :

1. **F6 transfère massivement offline**, donc la découverte d'observables a résolu un vrai goulot de représentation ;
2. **ce transfert ne garantit pas la force au temps**, comme l'établit le Pool1 v4 ;
3. **le coût d'extraction doit être traité comme une partie du contrat d'évaluation**, pas comme un détail après le fit.

La méthode à privilégier devient :

```text
search profond
→ identifier les erreurs de T
→ chercher les informations mécaniques absentes de la représentation
→ transformer ces informations en observables statiques sûrs
→ distiller dans T
→ confirmer sur fresh
→ prouver l'équivalence de toute optimisation runtime
→ mesurer le coût
→ seulement ensuite ouvrir un fresh de force séparé
```

---

## 7. Registre de décision compact

| Question | État | Décision |
|---|---|---|
| F6 contient-il un signal statique réel ? | **ÉTABLI** | conserver F6 exact |
| F6 transfère-t-il vers T offline ? | **ÉTABLI** | T3-A reste l'artefact scientifique gelé |
| D1 est-il additif au-dessus de F6 ? | **NON ÉTABLI / négatif** | fermer D1 comme input additionnel de cette lignée |
| T3-A est-il positionnel/transposition-safe et sans extra drift ? | **ÉTABLI par v1/v2** | conserver ces preuves sans réécrire leurs terminaux |
| Le contrat production-leaf est-il établi ? | **ÉTABLI par R0-v4** | contrat runtime validé |
| T3-A gagne-t-il de l'Elo au natif v4 ? | **NON** | `T3_F6_RUNTIME_STRENGTH_NOT_SUPPORTED`; Pool2 fermé |
| F6 est-il trop cher en wall-clock ? | **HYPOTHÈSE TECHNIQUE FORTE, causalité non établie** | O1 exact-cache, zéro force |
| Jass possède-t-il du headroom vers Scan profond ? | **ÉTABLI : large headroom** | préserver le benchmark-only |
| Un axe search-semantics isolé explique-t-il ce gap ? | **NON ÉTABLI** | aucune combinaison post-hoc dans la campagne consommée |
| Quelle est la prochaine étape autorisée ? | **O1 technique uniquement** | équivalence exacte puis profil, aucun match de force |

---

## 8. Garde scientifique

Les cohorts Q1, T2 fresh, RF1 fresh, T3 fresh, R0-v1, R0-v2, R0-v3, R0-v4 et Pool1 v4 sont consommées selon leurs contrats. Elles ne doivent pas être utilisées pour retune, calibration, feature selection ou model selection futurs ; leurs identités peuvent servir aux exclusions ou aux tests techniques d'équivalence lorsque la preregistration le prévoit.

Le benchmark Scan et l'attribution search-semantics sont benchmark/diagnostic-only et ne doivent pas devenir une source de tuning du T3-A actuel.

`CURRICULUM` reste champion de production. `POOL2_AUTHORIZED__FALSE`. O1 n'autorise aucune partie de force, aucun bake et aucune promotion automatique.
