# L3 — T3-A/F6 Runtime Strength v4 — résultat terminal

Date d'exécution terminale : 30 août 2026. Contrat :
`docs/experiments/L3_T3_F6_RUNTIME_STRENGTH_V4_20260829.md`.

## 1. R0-v4 — contrat production leaf établi

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

## 2. Identités gelées et reçus R0

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

## 3. Pool1 PRIMARY CPX62 — verdict causal terminal

Le Pool1 autorisé par R0-v4 a ensuite été exécuté sans retune, sans changement
de bytes ou de paramètres search/runtime :

Job : `cpx62-1686-l3-t3-f6-runtime-strength-pool1-v4`  
Attempt : `20260830T104034Z-0ead13cb`  
Code scientifique : `0ead13cb3579ce83c1278fe21c6634096d5e8eec`  
État : `completed`, exit `0`  
Games : `6000` = `3000` openings × deux couleurs  
Régime PRIMARY : native `0.1 s/move`, un thread, TT `16 MiB`, EGDB ON, book OFF.

Verdict exact :

```text
T3_F6_RUNTIME_STRENGTH_NOT_SUPPORTED
```

Reçu terminal read-only :

- job `cpx62-1689-l3-t3-f6-runtime-pool1-terminal-receipt-v1` ;
- attempt `20260830T114717Z-ea643d77` ;
- état `completed`, exit `0`.

Métriques exactes :

| Mesure | Valeur |
|---|---:|
| Victoires T3-A | `1167` |
| Nulles | `180` |
| Victoires CURRICULUM | `4653` |
| Score T3-A | **`0.2095`** |
| Elo T3−CURRICULUM | **`-230.6871387863655`** |
| CI95 game score | `[0.19943856856108436 ; 0.21956143143891563]` |
| CI95 paired opening | `[0.20033333333333334 ; 0.21866666666666668]` |
| `P(score > 0.5)` paired bootstrap | `0.0` |

La règle preregistrée est mécanique : le point estimate PRIMARY est `<= 0.5`,
donc :

```text
POOL2_AUTHORIZED__FALSE
```

Aucun Pool2 v4 ne doit être exécuté. Aucun Pool3 n'existe. Aucun bake ou
promotion n'est autorisé.

Ce résultat est un vrai résultat scientifique négatif de force runtime ; ce
n'est ni une panne technique, ni une CI ambiguë, ni un déficit de support.

## 4. Diagnostic HOME post-terminal — coût technique, pas force

Le premier sizer HOME `home-1687-l3-t3-f6-v4-q00-sizer` a échoué techniquement
avec exit `132`. L'autopsie/réparation `home-1688-l3-t3-f6-v4-q00-native-repair-v1`
a établi que le binaire natif CPX R0 déclenchait `SIGILL` sur HOME, puis a
reconstruit nativement les mêmes sources pour un diagnostic technique sans
partie de force.

`1688` a terminé exit `0` avec :

```text
VERDICT__HOME_Q00_V4_NATIVE_REPAIR_PASS
FOREIGN_R0_BINARY_HELLO_RC__132
FOREIGN_R0_BINARY_SIGILL__TRUE
HOME_NATIVE_LOADER__PASS
WALL_RATIO_T3_OVER_CURRICULUM__37.154452
NPS_RATIO_T3_OVER_CURRICULUM__0.053152
STRENGTH_GAMES__0
SCIENTIFIC_DECISION__FALSE
```

Les ratios HOME indiquent un coût runtime très élevé et motivent une branche
d'ingénierie d'équivalence exacte. Ils ne mesurent pas la force et ne peuvent
pas sauver le PRIMARY CPX62 négatif.

## 5. Lecture terminale v4

La chaîne v4 répond désormais à deux questions séparées :

1. **Le wrapper/leaf T3-A est-il fonctionnellement correct ?** Oui : R0-v4 PASS.
2. **Le T3-A/F6 gelé bat-il CURRICULUM sous le PRIMARY natif 0.1 s/move ?** Non : score `20.95 %`, environ `-230.7 Elo`.

Le signal offline F6 reste un résultat antérieur valide ; le terminal runtime
montre qu'il ne se transforme pas en force dans cette implémentation/régime.
Le coût technique observé rend plausible une domination par le coût
d'évaluation, mais cette explication doit être traitée comme une hypothèse
d'ingénierie tant qu'une optimisation **strictement équivalente** n'a pas été
établie puis, si justifié, retestée sous une preregistration de force séparée.

La prochaine branche autorisée n'est donc pas un retune de T3-A. La
preregistration `L3_T3_F6_RUNTIME_EXACT_CACHE_O1_20260830.md` propose une seule
transformation : cache exact du résiduel F6 par identité complète de position,
sans changement de modèle, de F6 ou de search.

## 6. Chaîne historique préservée

Les terminaux restent distincts et inchangés :

1. v1 : `R0_PRODUCTION_LEAF_CONTRACT_NOT_ESTABLISHED` ;
2. v2 : `R0_V2_NEGAMAX_OR_TERMINAL_PRECEDENCE_FAILED` ;
3. autopsie : `QUIESCENCE_OR_DEPTH_SEMANTICS_EXPLAINS_MISMATCH` ;
4. v3 : `R0_V3_RUNTIME_SUPPORT_INCONCLUSIVE` ;
5. v4 R0 : `R0_V4_PRODUCTION_LEAF_CONTRACT_ESTABLISHED` ;
6. v4 Pool1 : `T3_F6_RUNTIME_STRENGTH_NOT_SUPPORTED`.

Aucun résultat antérieur n'est réinterprété ou effacé.
