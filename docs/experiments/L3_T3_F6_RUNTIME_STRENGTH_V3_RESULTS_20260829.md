# L3 — T3/F6 Runtime Strength v3 — résultat terminal

Date : 29 août 2026. Statut : **terminal R0-v3 sur support mécanique
insuffisant, avant toute lecture d'évaluation v3 et avant toute partie de
force**.

Protocole immuable :
[`L3_T3_F6_RUNTIME_STRENGTH_V3_20260829.md`](L3_T3_F6_RUNTIME_STRENGTH_V3_20260829.md).
Les terminaux v1, v2 et l'autopsie negamax restent inchangés.

## 1. Verdict

```text
R0_V3_RUNTIME_SUPPORT_INCONCLUSIVE
```

Le générateur preregistré n'a trouvé que `5` racines P0 mécaniquement isolées
parmi `26004` positions P0 uniques admissibles, contre le minimum gelé de
`32`. La règle v3 interdit de relâcher le prédicat, changer les seeds, augmenter
post-hoc le pool ou substituer des témoins. La sélection s'est donc arrêtée
avant les gates d'évaluation.

Ce terminal n'est ni un défaut T3-A, ni un rejet du signal F6, ni un résultat
de force. Il signifie que le support du sous-gate 4A n'était pas suffisant sous
la recette target-blind preregistrée.

## 2. Chaîne authentifiée

| Étape | Job / attempt | Code | Résultat |
|---|---|---|---|
| R0-v3 | `cpx62-1652-l3-t3-f6-runtime-r0-v3` / `20260829T152726Z-880fccbe` | `880fccbec5929588e4e4120a2cf81ce5067bcd71` | completed, exit `0`, support inconclusif |
| Readout read-only | `cpx62-1653-l3-t3-f6-runtime-r0-v3-readout-v1` / `20260829T153756Z-880fccbe` | même code | completed, exit `0`, cause et quotas authentifiés |

Résultats :

- `r2:jass-data/runs/cpx62-1652-l3-t3-f6-runtime-r0-v3/20260829T152726Z-880fccbe` ;
- `r2:jass-data/runs/cpx62-1653-l3-t3-f6-runtime-r0-v3-readout-v1/20260829T153756Z-880fccbe`.

Preregistration v3 : Jass PR `#710`, merge
`b326bb6610a7eb9b9b997540c1dbb0508f433ca0`. Implémentation : Jass PR
`#711`, merge/code `880fccbec5929588e4e4120a2cf81ce5067bcd71`.
Soumission : jass-control PR `#374`, merge
`29521bc430f595e32bb261d027b126f07a26c4f1`. Readout : PR `#375`, merge
`76bf680c6548b61ed01fd06e7d91c2d863adfc4d`.

## 3. Bytes immuables

- T3-A/F6 SHA256 :
  `16e5db8fd78849bba12b158eee5c1da4ab170129d8aeac1b91ab7a40ad9d0bb2` ;
- CURRICULUM SHA256 :
  `319d174f4b548b1655aad4bb30d4c6dc86c08dd715c9c23f8b19ba1937dc0be1` ;
- RF1 SHA256 :
  `0d26ba50b668160b3da3e247cd4e1bd709c2cb7989b3b5877b9ea7deb34db58b` ;
- ordre F6 SHA256 :
  `cc4837e6829d937f7330f7bc71280f3ec0bed3f431e57b2664c651e1d763db4e`.

Les artefacts T3-A et CURRICULUM ont été authentifiés avant la sélection. Il
n'y a eu ni refit, retune, calibration, symétrisation, changement F6/F2,
changement search, D1, troisième bras, bake ou promotion.

## 4. Sélection target-blind et support

- candidates générées et rejouées : `120000` ;
- lignes de classification mécanique : `120000` ;
- uniques après exclusions : `119699` ;
- identités interdites agrégées : `222175` ;
- occurrences candidates exclues : `295` ;
- doublons candidates : `6` ;
- overlap interdit : `0` ;
- reads score/WDL/deep/runtime : `0/0/0/0` ;
- seed génération : `2026092101` ;
- seeds sélection/permutation/benchmark/isolated/trace :
  `2026092102 / 2026092103 / 2026092104 / 2026092105 / 2026092106`.

Le premier quota vérifié est P0 : `26004` uniques, `5` isolées, minimum `32`.
Le sélecteur fail-closed s'arrête à ce premier déficit ; il ne publie donc pas
de quotas interprétables P1/P2/P3 et aucune sélection `4096` n'est constituée.

## 5. Gates v3 non atteints

| Élément | Statut v3 |
|---|---|
| Corpus `4096`, `1024`/phase | non constitué |
| Gate 1 position/transposition | non exécuté v3 |
| Gate 2 F6/résiduel | non exécuté v3 |
| Gate 3 drift relatif | non exécuté v3 |
| Gate 4A leaf isolée | support `5/32` en P0, test non exécuté |
| Gate 4B search réel | non exécuté v3 |
| Gate 5 terminal/TB | non exécuté v3 |
| Gate 6 Python/native | non exécuté v3 |
| Gate 7 dormant OFF/ON | non exécuté v3 |
| Gate 8 coût runtime | non exécuté v3 |

Les métriques positives v2 restent des faits upstream : extra drift engine
mismatch `0`, max extra drift engine `0 cp`, max extra drift float
`1.1368683772161603e-13 cp`. Elles ne sont pas présentées comme une mesure v3.
La parité complète et le profil runtime v3 n'ont produit aucun résultat.
Le binaire de force n'a pas été publié par ce chemin terminal ; aucun SHA
executable n'est donc revendiqué pour Pool1/Pool2.

## 6. Force et décision

- Pool1 native : `0` game, non autorisé ;
- Pool2 native : `0` game, non autorisé ;
- Q00 : `0` game ;
- chained bootstrap : non exécuté ;
- promotion/bake : `false/false`.

Réponses terminales :

1. V3 **n'établit pas** le contrat leaf complet sous les vraies semantics Jass,
   car son support mécanique preregistré est insuffisant avant les gates. Elle
   ne démontre aucun défaut spécifique de T3-A.
2. La conversion du gain q200 en force native contre CURRICULUM reste
   **inconnue** : aucune partie causale n'a été légalement jouée.

Toute nouvelle recette permettant d'obtenir assez de témoins isolés serait une
nouvelle question scientifique et demanderait une preregistration séparée. Le
terminal v3 ne peut pas être réparé ou relâché post-hoc.
