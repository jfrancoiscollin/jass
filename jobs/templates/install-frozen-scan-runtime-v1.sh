#!/usr/bin/env bash
# Restaure le runtime Scan 3.1 GELÉ depuis l'archive R2, sur la box nommée.
#
# Généralisation de `home-0925-install-frozen-scan-runtime-v1`, qui était cloué
# sur HOME par un `[ "$HOST" = "User" ]` en dur. HOME est out (JFC 2026-07-31) et
# `cpx62-1111` s'est arrêté sur `binaire Scan absent` : l'installation n'avait
# jamais été faite ailleurs que sur HOME. La box cible devient un paramètre.
#
# Ce que ce job NE fait PAS : jouer une partie, entraîner, comparer, promouvoir.
# Il télécharge une archive déjà vérifiée, recompte TOUS les hashes, et installe
# atomiquement.
#
# ⚠️ Il n'écrase JAMAIS un `/root/jass-scan` existant dont l'empreinte diffère.
# Un runtime de référence différent est une INFORMATION (quelqu'un a installé
# autre chose, ou une install s'est interrompue), pas un obstacle à piétiner : on
# le décrit dans les artefacts et on sort en `CONFLICT` pour qu'un humain
# tranche. C'est exactement le cas que `cpx62-1111` ne pouvait pas distinguer —
# il voyait « pas exécutable » sans pouvoir dire « absent » ou « autre chose ».
set -Eeuo pipefail

: "${JASS_CODE_DIR:?}"; : "${JASS_RESULT_DIR:?}"; : "${JASS_ARTEFACT_DIR:?}"
: "${JASS_JOB_ID:?}"; : "${JASS_ATTEMPT_ID:?}"
: "${EXPECTED_CODE_SHA:?}"; : "${EXPECTED_JOB_ID:?}"; : "${EXPECTED_HOST:?}"

cd "$JASS_CODE_DIR"
W="$JASS_RESULT_DIR/work"
ART="$JASS_ARTEFACT_DIR"
mkdir -p "$W" "$ART"
# RES hors de l'arbre git (règle 8ter) : le runner resynchronise l'arbre à
# chaque tick et clobberait un fichier écrit dans le repo.
RES="$W/RESULTS.txt"
: > "$RES"
say(){ echo "$*" | tee -a "$RES"; }
die(){ say "ABORT: $*"; exit 1; }

finalize(){
  rc=$?
  trap - EXIT ERR TERM INT
  set +e
  cp "$RES" "$ART/RESULTS.txt"
  exit "$rc"
}
trap finalize EXIT
trap 'rc=$?; set +e; echo "ABORT line=$LINENO rc=$rc cmd=$BASH_COMMAND" | tee -a "$RES"; exit "$rc"' ERR
trap 'exit 143' TERM
trap 'exit 130' INT

[ "$JASS_JOB_ID" = "$EXPECTED_JOB_ID" ] || die "job id mismatch"
[ "$(git rev-parse HEAD)" = "$EXPECTED_CODE_SHA" ] || die "code SHA mismatch"
[ -z "$(git branch --show-current)" ] || die "worktree must be detached"
HOST="$(hostname)"
[ "$HOST" = "$EXPECTED_HOST" ] || die "box inattendue : $HOST (attendu $EXPECTED_HOST)"

# Archive gelée : source de vérité, vérifiée le 2026-07-23, 43 Mo.
REMOTE='r2:jass-data/runtime/scan/7aae17e7b7bfc47744601afb1ee7655e18983ce5'
EXPECTED_COMMIT='7aae17e7b7bfc47744601afb1ee7655e18983ce5'
EXPECTED_BIN='a634cbb44c9528eab277cdf6cdf8d29d506318ce5fba3f9bc69c2025b5941864'
EXPECTED_INI='dc201a7debaf98bb869fb3d6b641adb219df71b0ea22004b2d9b6f51cdb69538'
EXPECTED_EVAL='0e7161c38af605f5e367f3f8fe17525d1c40db722714c68921971b386e58abba'
EXPECTED_FP='91698ab5c17d5193130d058f3bd7438b868967ae5460c1296bdc6ab60c53d4bf'
# Surchargeable UNIQUEMENT pour que le banc d'essai puisse exercer pour de vrai
# les deux branches (installation propre / conflit préservé) sans écrire dans
# /root. Aucun script de queue ne le définit ; la valeur de production est en
# dur ci-dessous. Un chemin relatif est refusé : le `mv` atomique et le garde-fou
# du répertoire temporaire supposent tous deux un chemin absolu.
TARGET="${SCAN_INSTALL_TARGET:-/root/jass-scan}"
case "$TARGET" in /*) ;; *) die "SCAN_INSTALL_TARGET doit être absolu : $TARGET";; esac

say "phase=disk-guard"
# On mesure le système de fichiers où l'installation va ATTERRIR, pas un /root
# supposé : remonter jusqu'au premier ancêtre qui existe, puisque la cible
# elle-même est justement ce qu'on est peut-être en train de créer.
DFDIR="$TARGET"
while [ ! -d "$DFDIR" ] && [ "$DFDIR" != "/" ]; do DFDIR="$(dirname "$DFDIR")"; done
DFA=$(df -Pm "$DFDIR" | awk 'NR==2{print $4}')
[ "${DFA:-0}" -gt 3000 ] || die "moins de 3 Go libres sur $DFDIR (${DFA} Mo) — l'archive ne fait que 43 Mo, mais on ne travaille pas sur un disque plein (ccx33, 2026-07-11)"
say "  $DFDIR libre = ${DFA} Mo ✓"

# Ce que cpx62-1111 n'a pas pu dire : absent, ou présent-mais-autre-chose ?
say "phase=describe-what-is-already-there"
if [ -e "$TARGET" ] || [ -L "$TARGET" ]; then
  say "  $TARGET EXISTE — inventaire dans preexisting-listing.txt"
  ls -laR "$TARGET" > "$ART/preexisting-listing.txt" 2>&1 || true
  find "$TARGET" -type f -exec sha256sum {} + > "$ART/preexisting-sha256.txt" 2>&1 || true
else
  say "  $TARGET ABSENT — installation propre"
  : > "$ART/preexisting-listing.txt"
fi

say "phase=fetch-and-verify-archive"
STAGE="$JASS_RESULT_DIR/scan-archive"
mkdir -p "$STAGE"
rclone copy "$REMOTE" "$STAGE" || die "rclone copy a échoué depuis $REMOTE"

[ "$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["state"])' "$STAGE/_SUCCESS")" = verified ] ||
  die "_SUCCESS de l'archive n'est pas 'verified'"
CHECKSUMS_SHA="$(sha256sum "$STAGE/checksums.sha256" | awk '{print $1}')"
[ "$CHECKSUMS_SHA" = "$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["checksums_sha256"])' "$STAGE/_SUCCESS")" ] ||
  die "checksums.sha256 ne correspond pas à l'empreinte annoncée dans _SUCCESS"
(cd "$STAGE" && sha256sum -c checksums.sha256) > "$ART/archive-checksums.log" ||
  die "au moins un fichier de l'archive a un hash différent — voir archive-checksums.log"
[ "$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["source_commit"])' "$STAGE/archive-manifest.json")" = "$EXPECTED_COMMIT" ] ||
  die "source_commit de l'archive ≠ $EXPECTED_COMMIT"
[ "$(sha256sum "$STAGE/scan_linux"   | awk '{print $1}')" = "$EXPECTED_BIN"  ] || die "hash scan_linux"
[ "$(sha256sum "$STAGE/scan.ini"     | awk '{print $1}')" = "$EXPECTED_INI"  ] || die "hash scan.ini"
[ "$(sha256sum "$STAGE/data/eval"    | awk '{print $1}')" = "$EXPECTED_EVAL" ] || die "hash data/eval"
STAGED_FP="$(python3 jobs/tools/scan_runtime_fingerprint.py --scan-dir "$STAGE" --output "$ART/staged-scan-runtime-manifest.json")"
[ "$STAGED_FP" = "$EXPECTED_FP" ] || die "empreinte du runtime stagé ≠ $EXPECTED_FP"
say "  archive ✓ : 4 hashes + empreinte conformes à l'épinglage"

say "phase=install"
INSTALL_STATE=already_exact
CONFLICT=0
if [ -e "$TARGET" ] || [ -L "$TARGET" ]; then
  TARGET_FP="$(python3 jobs/tools/scan_runtime_fingerprint.py --scan-dir "$TARGET" \
                 --output "$ART/existing-scan-runtime-manifest.json" 2>/dev/null || true)"
  if [ "$TARGET_FP" != "$EXPECTED_FP" ]; then
    CONFLICT=1
    INSTALL_STATE=conflict_preserved
    say "  ⚠️ $TARGET existe avec une empreinte DIFFÉRENTE (« ${TARGET_FP:-illisible} »)"
    say "     rien n'a été touché — voir preexisting-listing.txt / preexisting-sha256.txt"
  else
    say "  $TARGET déjà exactement conforme — rien à faire"
  fi
else
  TMP_TARGET="$TARGET.install-$JASS_ATTEMPT_ID"
  # Le `rm -rf` de nettoyage ne doit JAMAIS pouvoir viser autre chose que ce
  # répertoire-là : on vérifie le suffixe avant de créer ET avant de supprimer.
  case "$TMP_TARGET" in "$TARGET".install-?*) ;; *) die "garde-fou chemin temporaire";; esac
  trap 'rc=$?; if [ -n "${TMP_TARGET:-}" ] && [ -e "$TMP_TARGET" ]; then case "$TMP_TARGET" in "$TARGET".install-?*) rm -rf -- "$TMP_TARGET";; esac; fi; exit "$rc"' ERR
  mkdir -p "$(dirname "$TARGET")" "$TMP_TARGET/data"
  install -m 0555 "$STAGE/scan_linux"                 "$TMP_TARGET/scan_linux"
  install -m 0444 "$STAGE/scan.ini"                   "$TMP_TARGET/scan.ini"
  install -m 0444 "$STAGE/data/eval"                  "$TMP_TARGET/data/eval"
  install -m 0444 "$STAGE/scan-source.bundle"         "$TMP_TARGET/scan-source.bundle"
  install -m 0444 "$STAGE/archive-manifest.json"      "$TMP_TARGET/archive-manifest.json"
  install -m 0444 "$STAGE/checksums.sha256"           "$TMP_TARGET/checksums.sha256"
  install -m 0444 "$STAGE/scan-runtime-manifest.json" "$TMP_TARGET/scan-runtime-manifest.json"
  mv "$TMP_TARGET" "$TARGET"          # atomique : jamais de /root/jass-scan à moitié écrit
  TMP_TARGET=''
  trap 'rc=$?; set +e; echo "ABORT line=$LINENO rc=$rc cmd=$BASH_COMMAND" | tee -a "$RES"; exit "$rc"' ERR
  INSTALL_STATE=installed
  say "  installé atomiquement dans $TARGET"
fi

if [ "$CONFLICT" -eq 0 ]; then
  say "phase=verify-installed-runtime"
  FINAL_FP="$(python3 jobs/tools/scan_runtime_fingerprint.py --scan-dir "$TARGET" \
                --output "$ART/final-scan-runtime-manifest.json")"
  [ "$FINAL_FP" = "$EXPECTED_FP" ] || die "empreinte post-installation ≠ $EXPECTED_FP"
  # Le contrôle qui compte vraiment : il PARLE. Un hash correct sur une box dont
  # le loader n'a pas les bonnes libs donnerait quand même un binaire muet.
  (cd "$TARGET" && printf 'hub\nquit\n' | timeout 15 ./scan_linux hub) > "$ART/scan-hub-smoke.log" 2>&1 ||
    die "Scan n'a pas répondu au handshake HUB — voir scan-hub-smoke.log"
  grep -q '^id name=Scan ' "$ART/scan-hub-smoke.log" || die "pas de ligne 'id name=Scan' au handshake"
  grep -q '^wait$'         "$ART/scan-hub-smoke.log" || die "pas de 'wait' au handshake"
  say "  handshake HUB ✓ : $(grep -m1 '^id name=Scan ' "$ART/scan-hub-smoke.log")"
  READY=1
  VERDICT="SCAN_RUNTIME_READY_${EXPECTED_HOST}"
else
  READY=0
  # En conflit, l'empreinte qui INFORME est celle du runtime TROUVÉ, pas celle
  # qu'on espérait : rapporter l'attendue ici ferait lire « conforme » à un
  # résumé qui dit par ailleurs scan_ready=false.
  FINAL_FP="${TARGET_FP:-unreadable}"
  VERDICT="SCAN_RUNTIME_CONFLICT_${EXPECTED_HOST}"
fi

python3 - "$ART/JASS_CONTROL_SUMMARY.json" "$VERDICT" "$READY" "$HOST" \
         "$INSTALL_STATE" "$REMOTE" "$EXPECTED_COMMIT" "${FINAL_FP:-$STAGED_FP}" \
         "$EXPECTED_FP" <<'PY'
import json, sys
out, verdict, ready, host, state, uri, commit, fp, expected_fp = sys.argv[1:10]
json.dump({"schema": 2, "verdict": verdict, "scan_ready": ready == "1",
           "host": host, "install_state": state, "archive_uri": uri,
           "source_commit": commit,
           # En READY les deux coïncident ; en CONFLICT « observed » dit ce qui
           # est réellement sur la box et « expected » ce qu'on voulait, et
           # l'écart entre les deux EST le rapport.
           "runtime_fingerprint_sha256": fp,
           "expected_runtime_fingerprint_sha256": expected_fp,
           "diagnostic_only": True, "promotion_authorized": False,
           "automatic_next_job": None},
          open(out, "w"), indent=2, sort_keys=True)
open(out, "a").write("\n")
PY
cp "$ART/JASS_CONTROL_SUMMARY.json" "$ART/scientific-summary.json"
: > "$ART/VERDICT__$VERDICT"
printf 'PROMOTION_AUTHORIZED__FALSE\n' > "$ART/PROMOTION_AUTHORIZED__FALSE"
printf 'AUTOMATIC_NEXT_JOB__NULL\n'    > "$ART/AUTOMATIC_NEXT_JOB__NULL"

say "$VERDICT install_state=$INSTALL_STATE fingerprint=${FINAL_FP:-$STAGED_FP} attendue=$EXPECTED_FP"
say "promotion=false automatic_next_job=null"
[ "$CONFLICT" -eq 0 ] || exit 4
