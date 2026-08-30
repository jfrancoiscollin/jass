# L3 — T3-A/F6 Runtime Strength v4 — résultat terminal R0

Date d'exécution terminale : 30 août 2026. Contrat :
`docs/experiments/L3_T3_F6_RUNTIME_STRENGTH_V4_20260829.md`.

## Verdict immuable

Job : `cpx62-1685-l3-t3-f6-runtime-r0-v4`  
Attempt : `20260830T083226Z-0ead13cb`  
Code : `0ead13cb3579ce83c1278fe21c6634096d5e8eec`  
État runner-v3 : `completed`, exit `0`  
Début : `2026-08-30T08:32:31Z`  
Fin : `2026-08-30T09:39:13Z`  
Résultat : `r2:jass-data/runs/cpx62-1685-l3-t3-f6-runtime-r0-v4/20260830T083226Z-0ead13cb`

Verdict exact :

```text
R0_V4_PRODUCTION_LEAF_CONTRACT_ESTABLISHED
```

Le reçu terminal publie également :

```text
POOL1_AUTHORIZED__TRUE
STRENGTH_GAMES__0
PROMOTION_AUTHORIZED__FALSE
BAKE__FALSE
SCIENTIFIC_PARAMETERS_CHANGED__FALSE
```

Ce PASS clôt uniquement R0-v4. Il établit le contrat de wrapper/leaf de
production demandé par la preregistration et autorise **Pool1 uniquement**. Il
ne constitue ni une preuve de force runtime, ni une promotion, ni un bake.

## Identités gelées et reçus présents

Les artefacts runner-v3 authentifiés du terminal comprennent notamment :

- `JASS_CONTROL_SUMMARY.json` ;
- `r0-selection.json` et `r0-corpus.fen` ;
- `r0-wrapper-contract.json` ;
- `r0-relative-contract.json` ;
- `r0-python-native-parity.json` ;
- `r0-runtime-profile.json` ;
- `r0-search-profile.json` ;
- `loader-auth.json` ;
- `runtime-contract.json` ;
- `zero-probe-manifest.json` ;
- l'exécutable exact `jass-t3-f6-force.gz` ;
- T3-A/F6 exact `t3-a-f6-only.json` ;
- CURRICULUM exact `curriculum.pjtw`.

Les identités scientifiques restent celles de la preregistration :

- T3-A/F6 SHA256
  `16e5db8fd78849bba12b158eee5c1da4ab170129d8aeac1b91ab7a40ad9d0bb2` ;
- CURRICULUM SHA256
  `319d174f4b548b1655aad4bb30d4c6dc86c08dd715c9c23f8b19ba1937dc0be1` ;
- aucun refit, retune, calibration, D1, retrait de feature, bake ou promotion.

Le terminal contient les reçus mécaniques suivants, explicitement sans
modification de paramètres scientifiques :

- `BUILD_MISSING_EXISTING_TARGET_ONLY` ;
- `EXPECTED_LOADER_FAILURE_ERR_TRAP_ONLY` ;
- `PARITY_PYTHONPATH_ONLY` ;
- `V4_BENCH_SEED_GUARD_ONLY`.

Ils restent des réparations techniques de contrat ; ils ne sont pas des
résultats scientifiques indépendants.

## Conséquence causale

La seule question de force autorisée reste :

```text
T3_A_F6 vs CURRICULUM
```

Le PRIMARY preregistré est Pool1 sur CPX62, native `0.1 s/move`, avec les
bytes/executable/search/runtime gelés par R0-v4. Le diagnostic Q00 depth 9 est
non bloquant et ne peut jamais sauver un PRIMARY CPX62 négatif.

Aucune partie de force n'a été jouée pendant R0-v4. Pool2 n'est pas autorisé
avant un Pool1 positif selon la règle preregistrée. Il n'existe ni Pool3 ni
promotion automatique.

## Chaîne historique préservée

Les terminaux antérieurs restent distincts et inchangés :

1. v1 : `R0_PRODUCTION_LEAF_CONTRACT_NOT_ESTABLISHED` ;
2. v2 : `R0_V2_NEGAMAX_OR_TERMINAL_PRECEDENCE_FAILED` ;
3. autopsie : `QUIESCENCE_OR_DEPTH_SEMANTICS_EXPLAINS_MISMATCH` ;
4. v3 : `R0_V3_RUNTIME_SUPPORT_INCONCLUSIVE` ;
5. v4 : `R0_V4_PRODUCTION_LEAF_CONTRACT_ESTABLISHED`.

V4 ne réinterprète ni n'efface aucun de ces terminaux.
