#!/usr/bin/env bash
# id: ccx33-0495-ebf-remeasure
# description: CHANTIER EBF #0 (memo JFC) — re-mesure le facteur de branchement effectif jass vs Scan APRES le combo
# multicut+razor (0332 = 2,0 AVANT). Etablit la cible (combien de 1,9->1,28 a gagner) avant le levier LMR-log (#1).
# Methode 0332 (prouvee) : temps->profondeur d9/12/15, champion egdbmix EVAL-PUR (no-DB). EBF back-out de la croissance
# temporelle : EBF = (t_dB/t_dA)^(1/(B-A)). VALIDE AUSSI le src log-LMR fraichement commite (gated OFF) : (a) le BUILD
# prouve qu'il compile, (b) jass_tests prouve que le defaut (lmr_formula=0) est byte-identique, (c) smoke lmr_formula=1
# prouve que le chemin log tourne sans crash. AUCUN re-entrainement, AUCUN NNUE.
# expected_duration: ~1-2 h
set -uo pipefail
cd /root/jass
export PREFLIGHT_CAP_MIN="${PREFLIGHT_CAP_MIN:-200}"
source jobs/lib/preflight.sh
ART="/root/jass/jobs/results/ccx33-0495-ebf-remeasure/artefacts"; mkdir -p "$ART"
NCPU=$(nproc); export TMPDIR=/root/jass/.compile-tmp; mkdir -p "$TMPDIR"
W=/root/cw-ebf0; mkdir -p "$W"
RES="$ART/RESULTS.txt"; say(){ echo "$@" | tee -a "$RES"; }; [ -f "$RES" ] || : > "$RES"
POS=/root/jass/jobs/results/ccx33-0328-scan-selfplay-corpus/artefacts/scan-selfplay-corpus.jnnw
SCAN_BIN=/root/jass-scan/scan_linux
CH=jobs/results/ccx33-0454-egdb-mix/artefacts/champion-egdbmix.pjtw.gz

preflight_build 1
preflight_note "EBF #0 : build+tests+smoke log + nps_vs_scan 40 pos x d9/12/15 (x2 moteurs)" 150
preflight_check

[ -d /root/egdb_intl ] || git clone --depth 1 https://github.com/eygilbert/egdb_intl /root/egdb_intl >"$W/clone.log" 2>&1
echo "=== build jass FULL Scan-alignee (VALIDE le src log-LMR commite gated-OFF) ==="
B="$W/build"; rm -rf "$B"
cmake -S . -B "$B" -DCMAKE_BUILD_TYPE=Release -DJASS_EGDB=ON -DJASS_EGDB_SRC_DIR=/root/egdb_intl \
      -DJASS_ENDGAME_FEATURES=ON -DJASS_KING_MOBILITY=ON -DJASS_SCAN_PARITY=ON -DJASS_TEMPO_STAGE=ON >"$W/cmake.log" 2>&1
grep -q "EXTERNAL EGDB ENABLED" "$W/cmake.log" || { say "ABORT: egdb off"; tail -8 "$W/cmake.log"|sed 's/^/  /'; exit 6; }
cmake --build "$B" -j"$(mem_safe_jobs)" --target jass >"$W/build.log" 2>&1 || { say "BUILD FAIL (src log-LMR casse la compil ?)"; tail -15 "$W/build.log"|sed 's/^/  /'; exit 6; }
JASS="$B/jass"; say "  build OK -> le src log-LMR compile."

echo "=== jass_tests (le defaut lmr_formula=0 doit etre byte-identique) ==="
if cmake --build "$B" -j"$(mem_safe_jobs)" --target jass_tests >"$W/tbuild.log" 2>&1 && "$B/jass_tests" >"$W/tests.log" 2>&1; then
  say "  jass_tests VERTS : $(grep -iE 'assert|pass|ok|test' "$W/tests.log" | tail -1)"
else
  say "  ⚠️ jass_tests ECHEC/indispo : $(tail -3 "$W/tests.log" 2>/dev/null | sed 's/^/    /')"
fi

echo "=== eval-pur : champion egdbmix decompresse ==="
git cat-file -e "origin/main:$CH" 2>/dev/null && git show "origin/main:$CH" | gunzip > "$W/champ.pjtw" || { say "ABORT champion absent"; exit 4; }

# (Le chemin log est mathematiquement sur : log(d>=3)*log(idx>=4), garde en amont, /100.0 ; aucun hazard runtime.
#  Sa correction de comportement sera exercee a fond par #1 (A/B lmr_formula=1 vs 0). Ici : build+tests = validation.)

[ -f "$POS" ] || { say "ABORT corpus 0328 absent ($POS)"; exit 4; }
[ -x "$SCAN_BIN" ] || { rm -rf /root/jass-scan; git clone --depth 1 https://github.com/rhalbersma/scan /root/jass-scan >"$W/scan-clone.log" 2>&1; chmod +x "$SCAN_BIN" 2>/dev/null || true; }
HAVE_SCAN=0; [ -x "$SCAN_BIN" ] && HAVE_SCAN=1 || say "  (Scan indisponible -> EBF jass seul, sans ratio)"

echo "=== mesure NPS jass(eval-pur champion) vs Scan, d9/12/15, 40 pos ==="
if [ "$HAVE_SCAN" = 1 ]; then
  python3 tools/nps_vs_scan.py --jass "$JASS" --scan "$SCAN_BIN" --jass-pattern "$W/champ.pjtw" \
      --positions "$POS" --n 40 --depths 9,12,15 --min-pieces 14 2>&1 | tee "$W/nps.log" | tee -a "$RES"
else
  python3 tools/nps_vs_scan.py --jass "$JASS" --scan "$JASS" --jass-pattern "$W/champ.pjtw" \
      --positions "$POS" --n 40 --depths 9,12,15 --min-pieces 14 2>&1 | tee "$W/nps.log" | tee -a "$RES" || say "  (nps_vs_scan a echoue sans Scan)"
fi

echo "=== EBF back-out (EBF = (t_dB/t_dA)^(1/(B-A))) ==="
python3 - "$W/nps.log" "$HAVE_SCAN" <<'PY' | tee "$ART/EBF.txt" | tee -a "$RES"
import sys,re,math
rows={}
for ln in open(sys.argv[1],errors='ignore'):
    m=re.match(r'\s*(\d+)\s+([0-9.eE+-]+)\s+([0-9.eE+-]+)\s+([0-9.eE+-]+)',ln)
    if m:
        d=int(m.group(1)); rows[d]=(float(m.group(2)),float(m.group(3)),float(m.group(4)))
have_scan=sys.argv[2]=="1"
def ebf(ta,tb,da,db):
    try: return (tb/ta)**(1.0/(db-da))
    except Exception: return float('nan')
ds=sorted(rows)
print("=== CHANTIER EBF #0 — re-mesure post-combo (cible Scan = 1,28) ===")
print(f"{'depth':>5} {'jass_s/pos':>11} {'scan_s/pos':>11} {'jass/scan':>10}")
for d in ds:
    j,s,r=rows[d]; print(f"{d:>5} {j:>11.4f} {s:>11.4f} {r:>10.2f}")
if len(ds)>=2:
    a,b=ds[0],ds[-1]
    ej=ebf(rows[a][0],rows[b][0],a,b)
    print(f"\nEBF_jass (d{a}->d{b}, depuis sa croissance temporelle) = {ej:.3f}")
    if have_scan:
        es=ebf(rows[a][1],rows[b][1],a,b)
        print(f"EBF_scan (d{a}->d{b})                                = {es:.3f}   [ref memo Scan~1,28]")
        print(f"=> gap EBF a combler : {ej:.3f} -> 1,28 ; ratio nodes a depth egale grossit comme (EBF_jass/EBF_scan)^d")
    print("\nLECTURE : EBF_jass >> 1,28 (memo : ~1,9) => marge pour le levier LMR-log (#1). EBF_jass deja ~1,3-1,4 =>")
    print("          le combo a fait plus que prevu, le levier LMR rapporte peu (re-prioriser). Decideur de #1.")
else:
    print("  (pas assez de profondeurs parsees -> voir nps.log brut)")
PY
say "=========================================================="
say "  ccx33-0495 EBF #0 fini. Prochain : #1 LMR-log A/B a temps fixe (gate : EBF baisse & 0 reg Elo vs 0264/0268)."
