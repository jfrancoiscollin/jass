# CURRENT — source de vérité active (programme « battre Scan »)

> **1 page, tenue à jour à CHAQUE verdict.** Le reste des docs = archive/historique.
> But : empêcher qu'un passage périmé relance une **branche morte**. Lire avec
> [ARBRE_DECISION.md](ARBRE_DECISION.md) (principe + arbre), [JOURNAL_DE_BORD.md](JOURNAL_DE_BORD.md)
> §0 (faits) et [SCAN_METHODOLOGY_GAP.md](SCAN_METHODOLOGY_GAP.md) (règles permanentes). MAJ : **2026-06-18**.

## Hypothèse active (2026-06-18) — la RECHERCHE est le levier DOMINANT
Le mur n'est **ni la data, ni la classe d'éval** — c'est que **la recherche de jass ne scale pas**.
- **0332** : à profondeur égale jass = Scan en vitesse (d9 : 1,1×) MAIS le branchement effectif est
  **2,0/ply (jass) vs 1,28 (Scan)** → l'arbre de jass explose (d15 : **18× plus lent**). jass ne peut
  pas atteindre les profondeurs de Scan à temps égal.
- **0330** : le gap d'éval est **réel mais petit** (~2-4 plies ; +2 plies → score ×6). jass *compense
  déjà* l'éval par la profondeur — qu'il n'arrive pas à obtenir (cf 0332). La recherche est le **multiplicateur**.
- **0333** : les prunings qui **achètent de la profondeur** (probcut/razor/multicut/iid) sont TOUS OFF
  par défaut ; le **combo = 0.639 à temps fixe** (≈ +100 Elo self-play). **Premier levier qui bouge.**

**Plan** : caler le combo de recherche (0334 ablations → 0335 vs Scan depth-égale), puis itérer le
réglage recherche (marges, LMR profond, ordering) — terrain neuf sous la BONNE méthodo (temps fixe).
L'éval (pool mixte) reste un levier secondaire additif (une éval plus nette aide aussi l'ordering).

## 🔑 Découvertes & ERREURS méthodologiques (2026-06-18) — à ne JAMAIS réintroduire
1. **ERREUR (corrigée) : on comparait à Scan à TEMPS FIXE ÉGAL depuis le début.** Ça confond éval et
   vitesse de recherche → on a longtemps mal diagnostiqué (« l'éval est nulle »). À temps égal jass voit
   moins de plies et perd quelle que soit l'éval. **Règle : depth fixe ou movetime compensé-NPS.**
2. **ERREUR (corrigée) : on a calé toute la recherche à PROFONDEUR FIXE.** Ce benchmark sous-évalue
   *structurellement* tout ce qui **achète de la profondeur** (à depth fixe la profondeur est gratuite →
   on ne voit que le risque du pruning) → probcut/razor/multicut/iid ont été désactivés à tort. **Régler
   la recherche À TEMPS FIXE** (self-play A/B `--benchmark-search-params … movetime_ms`).
3. **PIÈGE évité : ne PAS rallumer NMP.** Évident mais FAUX — NMP est off à dessein (+97 Elo, sweep
   0256/0259 ; zugzwang du draughts rend « passer est sûr » faux). Scan tient 1,28/ply SANS NMP.
4. **ERREUR (de raisonnement) : sur-indexation sur l'éval/data.** La conviction covariate-shift était
   forte et bien argumentée mais **réfutée** (0327/0329/0331 : 3 runs, même bande). Le vrai levier était
   la recherche. Leçon : *isoler* (éval vs recherche) AVANT de présumer la cause.

## ⛔ Principe (prior fort, pas dogme)
**Aucun pivot non-linéaire (FM/MLP) tant que la parité features/données/recherche avec Scan n'est pas
fermée.** La recherche est désormais le chantier ouvert — la fermer d'abord. (cf ARBRE_DECISION)

## Defaults actuels (build/recherche) — vérifier via le manifeste d'artefact
| flag | valeur | source |
|---|---|---|
| `JASS_ENDGAME_FEATURES` | **ON** (NUM_EXTRAS=110) | baké 0311 |
| `JASS_KING_MOBILITY` / `JASS_KING_PATTERNS` | OFF / OFF | 0311 / 0240 |
| `JASS_SCAN_PARITY` / `JASS_TEMPO_STAGE` | dispo (build runs récents ON) | 0323 |
| search NMP (`eg_no_nmp`) | **OFF partout** (garder) | +97 Elo 0256/0259 (zugzwang) |
| search **multicut** (min_depth=6, moves=8, cuts=2) + **razor** (max_depth=4) | **BAKÉ ON** (≈+75 Elo self-play) | 0336, jugé à temps fixe |
| search probcut / iid / conthist | OFF (n'ajoutent pas / nuisent) | 0334/0335/0336 |

## 🔒 RÈGLES PERMANENTES (2026-06-18)
- **Comparer à Scan** : jamais temps fixe égal → **profondeur fixe** (`--depth`/`--jass-depth`/`--scan-depth`)
  ou **movetime compensé-NPS** (`--jass-movetime`/`--scan-movetime`). Temps égal = seulement pour *mesurer*
  le handicap de vitesse. Garde-fou dans `calibrate_vs_scan.py`.
- **Régler la recherche** : à **TEMPS FIXE** (`--benchmark-search-params A B … movetime_ms`), jamais à
  profondeur fixe (sous-évalue le depth-buying).
- **Pool de données** : **mixer** Scan-self-play (qualité ; quiet → *nuit* seul, 0327) + jass-self-play
  (diversité) + coverage — `tools/jnnw_mix.py`. Diversité Scan : `scan_selfplay_gen.py --weak-depth`
  (fort vs affaibli) / `--depth-jitter`.
- **Outils** : `tools/nps_vs_scan.py` (handicap vitesse = facteur de compensation movetime) ;
  `tools/jnnw_mix.py` ; `tools/scan_selfplay_gen.py` (corpus fort).

## Verdicts récents (chronologie condensée)
- **0327/0329** — covariate-shift PUR : **NON**. NEW (Scan self-play) *pire* que OLD (0314) vs Scan
  (−545 vs −387), Elo_hc +182 vs +318 ; champion 500k = −545. La bonne distribution *seule* ne décolle pas.
- **0330** — éval vs recherche : **gap d'éval réel mais petit** (~2 plies). C2 depth9=0.056, C3 jass+2=0.333.
- **0331** — pool mixte jugé depth-égale : **pas d'amélioration nette** (dans le bruit 36 parties). Éval-data plafonné.
- **0332** — **la recherche ne scale pas** (branchement 2,0 vs 1,28 ; 18× à d15). Levier dominant.
- **0333** — prunings depth-buying OFF par défaut ; **combo = 0.639 à temps fixe**. Premier gain.
- **0334** ⏳ — ablations du combo (sans conthist ?) + confirmation 1500ms.

## Métriques — SCREEN vs DECISION (un proxy priorise, ne décide JAMAIS seul)
- **DECISION_GATE** : vs Scan **à profondeur égale / temps compensé** (méthodo permanente) · self-play
  A/B recherche **à temps fixe** (`--benchmark-search-params`) · autopsie endgame-rois.
- **SCREEN_ONLY** : `endgame_mse`, `val_mse`, Elo_hc, fit-check. ⚠️ **`endgame_mse` ⟂ force** (0311/0312).
- ⚠️ Matchs vs Scan : 36 parties = bruit ±0.08 → pour une décision, **≥90 parties** ou self-play A/B.

## Branches MORTES (NE PAS relancer — + condition de revival)
| Levier mort | Preuve | Reviendrait légitime si… |
|---|---|---|
| **Covariate-shift PUR** (data forte seule) | 0327/0329/0331 (3 runs, même bande) | dans un pool *mixte* + recherche réglée |
| Saturer le linéaire par cycles | 0297 plafonne/régresse | — |
| Gradient MTC comme **CIBLE** | 0306 (99,9 % proxy) | densité ≥10-MTC massivement enrichie |
| `--phase-weight` | −210 Elo (0261) | repro only |
| play-depth-finale SEUL (pré-egdb) | 0254/0265 | — |
| Géométrie de patterns | 0203-0236 (flat) | — |
| **Rallumer NMP** | −97 Elo (0256/0259, zugzwang) | — |
| **FM/MLP** | prématuré (principe) | parité features/données/**recherche** fermée |

> ⚠️ **VIVANT** : depth-RAMP `--play-depth-by-phase late-mid=12,endgame=16` en régime egdb-exact (revival 0293 +74 Elo).

## Garde-fou artefacts
`.pjtw`/`.jnnw` → **manifeste** (`jobs/lib/manifest.sh`). Avant tout A/B de deux `.pjtw` :
`manifest_assert_comparable`. Pré-flight compute : `jobs/lib/preflight.sh`. Sharding relabel : `jobs/lib/relabel.sh`.

## Sweep recherche 0333-0337 (jugé à TEMPS FIXE) — combo figé
- **multicut (min_depth=6, moves=8, cuts=2) + razor (max_depth=4) = ~+75 Elo self-play** (0336, 90 parties). **BAKÉ.**
- multicut SEUL ne suffit pas (0336 mc_only=0.439) ; probcut/iid/conthist n'ajoutent pas.
- Région-3 (LMP/asp/singular/history, 0337) : marginale (history_big 0.569 le seul ~1σ). Région-4 (home-0007) ⏳.

## Jobs en cours
- **cpx62** : **0338** (combo baké vs Scan — branchement + score à temps égal).
- **ccx33** : libre.
- **PC perso** : home-0007 (région-4) — heartbeat figé (PC peut-être en veille).

## Prochain verdict attendu
**0338** : le combo aplatit-il l'arbre (2,0 → vers 1,28) et marque-t-il **plus vs Scan à temps égal** ?
Si oui → continuer le tuning recherche, puis re-mesurer le gap d'éval résiduel (phase 2), puis la boucle gen-data (phase 3).
