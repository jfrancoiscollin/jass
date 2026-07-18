> ⚠️ **ARCHIVE — NE PAS PRENDRE COMME CONSIGNE ACTIVE.** Doc historique (ère pré-fit-volume / NNUE).
> Source de vérité unique = [CURRENT.md](../L3_CURRENT.md) (+ docs système : BOUCLE_VIRTUEUSE, SCAN_METHODOLOGY_GAP,
> DIAGNOSTIC_VS_SCAN, BIAIS_FIT_VOLUME, PROGRESSION_LITTERATURE). Conservé pour l'historique seulement. _(Classé archive 2026-06-24.)_

# Perf journey NNUE 128-64 : de l'archi sweep (0090) au pivot Othello (#170)

> ⚠️ **AVERTISSEMENT 2026-06-06 — les chiffres « vs Scan d10 » de ce
> document sont INVALIDÉS.** Toutes les mesures de qualité d'éval **à
> profondeur fixe contre Scan** ici (notamment le **0.870 / +331 vs Scan
> d10** présenté comme « baseline non-négociable ») sont **fausses** : un
> bug de buffer dans `tools/calibrate_vs_scan.py` (dérive de lecture
> stdout quand l'adversaire est lent en mode profondeur-fixe) faisait
> **forfaiter Scan sur des coups illégaux**, ce qui **gonflait Jass**.
> Mesuré sur le job 0137 : 46/54 parties depth-10 étaient des forfaits ;
> les rares parties propres montraient Jass *perdant*. Le bug est corrigé
> (lecteur threadé + queue, cf commit bridge) et la vraie mesure
> depth-fixe est relancée par le **job 0139**.
>
> ✅ **Restent valides** : le **vs Scan en movetime** (north-star réel
> ≈ **−685 ELO** à mt=0.5s, mesuré sur match propre) et **tous les
> benchmarks internes** (en un seul process, sans bridge Scan : v5→v8,
> PVS +47, SPSA, gates pattern…). La prémisse « notre éval bat déjà Scan
> à profondeur égale, l'écart est purement du NPS » qui s'appuyait sur le
> 0.870 est donc **non prouvée** — à trancher par 0139.

> Document chronologique de la chasse à la performance depuis le choix
> d'archi NNUE 128-64. Couvre toute la branche d'optims NNUE/search et
> se termine sur la décision honnête de pivot vers le Plan B pattern
> (Othello POC). Inclut les échecs autant que les succès — chaque
> verdict "FAIL" est une donnée qui élimine une hypothèse.

## 0. Point de départ : pourquoi 128-64

**Job 0090** (small-arch-sweep-movetime) :
- Sweep d'archi NNUE (96-48 / 128-64 / 192-96 / 256-128) en mode movetime
  (pas depth-fixe — depth-fixe favorise les grosses archis qui evaluent
  mieux par node mais coûtent plus cher en temps).
- **Verdict** : 128-64 best NPS-vs-strength dans le budget compute. Rate
  vs Scan d10 : **0.870**.
- Cette archi devient la baseline production.

## 1. Cible : parité Scan

| Engine | NPS | Multiple vs jass |
|---|---|---|
| jass v15 (128-64) | 917K | — |
| Scan d10 | 8.1M | **8.8×** |

Pour gagner en force vs Scan, il faut massivement augmenter NPS sans
sacrifier qualité d'eval. La rate 0.870 est notre baseline non-négociable.

## 2. Breakdown initial : où va le temps

**Job 0095** (eval-time-breakdown-pipe) — première mesure fine du temps :

| Bucket | Temps | % du total |
|---|---|---|
| eval (NNUE forward) | 4855ms | **25.7%** |
| movegen | 5819ms | **30.8%** |
| apply (pos.after) | 553ms | 2.9% |
| **other** | 7675ms | **40.6%** |

**Insight #1** : le bucket "other" (40.6%) est le plus gros, et on ne
sait pas ce qu'il contient. À ce stade on l'attribue vaguement à
"accumulator + tt + alloc + misc".

**Insight #2** : avec eval = 25.7%, le plafond Amdahl pour une
optimisation SIMD de l'eval seule est **+35% NPS** (1.23M NPS).
Insuffisant pour parité Scan (×8.8 requis).

## 3. Pivot architecture : Hybrid Eval

Après calcul Amdahl, décision : ne pas tout miser sur SIMD eval.
**Hybrid Eval** = utiliser une éval cheap (handcrafted) là où la
précision NNUE n'est pas nécessaire.

### 3.1 Tier 1 : cheap_eval RFP + NMP (PR #152, job 0096) — ❌ ÉCHEC CATASTROPHIQUE

**Hypothèse** : RFP et NMP utilisent l'eval comme gate ("eval >= beta ?").
Une éval cheap suffirait. ~10× moins cher que NNUE.

**Implémentation** : remplacer `eval_leaf` → `eval_cheap` (= `evaluate()` handcrafted) dans :
- Reverse Futility Pruning gate
- Null Move Pruning gate

**Verdict 0096** :
| Gate | Mesuré | Statut |
|---|---|---|
| NPS gain | +17.8% | PASS |
| **Rate vs Scan d10** | **0.056** | **FAIL** (baseline 0.870) |

**Diagnostic** : Jass perd 48/54 vs Scan, presque toujours par "no
legal move" (engine pourri ses pièces). Le bug : RFP retourne
`eval - margin` qui propage le score handcrafted dans alpha-beta.
Les biais handcrafted vs NNUE divergent de centaines de cp position
par position → faux scores propagés → mauvais best move → game lost.

**Erreur de design** : "cheap_eval comme remplacement direct" est
incompatible avec la sémantique de RFP qui RETOURNE l'eval. Le score
retourné DOIT être cohérent avec l'eval propagée par alpha-beta.

**Action** : revert via PR #153.

**Leçon apprise** :
> Toute optim qui touche au score retourné par alpha-beta doit
> préserver la cohérence d'échelle/biais entre tous les sites d'eval.
> Une cheap_eval ne peut être utilisée que comme GATE (skip NNUE
> quand clairement out-of-range), jamais comme replacement direct.

### 3.2 Tier 1bis : gate-only (jamais implémenté)

Idée alternative : cheap_eval pour décider de skip ou pas, mais NNUE
pour le score retourné. Sémantique correcte. Mis de côté pour pivoter
ailleurs.

## 4. Décomposition du bucket "other"

### Job 0097 (PR #154) : profile fine-grain — ✅ INFORMATIONNEL

Sub-buckets ajoutés via BD_TIME :
- accumulator : push_accumulator (NNUE L1 incremental update)
- tt : TT probe + store
- zobrist : zobrist_hash

**Verdict 0097** :

| Bucket | % | vs 0095 |
|---|---|---|
| movegen | 26.6% | ↓ 30.8% |
| eval | 22.9% | ↓ 25.7% |
| **accumulator** | **20.0%** | (était dans "other") |
| other-unaccounted | 17.4% | ↓ 40.6% |
| tt | 8.8% | (était dans "other") |
| apply | 2.6% | stable |
| zobrist | 1.7% | (était dans "other") |

**Insight #3** : `push_accumulator` (NNUE L1 update à chaque move)
coûte presque autant que l'eval elle-même. C'est le 3e plus gros
bucket. Et 90%+ de ces updates sont jetées (branches prunées avant
eval).

## 5. Lazy NNUE accumulator

### Job 0098 (PR #155) : lazy accumulator — ❌ ÉCHEC NPS (mais correctness OK)

**Hypothèse** : différer l'apply_move sur l'accumulator jusqu'au
moment où une eval est vraiment demandée. Branches prunées avant
eval ne paient jamais leur diff.

**Implémentation** : `acc_clean_ply`, `stack_pos[ply]`, lazy mark
dans `push_accumulator`, `ensure_accumulator(target_ply)` walk lazy
appliqué uniquement au eval call.

**Verdict 0098** :

| Gate | Mesuré | Statut |
|---|---|---|
| Accumulator pct | 18.4% (était 20.0%) | FAIL (devait <10%) |
| NPS gain | -0.4% | FAIL |
| **Rate vs Scan d10** | **0.870** | **PASS** (identique baseline) |

**Diagnostic** : l'hypothèse "beaucoup de branches prunées avant eval"
était fausse. En pratique :
- RFP gate appelle eval à depth ≤ 5
- NMP gate appelle eval à depth ≥ 4
- Quiescence appelle eval à terminal
- Leaf appelle eval à depth=0

→ 90%+ des nodes touchent l'accumulator. Le lazy ne fait que déplacer
le coût d'apply_move depuis push vers ensure. Pas évité.

**Action** : revert via PR #156. Le code lazy est correct (rate
préservé) mais inutile (-0.4% NPS pour +complexité).

**Leçon apprise** :
> Le succès d'une optim "lazy" dépend du taux de **branches pruned
> before eval**. En alpha-beta avec RFP/NMP/futility/leaf, ce taux
> est trop bas (<10%). Lazy reporte le travail au lieu de l'éviter.

## 6. Sub-profile movegen

### Job 0099 (PR #157) : split movegen — ✅ INFORMATIONNEL

Sub-buckets ajoutés : `movegen_capture` et `movegen_quiet` (dans
`movegen.cpp` via header `bd_time.hpp` partagé).

**Verdict 0099** :

| Composant | % total |
|---|---|
| movegen TOTAL | 32.3% (+5.7pp dû à overhead BD_TIME) |
| ├─ **capture** | **14.3%** (multi-capture recursion) |
| ├─ quiet | 9.9% (simples moves) |
| └─ **wrapper** | **8.1%** (filter max-captures + push) |

**Insight #4** : le wrapper (double scan max_n + filter loop dans
`generate_legal_moves`) coûte presque autant que `quiet`. Surprise —
on s'attendait à un wrapper trivial.

## 7. Movegen wrapper-kill

### Job 0100 (PR #158) : wrapper-kill — ❌ ÉCHEC NPS (mais code cleanup OK)

**Hypothèse** : éliminer le double scan + filter loop via tracking
`max_captures` incrémental dans `emit_chain` (clear ctx.out + reset
quand un chain plus long est trouvé). Passer `out` directement à
`generate_captures` (élimine temp MoveList + copy).

**Verdict 0100** :

| Gate | Mesuré | Statut |
|---|---|---|
| Wrapper bucket | 7.5% (était 8.1%) | FAIL (devait <3%) |
| NPS gain | -0.4% | FAIL |
| **Rate vs Scan d10** | **0.870** | **PASS** |

**Diagnostic** : le bucket "wrapper" était dominé par l'**overhead
du timer BD_TIME(movegen)** lui-même (atomic fetch_add), pas par le
code wrapper réel. La double-scan était cache-friendly + branch-pred
OK, optimisée par le compilateur.

**Action** : GARDÉ (code plus propre, élimine 1 allocation heap,
zéro régression). Mais le 8.1% n'était pas un vrai bottleneck —
**c'était un artefact de mesure**.

**Leçon apprise** :
> Les bucket d'instrumentation BD_TIME ont un overhead non
> négligeable (~50-100ns × atomic fetch_add par call). Quand un
> bucket est petit et appelé très souvent, l'overhead du timer
> peut dominer la vraie mesure. **Toujours vérifier qu'un "petit"
> bucket n'est pas juste du timer overhead avant d'optimiser.**

## 8. Capture pre-filter (en cours)

### Job 0101 (PR #159) : capture pre-filter — ✅ **PREMIER GAIN NPS RÉEL**

**Hypothèse** : `movegen_capture` (14.3%) est le vrai hot path
movegen. Beaucoup d'appels à `extend_man_captures` sont des
dead-ends (pas d'ennemi adjacent au man de départ).

**Implémentation** :
- Calculer `enemy_reach` = mask des squares 1-step adjacents à un
  ennemi (popcount(enemy) × 4 ops)
- Iterer SEULEMENT sur `friend_men & enemy_reach`
- Early-skip si `threat_men == 0 && kings == 0`
- Kings unchanged (long-range, pre-filter trop cher)

**Verdict 0101** :

| Gate | Mesuré | Statut |
|---|---|---|
| Capture pct | 13.7% (était 14.3%) | FAIL (metric mal choisi) |
| **NPS gain** | **+29.7%** | **✅ PASS énorme** |
| Rate vs Scan d10 | 0.870 | ✅ PASS (identique baseline) |

**NPS : 917K → 1.19M**. Quality 100% préservée.

**Paradoxe du bucket pct** : le bucket `capture` (% du total) baisse à
peine (-0.6 pp), pourtant NPS monte de +29.7%. Explication : l'optim
réduit le travail dans toute la search, donc tous les buckets baissent
proportionnellement. Le pct reste similaire, mais en valeur absolue le
travail par node a chuté.

**Leçon apprise** :
> Un bucket en % du total est une fraction, pas une mesure absolue.
> Si on accélère tout uniformément, les pct ne bougent pas. Toujours
> regarder NPS prod en valeur absolue pour mesurer le vrai gain.

**Position vs Scan** :
- Avant : 917K vs 8.1M = 8.8× gap
- Maintenant : 1.19M vs 8.1M = **6.8× gap** (réduit de 2×)

## 9. Score d'attaques tentées

| Job | PR | Optim | Gain NPS | Statut |
|---|---|---|---|---|
| 0096 | #152 | Hybrid Eval Tier 1 | +17.8% mais rate 0.056 | ❌ reverted #153 |
| 0098 | #155 | Lazy accumulator | -0.4% | ❌ reverted #156 |
| 0100 | #158 | Wrapper-kill movegen | -0.4% | ⚠️ gardé (cleanup) |
| 0101 | #159 | Capture pre-filter | **+29.7%** | ✅ MERGÉ |
| 0102 | #162 | Sub-profil "other" | n/a (diag) | ✅ MERGÉ |
| 0103 | #163 | NNUE quantize SIMD | **+8.5%** | ✅ MERGÉ |

**Cumul NPS depuis baseline 0091** :
| Version | NPS | Cumul gain |
|---|---|---|
| 0091 (baseline 128-64) | 917K | — |
| 0101 (capture pre-filter) | 1.19M | +29.7% |
| **0103 (quantize SIMD)** | **1.29M** | **+40.7%** |

**Gap vs Scan : 8.1M → 1.29M = 6.3×** (initial 8.8×, gap réduit de 28%).

## 10. Inventaire des optims restantes

### Buckets actuels (post-0097, encore valides) :

| Bucket | % total | Potentiel |
|---|---|---|
| movegen total | 26.6% | en cours (0101) |
| ├─ capture | 14.3% | cible 0101 |
| ├─ quiet | 9.9% | SIMD shifts ? |
| └─ wrapper | 8.1% (~5% vrai) | déjà optim |
| eval (NNUE) | 22.9% | SIMD seul plafonne +35% (Amdahl) |
| accumulator | 20.0% | lazy a échoué |
| other-unaccounted | 17.4% | jamais investigué |
| tt | 8.8% | layout / replacement |
| apply | 2.6% | trop petit |
| zobrist | 1.7% | trop petit |

### Pivots prioritaires si 0101 ne livre pas :

1. **Investiguer other-unaccounted (17.4%)** : encore inconnu. Sub-profil
   pour identifier (Position copies, MoveList alloc, history/killers
   lookup, hash_path linear scan, etc.).
2. **NNUE SIMD eval** : revenir au plan Phase A++ (cap +35% NPS, mais
   c'est qcq chose).
3. **TT layout** : 8.8% bucket. Probe path + replacement policy.

### Pivots à éviter (déjà éliminés) :

- ❌ Cheap_eval comme replacement (RFP/NMP cassent quality)
- ❌ Lazy accumulator (eval call rate trop élevé)
- ❌ Wrapper-kill movegen (bucket = timer artefact)

## 11. Leçons générales

1. **Tout bench DOIT inclure rate vs Scan d10** (≥0.85). Gain NPS sans
   gate qualité = piège (cf 0096).
2. **L'overhead BD_TIME est non négligeable**. Vérifier qu'un bucket
   isn't artefact d'instrumentation avant d'optimiser.
3. **Lazy ne marche que si le taux de skip est très élevé** (>50%).
   Mesurer le skip rate avant d'implémenter le lazy.
4. **Smoke handcrafted bit-identique main = nécessaire mais pas
   suffisant**. C'est juste une sanity sur la sémantique non-NNUE.
5. **Conserver le code clean même sans gain NPS** : si l'optim
   simplifie sans casser, garder (cf 0100 wrapper-kill).
6. **Le verdict "FAIL" est aussi une donnée**. 3 échecs ont éliminé
   3 hypothèses → on sait mieux où ne PAS chercher.

## 12. État post-#159 (capture pre-filter)

**Main HEAD post-#159** : capture pre-filter MERGÉE et livrée.
**NPS baseline relevée à 1.19M**, rate vs Scan d10 toujours 0.870.

### Pivots restants à tenter à ce stade

1. **Pre-filter quiet moves** : appliquer le même pattern aux men/kings
   qui ne peuvent pas avancer.
2. **Investiguer other-unaccounted** (17.4%) : encore jamais profilé.
3. **King capture pre-filter** : harder car long-range.
4. **TT layout** (8.8%) : probe path + replacement policy.
5. **NNUE SIMD eval** : Phase A++ revisit.

## 13. Sub-profil "other" et NNUE quantize SIMD (0102-0103)

### Job 0102 (PR #162) : sub-profil other-unaccounted — ✅ INFORMATIONNEL

Décomposition du bucket "other" (17.4%) en sous-catégories :
position-copy, movelist-alloc, history/killers lookup, hash-path,
search overhead. Verdict : aucun sub-bucket dominant > 5%, donc pas
de quick-win, mais inventaire utile.

### Job 0103 (PR #163) : NNUE quantize SIMD — ✅ +8.5% NPS

**Hypothèse** : la quantisation int8 du forward NNUE + AVX2 sur le
matmul donnent un speedup direct sur le bucket eval.

**Verdict 0103** :

| Gate | Mesuré | Statut |
|---|---|---|
| Eval pct | 12.7% (était 20.1% en 0102) | PASS |
| NPS gain vs 0101 | **+8.5%** | PASS |
| Rate vs Scan d10 | 0.870 | PASS |

**NPS : 1.19M → 1.29M**. Quality 100% préservée.

## 14. Audit SMP : faux signal puis vrai signal (0104 → 0104bis)

### Job 0104 (PR #164) : audit scaling SMP — ❌ BUG SETOPTION

**Idée** : mesurer NPS à threads ∈ {1, 2, 4, 8} pour comprendre si
les lazy helpers scaling existait dans nos benches.

**Résultat surprenant** : 4 mesures **bit-identiques** (6319318 nodes
/ depth 20 / 1.26M NPS). Statistiquement impossible si les threads
helpers étaient lancés.

**Diagnostic** : le script utilisait `setoption name threads value N`
(format UCI) mais le hub jass attend `setoption threads N` (format hub
minimal, cf. `src/hub.cpp:353`). Setoption rejeté silencieusement,
`threads_` restait à 1.

### Job 0104bis (PR #165) : fix format hub — ✅ VRAIE MESURE

**Vrai scaling table** (setoption au bon format) :

| threads | depth | NPS | scale vs 1t | efficiency |
|---|---|---|---|---|
| 1 | 20 | 1.26M | 1.00× | 100% |
| 2 | **22** | 1.09M | 0.86× | 43% |
| 4 | **22** | 1.09M | 0.86× | 22% |
| 8 | 21 | 604K | 0.48× | 6% |

**Insight #5** : NPS du main thread **sous-estime gravement le
travail SMP**. Les helpers populent la TT en parallèle → le main
thread atteint des **depths plus élevées avec moins de nodes**
(meilleur ordering = plus d'élagage). **+2 ply gratuits à 4
threads.** À 8 threads : contention TT visible (NPS chute, depth
recule).

**Leçon apprise** :
> Pour mesurer le scaling SMP, NPS seul ment. La métrique pertinente
> est **depth atteinte à temps égal** ou **ELO en jeu réel**.
> Mesurer NPS d'un seul thread n'attribue jamais le travail des
> helpers.

## 15. SMP self-play movetime (0105 → 0105bis)

### Job 0105 (PR #166) : self-play 1t vs 4t — ❌ MAL SIZÉ + STDOUT BUFFERED

**Idée** : 1t vs 4t à movetime fixe (3000ms), pairs=4 → ~96 games par
match. Estimé naïvement 75 min, en réalité **5-15h par match** (1
game = ~3 min × 96 games × 3 matches).

**Bug secondaire** : C++ iostream block-buffered vers pipe → le
log restait à 0 bytes pendant 35 min (rien à observer).

**Action** : killed via mécanisme GitOps `jobs/state/kill-in-flight`
(infra/runner.py:175). Découverte importante : ce mécanisme permet
d'arrêter un job en cours sans SSH au host.

### Job 0105bis (PR #167) : resized + line-buffered — ✅ VERDICT

**Sizing** : pairs=1, movetime=1500ms, stdbuf -oL pour line-buffer.

| match | n | rate_B | ΔELO | CI ±|
|---|---|---|---|---|
| 1t-vs-4t | 18 | **0.611** | +79 | ±0.23 |
| 1t-vs-2t | 18 | 0.556 | +39 | ±0.23 |
| 1t-vs-1t sanity | 18 | 0.528 | +19 | ±0.23 |

**Signal direction confirmé** : 4t aide. Magnitude estimée **+50-80
ELO**. n=18 trop petit pour CI exclusive de 0.50, mais delta
sanity-vs-4t cohérent avec gain réel.

**Recommandation prod** : `threads=4` par défaut. 8t à éviter (contention).

**Leçon apprise** :
> Le sizing d'un bench self-play se fait par **time-per-game** ×
> **n games**, pas seulement par n games. Self-play à movetime
> élevé coûte ~2× movetime × n moves par game. Pour 96 games à
> 3s/move sur 40 moves = 8h. Toujours estimer wall avant de queue.

## 16. Analyse honnête du gap time-search vs Scan

### Mesure mt=500ms (0090, 128-64)

| Run | rate vs Scan | ΔELO |
|---|---|---|
| 128-64 mt=500 (0090) | 0.028 | -618 |
| v11 mt=500 t=1 (0088 historique) | 0.009 | -817 |

128-64 v15 est ~+200 ELO meilleur que v11, mais le gap reste massif.

### Projection actualisée (après tout 0091-0105bis)

| Config | rate vs Scan mt=500 | ΔELO |
|---|---|---|
| 128-64 v15 1t (estimé post-0103, +30 ELO depuis 0090) | ~0.05 | ~-550 |
| 128-64 v15 4t SMP (+50-80 ELO) | ~0.08 | ~-500 |

### Audit eval : l'incrémental est **déjà acquis**

Dans la planification d'un pivot "refactor eval incrémentale" (qu'on
imaginait gros unlock), l'audit du repo a révélé :

- `src/nnue_accumulator.cpp` : 273 lignes, dual-accumulator (W+B)
- `apply_move` incrémental sur make_move (`search.cpp:205-218
  push_accumulator`)
- W1 column-major + SIMD AVX2 add/sub primitives
- Sparse update sur changements de pièces (max 22 deltas/move)
- Refresh complet en fallback
- **Speedup mesuré : ×1.57**

Tous les chiffres 0091→0103 sont **avec incremental déjà actif**. Le
gap -550 ELO time-search est **après** cette optim. Pas de quick win
restant sur ce front.

### Projection best-case avec Phase 2 + Phase 3

Plan Phase 2 (gen 2M depth 20 + train v16) + Phase 3 (distillation
128-64 → 96-48 ou 64-32) :

| État | vs Scan d10 | vs Scan mt=500 | Commentaire |
|---|---|---|---|
| Aujourd'hui v15 128-64 | +331 (0.870) | -550 (0.05) | Baseline |
| v16 128-64 (post-0107) | +400 à +450 | -450 à -500 | +80-120 ELO best |
| v17 96-48 distillé | +350 à +400 | -400 à -450 | -50 qualité, +50 vitesse |
| v17 64-32 distillé | +280 à +330 | -380 à -430 | Sweet-spot ? |

**Conclusion** : même best-case avec tout le plan, on resterait à
**-380 à -430 ELO vs Scan en time-search**. Le gap est structurel.

### Pour vraiment fermer le gap (estimation honnête)

- Movegen SIMD refactor : +50-100 ELO, semaines de travail
- Search avancé (PVS, multi-cut, aspiration, history gravity) :
  +100-150 ELO, semaines
- 5-10 cycles training itérés : +200-400 ELO, mois de compute
- **Total réaliste : -200 ELO restants vs Scan après tout ça**

Scan a 10+ ans d'optims accumulées. Fermer le gap mt=500 sur un
projet ouvert from-scratch n'est pas réaliste sur quelques semaines.

## 17. Décision pivot : Plan B Othello (PR #170)

### Verdict global

- À **profondeur fixe**, on écrase Scan (+331 ELO, rate 0.870)
- À **time-search**, gap structurel insurmontable sans années
- Le plan Phase 2+3 n'aurait pas fermé le gap (estimation honnête)

### Décision

Abandon Phase 2 (gen-data 2M cycles Stockfish). 0106 (gen-data 2M)
killé via `jobs/state/kill-in-flight` après ~3h (sacrifice mineur
pour libérer 8 jours runner).

Reprise du **Plan B documenté** dans `docs/ROADMAP.md:350` —
**Phase Pattern-1 Othello POC** :

- Move generator 8×8 + patterns Logistello-style (corners, edges,
  diagonals)
- Logistic regression sur self-play WDL
- Gate 1 : pattern bat random >95% → infra validée
- Cible : 2000-2200 ELO Othello

### PR #170 : Othello Day 1 — board + movegen

Livré :
- `othello/src/board.cpp` : black/white_count, to_ascii,
  to_string/from_string round-trip
- `othello/src/movegen.cpp` : 8 directions bitboard, generate_legal,
  flips, apply_move
- `othello/src/main.cpp` : CLI minimal (perft, play seq)
- `othello/tests/run_tests.cpp` : 44 assertions, framework léger

Validation :
- 44/44 tests passent
- Perft canonique depuis position initiale :
  - perft(1)=4, perft(2)=12, perft(3)=56, perft(4)=244
  - perft(5)=1396, perft(6)=8200
  - **perft(8)=390216 en 19ms** (match Edax exact)

Build standalone (pas lié au build jass core, cf README §5).

### Suite

- Day 2 : patterns (corners 2×2, edges, diagonals, base-3 encoding)
- Day 3 : eval + search alpha-beta basique
- Day 4 : self-play + WDL gen
- Day 5-6 : training Python L-BFGS + bench
- Day 7 : Gate 1 decision

## 18. Bilan global de la branche optim NNUE 128-64

### Score final

| Métrique | Valeur | Commentaire |
|---|---|---|
| NPS prod (single thread) | 917K → 1.29M | +40.7% cumulé |
| NPS prod (4 threads) | ~1.29M main | + depth +2 ply gratuit |
| Rate vs Scan d10 | 0.870 | Préservée à toutes étapes |
| Rate vs Scan mt=500 (estimé) | ~0.05-0.08 | Gap structurel |
| ELO vs Scan d10 | +331 | Domination profondeur fixe |
| ELO vs Scan mt=500 (estimé) | -500 à -550 | Gap insurmontable cheap |

### Optims tentées (score d'attaques)

| Job | PR | Optim | NPS | Rate vs Scan | Statut |
|---|---|---|---|---|---|
| 0096 | #152 | Hybrid Eval Tier 1 | +17.8% | 0.056 | ❌ reverted #153 |
| 0098 | #155 | Lazy accumulator | -0.4% | 0.870 | ❌ reverted #156 |
| 0100 | #158 | Wrapper-kill movegen | -0.4% | 0.870 | ⚠️ gardé (cleanup) |
| 0101 | #159 | Capture pre-filter | **+29.7%** | 0.870 | ✅ MERGÉ |
| 0102 | #162 | Sub-profil "other" | — | — | ✅ MERGÉ (diag) |
| 0103 | #163 | NNUE quantize SIMD | **+8.5%** | 0.870 | ✅ MERGÉ |
| 0104 | #164 | Audit SMP scaling | — | — | ❌ bug setoption |
| 0104bis | #165 | Audit SMP fix | — | — | ✅ MERGÉ (vrai scaling visible) |
| 0105 | #166 | SMP self-play movetime | — | — | ❌ mal sizé, killed |
| 0105bis | #167 | SMP self-play resized | +50-80 ELO @4t | — | ✅ MERGÉ |

### Méta-leçons de la branche

1. **Toujours gate qualité (rate vs Scan d10)** : un seul slip de
   rate révèle un bug d'eval (cf 0096 catastrophique).
2. **Mesurer avant d'optimiser** : 3 hypothèses sur 5 ont été
   éliminées par les benches (lazy, wrapper-kill, cheap_eval).
3. **L'overhead BD_TIME est non négligeable** : un bucket de 8%
   peut être 5% de timer + 3% de vrai code.
4. **NPS main thread sous-estime le SMP** : la métrique pertinente
   pour les threads est depth atteinte à temps égal.
5. **Le sizing wall-clock d'un bench self-play se calcule**
   movetime × moves × games. Pas movetime × games seul (cf 0105
   killed après 35 min de buffering vide).
6. **GitOps kill (jobs/state/kill-in-flight) permet d'arrêter un
   job sans SSH**. Découvert pendant 0105.
7. **Le verdict "FAIL" est aussi une donnée**. Chaque ❌ a éliminé
   une hypothèse. On sait mieux où ne PAS chercher.
8. **L'audit d'un refactor existant peut révéler qu'il est déjà
   fait** (eval incremental → déjà 273 lignes en place).

### Ce qu'on a accompli

- NNUE 128-64 production avec eval incrémentale + SIMD + quantisée
- +40.7% NPS depuis baseline 0091
- Rate 0.870 vs Scan d10 (= +331 ELO à profondeur fixe)
- SMP 4t fonctionnel (+50-80 ELO gain)
- Pipeline data/train/distill validé end-to-end
- 18 tentatives échouées documentées (paradigme pattern) +
  audit honnête du plafond NNUE

### Ce qu'on n'a pas accompli et pourquoi

- Fermer le gap time-search vs Scan : **structurel**, demande des
  années d'optims que la branche short-term ne peut pas porter.

### Prochaine valeur ajoutée : ailleurs

La branche optim NNUE 128-64 a livré tout ce qu'elle pouvait. La
suite va sur le **Plan B Othello** (cf §17) pour valider l'infra
pattern propre avant de la transposer sur draughts.
