> ⚠️ **ARCHIVE — NE PAS PRENDRE COMME CONSIGNE ACTIVE.** Doc historique (ère pré-fit-volume / NNUE).
> Source de vérité unique = [CURRENT.md](../L3_CURRENT.md) (+ docs système : BOUCLE_VIRTUEUSE, SCAN_METHODOLOGY_GAP,
> DIAGNOSTIC_VS_SCAN, BIAIS_FIT_VOLUME, PROGRESSION_LITTERATURE). Conservé pour l'historique seulement. _(Classé archive 2026-06-24.)_

# Phase A++ — inference SIMD AVX2 optimization plan

> ⚠️ **AVERTISSEMENT 2026-06-06 — prémisse de ce plan INVALIDÉE.** Ce plan
> est justifié par « eval qualité 128-64 = 0.87 vs Scan d10 → bottleneck
> purement NPS » (verdict 0090). Ce **0.87 est faux** : bug de buffer dans
> `tools/calibrate_vs_scan.py` qui faisait forfaiter Scan en depth-fixe
> (gonflait Jass ; 46/54 forfaits sur le job 0137). On n'a donc **aucune
> preuve fiable** que l'éval bat Scan à profondeur égale — la justification
> « optimiser le NPS plutôt que l'éval » est affaiblie. Bug corrigé ;
> vraie mesure relancée par le **job 0139**. Les gains NPS mesurés
> (capture pre-filter +29.7%, quantize SIMD +8.5%) restent réels (mesures
> internes), seul le *gate qualité 0.870* était bidon.

> Rédigé 2026-06-03. Plan technique pour optimiser l'inférence
> MLPNetworkQ 128-64 quantisée int8 sur AVX2 (CCX33 = AMD EPYC 7003).
> Cible : 3M NPS → 6-10M NPS = parity Scan.

## 1. Contexte

Verdict 0090 : eval qualité 128-64 Scan-distilled = 0.87 vs Scan d10.
Bottleneck unique = NPS. Avec inference SIMD optim, on vise Scan parity
NPS → combinaison eval supérieure × depth parity = compétitif vs Scan.

## 2. Architecture cible

MLPNetworkQ 128-64 :
- Input : HalfMen 450 features (binary 0/1)
- Layer 1 : Linear(450 → 128) + ReLU
- Layer 2 : Linear(128 → 64) + ReLU  
- Layer 3 : Linear(64 → 1) (scalar score)

Total ops par eval :
- L1 : 450 × 128 = 57600 mults
- L2 : 128 × 64 = 8192 mults
- L3 : 64 × 1 = 64 mults
- **Total : ~66K mults par eval**

## 3. Optimisations cumulatives

### 3.1 — int8 SIMD AVX2 (gain attendu 4-6×)

AVX2 = 256-bit registers = 32× int8 par instruction.

**VPMADDUBSW** : multiply-add packed bytes → 16-bit signed.
**VPADDD** : accumulate 32-bit signed integers.

Pour L1 (450 → 128) :
- Loop sur 128 output neurons
- Pour chaque : reduce 450 inputs × 450 weights[neuron] → int32 accum
- VPMADDUBSW + VPADDD : 16 inputs par cycle SIMD
- 450/16 = 28 cycles SIMD par neuron
- 128 neurons × 28 = ~3600 SIMD ops (vs 57600 scalar)

Gain attendu : ~4-6× vs scalar float32.

**Note importante** : HalfMen input est binary {0, 1}. On peut exploiter
sparsity : neurons inactifs (input bit = 0) → skip. ~150-200 actives
typiques sur 450 → autre 2-3× gain potentiel via gather/sparse path.

### 3.2 — Accumulator-style L1 (gain attendu 3-5× sur incremental update)

NNUE classique : L1 output = state intrinsèque, updated via diff
(piece added/removed). Au lieu de recalculer L1 chaque eval :

```
on apply_move:
  for piece in (removed):
    L1_accum -= W1[piece_feature, :]
  for piece in (added):
    L1_accum += W1[piece_feature, :]
on eval:
  use L1_accum directly  (skip 57600 mults)
```

jass MLPNetworkQ a déjà un accumulator path probablement. À vérifier
qu'il est utilisé en search.

Si accumulator path déjà OK : gain 3-5× (skip L1 entirely).
Si pas implémenté correctement : implémenter = gros gain.

### 3.3 — Cache-aligned weight layout (gain 1.3-1.5×)

Weights row-major mais access pattern column-major (par output neuron).
Reorganize weights en SOA (Struct of Arrays) :
- W1[neuron_block][feature] avec neuron_block = 4 ou 8 neurons groupés
- Permet SIMD load + multi-neuron accumulation
- Fits L1 cache : 128 × 450 × 1 byte = 56 KB > L1d 32 KB
- → utilise L2 (1 MB), still hot

Bonus : prefetch explicite `__builtin_prefetch` pour next neuron block.

### 3.4 — Loop unrolling + FMA (gain 1.2-1.5×)

Manual unroll inner loop par 4× pour cacher latence FMA.
Sur AMD Zen 3 (CCX33) : 4 FMA/cycle pour float, 2 pour int.

### 3.5 — Quantize tighter (gain optionnel)

Actuel : int32 weights. Si réduit à int16 (saturated) : 2× moins de
bandwidth mémoire, gain 1.3-1.5× sur memory-bound passes.

Risque : précision eval dégradée. À tester.

## 4. Gains cumulatifs estimés

| Optim | Multiplier | NPS atteint |
|---|---|---|
| baseline (float32 scalar) | 1× | 3M (mesuré 0090 pour 128-64) |
| + int8 SIMD AVX2 L1/L2/L3 | 4× | 12M |
| + accumulator L1 (skip 87% ops) | 1.5× (residuel) | 18M |
| + cache layout + prefetch | 1.3× | 23M |
| + loop unrolling | 1.2× | 28M |

⚠️ Estimations optimistes — réalité probable 50-70% du nominal.
**Cible réaliste : 10-15M NPS** = 1.2-1.8× plus rapide que Scan (8.1M).

## 5. Étapes implémentation

### Semaine 1

**Jour 1-2** : Profile existing inference path (`src/nnue.cpp`)
- Identifier hot path
- Mesurer baseline NPS précis (vs estimation 3M)
- Vérifier si accumulator path utilisé

**Jour 3-4** : int8 SIMD L1 + L2
- Réécrire matmul AVX2 dans nnue.cpp
- Tests : output bit-exact vs scalar version
- Bench NPS gain

**Jour 5** : Cache layout reorganization
- Weights → SOA neuron_block format
- Bench gain

### Semaine 2

**Jour 6-7** : Accumulator path verify/implement
**Jour 8-9** : Loop unroll + prefetch + FMA tuning
**Jour 10** : Final bench + comparison vs Scan mt500

## 6. Tests + non-régression

**Critique** : à chaque optim, vérifier eval bit-exact (ou ±1 cp tolérance
si int rounding diff). Sinon on introduit silent bugs.

Test harness existant :
- `test_nnue.cpp` : 3139 assertions doivent toujours passer
- Smoke bench vs handcrafted : score rate doit rester stable

## 7. Risques

- **Quantization shift** : int8 reduces dynamic range, eval may shift
  ±5-10 cp from float. Mitigation : retrain ou re-calibrer après.
- **Cache miss spike** : si layout pas optimal, perte vs scalar. Bench
  sur position diverse, pas juste startpos.
- **AMD Zen 3 vs Intel** : optims VPMADDUBSW marchent partout AVX2 mais
  latences/throughput différents → tune sur target hardware (CCX33).

## 8. Reference

- Stockfish NNUE inference : exactement ce pattern (int8 SIMD)
- nnue-pytorch wiki : tutoriels quantization int8
- Agner Fog instruction tables : latences exactes Zen 3

## 9. Decision gate post-optim

| NPS atteint | Action |
|---|---|
| > 8M (Scan parity) | Re-bench mt500 vs Scan. Si rate > 0.20 → ship v15 |
| 5-8M | Partial gain. Vérifier eval bit-exact. Bench. |
| < 5M | Optim faible. Investigate (probablement bug ou hardware bottleneck) |

## 10. Estimation gain ELO final

Si NPS atteint Scan-parity ET eval qualité maintenue :
- depth jass = depth Scan
- eval qualité jass > Scan (vu 0090 d10 = 0.87)
- → jass devrait gagner vs Scan en mt500

Réaliste : rate vs Scan mt500 entre 0.30-0.50, soit **-100 à -200 ELO**
résiduel = ~**2500-2700 FMJD**.

Si non — eval qualité s'effondre avec depth profond (Scan peut être
meilleur à d20+ même si moins bon à d10) — alors le gap reste.
