import json
from pathlib import Path
import tempfile
import unittest

from jobs.tools import jfi_force_readout as mod


CANDIDATE="a"*64; CURRICULUM="b"*64; EXE="c"*64; SEARCH=",".join(["x"]*63)


def gate(path, pool, view, rate):
    if rate==.75: wins,draws,losses,scores=3000,3000,0,[.75]*3000
    elif rate==.5: wins,draws,losses,scores=0,6000,0,[.5]*3000
    elif rate=="weak":
        wins,draws,losses,scores=1501,3000,1499,[.75]*1501+[.25]*1499
        rate=(wins+.5*draws)/6000
    else: raise ValueError(rate)
    payload={"complete":True,"n":6000,"wins_a":wins,"draws":draws,"wins_b":losses,
      "rate":rate,"jass_a_sha256":EXE,"jass_b_sha256":EXE,
      "pattern_a_sha256":CANDIDATE,"pattern_b_sha256":CURRICULUM,
      "search_params_a":SEARCH,"search_params_b":SEARCH,
      "pairs":1,"nshards":12,"max_parallel":12,
      "max_plies":160,"game_timeout":180,"fail_on_game_error":True,"book_disabled":True,
      "openings_file_sha256":str(pool)*64,
      "depth":None if view=="native" else 9,"movetime":.1 if view=="native" else None,
      "paired_opening":{"method":"paired_colour_opening_cluster_bootstrap","n_openings":3000,
        "games_per_opening":2,"bootstrap_samples":200000,"seed":mod.POOL_SEEDS[pool],
        "rate":rate,"ci_low":rate,"ci_high":rate,"probability_rate_gt_half":float(rate>.5),
        "wins_a":wins,"draws":draws,"wins_b":losses,
        "per_opening_scores":scores,"error_draws":0,"errors_by_arm":{"a":0,"b":0,"unknown":0},
        "errors_by_candidate_colour":{"white":0,"black":0},
        "score_by_candidate_colour":{"white":{"games":3000},"black":{"games":3000}}}}
    Path(path).write_text(json.dumps(payload))


class ForceReadoutTests(unittest.TestCase):
    def test_pool1_nonpositive_is_terminal_not_supported(self):
        with tempfile.TemporaryDirectory() as raw:
            n=Path(raw)/"n.json"; q=Path(raw)/"q.json"; gate(n,1,"native",.5); gate(q,1,"q00",.75)
            report=mod.build_pool1(n,q,CANDIDATE,CURRICULUM,EXE,SEARCH)
            self.assertEqual(report["verdict"],"JFI_JASS_NATIVE_STRENGTH_NOT_SUPPORTED")
            self.assertFalse(report["pool2_authorized"])

    def test_two_positive_pools_with_chained_lower_positive_establish(self):
        with tempfile.TemporaryDirectory() as raw:
            paths={}
            for pool in (1,2):
                for view in ("native","q00"):
                    path=Path(raw)/f"{pool}-{view}.json"; gate(path,pool,view,.75); paths[(pool,view)]=path
            report=mod.build_final(paths,CANDIDATE,CURRICULUM,EXE,SEARCH,chained_samples=100,chained_seed=7)
            self.assertEqual(report["verdict"],"JFI_JASS_NATIVE_STRENGTH_ESTABLISHED")
            self.assertGreater(report["chained_native"]["ci_low"],.5)
            self.assertFalse(report["markers"]["THIRD_POOL_AUTHORIZED"])

    def test_pool2_nonpositive_is_not_supported(self):
        with tempfile.TemporaryDirectory() as raw:
            paths={}
            for pool in (1,2):
                for view in ("native","q00"):
                    path=Path(raw)/f"{pool}-{view}.json"
                    gate(path,pool,view,.75 if pool==1 else .5); paths[(pool,view)]=path
            report=mod.build_final(paths,CANDIDATE,CURRICULUM,EXE,SEARCH,chained_samples=100,chained_seed=7)
            self.assertEqual(report["verdict"],"JFI_JASS_NATIVE_STRENGTH_NOT_SUPPORTED")

    def test_two_positive_pools_without_chained_lower_bound_are_inconclusive(self):
        with tempfile.TemporaryDirectory() as raw:
            paths={}
            for pool in (1,2):
                for view in ("native","q00"):
                    path=Path(raw)/f"{pool}-{view}.json"; gate(path,pool,view,"weak"); paths[(pool,view)]=path
            report=mod.build_final(paths,CANDIDATE,CURRICULUM,EXE,SEARCH,chained_samples=1000,chained_seed=7)
            self.assertEqual(report["verdict"],"JFI_JASS_NATIVE_STRENGTH_INCONCLUSIVE")
            self.assertLessEqual(report["chained_native"]["ci_low"],.5)


if __name__=="__main__": unittest.main()
