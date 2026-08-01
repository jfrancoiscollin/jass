#!/usr/bin/env bash
# L3 — les deux gardes d'une succession, pour un challengeur QUELCONQUE.
#
# La promotion d'EXACT (1er août) a été décidée sur le seul tête-à-tête. Celle de
# TURNOVER exigeait cinq garde-fous sur cinq, dont ceux-ci. Ce template les
# rejoue pour n'importe quel modèle, au lieu de rester enfoui dans
# `l3-pure-turnover-succession-gate-v1.sh` qui est câblé sur les identités de
# TURNOVER (préflight dédié, readout de dose, F2M en cellule primaire).
#
# Deux gardes, et rien d'autre — la cellule primaire est le travail de
# `l3-model-gate-v1.sh` :
#
#   1. NON-RÉGRESSION contre `gen2-mmto`, la référence historique figée. Gen2 est
#      un modèle **32cf** (`n_pat = 531441 × 32`) : il exige son PROPRE binaire,
#      d'où le second build. C'est la raison pour laquelle cette garde ne peut
#      pas tourner dans la porte générique, qui ne construit qu'une géométrie.
#   2. CONVERSION P3/P4 à **défenseur figé** — un binaire 32cf reconstruit depuis
#      un SHA moteur précis, pour que le plancher mesuré aujourd'hui soit
#      comparable à celui mesuré en juillet. Un défenseur qui bouge rendrait la
#      série temporelle inutilisable.
#
# ⚠️ Le pool d'ouvertures par défaut est celui de la succession TURNOVER, exprès :
# la garde n'a de sens que comparée à la garde de TURNOVER, et une comparaison
# sur un autre pool ne serait plus la même mesure.
#
# Aucune promotion, aucun chaînage automatique.
set -Eeuo pipefail

: "${JASS_CODE_DIR:?}"; : "${JASS_RESULT_DIR:?}"; : "${JASS_ARTEFACT_DIR:?}"
: "${JASS_JOB_ID:?}"; : "${JASS_OBJSTORE_REMOTE:?}"
: "${EXPECTED_CODE_SHA:?}"; : "${EXPECTED_JOB_ID:?}"
: "${CHALLENGER_PREFIX:?}"; : "${CHALLENGER_JOB:?}"
: "${CHALLENGER_FILE:?}"; : "${CHALLENGER_LABEL:?}"

cd "$JASS_CODE_DIR"
W="$JASS_RESULT_DIR/work"; IN="$JASS_RESULT_DIR/inputs"; ART="$JASS_ARTEFACT_DIR"
GEOM="$JASS_RESULT_DIR/geom"
mkdir -p "$W" "$IN" "$ART" "$GEOM" "$ART/force" "$ART/conversion"
RES="$W/RESULTS.txt"; PROG="$W/PROGRESS.txt"; STAGE="$W/.stage"
: > "$RES"; : > "$PROG"; echo start > "$STAGE"
say(){ echo "$*" | tee -a "$RES"; }
die(){ say "ABORT: $*"; exit 1; }
stage(){ echo "$1" > "$STAGE"; say "phase=$1"; }

PREFLIGHT_PREFIX="${PREFLIGHT_PREFIX:-r2:jass-data/runs/home-0995-l3-pure-turnover-succession-preflight-v2/20260727T054246Z-f20e59d0}"
EXPECTED_PREFLIGHT_JOB="${EXPECTED_PREFLIGHT_JOB:-home-0995-l3-pure-turnover-succession-preflight-v2}"
PREFLIGHT_FILE="${PREFLIGHT_FILE:-turnover-succession-openings.fen}"
EXPECTED_OPENING_SHA256="${EXPECTED_OPENING_SHA256:-eb129db1dd304ff3b47cae894f8f8d919d74fdf6b1c8a901e443b23920e4c203}"
NSH_GATE="${NSH_GATE:-12}"; PAR_GATE="${PAR_GATE:-12}"
NSH_CONV="${NSH_CONV:-4}"; CONV_DEPTH=10; TARGET_PER_STRATUM=300
FORCE_DEPTH=9; MOVETIME=0.1; CACHE_MB=128
CONV_FLOOR="${CONV_FLOOR:-0.95}"     # TURNOVER : P3 0,98 / P4 0,99
GEN2_GZ_SHA="01cc3ea59e9cc3ced1910d4d9054f88f92c1c4d9d220d5f28b0ebaaad33681a0"
P3_GAUGE_SHA="cd92710fec7934d113ccade22180d4cddf029b084dd20c8fa9e30ca686767c91"
P4_GAUGE_SHA="0d925c4fbd7e7928bf6d86bd2cd40f796ee6805e0010e51d5d6483986da2a1ac"
FIXED_DEFENDER_CODE_SHA="9c1d1e8eaaa5b9bbd86105f7f9807a3033784186"
GAUGE_PREFIX="${GAUGE_PREFIX:-r2:jass-data/runs/home-0954-l3-pure-m1-abextras-validation-v5/20260724T234944Z-8efd1c45}"
# Par défaut l'attaquant est construit depuis l'arbre du job — on veut tester le
# modèle tel qu'il sera utilisé. Mais cela rend un chiffre de conversion
# comparable UNIQUEMENT à un autre mesuré avec le même moteur attaquant : la
# règle du défenseur figé protégeait la moitié de la mesure et laissait l'autre
# dériver. `ATTACKER_CODE_SHA` permet de figer aussi l'attaquant, et donc de
# rejouer une mesure ancienne avec son moteur d'époque.
ATTACKER_CODE_SHA="${ATTACKER_CODE_SHA:-}"
# Une mesure d'archéologie ne veut que la conversion : la garde Gen2 d'un moteur
# ancien n'apprend rien, et c'est elle qui coûte. `cpx62-1139` a tenu 80 min sur
# la vue `native` — le moteur de juillet précède `16f8c151` (un `go movetime`
# rend après 5,5 s au lieu de 100 ms, une fois par processus) ET `9c1d1e8e` (coup
# nul sur toute racine nulle par répétition, lu comme un abandon, d'où des
# redémarrages qui repaient les 5,5 s). La conversion tourne à profondeur fixe,
# donc `has_deadline` n'est jamais armé et rien de tout cela ne s'applique.
SKIP_GEN2_GUARD="${SKIP_GEN2_GUARD:-0}"
Q00="rfp_max_depth=5,rfp_margin=100,nmp_min_depth=4,nmp_min_pieces=6,nmp_r_base=2,nmp_r_div=4,singular_min_depth=8,singular_margin=2,lmr_min_depth=3,lmr_first_full_moves=4,lmr_first_full_pv=4,lmr_first_full_nonpv=2,lmr_base=0,lmr_depth_div=6,lmr_idx_div=8,lmr_hist_div=0,lmr_formula=0,lmr_log_base=0,lmr_log_mul=40,lmr_bc_ld=100,lmr_bc_lidx=100,lmp_d1=4,lmp_d2=8,lmp_d3=14,lmp_max_depth=3,history_max=16384,hist_malus=0,hist_mode=1,prob_shift=5,hist_pure=1,hist_order_captures=0,aspiration_initial=50,use_pvs=1,razor_max_depth=4,razor_margin=200,probcut_min_depth=5,probcut_margin=150,probcut_reduction=4,ext_promotion=0,ext_forcing=0,forcing_ext_cap=0,ext_single_reply=0,use_improving=1,use_conthist=1,iid_min_depth=0,iid_reduction=2,no_reduce_forcing=0,qs_forcing_depth=0,qs_promo_depth=0,qs_threat_ext=0,qs_sacs=0,qs_sacs_depth0_only=1,multicut_min_depth=4,multicut_reduction=4,multicut_moves=8,multicut_cuts=2,tm_next_iter_pct=200,tm_min_depth=5,drawish_scaling=0,eg_pieces=40,eg_no_nmp=0,eg_no_lmp=0,eg_no_lmr=0"

MON=""
monitor(){
  ( t0=$(date +%s)
    while true; do
      { printf 'time_fr=%s\n' "$(TZ=Europe/Paris date '+%Y-%m-%dT%H:%M:%S%z')"
        printf 'phase=%s\n' "$(cat "$STAGE" 2>/dev/null || echo unknown)"
        printf 'elapsed_min=%d\n' "$(( ($(date +%s) - t0) / 60 ))"
        printf 'disk_free_mb=%s\n' "$(df -Pm "$JASS_RESULT_DIR" | awk 'NR==2{print $4}')"
        printf 'guard_views=%s\n' "$(find "$ART/force" -name '*.json' 2>/dev/null | wc -l || true)"
        printf 'conv_strata=%s\n' "$(find "$ART/conversion" -name '*.json' 2>/dev/null | wc -l || true)"
      } > "$PROG.tmp"
      mv "$PROG.tmp" "$PROG"; cp "$PROG" "$ART/PROGRESS.txt"
      sleep 120
    done ) &
  MON="$!"
}
restore_src(){ git checkout -- src/ pattern_jass/ 2>/dev/null || true; }
finalize(){
  rc=$?
  trap - EXIT ERR TERM INT
  set +e
  [ -z "$MON" ] || { kill "$MON" 2>/dev/null; wait "$MON" 2>/dev/null; }
  cp "$RES" "$ART/RESULTS.txt"
  [ -f "$PROG" ] && cp "$PROG" "$ART/PROGRESS.txt"
  (cd "$W" && find . -type f -name '*.log' -print0 |
    tar --null -czf "$ART/logs.tar.gz" -T -) 2>/dev/null || true
  rm -rf "$W/build8" "$W/build32" "$W/build32fixed" "$W/fixed-defender-code" \
         "$IN" "$W"/gate-* 2>/dev/null || true
  exit "$rc"
}
trap finalize EXIT
trap 'rc=$?; set +e; echo "ABORT line=$LINENO rc=$rc cmd=$BASH_COMMAND" | tee -a "$RES"; exit "$rc"' ERR
trap 'exit 143' TERM
trap 'exit 130' INT

wait_all(){
  local label="$1"; shift
  local fail=0 pid
  for pid in "$@"; do wait "$pid" || fail=$((fail+1)); done
  [ "$fail" -eq 0 ] || die "$label : $fail worker(s) en échec"
}

[ "$JASS_JOB_ID" = "$EXPECTED_JOB_ID" ] || die "job id mismatch"
[ "$(git rev-parse HEAD)" = "$EXPECTED_CODE_SHA" ] || die "code SHA mismatch"
[ -z "$(git branch --show-current)" ] || die "worktree must be detached"
[ "${FULL_RUN_APPROVED:-0}" = 1 ] && [ "${SCIENTIFIC_GO:-0}" = 1 ] ||
  die "scientific authorization missing"
[ "${NO_AUTOMATIC_CONTINUATION:-0}" = 1 ] || die "automatic continuation guard missing"

stage disk-guard
find /root -maxdepth 1 -name 'cw-*' -type d -mmin +180 ! -path "$W" -exec rm -rf {} + 2>/dev/null || true
DFA=$(df -Pm "$JASS_RESULT_DIR" | awk 'NR==2{print $4}')
[ "${DFA:-0}" -gt 8000 ] || die "moins de 8 Go libres (${DFA} Mo)"
NCPU=$(nproc); say "  nproc=$NCPU libre=${DFA}Mo challengeur=$CHALLENGER_LABEL"
monitor

stage fetch-inputs
python3 jobs/tools/fetch_result_files.py --prefix "$CHALLENGER_PREFIX" \
  --file "artefacts/$CHALLENGER_FILE=challenger.pjtw.gz" \
  --out-dir "$IN" --report "$ART/verified-challenger.json" \
  --expected-state completed > "$W/fetch-challenger.log" 2>&1 || die "fetch challengeur KO"
python3 - "$ART/verified-challenger.json" "$CHALLENGER_JOB" <<'PY'
import json, sys
r = json.load(open(sys.argv[1]))
if r.get("job_id") != sys.argv[2] or r.get("result_state") != "completed":
    raise SystemExit("challenger identity/state mismatch")
PY
python3 jobs/tools/fetch_result_files.py --prefix "$PREFLIGHT_PREFIX" \
  --file "artefacts/$PREFLIGHT_FILE=open-eval.fen" \
  --out-dir "$IN" --report "$ART/verified-openings.json" \
  --expected-state completed > "$W/fetch-openings.log" 2>&1 || die "fetch ouvertures KO"
# `fetch_t1bis_inputs.py` sert le bundle figé, dont Gen2 — mais PAS les jauges
# P3/P4. Vérifié dans son manifeste : il écrit parent/fixed/gen2.pjtw.gz,
# seeds.jnnw.gz, g1_pool.fen et gauge.fen, et rien d'autre. Les deux corpus de
# conversion viennent d'un préfixe distinct, exactement comme dans la porte de
# succession TURNOVER. Avoir supposé le contraire a tué cpx62-1136 au fetch.
python3 jobs/tools/fetch_t1bis_inputs.py --out-dir "$IN" \
  --report "$ART/verified-fixed-inputs.json" > "$W/fetch-fixed.log" 2>&1 ||
  die "fetch du bundle figé (gen2) KO"
python3 jobs/tools/fetch_result_files.py --prefix "$GAUGE_PREFIX" \
  --file artefacts/p3_mince-stable.jnnw.gz=p3.jnnw.gz \
  --file artefacts/p4_egal-stable.jnnw.gz=p4.jnnw.gz \
  --out-dir "$IN" --report "$ART/verified-gauge.json" \
  --expected-state completed > "$W/fetch-gauge.log" 2>&1 || die "fetch des jauges P3/P4 KO"

gunzip -c "$IN/challenger.pjtw.gz" > "$W/$CHALLENGER_LABEL.pjtw"
gunzip -c "$IN/gen2.pjtw.gz"       > "$W/GEN2.pjtw"
gunzip -c "$IN/p3.jnnw.gz"         > "$W/p3_mince.jnnw"
gunzip -c "$IN/p4.jnnw.gz"         > "$W/p4_egal.jnnw"
cp "$IN/open-eval.fen" "$W/open-eval.fen"

# Les trois entrées figées sont épinglées par hash : c'est ce qui rend le
# plancher de conversion comparable d'un mois à l'autre.
[ "$(sha256sum "$IN/gen2.pjtw.gz" | awk '{print $1}')" = "$GEN2_GZ_SHA" ] ||
  die "dérive du modèle Gen2"
for spec in "p3_mince:$P3_GAUGE_SHA" "p4_egal:$P4_GAUGE_SHA"; do
  name="${spec%%:*}"; want="${spec#*:}"
  [ "$(sha256sum "$W/$name.jnnw" | awk '{print $1}')" = "$want" ] ||
    die "dérive de la jauge $name"
done
[ "$(sha256sum "$W/open-eval.fen" | awk '{print $1}')" = "$EXPECTED_OPENING_SHA256" ] ||
  die "dérive du pool d'ouvertures"
NOPEN=$(awk '{sub(/#.*/,""); gsub(/^[ \t]+|[ \t]+$/,""); if (length) n++} END {print n+0}' "$W/open-eval.fen")
[ "$NOPEN" -gt 0 ] || die "aucune ouverture"

# Le challengeur doit être 8cf et Gen2 32cf — si ce n'est pas le cas, les deux
# binaires construits plus bas ne sont pas ceux qu'il faut, et personne ne s'en
# apercevrait avant de lire un Elo absurde.
python3 - "$W/$CHALLENGER_LABEL.pjtw" "$W/GEN2.pjtw" <<'PY' | tee -a "$RES"
import struct, sys
def head(p):
    with open(p, "rb") as f: return struct.unpack("<5I", f.read(20))
for path, want_pat, label in ((sys.argv[1], 531441 * 8, "challengeur 8cf"),
                              (sys.argv[2], 531441 * 32, "Gen2 32cf")):
    _, _, _, n_pat, n_ext = head(path)
    if n_pat != want_pat:
        raise SystemExit(f"{label} : n_pat={n_pat}, attendu {want_pat}")
    print(f"  {label} ✓ n_pat={n_pat:,} n_ext={n_ext}")
PY
say "  entrées ✓ $NOPEN ouvertures (pool épinglé)"

stage build-8cf-and-32cf
FLAGS="-DCMAKE_BUILD_TYPE=Release -DJASS_EGDB=ON -DJASS_EGDB_SRC_DIR=/root/egdb_intl -DJASS_ENDGAME_FEATURES=ON -DJASS_KING_MOBILITY=ON -DJASS_SCAN_PARITY=ON -DJASS_TEMPO_STAGE=ON"
EGDIR=""
for d in /root/egdb_db /root/egdb_extracted/app /root/egdb_extracted; do
  ls "$d"/db*.idx1 >/dev/null 2>&1 && { EGDIR="$d"; break; }
done
[ -n "$EGDIR" ] || die "EGDB absent — la garde ne serait pas comparable à celle de TURNOVER"
export JASS_EGDB_PATH="$EGDIR" JASS_EGDB_CACHE_MB="$CACHE_MB"
grep -q "g_emasks"        src/scan_eval.cpp || { restore_src; die "archi: scan_eval sans g_emasks"; }
grep -q "has_any_capture" src/search.cpp    || { restore_src; die "archi: search sans has_any_capture"; }
# Ces trois assertions portent sur l'ARBRE DU JOB, donc sur le binaire Gen2 et,
# par défaut, sur l'attaquant. Avec `ATTACKER_CODE_SHA` l'attaquant peut être
# LÉGITIMEMENT antérieur au correctif racine-nulle — c'est précisément l'objet
# d'une mesure d'archéologie, et le `say` ci-dessous le dit dans le rapport.
grep -q "root_is_drawn"   src/search.cpp    || { restore_src; die "moteur antérieur au correctif racine-nulle"; }

if [ -n "$ATTACKER_CODE_SHA" ]; then
  ATK_SRC="$W/attacker-code"; mkdir -p "$ATK_SRC"
  git archive "$ATTACKER_CODE_SHA" | tar -x -C "$ATK_SRC"
  ( cd "$ATK_SRC" && python3 pattern_jass/tools/gen_patterns.py --emit --variant 8cf ) \
    > "$W/gen8.log" 2>&1
  cp "$ATK_SRC/pattern_jass/tools/patterns.py" "$GEOM/patterns.py"
  cmake -S "$ATK_SRC" -B "$W/build8" $FLAGS > "$W/cmake8.log" 2>&1
  say "  ⚠️ attaquant FIGÉ au SHA $ATTACKER_CODE_SHA (mesure d'archéologie, pas le moteur courant)"
else
  ATK_SRC="."
  python3 pattern_jass/tools/gen_patterns.py --emit --variant 8cf > "$W/gen8.log" 2>&1
  cp pattern_jass/tools/patterns.py "$GEOM/patterns.py"
  cmake -S . -B "$W/build8" $FLAGS > "$W/cmake8.log" 2>&1
fi
cmake --build "$W/build8" -j"$NCPU" --target jass > "$W/build8.log" 2>&1
J8="$W/build8/jass"

python3 pattern_jass/tools/gen_patterns.py --emit --variant v4 > "$W/gen32.log" 2>&1
cmake -S . -B "$W/build32" $FLAGS > "$W/cmake32.log" 2>&1
cmake --build "$W/build32" -j"$NCPU" --target jass > "$W/build32.log" 2>&1
J32="$W/build32/jass"

# Défenseur FIGÉ : reconstruit depuis un SHA moteur précis, pour que le plancher
# de conversion reste comparable dans le temps. Un défenseur qui suit `develop`
# ferait dériver la référence sous les pieds de la série.
mkdir -p "$W/fixed-defender-code"
git archive "$FIXED_DEFENDER_CODE_SHA" | tar -x -C "$W/fixed-defender-code"
grep -q "root_is_drawn" "$W/fixed-defender-code/src/search.cpp" ||
  die "le défenseur figé est antérieur au correctif racine-nulle"
( cd "$W/fixed-defender-code" &&
  python3 pattern_jass/tools/gen_patterns.py --emit --variant v4 ) > "$W/gen32fixed.log" 2>&1
cmake -S "$W/fixed-defender-code" -B "$W/build32fixed" $FLAGS > "$W/cmake32fixed.log" 2>&1
cmake --build "$W/build32fixed" -j"$NCPU" --target jass > "$W/build32fixed.log" 2>&1
J32FIXED="$W/build32fixed/jass"
restore_src

for jass in "$J8" "$J32" "$J32FIXED"; do
  [ -x "$jass" ] || die "binaire manquant : $jass"
  [ "$("$jass" --perft 1 'W:W40,43,K2:B8,18,29,30' | awk '{print $3}')" = 9 ] ||
    die "témoin prise-par-dame en échec sur $jass"
done
printf 'hello\nquit\n' | timeout 60 "$J8" --pattern "$W/$CHALLENGER_LABEL.pjtw" > "$W/load8.log" 2>&1
grep -q '^ready' "$W/load8.log" || die "le binaire 8cf ne charge pas le challengeur"
printf 'hello\nquit\n' | timeout 60 "$J32" --pattern "$W/GEN2.pjtw" > "$W/load32.log" 2>&1
grep -q '^ready' "$W/load32.log" || die "le binaire 32cf ne charge pas Gen2"
say "  builds ✓ (8cf challengeur, 32cf Gen2, 32cf défenseur figé $FIXED_DEFENDER_CODE_SHA), EGDB $EGDIR"

stage guard-vs-gen2
run_guard(){
  local view="$1" args=()
  [ "$view" = q00 ] && args=(--depth "$FORCE_DEPTH") || args=(--movetime "$MOVETIME")
  timeout 21600 python3 jobs/tools/run_jass_gate_bounded.py \
    --jass-a "$J8" --jass-b "$J32" \
    --pattern-a "$W/$CHALLENGER_LABEL.pjtw" --pattern-b "$W/GEN2.pjtw" \
    --search-params-a "$Q00" --search-params-b "$Q00" \
    --openings-file "$W/open-eval.fen" "${args[@]}" --pairs 1 \
    --max-plies 160 --nshards "$NSH_GATE" --max-parallel "$PAR_GATE" \
    --timeout 10800 --game-timeout 180 \
    --work-dir "$W/gate-$view" \
    --out "$ART/force/$view-CHALLENGER-vs-GEN2.json" \
    > "$W/force-$view.log" 2>&1
}
if [ "$SKIP_GEN2_GUARD" = 1 ]; then
  say "  ⚠️ garde Gen2 SAUTÉE sur demande — ce job ne rend QUE la conversion"
else
  pids=()
  for view in q00 native; do run_guard "$view" & pids+=("$!"); done
  wait_all "garde Gen2" "${pids[@]}"
fi

stage conversion-vs-frozen-defender
run_conv(){
  local stratum="$1" pool="$2"
  local pids=() inputs=() shard out
  for shard in $(seq 0 $((NSH_CONV-1))); do
    out="$W/conv-$stratum-$shard.json"; inputs+=("$out")
    timeout 14400 python3 jobs/tools/conv_fixed_wdl.py \
      --jass "$J8" --defender-jass "$J32FIXED" \
      --pattern "$W/$CHALLENGER_LABEL.pjtw" --defender-pattern "$W/GEN2.pjtw" \
      --search-params "$Q00" --defender-search-params "$Q00" \
      --pool-jnnw "$pool" --depth "$CONV_DEPTH" --max-plies 260 \
      --shard "$shard" --nshards "$NSH_CONV" --out "$out" \
      > "$W/conv-$stratum-$shard.log" 2>&1 &
    pids+=("$!")
  done
  wait_all "conversion $stratum" "${pids[@]}"
  python3 jobs/tools/aggregate_conv_shards.py --inputs "${inputs[@]}" \
    --expected-shards "$NSH_CONV" --expected-records "$TARGET_PER_STRATUM" \
    --max-error-rate 0.08 --stratum "$stratum" --require-position-results \
    --out "$ART/conversion/$stratum.json" > "$W/agg-$stratum.log" 2>&1 ||
    die "agrégation $stratum en échec"
}
for stratum in p3_mince p4_egal; do
  stage "conversion-$stratum"
  run_conv "$stratum" "$W/$stratum.jnnw"
done

stage readout
python3 - "$ART/force" "$ART/conversion" "$CHALLENGER_LABEL" "$CONV_FLOOR" \
         "$ART/guards.json" "$ART/JASS_CONTROL_SUMMARY.json" "$SKIP_GEN2_GUARD" <<'PY' | tee -a "$RES"
import json, math, os, sys
force_dir, conv_dir, label, floor, out_g, out_s, skip = sys.argv[1:8]
floor = float(floor)
skip_gen2 = skip == "1"

gen2_ok = None
gen2_block = {"skipped": True}
if skip_gen2:
    # Aucune garde jouée : on ne fabrique PAS un taux à partir de zéro compteur.
    # Une cellule absente est INCONNUE, jamais 0,5 (règle n=0 du registre).
    print("  garde Gen2 : SAUTÉE (archéologie, conversion seule)")
else:
    # Vues SOMMÉES sur les compteurs BRUTS. Moyenner deux taux de n différents
    # pondérerait mal et rendrait un intervalle faux.
    w = l = d = 0
    views = {}
    for view in ("q00", "native"):
        p = os.path.join(force_dir, f"{view}-CHALLENGER-vs-GEN2.json")
        if not os.path.exists(p):
            raise SystemExit(f"vue {view} absente — garde INCONCLUANTE, pas 'neutre'")
        r = json.load(open(p))
        # Noms RÉELS de `run_jass_gate_bounded.py`, vérifiés sur un artefact réel.
        a, b, dr = r.get("wins_a"), r.get("wins_b"), r.get("draws", 0)
        if a is None or b is None:
            raise SystemExit(f"vue {view} : compteurs illisibles")
        n = a + b + dr
        if n < 1000:
            raise SystemExit(f"vue {view} : n={n} sous le plancher — ABORT, pas 'neutre'")
        if r.get("n") not in (None, n):
            raise SystemExit(f"vue {view} : n={r['n']} incohérent avec {a}+{b}+{dr}")
        views[view] = {"n": n, "wins": a, "losses": b, "draws": dr,
                       "rate": round((a + 0.5 * dr) / n, 6)}
        w += a; l += b; d += dr
    n = w + l + d
    rate = (w + 0.5 * d) / n
    se = math.sqrt(max(rate * (1 - rate) / n, 1e-12))
    lo, hi = rate - 1.96 * se, rate + 1.96 * se
    def elo(x): return 400 * math.log10(x / (1 - x)) if 0 < x < 1 else float("nan")
    print(f"  garde Gen2 : n={n}  {label} {w}W {d}D {l}L")
    print(f"    taux={rate:.4f}  IC95=[{lo:.4f} ; {hi:.4f}]  Elo={elo(rate):+.2f}")
    for v, x in views.items():
        print(f"    {v:6s} n={x['n']:5d} taux={x['rate']:.4f}")
    gen2_ok = lo > 0.5
    print(f"    → {'AUCUNE RÉGRESSION' if gen2_ok else 'RÉGRESSION POSSIBLE — borne basse sous 0,5'}")
    gen2_block = {"n": n, "wins": w, "draws": d, "losses": l,
                  "rate": round(rate, 6), "ci95": [round(lo, 6), round(hi, 6)],
                  "elo": round(elo(rate), 2), "per_view": views,
                  "no_regression": gen2_ok}

conv, conv_ok = {}, True
for stratum in ("p3_mince", "p4_egal"):
    path = os.path.join(conv_dir, f"{stratum}.json")
    if not os.path.exists(path):
        raise SystemExit(f"conversion {stratum} absente — INCONCLUANTE")
    r = json.load(open(path))
    # Noms RÉELS de `aggregate_conv_shards.py` (schema 2) : `conversion`, `n_pos`.
    v = r.get("conversion")
    nn = r.get("n_pos", 0)
    if v is None or not nn:
        raise SystemExit(f"conversion {stratum} : illisible ou vide")
    if not r.get("complete"):
        raise SystemExit(f"conversion {stratum} : agrégat incomplet")
    if nn < 0.9 * 300:
        raise SystemExit(f"conversion {stratum} : n_pos={nn} sous le plancher")
    conv[stratum] = {"rate": round(float(v), 6), "n": int(nn),
                     "n_win": r.get("n_win"), "n_draw": r.get("n_draw"),
                     "n_loss": r.get("n_loss")}
    ok = float(v) >= floor
    conv_ok = conv_ok and ok
    print(f"  conversion {stratum:9s} = {float(v):.4f}  n={nn}  "
          f"(W{r.get('n_win')} D{r.get('n_draw')} L{r.get('n_loss')})  "
          f"plancher {floor:.2f}  {'OK' if ok else 'SOUS LE PLANCHER'}")

if skip_gen2:
    verdict = "CONVERSION_ARCHAEOLOGY_" + ("ABOVE_FLOOR" if conv_ok else "BELOW_FLOOR")
else:
    verdict = ("SUCCESSION_GUARDS_GREEN" if (gen2_ok and conv_ok)
               else "SUCCESSION_GUARDS_RED")
print(f"  {verdict}")
# Repères TURNOVER (home-0996) : Gen2 58,83 % (+62,03 Elo), P3 0,98, P4 0,99.
json.dump({"schema": 1, "challenger": label, "verdict": verdict,
           "gen2_guard": gen2_block, "conversion": conv, "conversion_floor": floor,
           "gen2_guard_skipped": skip_gen2,
           "turnover_reference_home_0996": {"gen2_rate": 0.5883, "gen2_elo": 62.03,
                                            "p3": 0.98, "p4": 0.99}},
          open(out_g, "w"), indent=2, sort_keys=True)
json.dump({"schema": 1, "verdict": verdict, "diagnostic_only": True,
           "promotion_authorized": False, "automatic_next_job": None,
           "gen2_no_regression": gen2_ok, "conversion_above_floor": conv_ok},
          open(out_s, "w"), indent=2, sort_keys=True)
open(out_s, "a").write("\n")
PY

stage report
VERDICT="$(python3 -c 'import json,sys;print(json.load(open(sys.argv[1]))["verdict"])' "$ART/guards.json")"
: > "$ART/VERDICT__$VERDICT"
printf 'PROMOTION_AUTHORIZED__FALSE\n' > "$ART/PROMOTION_AUTHORIZED__FALSE"
printf 'AUTOMATIC_NEXT_JOB__NULL\n'    > "$ART/AUTOMATIC_NEXT_JOB__NULL"
say "$VERDICT promotion=false automatic_next_job=null"
