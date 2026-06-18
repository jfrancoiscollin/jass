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

## Audit move-ordering / pruning (`src/search.cpp`) — prochains leviers
| # | Constat | Lever / expé | Priorité |
|---|---|---|---|
| 1 | **LMP plafonnée à depth ≤ 3** (`constexpr LMP_MAX_DEPTH = 3`, l.804) — non réglable | **Paramétrer + ÉTENDRE la LMP en profondeur** (formule move-count quadratique jusqu'à d6-8). Classique depth-buyer, sous-évalué par l'ancien réglage depth-fixe. Code + valider à temps fixe. | **HAUTE** |
| 2 | **Captures non ordonnées** (`return 0`, l.318) — ordre de génération | Ordonner les rafles max (promotion / rois capturés d'abord). Cheap. Mineur (captures forcées). | basse |
| 3 | LMR cap `d-2`, formule monotone | Tester LMR plus profond *sélectif* (low-history) ; `lmr_idx_div` agressif a nui (0333). | moyenne |
| 4 | RFP `rfp_max_depth=5` | home-0007 : `rfp_max_depth=7,margin=70` = 0.639 (hc, 36p) → **confirmer sur éval pattern** (home-0008) puis baker. | moyenne |
| 5 | Éval → ordering | Une éval plus nette améliore l'ordering (moins de branchement) → l'axe éval reste *additif*. | (phase 2) |

## RFP — lead en cours
home-0007 (hc, 36 parties) : `rfp_max_depth=7, rfp_margin=70` = **0.639**. À re-valider sur l'éval
pattern par-dessus le combo baké (home-0008), puis ajouter au bake si confirmé.

## Garde-fous
- Tout changement de recherche se juge à **temps fixe** (self-play A/B) puis **vs Scan** (`--jass-search-params`).
- 36 parties = bruit ±0.08 ; pour décider, ≥90 parties ou faible contention CPU (peu de procs parallèles).
