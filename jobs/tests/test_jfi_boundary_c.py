import copy
from pathlib import Path
import unittest

from jobs.tools import jfi_boundary_c


def valid_input():
    return {"schema":"jass.jfi.boundary_c_input.v1","code_sha":"a"*40,
      "machine":{"host":"cpx62","nproc":16,"avx2":True,"bmi2":True},
      "disk":{"scratch_free_bytes":100*1024**3},
      "candidate":{"name":"JASS_NATIVE_ACTIVE_V1","sha256":"b"*64},
      "curriculum":{"sha256":"319d174f4b548b1655aad4bb30d4c6dc86c08dd715c9c23f8b19ba1937dc0be1"},
      "executable":{"sha256":"c"*64,"same_binary_both_arms":True},
      "consumed_root_sizers":{"native_0p1s":{"games":16,"seconds":10,"candidate_vs_itself":True},
                               "q00_depth9":{"games":16,"seconds":20,"candidate_vs_itself":True}},
      "force_runtime":{"shards":12,"parallelism":12,"per_game_timeout_seconds":180,"per_view_timeout_seconds":21600},
      "markers":dict(jfi_boundary_c.ZERO_MARKERS)}


class BoundaryCTests(unittest.TestCase):
    def test_ready_projects_both_views_and_stops(self):
        facts=jfi_boundary_c.build_facts(valid_input())
        self.assertEqual(facts["next_boundary"],"GO JFI FORCE")
        self.assertEqual(facts["consumed_root_sizers"]["native_0p1s"]["projected_pool1_seconds_6000_games"],3750)

    def test_model_or_marker_drift_fails_closed(self):
        source=valid_input(); source["candidate"]["name"]="other"
        with self.assertRaisesRegex(ValueError,"candidate"): jfi_boundary_c.build_facts(source)
        source=valid_input(); source["markers"]["STRENGTH_GAMES"]=1
        with self.assertRaisesRegex(ValueError,"zero-marker"): jfi_boundary_c.build_facts(source)

    def test_template_uses_consumed_self_play_and_no_scientific_contrast(self):
        text=(Path(__file__).resolve().parents[1]/"templates"/"l3-jfi-boundary-c-v1.sh").read_text()
        self.assertIn("big3000-openings.fen",text); self.assertIn("--pattern-b \"$W/candidate.pjtw\"",text)
        self.assertIn("NEXT_BOUNDARY__GO_JFI_FORCE",text); self.assertIn("STRENGTH_GAMES__0",text)
        self.assertNotIn("--pattern-b \"$W/curriculum.pjtw\"",text)


if __name__=="__main__": unittest.main()
