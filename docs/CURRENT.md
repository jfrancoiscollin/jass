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

## Verdict drawish (2026-06-18) — NEUTRE en jeu, NE PAS baker
La non-linéarité de Scan (drawish ÷8/÷2), enfin testée en jeu : 0351 (108p) semblait aider (0.028→0.139)
mais **0353 (270p) = BRUIT** (vrai OFF=0.083) → ON ≈ OFF (d9 0.083=0.083, d11 légèrement pire). Au jeu, **la
recherche résout déjà les finales** → le scaling statique est redondant. Code dispo (`drawish_scaling`, défaut 0).
0354 (résidus) : confondu par la saturation ±9999, MAIS révèle que jass **sous-évalue les finales matériel-vs-roi
gagnées** (≤7p, mais **gérées par l'egdb au jeu** → moot). Vrai résidu d'éval = **8-15p** (corr 0.51-0.57).
→ Options A (phase-split finale) + B (WDL logistique, méthode Scan) en test (0355/0356).

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
| **TT >16 Mo** | testé `--tt-mb` : −0,3 % nœuds (peu de transpositions draughts) | — |
| **Optimiser movegen captures** (man-jump) | testé, perft-OK, 0 gain (movegen déjà lean) — cf SEARCH_TUNING | rewrite movegen majeur |
| Prunings marginaux sur le combo (probcut/iid/conthist) | 0334/0336 ~0.5 (chevauchent le combo) | — |
| **FM/MLP** | prématuré (principe) | parité features/données/**recherche** fermée |

> ⚠️ **VIVANT** : depth-RAMP `--play-depth-by-phase late-mid=12,endgame=16` en régime egdb-exact (revival 0293 +74 Elo).

## Garde-fou artefacts
`.pjtw`/`.jnnw` → **manifeste** (`jobs/lib/manifest.sh`). Avant tout A/B de deux `.pjtw` :
`manifest_assert_comparable`. Pré-flight compute : `jobs/lib/preflight.sh`. Sharding relabel : `jobs/lib/relabel.sh`.

## Sweep recherche 0333-0337 (jugé à TEMPS FIXE) — combo figé
- **multicut (min_depth=6, moves=8, cuts=2) + razor (max_depth=4) = ~+75 Elo self-play** (0336, 90 parties). **BAKÉ.**
- multicut SEUL ne suffit pas (0336 mc_only=0.439) ; probcut/iid/conthist n'ajoutent pas.
- Région-3 (LMP/asp/singular/history, 0337) : marginale (history_big 0.569 le seul ~1σ). Région-4 (home-0007) ⏳.

## 🏁 Chapitre RECHERCHE clos (2026-06-18)
Combo `multicut+razor` baké = **le seul gain** (~+50 Elo, vs Scan 0.097→~0.12, 0338/0343). Tout le reste
(prunings marginaux, history-malus, TT, movegen, NPS) testé-et-plat → cf SEARCH_TUNING.md. jass perd encore
~7:1 vs Scan → **le gap restant est l'ÉVAL**. → **Phase 2**.

## Phase 2 ÉVAL — verdicts (2026-06-18)
- **0345** : gap d'éval **~5 plies** (jass@d14 ≈ Scan@d9). **0346** : teacher Scan d12 N'aide pas (distill plafonné).
- **0349** (corrélation éval-jass↔éval-Scan, ALIGNÉE) : **fort en midgame** (16-25p:0.79, 26+p:0.80), **effondré
  en FINALE** (≤7p:**0.39**). → **PAS un plafond linéaire absolu** ; **trou LOCALISÉ en finale** = briques
  manquantes, *là où Scan a sa non-linéarité (drawish-scaling)*. (0347 = bug d'alignement, ignoré.)

## Fine-tuning du fit linéaire (2026-06-19) — attaquer le résidu finale (poids eg sous-ajustés)
- **0355 (option A « phase-split ») = NO-OP confirmé** (evalA vs eval0 DIRECT = **0.5 exact**, pjtw byte-identiques).
  CAUSE (⚠️ VIGILANCE, à ne jamais reproduire) : le chemin `--scan-eval` **IGNORE `--phase-split`** et `--tempo-stage`
  **ÉCRASE** `--phase-lo/hi` → les deux arms étaient la MÊME config. Pour vraiment varier la rampe : `JASS_PHASE_LO/HI`
  (build) ↔ `--phase-lo/--phase-hi` (train) **SANS tempo**, 2 binaires distincts. → refait proprement en **0358**.
- **0356/0357 (option B, WDL logistique = recette Scan) = PIRE.** Sur data forte (0328 Scan-self-play) ~majorité de
  nulles → cible WDL≈0.5 → éval **plate** (corr ~0 vs Scan). La **distillation de score** reste supérieure pour notre
  setup (signal de score dense ; WDL dégénéré sur self-play fort). → branche WDL-sur-data-forte morte.

## ⭐ NEXT STEPS — fine-tuning du fit (briques/réglages linéaires) puis verdict plafond
1. **0358 (C) — rampe de phase finale-nette 8/24 vs legacy 0/40** (piece-count, SANS tempo, 2 binaires) :
   sépare vraiment les banques mg/eg pour spécialiser la finale. Jugé vs Scan d9, 270 p/arm. evalC > eval0 → baker.
2. **0359 (F) — jeu LEAN 8 patterns (= Scan) vs enrichi 32** : on est un SURENSEMBLE de Scan (32 ⊃ 8, hash=3^12=aucun) ;
   test si nos 24 patterns enrichis **sur-paramètrent** la finale clairsemée. Jugé vs Scan d9, 216 p/arm. F > 32 → baker 8.
3. **0360 — ROIS dans les patterns (`JASS_KING_PATTERNS`), le VRAI levier finale** (PAS l'élagage, cf ci-dessous).
   Le trou ≤7p (0349 : 0.39) vient de patterns **men-only aveugles aux rois** alors que la finale est dominée par eux.
   0240 = **+37 Elo** (men|kings) mais en Elo_hc (SCREEN) puis mis OFF sous logistic-WDL ; on re-juge en **distillation
   + vs Scan d9** (DECISION) + corr finale held-out. Guard SELFDESC ⇒ no-op type 0355 impossible. evalK > eval0 → baker.
4. **Si 0358/0359/0360 ≈ (dans le bruit)** → **plafond pratique du fit linéaire** posé : seul le **pivot NN** (boucle
   vertueuse + apprentissage de représentation) peut dépasser. **MLP boîte-noire reste INTERDIT** jusqu'à ce verdict.
- ✅ **Drawish (`JASS_DRAWISH_SCALING`) = NEUTRE en jeu** (0353, 270 p) — testé, codé, défaut 0, NE PAS baker (cf §drawish).

## ⛔ ÉLAGUER la capacité = branche MORTE (3 angles — NE PAS relancer)
Intuition « 32 patterns = 4× Scan = sur-paramétré, il faut élaguer » → **réfutée par notre propre historique** :
- **0230** : importance des 32 patterns **uniforme**, redondance ≤0.40 — aucun pattern mort. **0234** : drop des 8 moins
  importants (32→24) = **−31 Elo ET 0 vitesse** (la lenteur d'éval est dans les extras+recherche, PAS les lookups pattern).
- **0190/0193** : bucket-hashing lossy = **casse la profondeur** (les buckets rares **portent la connaissance**).
- **0239** : richesse géométrique **plate sous labels parfaits** (15→54 patterns) → le trou n'est PAS la capacité.
- La sparsité 90× est déjà gérée **sans perte** par `--prune` (remap dense collision-free, ×51, corr 0.9999). On ne paie
  rien pour les buckets fantômes. ⇒ réduire la *capacité* (géométrie OU buckets) = testé 3×, perd. **0359 (F) = re-test
  PROPRE de 0234** sous DECISION-gate (0234 n'était que Elo_hc) ; prior fort « ça perd ».

## Jobs en cours
- **cpx62** : **0358** (C — phase-split finale PROPRE) → puis **0360** (rois-dans-patterns, en file).
- **ccx33** : **0359** (F — jeu LEAN 8 vs 32).
- **PC perso** : éteint.
