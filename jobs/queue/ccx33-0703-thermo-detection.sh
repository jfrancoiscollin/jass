#!/usr/bin/env bash
# id: ccx33-0703-thermo-detection
# description: LEVIER D (memo trou tactique) — PROFIL DE DETECTION sur le thermometre PC Blues (224 pos figees).
# Separe "jass NE TROUVE PAS le 1er coup" de "trouve mais NE CONVERTIT PAS" (0688 = conversion 0.136 vs Scan 0.904).
# Pour chaque position : bestmove jass (--search-profile, TT froid) + Scan (HUB) a budgets croissants d7/d9/d11/d13,
# compare au 1er coup CERTIFIE (sol <m1>… du commentaire). +detection-sequence K=2,3 (rejeu prefixe via referee jass).
# PUR INSTRUMENT — zero changement moteur, les positions ne servent JAMAIS a l'entrainement.
# LECTURES PRE-ENGAGEES : detection qui SAUTE avec le budget => enterrement-par-reduction confirme => GO O (offer-no-reduce).
#                         detection BASSE et PLATE meme a gros budget => pathologie ordering/pruning => rediagnostic.
#                         detection HAUTE mais conversion 0.136 basse => trou en AVAL (technique finale) => A4/TB.
# PRE-ESTIMATION (ancre 0688 : 224 pos MATCHS d11 ~2-3h ; ici = recherches MONO-position, bcp + court) : ~30-60 min ccx33.
set -uo pipefail
cd /root/jass
exec 9>/root/.jass-0703.lock
if ! flock -n 9; then echo "ABORT 0703 : instance deja active"; exit 0; fi
NCPU=$(nproc); export TMPDIR=/root/jass/.compile-tmp; mkdir -p "$TMPDIR"
ART="/root/jass/jobs/results/ccx33-0703-thermo-detection/artefacts"; mkdir -p "$ART"
ARTREL="jobs/results/ccx33-0703-thermo-detection/artefacts"
W=/root/cw-0703
# hygiene disque (ccx33 = 152Go) : auto-clean cw-* stale + garde df
find /root -maxdepth 1 -name 'cw-*' -type d -mmin +180 ! -path "$W" -exec rm -rf {} + 2>/dev/null || true
rm -rf "$W"; mkdir -p "$W"
RES="$W/RESULTS.txt"; : > "$RES"; say(){ echo "$@" | tee -a "$RES"; }   # RES hors arbre git (rule 8ter)
SCAN_BIN=/root/jass-scan/scan_linux
CHAMP_GZ=jobs/results/BAKE-gen2-mmto/artefacts/champion-gen2-mmto.pjtw.gz
SRC_BRANCH=claude/pcblues-corpus-extraction-2i92bj
DEPTHS="7,9,11,13"; SCAN_DEPTHS="7,9,11"; REFD=11; KMAX=3; SHTIMEOUT=3600
NSH="$NCPU"

commit_to_main(){ local ab="$1" rel="$2" msg="$3"
  for a in 1 2 3 4 5; do git fetch origin main --quiet 2>/dev/null||true
    local idx="/root/.ti.$$.$RANDOM"; rm -f "$idx"; GIT_INDEX_FILE="$idx" git read-tree origin/main 2>/dev/null||return 1
    local b; b=$(git hash-object -w "$ab")||return 1
    GIT_INDEX_FILE="$idx" git update-index --add --cacheinfo 100644 "$b" "$rel"
    local t; t=$(GIT_INDEX_FILE="$idx" git write-tree); local c; c=$(printf '%s\n' "$msg"|git commit-tree "$t" -p origin/main)
    git push origin "$c:main" 2>/dev/null && { rm -f "$idx"; return 0; }; sleep $((a*4)); done; return 1; }

DFAVAIL=$(df -Pm /root 2>/dev/null|awk 'NR==2{print $4}'); say "=== 0703 PROFIL DETECTION thermometre PC Blues (levier D) — nproc=$NCPU NSH=$NSH df=${DFAVAIL}Mo ==="
[ "${DFAVAIL:-0}" -gt 3000 ] 2>/dev/null || { say "ABORT disque <3Go"; exit 3; }
[ -x "$SCAN_BIN" ] || { say "ABORT: Scan introuvable $SCAN_BIN"; commit_to_main "$RES" "$ARTREL/RESULTS.txt" "0703 ABORT scan absent"; exit 4; }

# --- src perf-critique + outils : pull develop (ref connue) + arch_assert AVANT cmake ---
# src+calibrate_vs_scan = canonique develop ; thermo_detection.py + data = branche corpus (SRC_BRANCH)
git fetch origin +refs/heads/develop:refs/remotes/origin/develop --quiet 2>/dev/null || true
git fetch origin +refs/heads/$SRC_BRANCH:refs/remotes/origin/$SRC_BRANCH --quiet 2>/dev/null || true
for f in src/main.cpp src/scan_eval.cpp src/scan_eval.hpp src/search.cpp src/search.hpp src/movegen.cpp src/movegen.hpp \
         src/hub.cpp src/hub.hpp tools/calibrate_vs_scan.py; do
  git show "origin/develop:$f" > "$f" 2>/dev/null || true
done
git show "origin/$SRC_BRANCH:tools/thermo_detection.py" > tools/thermo_detection.py 2>/dev/null || true
restore_src(){ git checkout -- src/main.cpp src/scan_eval.cpp src/scan_eval.hpp src/search.cpp src/search.hpp src/movegen.cpp src/movegen.hpp src/hub.cpp src/hub.hpp tools/calibrate_vs_scan.py tools/thermo_detection.py 2>/dev/null||true; }
[ -s tools/thermo_detection.py ] || { say "ABORT: tools/thermo_detection.py absent d'origin/$SRC_BRANCH (commiter d'abord)"; restore_src; exit 5; }
arch_assert(){
  grep -q "g_emasks"        src/scan_eval.cpp || { say "ABORT archi: scan_eval SANS opts NPS (g_emasks)"; restore_src; exit 5; }
  grep -q "has_any_capture" src/search.cpp    || { say "ABORT archi: search SANS has_any_capture"; restore_src; exit 5; }
  grep -q "has_any_capture" src/movegen.cpp   || { say "ABORT archi: movegen SANS has_any_capture"; restore_src; exit 5; }
  say "  garde-fou archi ✓ : scan_eval=g_emasks + has_any_capture (search+movegen)"; }
arch_assert
python3 -m py_compile tools/thermo_detection.py tools/calibrate_vs_scan.py || { say "ABORT: py_compile outils"; restore_src; exit 5; }

say "=== build jass (main-champion 32-pat extras, SANS egdb) ==="
cmake -S . -B "$W/build" -DCMAKE_BUILD_TYPE=Release \
    -DJASS_ENDGAME_FEATURES=ON -DJASS_KING_MOBILITY=ON -DJASS_SCAN_PARITY=ON -DJASS_TEMPO_STAGE=ON >"$W/cmake.log" 2>&1 || { say "ABORT cmake"; tail -8 "$W/cmake.log"|sed 's/^/  /'|tee -a "$RES"; restore_src; exit 6; }
cmake --build "$W/build" -j"$NCPU" --target jass >"$W/build.log" 2>&1 || { say "BUILD FAIL"; tail -12 "$W/build.log"|sed 's/^/  /'|tee -a "$RES"; restore_src; exit 6; }
JASS="$W/build/jass"
git show "origin/main:$CHAMP_GZ" | gunzip > "$W/champ.pjtw" || { say "ABORT: champion gen2-mmto absent"; restore_src; exit 4; }
git fetch origin +refs/heads/$SRC_BRANCH:refs/remotes/origin/$SRC_BRANCH --quiet 2>/dev/null || true
git show "origin/$SRC_BRANCH:data/pcblues_thermometre.fen" > "$W/thermo.fen" || { say "ABORT: thermometre absent de $SRC_BRANCH"; restore_src; exit 4; }
unset JASS_EGDB_PATH
NPOS=$(grep -cvE '^\s*(#|$)' "$W/thermo.fen"); say "  ✓ build ; champion=gen2-mmto ; thermometre=${NPOS} positions ; Scan=$SCAN_BIN (bb-size 0, FAIR)"

# --- profil sharde (chaque shard : sous-ensemble de positions, referee+scan propres) ---
say ""; say "=== detection jass(d$DEPTHS) + Scan(d$SCAN_DEPTHS) + sequence K=$KMAX @d$REFD sur $NPOS pos, $NSH shards ==="
PIDS=()
for s in $(seq 0 $((NSH-1))); do
  timeout "$SHTIMEOUT" python3 tools/thermo_detection.py \
    --jass "$JASS" --pattern "$W/champ.pjtw" --scan "$SCAN_BIN" --thermo-fen "$W/thermo.fen" \
    --depths "$DEPTHS" --scan-depths "$SCAN_DEPTHS" --ref-depth "$REFD" --kmax "$KMAX" \
    --shard "$s" --nshards "$NSH" --out "$W/detect.$s.jsonl" >"$W/sh.$s.log" 2>&1 &
  PIDS+=($!)
done
wait "${PIDS[@]}"
cat "$W"/detect.*.jsonl > "$ART/thermo_detection_records.jsonl" 2>/dev/null
NREC=$(grep -c . "$ART/thermo_detection_records.jsonl" 2>/dev/null || echo 0)
say "  positions profilees : $NREC / $NPOS"

# --- aggregation : rates detection(budget) jass vs Scan + sequence + lecture pre-engagee ---
python3 - "$ART/thermo_detection_records.jsonl" "$ART/thermo_detection_profile.json" "$DEPTHS" "$SCAN_DEPTHS" "$REFD" "$KMAX" <<'PY' 2>&1 | tee -a "$RES"
import json,sys
recs=[json.loads(l) for l in open(sys.argv[1]) if l.strip()]
outp=sys.argv[2]; depths=[int(x) for x in sys.argv[3].split(',')]; sdepths=[int(x) for x in sys.argv[4].split(',')]
refd=int(sys.argv[5]); kmax=int(sys.argv[6])
elig=[r for r in recs if r.get("n_certified",0)>=1 and "skip" not in r]
N=len(elig)
def rate(key,d):
    v=[r.get(key,{}).get(str(d)) for r in elig]; v=[x for x in v if x is not None]
    return (sum(1 for x in v if x)/len(v), len(v)) if v else (float('nan'),0)
prof={"n_positions":N,"depths":depths,"scan_depths":sdepths,"ref_depth":refd,
      "jass_detection":{}, "scan_detection":{}, "jass_sequence":{}, "scan_sequence":{},
      "conversion_0688":{"jass":0.136,"scan":0.904,"depth":11,"note":"reference 0688 (camp au trait)"}}
print(f"  positions eligibles (>=1 coup certifie) : {N}")
print(f"  --- DETECTION 1er coup (bestmove == m1 certifie) ---")
print(f"  {'budget':>8} | {'jass':>14} | {'Scan':>14}")
for d in sorted(set(depths+sdepths)):
    jr,jn=rate("jass_detect",d); sr,sn=rate("scan_detect",d)
    if d in depths: prof["jass_detection"][str(d)]={"rate":None if jn==0 else round(jr,4),"n":jn}
    if d in sdepths: prof["scan_detection"][str(d)]={"rate":None if sn==0 else round(sr,4),"n":sn}
    js=f"{jr:.3f} ({jn})" if d in depths and jn else ("n/a" if d in depths else "-")
    ss=f"{sr:.3f} ({sn})" if d in sdepths and sn else ("n/a" if d in sdepths else "-")
    print(f"  d{d:>6} | {js:>14} | {ss:>14}")
print(f"  --- DETECTION-SEQUENCE (K premiers coups suivis, @d{refd}) ---")
for k in range(1,kmax+1):
    jr,jn=rate("jass_seq",k); sr,sn=rate("scan_seq",k)
    prof["jass_sequence"][str(k)]={"rate":None if jn==0 else round(jr,4),"n":jn}
    prof["scan_sequence"][str(k)]={"rate":None if sn==0 else round(sr,4),"n":sn}
    js=f"{jr:.3f} ({jn})" if jn else "n/a"; ss=f"{sr:.3f} ({sn})" if sn else "n/a"
    print(f"  K={k:>2}     | jass {js:>14} | Scan {ss:>14}")
# --- lecture pre-engagee (chiffres d'abord ; decision finale JFC) ---
dl=[d for d in depths]; dlo,dhi=dl[0],dl[-1]
jlo=prof["jass_detection"].get(str(dlo),{}).get("rate"); jhi=prof["jass_detection"].get(str(dhi),{}).get("rate")
jmid=prof["jass_detection"].get(str(refd),{}).get("rate")
print("  --- LECTURE PRE-ENGAGEE ---")
if jlo is None or jhi is None:
    verdict="INCOMPLET : rates manquants (n=0) — verifier le harnais (jamais 'neutre')."
else:
    jump=jhi-jlo
    if jhi>=0.70:
        verdict=(f"DETECTION HAUTE (d{dhi}={jhi:.3f}) mais conversion 0688=0.136 => le trou est en AVAL "
                 f"(technique de finale post-combinaison) => territoire A4/TB-direct, PAS le search. O inutile.")
    elif jump>=0.15 and jhi>(jmid or 0):
        verdict=(f"DETECTION SAUTE avec le budget (d{dlo}={jlo:.3f} -> d{dhi}={jhi:.3f}, +{jump:.3f}) => "
                 f"ENTERREMENT-PAR-REDUCTION confirme (profondeur effective ecrasee) => GO O (offer-no-reduce).")
    elif jhi<0.35 and jump<0.10:
        verdict=(f"DETECTION BASSE ET PLATE (d{dlo}={jlo:.3f} ~ d{dhi}={jhi:.3f}) => pathologie ordering/pruning "
                 f"plus profonde (lignes jamais explorees, meme sans reduction) => O inutile, REDIAGNOSTIC.")
    else:
        verdict=(f"AMBIGU (d{dlo}={jlo:.3f} -> d{dhi}={jhi:.3f}, +{jump:.3f}) => trancher a JFC "
                 f"(saut partiel : tester O en gardant l'oeil sur le node-EBF).")
prof["reading"]=verdict
print("  => "+verdict)
json.dump(prof,open(outp,'w'),ensure_ascii=False,indent=2)
print(f"  profil -> {outp}")
PY

restore_src
commit_to_main "$ART/thermo_detection_records.jsonl" "$ARTREL/thermo_detection_records.jsonl" "0703 detection records ($NREC pos)" >/dev/null 2>&1 || true
commit_to_main "$ART/thermo_detection_profile.json" "$ARTREL/thermo_detection_profile.json" "0703 profil detection thermometre" >/dev/null 2>&1 || true
commit_to_main "$RES" "$ARTREL/RESULTS.txt" "0703 FIN profil detection : $(grep -A1 'LECTURE' "$RES"|tail -1|tr -s ' '|cut -c1-80)" \
  && say "  RESULTS committe ✓" || say "  ⚠ commit RESULTS"
say "=== fin 0703 ==="
rm -rf "$W"
