# L3 B3 — real adaptive sibling teacher v1 / implementation-parity contract

Date : 2026-09-06

Statut : **IMPLEMENTATION + TECHNICAL/CAUSAL PARITY CONTRACT**. Ce document n'autorise pas encore une nouvelle cohorte fraîche B3 ni un fit.

## 1. Prérequis terminal B2

B3-v1 est ouvert uniquement parce que le terminal B2 suivant est acquis :

```text
job      cpx62-1831-l3-decision-math-b2-statistical-completion-legacy-support-json-compat-v3
attempt  20260906T105358Z-bebadf91
verdict  B2_ADAPTIVE_SHADOW_POLICY_CONFIRMED_V1
R        200000
seed     2026110717
all_gates_passed = true
```

La science B2 confirmée est immuable :

```text
M5 = 100 cp
M50 = 60 cp
minimum_survivors = 2 lorsque possible
budgets = 5000 -> 50000 -> 200000 nœuds exacts
CURRICULUM uniquement
```

Aucun seuil n'est retuné dans B3-v1.

## 2. Question B3-v1

Le simulateur B1/B2 a montré qu'une allocation staged peut économiser du compute sans casser les gates confirmatoires. B3-v1 pose une question d'implémentation causale distincte :

> un **vrai** teacher qui n'exécute réellement que les recherches autorisées par la policy confirmée reproduit-il exactement, sur les parents B2 déjà consommés, les décisions et coûts simulés par les reçus B2 ?

Ce gate utilise la cohorte B2 uniquement comme fixture de parité déjà consommée. Il ne produit aucun nouveau résultat confirmatoire B2/B3 et ne peut pas servir à retuner la policy.

## 3. Teacher réel gelé

Pour chaque parent, le catalogue des actions est le catalogue légal sémantique trié comme B2.

### 3.1 Exactitude

1. si au moins une action a `exact_parent_utility=+1`, choisir la plus petite action sémantique exacte gagnante ; **0 search** ; raison `EXACT_WIN` ;
2. sinon, si toutes les actions sont exactes, choisir le plus petit draw exact s'il existe, sinon la plus petite loss exacte ; **0 search** ; raisons `ALL_EXACT_DRAW|ALL_EXACT_LOSS` ;
3. sinon seules les actions non exactes entrent dans le racing.

### 3.2 Racing confirmé

Pour les non-exacts :

1. recherche 5k réelle sur toutes les actions non exactes ;
2. `S5` = toutes les actions dans 100 cp du meilleur q5, puis top-2 minimum lorsque possible ; tie-break action sémantique croissante ;
3. recherche 50k réelle **uniquement** sur `S5` ;
4. `S50` = même règle avec marge 60 cp et minimum deux ;
5. si `|S50|=1`, choisir cette action, ne lancer aucun q200, publier `SOLE_UNRESOLVED_BEFORE_Q200`, `uncertified=true` ;
6. sinon lancer 200k réel **uniquement** sur `S50` puis choisir q200 maximum, tie-break action sémantique croissante.

Il est interdit de lire, calculer ou brancher sur q200 avant que `S50` soit scellé.

## 4. Search/runtime contract

Chaque recherche 5k/50k/200k :

```text
fresh Engine per sibling per budget = true
fresh TT per search = true
book = OFF
threads = 1
TT = 16 MiB
node limit mode = Exact
CURRICULUM = byte-pinned champion
EGDB = ON, explicit path, explicit 256 MiB cache
JASS_* inherited environment = empty
```

Aucune warm TT, continuation 5k->50k->200k, aspiration state partagée ou reuse d'Engine n'est autorisée dans v1. Une variante incrémentale serait un facteur séparé.

## 5. Outputs natifs

Le teacher écrit :

- tous les enfants légaux zero-target ;
- une ligne action par action ;
- observations uniquement pour les horizons réellement exécutés ;
- flags `searched5/searched50/searched200` ;
- flags `survived5/survived50/selected` ;
- raisons exact/sole-survivor ;
- compteurs réels de recherches et de nœuds.

Les horizons non exécutés ont des valeurs neutres mais sont toujours distingués par leur flag `searched*=false`. Ils ne deviennent jamais de faux labels zéro.

## 6. Parity gate obligatoire avant toute fraîcheur B3

Source : **exactement les 4 000 parents B2 déjà consommés**, sans nouvelle sélection.

Le checker compare le real adaptive teacher aux artefacts B2 full-teacher + projection, parent/action par parent/action.

PASS exige simultanément :

1. `parents=4000` et mêmes catalogues d'actions légales ;
2. aucune cible parent/enfant non nulle ;
3. pour toute recherche réelle exécutée en B3, score/nœuds/profondeur/stop/PV-EGDB égaux à l'observation B2 du même horizon (elapsed exclu) ;
4. `searched5` exactement égal aux actions non exactes sauf shortcut exact parent ;
5. `survived5` exactement égal à `S5_rows` B2 ;
6. `searched50` exactement égal à `S5_rows` B2 ;
7. `survived50` exactement égal à `S50_rows` B2 ;
8. `searched200` exactement égal à `S200_charge_rows` B2 ;
9. action `selected` exactement égale au choix B2 final : pre-q200 choice lorsqu'il existe, sinon argmax q200 sur `S200_charge_rows` avec le même tie-break ;
10. somme réelle des nœuds 5/50/200 par parent exactement égale à `shadow_nodes_total` B2 ;
11. les six parents exact-zero-cost B2 restent à `0/0` ;
12. aucune recherche q200 sur une action éliminée ;
13. aucune recherche q50 sur une action éliminée à 5k ;
14. aucune lecture/branche q200 avant scellement ;
15. fit/strength/promotion/bake = 0.

Verdict technique unique de succès :

```text
B3_REAL_ADAPTIVE_TEACHER_PARITY_ESTABLISHED_V1
```

Toute divergence est un **STOP technique**, jamais un verdict scientifique négatif.

## 7. SearchDecisionTrace

A1/A2/A3 est disponible, mais B3-v1 **ne l'utilise pas pour modifier l'allocation**. La policy reste strictement celle confirmée par B2.

Une future B3-v2 peut enregistrer ou utiliser des bornes/certificats pour safe-dominance, mais seulement comme facteur séparé après v1. Aucun changement `100/60/2` n'est caché derrière les bounds.

## 8. Suite après PASS

Après le parity gate seulement, une nouvelle preregistration `B3 fresh adaptive corpus` devra geler avant génération :

- nouveaux seeds de source/sélection ;
- exclusion historique + B2 ;
- volume et cellules ;
- métriques d'efficacité réelles ;
- éventuel audit full-ladder indépendant ;
- consommation downstream par SiblingDataset v2.

Aucun fresh B3 job ne doit être lancé par ce contrat seul.
