import pathlib,unittest


class TemplateTest(unittest.TestCase):
    def test_guards(self):
        root=pathlib.Path(__file__).resolve().parents[2]
        text=(root/'jobs/templates/l3-curriculum-error-loss-first-sibling-rank-preregistration-v1.sh').read_text()
        for token in ('PREREGISTRATION_ONLY','NO_NEW_EXACT_TARGETS','NO_PATTERNEVAL_FIT','NO_STRENGTH_GAMES','NO_SELFPLAY','NO_FROZEN_READ','NO_AUTOMATIC_PROMOTION','NO_AUTOMATIC_CONTINUATION','JASS_CURRICULUM_ERROR_LOSS_FIRST_SIBLING_RANK_PREREGISTERED'):
            self.assertIn(token,text)


if __name__=="__main__": unittest.main()
