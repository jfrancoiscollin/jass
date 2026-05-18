#!/usr/bin/env bash
# id: 0015-backup-cycle8-to-release
# description: Upload the Cycle 8 master-games artefacts produced by
#              0014 to a GitHub Release (tag `cycle8-data`) so the
#              data survives a CCX23 disaster. The runner's per-file
#              git-commit cap (95 MB after PR #48) catches small
#              files but leaves master-1600.jnnw (~300-600 MB) and
#              expert_games.db (~1-5 GB) server-only. This job is
#              the safety net for those.
#
#              Graceful degradation: if GITHUB_TOKEN is unset on the
#              runner host, the job logs a warning and exits 0 (no
#              failure cascade — downstream 0016 train job still
#              runs). To enable uploads, see "GITHUB_TOKEN setup"
#              in the project README.
#
#              Idempotent: re-running replaces the existing assets
#              on the same tag. Safe to re-queue (delete
#              jobs/results/0015-…/) any time.
# expected_duration: ~5-15 min on a typical Hetzner cloud uplink
#                    (master-1600 + DB compressed ~1-2 GB upload).
set -uo pipefail
cd /root/jass

OUT_BASE="/root/jass/jobs/results/0015-backup-cycle8-to-release"
ART="$OUT_BASE/artefacts.src"
mkdir -p "$ART"

FETCH_ART="/root/jass/jobs/results/0014-fetch-master-games/artefacts.src"
MASTER_2000="$FETCH_ART/master-2000.jnnw"
MASTER_1600="$FETCH_ART/master-1600.jnnw"
DB="/root/jass/data/expert_games.db"

REPO="jfrancoiscollin/jass"
TAG="cycle8-data"
API="https://api.github.com/repos/$REPO"
UPLOADS="https://uploads.github.com/repos/$REPO"

echo "=== host facts ==="
echo "host:   $(hostname)"
echo "disk:   $(df -h / | awk 'NR==2 {print $4" free of "$2}')"

echo
echo "=== preflight: prerequisites ==="
all_ok=1
for f in "$MASTER_2000" "$MASTER_1600" "$DB"; do
    if [ -f "$f" ]; then
        echo "  ✓ $(ls -lh "$f" | awk '{print $5"  "$9}')"
    else
        echo "  ✗ MISSING: $f"
        all_ok=0
    fi
done
if [ "$all_ok" -ne 1 ]; then
    echo "ABORT: some prerequisites are missing — did 0014 finish?"
    echo "Re-queue this job (rm -r jobs/results/0015-…) once 0014 completes."
    exit 3
fi

echo
echo "=== preflight: GitHub auth ==="
if [ -z "${GITHUB_TOKEN:-}" ]; then
    cat <<'WARN'
WARNING: GITHUB_TOKEN env var is not set on this host.

  Skipping upload — the job exits with rc=0 so the downstream
  pipeline (0016 train) is not blocked. The master-games artefacts
  remain on the server only; if CCX23 dies, they are regenerable
  via 0014 re-run (cost: ~6-14h re-fetch + ~1-3h re-convert).

  To enable uploads on a future run:

      ssh root@<ccx23-ip>
      # Create a fine-grained PAT at:
      #   https://github.com/settings/personal-access-tokens/new
      #   Repository access: only jfrancoiscollin/jass
      #   Permissions → Repository → Contents: Read and write
      mkdir -p /etc/jass-runner
      cat > /etc/jass-runner/secrets.env <<'EOF'
      GITHUB_TOKEN=ghp_xxxxxxxxxxxxxxxxxxxxxxxx
      EOF
      chmod 0600 /etc/jass-runner/secrets.env

      # Add EnvironmentFile=/etc/jass-runner/secrets.env to
      # /etc/systemd/system/jass-runner.service [Service] section,
      # then:
      systemctl daemon-reload
      systemctl restart jass-runner.timer

  Then re-queue this job:  rm -r jobs/results/0015-…  (+ commit + push)
WARN
    # Persist the "skipped" status as an artefact for visibility.
    echo "skipped — GITHUB_TOKEN not set, see README.md for setup" \
        > "$ART/upload.skipped"
    exit 0
fi
echo "GITHUB_TOKEN is set (length=${#GITHUB_TOKEN}); proceeding with upload."

# Resolve external deps. `curl` is universal; `jq` is needed to parse
# GitHub API responses. Install it if missing — small, ~1 MB.
if ! command -v jq > /dev/null; then
    echo "Installing jq…"
    apt-get update -qq && apt-get install -qq -y jq
fi
if ! command -v zstd > /dev/null; then
    echo "Installing zstd…"
    apt-get update -qq && apt-get install -qq -y zstd
fi

# Compress the SQLite for transit. PDN text compresses well (~3-5x).
DB_ZST="$ART/expert_games.db.zst"
echo
echo "=== compressing SQLite ($(du -h "$DB" | cut -f1)) → zstd-19 ==="
zstd -T0 -19 --force -o "$DB_ZST" "$DB"
echo "  $(du -h "$DB_ZST" | cut -f1) compressed (ratio $(python3 -c "
import os
src = os.path.getsize('$DB')
dst = os.path.getsize('$DB_ZST')
print(f'{src/dst:.2f}x')
"))"

# Reusable curl auth header pattern.
AUTH=(-H "Authorization: token $GITHUB_TOKEN" -H "Accept: application/vnd.github+json")

echo
echo "=== ensuring release tag '$TAG' exists ==="
HTTP=$(curl -s -o "$ART/release.json" -w "%{http_code}" "${AUTH[@]}" "$API/releases/tags/$TAG")
if [ "$HTTP" = "200" ]; then
    RELEASE_ID=$(jq -r '.id' "$ART/release.json")
    echo "  release exists, id=$RELEASE_ID"
elif [ "$HTTP" = "404" ]; then
    echo "  release does not exist, creating…"
    BODY=$(cat <<'EOF'
{
  "tag_name": "cycle8-data",
  "name": "Cycle 8 data — Lidraughts master games",
  "body": "Lidraughts master-game corpus produced by `jobs/queue/0014-fetch-master-games.sh`. Used as one half of the blended training set in 0016-train-with-master-blend.sh (see the project README's master-games roadmap section).\n\n**Assets**:\n- `master-2000.jnnw` — JNNW records for games where MIN(white_rating, black_rating) >= 2000\n- `master-1600.jnnw` — same, but rating >= 1600 (larger volume)\n- `expert_games.db.zst` — full SQLite store (zstd-compressed) with every fetched PDN; can re-derive the JNNW files via `tools/pdn_to_jnnw.py`\n\nThis tag is overwritten on every 0015 re-run, so it always reflects the most recent fetch.",
  "draft": false,
  "prerelease": false
}
EOF
)
    curl -s -X POST "${AUTH[@]}" "$API/releases" -d "$BODY" -o "$ART/release.json"
    RELEASE_ID=$(jq -r '.id // empty' "$ART/release.json")
    if [ -z "$RELEASE_ID" ]; then
        echo "ABORT: release creation failed. Response:"
        cat "$ART/release.json"
        exit 4
    fi
    echo "  release created, id=$RELEASE_ID"
else
    echo "ABORT: unexpected HTTP $HTTP from GET release. Response:"
    cat "$ART/release.json"
    exit 4
fi

# Function: delete existing asset of the same name (if any) then upload.
upload_asset() {
    local src="$1"
    local name="$(basename "$src")"
    local size_h="$(du -h "$src" | cut -f1)"

    echo
    echo "--- $name ($size_h) ---"

    # Find an existing asset with this name on the release.
    curl -s "${AUTH[@]}" "$API/releases/$RELEASE_ID/assets" \
        > "$ART/_assets.json"
    local existing
    existing=$(jq -r --arg n "$name" '.[] | select(.name==$n) | .id // empty' \
        "$ART/_assets.json")
    if [ -n "$existing" ]; then
        echo "  deleting existing asset id=$existing"
        curl -s -X DELETE "${AUTH[@]}" "$API/releases/assets/$existing" \
            > /dev/null
    fi

    echo "  uploading…"
    local t0=$(date +%s)
    curl -s -X POST \
        -H "Authorization: token $GITHUB_TOKEN" \
        -H "Content-Type: application/octet-stream" \
        --data-binary "@$src" \
        "$UPLOADS/releases/$RELEASE_ID/assets?name=$name" \
        -o "$ART/_upload_${name}.json"
    local rc=$?
    local elapsed=$(( $(date +%s) - t0 ))
    if [ "$rc" -ne 0 ]; then
        echo "  FAILED: curl rc=$rc after ${elapsed}s"
        return $rc
    fi
    local asset_state
    asset_state=$(jq -r '.state // empty' "$ART/_upload_${name}.json")
    if [ "$asset_state" != "uploaded" ]; then
        echo "  FAILED: asset state=$asset_state, response:"
        cat "$ART/_upload_${name}.json"
        return 1
    fi
    local browser_url
    browser_url=$(jq -r '.browser_download_url' "$ART/_upload_${name}.json")
    echo "  ✓ uploaded in ${elapsed}s → $browser_url"
}

echo
echo "=== uploading assets ==="
upload_asset "$MASTER_2000" || exit 5
upload_asset "$MASTER_1600" || exit 5
upload_asset "$DB_ZST"      || exit 5

# Drop the compressed DB once uploaded to save disk; the SQLite original
# stays at $DB for the runner to read between cycles.
rm -f "$DB_ZST"

echo
echo "=========================================================="
echo "                0015 BACKUP-CYCLE8 SUMMARY"
echo "=========================================================="
echo "  release tag:        $TAG"
echo "  release id:         $RELEASE_ID"
echo "  release URL:        https://github.com/$REPO/releases/tag/$TAG"
echo "  assets uploaded:    3 (master-2000.jnnw, master-1600.jnnw, expert_games.db.zst)"
echo "  recovery procedure: 'wget https://github.com/$REPO/releases/download/$TAG/<asset>'"
echo "=========================================================="
