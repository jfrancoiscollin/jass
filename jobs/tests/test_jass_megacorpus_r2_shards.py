# SPDX-License-Identifier: AGPL-3.0-or-later
from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest import mock


ROOT = Path(__file__).resolve().parents[2]
TOOL = ROOT / "jobs" / "tools" / "jass_megacorpus_r2_shards.py"
SPEC = importlib.util.spec_from_file_location("jass_megacorpus_r2_shards", TOOL)
assert SPEC is not None and SPEC.loader is not None
SHARDS = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(SHARDS)


class MegaCorpusR2ShardsTest(unittest.TestCase):
    def test_merge_is_complete_deduplicated_and_metadata_only(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            a = SHARDS.write_shard(root, "runs/job-a", "recursive", [
                {"Path": "attempt/manifest.json", "Size": 10, "ModTime": "2026-01-01Z"},
                {"Path": "attempt/artefacts/data.jnnw.gz", "Size": 1000, "ModTime": "2026-01-01Z"},
            ])
            b = SHARDS.write_shard(root, "historical/snap", "recursive", [
                {"Path": "manifests/paths.jsonl.gz", "Size": 20, "ModTime": "2026-01-01Z"},
            ])
            SHARDS.atomic_json(root / "state.json", {
                "schema": SHARDS.SCHEMA, "remote": "r2:jass-data",
                "split_depth": 2, "max_depth": 6,
                "prefixes": {"runs/job-a": {"state": "done", "shard": a},
                             "historical/snap": {"state": "done", "shard": b}},
            })
            index = root / "index.json"; metadata = root / "metadata.txt"
            summary = SHARDS.merge_checkpoint(root, index, metadata)
            rows = json.loads(index.read_text())
            self.assertEqual(summary["object_count"], 3)
            self.assertEqual(len({row["Path"] for row in rows}), 3)
            selected = metadata.read_text().splitlines()
            self.assertIn("runs/job-a/attempt/manifest.json", selected)
            self.assertIn("historical/snap/manifests/paths.jsonl.gz", selected)
            self.assertNotIn("runs/job-a/attempt/artefacts/data.jnnw.gz", selected)

    def test_checkpoint_digest_tamper_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            descriptor = SHARDS.write_shard(root, "runs/a", "recursive", [
                {"Path": "b/manifest.json", "Size": 1, "ModTime": None},
            ])
            descriptor["sha256_uncompressed"] = "0" * 64
            with self.assertRaisesRegex(ValueError, "digest mismatch"):
                SHARDS.read_shard(root, descriptor)

    def test_paths_reject_traversal(self) -> None:
        for path in ("../payload.jnnw", "/payload.jnnw", "payload/", "a//payload"):
            with self.subTest(path=path), self.assertRaisesRegex(ValueError, "unsafe"):
                SHARDS.normalize_path(path)

    def test_timeout_splits_and_completed_checkpoint_resumes_without_relisting(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            index = root / "index.json"
            metadata = root / "metadata.txt"
            args = SHARDS.argparse.Namespace(
                checkpoint_dir=str(root / "checkpoint"), remote="r2:jass-data",
                object_index=str(index), metadata_files=str(metadata),
                split_depth=1, max_depth=3, shard_timeout_seconds=60,
                discovery_timeout_seconds=60,
            )

            def listing(remote, prefix, *, recursive, files_only, dirs_only,
                        timeout_seconds, excludes=()):
                del remote, timeout_seconds, excludes
                if prefix == "" and files_only:
                    return [{"Path": "root.json", "Size": 1, "ModTime": None}]
                if prefix == "" and dirs_only:
                    return [{"Path": "runs/", "IsDir": True}]
                if prefix == "runs" and recursive:
                    raise SHARDS.subprocess.TimeoutExpired("rclone", 60)
                if prefix == "runs" and files_only:
                    return []
                if prefix == "runs" and dirs_only:
                    return [{"Path": "job-a", "IsDir": True}]
                if prefix == "runs/job-a" and recursive:
                    return [{"Path": "attempt/manifest.json", "Size": 9, "ModTime": None}]
                raise AssertionError((prefix, recursive, files_only, dirs_only))

            with mock.patch.object(SHARDS, "rclone_json", side_effect=listing):
                summary = SHARDS.census(args)
            self.assertEqual(summary["object_count"], 2)
            self.assertEqual(summary["split_prefix_count"], 2)
            self.assertEqual(summary["completed_prefix_count"], 1)
            self.assertEqual(metadata.read_text().splitlines(), [
                "runs/job-a/attempt/manifest.json"
            ])

            with mock.patch.object(
                SHARDS, "rclone_json", side_effect=AssertionError("resume relisted R2")
            ):
                resumed = SHARDS.census(args)
            self.assertEqual(resumed, summary)

    def test_timeout_on_leaf_finishes_from_nonrecursive_listing(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            args = SHARDS.argparse.Namespace(
                checkpoint_dir=str(root / "checkpoint"), remote="r2:jass-data",
                object_index=str(root / "index.json"),
                metadata_files=str(root / "metadata.txt"), split_depth=1,
                max_depth=3, shard_timeout_seconds=60, discovery_timeout_seconds=60,
            )

            def listing(remote, prefix, *, recursive, files_only, dirs_only,
                        timeout_seconds, excludes=()):
                del remote, timeout_seconds, excludes
                if prefix == "" and files_only:
                    return []
                if prefix == "" and dirs_only:
                    return [{"Path": "leaf", "IsDir": True}]
                if prefix == "leaf" and recursive:
                    raise SHARDS.subprocess.TimeoutExpired("rclone", 60)
                if prefix == "leaf" and files_only:
                    return [{"Path": "data.jnnw.gz", "Size": 42, "ModTime": None}]
                if prefix == "leaf" and dirs_only:
                    return []
                raise AssertionError((prefix, recursive, files_only, dirs_only))

            with mock.patch.object(SHARDS, "rclone_json", side_effect=listing):
                summary = SHARDS.census(args)
            self.assertEqual(summary["object_count"], 1)
            self.assertEqual(summary["completed_prefix_count"], 1)

    def test_job_scratch_is_a_directory_rule_not_a_name_rule(self) -> None:
        """Un REPERTOIRE `work/` est du scratch ; un FICHIER `work` ne l'est pas.

        Confondre les deux retirerait du catalogue un objet legitime, ce qu'aucun
        compteur ne signalerait ensuite.
        """
        for path in ("runs/j/a/work/tmp.bin", "runs/j/a/mini-jass-m13-work/x.json",
                     "runs/j/a/b/work/deep/y.npy"):
            with self.subTest(path=path):
                self.assertTrue(SHARDS.is_job_scratch(path))
        for path in ("runs/j/a/artefacts/result.json", "runs/j/a/geom/mesh.bin",
                     "runs/j/a/artefacts/work", "runs/j/a/network/model.bin",
                     "runs/j/a/homework/x", "corpora/jnnw/shard-0001.jnnw"):
            with self.subTest(path=path):
                self.assertFalse(SHARDS.is_job_scratch(path))

    def test_merge_filters_scratch_from_shards_listed_BEFORE_the_exclusion(self) -> None:
        """La coherence du catalogue ne peut pas dependre de la date du shard.

        `cpx62-1264` a indexe 603 prefixes SANS exclusion ; la reprise en ajoute
        avec. Si le filtre ne portait que sur les nouveaux shards, le catalogue
        melangerait les deux regimes sans que rien ne le dise.
        """
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            old = SHARDS.write_shard(root, "runs/j/a", "recursive", [
                {"Path": "work/tmp.bin", "Size": 10, "ModTime": None},
                {"Path": "artefacts/manifest.json", "Size": 10, "ModTime": None},
            ])
            new = SHARDS.write_shard(root, "runs/k/b", "recursive", [
                {"Path": "artefacts/inventory.json", "Size": 20, "ModTime": None},
            ])
            SHARDS.atomic_json(root / "state.json", {
                "schema": SHARDS.SCHEMA, "remote": "r2:jass-data",
                "split_depth": 2, "max_depth": 6,
                "prefixes": {"runs/j/a": {"state": "done", "shard": old},
                             "runs/k/b": {"state": "done", "shard": new}},
            })
            summary = SHARDS.merge_checkpoint(
                root, root / "index.json", root / "metadata.txt",
                exclude_job_scratch=True,
            )
            paths = [row["Path"] for row in json.loads((root / "index.json").read_text())]
            self.assertNotIn("runs/j/a/work/tmp.bin", paths)
            self.assertEqual(summary["object_count"], 2)
            self.assertEqual(summary["job_scratch_objects_excluded"], 1)
            self.assertIs(summary["job_scratch_filter_applied"], True)

    def test_without_the_flag_the_catalogue_is_unchanged(self) -> None:
        """Le defaut reste le comportement historique : aucun retrait silencieux."""
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            shard = SHARDS.write_shard(root, "runs/j/a", "recursive", [
                {"Path": "work/tmp.bin", "Size": 10, "ModTime": None},
                {"Path": "artefacts/manifest.json", "Size": 10, "ModTime": None},
            ])
            SHARDS.atomic_json(root / "state.json", {
                "schema": SHARDS.SCHEMA, "remote": "r2:jass-data",
                "split_depth": 2, "max_depth": 6,
                "prefixes": {"runs/j/a": {"state": "done", "shard": shard}},
            })
            summary = SHARDS.merge_checkpoint(
                root, root / "index.json", root / "metadata.txt")
            self.assertEqual(summary["object_count"], 2)
            self.assertEqual(summary["job_scratch_objects_excluded"], 0)
            self.assertIs(summary["job_scratch_filter_applied"], False)

    def test_scratch_children_are_pruned_from_the_queue_not_just_excluded(self) -> None:
        """⛔ Les motifs `--exclude` de rclone sont relatifs a la RACINE DU
        LISTING. Une fois le census descendu DANS `work/`, plus aucun motif ne
        matche -- mesure sur cpx62-1267, dont les 136 prefixes en attente etaient
        tous sous `work/attacker-code/` et tous a `max_depth`, ce qui a leve
        `unsplittable census shard failed at depth 6`. L'elagage doit donc se
        faire dans la FILE, pas par motif.
        """
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            args = SHARDS.argparse.Namespace(
                checkpoint_dir=str(root / "checkpoint"), remote="r2:jass-data",
                object_index=str(root / "index.json"),
                metadata_files=str(root / "metadata.txt"), split_depth=1,
                max_depth=3, shard_timeout_seconds=60, discovery_timeout_seconds=60,
                exclude_job_scratch=True,
            )
            visited: list[str] = []

            def listing(remote, prefix, *, recursive, files_only, dirs_only,
                        timeout_seconds, excludes=()):
                del remote, timeout_seconds, excludes
                visited.append(prefix)
                if prefix == "" and files_only:
                    return []
                if prefix == "" and dirs_only:
                    return [{"Path": "runs", "IsDir": True}]
                if prefix == "runs" and recursive:
                    raise SHARDS.subprocess.TimeoutExpired("rclone", 60)
                if prefix == "runs" and files_only:
                    return []
                if prefix == "runs" and dirs_only:
                    return [{"Path": "work", "IsDir": True},
                            {"Path": "artefacts", "IsDir": True}]
                if prefix == "runs/artefacts" and recursive:
                    return [{"Path": "manifest.json", "Size": 5, "ModTime": None}]
                raise AssertionError(("le census a visite un prefixe elague", prefix))

            with mock.patch.object(SHARDS, "rclone_json", side_effect=listing):
                summary = SHARDS.census(args)
            self.assertNotIn("runs/work", visited)
            self.assertIn("runs/artefacts", visited)
            self.assertEqual(summary["object_count"], 1)

    def test_scratch_children_recorded_by_an_EARLIER_attempt_stay_pruned(self) -> None:
        """Un `work/` enregistre dans les enfants d'un prefixe deja `split`
        reviendrait dans la file a la reprise sans un second filtre."""
        with tempfile.TemporaryDirectory() as td:
            root = Path(td) / "checkpoint"
            root.mkdir(parents=True)
            direct = SHARDS.write_shard(root, "runs", "direct", [])
            SHARDS.atomic_json(root / "state.json", {
                "schema": SHARDS.SCHEMA, "remote": "r2:jass-data",
                "split_depth": 1, "max_depth": 3,
                "prefixes": {
                    "": {"state": "split", "mode": "direct",
                         "shard": SHARDS.write_shard(root, "", "direct", []),
                         "children": ["runs"]},
                    "runs": {"state": "split", "mode": "direct", "shard": direct,
                             "children": ["runs/work", "runs/artefacts"]},
                },
            })
            args = SHARDS.argparse.Namespace(
                checkpoint_dir=str(root), remote="r2:jass-data",
                object_index=str(Path(td) / "index.json"),
                metadata_files=str(Path(td) / "metadata.txt"), split_depth=1,
                max_depth=3, shard_timeout_seconds=60, discovery_timeout_seconds=60,
                exclude_job_scratch=True,
            )

            def listing(remote, prefix, *, recursive, files_only, dirs_only,
                        timeout_seconds, excludes=()):
                del remote, timeout_seconds, excludes, files_only, dirs_only
                if prefix == "runs/artefacts" and recursive:
                    return [{"Path": "manifest.json", "Size": 5, "ModTime": None}]
                raise AssertionError(("prefixe elague revisite a la reprise", prefix))

            with mock.patch.object(SHARDS, "rclone_json", side_effect=listing):
                summary = SHARDS.census(args)
            self.assertEqual(summary["object_count"], 1)

    def test_scratch_rule_is_about_WHAT_not_about_the_job_name(self) -> None:
        """Ma premiere regle ne connaissait que `work`/`*-work`, calquee sur les
        40 prefixes que j'avais sous les yeux. Le tueur reel de cpx62-1269 etait
        `.../mini-jass-pattern-baselines/venv/lib` : un scratch nomme d'apres le
        JOB. Le nommage n'est pas normalise, donc la regle porte desormais sur des
        noms UNIVERSELS."""
        for prefix in ("runs/j/a/venv", "runs/j/a/x/venv/lib",
                       "runs/j/a/venv/lib/python3.11/site-packages",
                       "runs/j/a/build", "runs/j/a/node_modules",
                       "runs/j/a/__pycache__", "runs/j/a/.git",
                       "runs/j/a/work", "runs/j/a/mini-jass-m13-work"):
            with self.subTest(prefix=prefix):
                self.assertTrue(SHARDS.is_scratch_prefix(prefix))
        for prefix in ("", "corpora", "runs/j/a/artefacts", "runs/j/a/geom",
                       "runs/j/a/network", "runs/j/a/homework", "runs/j/a/rebuild"):
            with self.subTest(prefix=prefix):
                self.assertFalse(SHARDS.is_scratch_prefix(prefix))

    def test_an_unsplittable_prefix_is_PARTIAL_and_declared_not_fatal(self) -> None:
        """⛔ Un seul repertoire recalcitrant detruisait des heures acquises
        (cpx62-1267 : 2h24 et +195 shards perdus). Il doit desormais etre
        enregistre, compte, et surtout DECLARE -- un inventaire tronque ne doit
        jamais pouvoir se lire comme exhaustif."""
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            args = SHARDS.argparse.Namespace(
                checkpoint_dir=str(root / "checkpoint"), remote="r2:jass-data",
                object_index=str(root / "index.json"),
                metadata_files=str(root / "metadata.txt"), split_depth=1,
                max_depth=1, shard_timeout_seconds=60, discovery_timeout_seconds=60,
            )

            def listing(remote, prefix, *, recursive, files_only, dirs_only,
                        timeout_seconds, excludes=()):
                del remote, timeout_seconds, excludes
                if prefix == "" and files_only:
                    return []
                if prefix == "" and dirs_only:
                    return [{"Path": "stubborn", "IsDir": True}]
                # A max_depth le recursif expire, mais le listing PLAT passe.
                if prefix == "stubborn" and recursive:
                    raise SHARDS.subprocess.TimeoutExpired("rclone", 60)
                if prefix == "stubborn" and files_only:
                    return [{"Path": "manifest.json", "Size": 7, "ModTime": None}]
                if prefix == "stubborn" and dirs_only:
                    return [{"Path": "deeper", "IsDir": True}]
                raise AssertionError((prefix, recursive, files_only, dirs_only))

            with mock.patch.object(SHARDS, "rclone_json", side_effect=listing):
                summary = SHARDS.census(args)

            # Le census SURVIT, garde ce qui etait lisible, et le declare.
            self.assertEqual(summary["partial_prefix_count"], 1)
            self.assertEqual(summary["unindexed_child_count"], 1)
            self.assertIs(summary["census_is_exhaustive"], False)
            self.assertEqual(summary["object_count"], 1)
            self.assertEqual(
                json.loads((root / "index.json").read_text())[0]["Path"],
                "stubborn/manifest.json",
            )

    def test_a_complete_census_declares_itself_exhaustive(self) -> None:
        """Le pendant du test precedent : sans partiel, le drapeau doit dire OUI,
        sinon `census_is_exhaustive` ne vaudrait rien comme information."""
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            args = SHARDS.argparse.Namespace(
                checkpoint_dir=str(root / "checkpoint"), remote="r2:jass-data",
                object_index=str(root / "index.json"),
                metadata_files=str(root / "metadata.txt"), split_depth=1,
                max_depth=3, shard_timeout_seconds=60, discovery_timeout_seconds=60,
            )

            def listing(remote, prefix, *, recursive, files_only, dirs_only,
                        timeout_seconds, excludes=()):
                del remote, timeout_seconds, excludes
                if prefix == "" and files_only:
                    return []
                if prefix == "" and dirs_only:
                    return [{"Path": "runs", "IsDir": True}]
                if prefix == "runs" and recursive:
                    return [{"Path": "a/manifest.json", "Size": 3, "ModTime": None}]
                raise AssertionError(prefix)

            with mock.patch.object(SHARDS, "rclone_json", side_effect=listing):
                summary = SHARDS.census(args)
            self.assertEqual(summary["partial_prefix_count"], 0)
            self.assertIs(summary["census_is_exhaustive"], True)


if __name__ == "__main__":
    unittest.main()
