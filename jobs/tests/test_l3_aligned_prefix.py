import importlib.util
import struct
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location(
    "l3_aligned_prefix", ROOT / "jobs/tools/l3_aligned_prefix.py"
)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(MODULE)


def counted(path: Path, magic: bytes, record_size: int, records: int) -> None:
    body = b"".join(bytes([index + 1]) * record_size for index in range(records))
    path.write_bytes(struct.pack("<4sI", magic, records) + body)


class AlignedPrefixTests(unittest.TestCase):
    def test_exact_prefix_and_no_clobber(self):
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            data, meta = root / "in.jnnw", root / "in.jsm"
            out_data, out_meta = root / "out.jnnw", root / "out.jsm"
            counted(data, b"JNNW", 38, 4)
            counted(meta, b"JSM1", 17, 4)
            report = MODULE.slice_pair(data, meta, out_data, out_meta, 2)
            self.assertEqual(report["records"], 2)
            self.assertFalse(report["learning_curve_authorized"])
            self.assertEqual(struct.unpack("<4sI", out_data.read_bytes()[:8]), (b"JNNW", 2))
            self.assertEqual(out_data.read_bytes()[8:], data.read_bytes()[8:8 + 2 * 38])
            self.assertEqual(out_meta.read_bytes()[8:], meta.read_bytes()[8:8 + 2 * 17])
            with self.assertRaisesRegex(ValueError, "replace"):
                MODULE.slice_pair(data, meta, out_data, root / "again.jsm", 2)

    def test_rejects_alignment_and_bounds(self):
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            data, meta = root / "in.jnnw", root / "in.jsm"
            counted(data, b"JNNW", 38, 3)
            counted(meta, b"JSM1", 17, 2)
            with self.assertRaisesRegex(ValueError, "count mismatch"):
                MODULE.slice_pair(data, meta, root / "o.jnnw", root / "o.jsm", 2)
            counted(meta, b"JSM1", 17, 3)
            with self.assertRaisesRegex(ValueError, "records must"):
                MODULE.slice_pair(data, meta, root / "o.jnnw", root / "o.jsm", 4)

    def test_rejects_trailing_bytes_and_path_alias(self):
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            data, meta = root / "in.jnnw", root / "in.jsm"
            counted(data, b"JNNW", 38, 1)
            counted(meta, b"JSM1", 17, 1)
            data.write_bytes(data.read_bytes() + b"x")
            with self.assertRaisesRegex(ValueError, "counted size"):
                MODULE.slice_pair(data, meta, root / "o.jnnw", root / "o.jsm", 1)
            data.write_bytes(data.read_bytes()[:-1])
            with self.assertRaisesRegex(ValueError, "distinct"):
                MODULE.slice_pair(data, meta, data, root / "o.jsm", 1)


if __name__ == "__main__":
    unittest.main()
