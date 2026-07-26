# L3 — état courant et registre de décision

> **Mis à jour : 24 juillet 2026**
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
> d1x_rc4_autopsy_ready; top3_causal_conversion_matrix_ready;
> l3_pure_top3_causal_conversion_ready;
> top3_specialist_recipe_failure_localized_factors_confounded;
> conversion_2x2_cap_discovery_complete_three_caps;
> conversion_2x2_finalizer_home_ready;
> pure_maturity_m0_complete_parent_c0_selected_for_m1`.

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

Le benchmark M0 HOME est terminé. Sa revue humaine retient **C0 A-G3** comme
parent immuable de M1. La génération M1 utilise néanmoins le fingerprint Q00
complet : l’ancien fingerprint C0 reste une propriété historique du parent, pas
une configuration héritée par les nouveaux bras.

## 3. Campagnes et diagnostics publiés

| Track | Campagne | Job | Résultat durable |
|---|---|---|---|
| généraliste | C0 pur A-G3 | `ccx33-0790` + gate `0795` | **0,497 vs Gen2, parité pratique** |
| généraliste | frontière mobile C0 | `cpx62-0791` + gate `0795` | retirée, conversion −0,023 |
| généraliste propre | baseline Q00 | `cpx62-0842` | G1–G4 saine, `+7 Elo` natif vs Gen2 |
| maturité M0 | triangle C0/P1/Gen2 + couverture | `home-0934` / `home-0935` | **parent C0 retenu pour M1** |
| maturité M1 | F500/F2M/R2M + confirmation | `home-0963` / `home-0964` | **F2M champion L3-PURE** |
| champion général | F2M vs Gen2, moteur réparé symétrique | `home-0965` | **F2M nouveau champion général** |
| maturité M2 | 2M frais depuis F2M | `home-0966bis` | relance après séparation des builds test/EGDB, sans promotion automatique |
| spécialiste | imbalance2 V1 | `ccx33-0847` | P1 near-flat |
| spécialiste | role-aware V2 | `ccx33-0852` | crédit plus propre, pas de lead établi |
| spécialiste | comparaison V1/V2 | `0853→0857` | `V2_NO_CLEAR_LEAD_AT_P1` |
| spécialiste | role-aware V2 P2 | `ccx33-0859` | G5–G8 complets, aucune promotion |
| spécialiste | consolidation P2 | `ccx33-0870` | arrêt avant P3 |
| spécialiste | diagnostic causal | `cpx62-0871` | `D0_CAUSAL_PROFILE_READY` |
| spécialiste | représentation RC4 | `cpx62-0872` | **`D1_RC4_NO_GO`** |
| spécialiste | autopsie RC4 | `cpx62-0874` | **`D1X_RC4_AUTOPSY_READY`** |
| causal conversion | matrice TOP3 stable | `cpx62-0908` + salvage `0920` | **`SALVAGE_CAUSAL_CONVERSION_MATRIX_READY`** |
| causal conversion | miroir L3-PURE | `cpx62-0921` | **`L3_PURE_CAUSAL_CONVERSION_MATRIX_READY`** |
| autopsie recette | 0842 vs 0890bis, matrices 0908/0921 | analyse locale reproductible | **`TOP3_SPECIALIST_RECIPE_FAILURE_LOCALIZED_FACTORS_CONFOUNDED`** |
| ablation recette | `0922bis` G1, départ standard/TOP3 × reweight off/on | 4 modèles entraînés; matrice interrompue par 1 ply-cap | **reprise eval-only `0922quater` préparée** |

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

Le plan actif est décrit dans
[`L3_LINEAGE_ROLES_AND_MATURITY.md`](L3_LINEAGE_ROLES_AND_MATURITY.md) :

1. M0 : terminé ; C0 A-G3 est le parent immuable retenu ;
2. M1 : comparer 500 k frais, 2 M frais et 2 M avec
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

Le miroir `cpx62-0921` remplace uniquement le G4 spécialiste 0890bis par le G4
généraliste pur de `0842`. Il a terminé strictement les 2 688 parties, sans
erreur ni cap :

```text
Scan/Scan 382/0/2    Scan/G4 384/0/0    G4/Scan 78/0/306
G0/G0     342/0/42   G4/G0   374/0/10   G0/G4   202/0/182
G4/G4     345/0/39
```

Contrairement au spécialiste, G4 pur améliore causalement les deux rôles :
attaque `+0,1667`, IC95 `[+0,0990 ; +0,2344]`, et défense `+0,7292`, IC95
`[+0,6146 ; +0,8438]`. Leur combinaison G4/G4 est proche de G0/G0
(`+0,0156`, IC95 `[−0,0625 ; +0,0990]`) parce que l’attaquant et le défenseur
sont renforcés simultanément. Scan reste supérieur, surtout en défense.

La conclusion est donc localisée : l’architecture linéaire et le self-play WDL
sans oracle peuvent apprendre la conversion. C’est la recette spécialiste
0890bis qui a détruit le rôle attaquant ; elle ne doit pas être prolongée ni
servir de preuve d’un échec général de L3-PURE.

### 5.6 Autopsie de la recette 0890bis

L’autopsie des manifests, profils, poids G4 et résultats bruts appariés localise
le problème dans le bundle de recette 0890bis, sans pouvoir encore séparer ses
trois facteurs : départ exclusivement TOP3, volume `2 M/gen` et pondération
role-aware `1/2/4`.

Le corpus réel n’est pas majoritairement TOP3 : en G4, **72,59 %** des records
ont au plus 14 pièces et seulement **0,081 %** en ont au moins 30. Avant
resampling, seulement **5,765 %** du fit reste dans le domaine exact
`±2 hommes, dames égales` ; après resampling, cette part atteint **8,038 %**.
Les 94,235 % hors domaine sont conservés comme anchors.

Les matrices 0908/0921 sont exactement appariées sur les 2 688 lignes et les
contrôles G0/G0 et Scan/Scan sont identiques à 384/384. Remplacer seulement le
G4 spécialiste par le G4 pur améliore 171 positions et en dégrade 7 en attaque
contre G0 ; en défense contre G0, 171 s’améliorent et 17 se dégradent.

Verdict :

```text
TOP3_SPECIALIST_RECIPE_FAILURE_LOCALIZED_FACTORS_CONFOUNDED
0890bis_continuation_authorized=false
automatic_next_job=null
```

La seule ablation propre restante est un `2 × 2` départ standard/TOP3 ×
reweighting off/on, à volume identique. Ses quatre modèles G1 sont acquis ;
le verdict causal complet reste ouvert. Mémo immuable :
[`archives/l3/TOP3_SPECIALIST_RECIPE_AUTOPSY_20260723.md`](archives/l3/TOP3_SPECIALIST_RECIPE_AUTOPSY_20260723.md).

### 5.7 Écran G1 `2 × 2` — modèles acquis, reprise d’évaluation

`cpx62-0922bis-l3-conversion-2x2-g1-screen-v1` a entraîné les quatre modèles. Les
cellules off/on partagent exactement le même self-play et le même split :
500 000 records standard alimentent `standard_off/standard_on`, et 500 000
records TOP3 alimentent `top3_off/top3_on`.

Le gate devait jouer un contrôle G0/G0 commun et trois bras par candidat sur les 384
positions stables de 0921, soit 4 992 parties, puis 128 parties équilibrées par
candidat. `0922bis` s’est arrêté après un unique cap déterministe à 400 plis
dans `standard_off/g0_g4` ; ce résultat technique ne constitue pas un verdict
sur les modèles.

La première reprise `0922ter` a vérifié les modèles mais a échoué avant toute
partie : le build d’évaluation n’avait pas réémis la géométrie `8cf`.
`0922quater` a rétabli cette étape, puis a authentifié un second cap
déterministe à 400 plis dans `top3_off/g4_g0`, shard 12, position `62faf1...`.
Le premier reste `standard_off/g0_g4`, shard 10, position `9bc75f...`.

`home-0928` a réutilisé les quatre modèles vérifiés de `0922bis`, sans
réentraînement. Il a validé les deux caps connus puis a échoué fermé sur un
troisième shard technique dans `top3_off/g4_g4`, après 3 733/4 992 lignes.

`home-0928quater` a importé le tar brut vérifié de `home-0928`, réutilisé chaque
bras complet et joué uniquement les bras manquants. La matrice est complète :
4 992 lignes et exactement trois ply-caps propres à 400 plis, dans
`standard_off/g0_g4`, `top3_off/g4_g0` et `top3_off/g4_g4`. Aucun bras
`top3_on` ne contient d’anomalie et aucune erreur moteur n’a été observée.

`home-0928quinquies` a réutilisé cette matrice sans rejouer une ligne, exigé
les trois identités authentifiées, puis joué la garde équilibrée de 512
parties. Les quatre gardes passent. Le résultat final est :

```text
CONVERSION_2X2_G1_SCREEN_READY
technical_status=derived_complete_3_ply_caps
promotion_authorized=false
continuation_authorized=false
automatic_next_job=null
```

Les effets causaux sont nets. Par rapport au départ standard, le départ TOP3
exclusif dégrade l’attaque de `−0,5352` (IC95
`[−0,6055 ; −0,4674]`), la défense de `−0,6367`
(`[−0,7201 ; −0,5534]`) et l’effet joint de `−0,2383`
(`[−0,3125 ; −0,1654]`). Le reweight role-aware V2 dégrade aussi l’attaque
de `−0,2513`, la défense de `−0,1003` et l’effet joint de `−0,1315`,
avec des IC95 entièrement négatifs. Son interaction avec TOP3 est elle-même
négative.

La cellule propre `standard_off` conserve les gains causaux de L3-PURE :
attaque `+0,1719`, défense `+0,6536`, effet joint `+0,0104`. La recette à
retenir pour la maturité généraliste est donc **départ standard, sans reweight
V2**. TOP3 exclusif et le reweight V2 sont fermés pour cette continuation.
Cela attribue causalement l’échec 0890bis à la recette spécialiste et non à
l’architecture linéaire ni au principe d’autojeu WDL.

## 6. Prochaines actions séparées

### Généraliste `L3-PURE`

1. parent M1 : C0 A-G3, immuable ;
2. exécuter l’écran M1 `F500/F2M/R2M` sur 8cf et Q00 ;
3. mesurer séparément force, conversion, couverture et convergence ;
4. ne pas passer à 32cf tant que la couverture 8cf reste insuffisante.

### Spécialiste `L3-IMBALANCE2`

1. ne pas prolonger 0890bis ;
2. considérer le DOE `2 × 2` comme terminé : TOP3 exclusif et reweight V2
   sont causalement défavorables ;
3. ne pas réutiliser RC4 ;
4. ne pas relancer P3 à recette V2 identique ;
5. ne jamais présenter un résultat spécialiste comme un remplacement généraliste.

## 7. Artefacts de référence

- C0 pur : jobs `ccx33-0790-l3-pure-c0-a-v1` et gate `0795` ;
- baseline générale propre : `cpx62-0842` ;
- triangle M0 certifié :
  `r2:jass-data/runs/home-0934-finalize-m0-triangle-v2/20260724T020401Z-922930bc` ;
- couverture M0 :
  `r2:jass-data/runs/home-0935-l3-pure-m0-coverage-v3/20260724T020913Z-952f46d0` ;
- P1 V2 : `r2:jass-data/runs/ccx33-0852-l3-imbalance2-role-v2-p1/20260720T073236Z-61839d1d` ;
- P2 V2 : `r2:jass-data/runs/ccx33-0859-l3-imbalance2-role-v2-p2/20260720T105918Z-a0d2f238` ;
- consolidation : `r2:jass-data/runs/ccx33-0870-l3-imbalance2-p2-consolidate/20260720T175742Z-0e657bba` ;
- D0 : `r2:jass-data/runs/cpx62-0871-l3-imbalance2-d0-diagnostic/20260720T193310Z-bced44e7` ;
- D1-RC4 : `r2:jass-data/runs/cpx62-0872-l3-imbalance2-d1-rc4/20260720T202210Z-fa68634c` ;
- D1-X : `r2:jass-data/runs/cpx62-0874-l3-imbalance2-d1x-autopsy/20260720T220921Z-a7301ac6` ;
- matrice TOP3 0908 salvagée : `r2:jass-data/runs/cpx62-0920-salvage-0908-stable-top3-matrix-v1/20260723T133448Z-2ed34499`.
- miroir causal L3-PURE : `r2:jass-data/runs/cpx62-0921-l3-pure-top3-stable-conversion-matrix-v1/20260723T134611Z-fbf0c93e`.
- autopsie 0842/0890bis :
  [`archives/l3/TOP3_SPECIALIST_RECIPE_AUTOPSY_20260723.md`](archives/l3/TOP3_SPECIALIST_RECIPE_AUTOPSY_20260723.md).

Le préflight HOME M1 `home-0936-l3-pure-m1-preflight-v1` est vert
(`M1_PREFLIGHT_READY`). L’entraînement préenregistré suivant est
`home-0937-l3-pure-m1-train-v1`; il conserve une tranche fraîche commune
byte-identique entre F500/F2M/R2M et refuse toute convergence au plafond.
L’évaluation à défenseur fixe et de force générale reste un job séparé, lancé
seulement après publication vérifiée des trois modèles.

`home-0937` a produit et publié les sources fraîches ainsi que les trois
assemblages, puis s’est arrêté proprement parce que F500 atteignait le plafond
L-BFGS de 60 itérations. Le diagnostic `home-0938` classe explicitement la
cause `MAXITER` (ni OOM, ni timeout). La reprise `home-0939` réutilise les
sources 0937 vérifiées par inventaire/checksum, porte le budget à 200 et exige
désormais le statut `success` réel de SciPy avec rapport d’optimiseur ; elle ne
régénère donc aucune position et ne relâche pas le critère de convergence.
`home-0940/0941` montre que 0939 atteint 200 itérations avec un gradient infini
encore élevé (`2.170022328647e-02`). La reprise V2 `home-0942` conserve donc
les tolérances SciPy, augmente l’historique de courbure L-BFGS de 5 à 20
(dimension 8cf prunée compatible HOME) et autorise jusqu’à 1000 itérations,
toujours avec `success=true` obligatoire.
Le résultat 0943 est finalement `5.008773068760e-04` à 1000 itérations :
la courbure renforcée réduit le gradient d’un facteur 43. Comme les poids PJTW
sont quantifiés au millième, `home-0944` préenregistre `gtol=1e-3`, conserve
`maxcor=20/maxiter=1000` et exige toujours une terminaison SciPy réussie. Les
checkpoints sont désormais publiés même si un bras ultérieur échoue.
`home-0944` est terminé avec succès : F500, F2M et R2M ont tous convergé et
sont publiés. `home-0945` est l’évaluation non promotable préenregistrée :
force Q00 et native contre C0, ancrage Q00 contre Gen2, puis conversion P1–P4
contre le même défenseur Gen2 fixe.

Correctif du 25 juillet 2026 : les volets conversion de `home-0945` et
`home-0949` sont supersédés. Le gauge FEN historique a été produit avec les
pions et dames noirs intervertis lors de l’export JNNW → FEN. Les poids
entraînés, les ablations et le triangle de force M0 ne sont pas invalidés.
`home-0954` fournit le gauge JNNW stable corrigé ; `home-0955` rejoue C0, P1,
F500, F2M, R2M, AB_MAT, AB_KING et AB_EXTRAS sur exactement ces mêmes
positions et le même défenseur Gen2.

Les SHA, inventaires et checksums restent dans les manifests R2 et les statuts
GitOps. Aucun résultat volumineux n’est re-committé dans Git.

Le diagnostic causal `home-0961ter` clôt ensuite le faux plafond de
conversion : avec les poids Scan exacts et le défenseur Gen2 historique
inchangé, la réparation de légalité/terminaison fait passer `p3_mince` de
38,00 % à 99,00 % et `p4_egal` de 35,33 % à 98,00 %. L’ordre racine Scan
n’ajoute plus que +1,00 et +2,01 points. Le moteur, et non l’architecture
linéaire, était la cause dominante du déficit mesuré.

La reprise M1 doit donc d’abord rejouer sur le moteur réparé les poids déjà
produits C0/P1/F500/F2M/R2M et les ablations, appariés à la matrice 0955 et
avec un défenseur historique figé. Une nouvelle génération de données n’est
autorisée qu’après ce readout : si les poids existants restent sous le
plancher de conversion, la branche suivante sera une réplication
Scan-faithful propre ; sinon la revue portera sur le candidat M1 et sa force
générale. Aucune promotion ni continuation n’est automatique.

`home-0962` confirme que le moteur réparé convertit avec tous les poids M1 :
F500 atteint 98,00/99,33 %, F2M 97,33/98,33 % et R2M 99,67/97,33 % sur
`p3_mince/p4_egal`, sans erreur. `home-0963` rejoue ensuite la force sur 400
parties par vue et mesure les corpus exacts. F2M obtient 60,00 % Q00 et
60,25 % native contre C0, puis 91,00 % Q00 contre Gen2. Sa couverture 8cf
dépasse aussi C0 de 3 043 buckets visités et de 3 834 buckets vus au moins
100 fois. R2M est positif mais moins fort ; F500 reste sous la couverture du
parent. La règle préenregistrée sélectionne donc F2M pour une confirmation
indépendante, sans le promouvoir.

La confirmation suivante emploie 500 nouvelles ouvertures synthétiques
appariées, sans recouvrement avec DILF ni les pools synthétiques antérieurs,
soit 1 000 parties dans chaque vue. F2M doit avoir la borne basse à 95 % au
dessus de 50 % contre C0 en Q00 et native, et ne pas présenter de régression
établie contre R2M. Un succès ouvre seulement une revue humaine de promotion.

`home-0964` confirme F2M sur 1 000 parties indépendantes par vue : `60,35 %`
Q00 et `59,95 %` native contre C0, avec les deux bornes basses à 95 % au-dessus
de `57 %`. F2M et R2M restent statistiquement équivalents en confrontation
directe. Après autorisation humaine explicite, **F2M devient le champion de la
lignée L3-PURE et le parent prévu de M2**. Gen2-mmto reste provisoirement le
champion général historique.

Le protocole suivant rejoue F2M 8cf contre Gen2-mmto 32cf en construisant les
deux moteurs depuis le même SHA réparé. Il emploie un nouveau pool indépendant
et exige une borne basse à 95 % au-dessus de 50 % en Q00 et native pour
recommander F2M comme champion général. Détails :
[`experiments/L3_F2M_PROMOTION_AND_GEN2_REPAIRED_BENCH_20260725.md`](experiments/L3_F2M_PROMOTION_AND_GEN2_REPAIRED_BENCH_20260725.md).

`home-0965` passe ce gate : F2M marque `57,25 %` en Q00
(`562-21-417`, IC95 `[54,22 ; 60,28]`) et `58,60 %` en cadence native
(`580-12-408`, IC95 `[55,57 ; 61,63]`). Après revue humaine explicite,
**F2M remplace Gen2-mmto comme champion général courant**. Gen2 reste la
référence historique figée.

M2 repart de F2M avec 2 millions de positions entièrement fraîches, toujours
en 8cf/Q00 et WDL pur, sans replay, oracle, TOP3 ni reweight. L'entraînement
n'autorise qu'une évaluation séparée ; aucune promotion ou continuation M3
n'est automatique. Protocole :
[`experiments/L3_PURE_M2_PROTOCOL_20260725.md`](experiments/L3_PURE_M2_PROTOCOL_20260725.md).

`home-0966bis` termine l'entraînement M2 : 2 000 000 de positions fraîches,
convergence en 236 itérations, log-loss holdout `0,444311`, modèle SHA-256
`75ace3c0…`. L'écran indépendant `home-0967` est préenregistré avant les
matchs : force M2/F2M, garde-fou Gen2, conversion P3/P4 et couverture exacte.

`home-0967` s'est arrete avant tout match au controle du pool d'ouvertures.
La relance `home-0970` garde exactement les bras, budgets et seed
preenregistres, mais selectionne deterministiquement 500 ouvertures uniques
et disjointes depuis 2 000 candidates. Les builds de 0967 avaient passe ;
aucun verdict scientifique partiel n'est reutilise.

Le claim `home-0970` sur snapshot de controle stale a ete rejete par le
garde-fou SHA avant tout match. `home-0970bis` est le run autoritatif.

`home-0970bis` termine avec le verdict
`M2_PLATEAU_OR_REGRESSION_REVIEW`. M2 marque 50,60 % Q00 et 49,05 % native
contre F2M : aucune pente de force n'est établie. Les garde-fous passent :
56,30/58,80 % contre Gen2, conversion P3/P4 à 99,00/98,67 %, et couverture
utile en hausse de 2 075 buckets visités et 352 buckets vus au moins 100
fois. La recette d8/2M n'est donc pas poursuivie à l'identique. Le prochain
bras causal conserve F2M, 8cf, WDL pur, 2M, seeds, exploration, split et fit,
et change seulement la profondeur de jeu de d8 à d10. Protocole :
[`experiments/L3_PURE_D10_CAUSAL_PROTOCOL_20260726.md`](experiments/L3_PURE_D10_CAUSAL_PROTOCOL_20260726.md).

`home-0971` termine le bras d10 : exactement 2 000 000 positions fraîches,
split par ouverture 1 802 842/197 158, convergence en 16 itérations,
log-loss holdout `0,443257`, modèle SHA-256 `18930613…`. L'entraînement
n'autorise qu'une évaluation. Le readout indépendant `home-0972` compare D10
à M2 d8, F2M et Gen2 dans les deux vues, puis vérifie conversion et couverture
sur un pool seed 314159 préflighté, unique et disjoint (SHA-256 `e41ae387…`).

`home-0972` conclut `D10_PLATEAU_OR_REGRESSION_REVIEW`, avec tous les
garde-fous valides. D10 fait 47,50/50,70 % contre M2 d8 et 48,80/51,00 %
contre F2M en Q00/native. La conversion reste à 99,33/98,67 %, mais la
couverture recule de 4 864 buckets visités face à M2. Le prochain bras causal
est donc d12 pur à 2M, toujours depuis F2M avec les mêmes seeds ; seul le
facteur profondeur change. Protocole :
[`experiments/L3_PURE_D12_CAUSAL_PROTOCOL_20260726.md`](experiments/L3_PURE_D12_CAUSAL_PROTOCOL_20260726.md).
