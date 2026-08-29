# L3 — T3/F6 Runtime Strength v1 — résultat terminal

Date : 29 août 2026. Statut : **terminal en R0, avant toute partie de force**.

Protocole immuable :
[`L3_T3_F6_RUNTIME_STRENGTH_V1_20260829.md`](L3_T3_F6_RUNTIME_STRENGTH_V1_20260829.md).

## 1. Verdict

Le gate de production leaf n'est pas établi :

```text
R0_PRODUCTION_LEAF_CONTRACT_NOT_ESTABLISHED
```

Cause scientifique exacte :

```text
FROZEN_CURRICULUM_FAILS_PREREGISTERED_COLOUR_IMAGE_EXACTNESS
```

La campagne s'arrête donc avant R1. `Pool1` et `Pool2` ne sont pas autorisés.
Le contraste causal de force `T3_A_F6 vs CURRICULUM` n'a joué aucune partie ;
la question Elo reste indéterminée dans ce protocole.

Ce résultat n'invalide ni le transfert q200 de F6 ni la sûreté positionnelle
board+STM déjà observée avant l'assert négatif. Il établit que l'évaluateur
composé exact imposé par la preregistration ne satisfait pas tout le contrat de
perspective/couleur exigé pour devenir un leaf evaluator de production.

## 2. Identités immuables

- T3-A/F6 SHA256 :
  `16e5db8fd78849bba12b158eee5c1da4ab170129d8aeac1b91ab7a40ad9d0bb2` ;
- CURRICULUM SHA256 :
  `319d174f4b548b1655aad4bb30d4c6dc86c08dd715c9c23f8b19ba1937dc0be1` ;
- RF1 SHA256 :
  `0d26ba50b668160b3da3e247cd4e1bd709c2cb7989b3b5877b9ea7deb34db58b` ;
- ordre F6 SHA256 :
  `cc4837e6829d937f7330f7bc71280f3ec0bed3f431e57b2664c651e1d763db4e` ;
- preregistration Jass PR `#693`, merge `60e676867` ;
- implémentation native Jass PR `#695`, merge
  `1e2a1b9ac5b154dca1059c0eb6c6d95b300aae5c` ;
- correction technique des entrypoints Jass PR `#696`, code R0
  `362d1a09bdb0633ef783f4e4048721d8ae6ee980` ;
- readout terminal jass-control PR `#369`.

Le chemin natif reste dormant par défaut. Il ne s'active que par
`JASS_T3_F6_MODEL=<artifact>` et ne modifie que l'évaluation statique de feuille.
Aucun bake ni promotion n'est effectué.

## 3. Chaîne R0

| Étape | Job / attempt | Résultat |
|---|---|---|
| Premier R0 | `cpx62-1641-l3-t3-f6-runtime-r0-v1` / `20260829T104356Z-1e2a1b9a` | panne technique d'import avant science |
| R0 propre | `cpx62-1644-l3-t3-f6-runtime-r0-v1` / `20260829T112915Z-362d1a09` | sélection PASS, arrêt sur l'invariance native |
| Diagnostic de phase | `cpx62-1645-l3-t3-f6-runtime-r0-diagnostic-slim-v2` / `20260829T113937Z-362d1a09` | phase `invariance-and-native-parity` authentifiée |
| Log ciblé | `cpx62-1646-l3-t3-f6-runtime-r0-invariance-log-v1` / `20260829T114956Z-362d1a09` | `colour-image T0 drift` |
| Readout terminal | `cpx62-1647-l3-t3-f6-runtime-r0-terminal-readout-v1` / `20260829T120556Z-362d1a09` | verdict terminal R0 |

Le readout `1647` est `completed`, exit `0`, `technical_failure=false`. Résultat
immuable :
`r2:jass-data/runs/cpx62-1647-l3-t3-f6-runtime-r0-terminal-readout-v1/20260829T120556Z-362d1a09`.

L'échec `1641` était purement technique : les scripts Python exécutés
directement ne bootstrapaient pas la racine du dépôt. La correction minimale a
ajouté le bootstrap standard aux trois entrypoints et des tests subprocess ;
elle n'a changé ni l'artefact, ni les features, ni la science preregistrée.

## 4. Corpus R0 target-blind

La sélection de `1644` a passé avant toute mesure d'évaluation :

- `4096` positions, `1024` dans chacune de P0/P1/P2/P3 ;
- seed de sélection `2026090902` ;
- seed de permutation/contextes `2026090903` ;
- seed de benchmark `2026090904` ;
- overlap interdit `0` ;
- reads score `0`, WDL `0`, deep labels `0`.

Le corpus n'a donc pas été choisi à partir d'un score T0/T3, d'un résultat de
partie ou d'un label profond.

## 5. Probe séquentiel fail-closed

Le binaire s'arrête au premier assert négatif. Avant cet arrêt, il a établi :

- indépendance exacte à l'identité du parent, au chemin et à l'ordre des
  siblings ;
- transposition explicite obtenue par deux parents/chemins légaux distincts,
  avec F6 et score T3 identiques ;
- indépendance à la TT et au search state ;
- indépendance aux bytes q-score/WDL du conteneur de test ;
- égalité exacte des 66 features F6 sous rotate180+colour-swap ;
- égalité bit à bit du résiduel float64 sous cette même image.

Le premier assert négatif est exactement :

```text
t3_f6_invariance_probe: colour-image T0 drift
```

Le composant CURRICULUM gelé n'est donc pas identique sous la transformation
exigée par la section 3.2. Comme le résiduel F6 est, lui, identique et que
`T3 = T0 - residual_F6`, T3 hérite nécessairement du drift T0.

Le check search depth-1 du signe negamax se trouvait après cet assert et n'a
pas été atteint. Il est enregistré comme **non exécuté**, pas comme un échec.
La parité Python/native sur les `4096` lignes et le profil de coût étaient eux
aussi postérieurs au gate et n'ont pas été interprétés.

## 6. Garde scientifique

Le readout terminal authentifie :

- preregistration inchangée après résultat ;
- fit/refit post-freeze `0` ;
- retune `0` ;
- calibration `0` ;
- parties native `0` ;
- parties Q00 `0` ;
- Pool1 autorisé `false`, Pool2 autorisé `false` ;
- bake `false`, promotion autorisée `false`, promotion automatique `false`.

Modifier après coup l'égalité couleur/perspective en une règle relative au
baseline, réparer les bytes CURRICULUM, ou choisir un nouveau contrat serait
une nouvelle décision scientifique. Cela exige une nouvelle preregistration et
n'est pas autorisé par cette campagne après lecture du résultat R0.

## 7. Réponse à la question terminale

La campagne ne peut pas conclure si le gain q200 devient de l'Elo : le candidat
exact s'arrête au contrat de production avant que le contraste de force causal
ne soit légalement mesurable. CURRICULUM reste le champion inchangé ; T3-A reste
un artefact scientifique frozen et un chemin runtime dormant, sans promotion.
