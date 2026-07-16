# PR C migration scope

This draft starts the mechanical consolidation required before retiring the legacy branch.

Current audited baseline (develop `6043691587036aa41823fcd6301162ea2b0459ef`):

- 58 tracked files remain under `tools/`;
- 146 active references still mention the legacy branch or clone path;
- archives and historical result snapshots must remain unchanged.

## Required implementation sequence

1. Move active `tools/**` files to `jobs/tools/**` preserving file content and executable bits.
2. Rewrite only active references in CI, build files, templates and source code.
3. Keep compatibility shims only where an active consumer cannot be migrated atomically.
4. Generate a reviewed baseline for `infra/legacy_reference_guard.py` before enabling it in CI.
5. Remove the baseline progressively; the final PR gate is zero active findings and an empty root `tools/` directory.

No scientific parameter, shard count, model, corpus or gate setting may change in this PR.
