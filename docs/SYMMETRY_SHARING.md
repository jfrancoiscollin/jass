# Symmetry weight-sharing — audit vs Scan & implementation plan

> **Thesis (validée).** Scan's eval est une **classe LINÉAIRE** de patterns et atteint
> ~2500 Elo. Donc une géométrie linéaire bien montée DOIT pouvoir y arriver. Si on
> plafonne, il manque une **brique** — et il est hors de question de compenser une archi
> linéaire mal montée par du non-linéaire. **La brique manquante = le PARTAGE DE POIDS par
> le groupe de symétrie du damier (couleur + rotation 180° + réflexion + translation).**

## Audit (vérifié sur la source `rhalbersma/scan`, `src/eval.cpp`)

| Dimension | jass (nous) | Scan | Verdict |
|---|---|---|---|
| États/case | 3 (vide/pion-N/pion-B), **men-only** | 3, men-only | identique |
| Taille pattern | 12 cases | 12 cases | identique |
| Phase | MG/EG, `stage/40` | MG/EG, `Stage_Size=300` | + fin chez Scan (mineur) |
| Extras | king-PST + matériel + mobilité + balance | idem | identique |
| Entraînement | logistique WDL self-play | logistique WDL self-play | identique |
| **Tables de poids** | **32 indépendantes, positions fixes** | **4** (`4·3¹²`, `P=2 125 820`) | **8× trop** |
| **Antisym. couleur** | ✗ (N=1, B=2 → buckets indépendants) | ✓ `index = Trits[N] − Trits[B]` | **MANQUE** |
| **Rotation 180°+couleur** | ✗ | ✓ (bottom = tables inversées, `−index,−1`) | **MANQUE** |
| **Réflexion** | ✗ | ✓ `Perm_0`/`Perm_1` | **MANQUE** |
| **Translation** | ✗ (`v_top_0..3` = 4 tables séparées) | ✓ (1 bande glissée `wm>>0..3`) | **MANQUE** |

Tout l'écart est **linéaire** : COMMENT les poids sont liés. Le reste (états, taille,
phase, extras, objectif) est identique.

## Pourquoi c'est LE mur (mécanisme, cohérent avec nos mesures)
- Mesuré : sur 17M buckets, ~1M occurrents, **~38 % des touchés ont ≤2 visites** → la
  plupart des poids sont du bruit (prior L2). L'eval ≈ matériel + petite tête fréquente.
- Scan : ses ~2.1M poids sont chacun nourris par **toutes** les translations × 2 couleurs ×
  rotation × réflexion d'une structure locale → estimation DENSE, généralisation.
- Lier nos buckets sur l'orbite (couleur ×2 · rot ×2 · réflexion ×2 · translation ×4-8 ≈
  **16-32×**) effondre ~1M buckets affamés en **~30-60k poids denses** → bien estimés.
- Ça **réécrit aussi le besoin en data** : les ~30-60M positions estimées pour une table
  NON partagée tombent à une fraction → l'échelle Scan redevient atteignable.

Cohérence : le plateau proxy ~0.46 ET la montée Elo lente (B4 : +80 en 5 gens) sont les
deux symptômes de poids non partagés sous-entraînés. Le partage doit **relever le plafond
ET accélérer la montée**.

## Plan d'implémentation — INCRÉMENTAL (chaque phase testable au BON gauge = Elo réel)

> Métrique de test : **Elo réel** (vs handcrafted, commun, pas cher) + SPRT — PAS le proxy
> (cf B4 : le proxy ment). A/B : même boucle WDL cumulée, archi partagée vs non partagée.

- **Phase 1 — Antisymétrie COULEUR** (la plus locale, ~2×, exacte). Encodage ternaire SIGNÉ
  par case (N=+1, B=−1, vide=0) → `idx_signé = Σ cell_k·3^k ∈ [−M,+M]`, `M=(3¹²−1)/2=265720`.
  Canonique : `bucket = |idx_signé|`, `signe = sgn(idx_signé)` ; l'eval ajoute
  `signe · W[offset + bucket]`. Un config et son échange-couleur PARTAGENT un poids
  antisymétrique. `BUCKETS_PER_PATTERN : 531441 → 265721`, total 17M → 8.5M. Eval
  intrinsèquement nul-somme. Changement localisé : `patterns.py` (extract → (bucket,signe)),
  `scan_eval.cpp`/`pattern.hpp` (lecture signée), `train.py` (design signé ±1), nouveau
  format `.pjtw` (n_pat = 8.5M) ou flag de version.
- **Phase 2 — Rotation 180° + couleur** (l'autre moitié de la symétrie cœur de Scan). Lier
  pattern P avec rot180(P) (ex. `v_top_0 ↔ v_bot_3`) via index signé inversé. ~2× de plus.
- **Phase 3 — Réflexion gauche-droite + TRANSLATION** (réduction des 32 tables vers ~peu de
  formes glissées, à la Scan). Le gros 8× de réduction de tables. Refonte géométrie →
  1 forme (bande 6×2) glissée + canonicalisée, comme `indices_column` de Scan.

On implémente **Phase 1 d'abord**, on la teste en Elo réel vs la baseline non partagée. Si
ça monte plus haut/vite → Phase 2, puis 3. On vise la géométrie Scan-fidèle complète.

## Statut (2026-06-13) — TOUTES LES BRIQUES IMPLÉMENTÉES + VÉRIFIÉES
- **A (vérif source Scan)** : FAIT (constantes citées).
- **B (plan + docs)** : ce document + ARCHITECTURE.md (§ Symmetry weight-sharing).
- **Implémentation** (train.py replie puis ré-étend vers .pjtw 17M std, C++ inchangé) :
  - `--color-fold` (8.5M) · `--rot-fold` (4.9M, rot∘cs EXACT) · `--trans-fold` (1.2M)
    · `--full-fold` +réflexion LR EXACTE (1.0M). Symétries exactes vérifiées (0 viol).
  - `gen_patterns.py --lr-close` → géométrie 54 patterns fermée {rot180,LR} (0
    orphelin) → full-fold = **0.6M poids ≈ échelle Scan**. C++ build+tests OK.
- **Test** : A/B « échelle » en **Elo réel** (le proxy ment, cf B4/0216). Bras
  0220-0224 (32-pat) en cours ; LR-close 0225/0226 prêt (déployé après l'A/B).
- **Reste** (optimisation, pas correctness) : éval 54-pat ~1.7× plus lente →
  calculer chaque orbite de symétrie UNE fois dans le C++ (au lieu de N patterns liés).
