# L3 — Teacher distillation roadmap

> **Mis à jour : 28 août 2026**
> **Statut : roadmap scientifique active après M5.**
> Ce document décrit la stratégie de recherche prioritaire pour dépasser `CURRICULUM` en exploitant l'information créée par une recherche courte. Deux voies sont désormais étudiées explicitement : **distiller cette information dans un `PatternEval` statique** et **tester si un évaluateur conjoint `T+D` peut l'exploiter sans imposer cette compression**.
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

`R_1000` mesure la fraction du signal additionnel réellement disponible chez notre teacher 1000n absorbée par T1. **C'est la métrique principale pour la voie PatternEval.**

Publier également les asymétries d'erreur :

- `T1 correct / D1 faux` ;
- `D1 correct / T1 faux` ;
- `T1 correct / micro1000 faux` ;
- `micro1000 correct / T1 faux`.

Cette étape est diagnostique uniquement : zéro fit, zéro retune, zéro force game.

---

## 3. Étape B — optimiser le mécanisme de transfert vers PatternEval

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

## 4. Étape C — mesurer la capacité d'absorption de la représentation PatternEval

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
- si tous les modèles utilisant les mêmes observables plafonnent loin du teacher, l'information nécessaire est absente ou mal représentée.

Le diagnostic doit répondre à :

```text
Quelle fraction du signal q1000 est représentable par les features de production actuelles ?
```

---

## 5. Étape D — probe conjoint T + D

### Motivation

M5 peut indiquer non seulement que la distillation `teacher -> T` est difficile, mais aussi que la contrainte **PatternEval-only** détruit une grande partie de l'information disponible.

Il faut donc tester explicitement une seconde hypothèse :

```text
(T, D) -> J
```

au lieu d'imposer uniquement :

```text
D / q1000 -> T
```

`J` est un évaluateur conjoint appris contre les **mêmes labels deep q200**, sans refit opportuniste des cohorts de confirmation.

### D1. Stack minimal — test prioritaire et peu coûteux

Première expérience : un modèle léger prenant au minimum :

```text
T_score
D_score
phase
parent colour
piece count
legal move count
D margin / confidence si défini sans fuite
```

Tester d'abord un modèle linéaire/logistique, puis un petit MLP seulement si preregistré.

Question :

```text
T et D contiennent-ils une information complémentaire exploitable au-delà de D seul ?
```

Comparer sur fresh :

- `T0` ;
- `D1` ;
- `J(T,D)` ;
- `q1000` ;
- référence `q200`.

### D2. Joint full-features

Si le stack minimal est positif, tester :

```text
[PatternEval features, D features, T score, D score] -> J_full
```

Objectif : estimer la capacité maximale de la **représentation combinée** avant d'inventer de nouvelles features.

### D3. Residual D-on-T

Architecture particulièrement intéressante pour le runtime :

```text
J(x) = T(x) + Delta_D(x)
```

avec `Delta_D` appris uniquement pour corriger le résidu du champion vers le teacher/deep target.

Cela évite de demander à `D` de reconstruire toute l'évaluation et mesure directement la complémentarité des deux représentations.

### Métriques

Publier au minimum :

- pairwise/top-hit de `T`, `D`, `J`, `q1000` sur le même cohort ;
- `J-D` et `J-T` bootstrap CIs ;
- fraction du headroom q1000 récupérée par `J` ;
- asymétries d'erreur `T correct/D faux`, `D correct/T faux`, et celles corrigées par `J` ;
- calibration / stabilité par phase et couleur ;
- coût runtime projeté puis mesuré seulement si le probe offline est suffisamment positif.

### Interprétation structurante

Cas 1 :

```text
T ~60%, D ~73%, J >> D, q1000 ~94%
```

Alors l'information est largement présente dans les signaux `T+D` mais la compression vers PatternEval la détruit. **Le goulot est architectural / distillation, pas principalement la collecte de nouvelles features.**

Cas 2 :

```text
T ~60%, D ~73%, J ~74-76%, q1000 ~94%
```

Alors même la combinaison T+D reste loin du teacher. Il manque vraisemblablement des observables représentant le calcul dynamique de la recherche : passer à l'étape E.

### Règle scientifique

Le joint est une **branche expérimentale distincte**, pas un moyen de sauver post hoc T1. Cohorts, architecture, objectifs, seeds et gates doivent être preregistrés avant lecture fresh.

L'ancien échec du `D` utilisé comme **move-ordering** ne ferme pas cette branche : intégrer `D` dans un évaluateur conjoint est un mécanisme causal différent et doit être jugé séparément.

---

## 6. Étape E — ajouter des features seulement si le manque est démontré

Les features ne sont pas ajoutées parce qu'elles semblent plausibles ; elles doivent expliquer les erreurs résiduelles du teacher que **ni PatternEval optimisé, ni les probes riches sur ses entrées, ni le modèle conjoint T+D** ne parviennent à capturer.

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
6. admission dans la représentation uniquement si gain reproductible.

---

## 7. Étape F — campagne teacher optimisée → T2 / meilleur student

Une fois le mécanisme de transfert, la capacité et le feature set stabilisés, relancer une campagne complète d'apprentissage depuis un teacher court optimisé.

Teacher primaire : **micro-search court optimisé**, actuellement 1000 nœuds sauf nouvelle preuve preregistrée.

Baseline/prior :

- `CURRICULUM` si aucun nouveau champion n'a été validé ;
- sinon le champion nouvellement promu.

Deux sorties doivent être distinguées :

### Voie F1 — student PatternEval pur

```text
champion T_base
  -> teacher micro-search optimisé
  -> corpus large et disjoint
  -> transfert PatternEval optimisé
  -> représentation validée
  -> T2
  -> deep fresh confirmation
  -> force pools disjoints
```

### Voie F2 — student conjoint si D a démontré une complémentarité forte

Si l'étape D établit un gain fresh important et un coût runtime acceptable :

```text
champion base
  -> teacher micro-search optimisé
  -> représentation conjointe T+D validée
  -> J2 / residual-D-on-T
  -> deep fresh confirmation
  -> force pools disjoints
```

Ne pas forcer artificiellement la voie conjointe à retourner dans `PatternEval` si l'expérience a précisément montré que cette compression détruit l'information.

La promotion ne se fait que sur force robuste et protocole séparé. `T2` ou `J2` doit être considéré comme le premier candidat produit par un **pipeline teacher -> student réellement optimisé**, pas comme un simple patch de `T1`.

---

## 8. Étape G — expérience from-scratch / multi-points d'entrée

### Question finale

Une fois la procédure teacher→student stabilisée, vérifier si elle constitue un véritable opérateur d'amélioration qui converge vers un optimum reproductible.

Créer plusieurs lignées indépendantes avec :

- teacher optimisé dès le départ ;
- plusieurs seeds ;
- plusieurs points d'entrée / initialisations ;
- même représentation student sélectionnée (`T` pur ou joint si validé) ;
- mêmes règles de transfert et mêmes budgets ;
- validation mutuellement disjointe.

Schéma :

```text
B1 --teacher--> S1a --teacher--> S2a ...
B2 --teacher--> S1b --teacher--> S2b ...
...
Bk --teacher--> S1k --teacher--> S2k ...
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
force(S_g+1) - force(S_g)
```

sur plusieurs générations, plusieurs lignées et pools fresh.

---

## 9. Ordre d'exécution verrouillé

```text
A. Évaluer le transfert d'information T0/D1/q1000/T1
        ↓
B. Optimiser la recette de transfert PatternEval — max R_1000
        ↓
C. Mesurer la capacité d'absorption des features PatternEval actuelles
        ↓
D. Tester la représentation conjointe T+D sur les mêmes labels fresh
        ↓
E. Ajouter de nouvelles features seulement si les plafonds C et D le justifient
        ↓
F. Relancer teacher optimisé → T2 ou student conjoint validé
        ↓
G. Tester from scratch / multi-entry / multi-seed et la convergence
```

Ne pas sauter directement de A à E : un faible transfert peut venir de la recette ou de l'architecture et non des features.

Ne pas interpréter `J(T,D)` sur le cohort de training : toute décision d'architecture doit reposer sur une confirmation fresh preregistrée.

Ne pas sauter directement du meilleur pairwise à l'Elo : d'abord confirmer le mécanisme sur un cohort fresh, puis faire le gate causal de force.

---

## 10. Métriques de pilotage principales

| Niveau | Métrique principale | Question |
|---|---|---|
| Teacher | pairwise q1000 vs q200 | Le teacher produit-il l'information ? |
| Transfert PatternEval | `R_1000` | Quelle fraction de cette information passe dans T ? |
| Capacité PatternEval | meilleur pairwise possible avec features actuelles | L'information est-elle représentable dans T ? |
| Joint T+D | pairwise `J` vs q200 et delta `J-D` | Les deux représentations sont-elles complémentaires ? |
| Features | delta pairwise fresh + coût runtime | Une nouvelle observable paie-t-elle ? |
| Student | pairwise/top-hit student vs q200 | Le student a-t-il réellement absorbé le teacher ? |
| Force | native 0.1s paired Elo | Le gain d'éval se convertit-il en parties gagnées ? |
| Convergence | gain inter-génération multi-seed | Le procédé compose-t-il et vers quel optimum ? |

---

## 11. Principe directeur

La question scientifique n'est plus seulement :

> « Comment gagner quelques Elo ? »

Elle devient :

> **Peut-on construire un opérateur reproductible qui transforme de la recherche courte mais informative en un évaluateur étudiant de plus en plus fort — PatternEval pur si la compression fonctionne, ou représentation conjointe compacte si elle est réellement supérieure — et vers quel optimum cet opérateur converge-t-il ?**

C'est désormais l'axe prioritaire de L3.
