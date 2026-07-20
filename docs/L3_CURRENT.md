# L3-PURE — état courant et registre de décision

> **Mis à jour : 20 juillet 2026**  
> **Source de vérité active : ce document.** L’historique consolidé reste dans
> [`PROJECT_RESULTS.md`](PROJECT_RESULTS.md) et le contrat normatif de la lignée
> dans [`L3_PURE_PLAN.md`](L3_PURE_PLAN.md).
>
> **Statut scientifique :** `c0_retire_frontier_v1_flat; c1_q1_no_lead;
> c2_x1_no_lead; c3_mf_no_lead; 32cf_no_go_data_limited; recette_figee;
> p1_v2_no_clear_lead; p2_no_clear_improvement_or_unstable;
> stop_before_p3_redesign; d0_causal_profile_ready;
> d1_rc4_representation_screen_prepared_not_launched`.

## 1. Décision active

La lignée autonome est viable, mais le déficit de conversion n’est pas résorbé.
Tous les écrans DoE ont renvoyé `no_lead`; la recette générale reste figée :

- géométrie `8cf` ;
- Q00, 63 paramètres de recherche explicitement épinglés ;
- exploration `8 / 8 % / 60` ;
- labels WDL terminaux, ply-caps exclus ;
- fit logistic, `L2=3e-5` ;
- aucun teacher, aucune frontière mobile, aucun MMTO dans le train ;
- classe d’évaluation linéaire et interprétable.

La branche spécialiste retenue est `L3-IMBALANCE2-ROLE-V2`. Elle pondère par
position et rôle dans le domaine courant `|Δ hommes|=2` avec autant de dames :
côté `+2`, W/D/L=`1/2/4`; côté `−2`, W/D/L=`4/2/1`; hors domaine, poids `1`.
Scan et Gen2 restent des thermomètres, jamais des données de train.

**Décision définitive après P2 d10 : arrêter avant P3 et redessiner le
mécanisme.** La consolidation G4→G8 ne montre aucun progrès large ou significatif.
`promotion_authorized=false`, `p3_authorized=false` et aucun job n’est chaîné.
**P3 n’est pas autorisé.**

D0 est maintenant terminé. Le prochain bloc préparé est **D1-A RC4**, un écran
contrôle contre quatre interactions linéaires conditionnées par le rôle matériel.
Il n’utilise aucun nouveau self-play pour l’entraînement et ne peut pas autoriser
D1-B automatiquement.

## 2. Campagnes et diagnostics publiés

| Campagne | Job | Palier | Résultat durable |
|---|---|---|---|
| baseline générale | `cpx62-0842` | P1, G1–G4 d8 | saine, référence de pente |
| imbalance2 V1 | `ccx33-0847` | P1, G1–G4 d8 | near-flat |
| role-aware V2 | `ccx33-0852` | P1, G1–G4 d8 | crédit plus propre, pas de lead établi |
| comparaison V1/V2 | `0853→0857` | A64/B64 d10 | `V2_NO_CLEAR_LEAD_AT_P1` |
| role-aware V2 | `ccx33-0859` | P2, G5–G8 d10 | chaîne complète, aucune promotion |
| assess P2 | `0864→0869` | A64/B64 d10 | instable, plateau non confirmé |
| difficulté matérielle | `cpx62-0862` | EGDB + Scan d10 | référence des 18 strates |
| consolidation P2 | `ccx33-0870` | G4→G8 | arrêt avant P3 |
| diagnostic causal | `cpx62-0871` | 30 sentinelles, 360 recherches | `D0_CAUSAL_PROFILE_READY` |

## 3. Verdict P1 powered — V1 contre role-aware V2

La comparaison powered utilise les mêmes A64/B64. Après exclusion symétrique de
`plateau-a:1100`, elle conserve `n=1151` sur A et `n=1152` sur B.

| coût `2L+D` à G4 | pool A | pool B | global |
|---|---:|---:|---:|
| V1 | 0,951 | 0,965 | **0,958** |
| V2 role-aware | 0,963 | 0,929 | **0,946** |

Delta V2−V1 : **−0,013**, IC95 **[−0,061 ; +0,035]**. L’effet est sous le seuil
`0,02` et non significatif. V2 a été conservée comme décision de programme pour
sa sémantique, pas comme preuve de supériorité.

## 4. Verdict définitif P2 — G4 contre G8

`ccx33-0870` a appliqué la même exclusion symétrique à G4–G8 et joint la référence
EGDB/Scan uniquement pour l’interprétation.

| Mesure | Résultat | Lecture |
|---|---:|---|
| delta macro égal par strate | **+0,0053** | légère dégradation |
| IC95 bootstrap stratifié | **[−0,0426 ; +0,0526]** | contient zéro |
| strates non dégradées | **9 / 18** | sous le seuil 12/18 |
| delta pool A | **+0,0209** | dégradation |
| delta pool B | **−0,0104** | légère amélioration |
| plateau confirmé | **non** | instabilité persistante |

```text
P2_NO_CLEAR_IMPROVEMENT_OR_UNSTABLE
recommendation_for_review=STOP_BEFORE_P3_REDESIGN
promotion_authorized=false
p3_authorized=false
automatic_next_job=null
```

## 5. D0 causal — `cpx62-0871`

D0 a réutilisé les artefacts immuables `0852`, `0853`, `0859`, `0862` et `0864`.
Il a sélectionné 30 positions sentinelles puis analysé G4, G8 et Scan aux
profondeurs 8, 10, 12 et 14, soit **360 recherches statiques**.

Exécution :

- début : `2026-07-20T19:33:15Z` ;
- fin : `2026-07-20T19:38:41Z` ;
- durée : 5 min 26 s ;
- exit code : 0 ;
- résultat : `D0_CAUSAL_PROFILE_READY`.

Profil d’hypothèses :

| Hypothèse | Cas |
|---|---:|
| `REPRESENTATION_OR_OBJECTIVE_CANDIDATE` | **7 / 30** |
| `SEARCH_AND_EVAL_MIXED` | **23 / 30** |
| `SEARCH_HORIZON_CANDIDATE` | **0 / 30** |
| `TRAINING_CREDIT_OR_DISTRIBUTION_CANDIDATE` | **0 / 30** |

Ces catégories sont des heuristiques diagnostiques, pas des preuves causales.
L’absence de cas pur d’horizon ne justifie pas de modifier d’abord la recherche.

Artefact :

```text
r2:jass-data/runs/cpx62-0871-l3-imbalance2-d0-diagnostic/20260720T193310Z-bced44e7
```

## 6. D1-A RC4 — préparé, non lancé

Question : quatre gradients linéaires conditionnés par le rôle courant peuvent-ils
améliorer la conversion sans modifier la recherche ni les données ?

Le contrôle et RC4 sont refittés depuis zéro sur les **mêmes octets** du corpus
`g4-source` de `0852`, après le même split et la même pondération role-aware V2.
Aucun nouveau self-play n’est généré pour le train et Scan n’est pas un teacher.

RC4 ajoute, uniquement lorsque l’écart courant est exactement de deux hommes avec
le même nombre de dames :

1. delta de mobilité sûre ;
2. confinement du défenseur ;
3. marge de course à promotion ;
4. pression d’échange immédiate.

L’implémentation expérimentale est appliquée à une copie isolée du SHA mergé. Le
bras contrôle reste byte-identique à la source revue et le code de production ne
reçoit pas ces features tant qu’elles ne sont pas validées.

### 6.1 Évaluation

- nouveaux pools indépendants **C64/D64** ;
- seed `314159`, 18 strates, 64 positions par strate et par pool ;
- d10, `maxplies=400`, mêmes positions et même budget ;
- mesure principale : macro-moyenne égale par strate du coût `2L+D` ;
- replay d14 des 30 sentinelles D0 ;
- garde généraliste de 64 paires à d8 ;
- garde de débit RC4/contrôle ≥ `0,95`.

### 6.2 Gate préenregistré

Le volet principal exige simultanément :

- delta RC4−contrôle ≤ `−0,020` ;
- borne haute IC95 ≤ `0` ;
- aucun pool C/D dégradé ;
- au moins 12/18 strates non dégradées ;
- pire régression locale ≤ `0,10`.

Le gate mécanistique exige au moins 4/7 sentinelles représentation/objectif
corrigées vers le coup Scan d14 et au plus deux nouvelles divergences.

Un échec produit `D1_RC4_NO_GO`. Un succès produit seulement
`D1_RC4_SCREEN_PASS_REVIEW_D1B`. Dans les deux cas :

```text
d1b_authorized=false
training_continuation_authorized=false
promotion_authorized=false
automatic_next_job=null
```

Wrappers interchangeables, un seul à exécuter :

```text
jobs/prepared/l3-imbalance2-d1-rc4-20260720/ccx33-l3-imbalance2-d1-rc4.sh
jobs/prepared/l3-imbalance2-d1-rc4-20260720/cpx62-l3-imbalance2-d1-rc4.sh
```

## 7. Prochaines actions

1. faire relire et merger la PR D1-RC4 après CI verte ;
2. renseigner le SHA mergé et lancer un seul wrapper sur la première box libre ;
3. examiner le verdict C64/D64, les sentinelles, le débit et le garde généraliste ;
4. n’envisager D1-B qu’après une nouvelle décision humaine explicite ;
5. si RC4 échoue, préparer un pilote **search-only** séparé ;
6. ne jamais relancer P3 à recette role-aware V2 identique.

## 8. Artefacts de référence

- P1 V2 : `r2:jass-data/runs/ccx33-0852-l3-imbalance2-role-v2-p1/20260720T073236Z-61839d1d` ;
- P2 V2 : `r2:jass-data/runs/ccx33-0859-l3-imbalance2-role-v2-p2/20260720T105918Z-a0d2f238` ;
- référence : `r2:jass-data/runs/cpx62-0862-l3-imbalance2-a64-b64-difficulty-reference/20260720T130310Z-59940065` ;
- récupération P2 : `r2:jass-data/runs/ccx33-0869-p2-plateau-recover/20260720T152038Z-566943ea` ;
- consolidation : `r2:jass-data/runs/ccx33-0870-l3-imbalance2-p2-consolidate/20260720T175742Z-0e657bba` ;
- D0 : `r2:jass-data/runs/cpx62-0871-l3-imbalance2-d0-diagnostic/20260720T193310Z-bced44e7`.

Les URI exactes et SHA restent dans les manifests R2 et les statuts GitOps. Aucun
résultat volumineux n’est re-committé dans Git.
