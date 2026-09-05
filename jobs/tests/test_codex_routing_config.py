from __future__ import annotations

import tomllib
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
CODEX = ROOT / ".codex"


def load_toml(path: Path) -> dict:
    with path.open("rb") as handle:
        return tomllib.load(handle)


def test_cost_aware_root_and_registered_roles() -> None:
    config = load_toml(CODEX / "config.toml")
    assert config["model"] == "gpt-5.6-terra"
    assert config["model_reasoning_effort"] == "low"
    assert config["model_verbosity"] == "low"

    agents = config["agents"]
    assert agents["enabled"] is True
    assert agents["max_concurrent_threads_per_session"] == 2
    assert set(agents) >= {"monitor", "fast", "dev", "scientist"}

    expected_files = {
        "monitor": "agents/monitor.toml",
        "fast": "agents/fast.toml",
        "dev": "agents/dev.toml",
        "scientist": "agents/scientist.toml",
    }
    for role, relative in expected_files.items():
        assert agents[role]["config_file"] == relative
        assert (CODEX / relative).is_file()


def test_cost_tiers_are_monotonic_and_sol_is_not_default() -> None:
    expected = {
        "monitor": ("gpt-5.6-luna", "low"),
        "fast": ("gpt-5.6-luna", "medium"),
        "dev": ("gpt-5.6-terra", "medium"),
        "scientist": ("gpt-5.6-sol", "high"),
    }
    for role, (model, effort) in expected.items():
        config = load_toml(CODEX / "agents" / f"{role}.toml")
        assert config["model"] == model
        assert config["model_reasoning_effort"] == effort
        assert config["model_verbosity"] == "low"

    root = load_toml(CODEX / "config.toml")
    assert root["model"] != "gpt-5.6-sol"


def test_agents_policy_documents_ordered_escalation_and_luna_fallback() -> None:
    policy = (ROOT / "AGENTS.md").read_text(encoding="utf-8")
    assert "monitor (Luna low) → fast (Luna medium) → dev (Terra medium) → scientist (Sol high)" in policy
    assert "One failed bounded Luna repair is a signal to move to Terra" in policy
    assert "do **not** jump directly to Sol" in policy
    assert "one delegated worker at a time" in policy
