#!/usr/bin/env python3
"""Deterministic, order-preserving filters for aligned JNNW/JSM metadata."""

from __future__ import annotations

import argparse
import ast
import hashlib
import json
import struct
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools import selfplay_frontier as frontier  # noqa: E402


ALLOWED_COMPARE = {
    ast.Eq: lambda left, right: left == right,
    ast.NotEq: lambda left, right: left != right,
    ast.Lt: lambda left, right: left < right,
    ast.LtE: lambda left, right: left <= right,
    ast.Gt: lambda left, right: left > right,
    ast.GtE: lambda left, right: left >= right,
    ast.In: lambda left, right: left in right,
    ast.NotIn: lambda left, right: left not in right,
}

JSM2_ONLY_NAMES = {
    "ply", "game_plies", "last_eps_ply", "game_result", "has_game_context",
    "has_exploration", "contaminated", "plycap", "adjudicated", "tb_relabelled",
}


class Selection:
    """Small fail-closed expression language; never delegates to Python eval()."""

    def __init__(self, source: str):
        self.source = source.strip()
        if not self.source:
            raise ValueError("--select must not be empty")
        try:
            self.tree = ast.parse(self.source, mode="eval")
        except SyntaxError as exc:
            raise ValueError(f"invalid --select expression: {exc.msg}") from exc
        self.names = {node.id for node in ast.walk(self.tree) if isinstance(node, ast.Name)}
        self._validated_names: frozenset[str] | None = None
        self._validate(self.tree)

    def _validate(self, node: ast.AST) -> None:
        if isinstance(node, ast.Expression):
            self._validate(node.body)
        elif isinstance(node, ast.BoolOp) and isinstance(node.op, (ast.And, ast.Or)):
            if len(node.values) < 2:
                raise ValueError("boolean operator requires two operands")
            for value in node.values:
                self._validate(value)
        elif isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.Not):
            self._validate(node.operand)
        elif isinstance(node, ast.Compare):
            self._validate(node.left)
            for operator, comparator in zip(node.ops, node.comparators):
                if type(operator) not in ALLOWED_COMPARE:
                    raise ValueError(f"comparison {type(operator).__name__} is not allowed")
                self._validate(comparator)
        elif isinstance(node, ast.Name):
            if node.id.startswith("_"):
                raise ValueError("private names are not allowed")
        elif isinstance(node, ast.Constant) and isinstance(
            node.value, (bool, int, float, str, type(None))
        ):
            return
        elif isinstance(node, (ast.Tuple, ast.List, ast.Set)):
            for element in node.elts:
                self._validate(element)
        else:
            raise ValueError(f"expression node {type(node).__name__} is not allowed")

    def evaluate(self, values: dict[str, object]) -> bool:
        available = frozenset(values)
        if self._validated_names != available:
            unknown = self.names - values.keys()
            if unknown:
                raise ValueError(f"unknown predicate name(s): {', '.join(sorted(unknown))}")
            self._validated_names = available
        result = self._eval(self.tree.body, values)
        if not isinstance(result, bool):
            raise ValueError("--select must evaluate to a boolean")
        return result

    def _eval(self, node: ast.AST, values: dict[str, object]):
        if isinstance(node, ast.BoolOp):
            if isinstance(node.op, ast.And):
                for child in node.values:
                    value = self._eval(child, values)
                    if not isinstance(value, bool):
                        raise ValueError("and operands must be boolean")
                    if not value:
                        return False
                return True
            for child in node.values:
                value = self._eval(child, values)
                if not isinstance(value, bool):
                    raise ValueError("or operands must be boolean")
                if value:
                    return True
            return False
        if isinstance(node, ast.UnaryOp):
            value = self._eval(node.operand, values)
            if not isinstance(value, bool):
                raise ValueError("not operand must be boolean")
            return not value
        if isinstance(node, ast.Compare):
            left = self._eval(node.left, values)
            for operator, comparator in zip(node.ops, node.comparators):
                right = self._eval(comparator, values)
                try:
                    matched = ALLOWED_COMPARE[type(operator)](left, right)
                except TypeError as exc:
                    raise ValueError(
                        f"incompatible values in comparison: {left!r}, {right!r}"
                    ) from exc
                if not matched:
                    return False
                left = right
            return True
        if isinstance(node, ast.Name):
            return values[node.id]
        if isinstance(node, ast.Constant):
            return node.value
        if isinstance(node, ast.Tuple):
            return tuple(self._eval(child, values) for child in node.elts)
        if isinstance(node, ast.List):
            return [self._eval(child, values) for child in node.elts]
        if isinstance(node, ast.Set):
            return {self._eval(child, values) for child in node.elts}
        raise AssertionError(f"unvalidated AST node {type(node).__name__}")


def _position_values(record: bytes, row: frontier.Meta) -> dict[str, object]:
    wm, wk, bm, bk, stm, _score, wdl = struct.unpack("<QQQQBiB", record)
    if stm not in (0, 1):
        raise ValueError(f"side-to-move {stm} outside {{0,1}}")
    wdl = wdl if wdl < 128 else wdl - 256
    if wdl not in (-1, 0, 1):
        raise ValueError(f"WDL {wdl} outside {{-1,0,1}}")
    occupied = wm | wk | bm | bk
    if occupied >> 50:
        raise ValueError("piece bit outside the 50-square board")
    if occupied.bit_count() != sum(board.bit_count() for board in (wm, wk, bm, bk)):
        raise ValueError("overlapping piece bitboards")
    white_men = wm.bit_count()
    white_kings = wk.bit_count()
    black_men = bm.bit_count()
    black_kings = bk.bit_count()
    white_material = white_men + 3 * white_kings
    black_material = black_men + 3 * black_kings
    flags = row.flags or 0
    has_context = row.ply is not None
    contaminated = (
        has_context
        and row.last_eps_ply != 0xFFFF
        and row.ply <= row.last_eps_ply
    )
    return {
        "true": True,
        "false": False,
        "game_id": row.game_id,
        "opening_id": row.opening_id,
        "seeded": bool(row.seeded),
        "ply": row.ply,
        "game_plies": row.game_plies,
        "last_eps_ply": row.last_eps_ply,
        "game_result": row.game_result,
        "has_game_context": has_context,
        "has_exploration": has_context and row.last_eps_ply != 0xFFFF,
        "contaminated": bool(contaminated),
        "plycap": bool(flags & 0x01),
        "adjudicated": bool(flags & 0x02),
        "tb_relabelled": bool(flags & 0x04),
        "stm": stm,
        "wdl": wdl,
        "white_men": white_men,
        "white_kings": white_kings,
        "black_men": black_men,
        "black_kings": black_kings,
        "pieces": white_men + white_kings + black_men + black_kings,
        "kings": white_kings + black_kings,
        "has_kings": bool(wk or bk),
        "has_queens": bool(wk or bk),
        "white_material": white_material,
        "black_material": black_material,
        "material_balance_white": white_material - black_material,
        "abs_material_balance": abs(white_material - black_material),
    }


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def filter_corpus(
    data_path: Path,
    meta_path: Path,
    selection: Selection,
    out_data: Path,
    out_meta: Path,
    manifest_path: Path,
) -> dict:
    paths = [data_path, meta_path, out_data, out_meta, manifest_path]
    if len({path.resolve() for path in paths}) != len(paths):
        raise ValueError("input, output and manifest paths must all be distinct")
    for path in (out_data, out_meta, manifest_path):
        if path.exists():
            raise ValueError(f"refusing to overwrite existing output: {path}")

    total = frontier._counted_file_count(data_path, frontier.JNNW_MAGIC, frontier.JNNW_REC)
    meta_schema, meta_count = frontier._meta_file_info(meta_path)
    if total != meta_count:
        raise ValueError(f"data/meta count mismatch: {total} != {meta_count}")
    context_names = selection.names & JSM2_ONLY_NAMES
    if meta_schema is frontier.JSM1_SCHEMA and context_names:
        raise ValueError(
            "JSM2 is required for predicate(s): " + ", ".join(sorted(context_names))
        )

    out_data.parent.mkdir(parents=True, exist_ok=True)
    out_meta.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    data_tmp = out_data.with_name(out_data.name + ".tmp")
    meta_tmp = out_meta.with_name(out_meta.name + ".tmp")
    selected = 0
    try:
        with (
            data_path.open("rb") as data_in,
            meta_path.open("rb") as meta_in,
            data_tmp.open("wb") as data_out,
            meta_tmp.open("wb") as meta_out,
        ):
            data_in.seek(8)
            meta_in.seek(8)
            data_out.write(frontier.JNNW_MAGIC + struct.pack("<I", 0))
            meta_out.write(meta_schema.magic + struct.pack("<I", 0))
            for index in range(total):
                record = data_in.read(frontier.JNNW_REC)
                meta_raw = meta_in.read(meta_schema.record.size)
                if len(record) != frontier.JNNW_REC or len(meta_raw) != meta_schema.record.size:
                    raise ValueError(f"aligned pair truncated at record {index}")
                row = frontier._decode_meta(
                    meta_raw, meta_schema, context=f"{meta_path}: record {index}"
                )
                try:
                    keep = selection.evaluate(_position_values(record, row))
                except ValueError as exc:
                    raise ValueError(f"record {index}: {exc}") from exc
                if keep:
                    data_out.write(record)
                    meta_out.write(meta_raw)
                    selected += 1
            count = struct.pack("<I", selected)
            data_out.seek(4)
            data_out.write(count)
            meta_out.seek(4)
            meta_out.write(count)
        data_tmp.replace(out_data)
        meta_tmp.replace(out_meta)
    finally:
        for temporary in (data_tmp, meta_tmp):
            if temporary.exists():
                temporary.unlink()

    # Read back the complete counted pair before publishing the completion marker.
    if frontier._counted_file_count(out_data, frontier.JNNW_MAGIC, frontier.JNNW_REC) != selected:
        raise AssertionError("output JNNW count mismatch")
    out_schema, out_count = frontier._meta_file_info(out_meta)
    if out_schema is not meta_schema or out_count != selected:
        raise AssertionError("output sidecar schema/count mismatch")

    report = {
        "schema": 1,
        "operation": "corpus_filter",
        "selection": selection.source,
        "order_preserved": True,
        "input": {
            "data": str(data_path),
            "meta": str(meta_path),
            "records": total,
            "data_sha256": _sha256(data_path),
            "meta_sha256": _sha256(meta_path),
        },
        "output": {
            "data": str(out_data),
            "meta": str(out_meta),
            "records": selected,
            "data_sha256": _sha256(out_data),
            "meta_sha256": _sha256(out_meta),
        },
        "removed_records": total - selected,
        "sidecar_schema": {
            "magic": meta_schema.name,
            "record_size": meta_schema.record.size,
        },
    }
    manifest_path.write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data", required=True)
    parser.add_argument("--meta", required=True)
    parser.add_argument("--select", required=True)
    parser.add_argument("--out-data", required=True)
    parser.add_argument("--out-meta", required=True)
    parser.add_argument("--manifest", required=True)
    args = parser.parse_args(argv)
    try:
        report = filter_corpus(
            Path(args.data),
            Path(args.meta),
            Selection(args.select),
            Path(args.out_data),
            Path(args.out_meta),
            Path(args.manifest),
        )
    except (OSError, ValueError) as exc:
        parser.error(str(exc))
    print(json.dumps({
        "input_records": report["input"]["records"],
        "output_records": report["output"]["records"],
        "removed_records": report["removed_records"],
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
