# Phase Hybrid Eval — pivot architecture post-0095

> Rédigé 2026-06-03 après verdict 0095 : eval = 25.7% du temps total. Phase A++
> SIMD eval seul plafonne à 1.35× NPS (917K → 1.23M) selon Amdahl. Insuffisant
> pour parité Scan (8.8× requis). Pivot d'approche : hybrid eval + lazy
> accumulator.

## 1. Contexte chiffré (mesuré 0095)

| Bucket | Temps | % |
|---|---|---|
| eval (NNUE) | 4855ms | **25.7%** |
| movegen | 5819ms | 30.8% |
| apply (pos.after) | 553ms | 2.9% |
| other | 7675ms | **40.6%** |

Le bucket `other` inclut probablement les `push_accumulator` (NNUE L1 incremental
update). Ce n'est pas dans `eval` mais c'est du **travail dérivé de l'usage NNUE**.
Si on enlève l'accumulator (lazy), une part substantielle d'`other` disparaît.

## 2. Pourquoi hybrid eval

Constat : la NNUE est appelée à chaque eval, mais une grosse partie des appels
servent à PRUNING DECISIONS (RFP, NMP, futility margins), pas à des évals
exactes. Ces appels n'ont pas besoin de précision NNUE — un eval grossier
suffit pour répondre "cette position est-elle clairement >= beta ?".

Idem pour l'accumulator : il est maintenu à CHAQUE move, même quand 90% des
branches sont prunées avant d'arriver à eval. Lazy refresh = potentiel gros gain.

## 3. Trois sous-pivots (par ordre de risque)

### 3.1 — `cheap_eval` pour les pruning margins (Tier 1, low risk)

Remplace `eval_leaf` par `cheap_eval` dans :
- RFP (Reverse Futility Pruning, search.cpp:423)
- NMP gate (Null Move Pruning, search.cpp:453)

`cheap_eval` = `evaluate(pos)` (handcrafted) si pas de NNUE installée, sinon
soit handcrafted soit "NNUE L0 only" (skip layers L1/L2).

**Gain attendu** : `eval` 25.7% → ~15% du total (40% des appels deviennent
~10× cheaper). NPS +10-15%.

**Risque** : faible. RFP/NMP utilisent déjà des marges (100cp×depth), le bruit
du cheap_eval reste dans la marge.

**Effort** : 2-3 jours. ~50 lignes de code.

**Bench gate** : NPS up + rate vs Scan d10 stable (±0.05).

### 3.2 — `cheap_eval` à la terminale quiescence (Tier 2, medium risk)

À la fin de quiescence (calm position, no captures), on retourne actuellement
`eval_leaf` = NNUE. C'est techniquement le vrai eval qui revient dans le
score alpha-beta — précision importe.

Mais : si on est en deep quiescence (déjà 4+ plies au-delà de horizon),
l'apport de NNUE vs handcrafted est marginal (toutes les eval s'approchent
de la vérité comme depth → ∞).

**Variante** : cheap_eval pour quiescence ply >= 4 dans l'arbre. NNUE pour
les autres.

**Gain attendu** : encore -5-10% sur eval total.

**Risque** : modéré. Eval terminale est ce qui revient dans alpha-beta.
Quality drop possible.

**Effort** : 2-3 jours.

### 3.3 — Lazy accumulator (Tier 3, high risk, gros gain potentiel)

Actuellement `push_accumulator` runs à chaque move (diff update int8 sur L1).
Coût substantiel dans bucket `other`.

**Idée** : ne pas matérialiser `accumulators[ply+1]` à chaque move. Au lieu :
- Marquer accumulator dirty à chaque move (cheap : 1 flag)
- À l'eval (NNUE call), si dirty : appliquer les diffs en attente

**Cas favorable** : 90% des branches sont prunées avant eval. Donc 90% des
push_accumulator sont du travail jeté. Skip → gros gain.

**Cas défavorable** : si toute branche descend jusqu'à eval, lazy n'aide pas.

**Gain attendu** : -10-15% sur `other` total (potentiellement plus si la
proportion prune est élevée).

**Risque** : élevé. Bugs subtils sur la cohérence accumulator. Diff
incremental application order matters.

**Effort** : 1-2 semaines.

## 4. Estimation gains cumulatifs

| Étape | Gain NPS | Cumulé | NPS atteint |
|---|---|---|---|
| baseline 0095 | — | — | 917K |
| 3.1 cheap_eval RFP/NMP | +10-15% | +12% | 1.03M |
| 3.2 cheap_eval quiescence deep | +5-10% | +20% | 1.10M |
| 3.3 lazy accumulator | +10-25% | +35% | 1.24M |

**Plafond hybrid eval : ~1.3-1.5× NPS** (1.1-1.4M NPS).

Toujours **6-7× short de Scan** (8.1M NPS). Donc même hybrid eval ne suffit
pas pour parité Scan. Mais c'est la voie la moins risquée pour gratter du NPS
sans toucher à movegen / search core.

## 5. Plan implémentation

### Semaine 1 — Tier 1

- **Jour 1** : ajouter `cheap_eval(pos)` dans search.cpp. Si NNUE active,
  utiliser une L0-only forward (juste material count via L0 weights) sinon
  fallback handcrafted `evaluate()`.
- **Jour 2** : remplacer eval_leaf par cheap_eval dans RFP + NMP. Smoke
  test : NPS up sur sample 0091.
- **Jour 3** : bench complet vs Scan d10. Vérifier rate stable.
- **Verdict** : si gain ≥ +8% NPS ET rate stable → ship, continuer Tier 2.

### Semaine 2 — Tier 2 + Tier 3 pilot

- Tier 2 : variant cheap_eval en deep quiescence
- Tier 3 pilot : prototype lazy accumulator sur 100 positions, mesure gain
  réel vs surcoût refresh

### Semaine 3 — Tier 3 full + bench final

- Lazy accumulator complet
- Bench final vs Scan d10 + movetime 500ms
- Décision : ship combined hybrid eval ou abort lazy si gain < attendu

## 6. Bench gates non-négociables

À chaque tier shipped :
1. NPS gain ≥ +5% mesurable
2. rate vs Scan d10 ne baisse pas de plus de 0.05
3. tests unitaires passent (test_nnue.cpp 3139 assertions)
4. handcrafted bench vs NNUE-baseline reste positif

Si NIMPORTE quel gate fail → revert + investiguer.

## 7. Question ouverte : impact qualité eval

L'avantage actuel de jass = eval quality > Scan à d=10 (0.87 mesuré 0090).
Cet avantage vient de la NNUE Scan-distillée. Si on dégrade la qualité par
cheap_eval, l'avantage s'érode.

**Hypothèse** : cheap_eval ne remplace l'NNUE que sur PRUNE DECISIONS, pas
sur le score final retourné. Le score qui sort de search reste NNUE-based
(via eval_leaf à profondeur 0). Donc qualité préservée en théorie.

**À vérifier empiriquement** au tier 1 : le rate vs Scan d10 doit rester
≥ 0.85.

## 8. Hors-périmètre

Ce pivot ne couvre PAS :
- Movegen optim (bucket 30.8% — sera Phase Movegen-2 si Hybrid Eval livre)
- Lazy SMP scaling audit (orthogonal, peut tourner en parallèle)
- Réduction search work (LMR, futility) — déjà en place

Si après Phase Hybrid Eval on reste loin de Scan parity, prochaine étape =
movegen optim (gain 30.8% × 2× max = +15% NPS) puis SMP scaling.

## 9. Décision gate finale

Après les 3 tiers :
- Si NPS ≥ 1.3M ET rate vs Scan d10 ≥ 0.80 → ship v16
- Si NPS < 1.1M OU rate < 0.75 → revert, pivot autre direction
- Entre : décision case-par-case selon le gain réel mesuré
