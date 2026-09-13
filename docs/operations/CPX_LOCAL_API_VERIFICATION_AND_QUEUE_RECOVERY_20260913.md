# CPX local API verification and queue recovery — 2026-09-13

Classification: TECHNICAL. No ED4 scientific change or new scientific verdict.

## Verified scope

JFC supplied terminal output showing four tests passed, /health ok=true, and jass-control-plane.service active/running from the permanent path /opt/jass-control-plane/releases/b2c703b695a70e86e851d07b6c5cc8bb5aefe0e4/cpx_control_plane.py. The first post-restart curl connection failure was followed by successful bounded retry. No reinstall is indicated by that output.

JFC then supplied an authenticated /v1/status response: host=cpx62; ok=true; jobs=[]; runner Result=success, ExecMainStatus=0, ActiveState=inactive, SubState=dead, MainPID=0; StateChangeTimestamp=2026-09-13 15:51:39 UTC.

These are operator-provided observations, not a remotely retrieved CPX receipt. The configured runner is Type=oneshot. An inactive runner after a successful tick is not a service crash. The response does not establish timer state, a fresh ED4 claim, absence of all possible processes, or remote ChatGPT access. Do not infer any of those facts from ok=true.

## Queue defect and narrow repair

At jass-control commit f1dd428fed348423ac8e78a3ed470d8895127339, scripts 1939 and 1940 were placed under queue/, not queue/pending/, and the host filter selected the 1940 bootstrap. Earlier terminal output already showed this; repeated runner restarts were not a correction to the queue layout.

Companion repair: jfrancoiscollin/jass-control#644, head f7af7ea5fda19b170209c864f4972286cc06aa36.

- Move never-claimed 1939 into queue/pending and use the canonical set -Eeuo pipefail header.
- Keep its exact code SHA 04011fd1c7321021ef0df844517512ef9fa08795, spec/admission/profile, seeds, quotas, 900-second stage cap and 1500-second outer cap unchanged.
- Route cpx62 only to cpx62-1939-l3-ed4-fresh-s-source-rehearsal-v1; preserve other hosts and the global pause.
- Preserve unused 1940 outside the active queue as a disabled historical note; do not run its old installer over the successful permanent-path deployment.
- Do not fabricate a success status/receipt for 1940: manual installation is distinct from execution of that queued job.

Local validation actually performed: bash -n, all five unchanged dispatcher tests on the proposed queue fixture, a failing orphan-queue negative fixture, and recomputed spec/admission SHA256 checks. The test and dispatcher copies were verified against repository Git blob SHAs. These are not target-host tests; actual CPX claim and publication are pending.

Incident dedupe_key: cpx-1939-1940-orphan-queue-and-stale-route. Status remains MITIGATED pending a target-host receipt. This PR includes the auto-ledger incident payload; do not close it based only on CI or merge.

## Remote access is not yet connected

The local REST API is not itself a ChatGPT MCP connector. A separate adapter must expose only approved operations, keep the local token out of prompts/logs, and be connected through a supported authenticated transport. No public listener or token publication is authorized by this repair.

OpenAI currently documents Secure MCP Tunnel as a transport for a private MCP server, including stdio targets and outbound-only networking. This can avoid a public HTTPS endpoint, but requires tunnel permissions, association to the target ChatGPT workspace, a runtime credential stored outside Git, a working MCP adapter and an actual tool-discovery/authorization test.

Sources checked 2026-09-13:
- https://developers.openai.com/api/docs/guides/secure-mcp-tunnels
- https://developers.openai.com/api/docs/guides/developer-mode
- https://help.openai.com/en/articles/12584461-developer-mode-and-mcp-apps-in-chatgpt

The developer guide lists personal Plus/Pro eligibility and read/write tools, while the Help Center describes narrower Pro read/fetch availability. Do not promise write access on this account until the live interface and tool authorization establish it. The developer guide currently locates the user toggle under Settings > Security and login; other workspace interfaces are documented separately.

Next user-side connection check: enable or locate Developer mode in ChatGPT settings and inspect the custom-app/Tunnel creation options. This is not another CPX installation or runner restart. The MCP adapter, tunnel setup and an authenticated end-to-end tool call remain unfinished.
