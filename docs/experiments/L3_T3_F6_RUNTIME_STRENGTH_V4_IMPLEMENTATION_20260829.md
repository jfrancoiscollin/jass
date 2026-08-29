# L3 — T3-A/F6 Runtime v4 — reçu d'implémentation avant R0

Date : 29 août 2026. Ce reçu implémente sans la modifier la preregistration
V4 mergée au SHA `e857a5a951afa3c78957c7ad92afb67e4b0dae3b`. Il est publié avant
toute génération du corpus R0-v4 et avant toute lecture de score V4.

## Probe ZERO data-free

- générateur canonique : `jobs/tools/t3_f6_zero_artifact_v4.py` ;
- entrées de données : `0` ;
- fits/trainings/calibrations : `0` ;
- architecture : `66 -> 256 -> 128 -> 64 -> 1` ;
- normalisation : mean `0`, std `1` ;
- toutes matrices et tous biais : `0` ;
- format : JSON minimal, clés triées, séparateurs `,`/`:`, newline final ;
- SHA256 canonique ZERO :
  `160489327d419e3d7bbbbda900d6e0ec7bc960111149fc0a45cc27aaa55bf6aa`.

Le SHA du fichier générateur est calculé et publié dans
`zero-probe-manifest.json` avant la génération du corpus. Le job refuse tout
ZERO dont les bytes ne correspondent pas au SHA compilé ci-dessus.

Le loader production `JASS_T3_F6_MODEL` reste strictement `FrozenOnly` et
rejette le ZERO. Seul `t3_f6_runtime_contract_v4 --zero-probe` peut demander
la politique `ZeroProbeOnly`. Les deux modèles passent ensuite par la même
classe `t3_f6::Network`, `evaluate_from_base` et intégration search.

## Instrumentation passive

`SearchResult` expose en plus, sans les consulter dans aucune décision :
qnodes/qsearch calls, probes/hits TB et TT, terminaux, réductions et
extensions. Le gate V4 compare ces champs exactement entre OFF et ZERO.
Le binaire de force ne change aucune règle, option, limite ou branche search.

## Contrôles locaux avant PR

- générateur ZERO : SHA attendu exact ;
- Python protocol/unit tests : PASS ;
- parsing bash R0/Pool1/Pool2 : PASS ;
- build natif ciblé WSL : PASS ;
- `t3_f6_runtime_contract_v4 --selftest` : PASS ;
- `jass_tests` : `27257` assertions PASS.

Aucun score scientifique, label profond, partie de force, fit, retune, bake
ou promotion n'a été produit par ces contrôles.
