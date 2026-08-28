# L3 — Teacher distillation roadmap

> **Mis à jour : 28 août 2026**
> **Statut : roadmap active après le screen terminal Transfer / Capacity / Joint T+D.**
>
> Situation courante : [`L3_CURRENT.md`](L3_CURRENT.md). Protocole du screen : [`experiments/L3_TRANSFER_CAPACITY_JOINT_V1_20260828.md`](experiments/L3_TRANSFER_CAPACITY_JOINT_V1_20260828.md).

## 1. Ce que nous savons maintenant

Le teacher micro-search est établi et très informatif : sur deep fresh, ~1000 nœuds récupèrent la majorité du signal manquant par rapport à `CURRICULUM`.

La première distillation `q1000 -> PatternEval T1` a cependant presque tout perdu : le diagnostic post-M5 donne `R_1000≈0.0068` contre q200. Cela a motivé le screen A/B/C sur M3 uniquement.

Le screen terminal `cpx62-1614-l3-transfer-capacity-joint-screen-v2`, attempt `20260828T092856Z-d8241edc`, puis son readout compact `cpx62-1615-l3-transfer-capacity-joint-readout-publish-v1`, attempt `20260828T100556Z-d8241edc`, établissent quatre faits :

1. **la recette de transfert importe** : margin-weighting + L2 adapté bat nettement la recette M4 ;
2. **PatternEval linéaire/anchor est un vrai plafond** : un probe non linéaire sur les mêmes observables absorbe beaucoup plus de q1000 ;
3. **la quantification int32 est presque négligeable** ;
4. **T et D sont complémentaires** : le stack minimal T0+D1 bat significativement D1 seul ;
5. malgré cela, **les observables statiques restent loin du teacher**.

La roadmap doit donc poursuivre trois objectifs coordonnés :

```text
meilleur transfert pur-T
        +
student joint T+D plus expressif
        +
nouvelles observables ciblées sur le résidu q1000
```

---

## 2. Résultats de référence du screen A/B/C

### Split et anti-leakage

- source : M3 uniquement ;
- split parent-cluster seed `2026090401` ;
- TRAIN `80161`, DEV `19839` parents ;
- overlap parent/canonique `0` ;
- M5/1612 fit reads `0` ; model-selection reads `0` ;
- nouveaux q200 labels `0` ;
- selfplay/strength/promotion `0`.

Sur les parents DEV contribuant aux métriques : `19503` parents, `854040` paires.

### Attention à la cible

Dans ce screen, `micro1000=1.0` parce que q1000 est **la cible d'imitation**. Ces chiffres mesurent la capacité à reproduire q1000 sur M3 DEV ; ils ne sont pas des accuracies deep q200.

Baselines :

| Modèle | Pairwise q1000 | Top-hit |
|---|---:|---:|
| T0 | 0.6142493 | 0.2675315 |
| D1 | 0.6569985 | 0.2362201 |
| q1000 cible | 1.0000000 | 1.0000000 |

---

## 3. Voie A — PatternEval pur reste utile, mais secondaire

Le meilleur arm sous G0/G1/G2 est :

```text
A6_MARGIN_L2_1E5
```

Résultats :

| Guard | Pairwise | Top-hit | Scale |
|---|---:|---:|---:|
| G0 12/35 | 0.6197134 | 0.2733767 | 0.39172 |
| G1 20/60 | 0.6229890 | 0.2746176 | 0.66589 |
| G2 35/100 | 0.6262529 | 0.2764404 | 1.0 |

A0/M4 réplication : G0 `0.6158687`, G1 `0.6168534`, G2 `0.6171719`.

### Lecture

La margin-weighting est une amélioration reproductible de recette. Le candidat pur-T à porter en priorité vers une future confirmation est **A6-G0**, car il respecte le guard production-like original.

Mais A6-G0 ne récupère qu'environ `1.4 %` du gap T0→q1000 de ce DEV ; G2/unanchored ~`3.1 %`. La distillation pure PatternEval ne suffit pas comme axe unique.

### Règle

Ne plus multiplier les petits DOE PatternEval avant confirmation fresh. A6-G0 devient le représentant pur-T de cette famille pour le prochain protocole q200.

---

## 4. Voie B — changer l'architecture du student

### B0 : quantification disculpée

B0 float `0.6264145`, int32 `0.6262529` ; perte pairwise seulement `0.0162 pp`.

Donc :

```text
int32 quantization != goulot principal
```

L'anchor compte davantage que la quantification, mais même sans anchor le plafond linéaire reste faible.

### B1 : mêmes observables, modèle non linéaire

B1 :

- pairwise `0.6532856` ;
- top-hit `0.2666769` ;
- delta vs T0 bootstrap `+3.9037 pp`, CI95 `[+3.6624 ; +4.1445] pp`.

Il utilise les mêmes observables statiques de production, sans D ni search score comme input.

### Décision

**La prochaine génération de student ne doit pas être contrainte à reproduire exactement la forme linéaire historique de PatternEval.**

Il faut concevoir une architecture compacte et runtime-compatible qui conserve :

- déterminisme ;
- symétries/invariances ;
- coût mesurable ;
- serialization simple ;
- aucun search score à l'inférence.

B1 est un probe de capacité, pas un candidat de production tel quel.

---

## 5. Voie C — le joint T+D devient prioritaire

Le résultat central est C0 :

```text
C0 = stack minimal [T0 scalar, D1 scalar, phase, parent colour]
```

Résultats :

| Modèle | Pairwise | Top-hit |
|---|---:|---:|
| D1 | 0.6569985 | 0.2362201 |
| B1 | 0.6532856 | 0.2666769 |
| C0 | **0.6726851** | **0.3072861** |
| C1 residual D-on-T | 0.6185354 | 0.2680100 |
| C2 full linear joint | 0.6314341 | 0.2824181 |

C0−D1 pairwise bootstrap : mean `+0.0156777`, CI95 `[+0.0140121 ; +0.0172940]`.

### Décision

**La complémentarité T+D est établie sur le target q1000 de M3 DEV.**

Le prochain candidat joint doit partir de la simplicité de C0, pas de C1/C2 qui ont moins bien fonctionné.

Cependant C0 n'est qu'un probe offline. Avant toute confirmation fresh, il faut :

1. définir une représentation de modèle sérialisable et immuable ;
2. figer les coefficients/normalisations et le contrat de score ;
3. définir le chemin runtime exact de calcul D1 + T0 + stack ;
4. mesurer un coût micro-benchmark sans encore faire de force game ;
5. prouver OFF/ON/fail-closed et les symétries nécessaires.

L'ancien FAIL de DSSD **move-ordering** ne s'applique pas : le joint evaluator est un mécanisme causal distinct.

---

## 6. Voie D — nouvelles observables ciblées deviennent justifiées

Même le meilleur C0 atteint seulement `0.6727` contre une cible q1000 à `1.0` sur ce screen. Il récupère environ `15.1 %` du gap T0→q1000 ; la majorité reste inaccessible aux observables statiques actuelles.

On a maintenant la preuve nécessaire pour ouvrir la feature discovery, mais elle doit être **résiduelle et ciblée**, jamais un feature creep général.

### Corpus d'erreurs à analyser

Priorité aux paires où :

```text
q1000 correct / C0 wrong
q1000 correct / B1 wrong
q1000 correct / D1 wrong
```

et spécialement aux erreurs communes B1+C0, car elles sont le meilleur indicateur d'information absente plutôt que de simple architecture inadéquate.

### Familles candidates

À sélectionner seulement après autopsie quantitative :

- captures multiples et séquences forcées courtes ;
- relations multi-pièces / alignements / blocages ;
- mobilité conditionnelle après coup ;
- accès promotion / timing de promotion ;
- parity / tempo / zugzwang-like motifs ;
- king interaction / king mobility structurée ;
- échange/vulnérabilité après simplification ;
- résumés statiques appris des premiers plies de PV q1000, à condition d'être calculables sans search runtime.

Chaque famille doit passer une ablation offline M3-only avant toute admission runtime.

---

## 7. Prochaine expérience — preregistration fresh q200 séparée

**Aucun fresh q200 n'a encore été lancé.**

Le prochain protocole doit être écrit et mergé avant génération/lecture du cohort réservé.

### Candidats minimums

Le protocole doit comparer au moins :

1. `T0 = CURRICULUM` baseline ;
2. `A6-G0` pure-T, bytes gelés ;
3. un `J0` joint dérivé de C0, sérialisé et gelé ;
4. D1 scellé et micro1000 comme diagnostics, pas comme promotion candidates.

Éviter de tester une multiplicité large : les choix A6 et C0 ont déjà été faits sur M3 DEV.

### Cohort réservé

- exactement `4000` nouveaux parents ;
- `1000` par phase ;
- selection seed `2026090420` ;
- disjoint de M1/M2/M3/M5 et force pools ;
- même contrat stable q50/q200 ;
- micro1000 exact sur les mêmes siblings ;
- parent-cluster bootstrap `100000`, seed `2026090421`.

### Gates à preregistrer avant labels

Pour chaque candidat, au minimum :

- pairwise vs q200 et CI vs T0 ;
- top-hit et CI vs T0 ;
- phases/couleurs ;
- ratio de récupération du headroom q1000 ;
- déterminisme/serialization ;
- pour J0, D1/T0 artifacts exacts et aucune asymétrie de score.

Le PASS permettant un test Elo doit être fixé dans ce document avant le cohort fresh.

---

## 8. Après confirmation fresh

### Si A6-G0 confirme mais J0 non

Poursuivre la voie student statique pur avec architecture non linéaire inspirée de B1, puis nouvelle confirmation avant Elo.

### Si J0 confirme au-dessus de D1 et T0

Le joint devient la voie student principale. Étapes :

```text
J0 fresh q200 PASS
  -> micro-benchmark/runtime integration
  -> preregister force gate
  -> native 0.1s paired pools
  -> promotion seulement si force robuste
```

### Si ni A6 ni J0 ne récupèrent suffisamment de deep signal

Prioriser immédiatement la feature discovery résiduelle de la section 6. Ne pas relancer une série de petits retunes L2/anchor.

---

## 9. Construction de T2 / J2 et convergence

Une fois la représentation student choisie :

```text
champion/base
  -> teacher micro-search court
  -> corpus large disjoint
  -> student sélectionné (T pur ou J joint)
  -> fresh deep confirmation
  -> force gate
  -> promotion éventuelle
```

Puis tester l'opérateur d'amélioration sur plusieurs points d'entrée/seeds :

```text
B1 -> S1a -> S2a ...
B2 -> S1b -> S2b ...
...
```

Question finale : la procédure teacher→student converge-t-elle vers un optimum supérieur et reproductible, ou reste-t-elle dépendante du bassin initial ?

---

## 10. Métriques de pilotage

| Niveau | Métrique | Question |
|---|---|---|
| Teacher | q1000 vs q200 fresh | Le lookahead crée-t-il le bon signal ? |
| Pure transfer | R_1000 / pairwise fresh | Combien passe dans T ? |
| Architecture | B1-like ceiling | Les observables actuelles sont-elles exploitables avec plus de capacité ? |
| Joint | J−D / J−T fresh | T et D sont-ils complémentaires contre deep ? |
| Feature residual | gain sur erreurs B1+C0 | Une nouvelle observable capture-t-elle du signal absent ? |
| Runtime | coût eval / NPS / depth | Le student est-il économiquement utilisable ? |
| Force | native paired Elo | Le gain d'eval gagne-t-il des parties ? |
| Convergence | gain inter-génération multi-seed | L'opérateur compose-t-il ? |

---

## 11. Règles verrouillées

1. `CURRICULUM` reste champion jusqu'à force robuste.
2. M3 DEV peut sélectionner A6/C0 ; il ne doit jamais être appelé fresh.
3. Le futur cohort q200 réservé ne doit pas influencer architecture, hyperparamètres ou candidate selection avant prereg.
4. q1000 imitation, q200 accuracy et Elo sont trois niveaux distincts.
5. Pas de promotion offline.
6. Pas de réouverture du DSSD move-ordering.
7. Quantification int32 n'est plus une priorité de recherche.
8. Les nouveaux efforts doivent viser architecture joint/non-linéaire et observables résiduelles, pas un retuning infinitésimal de T1.

---

## 12. Principe directeur

La question L3 est maintenant :

> **Quelle représentation statique compacte peut conserver le plus possible de l'information créée par ~1000 nœuds de recherche, tout en restant assez rapide pour convertir ce gain en force réelle ?**

Le screen A/B/C a répondu à la première bifurcation : le futur student ne doit plus être pensé comme un simple `PatternEval` linéaire retuné. Le joint `T+D` et une architecture plus expressive sont désormais des voies de premier rang, avec feature discovery ciblée pour le signal qui reste hors de portée.
