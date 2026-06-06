# Programme « pattern compétitif » — notes & items de suivi

> Rédigé 2026-06-06. Consolide la réévaluation de l'approche pattern et les
> points à surveiller. But : ne pas refaire / ne pas oublier.

## Contexte

Le verdict historique « le pattern est faible » reposait sur **4 confondants
empilés**, tous corrigés dans cette série :

| # | Confondant | Corrigé par |
|---|---|---|
| 1 | Labels de distillation sales (~18 % de faux labels, captures forcées) | relabel fixé (#203) → 0141 |
| 2 | Jugé en **profondeur fixe** (la vitesse ~100× du pattern est invisible) | bench **movetime** (0141/0142) |
| 3 | Recherche réglée pour le **NNUE** (marges cp ≠ distribution pattern) | SPSA **pour le pattern** (#206/#209) → 0141 |
| 4 | Training **non search-aware** (scores statiques) | **TD-leaf(λ)** (#207) → 0142 |

Chaîne de jobs : **0141** (pattern propre + SPSA complet) → **0142** (TD-leaf
jusqu'à convergence) → **0143** (vs Scan, *en pause*, déclenché délibérément
après convergence).

## Couplage search↔éval : état

- ✅ **Toutes les marges cp** de la recherche (RFP, razoring, singular,
  probcut, NMP, LMP, LMR, fenêtre d'aspiration) sont dans le set SPSA →
  tunées **pour le pattern** par 0141 (#209). razoring/probcut/ext inclus :
  le pattern décide lui-même s'ils l'aident (pas le verdict NNUE de 0138).
- ✅ **Quiescence** : purement structurelle (captures forcées), **aucune**
  marge éval → rien à adapter.

## Items de suivi (watch-list)

### 1. Time-management à HAUTE profondeur  *(à surveiller — déclencheur ci-dessous)*

Le pattern (~100× plus rapide) atteint des profondeurs bien supérieures au
NNUE en movetime (depth 25-35+). Or deux heuristiques ont été pensées pour
le régime de profondeur du NNUE, **pas** pour ce régime :
- le **saut d'itération** (« projette la prochaine itération à ~2× le coût »),
- le **doublement d'aspiration** sur fail-high/low.

Ce ne sont **pas** des marges en cp (le SPSA ne les couvre pas) — c'est un
régime de profondeur.

**Déclencheur** : si, pour le pattern, `rate(vs v15 @ movetime) <
rate(vs v15 @ depth fixe)`. Un pattern rapide devrait faire **mieux** en
movetime (il creuse plus) ; s'il fait **pire**, sa recherche profonde ne
paie pas → suspecter (a) le time-mgmt/aspiration inadaptés à la haute
profondeur, ou (b) une instabilité de l'éval en profondeur.

**Action si déclenché** : tuner saut-d'itération + aspiration pour le régime
haute profondeur (ou diagnostiquer la stabilité de l'éval). 0141 et 0142
émettent un avertissement automatique si la condition est vue.

### 2. Échelle/distribution des scores du pattern  *(risque faible, géré)*

Calibrée par le training (le pattern apprend des cibles en cp) + le SPSA
absorbe le résiduel dans les marges. À monitorer, pas d'action a priori.

### 3. Accumulateur NNUE incrémental  *(non applicable)*

Le pattern n'emprunte pas le fast-path `MLPNetworkQ` (chemin éval générique).
Pas un problème de calibration ; aucune action (le pattern est déjà rapide).
