# Phase Pattern-1 — Othello POC implementation plan

> Rédigé 2026-06-02. Prep work anticipée pendant que 0090 cuit. Cible :
> implémentation rapide post-verdict 0090 si MLP confirmé plafond.
>
> But : valider que **notre infra pattern lookup propre fonctionne**
> sur un domaine où Logistello est documenté A à Z. C'est l'étape
> méthodologique que nos 18 tentatives draughts ont skipped.

## 1. Structure répertoire

```
othello/
├── README.md                 # ce doc
├── CMakeLists.txt            # build standalone, pas linké à jass core
├── src/
│   ├── board.hpp             # bitboard 8×8, repr + game state
│   ├── board.cpp             # impl
│   ├── movegen.hpp/.cpp      # générateur coups légaux + flip pieces
│   ├── pattern.hpp/.cpp      # extraction features + eval lookup
│   ├── eval.hpp/.cpp         # pattern eval (sum of pattern weights)
│   ├── search.hpp/.cpp       # alpha-beta basique (no LMR, no TT initially)
│   ├── selfplay.cpp          # gen-data CLI
│   ├── bench.cpp             # vs random + reference engines
│   └── main.cpp              # entry point HUB-style
├── tests/
│   ├── test_board.cpp        # FEN round-trip, position from string
│   ├── test_movegen.cpp      # known positions perft
│   ├── test_pattern.cpp      # feature extraction
│   └── test_eval.cpp         # eval signs/symmetries
├── tools/
│   ├── train_othello.py      # regression linéaire WDL
│   └── pgn_to_wdl.py         # import master games si dispo
└── data/
    └── (self-play datasets, weights bin)
```

## 2. Étapes implémentation (1 semaine)

### Jour 1 : board + movegen (foundation)

- [ ] `board.hpp` : `uint64_t black, white;` + `Color stm;` + `int passes;`
- [ ] `is_legal(sq)`, `apply_move(sq)` (flip bracketed pieces)
- [ ] Movegen tous coups légaux (8 directions, bracket detection)
- [ ] Tests perft : positions initiales, après K coups, count exact
- [ ] Cible : passe perft jusqu'à depth 8

### Jour 2 : pattern features

- [ ] Définir 6-8 patterns canoniques :
  - 4 corners 2×2 (chacun 3^4 = 81 buckets)
  - 4 edges 1×8 (3^8 = 6561 buckets each minus corners overlaps)
  - 2 main diagonals (3^8 = 6561 each)
- [ ] Total ~30-50K weights initialement, scalable
- [ ] `pattern.cpp` : `extract_indices(board, &out[N_PATTERNS])`
- [ ] Tests : positions connues + symétries (rotation/reflection)

### Jour 3 : eval + search basique

- [ ] `eval.cpp` : `sum(weights[pattern_idx[i]])` × phase split MG/EG
- [ ] `search.cpp` : negamax + alpha-beta, qu killer + history (réutilisable
  du code jass au besoin)
- [ ] Pas de TT initialement, focus correctness
- [ ] Bench vs random : eval doit win ≥99% pour validation

### Jour 4 : self-play + WDL gen

- [ ] `selfplay.cpp` : lance K=10K parties self-play, depth=4-6
- [ ] Sample positions à 1/4 plies
- [ ] Label par WDL résultat de la partie
- [ ] Output JNNW-like binary

### Jour 5-6 : training Python + bench

- [ ] `train_othello.py` : régression L-BFGS sur ~500K positions
- [ ] Sortie : weights binaires
- [ ] Reload dans C++, re-bench

### Jour 7 : iterate + decision Gate 1

- [ ] Cible : bat random à >95%
- [ ] Bench vs Edax weakened (~2000 ELO) si possible
- [ ] **Gate 1** : si pattern eval Othello bat random à ≥95% → infra
  pattern propre fonctionne. Continuer Phase Pattern-2 (jass).
- [ ] Si pas même bat random → BUG infra majeur. Debug avant rien d'autre.

## 3. Conventions importantes (à respecter pour transposition vers jass)

### Représentation

- Squares numérotés 0-63, row-major
- Bitboards uint64 (1 = piece presente)
- Side-to-move convention explicite (no implicit, à vérifier perpétuellement)

### Encoding pattern

- Base-3 (empty=0, black=1, white=2) — *exactement comme Scan pour draughts*
- Index = sum(state[sq] × 3^pos) over pattern squares
- Stored as int32 weight per bucket (later switch to int16 + float for sub-tables comme Scan)

### Loss training

- L-BFGS sur logistic loss = MSE sur WDL après tanh
- λ_reg = 1e-5 (L2 standard)
- White-POV labels

### Symétries

- Othello board a 8 symétries (4 rotations × 2 reflections)
- Augmenter le dataset ×8 gratuitement
- Patterns canoniques choisis pour être invariants par classe d'équivalence

## 4. Liens vers code de référence

- **Logistello (Buro 1997)** : papier + thèse
- **Edax** : engine Othello open-source moderne, board.cpp utile comme
  référence movegen
- **Reversi.io** : engines open-source en ligne, niveau ~2000 ELO

## 5. Points d'attention

- **Ne PAS lier au build jass core** : Othello POC doit être isolable,
  pas de risque de pollution
- **Pas de quantization int8 initialement** : float ou int32 simple,
  performance secondaire à correctness
- **Garder le code transposable** : conventions pattern + training
  pipeline doivent ressembler à ce qu'on portera sur draughts

## 6. Gates de décision

**Gate 1 (jour 7)** : bat random >95% → continuer Phase Pattern-2.
Sinon stop, debug infra.

**Gate 2 (extension, optionnelle)** : bat Edax-weakened ~2000 ELO → 
infrastructure éprouvée à un niveau respectable. Confiance pour porter
vers jass.

## 7. Ce que ce POC apporte vs nos 18 tentatives draughts

- **Domaine canonique** : Logistello documenté A à Z, on peut comparer
  exactement (vs flou des patterns Scan)
- **Bench fixe propre** : random + Edax-weak = baselines non-mouvantes
- **Échec révélateur** : si infra rate sur Othello (cas le plus simple),
  on sait que le bug est dans NOTRE pattern code, pas dans le paradigme
- **Code transposable** : si Phase Pattern-2 (draughts) rate après Othello
  réussi, on saura que c'est specific draughts (vs pattern paradigm) qui ne marche pas

## 8. Coût total

- Effort dev : 1 semaine (5-7 jours)
- Compute : négligeable (CPU local)
- Risque : 30% chance de découvrir un bug infra qui sauve les futures
  semaines pattern draughts
