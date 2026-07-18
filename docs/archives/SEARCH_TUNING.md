# Search tuning — le levier dominant (2026-06-18)

> Ouvert après 0332 (la recherche de jass ne scale pas : branchement effectif **2,0/ply
> vs 1,28 pour Scan** → jass ne peut pas atteindre les profondeurs de Scan à temps égal,
> ce qui empêche de compenser le petit gap d'éval ~2 plies de 0330). Lire avec
> [CURRENT.md](CURRENT.md) (état) et [SCAN_METHODOLOGY_GAP.md](SCAN_METHODOLOGY_GAP.md) (règles).

## Méthodo (permanente)
- **Régler/juger la recherche à TEMPS FIXE**, jamais à profondeur fixe (qui sous-évalue
  structurellement tout ce qui *achète de la profondeur* → c'est pour ça que les prunings
  ci-dessous étaient OFF à tort). Self-play A/B : `jass --benchmark-search-params <eval>
  "<A>" "<B>" <depthcap> <pairs> <threads> <movetime_ms>` ; `A-rate>0.5` = A achète du net.
- **vs Scan en UN build** : `calibrate_vs_scan.py --jass-search-params "k=v,k=v"` (le flag
  HUB `--search-params` câblé 2026-06-18 — plus besoin de rebuild/sed pour comparer un réglage
  vs Scan). Comparer à **temps égal** (le gain de profondeur s'y voit) ou depth-égale (éval pure).

## Acquis (baké dans `search_params.hpp`)
- **NMP OFF partout** (`eg_no_nmp=true`) — +97 Elo (0256/0259), zugzwang draughts. **NE PAS rallumer.**
- **Combo depth-buying baké (0336)** : `multicut_min_depth=6, multicut_moves=8, multicut_cuts=2`
  + `razor_max_depth=4`. ≈ **+75 Elo self-play** à temps fixe. Mesure mécanisme : à depth 16 le
  combo cherche **134k nœuds vs 291k** prunings off → **−54 % de l'arbre**.
- probcut / iid / conthist : OFF (n'ajoutent pas / nuisent — 0334/0335/0336).
- Région move-ordering/aspiration/LMP/singular/history (0337) : déjà bien calée (marginal).

## Audit move-ordering / pruning (`src/search.cpp`) — leviers
| # | Constat | Lever / expé | État |
|---|---|---|---|
| 1 | LMP était plafonnée à depth ≤ 3 (codé en dur) | **IMPLÉMENTÉ** : `lmp_max_depth` (défaut 3=inchangé), tail quadratique 2+d+d². −6 % nœuds à =5 (plateau : branchement quiet faible en draughts). À juger en force (0340). | ✅ param |
| 2 | LMR sans terme d'historique (depth+index seul) | **IMPLÉMENTÉ** : `lmr_hist_div` (défaut 0=OFF) : réduit moins les coups à fort historique. Effet nœuds petit (levier qualité). À juger en force. | ✅ param |
| 3 | RFP `rfp_max_depth=5` | home-0007 : `rfp_max_depth=7,margin=70`=0.639 (hc) → re-validé sur éval pattern dans 0340 (rfp7, lmpX_rfp7). | ⏳ 0340 |
| 4 | Captures non ordonnées (`return 0`, l.318) | Mineur (captures forcées, toutes longueur max) — **écarté**. | ✂️ |
| 5 | Éval → ordering | Une éval plus nette améliore l'ordering → l'axe éval reste *additif*. | (phase 2) |

## ⛔ Pistes TESTÉES et MORTES — NE PAS re-tester (2026-06-18)
| Piste | Verdict | Preuve |
|---|---|---|
| **Agrandir la TT** (>16 Mo) | ❌ mort | `--tt-mb` testé : à temps de match (~100-400k nœuds/search) 16 Mo n'est même pas pleine ; à 1,57M nœuds, 256 Mo = **−0,3 % nœuds**, même profondeur. Peu de transpositions en draughts (faible branchement). |
| **Optimiser la movegen captures** (table man-jump précalculée `[case][dir]={over,land}`) | ❌ mort (0 gain) | Implémentée + perft-vérifiée (perft9=35264, perft11=1 666 207 133, nodes identiques) : **0,5966 s vs 0,5925 s baseline** = bruit. La DFS des rafles n'est PAS le goulot ; `neighbour()` déjà optimisé par le compilo. Le « movegen_capture 15,5 % » = détection par-nœud (`reach_all_dirs`, O(1), irréductible) + récursion. **Reverté.** |
| **Captures ordonnées** (promotion/rois d'abord) | ✂️ écarté | Captures forcées, toutes longueur max → peu discriminant (l.318). |
| **Prunings marginaux SUR le combo** (probcut, iid, conthist, **lmp_max_depth, rfp7**) | ❌ ne stackent pas | 0334/0335/0336 + **0342 (90p propre)** : lmp5=0.54, rfp7=0.44, lmp5+rfp7=0.47 = bruit. Le 0.625 de 0340 (72p) était un spike. probcut chevauche razor ; le combo a déjà pris le gain de pruning. |
| **NPS via l'éval** | ❌ non pertinent | profil `--search-profile` : éval = **3,2 %** du temps/nœud (déjà SIMD). Le NPS n'est pas limité par l'éval. |
| **history-malus** (pénaliser quiets ratés) | ❌ marginal/inconclus | codé (`hist_malus`, défaut off). hc local ≈0.52 (neutre) ; pattern 0344 : hm50=0.578 (~1,5σ, non-monotone) — *pas bakeable sur 1 run*. Ordering déjà quasi-optimal. |

> ## 🏁 CHAPITRE RECHERCHE CLOS (2026-06-18)
> **Un seul vrai gain : le combo `multicut(min_depth=6,moves=8,cuts=2)+razor(max_depth=4)`** (baké),
> ~+50 Elo self-play, **vs Scan 0.097 → ~0.12** (0338/0343). Tout le reste est testé-et-plat (prunings
> marginaux, history-malus, TT, movegen-captures, NPS). jass perd encore ~7:1 vs Scan → **le gap restant
> est l'ÉVAL**. Infra dispo pour plus tard : `--search-params`, `--jass-search-params`, `--tt-mb`,
> `--search-profile`, params `lmp_max_depth`/`lmr_hist_div`/`hist_malus` (tous défaut-off/legacy).
> **→ Pivot Phase 2 : éval/data.**

> **Leçon générale (NPS)** : la movegen est lean, l'éval SIMD, la TT inutile → **le NPS est une traîne à faible plafond**. Le gros levier recherche (combo multicut+razor) est PRIS. Ne pas s'enliser ; le prochain grand levier = **éval/data (Phase 2/3)**.

### Combo recherche FINAL = **multicut + razor** (baké). Tranché.
0342 (90p propre) : les additions (lmp_max_depth, rfp7, lmr_hist) sont du **bruit** sur le combo.
0343 (en cours) solidifie le combo **vs Scan** (vs combo+lmp5+rfp7, 54p, un seul build).
**Levier d'ordering en test** : `hist_malus` (history malus, codé 2026-06-18) — jugé par A/B de force
(le node-count à depth fixe est trompeur : l'ordering change ce que LMR/LMP élaguent).

### Infra de tuning (2026-06-18)
- `jass --search-params "k=v,…"` : règle la recherche du moteur HUB sans rebuild.
- `calibrate_vs_scan --jass-search-params "…"` : tuning recherche **vs Scan en un seul build**.
- Tous les params : `src/search_params.hpp` (`parse_search_params`).

## RFP — lead en cours
home-0007 (hc, 36 parties) : `rfp_max_depth=7, rfp_margin=70` = **0.639**. À re-valider sur l'éval
pattern par-dessus le combo baké (home-0008), puis ajouter au bake si confirmé.

## Garde-fous
- Tout changement de recherche se juge à **temps fixe** (self-play A/B) puis **vs Scan** (`--jass-search-params`).
- 36 parties = bruit ±0.08 ; pour décider, ≥90 parties ou faible contention CPU (peu de procs parallèles).
