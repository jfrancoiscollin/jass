#!/usr/bin/env python3
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Check active code for dependencies that block retirement of the legacy branch.

Historical queues, results, documentation and retired one-shot templates are evidence,
not executable production surfaces. The guard scans only CI, runner-v3, current job
templates/tools and build/runtime code, then emits a deterministic JSON report.
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
from dataclasses import asdict, dataclass
from pathlib import Path


@dataclass(frozen=True)
class Finding:
    kind: str
    path: str
    line: int
    text: str


ACTIVE_PREFIXES = (
    ".github/workflows/",
    "infra/runner_v3",
    "infra/jass-runner-v3.",
    "infra/runner-v3.env",
    "jobs/templates/",
    "jobs/tools/",
    "src/",
    "pattern_jass/src/",
)
ACTIVE_ROOT_FILES = {"CMakeLists.txt", "Makefile", "pyproject.toml"}
EXCLUDED_PREFIXES = (
    "docs/",
    "jobs/results/",
    "jobs/queue/",
    "jobs/paused/",
    "jobs/archive/",
    "infra/control-plane-seed/",
)
POLICY_IMPLEMENTATION_FILES = {
    "infra/runner_v3.py",
    "infra/tests/test_runner_v3.py",
    "jobs/tools/check_retirement_readiness.py",
}
# Numbered templates are immutable records of completed historical experiments. They
# are not selected by runner-v3 and must not block branch retirement merely because
# they preserve the original absolute paths. Deprecated T1-bis launchers are likewise
# superseded by the native runner-v3 path.
RETIRED_TEMPLATE_RX = re.compile(r"^jobs/templates/\d{4}[a-z]?-.*\.sh$")
RETIRED_TEMPLATE_NAMES = {
    "jobs/templates/t1bis-adj-g1-v2-launch.sh",
    "jobs/templates/t1bis-adj-g1-v2.sh",
    "jobs/templates/t1bis-adj-g1.sh",
    "jobs/templates/t1bis-adj-g1-runner-v3.sh",
    "jobs/templates/wdl-loop-portable.sh",
}
TEXT_SUFFIXES = {
    ".c", ".cc", ".cpp", ".h", ".hpp", ".cmake", ".ini", ".json",
    ".md", ".py", ".sh", ".service", ".timer", ".toml", ".txt",
    ".yaml", ".yml",
}


def tracked_files(repo: Path) -> list[str]:
    raw = subprocess.check_output(["git", "-C", str(repo), "ls-files", "-z"])
    return [item.decode("utf-8", "surrogateescape") for item in raw.split(b"\0") if item]


def is_active(path: str) -> bool:
    if path in POLICY_IMPLEMENTATION_FILES:
        return False
    if path in RETIRED_TEMPLATE_NAMES or RETIRED_TEMPLATE_RX.match(path):
        return False
    if path in ACTIVE_ROOT_FILES:
        return True
    if path.startswith(EXCLUDED_PREFIXES):
        return False
    return path.startswith(ACTIVE_PREFIXES)


def patterns() -> dict[str, re.Pattern[str]]:
    primary = "".join(("ma", "in"))
    root_clone = "/" + "/".join(("root", "jass"))
    return {
        # Match the retired clone itself and its children, but not independent
        # paths that merely share the prefix (for example /root/jass-scan or
        # /root/jass-control).
        "hardcoded_legacy_clone": re.compile(
            re.escape(root_clone) + r"(?![A-Za-z0-9_.-])"
        ),
        "legacy_remote_ref": re.compile(re.escape("origin/" + primary)),
        "legacy_push_ref": re.compile(re.escape("HEAD:" + primary)),
        "legacy_full_ref": re.compile(re.escape("refs/heads/" + primary)),
    }


def scan(repo: Path) -> tuple[list[Finding], list[Finding]]:
    legacy: list[Finding] = []
    root_tools: list[Finding] = []
    legacy_patterns = patterns()
    root_tool_rx = re.compile(
        r"(?:python3?|PYTHONPATH=|--calibrate-tool\s+|['\"])(tools/[A-Za-z0-9_.\-/]+)"
    )
    for rel in tracked_files(repo):
        if not is_active(rel):
            continue
        path = repo / rel
        if path.suffix.lower() not in TEXT_SUFFIXES and path.name not in ACTIVE_ROOT_FILES:
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        for line_no, line in enumerate(text.splitlines(), 1):
            for kind, rx in legacy_patterns.items():
                if rx.search(line):
                    legacy.append(Finding(kind, rel, line_no, line[:500]))
            match = root_tool_rx.search(line)
            if match:
                root_tools.append(Finding("active_root_tool_reference", rel, line_no, line[:500]))
    return legacy, root_tools


def load_baseline(path: Path | None) -> dict[str, int]:
    if path is None:
        return {"legacy_findings": 0, "root_tool_references": 0}
    data = json.loads(path.read_text(encoding="utf-8"))
    return {
        "legacy_findings": int(data["legacy_findings"]),
        "root_tool_references": int(data["root_tool_references"]),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, default=Path.cwd())
    parser.add_argument("--baseline", type=Path)
    parser.add_argument("--out", type=Path)
    parser.add_argument("--require-zero", action="store_true")
    args = parser.parse_args(argv)

    repo = args.repo.resolve()
    legacy, root_tools = scan(repo)
    counts = {
        "legacy_findings": len(legacy),
        "root_tool_references": len(root_tools),
    }
    baseline = load_baseline(args.baseline)
    regressions = {
        key: counts[key] - baseline[key]
        for key in counts
        if counts[key] > baseline[key]
    }
    ready = not legacy and not root_tools
    result = {
        "schema": 1,
        "state": "completed",
        "ready_for_retirement": ready,
        "counts": counts,
        "baseline": baseline,
        "regressions": regressions,
        "legacy_findings": [asdict(item) for item in legacy],
        "root_tool_references": [asdict(item) for item in root_tools],
        "excluded_prefixes": list(EXCLUDED_PREFIXES),
        "retired_template_names": sorted(RETIRED_TEMPLATE_NAMES),
        "retired_numbered_templates": True,
    }
    rendered = json.dumps(result, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(rendered, encoding="utf-8")
    print(rendered, end="")

    if args.require_zero:
        return 0 if ready else 2
    return 0 if not regressions else 1


if __name__ == "__main__":
    raise SystemExit(main())
