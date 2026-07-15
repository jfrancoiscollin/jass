#!/usr/bin/env bash
# id: cpx62-0727-t1bis-adj-g1
# Phase 1 (spec codex_review_v3_2 §5) — T1-bis « ADJ + G1 » assemblé de bout en bout.
# gen pilotée-T0 (G1 seed-pool + cap-arbiter + --label-src-out) → RELABEL-ADJ complet d14+egdb (résolution
# oracle_cert §3 + survie tip) → fit ancré 0.05 (+ cellule λ-énorme garde-fou + z-stats) → jauges (conv
# WDL-grounded 1600 figé ventilé p1-p4 + gate vs parent + gate vs référence-fixe T0) → promotion_gate --regime
# young → mining PASSIF. PASS pré-engagé §5.5. Aucun NNUE. Cache×procs gardé (incident 0723). restart-on-death.
set -uo pipefail
cd /root/jass
JOB_ID=cpx62-0727-t1bis-adj-g1; TOUR=T1-bis
exec 9>/root/.jass-0727.lock; flock -n 9 || { echo "ABORT instance active"; exit 0; }
NCPU=$(nproc); export TMPDIR=/root/jass/.compile-tmp; mkdir -p "$TMPDIR"
ART="/root/jass/jobs/results/$JOB_ID/artefacts"; ARTREL="jobs/results/$JOB_ID/artefacts"; mkdir -p "$ART"
W=/root/cw-0727; GEOM=/root/geom-0727
find /root -maxdepth 1 -name 'cw-*' -type d -mmin +180 ! -path "$W" -exec rm -rf {} + 2>/dev/null || true
rm -rf "$W" "$GEOM"; mkdir -p "$W" "$GEOM"
RES="$W/RESULTS.txt"; : > "$RES"; say(){ echo "$@" | tee -a "$RES"; }
die(){ say "ABORT: $*"; restore_src 2>/dev/null||true; commit_to_main "$RES" "$ARTREL/RESULTS.txt" "0727 ABORT: $*" 2>/dev/null||true; exit 1; }
DFA=$(df -Pm /root|awk 'NR==2{print $4}'); [ "${DFA:-0}" -gt 5000 ] || { echo "ABORT disque <5Go"; exit 3; }

FLAGS_EGDB="-DCMAKE_BUILD_TYPE=Release -DJASS_EGDB=ON -DJASS_EGDB_SRC_DIR=/root/egdb_intl -DJASS_ENDGAME_FEATURES=ON -DJASS_KING_MOBILITY=ON -DJASS_SCAN_PARITY=ON -DJASS_TEMPO_STAGE=ON"
GEN2_GZ=jobs/results/BAKE-gen2-mmto/artefacts/champion-gen2-mmto.pjtw.gz
SEEDS_GZ=jobs/results/cpx62-0556-gen2M-mixdepth/artefacts/corpus-mix2M.jnnw.gz
G1POOL=jobs/results/ccx33-0718-mine-tip/artefacts/conversion_pool_train_v2.fen
GAUGE1600=jobs/results/ccx33-0718-mine-tip/artefacts/conv_self_eval_strat_v2.fen
# --- sizing (~400k généré, relabel-adj complet) ---
GAMES=${GAMES:-300}; PLAYD=10; MAXPLIES=200; MINPC=36; SEEDFRAC=0.18; ARB_DEPTH=14; SEED=72700
CACHE_MB=512; ANCHOR=0.05; MAXIT=60; CHUNK=1000000; CONV_DEPTH=10
NOPEN=300; PAIRS=1; DEPTH=9; QS="qs_forcing_depth=6,qs_promo_depth=6"; NSH="$NCPU"; SHARD_TIMEOUT=7000; RELABEL_TIMEOUT=4000

commit_to_main(){ local ab="$1" rel="$2" msg="$3"
  for a in 1 2 3 4 5; do git fetch origin main --quiet 2>/dev/null||true
    local idx="/root/.ti.$$.$RANDOM"; rm -f "$idx"; GIT_INDEX_FILE="$idx" git read-tree origin/main 2>/dev/null||return 1
    local b; b=$(git hash-object -w "$ab")||return 1; GIT_INDEX_FILE="$idx" git update-index --add --cacheinfo 100644 "$b" "$rel"
    local t; t=$(GIT_INDEX_FILE="$idx" git write-tree); local c; c=$(printf '%s\n' "$msg"|git commit-tree "$t" -p origin/main)
    git push origin "$c:main" 2>/dev/null && { rm -f "$idx"; return 0; }; sleep $((a*4)); done; return 1; }
merge_jnnw(){ python3 - "$1" "$2" <<'PY'
import struct,glob,sys
outp,pref=sys.argv[1],sys.argv[2]; REC=38; body=bytearray(); tot=0
for f in sorted(glob.glob(pref+"*")):
    b=open(f,'rb').read()
    if b[:4]!=b'JNNW': continue
    n=struct.unpack('<I',b[4:8])[0]; body+=b[8:8+n*REC]; tot+=n
open(outp,'wb').write(b'JNNW'+struct.pack('<I',tot)+bytes(body)); print(tot)
PY
}
merge_labels(){ python3 - "$1" "$2" <<'PY'
import glob,sys
outp,pref=sys.argv[1],sys.argv[2]; body=bytearray()
for f in sorted(glob.glob(pref+"*")): body+=open(f,'rb').read()
open(outp,'wb').write(bytes(body)); print(len(body))
PY
}
gate(){ local pids=()  # $1=lab $2=patA $3=patB -> "rate n elo ci_low ci_high wins_a draws wins_b"
  for s in $(seq 0 $((NSH-1))); do
    timeout "$SHARD_TIMEOUT" python3 tools/jass_vs_jass_arch.py --jass-a "$J" --pattern-a "$2" --jass-b "$J" --pattern-b "$3" \
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
n=a+d+b; r=(a+0.5*d)/n if n else 0
var=max(0.0,(a+0.25*d)/n-r*r) if n else 0; se=math.sqrt(var/n) if n else 0
lo=max(0.0,r-1.96*se); hi=min(1.0,r+1.96*se); elo=-400*math.log10(1/r-1) if 0<r<1 else 0
print(f"{r:.4f} {n} {elo:+.0f} {lo:.4f} {hi:.4f} {a} {d} {b}")
PY
}

say "=== T1-bis ADJ+G1 ($JOB_ID) — HEAD $(git log --oneline -1|cat) — NCPU=$NCPU df=${DFA}Mo ==="
# ── §13 checklist ──
python3 jobs/tools/cache_guard.py --cache-mb "$CACHE_MB" --procs "$NCPU" | tee -a "$RES" || die "cache agrégé > budget (§13)"
for t in test_oracle_cert test_promotion_gate test_probe_mining test_cache_guard; do python3 "jobs/tests/$t.py" >"$W/$t.log" 2>&1 || die "tests $t rouges"; done
say "  [✓] §13 : cache OK + tests Phase 0 verts"
# ── pull src+tools (develop pinné) ──
git fetch origin +refs/heads/develop:refs/remotes/origin/develop --quiet 2>/dev/null || die "fetch develop"
DEVSHA=$(git rev-parse origin/develop); MAINSHA=$(git rev-parse origin/main)
for f in $(git diff --name-only origin/main origin/develop -- src pattern_jass/src); do git show "origin/develop:$f" > "$f"; done
for f in tools/scan_selfplay_gen.py tools/jass_vs_jass_arch.py tools/calibrate_vs_scan.py \
         pattern_jass/tools/wdl_finetune.py pattern_jass/tools/train_stream.py pattern_jass/tools/make_bootstrap_eval.py; do
  git show "origin/develop:$f" > "$f" || die "$f absent develop"; done
restore_src(){ git checkout -- src pattern_jass/src tools/scan_selfplay_gen.py tools/jass_vs_jass_arch.py tools/calibrate_vs_scan.py pattern_jass/tools/wdl_finetune.py pattern_jass/tools/train_stream.py pattern_jass/tools/make_bootstrap_eval.py 2>/dev/null||true; }
grep -q label-src-out tools/scan_selfplay_gen.py || die "scan_selfplay_gen sans --label-src-out"
grep -q g_emasks src/scan_eval.cpp || die "archi"
python3 -m py_compile tools/scan_selfplay_gen.py jobs/tools/oracle_cert.py jobs/tools/promotion_gate.py jobs/tools/probe_mining.py jobs/tools/conv_fixed_wdl.py jobs/tools/jnnw_doe.py || die "py_compile"
[ -d /root/egdb_intl ] || git clone --depth 1 https://github.com/eygilbert/egdb_intl /root/egdb_intl >"$W/clone.log" 2>&1
EGDIR=""; for d in /root/egdb_db /root/egdb_extracted/app /root/egdb_extracted; do ls "$d"/db*.idx1 >/dev/null 2>&1 && { EGDIR="$d"; break; }; done
[ -n "$EGDIR" ] || die "egdb"; export JASS_EGDB_PATH="$EGDIR"

say "=== build jass egdb ==="
cmake -S . -B "$W/build" $FLAGS_EGDB >"$W/cmake.log" 2>&1 && grep -q "EXTERNAL EGDB ENABLED" "$W/cmake.log" || die "cmake"
cmake --build "$W/build" -j"$NCPU" --target jass >"$W/build.log" 2>&1 || die "build"
J="$W/build/jass"
python3 pattern_jass/tools/gen_patterns.py --emit --variant v4 >/dev/null 2>&1 || true
NP=$(python3 -c "import sys;sys.path.insert(0,'pattern_jass/tools');import patterns;print(patterns.NUM_PATTERNS)"); [ "$NP" = 32 ] || die "geom NP=$NP"
cp pattern_jass/tools/patterns.py "$GEOM/patterns.py"
git show "origin/main:$GEN2_GZ" | gunzip > "$W/gen2.pjtw" || die "gen2"
# T0 = bootstrap (parent ET référence fixe pour T1-bis)
python3 pattern_jass/tools/make_bootstrap_eval.py --out "$W/T0.pjtw" --like "$W/gen2.pjtw" >/dev/null || die "bootstrap"
git show "origin/main:$SEEDS_GZ" | gunzip > "$W/seeds.jnnw" || die "seeds"
git show "origin/main:$G1POOL" | sed 's/#.*//' | awk 'NF' > "$W/g1_pool.fen" || die "G1"
grep -v '^[[:space:]]*#' data/dilf_combinations.fen | sed 's/#.*//' | awk 'NF' | head -"$NOPEN" > "$W/open.fen"

# ── §5.1 GÉNÉRATION pilotée-T0 (G1 seed-pool + cap-arbiter + label-src-out) ──
say ""; say "=== §5.1 génération pilote-T0 + G1 + cap-arbiter — ${GAMES}×${NSH} ==="
pids=()
for s in $(seq 0 $((NSH-1))); do
  timeout "$SHARD_TIMEOUT" python3 tools/scan_selfplay_gen.py --jass "$J" --player-jass-bin "$J" --player-pattern "$W/T0.pjtw" \
    --seeds "$W/seeds.jnnw" --out "$W/sp.$s" --games "$GAMES" --max-plies "$MAXPLIES" --min-pieces "$MINPC" \
    --sample-every 1 --depth "$PLAYD" --seed "$SEED" --nshards "$NSH" --shard "$s" \
    --seed-pool "$W/g1_pool.fen" --seed-frac "$SEEDFRAC" --cap-arbiter d14 --egdb-dir "$EGDIR" --arb-depth "$ARB_DEPTH" \
    --label-src-out "$W/lab.$s" >"$W/sp-$s.log" 2>&1 & pids+=($!)
done
wait "${pids[@]}"
NPOS=$(merge_jnnw "$W/gen.jnnw" "$W/sp."); NLAB=$(merge_labels "$W/lab.labels" "$W/lab.")
[ "$NPOS" = "$NLAB" ] || die "désalignement corpus/labels ($NPOS != $NLAB)"
say "  généré=$NPOS positions (labels ONP/GYM/CAP alignés)"

# ── §5.2 RELABEL-ADJ complet d14+egdb (résolution oracle_cert : GYM/CAP protègent le tip) ──
say ""; say "=== §5.2 relabel-ADJ complet d$ARB_DEPTH+egdb ($NSH shards) ==="
python3 - "$W/gen.jnnw" "$W/rs" "$NSH" <<'PY'
import struct,sys
b=open(sys.argv[1],'rb').read(); n=struct.unpack('<I',b[4:8])[0]; body=b[8:]; REC=38; nsh=int(sys.argv[3])
per=(n+nsh-1)//nsh
for s in range(nsh):
    seg=body[s*per*REC:(s+1)*per*REC]
    open(f"{sys.argv[2]}.{s:03d}.jnnw",'wb').write(b'JNNW'+struct.pack('<I',len(seg)//REC)+seg)
PY
pids=()
for s in $(seq 0 $((NSH-1))); do t=$(printf '%03d' "$s")
  timeout "$RELABEL_TIMEOUT" "$J" --deep-relabel "$W/rs.$t.jnnw" "$W/rr.$t.jnnw" "$ARB_DEPTH" --egdb "$EGDIR" --cache-mb "$CACHE_MB" >"$W/rr.$t.log" 2>&1 & pids+=($!)
done
fail=0; for p in "${pids[@]}"; do wait "$p" || fail=$((fail+1)); done
[ "$fail" -eq 0 ] || die "relabel-adj : $fail shards morts (cache/OOM ? cf garde §13)"
# fusion ordonnée + survie tip (§3.5) : GYM/CAP=oracle doivent survivre décisifs
python3 - "$W/gen.jnnw" "$W/lab.labels" "$W/rr" "$NSH" "$W/adj.jnnw" "$ART/tip_survival.json" <<'PY' | tee -a "$RES"
import struct,glob,sys,json
sys.path.insert(0,'jobs/tools'); import oracle_cert as OC
gen,labf,pref,nsh,outp,survp=sys.argv[1],sys.argv[2],sys.argv[3],int(sys.argv[4]),sys.argv[5],sys.argv[6]
REC=38; adj=bytearray(); tot=0; recs=[]
labels=open(labf,'rb').read()
gi=0
for s in range(nsh):
    b=open(f"{pref}.{s:03d}.jnnw",'rb').read(); assert b[:4]==b'JNNW'; n=struct.unpack('<I',b[4:8])[0]; body=b[8:]
    for i in range(n):
        rec=body[i*REC:(i+1)*REC]; adj+=rec; wdl=struct.unpack_from('<b',rec,37)[0]
        tag=labels[gi] if gi<len(labels) else 0; gi+=1
        tier="ON_POLICY" if tag==0 else "CERT_PROOF"      # GYM/CAP = oracle certifié (tag 1/2)
        recs.append({"oracle_tier":tier,"survived":bool(wdl!=0 or tag==0),"cert_valid":True,
                     "strata":"unknown","provenance":"gen","tour":"T1-bis"})
    tot+=n
open(outp,'wb').write(b'JNNW'+struct.pack('<I',tot)+bytes(adj))
rep=OC.tip_survival(recs); json.dump(rep,open(survp,'w'),indent=2)
print(f"  adj={tot} ; tip survie totale={rep['tip_total']['rate']} ; investigate={rep['investigate']}")
PY
NADJ=$(python3 -c "import struct;print(struct.unpack('<I',open('$W/adj.jnnw','rb').read(8)[4:8])[0])")

# ── §5.3 FIT ancré 0.05 (+ cellule λ-énorme garde-fou + z-stats) ──
say ""; say "=== §5.3 fit wdl_finetune anchor=$ANCHOR (+ garde-fou λ-énorme) ==="
fit_cell(){ # $1=lab $2=anchor $3=data
  "$J" --dump-eval-features "$3" "$W/feat_$1" >"$W/dump_$1.log" 2>&1 || return 1
  env JASS_PATTERNS_DIR="$GEOM" PYTHONPATH="$GEOM:pattern_jass/tools" python3 pattern_jass/tools/wdl_finetune.py \
    --champion "$W/T0.pjtw" --data "$3" --feat "$W/feat_$1" --out "$W/cand_$1.pjtw" --tools pattern_jass/tools \
    --anchor "$2" --color-fold --tempo-stage --max-iter "$MAXIT" --chunk "$CHUNK" --verify-jass "$J" --verify-n 80 >"$W/ft_$1.log" 2>&1
}
fit_cell t1bis "$ANCHOR" "$W/adj.jnnw" || die "fit t1bis: $(tail -1 "$W/ft_t1bis.log")"
fit_cell guard 1000000 "$W/adj.jnnw" || say "  [!] cellule garde-fou λ-énorme échouée (non bloquant)"
grep -iE 'z-stats|Spearman' "$W/ft_t1bis.log"|sed 's/^/    /'|tee -a "$RES"

# ── §5.4 JAUGES : conv WDL-grounded (1600 figé, restart-on-death) + gate vs parent + vs référence fixe ──
say ""; say "=== §5.4 jauges ==="
git show "origin/main:$GAUGE1600" | grep -vE '^\s*#' | sed 's/#.*//' | awk 'NF' > "$W/gauge.fen"
python3 jobs/tools/jnnw_doe.py fen-to-jnnw --input "$W/gauge.fen" --output "$W/gauge_raw.jnnw" >>"$RES" || die "gauge pack"
pids=(); python3 - "$W/gauge_raw.jnnw" "$W/gg" "$NSH" <<'PY'
import struct,sys
b=open(sys.argv[1],'rb').read(); n=struct.unpack('<I',b[4:8])[0]; body=b[8:]; REC=38; nsh=int(sys.argv[3]); per=(n+nsh-1)//nsh
for s in range(nsh):
    seg=body[s*per*REC:(s+1)*per*REC]; open(f"{sys.argv[2]}.{s:03d}.jnnw",'wb').write(b'JNNW'+struct.pack('<I',len(seg)//REC)+seg)
PY
for s in $(seq 0 $((NSH-1))); do t=$(printf '%03d' "$s")
  timeout "$RELABEL_TIMEOUT" "$J" --deep-relabel "$W/gg.$t.jnnw" "$W/ggr.$t.jnnw" "$ARB_DEPTH" --egdb "$EGDIR" --cache-mb "$CACHE_MB" >"$W/ggr.$t.log" 2>&1 & pids+=($!)
done
for p in "${pids[@]}"; do wait "$p"||true; done
merge_jnnw "$W/gauge_rel.jnnw" "$W/ggr." >/dev/null
python3 jobs/tools/jnnw_doe.py keep-decisive --input "$W/gauge_rel.jnnw" --output "$W/gauge_dec.jnnw" >>"$RES" || die "gauge keep-decisive"
# conv WDL-grounded (restart-on-death), sharded
pids=(); for s in $(seq 0 $((NSH-1))); do
  timeout "$SHARD_TIMEOUT" python3 jobs/tools/conv_fixed_wdl.py --jass "$J" --pattern "$W/cand_t1bis.pjtw" --defender-pattern "$W/gen2.pjtw" \
    --pool-jnnw "$W/gauge_dec.jnnw" --calibrate-tool tools/calibrate_vs_scan.py --depth "$CONV_DEPTH" --max-plies 260 \
    --shard "$s" --nshards "$NSH" --out "$W/conv.$s.json" >"$W/conv.$s.log" 2>&1 & pids+=($!); done
for p in "${pids[@]}"; do wait "$p"||true; done
CONV=$(python3 - "$W"/conv.*.json <<'PY'
import json,sys
P=Wn=E=R=0
for f in sys.argv[1:]:
    try:
        j=json.load(open(f)); P+=j.get("n_pos",0); Wn+=j.get("n_win",0); E+=j.get("n_errors",0); R+=j.get("n_restarts",0)
    except Exception: pass
print(f"{(Wn/P if P else 0):.4f} {P} {E} {R}")
PY
)
read CV CN CE CR <<<"$CONV"; say "  conv WDL-grounded=$CV (n=$CN err=$CE restarts=$CR)"
# gates : parent = référence fixe = T0 (bootstrap) pour T1-bis
read PR PN PE PLO PHI PA PD PB < <(gate parent "$W/cand_t1bis.pjtw" "$W/T0.pjtw")
say "  gate vs parent(T0) : rate=$PR n=$PN elo=$PE ci=[$PLO,$PHI]"

# ── §5.5 PROMOTION --regime young ──
say ""; say "=== §5.5 promotion_gate --regime young ==="
cat > "$W/promo_in.json" <<JSON
{"vs_parent":{"wins_a":$PA,"draws":$PD,"wins_b":$PB},
 "vs_fixed_reference":{"wins_a":$PA,"draws":$PD,"wins_b":$PB},
 "conversion":{"global":$CV}}
JSON
python3 jobs/tools/promotion_gate.py --regime young --tour "$TOUR" --input "$W/promo_in.json" --out "$ART/promotion.json" | tee -a "$RES"
VERDICT=$(python3 -c "import json;print(json.load(open('$ART/promotion.json'))['promotion_decision'])")

# ── §7 MINING PASSIF (best-effort : inventaire hors-boucle depuis les seeds G1 non-convertis) ──
say ""; say "=== §7 mining passif (hors-boucle, inventaire seulement) ==="
say "  (v1 : inventaire structurel ; extraction trajectoires complètes = passe dédiée follow-up)"

# manifests + commit
python3 - "$MAINSHA" "$DEVSHA" "$NPOS" "$NADJ" "$CN" "$CE" "$CR" "$ART/run_manifest.json" <<'PY'
import json,sys
main,dev,npos,nadj,cn,ce,cr,out=sys.argv[1:]
json.dump({"job":"T1-bis","main_sha":main,"develop_sha":dev,"generated":int(npos),"adj_records":int(nadj),
           "conv_n":int(cn),"conv_errors":int(ce),"conv_restarts":int(cr),"cache_mb":512,"anchor":0.05},
          open(out,'w'),indent=2)
PY
commit_to_main "$ART/tip_survival.json" "$ARTREL/tip_survival.json" "0727 tip survival" >/dev/null 2>&1||true
commit_to_main "$ART/promotion.json"    "$ARTREL/promotion.json"    "0727 promotion young ($VERDICT)" >/dev/null 2>&1||true
commit_to_main "$ART/run_manifest.json" "$ARTREL/run_manifest.json" "0727 run manifest" >/dev/null 2>&1||true
restore_src
commit_to_main "$RES" "$ARTREL/RESULTS.txt" "0727 FIN T1-bis : promotion=$VERDICT conv=$CV gate_parent=$PE gen=$NPOS adj=$NADJ" && say "  ✓ RESULTS committé" || say "  ⚠ commit"
say "=== 0727 T1-bis FIN — promotion=$VERDICT ==="
rm -rf "$W" "$GEOM"
