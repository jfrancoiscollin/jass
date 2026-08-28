# L3 — état courant et registre de décision

> **Mis à jour : 28 août 2026**
> **Source de vérité active : ce document.**
>
> Historique détaillé : Git, `PROJECT_RESULTS.md`, protocoles sous `docs/experiments/` et archives L3. Roadmap active : [`L3_TEACHER_DISTILLATION_ROADMAP.md`](L3_TEACHER_DISTILLATION_ROADMAP.md).

---

## 1. Champion de production

### `CURRICULUM` — champion courant

Aucun candidat post-CURRICULUM n'est promu.

- raw/decompressed `.pjtw` SHA256 : `319d174f4b548b1655aad4bb30d4c6dc86c08dd715c9c23f8b19ba1937dc0be1` ;
- source R2 : `r2:jass-data/runs/cpx62-1341-jass-megacorpus-arm-d-fit-v1/20260814T191555Z-18c38a33/artefacts/D-c-prior-then-current.pjtw.gz`.

Aucun runtime joint, aucune partie de force/Elo et aucune promotion n'ont été autorisés par la campagne Q1.

---

## 2. Conclusion scientifique actuelle

La campagne preregistrée [`experiments/L3_JOINT_TD_DEEP_FRESH_CONFIRMATION_V1_20260828.md`](experiments/L3_JOINT_TD_DEEP_FRESH_CONFIRMATION_V1_20260828.md), merge SHA `b280fc1f4878133a41168f4bbc6a537eec526cdc`, est **terminale**.

Verdict primaire :

```text
JOINT_TD_DEEP_FRESH_NOT_CONFIRMED
```

Le stack offline `C0 = T0 + D1 + phase + couleur`, qui battait D1 sur le DEV q1000 de M3, **ne confirme pas contre q200 fresh**. Il améliore fortement T0 et améliore le top-hit par rapport à D1, mais il perd significativement en pairwise contre D1 et échoue dans trois phases sur quatre ainsi que dans les deux couleurs.

En revanche, le candidat PatternEval pur `A6-G0` passe son gate secondaire preregistré :

```text
A6_G0_DEEP_TRANSFER_CONFIRMED = TRUE
```

Donc :

1. la meilleure recette de transfert pur-T donne un petit gain deep fresh, réel et robuste ;
2. la complémentarité T+D observée sur q1000 DEV **ne généralise pas sous la forme C0** au critère primaire q200 ;
3. D1 reste nettement meilleur que T0/A6/B1/C0 en pairwise q200 ;
4. q1000 reste de très loin le meilleur diagnostic, donc le signal de recherche existe toujours mais reste largement non distillé ;
5. la campagne s'arrête ici avant runtime/Elo/promotion.

---

## 3. Upstream et freeze immuables

Prereg Q1 : `b280fc1f4878133a41168f4bbc6a537eec526cdc`.

Stage F :

- job `cpx62-1616-l3-joint-td-candidate-freeze-v1` ;
- attempt `20260828T104336Z-3348397a` ;
- Jass code SHA `3348397a0459b8c3335d46a70af5755d6e9488e0` ;
- verdict `JOINT_TD_CANDIDATE_FREEZE_READY` ;
- candidate-freeze SHA256 `7f5d28b8a3ea810bde0969959b2fdd01a2e778b9a63e602125c796432c76bf40` ;
- aucun label deep/fresh lu avant freeze ; aucun refit D1/A6 ; aucun selfplay/strength/promotion.

Identités gelées :

| ID | Candidat | SHA256 |
|---|---|---|
| S0 | T0 / CURRICULUM | `319d174f4b548b1655aad4bb30d4c6dc86c08dd715c9c23f8b19ba1937dc0be1` |
| S1 | D1 scellé | `e91a55500713154f50be74db5d699b64d7684e1c078725d09e1d15e713549b49` |
| S2 | A6-G0 | `271733adb8441630e1bae77b85951c05caa452107d3e8af4782f577347be06ed` |
| S3 | B1 manifest | `052090887dd45f40f14cdb2a336c34b3c5d27c61dd483f82349c3086cd9577c7` |
| S4 | C0 artifact | `2b51e8d36f3d0241ca5254de68a686808b6dbf619211c5bbdcc02879921493ba` |

B1 et C0 reproduisent exactement les métriques DEV 1614 à tolérance `1e-12` avant toute sélection fresh.

---

## 4. Cohort Q1 fresh

Sélection :

- job `cpx62-1617-l3-joint-td-q1-select-v7` ;
- attempt `20260828T114236Z-2034c5c9` ;
- Jass code SHA `2034c5c98f3e3260254dd7449bc5032dd125e581` ;
- verdict `JOINT_TD_Q1_SELECTION_READY` ;
- seed `2026090420` ; target-blind `true` ;
- exactement `4000` parents : P0/P1/P2/P3 = `1000/1000/1000/1000` ;
- overlap canonique M3 = `0`, M5 = `0` ;
- lectures q1000/q50/q200 avant sélection = `0` ; fits/refits/strength/promotion = `0`.

Le cohort `1617-v7` est immuable ; tous les retries techniques l'ont réutilisé.

---

## 5. Teacher/readout Q1 terminal

Le run scientifique ayant produit les scores et le `q1-report.json` est :

- job source `cpx62-1624-l3-joint-td-q1-teacher-readout-v5` ;
- attempt `20260828T143246Z-8df8f407` ;
- Jass code SHA `8df8f4073109b2016e5425a5ac18ec3ac9008c85` ;
- q1000/q50/q200 = `1000/50000/200000` nœuds exacts ; book OFF ; 1 thread ; Engine/TT/search-state frais par sibling et budget ;
- zéro post-freeze fit/refit, selfplay, strength, runtime/Elo ou promotion.

`1624` a terminé techniquement en erreur **après génération du q1-report**, lors d'une augmentation de reporting non scientifique. Le rapport déjà produit a été authentifié et republié sans recalcul scientifique par :

- job `cpx62-1625-l3-joint-td-q1-terminal-recover-v1` ;
- attempt `20260828T154226Z-8df8f407` ;
- exit `0` ;
- control recovery merge SHA `569540fb5d7c36af5e25ca39f21dad45064ad98f` ;
- verdict republié inchangé `JOINT_TD_DEEP_FRESH_NOT_CONFIRMED` ;
- recovery = read-only, teacher rerun `false`, rescoring `false`, fit/refit `false`, runtime/Elo `false`, promotion `false`.

---

## 6. Support gate

Support PASS :

- sélectionnés : `4000` ;
- acceptés : `3397` ;
- stable pairs : `96862` ;
- acceptés par phase : P0 `903`, P1 `929`, P2 `928`, P3 `637` ;
- acceptés par couleur : white `1710`, black `1687` ;
- chaque parent accepté possède au moins une paire stable ;
- overlap interdit = `0` ;
- candidate-freeze auth = PASS.

Tous les seuils preregistrés sont satisfaits.

---

## 7. Métriques q200 fresh terminales

Toutes les lignes utilisent exactement les mêmes `3397` parents acceptés et les mêmes `96862` paires stables.

| Modèle | Pairwise q200 | Top-hit |
|---|---:|---:|
| T0 | `0.6084468414` | `0.5540673143` |
| A6-G0 | `0.6171234955` | `0.5643214601` |
| B1 | `0.7089233688` | `0.6452752429` |
| C0 | `0.7184044328` | `0.6764792464` |
| D1 | **`0.7341739720`** | `0.6529290550` |
| q1000 | **`0.9357350801`** | **`0.8591894809`** |

### C0 vs D1 — gate primaire

Pairwise :

- delta mean `-0.0157695392` = **−1.577 pp** ;
- CI95 `[-0.0221178885 ; -0.0095172194]` ;
- `P(delta>0)=0`.

Top-hit :

- delta mean `+0.0235501913` = **+2.355 pp** ;
- CI95 `[+0.0088313218 ; +0.0385634383]` ;
- `P(delta>0)=0.99909`.

Pairwise C0−D1 par phase :

- P0 `+0.0114735255` ;
- P1 `-0.0188953024` ;
- P2 `-0.0330197067` ;
- P3 `-0.0246996774`.

Par couleur : black `-0.0111184352`, white `-0.0203580845`.

Ainsi trois gates primaires échouent : CI pairwise C0−D1, positivité dans les quatre phases, positivité dans les deux couleurs. Les gates support, top-hit C0−D1, pairwise C0−T0, identité des candidats et absence d'activité post-freeze passent.

C0−T0 pairwise : mean `+0.1099575914`, CI95 `[+0.1041810992 ; +0.1157831291]`.

Ratios preregistrés :

- `R_C0_from_D = -0.0782370139` ;
- `R_C0_from_T = 0.3359656058`.

### A6-G0 — gate secondaire

A6−T0 pairwise : mean `+0.0086766542`, CI95 `[+0.0071898443 ; +0.0101730833]`.

A6−T0 top-hit : mean `+0.0102541458`, CI95 `[+0.0054950446 ; +0.0151604357]`.

Les deltas pairwise sont positifs dans P0/P1/P2/P3 et dans les deux couleurs. Verdict secondaire : `A6_G0_DEEP_TRANSFER_CONFIRMED = TRUE`.

Diagnostics : B1−D1 pairwise mean `-0.0252506032` ; C0−B1 mean `+0.0094810640` ; q1000−C0 mean `+0.2173306474`.

---

## 8. Décision terminale

```text
Primary Joint T+D C0 = NOT CONFIRMED
Secondary pure-T A6 = CONFIRMED
Runtime/Elo          = STOP
Promotion            = STOP
Champion             = CURRICULUM
```

Le résultat q1000-DEV de C0 était donc un signal réel d'ajustement au teacher, mais pas une preuve de généralisation q200. **Il est interdit de lancer un runtime joint, un gate Elo ou une promotion à partir de cette campagne.** Une nouvelle expérience nécessiterait une preregistration séparée.

Le cohort Q1 est désormais un cohort de validation consommé : aucun tuning, recalibrage ou sélection future ne doit être effectué dessus.

---

## 9. Priorités scientifiques après Q1

1. Ne pas poursuivre C0 tel quel : son avantage q1000 DEV ne passe pas le gate pairwise D1 sur q200 fresh.
2. Conserver A6-G0 comme preuve qu'un transfert pur PatternEval est possible, mais le gain reste petit ; tout test de force éventuel nécessite une prereg séparée.
3. Garder D1 comme meilleure représentation statique actuellement observée contre q200 fresh, sans en déduire une promotion runtime automatique.
4. Exploiter le grand headroom q1000 (`0.9357` pairwise) pour rechercher, hors Q1, des observables/architectures capables de préserver ce signal.
5. Pour toute future architecture joint/non-linéaire, sélectionner/tuner uniquement sur des données autorisées distinctes de Q1, puis réserver un nouveau cohort fresh pour confirmation.

---

## 10. Règles verrouillées

1. Technique ≠ science.
2. q1000 imitation ≠ q200 deep accuracy ≠ Elo.
3. Q1 est consommé et ne peut jamais devenir un jeu de tuning.
4. Aucun post-freeze fit/refit n'est autorisé rétroactivement.
5. Aucun runtime/Elo/promotion n'est autorisé par le verdict Q1.
6. `CURRICULUM` reste champion.
7. Toute étape future doit avoir sa propre preregistration et ses propres données de sélection/confirmation.
