# L3 — T3/F6 Runtime Strength v2 — résultat terminal

Date : 29 août 2026. Statut : **terminal en R0-v2, avant toute partie de
force**.

Protocole immuable :
[`L3_T3_F6_RUNTIME_STRENGTH_V2_20260829.md`](L3_T3_F6_RUNTIME_STRENGTH_V2_20260829.md).
Le terminal v1 reste inchangé dans
[`L3_T3_F6_RUNTIME_STRENGTH_V1_RESULTS_20260829.md`](L3_T3_F6_RUNTIME_STRENGTH_V1_RESULTS_20260829.md).

## 1. Verdict

V2 établit le contrat relatif de drift, mais échoue au gate de perspective
negamax depth-1 :

```text
R0_V2_NEGAMAX_OR_TERMINAL_PRECEDENCE_FAILED
```

Décomposition authentifiée :

```text
gate1 position/transposition       = PASS
gate2 F6/residual invariance       = PASS
gate3 relative drift               = PASS
negamax single inversion depth-1  = FAIL
terminal precedence               = PASS
EGDB available                    = true
tablebase precedence              = PASS
```

La campagne s'arrête donc avant R1. Pool1 et Pool2 ne sont pas autorisés.
Le contraste `T3_A_F6 vs CURRICULUM` a joué zéro partie native et zéro partie
Q00. Le gain q200 n'est ni converti en Elo, ni réfuté par une cellule de force :
la condition de légitimité leaf preregistrée n'est pas entièrement établie.

## 2. Identités et preregistration

- T3-A/F6 SHA256 :
  `16e5db8fd78849bba12b158eee5c1da4ab170129d8aeac1b91ab7a40ad9d0bb2` ;
- CURRICULUM SHA256 :
  `319d174f4b548b1655aad4bb30d4c6dc86c08dd715c9c23f8b19ba1937dc0be1` ;
- RF1 SHA256 :
  `0d26ba50b668160b3da3e247cd4e1bd709c2cb7989b3b5877b9ea7deb34db58b` ;
- ordre F6 SHA256 :
  `cc4837e6829d937f7330f7bc71280f3ec0bed3f431e57b2664c651e1d763db4e` ;
- preregistration v2 Jass PR `#700`, merge
  `b6c747091aea265cd3f7ddeb4175fe05912ad255` ;
- implémentation Jass PR `#703`, merge/code
  `f559baede4047f47abe13724b16d1ad669c5f36f` ;
- mise en queue R0-v2 jass-control PR `#370`, merge `1ef67f568` ;
- readout terminal read-only jass-control PR `#371`, merge `7778835b0`.

Les bytes T3-A et CURRICULUM sont restés strictement inchangés. Il n'y a eu ni
refit, calibration, symétrisation, retrait de feature, D1, troisième bras,
scale tuning ni tuning search.

## 3. Chaîne terminale

| Étape | Job / attempt | Code | Résultat |
|---|---|---|---|
| R0-v2 causal | `cpx62-1648-l3-t3-f6-runtime-r0-v2` / `20260829T132226Z-f559baed` | `f559baede4047f47abe13724b16d1ad669c5f36f` | completed, exit `0`, gate 4 négatif |
| Readout terminal | `cpx62-1649-l3-t3-f6-runtime-r0-v2-terminal-readout` / `20260829T133232Z-f559baed` | même code | completed, exit `0`, verdict terminal authentifié |

Résultat source :
`r2:jass-data/runs/cpx62-1648-l3-t3-f6-runtime-r0-v2/20260829T132226Z-f559baed`.

Readout terminal :
`r2:jass-data/runs/cpx62-1649-l3-t3-f6-runtime-r0-v2-terminal-readout/20260829T133232Z-f559baed`.

## 4. Corpus R0-v2 target-blind

La sélection a été figée avant toute lecture T0/T3 :

- `40000` candidates, SHA256
  `cd6729a824b7d1987d3cd95a59baedab9fe279db2721b48f15f029df5d745aa3` ;
- génération `2026091701`, sélection `2026091702`, permutation/contextes
  `2026091703`, benchmark `2026091704` ;
- `4096` positions, P0/P1/P2/P3 = `1024/1024/1024/1024` ;
- black/white = `2042/2054` ;
- corpus FEN SHA256
  `ad246022f41d8fb2cf3cd98499a809909ce78c4d0119334c7b1b9736f680096d` ;
- `218066` identités uniques exclues, dont le corpus R0-v1 ;
- `98` occurrences candidates exclues ;
- overlap interdit `0` ;
- reads score/WDL/deep-label = `0/0/0`.

## 5. Gates 1 et 2

Le nouveau corpus reproduit les résultats positionnels positifs de v1 :

- replay parent/chemin/ordre : mismatch `0` ;
- q-score/WDL container : mismatch `0` ;
- TT/search state : mismatch `0` ;
- transposition issue de parents légaux distincts : PASS, profondeur `3` ;
- 66 F6 sous rotate180+colour-swap : mismatch rows `0` ;
- résiduel binary64 sous la même image : mismatch rows `0` ;
- saturation : `0`.

T3-A/F6 est donc positionnel, transposition-safe et n'utilise ni parent, ni
chemin, ni TT, ni search state, ni q-score/WDL caché sur ce contrat.

## 6. Gate 3 — drift relatif établi

Le résultat central de v2 est exact :

```text
engine_extra_drift_mismatch_count = 0 / 4096
max_abs_extra_drift_engine_cp     = 0
max_abs_extra_drift_float_cp      = 1.1368683772161603e-13
tolérance float preregistrée      = 1e-10 cp
```

Les distributions du drift absolu sont identiques :

| Évaluateur | min | moyenne | p50 | p95 | p99 | max | nonzero |
|---|---:|---:|---:|---:|---:|---:|---:|
| T0/CURRICULUM | 0 | 5.02734375 | 5 | 11 | 19.050000000000182 | 40 | 3871 |
| T3-A/F6 | 0 | 5.02734375 | 5 | 11 | 19.050000000000182 | 40 | 3871 |

La nouvelle hypothèse v2 est donc confirmée : **T3-A ne crée aucune asymétrie
supplémentaire par rapport au CURRICULUM exact qu'il remplace**. Le terminal v1
n'est pas réécrit : son exigence absolue restait négative, tandis que v2 répond
à un contraste relatif différent.

## 7. Gate 4 — arrêt preregistré

Le témoin terminal et le témoin tablebase gardent les priorités moteur :

- `terminal_precedence = true` ;
- `egdb_available = true` ;
- `tablebase_precedence = true`.

En revanche, le check preregistré depth-1 ne donne pas l'égalité exacte
`search(root) = max_child(-T3(child))` :

```text
negamax_depth1_score     = -51
negamax_single_inversion = false
```

Le rapport ne permet pas de transformer ce mismatch en simple bruit numérique
ou en calibration : il porte sur une égalité entière de sémantique search.
Conformément au gate gelé, ce seul FAIL interdit toute partie de force. La
parité Python/native complète, le profil de coût R0 et le dormant OFF/ON
postérieurs au gate n'ont pas été interprétés.

## 8. Garde et réponse terminale

Le readout authentifie :

- strength native `0`, Q00 `0` ;
- Pool1/Pool2 autorisés `false/false` ;
- post-freeze fits `0`, retunes `0`, calibrations `0` ;
- bake `false`, promotion autorisée/automatique `false/false`.

Réponse à la question : le T3-A/F6 frozen conserve exactement le drift du
baseline, mais il **n'a pas été légalement soumis au test Elo**, car son score
statique n'a pas satisfait le contrat depth-1 exact avec les sémantiques de
search. La conversion du gain q200 en force de jeu reste donc indéterminée.

Toute tentative future de modifier le témoin negamax, d'adapter la valeur à la
perspective search ou de lancer malgré ce FAIL constituerait une nouvelle
question scientifique et exigerait une nouvelle preregistration. Cette
campagne s'arrête ici, sans promotion.
