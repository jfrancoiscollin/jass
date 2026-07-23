# L3 — état courant et registre de décision

> **Mis à jour : 23 juillet 2026**
> **Source de vérité active : ce document.** L’historique consolidé reste dans
> [`PROJECT_RESULTS.md`](PROJECT_RESULTS.md), les verdicts immuables sous
> [`archives/l3/`](archives/l3/), le contrat généraliste dans
> [`L3_PURE_PLAN.md`](L3_PURE_PLAN.md) et la séparation des rôles dans
> [`L3_LINEAGE_ROLES_AND_MATURITY.md`](L3_LINEAGE_ROLES_AND_MATURITY.md).
>
> **Statut scientifique :** `c0_pure_at_gen2_practical_parity;
> c0_retire_frontier_v1_flat; c1_q1_no_lead; c2_x1_no_lead;
> c3_mf_no_lead; 32cf_no_go_data_limited; pure_maturity_experiment_open;
> imbalance2_p1_v2_no_clear_lead; imbalance2_p2_no_clear_improvement_or_unstable;
> imbalance2_stop_before_p3_redesign; d0_causal_profile_ready; d1_rc4_no_go;
> d1x_rc4_autopsy_ready; top3_causal_conversion_matrix_ready`.

## 1. Architecture du programme

### 1.1 `L3-PURE` — voie généraliste

`L3-PURE` est la seule lignée destinée à produire une évaluation généraliste
entièrement autonome et, si les gates de force sont franchis, un successeur à
`gen2-mmto`.

Le bras pur C0 A-G3 a été entraîné uniquement par autojeu, pendant trois
générations de 500 000 records. Il a obtenu un score de **0,497 contre
`gen2-mmto`**, soit une parité pratique dans le protocole `0795`. C’est un
résultat majeur : il démontre qu’une lignée linéaire sans teacher peut rejoindre
le champion historique avec un volume encore faible au regard de la géométrie
8cf. Il ne prouve ni une supériorité, ni un plafond.

Une extension de maturité contrôlée est donc scientifiquement ouverte. Elle doit
séparer trois effets : générations supplémentaires, volume par fit et mémoire
explicite par replay/cumul. Répéter seulement des générations de 500 000 records
frais ne constitue pas automatiquement un entraînement cumulatif.

### 1.2 `L3-IMBALANCE2` — laboratoire spécialiste

`L3-IMBALANCE2` et `L3-IMBALANCE2-ROLE-V2` sont des expériences spécialisées sur
les positions à exactement deux hommes d’écart. Elles ne sont pas candidates au
remplacement généraliste de `L3-PURE` ou de `gen2-mmto`.

La mention « référence V2 » signifie uniquement **référence interne du track
spécialiste**. Ses pools, pondérations et gates mesurent conversion et résilience
dans ce domaine borné ; ils ne fournissent pas un Elo généraliste.

Au mieux, un spécialiste confirmé pourrait devenir plus tard un sidecar, un
expert appelé par un routeur ou une composante de méta-évaluation combinée avec
`L3-PURE`. Une telle combinaison exigerait une expérience séparée, une activation
bornée, une garde de débit et une non-régression généraliste.

## 2. Recette générale propre

La recette générale Q00 reste figée pour les comparaisons propres :

- géométrie `8cf` ;
- 63 paramètres de recherche explicitement épinglés ;
- exploration `8 / 8 % / 60` ;
- labels WDL terminaux, ply-caps exclus ;
- fit logistic, `L2=3e-5` ;
- aucun teacher, aucune frontière mobile, aucun MMTO dans le train ;
- classe d’évaluation linéaire et interprétable.

Le modèle C0 A-G3 ayant démontré la parité est un parent historique valide, mais
il appartient à l’ancien fingerprint partiellement implicite. La baseline
propre `cpx62-0842` utilise Q00 et le fingerprint complet. Avant une campagne
longue, un benchmark triangulaire doit choisir explicitement entre ces deux
parents, avec `gen2-mmto` comme thermomètre figé.

## 3. Campagnes et diagnostics publiés

| Track | Campagne | Job | Résultat durable |
|---|---|---|---|
| généraliste | C0 pur A-G3 | `ccx33-0790` + gate `0795` | **0,497 vs Gen2, parité pratique** |
| généraliste | frontière mobile C0 | `cpx62-0791` + gate `0795` | retirée, conversion −0,023 |
| généraliste propre | baseline Q00 | `cpx62-0842` | G1–G4 saine, Elo vs Gen2 non mesuré |
| spécialiste | imbalance2 V1 | `ccx33-0847` | P1 near-flat |
| spécialiste | role-aware V2 | `ccx33-0852` | crédit plus propre, pas de lead établi |
| spécialiste | comparaison V1/V2 | `0853→0857` | `V2_NO_CLEAR_LEAD_AT_P1` |
| spécialiste | role-aware V2 P2 | `ccx33-0859` | G5–G8 complets, aucune promotion |
| spécialiste | consolidation P2 | `ccx33-0870` | arrêt avant P3 |
| spécialiste | diagnostic causal | `cpx62-0871` | `D0_CAUSAL_PROFILE_READY` |
| spécialiste | représentation RC4 | `cpx62-0872` | **`D1_RC4_NO_GO`** |
| spécialiste | autopsie RC4 | `cpx62-0874` | **`D1X_RC4_AUTOPSY_READY`** |
| causal conversion | matrice TOP3 stable | `cpx62-0908` + salvage `0920` | **`SALVAGE_CAUSAL_CONVERSION_MATRIX_READY`** |

## 4. Couverture et maturité de `L3-PURE`

Les audits publiés montrent que 8cf reste sous-alimentée :

- 300 000 records : environ **5,9 %** de buckets visités ;
- 1,5 million de records agrégés dans X1 : environ **9,0 %** ;
- buckets avec au moins 100 visites : **1,0 %** ;
- Gini des visites : environ **0,85**.

Le passage de 300 k à 1,5 M a accru la couverture de manière sous-linéaire. Cela
ferme 32cf à court terme, mais ne ferme pas une expérience de maturité sur 8cf.
Il faut néanmoins distinguer volume total généré et volume réellement présent
dans un même fit.

Le plan recommandé est décrit dans
[`L3_LINEAGE_ROLES_AND_MATURITY.md`](L3_LINEAGE_ROLES_AND_MATURITY.md) :

1. M0 : comparer C0 A-G3, baseline propre `0842` G4 et `gen2-mmto` ;
2. M1 : depuis le parent retenu, comparer 500 k frais, 2 M frais et 2 M avec
   mémoire historique explicite ;
3. mesurer Elo, conversion, couverture, holdout et coût ;
4. arrêter après deux étapes sans pente de force positive.

Aucune campagne longue ou promotion n’est autorisée automatiquement.

## 5. Track spécialiste — verdicts actuels

### 5.1 P2 G4→G8

`ccx33-0870` a produit `P2_NO_CLEAR_IMPROVEMENT_OR_UNSTABLE` : delta macro
`+0,0053`, IC95 `[−0,0426 ; +0,0526]`, 9/18 strates non dégradées. P3 à recette
identique reste interdit.

### 5.2 D0 causal

`cpx62-0871` a analysé 30 sentinelles et 360 recherches :

- `REPRESENTATION_OR_OBJECTIVE_CANDIDATE` : 7/30 ;
- `SEARCH_AND_EVAL_MIXED` : 23/30 ;
- cas purement search-horizon : 0/30 ;
- cas training-credit/distribution : 0/30.

### 5.3 D1-A RC4 — verdict final `D1_RC4_NO_GO`

RC4 a ajouté quatre extras spécialisés, sans gain : delta macro `+0,003038`,
IC95 `[−0,043403 ; +0,049913]`, 9/18 strates non dégradées, 0/7 sentinelles
corrigées, débit `0,935302` et garde généraliste `0,4140625`.

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

### 5.4 D1-X — autopsie RC4 terminée

`cpx62-0874` est terminé avec exit code 0. Le verdict est
`D1X_RC4_AUTOPSY_READY` et la classification est :

```text
RC4_ACTIVE_BUT_NONCAUSAL_FOR_CONVERSION
```

Le rapport complet est publié dans R2 :

```text
r2:jass-data/runs/cpx62-0874-l3-imbalance2-d1x-autopsy/20260720T220921Z-a7301ac6
```

D1-X recommande seulement la conception humaine d’un pilote search-only séparé
`S1_ROLE_STABILITY_EXTENSION`. Il n’autorise ni implémentation automatique, ni
entraînement, ni promotion.

### 5.5 Matrice causale de conversion TOP3 stable

`cpx62-0908` a joué les 2 688 parties prévues sur les 384 mêmes positions +2
stables. Son gate technique strict a échoué sur un unique cap à 400 plies.
`cpx62-0920` n’a rejoué aucune partie : il a authentifié le tar brut, adjugé
uniquement cette partie nulle, puis calculé la matrice et 10 000 bootstraps.
Le gate zéro-cap original reste explicitement `FAILED`.

W/D/L du point de vue du camp +2 :

```text
Scan/Scan 382/0/2    Scan/G4 384/0/0    G4/Scan 7/0/377
G0/G0     342/0/42   G4/G0   210/0/174  G0/G4   356/0/28
G4/G4     270/1/113
```

Le résultat causal principal est négatif pour l’apprentissage de conversion de
G4 : effet d’attaque `G4/G0 − G0/G0 = −0,6875`, IC95
`[−0,8021 ; −0,5677]`. L’effet joint G4 est aussi négatif
(`−0,3724`, IC95 `[−0,4818 ; −0,2656]`). Scan domine G4 dans les deux rôles :
attaque `+0,5911` et défense `+1,3724`, avec IC95 entièrement positifs.

Cela ferme l’interprétation « G4 a appris une conversion seulement masquée par
le harnais ». Sur ce domaine borné, la politique issue de l’autojeu G4 a
dégradé le rôle attaquant par rapport à G0. Le fait que Scan partage une classe
d’évaluation linéaire ne suffit donc pas : sa fonction apprise et sa
co-adaptation recherche/évaluation restent causalement différentes.

## 6. Prochaines actions séparées

### Généraliste `L3-PURE`

1. préparer le benchmark M0 C0 A-G3 / `0842` G4 / `gen2-mmto` ;
2. choisir un parent généraliste immuable ;
3. préparer l’écran M1 volume/mémoire sur 8cf ;
4. ne pas passer à 32cf tant que la couverture 8cf reste insuffisante.

### Spécialiste `L3-IMBALANCE2`

1. relire le rapport D1-X ;
2. décider humainement si un unique pilote search-only mérite une PR ;
3. ne pas réutiliser RC4 ;
4. ne pas relancer P3 à recette V2 identique ;
5. ne jamais présenter un résultat spécialiste comme un remplacement généraliste.

## 7. Artefacts de référence

- C0 pur : jobs `ccx33-0790-l3-pure-c0-a-v1` et gate `0795` ;
- baseline générale propre : `cpx62-0842` ;
- P1 V2 : `r2:jass-data/runs/ccx33-0852-l3-imbalance2-role-v2-p1/20260720T073236Z-61839d1d` ;
- P2 V2 : `r2:jass-data/runs/ccx33-0859-l3-imbalance2-role-v2-p2/20260720T105918Z-a0d2f238` ;
- consolidation : `r2:jass-data/runs/ccx33-0870-l3-imbalance2-p2-consolidate/20260720T175742Z-0e657bba` ;
- D0 : `r2:jass-data/runs/cpx62-0871-l3-imbalance2-d0-diagnostic/20260720T193310Z-bced44e7` ;
- D1-RC4 : `r2:jass-data/runs/cpx62-0872-l3-imbalance2-d1-rc4/20260720T202210Z-fa68634c` ;
- D1-X : `r2:jass-data/runs/cpx62-0874-l3-imbalance2-d1x-autopsy/20260720T220921Z-a7301ac6` ;
- matrice TOP3 0908 salvagée : `r2:jass-data/runs/cpx62-0920-salvage-0908-stable-top3-matrix-v1/20260723T133448Z-2ed34499`.

Les SHA, inventaires et checksums restent dans les manifests R2 et les statuts
GitOps. Aucun résultat volumineux n’est re-committé dans Git.
