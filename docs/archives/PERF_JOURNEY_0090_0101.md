# Historique performance 0090–0101 — archive

> **Document archivé le 17 juillet 2026.** Ce contenu historique est conservé à l'identique depuis la branche `claude/docs-perf-journey`. Les références actives restent [`docs/CURRENT.md`](../CURRENT.md) et [`docs/JOURNAL_DE_BORD.md`](../JOURNAL_DE_BORD.md).

# Perf journey : du 128-64 (0090) au capture pre-filter (0101)

> Document chronologique de la chasse à la NPS depuis le choix d'archi
> NNUE 128-64. Inclut les échecs autant que les succès — chaque verdict
> "FAIL" est une donnée qui élimine une hypothèse.

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

### Job 0101 (PR #159) : capture pre-filter — 🔄 EN FLIGHT

**Hypothèse** : `movegen_capture` (14.3%) est le vrai hot path
movegen. Beaucoup d'appels à `extend_man_captures` sont des
dead-ends (pas d'ennemi adjacent au man de départ).

**Implémentation** :
- Calculer `enemy_reach` = mask des squares 1-step adjacents à un
  ennemi (popcount(enemy) × 4 ops)
- Iterer SEULEMENT sur `friend_men & enemy_reach`
- Early-skip si `threat_men == 0 && kings == 0`
- Kings unchanged (long-range, pre-filter trop cher)

Gates :
- Capture bucket < 11% (était 14.3%)
- NPS gain ≥ +3%
- Rate vs Scan d10 ≥ 0.85

## 9. Score d'attaques tentées

| Job | PR | Optim | Gain NPS | Mergé ? |
|---|---|---|---|---|
| 0096 | #152 | Hybrid Eval Tier 1 | +17.8% mais rate 0.056 | reverted #153 |
| 0098 | #155 | Lazy accumulator | -0.4% | reverted #156 |
| 0100 | #158 | Wrapper-kill movegen | -0.4% | gardé (cleanup) |
| 0101 | #159 | Capture pre-filter | ? | en flight |

**0 sur 3** optims ont livré du NPS jusqu'ici. Mais on a éliminé 3
hypothèses fausses et appris des choses non triviales.

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

## 12. État courant et next steps

**Main HEAD post-#159** : capture pre-filter en flight. NPS baseline
toujours 917K, rate vs Scan d10 toujours 0.870.

**Si 0101 PASS** : continue movegen optim (quiet SIMD, then capture
extend_*_captures inner loop).

**Si 0101 FAIL** : pivot vers investigation `other-unaccounted`
(17.4%, encore inconnu). Cheap diagnostic puis decide.

**Long-terme** : si même après movegen + other on plafonne à
+30-40% NPS (1.2-1.3M), parity Scan reste inaccessible. Il faudra
soit :
- Pivot vers SMP scaling (lazy SMP audit)
- Pivot vers archi NNUE plus petite (96-48 ou 64-32) si l'eval
  quality le permet
- Pivot vers SIMD eval (Phase A++ revenue)
