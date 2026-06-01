#!/usr/bin/env bash
# id: 0081-scan-distill-pattern-amplitude-fix
# description: Diagnostic confirmé : Scan eval a dynamique intrinsèquement
#              plus petite que v7 NNUE (std ~150 vs 425). Pattern model
#              entraîné sur labels Scan apprend cette distribution
#              compressée. Search jass tuné pour std ~400-500 → constants
#              (NMP, futility, aspiration) miscalibrent → cutoffs jamais
#              déclenchés → search dégrade malgré pearson 0.78.
#
# Fix : scaler les labels Scan × 2.7 avant training (= ratio v7_std/Scan_std).
# Le pattern model apprend amplitudes "v7-style" qui matchent les
# constantes search. La fonction de ranking reste identique (linear scale).
#
# Decision gate :
#   * pattern vs Scan > 0.10 → amplitude était le bug, scale-up
#   * pearson maintenu > 0.75 mais vs Scan flat → bug ailleurs
#   * tout flat → pattern paradigm vraiment plafonné
#
# Utilise le dataset 1M distilled de 0078, mais multiplie les scores ×2.7
# en place avant training (le sample dataset).
#
# expected_duration: ~30-45 min (scale + train + bench)
set -uo pipefail
cd /root/jass

OUT_BASE="/root/jass/jobs/results/0081-scan-distill-pattern-amplitude-fix"
ART="$OUT_BASE/artefacts.src"
mkdir -p "$ART"

SCAN_BIN=/root/jass-scan/scan_linux
[ -x "$SCAN_BIN" ] || { echo "ABORT: Scan binary not present"; exit 3; }

V6=$(ls -t /root/jass/jobs/results/0045-quiet-pv-extract-scaleup/artefacts.src/nnue-*-q.bin 2>/dev/null | head -1)
V7=$(ls -t /root/jass/jobs/results/0050-v7-quiet-pv-extract-1M/artefacts.src/nnue-*-q.bin 2>/dev/null | head -1)
V8=$(ls -t /root/jass/jobs/results/0056-v8-quiet-pv-1M-v7-labeller/artefacts.src/nnue-*-q.bin 2>/dev/null | head -1)
MASTER_SAMPLE=$(ls -t /root/jass/jobs/results/0014-fetch-master-games/artefacts.src/master-1600.jnnw 2>/dev/null | head -1)

RELAB_1M=/root/jass/jobs/results/0078-scan-distill-1M-mlp-scaleup/artefacts.src/v10-distilled-1M.bin
[ -f "$RELAB_1M" ] || { echo "ABORT: 0078 distilled 1M not found"; exit 3; }

echo "=== host facts ==="
echo "host: $(hostname)  nproc: $(nproc)"

cmake --build build -j"$(nproc)" 2>&1 | tail -3

if ! python3 -c "import torch, numpy" 2>/dev/null; then
    PIP_SCRATCH="/root/jass/.pip-scratch"
    mkdir -p "$PIP_SCRATCH"
    for attempt in 1 2 3; do
        TMPDIR="$PIP_SCRATCH" pip3 install --break-system-packages --no-cache-dir --quiet \
            numpy torch --index-url https://download.pytorch.org/whl/cpu && break
        sleep 10
    done
    rm -rf "$PIP_SCRATCH"
fi

# First, measure Scan label std vs v7 NNUE eval std on the same positions.
# This gives us the empirical scale ratio.
echo
echo "=========================================================="
echo "=== Mesure empirique : std(Scan labels) vs std(v7 eval) ==="
echo "=========================================================="
python3 - <<EOF
import struct, statistics, subprocess, tempfile, random
from pathlib import Path

raw = Path("$RELAB_1M").read_bytes()
n = struct.unpack_from('<I', raw, 4)[0]

# Sample 5000 records for std estimate
rng = random.Random(42)
idx = sorted(rng.sample(range(n), 5000))

# Extract Scan scores from sampled positions
scan_scores = []
for i in idx:
    off = 8 + i * 38
    score = struct.unpack_from('<i', raw, off + 33)[0]
    scan_scores.append(score)

scan_mean = statistics.mean(scan_scores)
scan_std  = statistics.stdev(scan_scores)
print(f"Scan labels (n={len(scan_scores)}): mean={scan_mean:.1f}  std={scan_std:.1f}  "
      f"range=[{min(scan_scores)}, {max(scan_scores)}]", flush=True)

# Save the sample as JNNW for v7 rewrite
sample_path = "$ART/sample-5K-for-scale.jnnw"
with open(sample_path, "wb") as f:
    f.write(b"JNNW")
    f.write(struct.pack("<I", len(idx)))
    for i in idx:
        off = 8 + i * 38
        f.write(raw[off:off+38])

# Run v7 NNUE eval via rewrite-scores-with-nnue
out_v7 = "$ART/sample-5K-v7-eval.jnnw"
subprocess.run(["/root/jass/build/jass", "--rewrite-scores-with-nnue",
                sample_path, out_v7, "--nnue", "$V7"], check=True, capture_output=True)

raw_v7 = Path(out_v7).read_bytes()
v7_scores = []
for i in range(len(idx)):
    off = 8 + i * 38
    score = struct.unpack_from('<i', raw_v7, off + 33)[0]
    v7_scores.append(score)

v7_mean = statistics.mean(v7_scores)
v7_std  = statistics.stdev(v7_scores)
print(f"v7 NNUE eval (n={len(v7_scores)}): mean={v7_mean:.1f}  std={v7_std:.1f}  "
      f"range=[{min(v7_scores)}, {max(v7_scores)}]", flush=True)

ratio = v7_std / scan_std if scan_std > 0 else 1.0
print(f"SCALE FACTOR (v7_std / scan_std) = {ratio:.3f}", flush=True)

# Persist for the next step
Path("$ART/scale-factor.txt").write_text(f"{ratio:.4f}\n")
EOF

SCALE=$(cat "$ART/scale-factor.txt")
echo "Using scale factor : $SCALE"

# Create the SCALED dataset
echo
echo "=========================================================="
echo "=== Scale Scan labels × $SCALE ==="
echo "=========================================================="
SCALED="$ART/v10-distilled-1M-scaled.bin"
python3 - <<EOF
import struct
from pathlib import Path
scale = float("$SCALE")
src = Path("$RELAB_1M").read_bytes()
n = struct.unpack_from('<I', src, 4)[0]
out = bytearray(b"JNNW" + struct.pack("<I", n))
for i in range(n):
    off = 8 + i * 38
    rec = src[off:off+38]
    score = struct.unpack_from('<i', rec, 33)[0]
    new_score = int(round(score * scale))
    # Clamp to int32 range
    new_score = max(-2**31, min(2**31 - 1, new_score))
    new_rec = rec[:33] + struct.pack("<i", new_score) + rec[37:38]
    out.extend(new_rec)
Path("$SCALED").write_bytes(bytes(out))
print(f"wrote {Path('$SCALED')} ({n} records, scores × {scale})", flush=True)
EOF

# Train pattern V3 + V2 sur le SCALED dataset, même config Adam V1
RESULTS=""
for PSET in v3 v2; do
    JPAT="$ART/pattern-$PSET-scan-1M-scaled.jpat"
    echo
    echo "=========================================================="
    echo "=== train pattern $PSET Adam 60ep sur 1M SCALED ==="
    echo "=========================================================="
    START=$(date +%s)
    python3 tools/train_pattern.py \
        --data           "$SCALED" \
        --out            "$JPAT" \
        --patterns       "$PSET" \
        --hybrid \
        --pattern-base   3 \
        --init-man       100 --init-king 300 \
        --optimizer      adam \
        --epochs         60 \
        --lr             1e-3 \
        --lambda         1.0 \
        --score-scale    0.01 \
        --weight-decay   1e-5 \
        --symmetry \
        --num-seeds      1 \
        --seed           42 \
        2>&1 | tee "$ART/train-$PSET.log"
    T_SEC=$(( $(date +%s) - START ))

    # Pearson vs v7 (qualitative signal)
    PEARSON="-"
    if [ -f "$MASTER_SAMPLE" ] && [ -n "$V7" ]; then
        python3 tools/pattern_eval_correlation.py \
            --pattern "$JPAT" --ref "$V7" --data "$MASTER_SAMPLE" --n 1000 \
            2>&1 | tee "$ART/pearson-$PSET.log"
        PEARSON=$(grep -oE 'pearson_r = [-+0-9.]+' "$ART/pearson-$PSET.log" | head -1 | awk '{print $3}')
        # Capture pattern std vs ref std
        PATTERN_STD=$(grep -oE 'pattern : .*std=[0-9.]+' "$ART/pearson-$PSET.log" | head -1 | grep -oE 'std=[0-9.]+' | cut -d= -f2)
        REF_STD=$(grep -oE 'ref *: .*std=[0-9.]+' "$ART/pearson-$PSET.log" | head -1 | grep -oE 'std=[0-9.]+' | cut -d= -f2)
    fi

    python3 tools/calibrate_vs_scan.py \
        --jass ./build/jass --scan "$SCAN_BIN" --nnue "$JPAT" \
        --depth 10 --pairs 3 \
        2>&1 | tee "$ART/bench-$PSET-vs-scan-d10.log"
    R_SCAN=$(grep -oE 'score rate: [0-9.]+' "$ART/bench-$PSET-vs-scan-d10.log" | head -1 | awk '{print $3}')

    [ -n "$V6" ] && ./build/jass --benchmark-nnue-vs-nnue "$JPAT" "$V6" 10 3 1 0 \
        2>&1 | tee "$ART/bench-$PSET-vs-v6-d10.log"
    R_V6=$(grep -oE 'score rate: [0-9.]+' "$ART/bench-$PSET-vs-v6-d10.log" 2>/dev/null | head -1 | awk '{print $3}')

    [ -n "$V7" ] && ./build/jass --benchmark-nnue-vs-nnue "$JPAT" "$V7" 10 3 1 0 \
        2>&1 | tee "$ART/bench-$PSET-vs-v7-d10.log"
    R_V7=$(grep -oE 'score rate: [0-9.]+' "$ART/bench-$PSET-vs-v7-d10.log" 2>/dev/null | head -1 | awk '{print $3}')

    [ -n "$V8" ] && ./build/jass --benchmark-nnue-vs-nnue "$JPAT" "$V8" 10 3 1 0 \
        2>&1 | tee "$ART/bench-$PSET-vs-v8-d10.log"
    R_V8=$(grep -oE 'score rate: [0-9.]+' "$ART/bench-$PSET-vs-v8-d10.log" 2>/dev/null | head -1 | awk '{print $3}')

    RESULTS+="  $PSET (train ${T_SEC}s) : pearson $PEARSON std=$PATTERN_STD (ref=$REF_STD)  vs Scan $R_SCAN  vs v6 $R_V6  vs v7 $R_V7  vs v8 $R_V8"$'\n'
done

echo
echo "=========================================================="
echo "       0081 PATTERN AMPLITUDE-FIX VERDICT"
echo "=========================================================="
echo "$RESULTS"
echo
echo "  Reference (avant amplitude fix) :"
echo "    Pattern V3 1M (0080) : std=157 ref=425  pearson 0.79  vs Scan 0.000  vs v8 0.222"
echo "    Pattern V2 1M (0080) : pearson 0.77  vs Scan 0.000  vs v8 0.083"
echo
echo "  Decision :"
echo "    * pattern V3 vs Scan > 0.10 → amplitude était le bug, ship pattern!"
echo "    * std désormais proche du ref std + vs Scan amélioré → fix confirmé"
echo "    * pearson maintenu > 0.75 mais vs Scan toujours flat → bug ailleurs"
echo "    * tout flat → pattern paradigm vraiment plafonné, MLP wins"
echo "=========================================================="
