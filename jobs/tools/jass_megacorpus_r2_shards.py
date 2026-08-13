#!/usr/bin/env python3
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Build a resumable, adaptively sharded R2 object index without payload reads."""

from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import subprocess
import sys
import time
from typing import Any


SCHEMA = "jass.megacorpus.r2_sharded_census.v1"
CONTROL_NAMES = {
    "manifest.json",
    "inventory.json",
    "checksums.sha256",
    "_SUCCESS",
    "_FAILED",
}


def normalize_path(value: object) -> str:
    if not isinstance(value, str):
        raise ValueError(f"invalid R2 path: {value!r}")
    value = value.replace("\\", "/")
    raw_parts = value.split("/")
    if value.startswith("/") or value.endswith("/") or any(
        part in {"", ".", ".."} for part in raw_parts
    ):
        raise ValueError(f"unsafe R2 path: {value!r}")
    path = PurePosixPath(value)
    if not value or path.is_absolute():
        raise ValueError(f"unsafe R2 path: {value!r}")
    return str(path)


def joined(prefix: str, relative: object) -> str:
    child = normalize_path(relative)
    return normalize_path(f"{prefix}/{child}" if prefix else child)


def shard_name(prefix: str, mode: str) -> str:
    label = prefix or "__root__"
    digest = hashlib.sha256(f"{mode}\0{label}".encode()).hexdigest()[:20]
    return f"{digest}.json.gz"


def atomic_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp-{os.getpid()}-{time.time_ns()}")
    temporary.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(temporary, path)


def write_shard(root: Path, prefix: str, mode: str, items: list[dict[str, Any]]) -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    for item in items:
        if not isinstance(item, dict) or item.get("IsDir") is True:
            continue
        path = joined(prefix, item.get("Path"))
        size = item.get("Size")
        if not isinstance(size, int) or isinstance(size, bool) or size < 0:
            raise ValueError(f"invalid object size for {path}: {size!r}")
        modtime = item.get("ModTime")
        if modtime is not None and not isinstance(modtime, str):
            raise ValueError(f"invalid ModTime for {path}")
        rows.append({"Path": path, "Size": size, "ModTime": modtime})
    rows.sort(key=lambda row: row["Path"])
    name = shard_name(prefix, mode)
    output = root / "shards" / name
    output.parent.mkdir(parents=True, exist_ok=True)
    raw = json.dumps(rows, sort_keys=True, separators=(",", ":")).encode()
    temporary = output.with_name(f".{output.name}.tmp-{os.getpid()}-{time.time_ns()}")
    with gzip.open(temporary, "wb", compresslevel=6) as handle:
        handle.write(raw)
    os.replace(temporary, output)
    return {
        "file": f"shards/{name}",
        "object_count": len(rows),
        "object_bytes": sum(row["Size"] for row in rows),
        "sha256_uncompressed": hashlib.sha256(raw).hexdigest(),
    }


def read_shard(root: Path, descriptor: dict[str, Any]) -> list[dict[str, Any]]:
    path = root / descriptor["file"]
    with gzip.open(path, "rb") as handle:
        raw = handle.read()
    if hashlib.sha256(raw).hexdigest() != descriptor["sha256_uncompressed"]:
        raise ValueError(f"checkpoint shard digest mismatch: {path}")
    rows = json.loads(raw)
    if not isinstance(rows, list):
        raise ValueError(f"checkpoint shard is not a list: {path}")
    return rows


# ⛔ SCRATCH DE JOB, PAS CANDIDAT CORPUS. Les jobs publient leur repertoire de
# travail sur R2 : `work/`, `mini-jass-m13-work/`, `mini-jass-m18-work/`... Ce
# sont des fichiers intermediaires que rien ne consommera jamais, et ce sont eux
# qui faisaient expirer le listing recursif des repertoires de tentative
# (mesure `cpx62-1264` : 34 splits a la profondeur 2, 17 a la profondeur 3, a
# 900 s chacun). Les exclure est une decision de PERIMETRE, pas une optimisation.
SCRATCH_EXCLUDES: tuple[str, ...] = (
    "work/**", "**/work/**", "*-work/**", "**/*-work/**",
)

# ⛔ ELAGUER SUR CE QUE CES REPERTOIRES SONT, PAS SUR LE NOM DU JOB. Ma premiere
# regle ne connaissait que `work` et `*-work` -- calquee sur les 40 prefixes que
# j'avais sous les yeux. Le tueur reel etait
# `.../mini-jass-pattern-baselines/venv/lib`, dont le scratch porte le nom du JOB
# et pas `work` (mesure : `cpx62-1269`, abort a depth 6 sur un `lsjson` de
# virtualenv expire a 90 s -- site-packages, donc des dizaines de milliers de
# fichiers).
#
# Le nommage des scratch n'est pas normalise, donc filtrer par nom de job est une
# course perdue : il y aura toujours un nom non vu. Ces noms-ci sont UNIVERSELS
# et ne sont candidats corpus dans aucun cas de figure.
SCRATCH_SEGMENTS: frozenset[str] = frozenset({
    "work", "venv", ".venv", "site-packages", "node_modules",
    "__pycache__", ".git", "build", ".tox", ".mypy_cache", ".pytest_cache",
})


def is_scratch_prefix(prefix: str) -> bool:
    """Le prefixe EST-IL, ou traverse-t-il, un repertoire de travail de job ?

    ⛔ POURQUOI CETTE FONCTION EXISTE EN PLUS DE `is_job_scratch`. Les motifs
    `--exclude` de rclone sont relatifs a la RACINE DU LISTING. Tant qu'on liste
    `runs/<job>/<attempt>/`, `work/**` matche. Mais le census met `work` en file
    comme prefixe a part entiere, et liste ensuite `runs/<job>/<attempt>/work/` :
    vu de cette racine, le contenu est `attacker-code/...` et PLUS AUCUN motif ne
    matche. L'exclusion au listing etait donc inoperante des qu'on descendait
    dedans -- mesure sur `cpx62-1267`, dont les 136 prefixes en attente etaient
    TOUS sous `work/attacker-code/`, et tous a `max_depth`, ce qui a leve
    `unsplittable census shard failed at depth 6`.

    On elague donc dans la FILE, en Python, ou la semantique est exacte et
    testable, au lieu de la deleguer a des motifs dont la racine bouge.
    """
    if not prefix:
        return False
    return any(
        part in SCRATCH_SEGMENTS or part.endswith("-work")
        for part in PurePosixPath(prefix).parts
    )


def is_job_scratch(path: str) -> bool:
    """Le chemin traverse-t-il un repertoire de travail de job ?

    On teste les segments de REPERTOIRE uniquement (`parts[:-1]`) : un fichier
    nomme `work` n'est pas un repertoire de scratch, et le confondre retirerait
    un objet legitime du catalogue.
    """
    for part in PurePosixPath(path).parts[:-1]:
        if part in SCRATCH_SEGMENTS or part.endswith("-work"):
            return True
    return False


def rclone_json(
    remote: str,
    prefix: str,
    *,
    recursive: bool,
    files_only: bool,
    dirs_only: bool,
    timeout_seconds: int,
    excludes: tuple[str, ...] = (),
) -> list[dict[str, Any]]:
    target = remote.rstrip("/") + (f"/{prefix}" if prefix else "")
    command = ["rclone", "lsjson", target, "--no-mimetype"]
    if recursive:
        command.append("--recursive")
    if files_only:
        command.append("--files-only")
    if dirs_only:
        command.append("--dirs-only")
    for pattern in excludes:
        command.extend(["--exclude", pattern])
    last_error = ""
    for attempt in range(1, 4):
        completed = subprocess.run(
            command,
            check=False,
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
        )
        if completed.returncode == 0:
            try:
                payload = json.loads(completed.stdout)
            except json.JSONDecodeError as exc:
                raise RuntimeError(f"rclone returned invalid JSON for {target}: {exc}") from exc
            if not isinstance(payload, list):
                raise RuntimeError(f"rclone did not return a JSON list for {target}")
            return payload
        last_error = completed.stderr[-1000:]
        if attempt < 3:
            time.sleep(attempt)
    raise RuntimeError(f"rclone rc={completed.returncode} target={target}: {last_error}")


def load_state(root: Path, remote: str, split_depth: int, max_depth: int) -> dict[str, Any]:
    path = root / "state.json"
    if not path.exists():
        return {
            "schema": SCHEMA,
            "remote": remote.rstrip("/"),
            "split_depth": split_depth,
            "max_depth": max_depth,
            "prefixes": {},
        }
    state = json.loads(path.read_text(encoding="utf-8"))
    if (
        state.get("schema") != SCHEMA
        or state.get("remote") != remote.rstrip("/")
        or state.get("split_depth") != split_depth
        or state.get("max_depth") != max_depth
    ):
        raise ValueError("resume checkpoint contract differs from requested census")
    return state


def split_prefix(
    remote: str,
    root: Path,
    prefix: str,
    timeout_seconds: int,
    excludes: tuple[str, ...] = (),
) -> tuple[list[str], dict[str, Any]]:
    files = rclone_json(
        remote, prefix, recursive=False, files_only=True, dirs_only=False,
        timeout_seconds=timeout_seconds, excludes=excludes,
    )
    dirs = rclone_json(
        remote, prefix, recursive=False, files_only=False, dirs_only=True,
        timeout_seconds=timeout_seconds, excludes=excludes,
    )
    children = sorted({joined(prefix, str(item["Path"]).rstrip("/")) for item in dirs})
    direct = write_shard(root, prefix, "direct", files)
    return children, direct


def census(args: argparse.Namespace) -> dict[str, Any]:
    checkpoint = Path(args.checkpoint_dir)
    checkpoint.mkdir(parents=True, exist_ok=True)
    state = load_state(checkpoint, args.remote, args.split_depth, args.max_depth)
    # ⚠️ Les excludes ne font PAS partie du contrat de reprise verifie par
    # `load_state`. C'est deliberé : les 603 prefixes deja indexes par
    # `cpx62-1264` l'ont ete SANS exclusion, et refuser la reprise jetterait ce
    # travail. La coherence du catalogue est assuree ailleurs -- `merge_checkpoint`
    # filtre TOUS les shards, anciens comme nouveaux. L'exclusion au listing
    # n'est qu'une economie de cout ; le filtre au merge est la garantie.
    prune_scratch = bool(getattr(args, "exclude_job_scratch", False))
    excludes = SCRATCH_EXCLUDES if prune_scratch else ()
    state["job_scratch_excluded_at_listing"] = prune_scratch
    state["job_scratch_pruned_from_queue"] = prune_scratch
    queue = [""]
    while queue:
        prefix = queue.pop(0)
        entry = state["prefixes"].get(prefix)
        if entry and entry["state"] == "done":
            continue
        if entry and entry["state"] == "split":
            # ⚠️ Filtrer AUSSI ici : les enfants d'un prefixe deja `split` sont
            # relus du checkpoint, donc un `work/` enregistre par une tentative
            # precedente reviendrait dans la file sans ce test.
            queue.extend(
                child for child in entry["children"]
                if child not in queue
                and not (prune_scratch and is_scratch_prefix(child))
            )
            continue
        depth = 0 if not prefix else len(PurePosixPath(prefix).parts)
        force_split = depth < args.split_depth
        if not force_split:
            try:
                items = rclone_json(
                    args.remote, prefix, recursive=True, files_only=True,
                    dirs_only=False, timeout_seconds=args.shard_timeout_seconds,
                    excludes=excludes,
                )
                descriptor = write_shard(checkpoint, prefix, "recursive", items)
                state["prefixes"][prefix] = {
                    "state": "done", "mode": "recursive", "shard": descriptor,
                }
                atomic_json(checkpoint / "state.json", state)
                print(f"done prefix={prefix or '/'} objects={descriptor['object_count']}", flush=True)
                continue
            except (RuntimeError, subprocess.TimeoutExpired) as exc:
                if depth >= args.max_depth:
                    # ⛔ NE PLUS LEVER. Un seul repertoire recalcitrant detruisait
                    # jusqu'ici des heures de travail acquis (cpx62-1267 : 2h24 et
                    # +195 shards perdus sur un `venv/lib`). On enregistre ce qui
                    # est LISIBLE a ce niveau et on DECLARE le reste comme non
                    # indexe -- un inventaire tronque ne doit jamais pouvoir se
                    # lire comme exhaustif.
                    try:
                        children, direct = split_prefix(
                            args.remote, checkpoint, prefix,
                            args.discovery_timeout_seconds, excludes=excludes,
                        )
                    except (RuntimeError, subprocess.TimeoutExpired) as inner:
                        state["prefixes"][prefix] = {
                            "state": "partial", "mode": "none",
                            "shard": write_shard(checkpoint, prefix, "partial", []),
                            "unindexed_children": [],
                            "reason": f"max-depth listing failed: {inner}",
                        }
                    else:
                        state["prefixes"][prefix] = {
                            "state": "partial", "mode": "direct", "shard": direct,
                            "unindexed_children": children,
                            "reason": f"max-depth recursive listing failed: {exc}",
                        }
                    atomic_json(checkpoint / "state.json", state)
                    print(
                        f"partial prefix={prefix or '/'} depth={depth} "
                        f"unindexed_children="
                        f"{len(state['prefixes'][prefix]['unindexed_children'])}",
                        flush=True,
                    )
                    continue
                print(f"split-after-failure prefix={prefix or '/'} reason={exc}", flush=True)
        children, direct = split_prefix(
            args.remote, checkpoint, prefix, args.discovery_timeout_seconds,
            excludes=excludes,
        )
        if children:
            state["prefixes"][prefix] = {
                "state": "split", "mode": "direct", "shard": direct,
                "children": children,
            }
        else:
            state["prefixes"][prefix] = {
                "state": "done", "mode": "direct", "shard": direct,
            }
        atomic_json(checkpoint / "state.json", state)
        queue.extend(
            child for child in children
            if not (prune_scratch and is_scratch_prefix(child))
        )
        print(
            f"{'split' if children else 'done-direct'} prefix={prefix or '/'} "
            f"direct={direct['object_count']} children={len(children)}",
            flush=True,
        )
    return merge_checkpoint(
        checkpoint, Path(args.object_index), Path(args.metadata_files),
        exclude_job_scratch=bool(getattr(args, "exclude_job_scratch", False)),
    )


def is_control_metadata(path: str) -> bool:
    parts = PurePosixPath(path).parts
    if len(parts) >= 4 and parts[0] == "runs" and parts[-1] in CONTROL_NAMES:
        return True
    if parts and parts[0] == "historical":
        lower = path.lower()
        return lower.endswith(".json") or lower.endswith("/manifests/paths.jsonl.gz")
    return False


def merge_checkpoint(
    root: Path, object_index: Path, metadata_files: Path,
    exclude_job_scratch: bool = False,
) -> dict[str, Any]:
    state = json.loads((root / "state.json").read_text(encoding="utf-8"))
    rows: list[dict[str, Any]] = []
    seen_shards: set[str] = set()
    for entry in state["prefixes"].values():
        descriptor = entry.get("shard")
        if not descriptor or descriptor["file"] in seen_shards:
            continue
        seen_shards.add(descriptor["file"])
        rows.extend(read_shard(root, descriptor))
    # ⛔ LE FILTRE PORTE SUR TOUS LES SHARDS, pas seulement ceux listes apres
    # l'ajout des excludes. Sans ca le catalogue melangerait des shards anciens
    # CONTENANT le scratch et des shards recents SANS lui -- une incoherence
    # invisible qui polluerait la liste des candidats corpus.
    scratch = 0
    if exclude_job_scratch:
        kept = [row for row in rows if not is_job_scratch(row["Path"])]
        scratch = len(rows) - len(kept)
        rows = kept
    rows.sort(key=lambda row: row["Path"])
    paths = [row["Path"] for row in rows]
    if len(paths) != len(set(paths)):
        raise ValueError("sharded R2 census contains duplicate object paths")
    object_index.parent.mkdir(parents=True, exist_ok=True)
    object_index.write_text(json.dumps(rows, separators=(",", ":")), encoding="utf-8")
    controls = [path for path in paths if is_control_metadata(path)]
    metadata_files.write_text("".join(f"{path}\n" for path in controls), encoding="utf-8")
    summary = {
        "schema": SCHEMA,
        "object_count": len(rows),
        "object_bytes": sum(row["Size"] for row in rows),
        "checkpoint_shard_count": len(seen_shards),
        "metadata_object_count": len(controls),
        "job_scratch_objects_excluded": scratch,
        "job_scratch_filter_applied": bool(exclude_job_scratch),
        "completed_prefix_count": sum(
            entry["state"] == "done" for entry in state["prefixes"].values()
        ),
        "split_prefix_count": sum(
            entry["state"] == "split" for entry in state["prefixes"].values()
        ),
        # ⛔ SANS CE COMPTEUR, UN INVENTAIRE TRONQUE SE LIT COMME EXHAUSTIF.
        "partial_prefix_count": sum(
            entry["state"] == "partial" for entry in state["prefixes"].values()
        ),
        "unindexed_child_count": sum(
            len(entry.get("unindexed_children", []))
            for entry in state["prefixes"].values()
            if entry["state"] == "partial"
        ),
        "census_is_exhaustive": not any(
            entry["state"] == "partial" for entry in state["prefixes"].values()
        ),
    }
    atomic_json(root / "summary.json", summary)
    return summary


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--remote", required=True)
    parser.add_argument("--checkpoint-dir", required=True)
    parser.add_argument("--object-index", required=True)
    parser.add_argument("--metadata-files", required=True)
    parser.add_argument("--split-depth", type=int, default=2)
    parser.add_argument("--max-depth", type=int, default=6)
    parser.add_argument("--shard-timeout-seconds", type=int, default=900)
    parser.add_argument("--discovery-timeout-seconds", type=int, default=300)
    parser.add_argument(
        "--exclude-job-scratch", action="store_true",
        help="ignore job work directories at listing AND at merge",
    )
    args = parser.parse_args(argv)
    if not (1 <= args.split_depth < args.max_depth <= 12):
        parser.error("require 1 <= split-depth < max-depth <= 12")
    try:
        summary = census(args)
    except (OSError, ValueError, RuntimeError, subprocess.TimeoutExpired) as exc:
        print(f"jass_megacorpus_r2_shards: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(summary, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
