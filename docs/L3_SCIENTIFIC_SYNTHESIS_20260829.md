# L3 — synthèse scientifique après RF1, T3 et runtime R0-v4

> **Mise à jour : 30 août 2026**  
> **Statut : synthèse de décision — aucun nouveau résultat scientifique produit par ce document.**  
> Sources de vérité détaillées : [`L3_CURRENT.md`](L3_CURRENT.md), [`L3_TEACHER_DISTILLATION_ROADMAP.md`](L3_TEACHER_DISTILLATION_ROADMAP.md), prereg T3 [`experiments/L3_T3_RF1_JOINT_AB_V1_20260829.md`](experiments/L3_T3_RF1_JOINT_AB_V1_20260829.md), [prereg runtime v4](experiments/L3_T3_F6_RUNTIME_STRENGTH_V4_20260829.md), [résultat runtime v4](experiments/L3_T3_F6_RUNTIME_STRENGTH_V4_RESULTS_20260829.md), [résultat runtime v3](experiments/L3_T3_F6_RUNTIME_STRENGTH_V3_RESULTS_20260829.md), [autopsie negamax](experiments/L3_T3_F6_NEGAMAX_AUTOPSY_20260829.md), benchmark Scan [`experiments/L3_SCAN_CEILING_BENCHMARK_V1_RESULTS_20260829.md`](experiments/L3_SCAN_CEILING_BENCHMARK_V1_RESULTS_20260829.md).

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
8. v4 a ensuite établi séparément le contrat production-leaf exact (`R0_V4_PRODUCTION_LEAF_CONTRACT_ESTABLISHED`) et autorisé Pool1, toujours avec `strength_games=0`.

Conclusion actuelle : **la distillation reste la piste principale et est plus crédible qu'avant**, mais la question suivante n'est plus un nouveau model search. Le candidat T3-A/F6 est gelé et doit maintenant recevoir son verdict causal runtime `T3_A_F6 vs CURRICULUM` sur Pool1 PRIMARY CPX62. Aucun retune, D1, retrait de F6 ou promotion automatique n'est permis.

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

### 2.4 Le contrat runtime de T3-A est maintenant établi en R0-v4

Les résultats runtime positifs antérieurs restent immuables : v1 a établi les invariances de chemin/transposition/F6 avant son gate couleur absolu ; v2 a établi zéro extra-drift de T3 et l'autopsie a localisé son échec depth-1 dans la quiescence de production ; v3 a ensuite échoué fail-closed sur le support mécanique de son témoin isolé (`5/32` P0), sans lire les métriques de force.

V4 est une campagne distincte, preregistrée sans retune de T3-A, et son terminal est :

```text
R0_V4_PRODUCTION_LEAF_CONTRACT_ESTABLISHED
```

Job `cpx62-1685-l3-t3-f6-runtime-r0-v4`, attempt `20260830T083226Z-0ead13cb`, code `0ead13cb3579ce83c1278fe21c6634096d5e8eec`, completed exit `0`.

Le reçu terminal publie `POOL1_AUTHORIZED__TRUE`, `STRENGTH_GAMES__0`, `PROMOTION_AUTHORIZED__FALSE`, `BAKE__FALSE` et `SCIENTIFIC_PARAMETERS_CHANGED__FALSE`. Il établit le contrat production-leaf et l'identité des bytes/runtime ; **il ne constitue pas un résultat Elo**.

---

## 3. Ce qui est réfuté ou fortement dépriorisé

### 3.1 « Il suffit d'augmenter la profondeur du teacher »

Réfuté comme explication suffisante. Les teachers plus profonds contiennent un fort signal, mais les tentatives antérieures de transfert vers une représentation T pauvre n'ont pas composé ce signal de façon satisfaisante.

La profondeur du teacher reste utile comme source d'information, mais **elle ne remplace pas les observables nécessaires côté student**.

### 3.2 « Il suffit d'augmenter la capacité du réseau »

Fortement dépriorisé. T2, avec davantage de capacité, board brut et spécialistes de phase, apprenait un signal réel mais restait sous D1. L'expérience suggère que plus de paramètres ne compensent pas l'absence d'observables mécaniques pertinents.

### 3.3 « T + D1 + F6 doit forcément être meilleur que T + F6 »

Réfuté pour le bras joint preregistré. T3-B est pairwise significativement inférieur à T3-A. Aucun troisième bras ou retune post-hoc n'est autorisé sur le fresh consommé.

### 3.4 « Le fail-close d'un ancien R0 signifie que F6/T3-A est inutilisable »

Réfuté. V1/v2/v3 sont des terminaux techniques distincts qui ont chacun préservé leurs preuves acquises et se sont arrêtés fail-closed. Aucun n'a démontré un défaut de formule/POV F6/T3-A. V4 a ensuite établi son propre contrat de leaf evaluator de production sans réécrire ces résultats antérieurs.

---

## 4. Ce qui reste inconnu

### 4.1 Le gain q200 devient-il de l'Elo ?

Toujours inconnu. Les terminaux runtime jusqu'à R0-v4 ont `strength_games = 0`. V4 autorise désormais Pool1 PRIMARY CPX62, mais tant que ce Pool1 n'est pas terminé il n'existe aucun verdict de force à interpréter.

La question causale reste exactement :

```text
T3_A_F6 vs CURRICULUM
```

### 4.2 Quel est le coût runtime effectif de F6 sous les régimes de force ?

R0-v4 a produit un profil technique authentifié, ce qui établit que le coût peut être mesuré sous les bytes et le search exacts. En revanche, son impact pratique sur le verdict de force sous native `0.1 s/move` et le diagnostic Q00 depth 9 reste à observer dans la campagne autorisée.

F2 `RESPONSE_FRONTIER` implique notamment une énumération bornée de réponses légales. Un scénario possible reste : signal statique positif à profondeur fixe mais coût assez élevé pour réduire le bénéfice wall-clock. Ce scénario doit être tranché par les mesures runtime preregistrées, pas par un retune du modèle.

### 4.3 Où est le plafond pratique de notre teacher/search ?

Le benchmark Scan/Home est maintenant terminal et établit un large headroom de Jass vers Scan profond (`JASS_SEARCH_LARGE_HEADROOM_TO_SCAN_ESTABLISHED`). Ce résultat est benchmark-only et n'autorise aucun tuning de T3-A actuel.

Une attribution séparée des six axes search-semantics Jass/Scan s'est également terminée sur `NO_SINGLE_SEARCH_SEMANTICS_AXIS_ESTABLISHED` : aucun axe isolé preregistré n'explique à lui seul le gap selon les critères gelés. Les combinaisons post-hoc ne sont pas autorisées dans cette campagne.

---

## 5. Pistes actives à creuser

### 5.1 Priorité immédiate — verdict causal Pool1 T3-A/F6 vs CURRICULUM

R0-v4 est PASS et autorise Pool1 uniquement. La priorité opérationnelle est donc le PRIMARY CPX62 native `0.1 s/move` sous les bytes, pools, seeds, search et runtime gelés par la preregistration v4.

Le Q00 Home depth 9 est diagnostic/non bloquant. Il peut aider à séparer signal statique et coût runtime, mais il ne peut jamais sauver un PRIMARY négatif et n'autorise pas Pool2 à lui seul.

Si Pool1 est positif selon le mapping preregistré, Pool2 devient la seule étape de force suivante autorisée. Sinon la campagne de force s'arrête. Aucun Pool3 ni promotion automatique.

### 5.2 Benchmark Scan et attribution search-semantics — résultats acquis, pas source de retune T3

Le benchmark Scan a établi un large headroom vers la référence profonde. L'attribution single-axis suivante n'a établi aucun axe isolé. Ces résultats orientent la recherche future, mais restent séparés du contraste causal T3-A/F6 actuel.

Ils ne permettent ni de modifier Q00/PRIMARY, ni d'ajouter une combinaison d'axes post-hoc, ni de retuner le candidat avant Pool1.

### 5.3 Piste future après le verdict de force — représentation-guided distillation / search semantics

Une fois le verdict T3-A/F6 acquis, les données déjà établies suggèrent deux familles de travail futures, qui demanderont chacune une nouvelle preregistration si ouvertes :

- poursuivre la découverte d'observables statiques manquants puis les distiller ;
- comprendre le headroom search Jass→Scan sans sélectionner post-hoc sur les cohorts consommés.

Le choix entre ces familles doit utiliser les verdicts terminaux comme contexte, pas réutiliser leurs cohorts pour retune/model selection.

### 5.4 Piste secondaire — asymétrie historique de CURRICULUM

Le gate R0 v1 a découvert que CURRICULUM n'est pas exactement invariant sous rotate180+colour-swap selon le contrat v1. Cette asymétrie préexistante mérite une autopsie séparée.

Elle ne doit pas être corrigée maintenant dans la branche T3 : modifier T0 changerait le baseline et brouillerait le contraste causal. Une future prereg séparée pourra mesurer son origine, sa magnitude et son coût éventuel.

---

## 6. Lecture actuelle de la distillation

La distillation reste la piste centrale pour trois raisons :

1. **on a maintenant une preuve de transfert massive et fresh** : T3-A gagne environ `+17.5 pp` pairwise contre T0 ;
2. **la découverte d'observables a précédé le succès de transfert** : la représentation, et pas seulement la capacité, était un goulot démontré ;
3. **il reste beaucoup de headroom** entre T3-A et la recherche profonde/externe.

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
| F6 transfère-t-il vers T ? | **ÉTABLI** | T3-A reste le candidat scientifique gelé |
| D1 est-il additif au-dessus de F6 ? | **NON ÉTABLI / négatif** | fermer D1 comme input additionnel de cette lignée |
| T3-A est-il positionnel/transposition-safe et sans extra drift ? | **ÉTABLI par v1/v2** | conserver ces preuves sans réécrire leurs terminaux |
| Le contrat production-leaf est-il établi ? | **ÉTABLI par R0-v4** | Pool1 PRIMARY autorisé |
| T3-A gagne-t-il de l'Elo ? | **INCONNU, 0 game** | exécuter Pool1 PRIMARY CPX62 |
| F6 est-il trop cher en wall-clock ? | **À trancher dans la force/diagnostic v4** | ne pas retuner avant verdict |
| Jass possède-t-il du headroom vers Scan profond ? | **ÉTABLI : large headroom** | préserver le benchmark-only |
| Un axe search-semantics isolé explique-t-il ce gap ? | **NON ÉTABLI** | aucune combinaison post-hoc dans la campagne consommée |
| Faut-il encore poursuivre la distillation à long terme ? | **OUI, priorité haute** | après le verdict de force courant |

---

## 8. Garde scientifique

Les cohorts Q1, T2 fresh, RF1 fresh, T3 fresh, R0-v1, R0-v2, R0-v3 et R0-v4 sont consommées selon leurs contrats. Elles ne doivent pas être utilisées pour retune, calibration, feature selection ou model selection futurs ; leurs identités peuvent servir aux exclusions lorsque la preregistration le prévoit.

Le benchmark Scan et l'attribution search-semantics sont benchmark/diagnostic-only et ne doivent pas devenir une source de tuning du T3-A actuel.

`CURRICULUM` reste champion de production. R0-v4 autorise Pool1, pas une promotion. Aucun résultat décrit ici n'autorise bake ou promotion automatique.
