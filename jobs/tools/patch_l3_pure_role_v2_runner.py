#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path

DUMP_NEEDLE = '''  "$J" --dump-eval-features "$W/g${generation}.fit.jnnw" \\
    "$W/g${generation}.feat" > "$W/g${generation}-features.log" 2>&1
'''
DUMP_REPLACEMENT = '''  IMBALANCE2_REWEIGHT_POLICY=role-aware-v2 python3 \\
    jobs/tools/prepare_imbalance2_training.py reweight \\
      --input "$W/g${generation}.fit.jnnw" \\
      --output "$W/g${generation}.weighted.jnnw" \\
      --holdout-count "$HOLDOUT_COUNT" \\
      --win-weight 1 --draw-weight 2 --loss-weight 4 \\
      --seed $((BASE_SEED + generation)) \\
      --report "$ART/g${generation}-role-v2-reweight.json"
  TRAIN_DATA="$W/g${generation}.weighted.jnnw"
  "$J" --dump-eval-features "$TRAIN_DATA" \\
    "$W/g${generation}.feat" > "$W/g${generation}-features.log" 2>&1
'''
TRAIN_NEEDLE = '''      --data "$W/g${generation}.fit.jnnw" \\
'''
TRAIN_REPLACEMENT = '''      --data "$TRAIN_DATA" \\
'''


def patch_text(text: str) -> str:
    if text.count(DUMP_NEEDLE) != 1:
        raise ValueError("frozen runner dump-feature insertion point changed")
    if text.count(TRAIN_NEEDLE) != 1:
        raise ValueError("frozen runner train-data insertion point changed")
    patched = text.replace(DUMP_NEEDLE, DUMP_REPLACEMENT)
    patched = patched.replace(TRAIN_NEEDLE, TRAIN_REPLACEMENT)
    return patched


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()

    source = Path(args.input)
    output = Path(args.output)
    patched = patch_text(source.read_text(encoding="utf-8"))
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(patched, encoding="utf-8")
    output.chmod(0o755)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
