"""Constructed examples only; these do not verify historical data."""

import copy
import hashlib
import json
import unittest

from tests.identity_projection_fixture_verifier import verify_fixture


def encode(obj):
    return json.dumps(obj, sort_keys=True, separators=(",", ":")).encode("utf-8")


def sha(data):
    return hashlib.sha256(data).hexdigest()


def tally(rows, key):
    result = {}
    for row in rows:
        result[row[key]] = result.get(row[key], 0) + 1
    return result


def fixture():
    parts = ("H", "D", "W", "S")
    classes = ("parent", "legal_child", "played_position", "opening_root", "group_membership")
    occurrences = {}
    links = {}
    for p in parts:
        occurrences[p] = [{"id": p + str(i), "source_ref": p + "ref" + str(i), "class": cls,
                           "token": p.lower() + suffix}
                          for i, (cls, suffix) in enumerate(zip(classes, ("parent", "child", "played", "open", "group")))]
        links[p] = [
            {"kind": "parent_child", "from_ref": p + "ref0", "to_ref": p + "ref1", "qualifier": "move"},
            {"kind": "game_position", "from_ref": p + "game1", "to_ref": p + "ref2", "qualifier": "ply0"},
            {"kind": "game_opening", "from_ref": p + "game1", "to_ref": p + "ref3", "qualifier": "open"},
            {"kind": "pair_game", "from_ref": p + "pair", "to_ref": p + "game1", "qualifier": "first"},
            {"kind": "pair_game", "from_ref": p + "pair", "to_ref": p + "game2", "qualifier": "second"},
            {"kind": "game_group", "from_ref": p + "game1", "to_ref": p + "ref4", "qualifier": "member"},
            {"kind": "game_group", "from_ref": p + "game2", "to_ref": p + "ref4", "qualifier": "member"},
        ]
    reference = {p: {"occurrences": occurrences[p], "links": links[p]} for p in parts}
    reference_hash = sha(encode(reference))
    pos = {p.lower() + suffix: p.lower() + suffix for p in parts for suffix in ("parent", "child", "played", "open")}
    pos["dchild"] = "hparent"
    groups = {"hgroup": "sharedgroup", "dgroup": "sharedgroup", "wgroup": "wgroup", "sgroup": "sgroup"}
    spec = {"profile": "identity-spec.fixture.v1", "position_aliases": [{"token": k, "key": v} for k, v in sorted(pos.items())],
            "group_aliases": [{"token": k, "key": v} for k, v in sorted(groups.items())],
            "vectors": [{"space": "position", "left": "hparent", "right": "dchild", "equal": True},
                        {"space": "position", "left": "hparent", "right": "hchild", "equal": False},
                        {"space": "group", "left": "hgroup", "right": "dgroup", "equal": True},
                        {"space": "group", "left": "hgroup", "right": "wgroup", "equal": False}]}
    spec_bytes = encode(spec)
    sources = [{"id": p, "partition": p, "attempt": "attempt" + p, "producer_id": "producer" + p,
                "input_manifest_sha256": sha(("manifest" + p).encode()),
                "cells": [{"class": c, "requirement": "REQUIRED", "basis_ref": "basis" + p + c} for c in classes]}
               for p in parts]
    scope = {"profile": "scope.fixture.v1", "reference_sha256": reference_hash,
             "identity_spec_sha256": sha(spec_bytes), "sources": sources}
    projections = {p: {"profile": "projection.fixture.v1", "source_id": p, "identity_spec_sha256": sha(spec_bytes),
                       "occurrences": occurrences[p], "links": links[p]} for p in parts}
    return encode(scope), spec_bytes, sources, reference_hash, projections


def run(bundle, mutate_bytes=None):
    scope, spec, sources, reference_hash, projections = bundle
    raw = {p: encode(obj) for p, obj in projections.items()}
    receipts = {}
    for source in sources:
        p = source["id"]
        receipt = {"profile": "coverage_receipt.fixture.v1", "source_id": p, "attempt": source["attempt"],
                   "producer_id": source["producer_id"], "input_manifest_sha256": source["input_manifest_sha256"],
                   "reference_sha256": reference_hash, "projection_sha256": sha(raw[p]), "projection_bytes": len(raw[p]),
                   "occurrence_counts": tally(projections[p]["occurrences"], "class"),
                   "link_counts": tally(projections[p]["links"], "kind"), "omissions": 0}
        receipts[p] = encode(receipt)
    if mutate_bytes:
        scope, spec, raw, receipts = mutate_bytes(scope, spec, raw, receipts)
    return json.loads(verify_fixture(scope, spec, raw, receipts))


class FixtureVerifierTests(unittest.TestCase):
    def test_overlap_is_reported_in_both_spaces(self):
        report = run(fixture())
        self.assertEqual(report["status"], "FIXTURE_CONFORMANT")
        self.assertEqual(len(report["intersections"]), 6)
        self.assertEqual(report["intersections"]["H:D"]["positions"]["count"], 1)
        self.assertEqual(report["intersections"]["H:D"]["groups"]["count"], 1)
        self.assertEqual(report["intersections"]["H:W"]["groups"]["count"], 0)

    def test_omission_hidden_by_receipt_rejected(self):
        bundle = fixture()
        bundle[4]["H"]["occurrences"].pop()
        report = run(bundle)
        self.assertEqual(report["status"], "FIXTURE_REJECTED")
        self.assertEqual(report["errors"][0]["code"], "COVERAGE_MISMATCH")
        self.assertIsNone(report["intersections"])

    def test_same_count_substitution_and_incomplete_pair_rejected(self):
        for change in ("substitution", "pair"):
            with self.subTest(change=change):
                bundle = fixture()
                if change == "substitution": bundle[4]["H"]["occurrences"][0]["source_ref"] = "otherref"
                else: bundle[4]["H"]["links"].pop(4)
                self.assertEqual(run(bundle)["errors"][0]["code"], "COVERAGE_MISMATCH")

    def test_non_string_link_field_rejected(self):
        bundle = fixture()
        bundle[4]["H"]["links"][0]["qualifier"] = 4
        report = run(bundle)
        self.assertEqual(report["status"], "FIXTURE_REJECTED")
        self.assertEqual(report["errors"][0]["code"], "INVALID_TOKEN")
        self.assertIsNone(report["intersections"])

    def test_bad_inputs_rejected(self):
        def bad(kind):
            def mutate(scope, spec, projections, receipts):
                if kind == "malformed": scope = b"{"
                if kind == "invalid_utf8": scope = b"\xff"
                if kind == "duplicate": scope = b'{"profile":"x","profile":"y"}'
                if kind == "unknown_field":
                    obj = json.loads(scope); obj["extra"] = 1; scope = encode(obj)
                if kind == "unknown_version":
                    obj = json.loads(scope); obj["profile"] = "scope.fixture.v2"; scope = encode(obj)
                if kind == "hash_mismatch": projections["H"] += b" "
                if kind == "count_form":
                    obj = json.loads(receipts["H"]); obj["omissions"] = False; receipts["H"] = encode(obj)
                return scope, spec, projections, receipts
            return mutate
        for kind in ("malformed", "invalid_utf8", "duplicate", "unknown_field", "unknown_version", "hash_mismatch", "count_form"):
            with self.subTest(kind=kind):
                result = run(fixture(), bad(kind))
                self.assertEqual(result["status"], "FIXTURE_REJECTED")
                self.assertIsNone(result["unions"])

    def test_permutation_preserves_sets_but_changes_input_hash(self):
        original = fixture()
        before = run(original)
        changed = copy.deepcopy(original)
        changed[4]["H"]["occurrences"].reverse()
        after = run(changed)
        self.assertEqual(after["status"], "FIXTURE_CONFORMANT")
        self.assertEqual(before["unions"], after["unions"])
        self.assertEqual(before["intersections"], after["intersections"])
        self.assertNotEqual(before["input_sha256"]["projection:H"], after["input_sha256"]["projection:H"])


if __name__ == "__main__":
    unittest.main()

