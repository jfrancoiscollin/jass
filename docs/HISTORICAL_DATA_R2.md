# Historical experiment data

Large generated artifacts formerly committed on `main` and `develop` are archived and checksum-verified in Cloudflare R2.

Snapshot archive:

`r2:jass-data/historical/jass-snapshots/main-3b0ebd8de052__develop-9ff75ca633d8`

Complete pre-cleanup Git bundle (split parts, reassemble with `rclone cat <prefix>/part-*` in lexical order; sha256 of the concatenation = `4681248a140603b959a5f13ca49c8667f092717526b20ab33d84683af74db5c8`, 1 891 899 394 bytes):

`r2:jass-data/historical/git-bundles/jass-pre-cleanup-main-3b0ebd8de052__develop-f5410cbf7c38.bundle.parts`

The snapshot archive contains exact path-to-blob manifests and deduplicated packs. The Git bundle preserves the original commit graph for rollback (pre-rewrite tips: main `3b0ebd8de052dc82365ea6109442b9825f99a54c`, develop `f5410cbf7c385a5ae48e82f7ccb8ce11f81b12ff`). New runner-v3 results are written directly to R2 and must not be committed to this repository.

Use `tools/r2_restore_historical.py` on a configured runner host to restore an archived file.
