# Shared Jass agent boundary

Claude Code does not use Codex's `.codex/config.toml`. For scientific and operational boundaries, keep behavior aligned with the repository-wide policy in `AGENTS.md` and the authoritative Jass rules in `CLAUDE.md`.

If a Claude-specific routing instruction conflicts with an active experiment preregistration, terminal result, or an explicit current user instruction, the active scientific contract and current user instruction win. Do not use model routing as a reason to reinterpret frozen history or bypass launch approvals.
