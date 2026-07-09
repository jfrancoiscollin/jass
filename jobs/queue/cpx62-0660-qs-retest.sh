#!/usr/bin/env bash
# id: cpx62-0660-qs-retest
# description: RE-TEST QUIESCENCE avec gen2-mmto (question JFC : la qs qu'on a bridée, sans contrainte de temps, ferme-t-elle
# le gap ?). A4-bis (0592, ANCIENNE éval) : à profondeur fixe d9, qs_forcing=6,qs_promo=6 HALVAIT le gap vs Scan (-335->-175)
# mais MOURAIT au movetime (0593) et ne co-adaptait pas à l'ordering (0603). Ouvert = la CO-ADAPTATION avec la NOUVELLE éval
# (next-step #4 jamais fait). Ici, à PROFONDEUR FIXE d9 : (1) d9-vs-Scan gen2-mmto default vs qs6 vs qsmax = le gap se
# ferme-t-il plus / autant avec gen2 ? (2) self-play A/B qs6/qsmax vs default = la qs forte améliore-t-elle le choix de coup
# de gen2 ? Runtime --search-params (1 build). Profondeur fixe = pas de bug movetime-overshoot. AUCUN NNUE. gen2 reste champion.
set -uo pipefail
cd /root/jass
NCPU=$(nproc); export TMPDIR=/root/jass/.compile-tmp; mkdir -p "$TMPDIR"
ART="/root/jass/jobs/results/cpx62-0660-qs-retest/artefacts"; mkdir -p "$ART"
ARTREL="jobs/results/cpx62-0660-qs-retest/artefacts"
RES="$ART/RESULTS.txt"; : > "$RES"; say(){ echo "$@" | tee -a "$RES"; }
W=/root/cw-qs-retest; rm -rf "$W"; mkdir -p "$W"
SCAN_BIN=/root/jass-scan/scan_linux
FLAGS="-DJASS_ENDGAME_FEATURES=ON -DJASS_KING_MOBILITY=ON -DJASS_SCAN_PARITY=ON -DJASS_TEMPO_STAGE=ON"
GEN2_GZ=jobs/results/BAKE-gen2-mmto/artefacts/champion-gen2-mmto.pjtw.gz
CORPUS_GZ=jobs/results/cpx62-0556-gen2M-mixdepth/artefacts/corpus-mix2M.jnnw.gz
DEPTH=9; NOPEN=64; PAIRS=8
QS6="qs_forcing_depth=6,qs_promo_depth=6"
QSMAX="qs_forcing_depth=6,qs_promo_depth=6,qs_threat_ext=1,qs_sacs=1"

commit_to_main(){ local ab="$1" rel="$2" msg="$3"
  for a in 1 2 3 4 5; do git fetch origin main --quiet 2>/dev/null||true
    local idx="/root/.ti.$$.$RANDOM"; rm -f "$idx"; GIT_INDEX_FILE="$idx" git read-tree origin/main 2>/dev/null||return 1
    local b; b=$(git hash-object -w "$ab")||return 1
    GIT_INDEX_FILE="$idx" git update-index --add --cacheinfo 100644 "$b" "$rel"
    local t; t=$(GIT_INDEX_FILE="$idx" git write-tree); local c; c=$(printf '%s\n' "$msg"|git commit-tree "$t" -p origin/main)
    git push origin "$c:main" 2>/dev/null && { rm -f "$idx"; return 0; }; sleep $((a*4)); done; return 1; }

say "=== RE-TEST QUIESCENCE gen2-mmto (profondeur fixe d$DEPTH) — HEAD $(git log --oneline -1|cat) ==="
[ -x "$SCAN_BIN" ] || { rm -rf /root/jass-scan; git clone --depth 1 https://github.com/rhalbersma/scan /root/jass-scan >"$W/scan-clone.log" 2>&1 || true; chmod +x "$SCAN_BIN" 2>/dev/null || true; }
[ -x "$SCAN_BIN" ] || { say "  ❌ ABORT Scan"; commit_to_main "$RES" "$ARTREL/RESULTS.txt" "0660 ABORT Scan"; exit 5; }
git fetch origin +refs/heads/develop:refs/remotes/origin/develop --quiet 2>/dev/null || true
git show origin/develop:src/main.cpp > src/main.cpp
git show origin/develop:tools/calibrate_vs_scan.py > tools/calibrate_vs_scan.py
git show origin/develop:tools/jass_vs_jass_arch.py > tools/jass_vs_jass_arch.py
restore_src(){ git checkout -- src/main.cpp tools/calibrate_vs_scan.py tools/jass_vs_jass_arch.py 2>/dev/null||true; }
cmake -S . -B "$W/build" -DCMAKE_BUILD_TYPE=Release $FLAGS >"$W/cmake.log" 2>&1
cmake --build "$W/build" -j"$NCPU" --target jass >"$W/build.log" 2>&1 || { say "BUILD FAIL"; tail -12 "$W/build.log"|sed 's/^/  /'|tee -a "$RES"; commit_to_main "$RES" "$ARTREL/RESULTS.txt" "0660 BUILD FAIL"; restore_src; exit 6; }
J="$W/build/jass"
git show "origin/main:$GEN2_GZ" | gunzip > "$W/gen2.pjtw" || { say "ABORT gen2"; restore_src; exit 4; }
git show "origin/main:$CORPUS_GZ" | gunzip > "$W/corpus.jnnw"
python3 - "$W/corpus.jnnw" "$W/gen.fen" "$NOPEN" <<'PY' 2>&1 | tee -a "$RES"
import struct,sys
d=open(sys.argv[1],'rb').read(); n=struct.unpack('<I',d[4:8])[0]; REC=38; body=d[8:]; K=int(sys.argv[3])
def fen(wm,wk,bm,bk,stm):
    Wl=[str(s) for s in range(1,51) if (wm>>(s-1))&1]+["K"+str(s) for s in range(1,51) if (wk>>(s-1))&1]
    Bl=[str(s) for s in range(1,51) if (bm>>(s-1))&1]+["K"+str(s) for s in range(1,51) if (bk>>(s-1))&1]
    return f"{'B' if stm==1 else 'W'}:W{','.join(Wl)}:B{','.join(Bl)}"
out=[]; step=max(1,n//(K*40))
for i in range(0,n,step):
    r=body[i*REC:(i+1)*REC]; wm,wk,bm,bk=struct.unpack('<QQQQ',r[:32]); stm=r[32]
    if bin(wm).count('1')+bin(wk).count('1')+bin(bm).count('1')+bin(bk).count('1')>=38: out.append(fen(wm,wk,bm,bk,stm))
    if len(out)>=K: break
open(sys.argv[2],'w').write("\n".join(out)+"\n"); print(f"  generaliste : {len(out)} openings")
PY
NG=$(grep -c . "$W/gen.fen"); say "  openings ≥38p : $NG ; build+Scan+gen2 ✓"; [ "$NG" -gt 20 ] 2>/dev/null || { say "ABORT openings"; restore_src; exit 7; }

# ---- PARTIE 1 : d9-vs-Scan (calibrate, profondeur fixe) — le gap se ferme-t-il ? ----
say ""; say "=== (1) d$DEPTH-vs-Scan : gap gen2-mmto default vs qs6 vs qsmax (le levier direct) ==="
scan_cell(){ local name="$1" sp="$2"; local pref="$W/sc_$name"; rm -f "${pref}".* "${pref}_op".*
  python3 - "$W/gen.fen" "${pref}_op" "$NCPU" <<'PY'
import sys
lines=[l for l in open(sys.argv[1]) if l.strip()]; pref=sys.argv[2]; nc=int(sys.argv[3])
for s in range(nc): open(f"{pref}.{s}",'w').write("".join(lines[s::nc]))
PY
  local spa=(); [ -n "$sp" ] && spa=(--jass-search-params "$sp")
  for s in $(seq 0 $((NCPU-1))); do
    [ -s "${pref}_op.$s" ] || continue
    timeout 3000 python3 tools/calibrate_vs_scan.py --jass "$J" --scan "$SCAN_BIN" --jass-pattern "$W/gen2.pjtw" \
      --depth "$DEPTH" --pairs "$PAIRS" --max-plies 180 --openings-file "${pref}_op.$s" "${spa[@]}" >"${pref}.$s" 2>&1 &
  done; wait
  python3 - "$name" "$sp" "$W/.sc" "${pref}".* <<'PY'
import sys,math,re
name,sp,outp=sys.argv[1],sys.argv[2],sys.argv[3]; jw=sw=dr=0
for f in sys.argv[4:]:
    if "_op." in f: continue
    try:
        last=None
        for l in open(f):
            m=re.search(r'Jass=(\d+)\s+Scan=(\d+)\s+Draws=(\d+)',l)
            if m: last=m
        if last: jw+=int(last.group(1)); sw+=int(last.group(2)); dr+=int(last.group(3))
    except Exception: pass
g=jw+sw+dr; r=(jw+0.5*dr)/g if g else 0; se=(0.5/(g**0.5)) if g else 1
elo=-400*math.log10(1/r-1) if 0<r<1 else 0
open(outp,'w').write(f"  [d9-vs-Scan | {name:8s} {sp:52s}] Jass={jw} Scan={sw} D={dr} n={g} rate={r:.3f}+-{1.96*se:.3f} elo~{elo:+.0f}\n")
PY
  cat "$W/.sc" | tee -a "$RES"; }
scan_cell default ""
commit_to_main "$RES" "$ARTREL/RESULTS.txt" "0660 d9-vs-Scan default" >/dev/null 2>&1 || true
scan_cell qs6 "$QS6"
commit_to_main "$RES" "$ARTREL/RESULTS.txt" "0660 d9-vs-Scan qs6" >/dev/null 2>&1 || true
scan_cell qsmax "$QSMAX"
commit_to_main "$RES" "$ARTREL/RESULTS.txt" "0660 d9-vs-Scan qsmax" >/dev/null 2>&1 || true

# ---- PARTIE 2 : self-play A/B d9 (qs fort vs default, même éval gen2) ----
say ""; say "=== (2) self-play A/B d$DEPTH : qs fort (A) vs default (B), même éval gen2-mmto ==="
sp_cell(){ local name="$1" sp="$2"; local pref="$W/sp_$name"; rm -f "${pref}".*
  for s in $(seq 0 $((NCPU-1))); do timeout 3000 python3 tools/jass_vs_jass_arch.py \
    --jass-a "$J" --pattern-a "$W/gen2.pjtw" --jass-b "$J" --pattern-b "$W/gen2.pjtw" --search-params-a "$sp" \
    --depth "$DEPTH" --pairs "$PAIRS" --max-plies 160 --shard "$s" --nshards "$NCPU" --quiet --openings-file "$W/gen.fen" >"${pref}.$s" 2>&1 & done; wait
  python3 - "$name" "$sp" "$W/.sp" "${pref}".* <<'PY'
import sys,math
name,sp,outp=sys.argv[1],sys.argv[2],sys.argv[3]; a=d=b=0
for f in sys.argv[4:]:
    try:
        for l in open(f):
            if l.startswith("RESULT"): _,x,y,z=l.split(); a+=int(x);d+=int(y);b+=int(z)
    except Exception: pass
g=a+d+b; r=(a+0.5*d)/g if g else 0; se=(0.5/(g**0.5)) if g else 1
elo=-400*math.log10(1/r-1) if 0<r<1 else 0; lo,hi=r-1.96*se,r+1.96*se
vd="qs fort AJOUTE hors-IC" if lo>0.5 else ("qs fort PERD hors-IC" if hi<0.5 else "neutre")
open(outp,'w').write(f"  [self-play d9 | {name:6s} vs default {sp:52s}] A={a} B={b} D={d} n={g} rate_A={r:.3f}+-{1.96*se:.3f} elo~{elo:+.0f} => {vd}\n")
PY
  cat "$W/.sp" | tee -a "$RES"; }
sp_cell qs6 "$QS6"; commit_to_main "$RES" "$ARTREL/RESULTS.txt" "0660 self-play qs6" >/dev/null 2>&1 || true
sp_cell qsmax "$QSMAX"
restore_src
say ""; say "  LECTURE : (1) rate d9-vs-Scan qs6/qsmax > default => la qs forte ferme le gap par-nœud AVEC gen2 (co-adaptation OK)."
say "  (2) self-play qs fort >0.5 hors-IC => la qs forte améliore le choix de coup de gen2 à prof fixe."
say "  ⚠ RAPPEL : gain à PROFONDEUR FIXE ; la conversion en MOVETIME est un 2e test (0593 = mort au mt ; résidu = NPS -134)."
commit_to_main "$RES" "$ARTREL/RESULTS.txt" "0660 FIN re-test qs gen2-mmto : la qs forte ferme-t-elle le gap par-noeud avec la nouvelle eval" \
  && say "  RESULTS committé ✓" || say "  ⚠ commit échoue"
say "=== fin re-test quiescence ==="
