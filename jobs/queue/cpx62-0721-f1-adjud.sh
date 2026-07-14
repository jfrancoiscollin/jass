#!/usr/bin/env bash
# id: cpx62-0721-f1-adjud
# description: F1 ADJUD (suite 0720, diagnostic bouclé) — le blocage L3 = la QUALITÉ DES LABELS, pas l'anchor/référence/
# échelle (0716/0719/0720 tous éliminés). Le corpus T1 = self-play on-policy du bootstrap (fort matériel, NAÏF positionnel)
# → issues WDL d9 = son jeu faible → fitter régresse l'éval (0720 T=1 : conv 0.355→0.340, gate −279). TEST DÉCISIF, ISOLE
# L'EFFET-LABEL : MÊME sous-échantillon du corpus, fitté 2× — (A) labels ON-POLICY (contrôle) vs (B) labels d14+egdb
# (ADJUD, issues VRAIES). conv_self (jauge v2 FIGÉE) + gate vs bootstrap pour chaque. Si ADJUD > ON-POLICY ⟹ les labels
# étaient le bloqueur ⟹ scale up (regen adjud pleine). Sinon ⟹ ni labels ni échelle : repenser le départ (bootstrap-faible).
# ⚠ d14 sur positions MILIEU (pas d'egdb ≤7p) = plus lent que le tip → MICRO-SONDE le rate + AUTO-SIZE (budget relabel
# ~45min/shard, plancher N_MIN). Build egdb. AUCUN NNUE. AUCUN bake. Corpus committé (sous-échantillon, pas de gen).
set -uo pipefail
cd /root/jass
exec 9>/root/.jass-0721.lock
if ! flock -n 9; then echo "ABORT 0721 : instance deja active"; exit 0; fi
NCPU=$(nproc); export TMPDIR=/root/jass/.compile-tmp; mkdir -p "$TMPDIR"
ART="/root/jass/jobs/results/cpx62-0721-f1-adjud/artefacts"; mkdir -p "$ART"
ARTREL="jobs/results/cpx62-0721-f1-adjud/artefacts"
W=/root/cw-0721; GEOM=/root/jass-geom32-0721
find /root -maxdepth 1 -name 'cw-*' -type d -mmin +180 ! -path "$W" -exec rm -rf {} + 2>/dev/null || true
rm -rf "$W"; mkdir -p "$W"
RES="$W/RESULTS.txt"; : > "$RES"; say(){ echo "$@" | tee -a "$RES"; }
DFA=$(df -Pm /root|awk 'NR==2{print $4}'); [ "${DFA:-0}" -gt 3000 ] || { echo "ABORT disque <3Go"; exit 3; }
FLAGS_EGDB="-DCMAKE_BUILD_TYPE=Release -DJASS_EGDB=ON -DJASS_EGDB_SRC_DIR=/root/egdb_intl -DJASS_ENDGAME_FEATURES=ON -DJASS_KING_MOBILITY=ON -DJASS_SCAN_PARITY=ON -DJASS_TEMPO_STAGE=ON"
GEN2_GZ=jobs/results/BAKE-gen2-mmto/artefacts/champion-gen2-mmto.pjtw.gz
CORPUS_GZ=jobs/results/cpx62-0715-d1-ablation/artefacts/corpus_T1.jnnw.gz
EVALSTRAT=jobs/results/ccx33-0718-mine-tip/artefacts/conv_self_eval_strat_v2.fen
SRC_BRANCH=claude/pcblues-corpus-extraction-2i92bj
MAXIT=60; CHUNK=1000000; CONV_DEPTH=10; ANCHOR=0.05; ARB_DEPTH=14
N_MAX=80000; N_MIN=20000; BUDGET=2700   # relabel budget ~45 min/shard
NOPEN=300; PAIRS=1; DEPTH=9; QS="qs_forcing_depth=6,qs_promo_depth=6"; NSH="$NCPU"

commit_to_main(){ local ab="$1" rel="$2" msg="$3"
  for a in 1 2 3 4 5; do git fetch origin main --quiet 2>/dev/null||true
    local idx="/root/.ti.$$.$RANDOM"; rm -f "$idx"; GIT_INDEX_FILE="$idx" git read-tree origin/main 2>/dev/null||return 1
    local b; b=$(git hash-object -w "$ab")||return 1
    GIT_INDEX_FILE="$idx" git update-index --add --cacheinfo 100644 "$b" "$rel"
    local t; t=$(GIT_INDEX_FILE="$idx" git write-tree); local c; c=$(printf '%s\n' "$msg"|git commit-tree "$t" -p origin/main)
    git push origin "$c:main" 2>/dev/null && { rm -f "$idx"; return 0; }; sleep $((a*4)); done; return 1; }
conv_self(){ local pids=()  # $1=lab $2=pattern -> "conv n"
  for s in $(seq 0 $((NSH-1))); do
    timeout 4000 python3 tools/conv_self.py --jass "$J" --pattern "$2" --defender-pattern "$W/gen2.pjtw" \
      --pool-file "$W/conv_pool.fen" --depth "$CONV_DEPTH" --lead 1 --max-plies 260 \
      --shard "$s" --nshards "$NSH" --out "$W/cs_$1.$s.json" >"$W/cs_$1.$s.log" 2>&1 & pids+=($!); done
  wait "${pids[@]}"
  python3 - "$W"/cs_$1.*.json <<'PY'
import json,sys
P=Wn=0
for f in sys.argv[1:]:
    try: j=json.load(open(f)); P+=j["n_pos"]; Wn+=j["n_win"]
    except Exception: pass
print(f"{(Wn/P if P else 0):.4f} {P}")
PY
}
gate_vs_boot(){ local pids=()  # $1=lab $2=pattern -> "rate n elo"
  for s in $(seq 0 $((NSH-1))); do
    timeout 4000 python3 tools/jass_vs_jass_arch.py --jass-a "$J" --pattern-a "$2" --jass-b "$J" --pattern-b "$W/bootstrap.pjtw" \
      --search-params-a "$QS" --search-params-b "$QS" --depth "$DEPTH" --pairs "$PAIRS" --max-plies 160 \
      --shard "$s" --nshards "$NSH" --quiet --openings-file "$W/open.fen" >"$W/g_$1.$s" 2>&1 & pids+=($!); done
  wait "${pids[@]}"
  python3 - "$W"/g_$1.* <<'PY'
import sys,math
a=d=b=0
for f in sys.argv[1:]:
    try:
        for l in open(f):
            if l.startswith("RESULT"): _,x,y,z=l.split(); a+=int(x);d+=int(y);b+=int(z)
    except Exception: pass
g=a+d+b; r=(a+0.5*d)/g if g else 0; elo=-400*math.log10(1/r-1) if 0<r<1 else 0
print(f"{r:.4f} {g} {elo:+.0f}")
PY
}
fit_a(){ # $1=lab $2=data -> $W/cand_$1.pjtw
  "$J" --dump-eval-features "$2" "$W/feat_$1" >"$W/dump_$1.log" 2>&1 || { say "  [$1] DUMP FAIL"; return 1; }
  env JASS_PATTERNS_DIR="$GEOM" PYTHONPATH="$GEOM:pattern_jass/tools" python3 pattern_jass/tools/wdl_finetune.py \
    --champion "$W/bootstrap.pjtw" --data "$2" --feat "$W/feat_$1" --out "$W/cand_$1.pjtw" \
    --tools pattern_jass/tools --anchor "$ANCHOR" --color-fold --tempo-stage --max-iter "$MAXIT" --chunk "$CHUNK" >"$W/ft_$1.log" 2>&1 \
    || { say "  [$1] FIT ABORT : $(tail -1 "$W/ft_$1.log")"; return 1; }
  grep -iE 'nz|patterns nz' "$W/ft_$1.log" >/dev/null 2>&1 || true; return 0
}

say "=== F1 ADJUD (labels on-policy vs d14+egdb, MÊME sous-échantillon) — HEAD $(git log --oneline -1|cat) — NCPU=$NCPU df=${DFA}Mo ==="
git fetch origin +refs/heads/develop:refs/remotes/origin/develop --quiet 2>/dev/null || true
git fetch origin +refs/heads/$SRC_BRANCH:refs/remotes/origin/$SRC_BRANCH --quiet 2>/dev/null || true
DIVERGED=$(git diff --name-only origin/main origin/develop -- src pattern_jass/src)
for f in $DIVERGED; do git show "origin/develop:$f" > "$f"; done
git show origin/develop:pattern_jass/tools/wdl_finetune.py > pattern_jass/tools/wdl_finetune.py
git show origin/develop:pattern_jass/tools/train_stream.py > pattern_jass/tools/train_stream.py
git show origin/develop:tools/jass_vs_jass_arch.py > tools/jass_vs_jass_arch.py
for f in tools/conv_self.py pattern_jass/tools/make_bootstrap_eval.py; do git show "origin/$SRC_BRANCH:$f" > "$f" 2>/dev/null || true; done
restore_src(){ git checkout -- src pattern_jass/src pattern_jass/tools/wdl_finetune.py pattern_jass/tools/train_stream.py tools/jass_vs_jass_arch.py 2>/dev/null||true; rm -f tools/conv_self.py pattern_jass/tools/make_bootstrap_eval.py; }
grep -q "g_emasks" src/scan_eval.cpp || { say "ABORT archi"; restore_src; exit 5; }
python3 -m py_compile tools/conv_self.py pattern_jass/tools/make_bootstrap_eval.py || { say "ABORT py_compile"; restore_src; exit 5; }
[ -d /root/egdb_intl ] || git clone --depth 1 https://github.com/eygilbert/egdb_intl /root/egdb_intl >"$W/clone.log" 2>&1
EGDIR=""; for d in /root/egdb_db /root/egdb_extracted/app /root/egdb_extracted; do ls "$d"/db*.idx1 >/dev/null 2>&1 && { EGDIR="$d"; break; }; done
[ -n "$EGDIR" ] || { say "ABORT egdb"; restore_src; commit_to_main "$RES" "$ARTREL/RESULTS.txt" "0721 ABORT egdb"; exit 4; }
export JASS_EGDB_PATH="$EGDIR"

say "=== build jass egdb ==="
cmake -S . -B "$W/build" $FLAGS_EGDB >"$W/cmake.log" 2>&1 && grep -q "EXTERNAL EGDB ENABLED" "$W/cmake.log" || { say "ABORT cmake"; tail -8 "$W/cmake.log"|sed 's/^/  /'; restore_src; exit 6; }
cmake --build "$W/build" -j"$NCPU" --target jass >"$W/build.log" 2>&1 || { say "BUILD FAIL"; tail -10 "$W/build.log"|sed 's/^/  /'; restore_src; commit_to_main "$RES" "$ARTREL/RESULTS.txt" "0721 BUILD FAIL"; exit 6; }
J="$W/build/jass"
python3 pattern_jass/tools/gen_patterns.py --emit --variant v4 >/dev/null 2>&1 || true
NP=$(python3 -c "import sys;sys.path.insert(0,'pattern_jass/tools');import patterns;print(patterns.NUM_PATTERNS)")
[ "$NP" = 32 ] || { say "ABORT geom NP=$NP"; restore_src; exit 7; }
rm -rf "$GEOM"; mkdir -p "$GEOM"; cp pattern_jass/tools/patterns.py "$GEOM/patterns.py"
git show "origin/main:$GEN2_GZ" | gunzip > "$W/gen2.pjtw" || { say "ABORT gen2"; restore_src; exit 4; }
python3 pattern_jass/tools/make_bootstrap_eval.py --out "$W/bootstrap.pjtw" --like "$W/gen2.pjtw" >/dev/null
grep -v '^[[:space:]]*#' data/dilf_combinations.fen | sed 's/#.*//' | awk 'NF' | head -"$NOPEN" > "$W/open.fen"
git show "origin/main:$CORPUS_GZ" | gunzip > "$W/full.jnnw" || { say "ABORT corpus T1"; restore_src; exit 4; }
git show "origin/main:$EVALSTRAT" | grep -vE '^\s*#' | awk 'NR%4==1' > "$W/conv_pool.fen"
NCP=$(grep -cvE '^\s*#' "$W/conv_pool.fen"); say "  ✓ build egdb + bootstrap + corpus T1 + jauge conv_self v2 sous-éch ($NCP pos)"

# --- MICRO-SONDE : rate d14+egdb sur positions MILIEU (auto-size) ---
say ""; say "=== micro-sonde rate d$ARB_DEPTH+egdb (600 pos milieu) ==="
PROBE_N=600
python3 - "$W/full.jnnw" "$W/probe.jnnw" "$PROBE_N" <<'PY'
import struct,sys
b=open(sys.argv[1],'rb').read(); n=struct.unpack('<I',b[4:8])[0]; body=b[8:]; REC=38; k=int(sys.argv[3])
st=max(1,n//k); idx=list(range(0,n,st))[:k]
out=b''.join(body[i*REC:(i+1)*REC] for i in idx)
open(sys.argv[2],'wb').write(b'JNNW'+struct.pack('<I',len(idx))+out); print(len(idx))
PY
T0=$(date +%s)
timeout 900 "$J" --deep-relabel "$W/probe.jnnw" "$W/probe_rel.jnnw" "$ARB_DEPTH" --egdb "$EGDIR" --cache-mb 2048 >"$W/probe.log" 2>&1 || true
T1=$(date +%s); PROBE_SEC=$((T1-T0))
PROBE_DONE=$(python3 -c "import struct,os;p='$W/probe_rel.jnnw';print(struct.unpack('<I',open(p,'rb').read(8)[4:8])[0] if os.path.exists(p) else 0)" 2>/dev/null||echo 0)
if [ "$PROBE_SEC" -ge 890 ] || [ "${PROBE_DONE:-0}" -lt "$PROBE_N" ]; then
  RATE=$(python3 -c "print(round(900.0/$PROBE_N,3))"); N_EFF=$N_MIN   # sonde time-out ou incomplète = d14 milieu LENT → plancher (conservateur)
  say "  ⚠ sonde time-out/incomplète (${PROBE_SEC}s, ${PROBE_DONE}/$PROBE_N) → d14 milieu LENT → N_EFF=plancher $N_MIN (≥${RATE}s/pos)"
else
  RATE=$(python3 -c "print(max(0.001, $PROBE_SEC/float($PROBE_N)))")
  N_EFF=$(python3 -c "print(min($N_MAX, max($N_MIN, int($BUDGET*$NSH/max(0.001,$RATE))//1000*1000)))")
  say "  sonde : $PROBE_N pos en ${PROBE_SEC}s → ${RATE}s/pos (1 thread) → N_EFF=$N_EFF (budget ${BUDGET}s×$NSH shards, cap [$N_MIN,$N_MAX])"
fi
ETA_REL=$(python3 -c "print(round($N_EFF*$RATE/$NSH/60,1))")
say "  ETA relabel ≈ ${ETA_REL} min ($N_EFF pos / $NSH shards)"

# --- sous-échantillon corpus → sub.jnnw (N_EFF, stride déterministe) ---
python3 - "$W/full.jnnw" "$W/sub.jnnw" "$N_EFF" <<'PY'
import struct,sys
b=open(sys.argv[1],'rb').read(); n=struct.unpack('<I',b[4:8])[0]; body=b[8:]; REC=38; k=int(sys.argv[3])
st=max(1,n//k); idx=list(range(0,n,st))[:k]
out=b''.join(body[i*REC:(i+1)*REC] for i in idx)
open(sys.argv[2],'wb').write(b'JNNW'+struct.pack('<I',len(idx))+out); print("sub:",len(idx))
PY
NSUB=$(python3 -c "import struct;print(struct.unpack('<I',open('$W/sub.jnnw','rb').read(8)[4:8])[0])")

# --- (A) fit CONTROL on-policy (labels inchangés) ---
say ""; say "--- (A) fit CONTROL on-policy (N=$NSUB, labels d9 bruts) ---"
if fit_a onp "$W/sub.jnnw"; then
  read AC AN < <(conv_self onp "$W/cand_onp.pjtw"); read AGR AGN AGE < <(gate_vs_boot onp "$W/cand_onp.pjtw")
  say "  [ON-POLICY] conv_self=$AC (n=$AN) | gate vs bootstrap : rate=$AGR n=$AGN elo=$AGE"
fi

# --- relabel ADJUD d14+egdb, shardé (timeout calibré, wait sur PIDs) ---
say ""; say "=== relabel ADJUD d$ARB_DEPTH+egdb sur $NSUB pos ($NSH shards) ==="
python3 - "$W/sub.jnnw" "$W/sh" "$NSH" <<'PY'
import struct,sys
b=open(sys.argv[1],'rb').read(); n=struct.unpack('<I',b[4:8])[0]; body=b[8:]; REC=38; nsh=int(sys.argv[3])
for s in range(nsh):
    idx=[i for i in range(n) if i%nsh==s]
    out=b''.join(body[i*REC:(i+1)*REC] for i in idx)
    open(f"{sys.argv[2]}.{s}.jnnw",'wb').write(b'JNNW'+struct.pack('<I',len(idx))+out)
PY
TOSH=$(python3 -c "print(int($BUDGET*1.3))")   # timeout/shard = budget × marge
pids=()
for s in $(seq 0 $((NSH-1))); do
  timeout "$TOSH" "$J" --deep-relabel "$W/sh.$s.jnnw" "$W/sh_rel.$s.jnnw" "$ARB_DEPTH" --egdb "$EGDIR" --cache-mb 2048 >"$W/rel.$s.log" 2>&1 & pids+=($!)
done
wait "${pids[@]}"
python3 - "$W/sub_adj.jnnw" "$W/sh_rel" <<'PY'
import struct,glob,sys
outp,pref=sys.argv[1],sys.argv[2]; REC=38; body=bytearray(); tot=0
for f in sorted(glob.glob(pref+".*.jnnw")):
    b=open(f,'rb').read()
    if b[:4]!=b'JNNW': continue
    n=struct.unpack('<I',b[4:8])[0]; body+=b[8:8+n*REC]; tot+=n
open(outp,'wb').write(b'JNNW'+struct.pack('<I',tot)+bytes(body)); print("adjud relabeled:",tot)
PY
NADJ=$(python3 -c "import struct;print(struct.unpack('<I',open('$W/sub_adj.jnnw','rb').read(8)[4:8])[0])")
[ "${NADJ:-0}" -ge "$N_MIN" ] || { say "ABORT: relabel adjud n=$NADJ < plancher $N_MIN (shards timeout ?)"; restore_src; commit_to_main "$RES" "$ARTREL/RESULTS.txt" "0721 ABORT relabel n=$NADJ"; exit 9; }
# diff de labels (combien d'issues on-policy étaient FAUSSES ?)
python3 - "$W/sub.jnnw" "$W/sub_adj.jnnw" <<'PY' | tee -a "$RES"
import struct,sys
def wdls(p):
    b=open(p,'rb').read(); n=struct.unpack('<I',b[4:8])[0]; body=b[8:]
    return [struct.unpack_from('<b',body,i*38+37)[0] for i in range(n)]
o=wdls(sys.argv[1]); a=wdls(sys.argv[2]); m=min(len(o),len(a))
ch=sum(1 for i in range(m) if o[i]!=a[i])
print(f"  labels changés par l'adjud : {ch}/{m} = {100.0*ch/max(1,m):.1f}%  (mesure directe de la corruption on-policy)")
PY

# --- (B) fit ADJUD ---
say ""; say "--- (B) fit ADJUD (N=$NADJ, labels d$ARB_DEPTH+egdb VRAIS) ---"
if fit_a adj "$W/sub_adj.jnnw"; then
  read BC BN < <(conv_self adj "$W/cand_adj.pjtw"); read BGR BGN BGE < <(gate_vs_boot adj "$W/cand_adj.pjtw")
  say "  [ADJUD] conv_self=$BC (n=$BN) | gate vs bootstrap : rate=$BGR n=$BGN elo=$BGE"
fi

say ""; say "=== VERDICT F1 ADJUD ==="
python3 - "$RES" <<'PY' | tee -a "$RES"
import re,sys
txt=open(sys.argv[1]).read()
def grab(tag):
    m=re.search(rf"\[{tag}\] conv_self=([\d.]+) \(n=(\d+)\) \| gate vs bootstrap : rate=[\d.]+ n=\d+ elo=([+-]?\d+)",txt)
    return (float(m.group(1)),int(m.group(3))) if m else None
mc=re.search(r"labels changés par l'adjud : \d+/\d+ = ([\d.]+)%",txt); chg=float(mc.group(1)) if mc else None
onp=grab("ON-POLICY"); adj=grab("ADJUD")
print(f"  labels changés par adjud = {chg}%")
if onp: print(f"  ON-POLICY : conv_self={onp[0]:.4f}  gate_elo={onp[1]:+d}")
if adj: print(f"  ADJUD     : conv_self={adj[0]:.4f}  gate_elo={adj[1]:+d}")
if onp and adj:
    dconv=adj[0]-onp[0]; delo=adj[1]-onp[1]
    if dconv>=0.03 and delo>=15:
        print(f"  => ✓ LES LABELS ÉTAIENT LE BLOQUEUR : adjud > on-policy (conv +{dconv:.3f}, elo +{delo}). ⟹ regen ADJUD pleine (arbitre d14+egdb dans la gen) = la recette L3 corrigée. Scale up.")
    elif dconv>=0.03 or delo>=15:
        print(f"  => ~ adjud AIDE partiellement (conv {dconv:+.3f}, elo {delo:+d}) — signal réel mais pas franc ; augmenter N (relabel plus profond/large) ou combiner avec up-weight gymnase.")
    else:
        print(f"  => ✗ adjud N'AIDE PAS (conv {dconv:+.3f}, elo {delo:+d}) ⟹ ni labels ni échelle : le bootstrap-fort-naïf est un mauvais point de départ pour 1 tour. Repenser le DÉPART (zero vs bootstrap-faible / campagne multi-tours).")
PY
restore_src
commit_to_main "$RES" "$ARTREL/RESULTS.txt" "0721 FIN F1 adjud : on-policy vs d14+egdb (N=$NADJ, chg labels)" && say "  ✓ RESULTS committé" || say "  ⚠ commit"
say "=== 0721 FINI ==="
rm -rf "$W" "$GEOM"
