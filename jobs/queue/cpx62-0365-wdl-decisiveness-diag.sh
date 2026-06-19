#!/usr/bin/env bash
# id: cpx62-0365-wdl-decisiveness-diag
# description: DIAGNOSTIC promis — pourquoi 0363 (bootstrap WDL) grimpe en DIRECT (0.5→0.72 vs gen1) mais reste PLAT
# vs Scan (~0) ? Suspect n°1 = signal WDL dégénéré (trop de NULLES). On mesure le ratio W/D/L des parties self-play
# dans 3 régimes : (a) seed MATÉRIEL-SEUL @ play_depth=4 (= le régime exact de 0363), (b) matériel @ d9 (jouer plus
# profond rend-il + décisif ?), (c) eval EMBARQUÉE @ d4 (pilote + fort → + drawish ?). Décisif% élevé → le signal
# était là, le plafond vs Scan = volume/recherche (pas la décisivité) → scaler (mini-batch) + search. Nulles ≫ décisifs
# → signal dégénéré → il FAUT forcer la décisivité (plies aléatoires/température) avant de scaler. Lit le WDL au byte 37.
# expected_duration: ~15 min
set -uo pipefail
cd /root/jass
export PREFLIGHT_CAP_MIN="${PREFLIGHT_CAP_MIN:-60}"
source jobs/lib/preflight.sh
ART="/root/jass/jobs/results/cpx62-0365-wdl-decisiveness-diag/artefacts.src"; mkdir -p "$ART"
NCPU=$(nproc); export TMPDIR=/root/jass/.compile-tmp; mkdir -p "$TMPDIR"; SCALE=1000
preflight_build 1; preflight_note "3 échantillons self-play + comptage W/D/L" 15; preflight_check

[ -d /root/egdb_intl ] || git clone --depth 1 https://github.com/eygilbert/egdb_intl /root/egdb_intl >"$ART/clone.log" 2>&1
echo "=== build (EGDB ON = même adjudication finale que 0363) ==="
B=build-prod; rm -rf "$B"
cmake -S . -B "$B" -DCMAKE_BUILD_TYPE=Release -DJASS_EGDB=ON -DJASS_EGDB_SRC_DIR=/root/egdb_intl \
      -DJASS_ENDGAME_FEATURES=ON -DJASS_KING_MOBILITY=ON -DJASS_SCAN_PARITY=ON -DJASS_TEMPO_STAGE=ON >"$ART/cmake.log" 2>&1
grep -q "EXTERNAL EGDB ENABLED" "$ART/cmake.log" || { echo "ABORT: egdb off"; exit 6; }
cmake --build "$B" -j"$(mem_safe_jobs)" --target jass >"$ART/build.log" 2>&1 || { echo "BUILD FAIL"; tail -8 "$ART/build.log"; exit 6; }
JASS="$PWD/$B/jass"
[ -d /root/egdb_extracted ] && export JASS_EGDB_PATH=/root/egdb_extracted && echo "  egdb data: ON" || echo "  egdb data: absente"

echo "=== seed matériel-seul (= 0363) ==="
"$JASS" --gen-data-wdl 256 "$ART/mini.jnnw" 2 2 60 1 >/dev/null 2>&1
"$JASS" --dump-eval-features "$ART/mini.jnnw" "$ART/seed.feat" >/dev/null 2>&1
python3 - "$ART/seed.feat" "$ART/seed.pjtw" "$SCALE" <<'PY'
import sys,struct,numpy as np; sys.path.insert(0,'pattern_jass/tools')
import patterns as P, train; from pathlib import Path
feat,out,scale=sys.argv[1],sys.argv[2],int(sys.argv[3])
raw=open(feat,'rb').read(); cnt,k=struct.unpack_from('<II',raw,4)
NB=P.NUM_PATTERNS*P.BUCKETS_PER_PATTERN
pat=np.zeros(NB,np.int32); ext=np.zeros(k,np.int32)
ext[100]=scale; ext[101]=-scale; ext[0:50]=3*scale; ext[50:100]=-3*scale
train.write_weights_v3(Path(out),pat,pat.copy(),ext,ext.copy(),scale,king=False); print('seed ok n_ext=%d'%k)
PY

# génère <n> positions self-play, pilote <pilot|embedded>, play_depth <pd> → compte W/D/L (byte 37, int8 STM-POV)
sample(){ local tag="$1" n="$2" pd="$3" pilot="$4"; local per=$(( (n + NCPU - 1) / NCPU ))
  for s in $(seq 1 "$NCPU"); do
    "$JASS" --gen-data-wdl "$per" "$ART/$tag.$s.jnnw" 4 "$pd" 200 "$((RANDOM*RANDOM+s))" ${pilot:+--nnue "$pilot"} >"$ART/$tag.$s.log" 2>&1 &
  done; wait
  python3 - "$ART/$tag" <<'PY'
import sys,glob,re
tag=sys.argv[1]; REC=38; w=d=l=0
for f in glob.glob(tag+".*.jnnw"):
    b=open(f,'rb').read()
    if b[:4]!=b'JNNW': continue
    n=(len(b)-8)//REC; body=b[8:]
    for i in range(n):
        v=body[i*REC+37]; v=v-256 if v>127 else v   # int8
        if v>0: w+=1
        elif v<0: l+=1
        else: d+=1
tot=w+d+l or 1
print(f"  {tag:18s} n={w+d+l:6d}  W={100*w/tot:4.1f}%  D={100*d/tot:4.1f}%  L={100*l/tot:4.1f}%  -> décisif={100*(w+l)/tot:4.1f}%")
PY
  rm -f "$ART/$tag".*.jnnw
}
echo "=== W/D/L par régime ==="
sample mat_d4   80000 4 "$ART/seed.pjtw"   # = régime exact de 0363
sample mat_d9   40000 9 "$ART/seed.pjtw"   # matériel mais joué + profond
sample embed_d4 40000 4 ""                  # eval embarquée (pilote + fort)

echo; echo "=========================================================="
echo "   cpx62-0365 — DÉCISIVITÉ du self-play (pourquoi 0363 plat vs Scan ?)"
echo "   (cf comptages ci-dessus)"
echo "----------------------------------------------------------"
echo "   décisif% ÉLEVÉ (>40%) → signal WDL présent → plafond vs Scan = VOLUME/RECHERCHE → scaler (mini-batch)+search."
echo "   NULLES ≫ décisifs → signal dégénéré → FORCER la décisivité (plies aléatoires/température) avant de scaler."
echo "=========================================================="
