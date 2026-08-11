"""Static safety contracts for the full-Jass conditional transfer probe."""
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
TEMPLATE = ROOT / "jobs" / "templates" / "l3-conditional-target-transfer-probe-v1.sh"


def test_probe_reuses_existing_selfplay_and_l2low() -> None:
    script = TEMPLATE.read_text(encoding="utf-8")
    assert "home-0977-l3-pure-turnover1to1-train-v1" in script
    assert "cpx62-1164-l3-prior-dose-l2-refit-v1" in script
    assert "turnover1to1.jnnw.gz" in script
    assert "turnover1to1.jsm.gz" in script
    assert "control.pjtw.gz" in script
    assert "generate-selfplay" not in script
    assert "new_selfplay_generated" in script


def test_probe_is_architecture_and_recipe_correct() -> None:
    script = TEMPLATE.read_text(encoding="utf-8")
    for flag in (
        "-DJASS_ENDGAME_FEATURES=ON",
        "-DJASS_KING_MOBILITY=ON",
        "-DJASS_SCAN_PARITY=ON",
        "-DJASS_TEMPO_STAGE=ON",
        "--exact-fold",
        "--prior-mean",
        "--prior-decay 0",
        "--l2 1e-5",
        "--lbfgs-gtol 1e-4",
    ):
        assert flag in script
    assert "EXPECTED_EXTRAS=120" in script
    assert "architecture guard" in script


def test_probe_has_operational_guards_and_no_continuation() -> None:
    script = TEMPLATE.read_text(encoding="utf-8")
    assert "post-sizing human GO missing" in script
    assert "nproc=16" in script or '"$NCPU" -eq 16' in script
    assert "less than 10 GiB" in script
    assert "PROGRESS.txt" in script
    assert "TARGET_TIMEOUT" in script and "FIT_TIMEOUT" in script
    assert "n=0" in script
    assert "AUTOMATIC_NEXT_JOB__NULL" in script
    assert "PROMOTION_AUTHORIZED__FALSE" in script


def test_probe_builds_aligned_and_marginal_matched_external_targets() -> None:
    script = TEMPLATE.read_text(encoding="utf-8")
    assert "jobs/tools/l3_conditional_targets.py" in script
    assert "--aligned-out" in script and "--shuffled-out" in script
    assert script.count("--target external") == 1  # inside the shared fit function
    assert "--target-values" in script
    assert "--targets-report" in script
    assert "MAXIT=25" in script
    assert "convergence_required_for_probe" in script
