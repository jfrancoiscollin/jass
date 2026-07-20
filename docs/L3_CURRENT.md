# L3-PURE — état courant et registre de décision

> **Mis à jour : 20 juillet 2026**  
> **Source de vérité active : ce document.** L’historique consolidé reste dans
> [`PROJECT_RESULTS.md`](PROJECT_RESULTS.md), les verdicts immuables sous
> [`archives/l3/`](archives/l3/) et le contrat normatif dans
> [`L3_PURE_PLAN.md`](L3_PURE_PLAN.md).
> 
> **Statut scientifique :** `c0_retire_frontier_v1_flat; c1_q1_no_lead;
> c2_x1_no_lead; c3_mf_no_lead; 32cf_no_go_data_limited; recette_figee;
> p1_v2_no_clear_lead; p2_no_clear_improvement_or_unstable;
> stop_before_p3_redesign; d0_causal_profile_ready; d1_rc4_no_go;
> d1x_rc4_autopsy_prepared_not_launched`.

## 1. Décision active

La lignée autonome est viable, mais le déficit de conversion n’est pas résorbé.
La recette générale reste figée :

- géométrie `8cf` ;
- Q00 et 63 paramètres de recherche explicitement épinglés ;
- exploration `8 / 8 % / 60` ;
- labels WDL terminaux, ply-caps exclus ;
- fit logistic, `L2=3e-5` ;
- aucun teacher, aucune frontière mobile, aucun MMTO dans le train ;
- classe d’évaluation linéaire et interprétable.

La branche spécialiste conservée comme référence est `L3-IMBALANCE2-ROLE-V2`.
Elle pondère le domaine courant `|Δ hommes|=2` avec autant de dames : côté `+2`,
W/D/L=`1/2/4`; côté `−2`, W/D/L=`4/2/1`; hors domaine, poids `1`. Scan et Gen2
restent des thermomètres, jamais des données de train.

**P3 reste interdit.** La consolidation G4→G8 a produit
`P2_NO_CLEAR_IMPROVEMENT_OR_UNSTABLE`. Le pilote de représentation RC4 a ensuite
produit **`D1_RC4_NO_GO`** : aucun gain de conversion, aucune sentinelle ciblée
corrigée, débit sous le seuil et garde généraliste échouée.

La prochaine action autorisée est **D1-X**, une autopsie read-only de RC4. Elle
mesure l’activité réelle des quatre features, leurs poids et la dérive du refit,
puis localise les régressions C64/D64 et généralistes. Elle ne peut autoriser ni
entraînement, ni pilote search, ni promotion.

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
| représentation RC4 | `cpx62-0872` | contrôle/RC4, C64/D64 | **`D1_RC4_NO_GO`** |

## 3. Verdict P1 powered — V1 contre role-aware V2

La comparaison powered utilise les mêmes A64/B64. Après exclusion symétrique de
`plateau-a:1100`, elle conserve `n=1151` sur A et `n=1152` sur B.

| coût `2L+D` à G4 | pool A | pool B | global |
|---|---:|---:|---:|
| V1 | 0,951 | 0,965 | **0,958** |
| V2 role-aware | 0,963 | 0,929 | **0,946** |

Delta V2−V1 : **−0,013**, IC95 **[−0,061 ; +0,035]**. L’effet est sous le seuil
`0,02` et non significatif. V2 a été conservée pour sa sémantique, pas comme
preuve de supériorité.

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
Il a analysé 30 sentinelles avec G4, G8 et Scan aux profondeurs 8, 10, 12 et 14,
soit **360 recherches statiques**.

- début : `2026-07-20T19:33:15Z` ;
- fin : `2026-07-20T19:38:41Z` ;
- durée : 5 min 26 s ;
- résultat : `D0_CAUSAL_PROFILE_READY`.

| Hypothèse | Cas |
|---|---:|
| `REPRESENTATION_OR_OBJECTIVE_CANDIDATE` | **7 / 30** |
| `SEARCH_AND_EVAL_MIXED` | **23 / 30** |
| `SEARCH_HORIZON_CANDIDATE` | **0 / 30** |
| `TRAINING_CREDIT_OR_DISTRIBUTION_CANDIDATE` | **0 / 30** |

Ces catégories sont heuristiques. L’absence de cas pur d’horizon ne prouve pas
que la recherche est hors cause, mais interdisait de modifier simultanément
représentation et recherche.

## 6. D1-A RC4 — verdict final `D1_RC4_NO_GO`

D1-A a refitté contrôle et RC4 depuis zéro sur les mêmes octets du corpus G4 de
`0852`, avec le même split, les mêmes labels, la même pondération role-aware V2
et le même optimiseur. RC4 ajoutait quatre extras dans le domaine courant exact
`|Δ hommes|=2`, dames égales : mobilité sûre, confinement du défenseur, marge de
course à promotion et pression d’échange.

Évaluation : C64/D64 indépendants, 18 strates × 64 positions par pool, d10,
`maxplies=400`, replays d14 des 30 sentinelles, garde généraliste de 64 paires et
garde de débit.

Exécution :

- début : `2026-07-20T20:22:16Z` ;
- fin : `2026-07-20T20:32:52Z` ;
- durée : 10 min 36 s ;
- exit code : 0.

| Gate | Résultat | Seuil | Verdict |
|---|---:|---:|---|
| delta macro RC4−contrôle | **+0,003038** | ≤ −0,020 | échec |
| IC95 stratifié | **[−0,043403 ; +0,049913]** | borne haute ≤ 0 | échec |
| strates non dégradées | **9 / 18** | ≥ 12 / 18 | échec |
| sentinelles ciblées corrigées | **0 / 7** | ≥ 4 / 7 | échec |
| nouvelles divergences | **0** | ≤ 2 | passe |
| débit RC4/contrôle | **0,935302** | ≥ 0,95 | échec |
| garde généraliste | **0,4140625** | ≥ 0,45 et IC non régressif | échec |

Le signe positif du delta signifie une légère dégradation. RC4 ne corrige aucune
sentinelle visée, ralentit le moteur d’environ 6,5 % et échoue la garde
généraliste. La piste est close à protocole identique.

```text
D1_RC4_NO_GO
RC4_CLOSED_DO_NOT_REPEAT_IDENTICALLY
d1b_authorized=false
training_continuation_authorized=false
promotion_authorized=false
automatic_next_job=null
```

Mémo immuable :
[`archives/l3/D1_RC4_NO_GO_20260720.md`](archives/l3/D1_RC4_NO_GO_20260720.md).

## 7. D1-X — autopsie RC4 préparée, non lancée

D1-X consomme les artefacts immuables de `0852` et `0872`. Il reconstruit
uniquement l’extracteur expérimental RC4 afin de dumper les quatre features sur
le corpus G4 et les pools C64/D64. Aucun poids n’est refitté et aucune partie
n’est jouée.

Il publie :

1. taux d’activation et distribution de chaque feature ;
2. poids MG/EG appris et dérive des poids communs contrôle→RC4 ;
3. transitions W/D/L appariées et classement des 18 strates ;
4. changements de coup/score sur les 30 sentinelles ;
5. reconstruction des 64 paires généralistes et des cas les plus défavorables ;
6. une classification causale et, au plus, un concept search-only à revoir.

Wrappers interchangeables :

```text
jobs/prepared/l3-imbalance2-d1x-20260720/ccx33-l3-imbalance2-d1x-autopsy.sh
jobs/prepared/l3-imbalance2-d1x-20260720/cpx62-l3-imbalance2-d1x-autopsy.sh
```

Contrats :

```text
training_authorized=false
search_pilot_authorized=false
promotion_authorized=false
automatic_next_job=null
```

## 8. Prochaines actions

1. relire et merger la PR D1-X après CI verte ;
2. épingler le SHA mergé et lancer un seul wrapper sur la première box libre ;
3. décider, à partir de l’autopsie, si un pilote search-only est justifié ;
4. si oui, préparer **un seul** mécanisme hors quiescence, avec nouveaux pools
   E64/F64 et gates fixe-nœuds + movetime + généraliste + débit ;
5. ne pas réutiliser RC4 et ne jamais relancer P3 à recette V2 identique.

## 9. Artefacts de référence

- P1 V2 : `r2:jass-data/runs/ccx33-0852-l3-imbalance2-role-v2-p1/20260720T073236Z-61839d1d` ;
- P2 V2 : `r2:jass-data/runs/ccx33-0859-l3-imbalance2-role-v2-p2/20260720T105918Z-a0d2f238` ;
- référence : `r2:jass-data/runs/cpx62-0862-l3-imbalance2-a64-b64-difficulty-reference/20260720T130310Z-59940065` ;
- consolidation : `r2:jass-data/runs/ccx33-0870-l3-imbalance2-p2-consolidate/20260720T175742Z-0e657bba` ;
- D0 : `r2:jass-data/runs/cpx62-0871-l3-imbalance2-d0-diagnostic/20260720T193310Z-bced44e7` ;
- D1-RC4 : `r2:jass-data/runs/cpx62-0872-l3-imbalance2-d1-rc4/20260720T202210Z-fa68634c`.

Les SHA, inventaires et checksums restent dans les manifests R2 et les statuts
GitOps. Aucun résultat volumineux n’est re-committé dans Git.
