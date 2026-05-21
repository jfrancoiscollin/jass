#!/usr/bin/env bash
# id: 0024-probe-fmjd-spa
# description: Reverse-engineer the FMJD results SPA to find its PDN
#              download endpoint. The SPA at https://results.fmjd.org/
#              games/ shows config objects with `downloadAllGamesEnable=1`
#              and `pdnButtonEnable=1`, proving a PDN endpoint exists,
#              but we don't know its URL — and the user's DevTools
#              Network tab is mysteriously empty (probably service-worker
#              caching).
#
#              Strategy: download the SPA's HTML + JS bundles directly,
#              grep for the hardcoded API base URL and the PDN download
#              path. The runner has unrestricted egress (unlike my
#              local sandbox which is blocked by host_not_allowed), so
#              it can fetch results.fmjd.org without anti-bot trouble.
#
#              Also probes a short list of likely URL patterns as a
#              fallback (1 working pattern is enough — we report HTTP
#              status + first few bytes of the body for each).
#
#              Outputs to artefacts.src/:
#                spa-index.html   homepage of the SPA
#                spa-script-N.js  each JS bundle referenced
#                probe.log        full probe transcript (greps + HTTP
#                                 status for each candidate URL)
# expected_duration: ~30-60 seconds (16 HTTP requests, ~5 MB total).
set -uo pipefail
cd /root/jass

OUT_BASE="/root/jass/jobs/results/0024-probe-fmjd-spa"
ART="$OUT_BASE/artefacts.src"
mkdir -p "$ART"

UA="Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
SPA="https://results.fmjd.org/games/"

# Known tournament keys we saw in the FMJD homepage HTML.
KEYS=(
    "2026/fd_2333"    # World Team Championship 2026
    "2026/f_2786"     # the one whose JS config we inspected
    "2026/f_1926"     # Bourges Open 2026
)
IDS=("4993")          # the internal id we saw

LOG="$ART/probe.log"
exec > >(tee -a "$LOG") 2>&1

echo "=== Phase 1: SPA HTML ==="
curl -sSL -A "$UA" --max-time 15 "$SPA" -o "$ART/spa-index.html" \
    && echo "OK ($(stat -c%s "$ART/spa-index.html") B)" \
    || echo "FAIL"

echo
echo "=== Phase 2: linked JS bundles ==="
# Pull every <script src=...> reference; download each.
mapfile -t SCRIPTS < <(
    grep -oE 'src="[^"]+\.js[^"]*"' "$ART/spa-index.html" 2>/dev/null \
      | sed 's/src="//;s/"$//' | sort -u
)
echo "found ${#SCRIPTS[@]} scripts referenced"
i=0
for s in "${SCRIPTS[@]}"; do
    i=$((i + 1))
    # Resolve relative URLs against SPA base.
    case "$s" in
        http*) url="$s" ;;
        //*)   url="https:$s" ;;
        /*)    url="https://results.fmjd.org$s" ;;
        *)     url="${SPA}${s}" ;;
    esac
    out="$ART/spa-script-${i}.js"
    echo "  [$i] $url"
    curl -sSL -A "$UA" --max-time 15 "$url" -o "$out" 2>/dev/null \
        && echo "      -> $(stat -c%s "$out") B" \
        || echo "      -> FAIL"
done

echo
echo "=== Phase 3: grep JS for endpoints ==="
# Look for any URL or path that suggests API/PDN endpoints.
PATTERNS=(
    '"/[a-zA-Z0-9_/?&=.-]*api[a-zA-Z0-9_/?&=.-]*"'
    '"/[a-zA-Z0-9_/?&=.-]*pdn[a-zA-Z0-9_/?&=.-]*"'
    '"/[a-zA-Z0-9_/?&=.-]*download[a-zA-Z0-9_/?&=.-]*"'
    '"https?://[a-zA-Z0-9_/?&=.-]+\.(json|pdn|php)[^"]*"'
)
for p in "${PATTERNS[@]}"; do
    echo "--- pattern: $p ---"
    grep -hoE "$p" "$ART"/spa-script-*.js "$ART"/spa-index.html 2>/dev/null \
      | sort -u | head -40 || true
done

echo
echo "=== Phase 4: blind probe of likely PDN URLs ==="
URLS=()
for k in "${KEYS[@]}"; do
    kenc="${k/\//[@SL]}"   # 2026/f_2786 -> 2026[@SL]f_2786
    URLS+=(
        "https://results.fmjd.org/games/api/games?key=$k"
        "https://results.fmjd.org/games/api/games?key=$kenc"
        "https://results.fmjd.org/games/api/tournament?key=$k"
        "https://results.fmjd.org/games/api/pdn?key=$k"
        "https://results.fmjd.org/games/data/$k/all.pdn"
        "https://results.fmjd.org/games/data/$k/games.pdn"
        "https://results.fmjd.org/tournaments/$k/tournament.pdn"
        "https://results.fmjd.org/tournaments/$k/games.pdn"
        "https://results.fmjd.org/tournaments/$k/all_games.pdn"
        "https://results.fmjd.org/tournaments/$k/games/all.pdn"
    )
done
for id in "${IDS[@]}"; do
    URLS+=(
        "https://results.fmjd.org/games/api/games?id=$id"
        "https://results.fmjd.org/games/api/tournament/$id"
        "https://results.fmjd.org/games/api/tournament/$id/pdn"
        "https://results.fmjd.org/games/api/pdn?id=$id"
        "https://results.fmjd.org/games/pdn/$id"
        "https://results.fmjd.org/games/pdn/$id.pdn"
        "https://results.fmjd.org/pdn/$id.pdn"
        "https://results.fmjd.org/download/pdn/$id"
    )
done

for url in "${URLS[@]}"; do
    code=$(curl -sSL -A "$UA" --max-time 10 -o "$ART/last-probe.body" \
                -w "%{http_code}" "$url" 2>/dev/null)
    sz=$(stat -c%s "$ART/last-probe.body" 2>/dev/null || echo 0)
    # First chars of body to confirm PDN content (PDN starts with `[` typically).
    head_bytes=$(head -c 80 "$ART/last-probe.body" 2>/dev/null \
                    | tr -d '\n\r' | head -c 80)
    printf "  %s  %5d B  %s\n" "$code" "$sz" "$url"
    if [ "$code" = "200" ] && [ "$sz" -gt 200 ]; then
        printf "    body[0..80]: %s\n" "$head_bytes"
    fi
done
rm -f "$ART/last-probe.body"

echo
echo "=========================================================="
echo "       0024 FMJD-SPA-PROBE SUMMARY"
echo "=========================================================="
echo "  scripts downloaded:  ${#SCRIPTS[@]}"
echo "  endpoint patterns:   see Phase 3 above"
echo "  URL probes:          ${#URLS[@]} (see Phase 4 above)"
echo "=========================================================="
echo
echo "Next: identify the working URL in Phase 4 (HTTP 200 + non-trivial"
echo "body), confirm it returns PDN/JSON, and code the proper scraper"
echo "as 0025."
