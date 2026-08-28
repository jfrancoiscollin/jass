# L3 — Teacher distillation roadmap

> **Mis à jour : 28 août 2026**
> **Statut : roadmap scientifique active après M5.**
> Ce document décrit la stratégie de recherche prioritaire pour dépasser `CURRICULUM` en transformant de l'information de recherche coûteuse en une évaluation statique `PatternEval` plus forte.
>
> Le document de situation courante est [`L3_CURRENT.md`](L3_CURRENT.md). Le protocole qui a établi le teacher micro-search et produit `T1` est [`experiments/L3_MICRO_SEARCH_TEACHER_TO_T_V1_20260827.md`](experiments/L3_MICRO_SEARCH_TEACHER_TO_T_V1_20260827.md).

## 1. Point de départ expérimental

La séquence DSSD / Rich-D / micro-search a permis de localiser le goulot principal.

Sur des cohorts indépendants, les ordres de grandeur observés sont :

- `T0 = CURRICULUM` : ~60–61 % de pairwise accuracy contre la préférence deep 200k ;
- `D1` statique : ~72–73 % ;
- `Rich-D` statique : ~73 % ;
- micro-search 1000 nœuds : ~93–94 % ;
- micro-search 5000 nœuds : ~95–96 %.

Conclusion : augmenter simplement la capacité statique de `D` ne récupère pas le signal manquant. La majorité de l'information utile est **créée par un très court lookahead**.

Le programme micro-search a ensuite montré :

- M1 : `B*=1000` nœuds sélectionné ;
- M2 fresh : `MICRO_SEARCH_TEACHER_SIGNAL_ESTABLISHED` ;
- M3 : 100k parents, 928 639 siblings, 828 639 contraintes top-vs-rest, design PatternEval exact ;
- M4 : un vrai `T1.pjtw` a été produit par distillation full PatternEval ;
- M5 fresh : le transfert global est positif mais le gate complet échoue (`MICRO_SEARCH_TO_T_TRANSFER_NOT_ESTABLISHED`).

M5 donne :

- `T0` pairwise = `0.60020599797` ;
- `T1` pairwise = `0.60250151200` ;
- delta = `+0.00229551403` soit **+0.2296 point de pourcentage** ;
- bootstrap parent-cluster 100k : CI95 `[+0.0011948 ; +0.0033755]`, `P(delta>0)=0.99998` ;
- top-hit delta = `+0.0002191`, CI95 `[-0.0031649 ; +0.0036274]` : non établi ;
- P0 pairwise delta = `-0.0017280` ; P1 `+0.0018483` ; P2 `+0.0037324` ; P3 `+0.0065130` ;
- les deux couleurs sont positives ;
- anchor T1 reste valide : RMS `9.388 cp`, p99 `35 cp` ;
- aucune utilisation de `D` ou du micro-search à l'inférence.

**Lecture scientifique :** le signal est transférable dans `PatternEval`, mais la première recette n'en absorbe qu'une faible fraction et le transfert n'est pas encore robuste sur toutes les familles de positions.

---

## 2. Étape A — mesurer exactement le transfert d'information

### Objectif

Quantifier, sur **le même cohort M5 et les mêmes labels deep 200k**, où se situe `T1` entre `T0`, `D1` et le teacher micro-search.

Publier :

- `A_T0` : pairwise accuracy de `CURRICULUM` ;
- `A_D1` : pairwise accuracy du `D1` scellé ;
- `A_1000` : pairwise accuracy du micro-search 1000 nœuds ;
- `A_T1` : pairwise accuracy du `T1` gelé ;
- top-hit correspondant ;
- résultats par phase et couleur ;
- bootstrap parent-cluster des deltas pertinents.

Deux ratios deviennent les métriques centrales :

```text
R_D    = (A_T1 - A_T0) / (A_D1   - A_T0)
R_1000 = (A_T1 - A_T0) / (A_1000 - A_T0)
```

`R_D` mesure la fraction du signal statique additionnel de D1 absorbée par T1.

`R_1000` mesure la fraction du signal additionnel réellement disponible chez notre teacher 1000n absorbée par T1. **C'est la métrique principale pour la suite.**

Publier également les asymétries d'erreur :

- `T1 correct / D1 faux` ;
- `D1 correct / T1 faux` ;
- `T1 correct / micro1000 faux` ;
- `micro1000 correct / T1 faux`.

Cette étape est diagnostique uniquement : zéro fit, zéro retune, zéro force game.

---

## 3. Étape B — optimiser le mécanisme de transfert

### Hypothèse

Le premier `T1` n'a modifié que 452 coefficients int32 et a dû shrinker le résidu à `s≈0.522` pour respecter l'anchor. Le faible `R_1000` attendu peut donc provenir d'une **recette de distillation sous-optimale**, avant même de conclure à un manque de features.

### DOE de transfert

Créer un DOE séparé de M5, avec train/validation dédiés et confirmation fresh finale. Axes candidats :

1. **L2 résiduel** ;
2. **shrinkage / contrainte d'anchor** ;
3. top-vs-rest vs ensemble plus riche de paires ;
4. pondération par marge du teacher 1000n ;
5. température / transformation des écarts teacher ;
6. pondération des erreurs de `T0` corrigées par le teacher ;
7. balancing P0/P1/P2/P3 ;
8. balancing couleurs ;
9. nombre de contraintes / cap de rows ;
10. curriculum de fit : contraintes faciles → difficiles ou inversement ;
11. éventuelle séparation de régularisation patterns / extras.

### Fonction objectif

Primaire :

```text
max R_1000
```

Sous contraintes :

- pas de régression systématique par phase/couleur ;
- dérive T vs champion bornée par des guards preregistrés ;
- artefact exact, chargeable et reproductible ;
- zéro micro-search à l'inférence.

Secondaire : pairwise absolu de `T_candidate` contre deep 200k.

**Ne pas optimiser directement sur l'Elo à ce stade.** L'Elo servira de validation causale après qu'une recette de transfert soit sélectionnée sur données indépendantes.

---

## 4. Étape C — mesurer la capacité d'absorption de la représentation

Avant d'ajouter des features, distinguer deux causes :

```text
mauvais transfert != représentation insuffisante
```

### Test de capacité

Sur les mêmes entrées `PatternEval` existantes :

- entraîner un ou plusieurs probes beaucoup plus flexibles, offline uniquement ;
- mesurer leur pairwise fresh contre deep 200k ;
- comparer leur plafond à `T_candidate` ;
- analyser le résidu par phase, type de position et motif d'erreur.

Interprétation :

- si un modèle riche sur les **mêmes features** rejoint fortement micro1000, les features contiennent l'information : le problème est optimisation/architecture/quantification `PatternEval` ;
- si tous les modèles utilisant les mêmes observables plafonnent loin du teacher, l'information nécessaire est absente ou mal représentée : passer à l'étape D.

Le diagnostic doit répondre à :

```text
Quelle fraction du signal q1000 est représentable par les features de production actuelles ?
```

---

## 5. Étape D — ajouter des features seulement si le manque est démontré

Les features ne sont pas ajoutées parce qu'elles semblent plausibles ; elles doivent expliquer les erreurs résiduelles du teacher que les observables actuelles ne peuvent pas capturer.

Familles candidates, à confirmer par analyse d'erreur :

- motifs tactiques de captures multiples ;
- relations spatiales multi-pièces ;
- menaces / séquences forcées courtes ;
- mobilité conditionnelle ;
- promotion et cases de promotion ;
- tempo / parity / zugzwang-like motifs ;
- king mobility / king interaction plus structurée ;
- vulnérabilité après échange ;
- motifs locaux appris directement des PV 1000n.

Chaque famille passe par :

1. définition preregistrée ;
2. ablation offline ;
3. pairwise fresh ;
4. test d'invariance/symétrie ;
5. coût runtime ;
6. admission dans `PatternEval` uniquement si gain reproductible.

---

## 6. Étape E — campagne teacher optimisée → T2

Une fois le mécanisme de transfert et la capacité/feature set stabilisés, relancer une campagne complète de distillation.

Teacher primaire : **micro-search court optimisé**, actuellement 1000 nœuds sauf nouvelle preuve preregistrée.

Baseline/prior :

- `CURRICULUM` si aucun nouveau champion n'a été validé ;
- sinon le champion nouvellement promu.

Pipeline :

```text
champion T_base
  -> teacher micro-search optimisé
  -> corpus large et disjoint
  -> transfert optimisé
  -> représentation validée
  -> T2
  -> deep fresh confirmation
  -> force pools disjoints
  -> promotion seulement si force robuste
```

`T2` doit être considéré comme le premier candidat produit par un **pipeline teacher → student réellement optimisé**, pas comme un simple patch de `T1`.

---

## 7. Étape F — expérience from-scratch / multi-points d'entrée

### Question finale

Une fois la procédure teacher→T stabilisée, vérifier si elle constitue un véritable opérateur d'amélioration qui converge vers un optimum reproductible.

Créer plusieurs lignées indépendantes avec :

- teacher optimisé dès le départ ;
- plusieurs seeds ;
- plusieurs points d'entrée / initialisations ;
- mêmes règles de transfert et mêmes budgets ;
- validation mutuellement disjointe.

Schéma :

```text
B1 --teacher--> T1a --teacher--> T2a ...
B2 --teacher--> T1b --teacher--> T2b ...
...
Bk --teacher--> T1k --teacher--> T2k ...
```

Les points d'entrée doivent inclure au minimum :

- from scratch / baseline neutre lorsque techniquement défini ;
- `CURRICULUM` ;
- le champion courant si différent ;
- éventuellement plusieurs seeds d'une même base.

### Trois résultats structurants

1. **Convergence commune autour de CURRICULUM** : indication d'un plafond structurel de la représentation/procédure.
2. **Convergence vers un optimum commun supérieur au champion** : preuve d'un opérateur d'amélioration reproductible.
3. **Optima différents selon seed/point d'entrée** : paysage multi-bassins ; alors exploiter diversité, pooling, sélection ou distillation inter-lignées.

Le critère n'est pas une génération isolée positive mais la trajectoire :

```text
force(T_g+1) - force(T_g)
```

sur plusieurs générations, plusieurs lignées et pools fresh.

---

## 8. Ordre d'exécution verrouillé

```text
A. Évaluer le transfert d'information T0/D1/q1000/T1
        ↓
B. Optimiser la recette de transfert — max R_1000
        ↓
C. Mesurer la capacité d'absorption avec les features actuelles
        ↓
D. Ajouter des features seulement si nécessaire et démontré
        ↓
E. Relancer teacher optimisé → T2 sur le champion courant
        ↓
F. Tester from scratch / multi-entry / multi-seed et la convergence
```

Ne pas sauter directement de A à D : un faible transfert peut venir de la recette et non des features.

Ne pas sauter directement de B à l'Elo : d'abord confirmer le mécanisme sur un cohort fresh, puis faire le gate causal de force.

---

## 9. Métriques de pilotage principales

| Niveau | Métrique principale | Question |
|---|---|---|
| Teacher | pairwise q1000 vs q200 | Le teacher produit-il l'information ? |
| Transfert | `R_1000` | Quelle fraction de cette information passe dans T ? |
| Capacité | meilleur pairwise possible avec features actuelles | L'information est-elle représentable ? |
| Features | delta pairwise fresh + coût runtime | Une nouvelle observable paie-t-elle ? |
| Student | pairwise/top-hit T vs q200 | T a-t-il réellement absorbé le teacher ? |
| Force | native 0.1s paired Elo | Le gain d'éval se convertit-il en parties gagnées ? |
| Convergence | gain inter-génération multi-seed | Le procédé compose-t-il et vers quel optimum ? |

---

## 10. Principe directeur

La question scientifique n'est plus seulement :

> « Comment gagner quelques Elo ? »

Elle devient :

> **Peut-on construire un opérateur reproductible qui transforme de la recherche courte mais informative en une évaluation statique de plus en plus forte, et vers quel optimum cet opérateur converge-t-il ?**

C'est désormais l'axe prioritaire de L3.
