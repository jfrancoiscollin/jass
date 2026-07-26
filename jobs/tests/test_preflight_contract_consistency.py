"""Les scalaires shell d'un préflight doivent égaler les littéraux de son contrat.

Trois runs ont été perdus sur cette seule classe de bug : `home-0981bis` sur un
chemin de champ, `home-0984` sur une complétude de schéma, `home-0990` sur des
littéraux `NOPEN`/`OPENING_SEED` restés à leur valeur d'origine dans le heredoc
python du certificat alors que les variables shell avaient été changées.

Le piège est que les littéraux python s'écrivent avec des séparateurs
(`1_836_311`), donc une recherche sur la forme shell (`1836311`) ne les trouve
pas. Ce test compare les deux formes.
"""
from __future__ import annotations

import re
from pathlib import Path

import unittest

TEMPLATES = Path(__file__).resolve().parents[1] / "templates"

# variable shell -> motifs du contrat python qui doivent porter la même valeur
BINDINGS = {
    "NOPEN": (
        r'openings\.get\("records"\) != ([0-9_]+)',
        r'openings\.get\("unique_records"\) != ([0-9_]+)',
    ),
    "OPENING_SEED": (
        r'openings\.get\("generator_seed"\) != ([0-9_]+)',
        r'"seed": ([0-9_]+),',
    ),
    "TOTAL_RECORDS": (
        r'manifest\.get\("records"\) != ([0-9_]+)',
        r'split\.get\("records"\) != ([0-9_]+)',
    ),
    "MIX_SEED": (
        r'manifest\.get\("seed"\) != ([0-9_]+)',
        r'"mix_seed": ([0-9_]+),',
    ),
    "SPLIT_SEED": (r'"split_seed": ([0-9_]+),',),
    "PARENT_RECORDS": (
        r'sources\.get\("PARENT", \{\}\)\.get\("selected_records"\) != ([0-9_]+)',
        r'sources\["PARENT"\]\["selected_records"\] != ([0-9_]+)',
        r'"historical_replay_records": ([0-9_]+),',
    ),
    "FRESH_RECORDS": (
        r'sources\.get\("FRESH", \{\}\)\.get\("selected_records"\) != ([0-9_]+)',
        r'sources\["FRESH"\]\["selected_records"\] != ([0-9_]+)',
        r'"fresh_records": ([0-9_]+),',
    ),
}


def shell_scalars(text: str) -> dict[str, int]:
    found = {}
    for name in BINDINGS:
        match = re.search(rf"^{name}=(\d+)$", text, re.M)
        if match:
            found[name] = int(match.group(1))
    return found


def preflight_templates() -> list[Path]:
    return sorted(p for p in TEMPLATES.glob("*preflight*.sh"))


class PreflightContractConsistencyTest(unittest.TestCase):
    def test_at_least_one_preflight_is_covered(self):
        self.assertTrue(preflight_templates(), "aucun template de préflight trouvé")

    def test_shell_scalars_match_contract_literals(self):
        checked = 0
        for path in preflight_templates():
            text = path.read_text(encoding="utf-8")
            scalars = shell_scalars(text)
            for name, value in scalars.items():
                for pattern in BINDINGS[name]:
                    for raw in re.findall(pattern, text):
                        literal = int(raw.replace("_", ""))
                        checked += 1
                        self.assertEqual(
                            literal,
                            value,
                            f"{path.name}: le contrat porte {raw} là où "
                            f"{name}={value} — littéral périmé",
                        )
        self.assertGreater(checked, 0, "aucun littéral de contrat inspecté")

    def test_detects_a_stale_literal(self):
        """Le test doit échouer sur le bug réel de home-0990."""
        broken = (
            "NOPEN=1250\n"
            "OPENING_SEED=3141593\n"
            'if openings.get("records") != 500:\n'
            "    raise SystemExit()\n"
        )
        scalars = shell_scalars(broken)
        self.assertEqual(scalars["NOPEN"], 1250)
        literals = [
            int(raw.replace("_", ""))
            for raw in re.findall(BINDINGS["NOPEN"][0], broken)
        ]
        self.assertEqual(literals, [500])
        self.assertNotEqual(literals[0], scalars["NOPEN"])


if __name__ == "__main__":
    unittest.main()
