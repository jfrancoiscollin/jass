from __future__ import annotations
import os, struct, tempfile, unittest
import hashlib
import gzip
import time
from pathlib import Path
from unittest import mock

from jobs.tools import ed4_c0c_exact_linkage_diagnostic as subject
from jobs.tools import ed4_c0c_exact_linkage_diagnostic_stage as stage


def jnnw(prefixes: list[bytes]) -> bytes:
    return b"JNNW" + struct.pack("<I", len(prefixes)) + b"".join(p + b"SECRET"[:5] for p in prefixes)


def prefix(wm: int, stm: int = 0) -> bytes:
    return struct.pack("<QQQQB", wm, 0, 0, 0, stm)


class ExactLinkageTests(unittest.TestCase):
    def schema(self, **changes):
        value = dict(columns=("row_index", "parent_id", "child_canonical", "target"),
                     allowed_fields=frozenset({"row_index", "parent_id", "child_canonical"}),
                     expected_rows=2, parent_count=2, parent_child_counts=(1, 1))
        value.update(changes)
        return subject.TsvSchema(**value)

    def test_selective_reader_never_decodes_forbidden_sentinel(self):
        ledger = subject.SemanticReadLedger()
        first, second = prefix(1), prefix(2)
        rows = subject.selective_tsv_rows(b"row_index\tparent_id\tchild_canonical\ttarget\n0\t0\t" + subject.canonical_fingerprint(subject.prefix_fingerprint(first)).encode() + b"\tFORBIDDEN-TARGET\n1\t1\t" + subject.canonical_fingerprint(subject.prefix_fingerprint(second)).encode() + b"\tFORBIDDEN-TARGET\n", self.schema(), ledger)
        self.assertEqual(rows[0]["child_canonical"], subject.canonical_fingerprint(subject.prefix_fingerprint(first)))
        self.assertNotIn("target", rows[0])
        self.assertEqual(ledger.forbidden_field_values_read, 0)
        self.assertEqual(ledger.structural_field_values_read, 6)

    def test_header_column_count_unknown_schema_and_row_order_fail_closed(self):
        ledger = subject.SemanticReadLedger()
        with self.assertRaisesRegex(subject.ExactLinkageError, "header_drift"):
            subject.selective_tsv_rows(b"row_index\tparent_id\tunknown\ttarget\n", self.schema(), ledger)
        with self.assertRaisesRegex(subject.ExactLinkageError, "column_count"):
            subject.selective_tsv_rows(b"row_index\tparent_id\tchild_canonical\ttarget\n0\t0\tbad\n", self.schema(), ledger)
        with self.assertRaisesRegex(subject.ExactLinkageError, "row_index"):
            subject.selective_tsv_rows(b"row_index\tparent_id\tchild_canonical\ttarget\n1\t0\tbad\tx\n0\t1\tbad\tx\n", self.schema(), ledger)

    def test_jnnw_exact_geometry_and_target_slots_are_not_interpreted(self):
        ledger = subject.SemanticReadLedger(); payload = jnnw([prefix(1), prefix(2)])
        self.assertEqual(subject.jnnw_prefixes(payload, 2, ledger), (prefix(1), prefix(2)))
        with self.assertRaisesRegex(subject.ExactLinkageError, "geometry"):
            subject.jnnw_prefixes(payload + b"x", 2, ledger)

    def test_hash_drift_and_novel_or_missing_manifest_rows_fail_closed(self):
        ledger = subject.SemanticReadLedger(); raw = b"opaque payload"
        subject.require_exact_sha256(raw, subject.opaque_sha256(raw, subject.SemanticReadLedger()), ledger)
        with self.assertRaisesRegex(subject.ExactLinkageError, "hash_drift"):
            subject.require_exact_sha256(raw, "0" * 64, ledger)
        expected = (("job", "attempt", "path", "kind", "sha", "1", "outcome"),)
        with self.assertRaisesRegex(subject.ExactLinkageError, "novel_descriptor_row"):
            subject.require_exact_descriptor_rows(expected, (("job", "attempt", "other", "kind", "sha", "1", "outcome"),))
        with self.assertRaisesRegex(subject.ExactLinkageError, "cardinality"):
            subject.require_exact_descriptor_rows(expected, ())

    def test_child_parent_geometry_and_permutation_fail_closed(self):
        ledger = subject.SemanticReadLedger(); schema = self.schema()
        first, second = prefix(1), prefix(2)
        data = b"row_index\tparent_id\tchild_canonical\ttarget\n0\t0\t" + subject.canonical_fingerprint(subject.prefix_fingerprint(first)).encode() + b"\tx\n1\t1\t" + subject.canonical_fingerprint(subject.prefix_fingerprint(second)).encode() + b"\tx\n"
        rows = subject.selective_tsv_rows(data, schema, ledger)
        result = subject.validate_child_linkage(rows, schema, [first, second], ledger)
        self.assertEqual(result["linked_rows"], 2)
        with self.assertRaisesRegex(subject.ExactLinkageError, "prefix_mismatch"):
            subject.validate_child_linkage(rows, schema, [second, first], ledger)
        bad_rows = (dict(rows[0]), dict(rows[1], parent_id="0"))
        with self.assertRaisesRegex(subject.ExactLinkageError, "parent_child_geometry"):
            subject.validate_child_linkage(bad_rows, schema, [first, second], ledger)

    def test_stage_needs_manifest_and_never_calls_builder(self):
        with tempfile.TemporaryDirectory() as td, mock.patch.dict(os.environ, {"JASS_ARTEFACT_DIR": str(Path(td) / "a"), "LAUNCH_MODE": "rehearsal"}, clear=False):
            self.assertEqual(stage.main(), 2)


class FullSyntheticEvidenceTests(unittest.TestCase):
    """A 21-row/4-schema fixture with poison only in forbidden TSV cells."""
    def make_fixture(self):
        payloads = {}; failures = []; schemas = {}; cases = []
        parents = jnnw([prefix(1)]); children = jnnw([prefix(2, 1)])
        parent_raw = subject.prefix_fingerprint(prefix(1)); child_raw = subject.prefix_fingerprint(prefix(2, 1))
        kinds = [
            ("b2", ("row_index", "parent_id", "parent_fingerprint", "parent_stm", "target"), ("row_index", "parent_id", "parent_fingerprint", "parent_stm"), 3),
            ("home", ("row_index", "sibling_identity", "parent_id", "parent_canonical", "parent_fingerprint", "parent_stm", "child_fingerprint", "child_canonical", "target"), ("row_index", "sibling_identity", "parent_id", "parent_canonical", "parent_fingerprint", "parent_stm", "child_fingerprint", "child_canonical"), 3),
            ("p0", ("row_index", "sibling_identity", "child_fingerprint", "parent_id", "parent_stm", "target"), ("row_index", "sibling_identity", "child_fingerprint", "parent_id", "parent_stm"), 7),
            ("confirmation", ("row_index", "sibling_identity", "child_fingerprint", "parent_id", "parent_stm", "target"), ("row_index", "sibling_identity", "child_fingerprint", "parent_id", "parent_stm"), 2),
        ]
        for case_id, columns, allowed, aliases_n in kinds:
            schemas[case_id] = {"columns": list(columns), "allowed_fields": list(allowed),
                                "header_canonical_sha256":hashlib.sha256(subject._canonical(list(columns))).hexdigest()}
            values = {"row_index":"0", "parent_id":"0", "parent_fingerprint":parent_raw, "parent_canonical":subject.canonical_fingerprint(parent_raw), "parent_stm":"0", "child_fingerprint":child_raw, "child_canonical":subject.canonical_fingerprint(child_raw), "sibling_identity":case_id + ":0", "target":"FORBIDDEN-TARGET-POISON"}
            raw = ("\t".join(columns) + "\n" + "\t".join(values[x] for x in columns) + "\n").encode()
            aliases=[]
            for n in range(aliases_n):
                row={"job_id":f"job-{case_id}-{n}","attempt_id":"a","path":"groups.tsv","kind":"groups_tsv","sha256":hashlib.sha256(raw).hexdigest(),"size_bytes":len(raw)}
                payloads[subject.descriptor_key(row)] = raw; aliases.append(row); failures.append(row)
            compressed = case_id == "home"; parent_bytes=gzip.compress(parents) if compressed else parents; child_bytes=gzip.compress(children) if compressed else children
            par={"job_id":f"comp-{case_id}","attempt_id":"a","path":"parents.jnnw"+(".gz" if compressed else ""),"sha256":hashlib.sha256(parent_bytes).hexdigest(),"size_bytes":len(parent_bytes),"compression":"gzip" if compressed else "none"}
            chi={"job_id":f"comp-{case_id}","attempt_id":"a","path":"children.jnnw"+(".gz" if compressed else ""),"sha256":hashlib.sha256(child_bytes).hexdigest(),"size_bytes":len(child_bytes),"compression":"gzip" if compressed else "none"}
            payloads[subject.descriptor_key(par)]=parent_bytes; payloads[subject.descriptor_key(chi)]=child_bytes
            cases.append({"case_id":case_id,"schema_id":case_id,"aliases":aliases,"representative":aliases[0],"tsv_sha256":hashlib.sha256(raw).hexdigest(),"expected_data_rows":1,"expected_parent_count":1,"parents":par,"children":chi})
        comment=b"# comment only\n"
        comments=[]
        for n in range(3):
            row={"job_id":f"fen-{n}","attempt_id":"a","path":"x.fen","kind":"fen","sha256":hashlib.sha256(comment).hexdigest(),"size_bytes":len(comment)}; payloads[subject.descriptor_key(row)]=comment; comments.append(row); failures.append(row)
        invalid=jnnw([prefix(1,2)]); invalids=[]
        for n in range(3):
            row={"job_id":f"bad-{n}","attempt_id":"a","path":"x.jnnw","kind":"jnnw","sha256":hashlib.sha256(invalid).hexdigest(),"size_bytes":len(invalid)}; payloads[subject.descriptor_key(row)]=invalid; invalids.append(row); failures.append(row)
        manifest={"schema":"jass.ed4.c0c_exact_linkage_manifest.v1","failure_rows":failures,"schemas":schemas,"tsv_cases":cases,"comment_only":{"aliases":comments},"invalid_stm":{"aliases":invalids,"declared_count":1,"complete_coverage_proof":None,"recovery_authorized":False}}
        return manifest,payloads

    def test_full_21_row_four_schema_evidence_is_blocked_and_target_blind(self):
        manifest,payloads=self.make_fixture()
        result=subject.build_synthetic_diagnostic(manifest,payloads)
        self.assertEqual(len(result["recovery_evidence"]),21)
        self.assertEqual(result["terminal"],"ED4_C0C_V7_BLOCKED_BY_INCOMPLETE_STRUCTURAL_COVERAGE")
        self.assertEqual(sum(x["evidence"]=="exact-tsv-child-linkage-proven" for x in result["recovery_evidence"]),15)
        self.assertEqual(result["read_ledger"]["forbidden_field_values_read"],0)
        self.assertNotIn("FORBIDDEN-TARGET-POISON",str(result))

    def test_full_fixture_rejects_alias_drift_missing_and_parent_or_stm_drift(self):
        manifest,payloads=self.make_fixture(); key=subject.descriptor_key(manifest["tsv_cases"][0]["aliases"][1]); payloads[key]=b"drift"
        with self.assertRaisesRegex(subject.ExactLinkageError,"payload_size_drift"): subject.build_synthetic_diagnostic(manifest,payloads)
        manifest,payloads=self.make_fixture(); del payloads[subject.descriptor_key(manifest["failure_rows"][0])]
        with self.assertRaisesRegex(subject.ExactLinkageError,"descriptor_set"): subject.build_synthetic_diagnostic(manifest,payloads)
        manifest,payloads=self.make_fixture(); case=manifest["tsv_cases"][0]; key=subject.descriptor_key(case["representative"]); payloads[key]=payloads[key].replace(b"\t0\tFORBIDDEN",b"\t1\tFORBIDDEN")
        with self.assertRaises(subject.ExactLinkageError): subject.build_synthetic_diagnostic(manifest,payloads)

    def test_gzip_hash_drift_deadline_and_extra_payload_fail_closed(self):
        manifest,payloads=self.make_fixture(); home=manifest["tsv_cases"][1]; key=subject.descriptor_key(home["parents"])
        raw=payloads[key]; payloads[key]=raw[:-1]+bytes([raw[-1]^1])
        with self.assertRaisesRegex(subject.ExactLinkageError,"hash_drift"): subject.build_synthetic_diagnostic(manifest,payloads)
        manifest,payloads=self.make_fixture()
        with self.assertRaisesRegex(subject.ExactLinkageError,"deadline"): subject.build_synthetic_diagnostic(manifest,payloads,deadline=0.0)
        manifest,payloads=self.make_fixture(); payloads[("novel","a","x")]=b"x"
        with self.assertRaisesRegex(subject.ExactLinkageError,"descriptor_set"): subject.build_synthetic_diagnostic(manifest,payloads)

    def test_parent_blocks_siblings_raw_canonical_and_stm_are_strict(self):
        schema=subject.TsvSchema(("row_index","sibling_identity","parent_id","parent_fingerprint","parent_canonical","parent_stm"),frozenset({"row_index","sibling_identity","parent_id","parent_fingerprint","parent_canonical","parent_stm"}),2,2)
        p0,p1=prefix(1),prefix(2,1); r0,r1=subject.prefix_fingerprint(p0),subject.prefix_fingerprint(p1)
        valid=(
            {"row_index":"0","sibling_identity":"0:0","parent_id":"0","parent_fingerprint":r0,"parent_canonical":subject.canonical_fingerprint(r0),"parent_stm":"0"},
            {"row_index":"1","sibling_identity":"1:0","parent_id":"1","parent_fingerprint":r1,"parent_canonical":subject.canonical_fingerprint(r1),"parent_stm":"1"},)
        ledger=subject.SemanticReadLedger(); subject.validate_parent_linkage(valid,(p0,p1),ledger)
        with self.assertRaisesRegex(subject.ExactLinkageError,"prefix_mismatch"):
            subject.validate_parent_linkage((dict(valid[0],parent_canonical=r0),valid[1]),(p0,p1),ledger)
        with self.assertRaisesRegex(subject.ExactLinkageError,"stm_mismatch"):
            subject.validate_parent_linkage((dict(valid[0],parent_stm="1"),valid[1]),(p0,p1),ledger)
        with self.assertRaisesRegex(subject.ExactLinkageError,"sibling_identity_duplicate"):
            subject.validate_row_geometry((valid[0],dict(valid[1],sibling_identity="0:0")),schema)
        with self.assertRaisesRegex(subject.ExactLinkageError,"parent_block_start"):
            subject.validate_row_geometry((valid[1],valid[0]),schema)


if __name__ == "__main__":
    unittest.main()
