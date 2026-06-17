# shellcheck shell=bash
# jobs/lib/manifest.sh — artefact provenance + comparison guard (science-ops).
# ----------------------------------------------------------------------------
# Footgun this prevents: two .pjtw can share NUM_EXTRAS=110 yet carry DIFFERENT
# extras (e.g. JASS_ENDGAME_FEATURES vs JASS_KING_MOBILITY) — a wrong binary
# loads them silently and mis-evaluates. A manifest records the exact build
# flags + dataset fingerprint next to each artefact; the guard ABORTS an A/B
# whose two artefacts are not actually comparable.
#
# Usage in a job:
#   source jobs/lib/manifest.sh
#   manifest_write "$ART/endg.pjtw" "JASS_ENDGAME_FEATURES=ON" "$CUM"   # after training
#   manifest_jnnw  "$CUM"                                               # dataset stats sidecar
#   manifest_assert_comparable "$A.pjtw" "$B.pjtw"                      # before any A/B benchmark

# manifest_write <pjtw> <build_flags_string> [data_path] [extra key=val ...]
manifest_write() {
  local pjtw="${1:?pjtw}" flags="${2:-}" data="${3:-}"; shift $(( $# >= 3 ? 3 : $# ))
  local commit host now nx dsz="0" dhash=""
  commit=$(git rev-parse --short HEAD 2>/dev/null || echo unknown)
  host=$(hostname); now=$(date -u +%Y-%m-%dT%H:%M:%SZ)
  nx=$(python3 -c "import struct;print(struct.unpack('<I',open('$pjtw','rb').read(20)[16:20])[0])" 2>/dev/null || echo -1)
  if [ -n "$data" ] && [ -f "$data" ]; then
    dsz=$(stat -c%s "$data" 2>/dev/null || echo 0)
    dhash=$(head -c 67108864 "$data" 2>/dev/null | sha256sum | cut -d' ' -f1)
  fi
  python3 - "$pjtw" "$flags" "$commit" "$host" "$now" "$nx" "$data" "$dsz" "$dhash" "$@" <<'PY'
import json,sys
pjtw,flags,commit,host,now,nx,data,dsz,dhash,*extra=sys.argv[1:]
m={"pjtw":pjtw,"git_commit":commit,"host":host,"date":now,
   "n_ext":int(nx),"build_flags":flags,
   "dataset":{"path":data,"bytes":int(dsz),"sha256_head64m":dhash}}
for kv in extra:
    if "=" in kv:
        k,v=kv.split("=",1); m[k]=v
open(pjtw+".manifest.json","w").write(json.dumps(m,indent=2,sort_keys=True))
print(f"  [manifest] {pjtw}.manifest.json  (n_ext={nx}, flags='{flags}')")
PY
}

# manifest_jnnw <jnnw> — dataset stats sidecar via jnnw_stats.py (best-effort).
manifest_jnnw() {
  local data="${1:?jnnw}" tool="pattern_jass/tools/jnnw_stats.py"
  [ -f "$data" ] || { echo "  [manifest] (jnnw absent: $data)"; return 0; }
  if [ -f "$tool" ]; then
    python3 "$tool" "$data" --json > "${data}.stats.json" 2>/dev/null \
      && echo "  [manifest] ${data}.stats.json (jnnw_stats)" \
      || echo "  [manifest] (jnnw_stats a échoué sur $data)"
  fi
}

# manifest_assert_comparable <pjtwA> <pjtwB> — ABORT (exit 9) if not comparable.
manifest_assert_comparable() {
  python3 - "${1:?A}" "${2:?B}" <<'PY'
import json,sys
a,b=sys.argv[1],sys.argv[2]
def load(p):
    try: return json.load(open(p+".manifest.json"))
    except FileNotFoundError:
        print(f"  [manifest] ABORT — manifeste manquant pour {p} (comparaison non garantie)",file=sys.stderr); sys.exit(9)
ma,mb=load(a),load(b)
probs=[]
if ma["n_ext"]!=mb["n_ext"]: probs.append(f"n_ext {ma['n_ext']} != {mb['n_ext']}")
if ma["build_flags"]!=mb["build_flags"]: probs.append(f"flags '{ma['build_flags']}' != '{mb['build_flags']}'")
da,db=ma.get("dataset",{}),mb.get("dataset",{})
ha,hb=da.get("sha256_head64m"),db.get("sha256_head64m")
if ha and hb and ha!=hb: probs.append("dataset hash différent")
if probs:
    print("  [manifest] ABORT — artefacts NON comparables :",file=sys.stderr)
    for p in probs: print("    -",p,file=sys.stderr)
    sys.exit(9)
print(f"  [manifest] OK — comparables (n_ext={ma['n_ext']}, flags='{ma['build_flags']}')")
PY
}
