#!/usr/bin/env python3
"""Mechanical ED5 W source repair: make the frozen >int32 seeds effective.

The historical ``--gen-data-wdl`` CLI stores/parses its positional seed as an
``int``.  ED4's 202609120402 seed and ED5's preregistered 202609140502 /
202609140512 seeds therefore all overflow and silently fall back to the legacy
seed.  That made the first ED5 W attempts reproduce the consumed ED4 W source.

This wrapper changes no ED5 science.  It patches only the throw-away archived
engine source built by the W source stage so the already-frozen numeric seed is
parsed and mixed as uint64_t.  Small historical seeds retain byte-identical seed
mixing semantics; no candidate/control/target is read here.
"""
from __future__ import annotations

from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from jobs.tools import ed4_fresh_w_source_stage as base
from jobs.tools import ed5_fresh_w_source_stage as stage


_OLD_DECL = "    int          random_seed      = 0;    // 0 → engine-fixed seed (legacy)"
_NEW_DECL = "    std::uint64_t random_seed      = 0;    // 0 → engine-fixed seed (legacy)"

_OLD_PARSE = """    if (p_argc > 7) {
        int v = parse_int_or(p_argv[7], -1);
        if (v > 0) random_seed = v;
    }
"""
_NEW_PARSE = """    if (p_argc > 7) {
        std::uint64_t v = 0;
        const std::string_view seed_arg{p_argv[7]};
        const auto [ptr, ec] = std::from_chars(
            seed_arg.data(), seed_arg.data() + seed_arg.size(), v);
        if (ec == std::errc{} && ptr == seed_arg.data() + seed_arg.size() && v > 0) {
            random_seed = v;
        }
    }
"""

_OLD_MIX = """    const std::uint64_t seed_value = (random_seed > 0)
        ? static_cast<std::uint64_t>(static_cast<std::uint32_t>(random_seed))
              * std::uint64_t{0x9E3779B97F4A7C15}
        : std::uint64_t{0x5eed5eed5eed5eed};
"""
_NEW_MIX = """    const std::uint64_t seed_value = (random_seed > 0)
        ? random_seed * std::uint64_t{0x9E3779B97F4A7C15}
        : std::uint64_t{0x5eed5eed5eed5eed};
"""


def patch_seed_width(source_root: Path) -> None:
    """Patch exactly the three known int32 seed truncation sites, fail closed."""
    path = source_root / "src/main.cpp"
    text = path.read_text()
    replacements = (
        (_OLD_DECL, _NEW_DECL, "seed declaration"),
        (_OLD_PARSE, _NEW_PARSE, "seed parser"),
        (_OLD_MIX, _NEW_MIX, "seed mixer"),
    )
    for old, new, label in replacements:
        count = text.count(old)
        if count != 1:
            raise ValueError(f"ed5_w_seed_width_patch_drift:{label}:{count}")
        text = text.replace(old, new, 1)
    path.write_text(text)


_ORIGINAL_CONFIGURE = stage.configure_base


def configure_base(seed: int, record_budget: int) -> None:
    """Keep ED5's existing mechanics and inject the isolated source repair."""
    _ORIGINAL_CONFIGURE(seed, record_budget)
    if getattr(configure_base, "installed", False):
        return

    previous_run = base.subprocess.run

    def run_with_seed_width_patch(*args, **kwargs):
        command = args[0] if args else kwargs.get("args")
        cwd = kwargs.get("cwd")
        if (
            isinstance(command, (list, tuple))
            and len(command) >= 2
            and command[1] == "pattern_jass/tools/gen_patterns.py"
            and cwd is not None
        ):
            patch_seed_width(Path(cwd))
        return previous_run(*args, **kwargs)

    base.subprocess.run = run_with_seed_width_patch
    setattr(configure_base, "installed", True)


stage.configure_base = configure_base


def main() -> int:
    return stage.main()


if __name__ == "__main__":
    raise SystemExit(main())
