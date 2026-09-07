---
applyTo: "jobs/tools/d1_terminal_autopsy.py,jobs/tests/test_d1_terminal_autopsy.py,jobs/templates/l3-d1-terminal-autopsy-v1.sh,docs/experiments/L3_D1_TERMINAL_AUTOPSY_V1_20260907.md"
---

D1 terminal autopsy is post-terminal diagnostic work only.

- Do not add a fit, refit, lambda/tau sweep, model search, teacher search, strength game, promotion or bake.
- Do not read 1843 full-ladder values or q5/q50/q200 values as targets.
- Do not authorize equal-node from this stage.
- Preserve terminal D1 verdict `D1_DECISION_TRANSFER_NOT_ESTABLISHED_V1` as immutable evidence.
- Any future transfer redesign requires a separate preregistration after this autopsy.
