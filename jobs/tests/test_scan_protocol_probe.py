"""La sonde est testée contre un FAUX Scan.

Ce que ces tests vérifient : la plomberie (handshake, capture verbatim,
sentinelles, transcription, verdict). Ce qu'ils ne vérifient PAS, et ne peuvent
pas : le vrai format des lignes de Scan 3.1 — c'est précisément ce que la sonde
va chercher sur la box. Un faux Scan qui parlerait le format que j'ai deviné ne
prouverait rien du tout ; c'est pourquoi l'un des faux répond SANS score, et le
test exige que la sonde le dise au lieu de rendre un zéro.
"""

import importlib.util
import json
import stat
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location(
    "scan_protocol_probe", ROOT / "jobs/tools/scan_protocol_probe.py")
M = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
sys.modules["scan_protocol_probe"] = M
SPEC.loader.exec_module(M)


FAKE_WITH_SCORE = r'''#!/usr/bin/env python3
import sys
for line in sys.stdin:
    c = line.strip()
    if c == "hub":
        print("id name=Scan version=3.1"); print("wait")
    elif c == "init":
        print("ready")
    elif c == "go think":
        print("info depth=8 score=11 nodes=1000")
        print("info depth=9 score=-27 nodes=9000")
        print("done move=32-28")
    elif c == "quit":
        break
    sys.stdout.flush()
'''

FAKE_WITHOUT_SCORE = r'''#!/usr/bin/env python3
import sys
for line in sys.stdin:
    c = line.strip()
    if c == "hub":
        print("id name=Scan version=3.1"); print("wait")
    elif c == "init":
        print("ready")
    elif c == "go think":
        print("info depth=9 eval=-27 nodes=9000")
        print("done move=32-28")
    elif c == "quit":
        break
    sys.stdout.flush()
'''


def write_fake(body: str) -> Path:
    d = Path(tempfile.mkdtemp())
    p = d / "scan_linux"
    p.write_text(body)
    p.chmod(p.stat().st_mode | stat.S_IEXEC)
    return p


class ProbeAgainstFakeScan(unittest.TestCase):
    def _run(self, fake: Path):
        d = Path(tempfile.mkdtemp())
        tr, out = d / "transcript.txt", d / "report.json"
        rc = M.main(["--scan", str(fake), "--depth", "4",
                     "--transcript", str(tr), "--out", str(out)])
        return rc, tr, json.loads(out.read_text())

    def test_extracts_the_last_score_and_says_the_pattern_works(self):
        rc, tr, rep = self._run(write_fake(FAKE_WITH_SCORE))
        self.assertEqual(rc, 0)
        self.assertEqual(rep["verdict"], "SCAN_SCORE_PATTERN_WORKS")
        self.assertEqual(rep["positions_probed"], len(M.PROBE_FENS))
        self.assertEqual(rep["positions_with_score_extracted"],
                         len(M.PROBE_FENS))
        for f in rep["findings"]:
            self.assertEqual(f["score_extracted"], -27.0)
            self.assertTrue(f["reached_done"])

    def test_a_format_it_cannot_read_is_reported_not_silently_zeroed(self):
        """Le cas qui justifie la sonde : Scan répond, mais pas dans le gabarit
        attendu. Il faut que ça ressorte comme un verdict, avec les lignes
        brutes, pour qu'on écrive le bon motif."""
        rc, tr, rep = self._run(write_fake(FAKE_WITHOUT_SCORE))
        self.assertEqual(rc, 0)          # ce n'est pas un plantage, c'est le résultat
        self.assertEqual(rep["verdict"], "SCAN_SCORE_PATTERN_NEEDS_REWORK")
        self.assertEqual(rep["positions_with_score_extracted"], 0)
        for f in rep["findings"]:
            self.assertIsNone(f["score_extracted"])
            self.assertTrue(f["reached_done"])
            # La ligne réelle est conservée pour qu'un humain voie le gabarit.
            self.assertTrue(any("eval=-27" in l for l in f["last_three_lines"]))

    def test_transcript_is_verbatim_in_both_directions(self):
        _, tr, _ = self._run(write_fake(FAKE_WITH_SCORE))
        text = tr.read_text()
        self.assertIn("> hub", text)
        self.assertIn("> go think", text)
        self.assertIn("< done move=32-28", text)
        self.assertIn("< info depth=9 score=-27 nodes=9000", text)
        # Les positions sondées doivent apparaître comme des sections nommées.
        for label, _ in M.PROBE_FENS:
            self.assertIn(f"== position {label}", text)

    def test_missing_binary_fails_loudly(self):
        d = Path(tempfile.mkdtemp())
        rc = M.main(["--scan", str(d / "absent"), "--transcript",
                     str(d / "t.txt"), "--out", str(d / "o.json")])
        self.assertEqual(rc, 2)


class PositionsAreDerivedNotInvented(unittest.TestCase):
    def test_every_probe_position_is_a_valid_51_char_scan_layout(self):
        to_scan = M.load_fen_converter()
        for label, fen in M.PROBE_FENS:
            pos = to_scan(fen)
            self.assertEqual(len(pos), 51, label)
            self.assertIn(pos[0], ("W", "B"), label)
            self.assertTrue(set(pos[1:]) <= set("ewbWB"), label)


if __name__ == "__main__":
    unittest.main()
