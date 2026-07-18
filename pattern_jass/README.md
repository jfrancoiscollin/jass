# Phase Pattern-2 — pattern jass minimaliste

> Documenté `docs/archives/ROADMAP.md:362`. Cible : valider que le pipeline
> pattern éprouvé sur Othello (Phase Pattern-1, cf
> `docs/archives/OTHELLO_POC_VERDICT.md`) se transpose proprement sur draughts
> 50-square avec des **8 features Scan-geometry mais code from scratch**.
>
> **Gate 2** : pattern jass ≥ 55% vs handcrafted (eval_basic-équivalent
> draughts) → infra pattern jass fonctionne. Sinon, l'infra pattern
> ne marche PAS sur draughts (raison à investiguer).

## Structure

Standalone, **pas lié au build jass core** (isolation comme la POC
Othello, cf `othello/README.md` §5).

```
pattern_jass/
├── README.md               # ce doc
├── CMakeLists.txt
├── src/
│   ├── pattern.hpp/.cpp    # 8 patterns, extract_indices ternaire
│   └── board_view.hpp      # mini wrapper bitboard (men only)
├── tests/
│   └── run_tests.cpp       # extract sur positions connues + symétries
```

## Géométrie pattern v1 (Day 1)

8 patterns, chacun 10 cases. Encoding ternaire (empty=0, black_man=1,
white_man=2). Total 8 × 3¹⁰ = **472 392 buckets**.

| # | Nom | Squares (FMJD) | Forme |
|---|---|---|---|
| 0 | row_top    | 1..10                                  | 2 rangées du haut |
| 1 | row_2      | 11..20                                 | 2 rangées suivantes |
| 2 | row_mid    | 21..30                                 | 2 rangées du milieu |
| 3 | row_4      | 31..40                                 | 2 rangées suivantes |
| 4 | row_bot    | 41..50                                 | 2 rangées du bas |
| 5 | col_left   | 1, 6, 11, 16, 21, 26, 31, 36, 41, 46   | colonne gauche |
| 6 | col_mid    | 3, 8, 13, 18, 23, 28, 33, 38, 43, 48   | colonne centre |
| 7 | col_right  | 5, 10, 15, 20, 25, 30, 35, 40, 45, 50  | colonne droite |

**Choix design** :
- **Kings exclus** (comme Scan, cf `docs/archives/SCAN_ARCHITECTURE_NOTES.md`
  §3 fin) — kings via PST hors-pattern dans une étape ultérieure.
- **Pas de MG/EG split** pour v1 — ajout possible si Gate 2 marginal.
- Patterns horizontaux + verticaux ≠ Scan (qui fait des verticaux
  longue distance). On garde simple pour cette POC.

## Encoding bitboard

Conformément à `src/bitboard.hpp:5`, bit `i` du `uint64_t` correspond à
**FMJD square (i+1)**. Donc square 1 = bit 0, square 50 = bit 49.

Index ternaire : `idx = sum(cell[sq[k]] * 3^k)` pour `k ∈ [0, 10)`,
avec cell ∈ {0, 1, 2}. Match exact de la convention Othello (cf
`othello/src/pattern.cpp`).

## Étapes Day 1 (ce PR)

- [x] Définir les 8 patterns
- [x] `extract_index(black_men, white_men, pattern)`
- [x] `extract_all(...)` vectoriel
- [x] Tests : empty board, single piece, signs, total bucket count

## Suite (Days 2-5)

- **Day 2** : training pipeline Python L-BFGS sur master 1.6M (label
  WDL d'après résultat de partie master)
- **Day 3** : loader C++ + bench pattern_jass vs handcrafted_jass
- **Day 4-5** : tuning si Gate 2 marginal (MG/EG split, plus de patterns,
  features auxiliaires kings/material)

## Différence avec Phase Pattern-1 Othello

| Aspect | Othello POC | Pattern jass v1 |
|---|---|---|
| Board | 8×8 (64 squares) | 10×10 brick (50 dark) |
| Pièces | 1 type | 2 types (man + king ; on prend men only v1) |
| # patterns | 10 | 8 |
| # squares/pattern | 4 ou 8 | 10 |
| Total buckets | 39 690 | 472 392 (12× plus) |
| Source training | self-play self-supervised | master games WDL |

Le **pipeline** (gen → train L-BFGS → quantize → loader → bench) est
identique à Othello — c'est précisément ce qu'on a validé Phase 1.
