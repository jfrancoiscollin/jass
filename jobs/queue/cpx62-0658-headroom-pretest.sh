#!/usr/bin/env bash
# id: cpx62-0658-headroom-pretest
# description: ÉTAPE 0 du mémo boucle auto-amélioration (thèse JFC : prof = SOI + du TEMPS). PRÉ-TEST HEADROOM : le
# champion jass(gen2-mmto) joué à mt-10s et mt-30s bat-il Scan-mt0.2 (= le niveau-prof qu'il a ABSORBÉ, cf 0625) ? Si oui,
# jass-mt-long est un prof PLUS FORT que le tutorat reçu => le carburant d'auto-amélioration existe => ÉTAPE 1. Sinon
# STOP éval, search d'abord. ~96 games mt10 + ~64 games mt30, openings appariés ≥38p, parallélisé (16 procs calibrate, un
# sous-lot d'openings chacun). Harnais : timeout x5 (develop) tolère l'overshoot movetime-endgame. On cherche un SIGNE
# (gate rate vs 0.5), pas un Elo fin. AUCUN NNUE, aucune modif champion. gen2-mmto reste champion.
set -uo pipefail
cd /root/jass
NCPU=$(nproc); export TMPDIR=/root/jass/.compile-tmp; mkdir -p "$TMPDIR"
ART="/root/jass/jobs/results/cpx62-0658-headroom-pretest/artefacts"; mkdir -p "$ART"
ARTREL="jobs/results/cpx62-0658-headroom-pretest/artefacts"
RES="$ART/RESULTS.txt"; : > "$RES"; say(){ echo "$@" | tee -a "$RES"; }
W=/root/cw-headroom; rm -rf "$W"; mkdir -p "$W"
SCAN_BIN=/root/jass-scan/scan_linux
FLAGS="-DJASS_ENDGAME_FEATURES=ON -DJASS_KING_MOBILITY=ON -DJASS_SCAN_PARITY=ON -DJASS_TEMPO_STAGE=ON"
GEN2_GZ=jobs/results/BAKE-gen2-mmto/artefacts/champion-gen2-mmto.pjtw.gz
CORPUS_GZ=jobs/results/cpx62-0556-gen2M-mixdepth/artefacts/corpus-mix2M.jnnw.gz
SCAN_MT=0.2                       # le niveau-prof absorbé (0625)
NOPEN_10=48; NOPEN_30=32; PAIRS=1 # games = NOPEN*PAIRS*2 (colour-swap) : mt10~96, mt30~64

commit_to_main(){ local ab="$1" rel="$2" msg="$3"
  for a in 1 2 3 4 5; do git fetch origin main --quiet 2>/dev/null||true
    local idx="/root/.ti.$$.$RANDOM"; rm -f "$idx"; GIT_INDEX_FILE="$idx" git read-tree origin/main 2>/dev/null||return 1
    local b; b=$(git hash-object -w "$ab")||return 1
    GIT_INDEX_FILE="$idx" git update-index --add --cacheinfo 100644 "$b" "$rel"
    local t; t=$(GIT_INDEX_FILE="$idx" git write-tree); local c; c=$(printf '%s\n' "$msg"|git commit-tree "$t" -p origin/main)
    git push origin "$c:main" 2>/dev/null && { rm -f "$idx"; return 0; }; sleep $((a*4)); done; return 1; }

say "=== ÉTAPE 0 HEADROOM : jass(gen2-mmto) mt-long vs Scan-mt$SCAN_MT — HEAD $(git log --oneline -1|cat) ==="
[ -x "$SCAN_BIN" ] || { rm -rf /root/jass-scan; git clone --depth 1 https://github.com/rhalbersma/scan /root/jass-scan >"$W/scan-clone.log" 2>&1 || true; chmod +x "$SCAN_BIN" 2>/dev/null || true; }
[ -x "$SCAN_BIN" ] || { say "  ❌ ABORT Scan"; commit_to_main "$RES" "$ARTREL/RESULTS.txt" "0658 ABORT Scan"; exit 5; }
git fetch origin +refs/heads/develop:refs/remotes/origin/develop --quiet 2>/dev/null || true
git show origin/develop:src/main.cpp > src/main.cpp
git show origin/develop:tools/calibrate_vs_scan.py > tools/calibrate_vs_scan.py
restore_src(){ git checkout -- src/main.cpp tools/calibrate_vs_scan.py 2>/dev/null||true; }
cmake -S . -B "$W/build" -DCMAKE_BUILD_TYPE=Release $FLAGS >"$W/cmake.log" 2>&1
cmake --build "$W/build" -j"$NCPU" --target jass >"$W/build.log" 2>&1 || { say "BUILD FAIL"; tail -12 "$W/build.log"|sed 's/^/  /'|tee -a "$RES"; commit_to_main "$RES" "$ARTREL/RESULTS.txt" "0658 BUILD FAIL"; restore_src; exit 6; }
J="$W/build/jass"
git show "origin/main:$GEN2_GZ" | gunzip > "$W/gen2.pjtw" || { say "ABORT gen2"; restore_src; exit 4; }

# openings généralistes ≥38p appariées
git show "origin/main:$CORPUS_GZ" | gunzip > "$W/corpus.jnnw"
python3 - "$W/corpus.jnnw" "$W/gen.fen" 64 <<'PY' 2>&1 | tee -a "$RES"
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
NG=$(grep -c . "$W/gen.fen"); say "  openings ≥38p : $NG"; [ "$NG" -gt 30 ] 2>/dev/null || { say "ABORT openings"; restore_src; exit 7; }
say "  ✓ build+Scan+gen2 ; contournement overshoot = timeout x5 (harnais develop)"

# ---- cellule : jass(gen2) mt=$1 vs Scan-mt$SCAN_MT, sur $2 openings, 16 procs ----
cell(){ local mt="$1" nop="$2"; local pref="$W/hr_${mt}"; rm -f "${pref}".* "${pref}_op".*
  head -n "$nop" "$W/gen.fen" > "${pref}.openings"
  # split openings round-robin en NCPU sous-fichiers
  python3 - "${pref}.openings" "${pref}_op" "$NCPU" <<'PY'
import sys
lines=[l for l in open(sys.argv[1]) if l.strip()]; pref=sys.argv[2]; nc=int(sys.argv[3])
for s in range(nc):
    sub=lines[s::nc]
    open(f"{pref}.{s}",'w').write("".join(sub))
PY
  for s in $(seq 0 $((NCPU-1))); do
    [ -s "${pref}_op.$s" ] || { : > "${pref}.$s"; continue; }
    python3 tools/calibrate_vs_scan.py --jass "$J" --scan "$SCAN_BIN" --jass-pattern "$W/gen2.pjtw" \
      --jass-movetime "$mt" --scan-movetime "$SCAN_MT" --pairs "$PAIRS" --max-plies 180 \
      --openings-file "${pref}_op.$s" >"${pref}.$s" 2>&1 &
  done; wait
  python3 - "$mt" "$SCAN_MT" "$W/.hr" "${pref}".* <<'PY'
import sys,math,re,glob
mt,smt,outp=sys.argv[1],sys.argv[2],sys.argv[3]; jw=sw=dr=0
for f in sys.argv[4:]:
    if f.endswith(".openings") or "_op." in f: continue
    try:
        last=None
        for l in open(f):
            m=re.search(r'Jass=(\d+)\s+Scan=(\d+)\s+Draws=(\d+)',l)
            if m: last=m
        if last: jw+=int(last.group(1)); sw+=int(last.group(2)); dr+=int(last.group(3))
    except Exception: pass
g=jw+sw+dr; r=(jw+0.5*dr)/g if g else 0
se=(0.5/(g**0.5)) if g else 1; elo=-400*math.log10(1/r-1) if 0<r<1 else 0
lo,hi=r-1.96*se,r+1.96*se
vd="HEADROOM>0 (jass-mt bat/égale le prof absorbé)" if lo>0.5 else ("headroom<0 (sous le prof)" if hi<0.5 else "≈ prof absorbé (limite)")
open(outp,'w').write(f"  [jass(gen2) mt{mt}s vs Scan-mt{smt}] Jass={jw} Scan={sw} Draws={dr} n={g} rate={r:.3f}+-{1.96*se:.3f} elo~{elo:+.0f} => {vd}\n")
PY
  cat "$W/.hr" | tee -a "$RES"; }

say ""; say "=== cellule mt-10s (${NOPEN_10} openings ~$((NOPEN_10*PAIRS*2)) games) ==="
cell 10 "$NOPEN_10"
commit_to_main "$RES" "$ARTREL/RESULTS.txt" "0658 headroom mt10" >/dev/null 2>&1 || true
say ""; say "=== cellule mt-30s (${NOPEN_30} openings ~$((NOPEN_30*PAIRS*2)) games) ==="
cell 30 "$NOPEN_30"
restore_src
say ""
say "  GATE : rate ≥ 0.5 hors-IC (jass-mt-long ≥ Scan-mt$SCAN_MT) => CARBURANT existe => ÉTAPE 1 (corpus prof-soi mt-long)."
say "  rate < 0.5 nettement => pas de headroom => STOP éval, search d'abord (0657 DOE, fix movetime), re-tester après bake."
commit_to_main "$RES" "$ARTREL/RESULTS.txt" "0658 FIN headroom : jass(gen2) mt-long vs Scan-mt$SCAN_MT (le carburant auto-amélioration existe-t-il)" \
  && say "  RESULTS committé ✓" || say "  ⚠ commit échoue"
say "=== fin pré-test headroom ==="
