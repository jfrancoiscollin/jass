#!/usr/bin/env bash
# id: cpx62-0662-nps-ab
# description: VALIDATION Elo du gain NPS (session opt). Deux binaires jass, MÊME éval gen2-mmto, ne différant QUE par les
# optimisations NPS byte-identiques bakées cette session (scan_eval : dot creux + tempo/balance/skew popcount-masqués,
# ~+13-15% NPS). NEW = main HEAD (avec opts) ; OLD = main HEAD mais scan_eval.cpp = blob pré-NPS 9f622a4e (clean). A/B au
# MOVETIME (mt0.2 + mt0.3, généraliste) : à temps fixe le +NPS cherche plus profond → doit GAGNER. GATE : NEW>0.5 hors-IC =>
# le NPS se convertit en Elo movetime (la prémisse du programme validée). Byte-identique à prof fixe (0 Elo) donc tout écart
# = pur bénéfice vitesse. AUCUN NNUE. gen2-mmto reste champion.
set -uo pipefail
cd /root/jass
NCPU=$(nproc); export TMPDIR=/root/jass/.compile-tmp; mkdir -p "$TMPDIR"
ART="/root/jass/jobs/results/cpx62-0662-nps-ab/artefacts"; mkdir -p "$ART"
ARTREL="jobs/results/cpx62-0662-nps-ab/artefacts"
RES="$ART/RESULTS.txt"; : > "$RES"; say(){ echo "$@" | tee -a "$RES"; }
W=/root/cw-nps-ab; rm -rf "$W"; mkdir -p "$W"
FLAGS="-DJASS_ENDGAME_FEATURES=ON -DJASS_KING_MOBILITY=ON -DJASS_SCAN_PARITY=ON -DJASS_TEMPO_STAGE=ON"
GEN2_GZ=jobs/results/BAKE-gen2-mmto/artefacts/champion-gen2-mmto.pjtw.gz
CORPUS_GZ=jobs/results/cpx62-0556-gen2M-mixdepth/artefacts/corpus-mix2M.jnnw.gz
PRE_NPS_BLOB=9f622a4e59fe36741bcb7697c5820dfc8c848303   # scan_eval.cpp clean (avant dot-creux + masks)
NOPEN=96; PAIRS=10

commit_to_main(){ local ab="$1" rel="$2" msg="$3"
  for a in 1 2 3 4 5; do git fetch origin main --quiet 2>/dev/null||true
    local idx="/root/.ti.$$.$RANDOM"; rm -f "$idx"; GIT_INDEX_FILE="$idx" git read-tree origin/main 2>/dev/null||return 1
    local b; b=$(git hash-object -w "$ab")||return 1
    GIT_INDEX_FILE="$idx" git update-index --add --cacheinfo 100644 "$b" "$rel"
    local t; t=$(GIT_INDEX_FILE="$idx" git write-tree); local c; c=$(printf '%s\n' "$msg"|git commit-tree "$t" -p origin/main)
    git push origin "$c:main" 2>/dev/null && { rm -f "$idx"; return 0; }; sleep $((a*4)); done; return 1; }

say "=== VALIDATION Elo du gain NPS (NEW opts vs OLD clean, même éval) — HEAD $(git log --oneline -1|cat) ==="
git show "origin/main:src/scan_eval.cpp" | grep -q "g_emasks" && say "  main scan_eval = NPS-opt ✓" || { say "ABORT main sans opts NPS"; exit 4; }

# ---- build NEW (main HEAD, avec opts NPS) ----
cmake -S . -B "$W/bnew" -DCMAKE_BUILD_TYPE=Release $FLAGS >"$W/cmnew.log" 2>&1
cmake --build "$W/bnew" -j"$NCPU" --target jass >"$W/bnew.log" 2>&1 || { say "BUILD NEW FAIL"; tail -12 "$W/bnew.log"|sed 's/^/  /'|tee -a "$RES"; commit_to_main "$RES" "$ARTREL/RESULTS.txt" "0662 BUILD NEW FAIL"; exit 6; }
JNEW="$W/bnew/jass"; say "  ✓ build NEW (opts NPS)"

# ---- build OLD (scan_eval.cpp = blob pré-NPS clean) ----
cp src/scan_eval.cpp "$W/scan_eval.NEW.cpp"
if ! git cat-file blob "$PRE_NPS_BLOB" > src/scan_eval.cpp 2>/dev/null; then
  git fetch origin main --unshallow >/dev/null 2>&1 || git fetch origin main >/dev/null 2>&1 || true
  git cat-file blob "$PRE_NPS_BLOB" > src/scan_eval.cpp 2>/dev/null || { say "ABORT blob pré-NPS introuvable"; cp "$W/scan_eval.NEW.cpp" src/scan_eval.cpp; exit 4; }
fi
grep -q "g_emasks" src/scan_eval.cpp && { say "ABORT: OLD contient encore les opts"; cp "$W/scan_eval.NEW.cpp" src/scan_eval.cpp; exit 4; }
cmake -S . -B "$W/bold" -DCMAKE_BUILD_TYPE=Release $FLAGS >"$W/cmold.log" 2>&1
cmake --build "$W/bold" -j"$NCPU" --target jass >"$W/bold.log" 2>&1 || { say "BUILD OLD FAIL"; tail -12 "$W/bold.log"|sed 's/^/  /'; cp "$W/scan_eval.NEW.cpp" src/scan_eval.cpp; exit 6; }
JOLD="$W/bold/jass"; cp "$W/scan_eval.NEW.cpp" src/scan_eval.cpp   # restore working tree
say "  ✓ build OLD (clean pré-NPS)"

git show "origin/main:$GEN2_GZ" | gunzip > "$W/gen2.pjtw" || { say "ABORT gen2"; exit 4; }
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
NG=$(grep -c . "$W/gen.fen"); say "  openings ≥38p : $NG"; [ "$NG" -gt 20 ] 2>/dev/null || { say "ABORT openings"; exit 7; }

abcell(){ local mt="$1"; local pref="$W/ab_$mt"; rm -f "${pref}".*
  for s in $(seq 0 $((NCPU-1))); do timeout 3000 python3 tools/jass_vs_jass_arch.py \
    --jass-a "$JNEW" --pattern-a "$W/gen2.pjtw" --jass-b "$JOLD" --pattern-b "$W/gen2.pjtw" \
    --movetime "$mt" --pairs "$PAIRS" --max-plies 160 --shard "$s" --nshards "$NCPU" --quiet --openings-file "$W/gen.fen" >"${pref}.$s" 2>&1 & done; wait
  python3 - "$mt" "$W/.ab" "${pref}".* <<'PY'
import sys,math
mt,outp=sys.argv[1],sys.argv[2]; a=d=b=0
for f in sys.argv[3:]:
    try:
        for l in open(f):
            if l.startswith("RESULT"): _,x,y,z=l.split(); a+=int(x);d+=int(y);b+=int(z)
    except Exception: pass
g=a+d+b; r=(a+0.5*d)/g if g else 0; se=(0.5/(g**0.5)) if g else 1
elo=-400*math.log10(1/r-1) if 0<r<1 else 0; lo,hi=r-1.96*se,r+1.96*se
vd="NPS-opt GAGNE hors-IC (NPS->Elo)" if lo>0.5 else ("PERD hors-IC (anormal!)" if hi<0.5 else "neutre")
open(outp,'w').write(f"  [NEW(opts) vs OLD(clean) | mt{mt} | même éval gen2] A={a} B={b} D={d} n={g} rate_NEW={r:.3f}+-{1.96*se:.3f} elo~{elo:+.0f} => {vd}\n")
PY
  cat "$W/.ab" | tee -a "$RES"; }
say ""; say "=== A/B NEW(opts NPS) vs OLD(clean), même éval gen2-mmto, au movetime ==="
abcell 0.2; commit_to_main "$RES" "$ARTREL/RESULTS.txt" "0662 A/B mt0.2" >/dev/null 2>&1 || true
abcell 0.3
say ""; say "  GATE : NEW>0.5 hors-IC => les +13-15% NPS byte-identiques se convertissent en Elo movetime (prémisse validée)."
say "  neutre => le NPS ne paie pas au movetime (surprenant) ; PERD => anomalie à investiguer (ne devrait pas, byte-identique)."
commit_to_main "$RES" "$ARTREL/RESULTS.txt" "0662 FIN validation NPS->Elo : les opts byte-identiques payent-elles au movetime" \
  && say "  RESULTS committé ✓" || say "  ⚠ commit échoue"
say "=== fin validation NPS ==="
