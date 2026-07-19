# L3-PURE — état courant et registre de résultats

> **Mis à jour : 19 juillet 2026**
> **Statut scientifique : `c0_retire_frontier_v1_flat; c1_q1_no_lead; c2_x1_no_lead; gen2_p3_sibling_no_actionable_signal`**
> **Spécification normative :** [L3_PURE_PLAN.md](L3_PURE_PLAN.md)
> **Ancien état C0 :** [L3_CURRENT_C0_RUNNING_20260718.md](archives/l3/L3_CURRENT_C0_RUNNING_20260718.md)
> **Mémoire du projet :** [PROJECT_RESULTS.md](PROJECT_RESULTS.md)

## 1. État en une phrase

C0 a retiré la frontière mobile v1 et validé la viabilité de l'autojeu pur.
C1-Q1 est clos contract-grade : `0812` donne `q1_no_lead`, donc Q00 devient la
baseline et Q2 n'est pas déclenché. **C2-X1 est maintenant clos aussi** : le
verdict `0824` (`l3_x1_verdict.py`, cinq cellules, n_paired global 860) donne
`x1_no_lead` — les facteurs d'exploration (plies d'ouverture, epsilon,
décroissance) sont tous plats, IC straddle 0, aucune cellule n'atteint Δ+0,02.
Le plateau de conversion ~0,67 a désormais résisté à frontière, fork, teacher,
quiescence, head statique P3, décisions-sibling P3 **et** dose d'exploration.
Le track Gen2-MMTO « tête P3 » est lui aussi négatif : l'autopsie D0 `0822`
donne `no_actionable_sibling_signal` (recovery 37,4 % < 50 %, Δ pairé +0,035
IC [−0,022 ; +0,093]). Les leviers restants sont **la régularisation/mémoire du
fit (M/F)** et **la capacité de représentation (32cf)**.

## 2. C0 — faits d'exécution publiés

| Bras / job | Code | Début UTC | Fin UTC | État | Artefacts utiles |
|---|---|---|---|---|---|
| A — `ccx33-0790-l3-pure-c0-a-v1` | `8fc4eacb` | 10:42:49 | 11:09:08 | complet, rc=0 | G0, G1–G3, corpus+sidecars, splits, manifest |
| B — `cpx62-0791-l3-pure-c0-b-v1` | `c80c6792` | 10:41:16 | 11:02:30 | complet, rc=0 | mêmes artefacts + frontières G1/G2 |
| haut-N — `cpx62-0792-l3-pure-c0-highn-v1` | `b954ef97` | 11:39:10 | 11:44:18 | échec, rc=1 | `not enough fixed openings` (750 requis vs 305 dispo) ; aucun verdict |
| haut-N v2 — `cpx62-0795-l3-pure-c0-highn-v2` | `2e8228b7` | 14:27:57 | ~15:35 | complet, rc=0 | 3 gates + conversion P1–P4 + `c0-highn-verdict.json` |

URIs publiées :

- A : `r2:jass-data/runs/ccx33-0790-l3-pure-c0-a-v1/20260718T104245Z-8fc4eacb` ;
- B : `r2:jass-data/runs/cpx62-0791-l3-pure-c0-b-v1/20260718T104110Z-c80c6792` ;
- haut-N v2 (verdict) :
  `r2:jass-data/runs/cpx62-0795-l3-pure-c0-highn-v2/…-2e8228b7`.

Diagnostic de l'échec `0792` : le job exigeait 750 ouvertures fixes mais
`data/dilf_combinations.fen` n'en contient que 305 (bug de sizing, non
scientifique). `0795` relance à l'identique avec **NOPEN=300** et un assert de
gate **dynamique `n=2·NOPEN`** ; les entrées, gauge, gates et critères §7 sont
inchangés. Seul le gate généraliste passe à 600 parties (au lieu de 1500) ; la
conversion P1–P4 (issue du gauge, pas des ouvertures) garde sa puissance.

## 2bis. Verdict C0 pré-engagé — `retire_frontier_v1_flat`

Décision §7 exécutée : **frontière plate, bras A sain → retirer la frontière
mobile v1, poursuivre l'hypothèse de lignée pure.** Critères :
`global_delta_at_least_0_03=false`, `p3_visible_improvement=false`,
`generalist_regression_established=false`.

**Conversion (part des positions à avantage matériel converties en gain) :**

| Stratum | A-G3 | B-G3 | B−A | IC (diff. Wilson conservatrice) |
|---|---:|---:|---:|---|
| global | 0,674 | 0,651 | **−0,023** | [−0,086 ; +0,040] |
| P1 net | 0,836 | 0,833 | −0,003 | [−0,079 ; +0,074] |
| P2 moyen | 0,584 | 0,540 | −0,045 | [−0,179 ; +0,092] |
| P3 mince | 0,547 | 0,478 | **−0,070** | [−0,213 ; +0,076] |
| P4 égal | 0,513 | 0,539 | +0,026 | [−0,154 ; +0,205] |

**Force généraliste (600 parties/gate, d9) :**

| Gate | Rate | IC95 | Lecture |
|---|---:|---:|---|
| B vs A | 0,555 | [0,515 ; 0,595] | B ≥ A → **pas de régression** |
| A vs `gen2-mmto` | 0,497 | [0,457 ; 0,537] | **parité** avec le champion établi |
| B vs `gen2-mmto` | 0,470 | [0,430 ; 0,510] | légèrement sous le champion |

Holdout WDL log-loss : A-G3 **0,451**, B-G3 **0,435** (deux G3 sains).

Lecture : la conversion pure reproduit le plateau (~0,67 global) sans le casser
à 3 générations, mais le bras A atteint déjà la **parité avec `gen2-mmto`** —
la lignée pure est viable. La frontière mobile v1 est un **levier mort** (comme
fork-a/fork-c/teacher avant). C1-Q1 a ensuite clos la quiescence ; le prochain
axe est C2-X1 sur la distribution d'exploration, toujours sans frontière.

## 3. Réserve découverte pendant la revue des paramètres

Le correctif #350 a rendu les cinq paramètres de quiescence explicites pour les
futurs runs, mais la chaîne ne contenait pas les 58 autres clés reconnues par
`SearchParams`. Le manifest indiquait donc à tort
`search_params_inherited_defaults=false` pour la configuration entière.

Cela n'invalide pas `0790/0791` : ils sont appariés et épinglés sur leurs SHA.
Cela interdit en revanche d'utiliser leur fingerprint partiel comme contrat du
nouveau fork. Le runner v4 épingle les 63 clés et un test compare leur ensemble
à celui du parseur C++.

Deuxième réserve : le champ score JNNW n'entre pas dans la loss WDL, mais le
générateur lançait tout de même une recherche de label dans le même `Engine`.
La TT persiste entre les recherches ; le label pouvait donc influencer le
prochain coup joué. C1 utilise `--wdl-zero-score`, exige
`label_score_searches=0` et sépare enfin la politique de jeu d'une sortie
inutilisée.

## 4. Décision de revue

| Groupe | État |
|---|---|
| vérité terminale, EGDB naturelle, censure ply-cap, provenance, holdout par ouverture | invariant |
| recherche de score JNNW | supprimée dans C1 |
| 63 paramètres de recherche | entièrement épinglés |
| menace / sacrifices sélectifs | **clos** : C1-Q1 `q1_no_lead` |
| forcing, promotion, récursion des sacs | Q2 non déclenché |
| pruning/réductions/history et budget | profil + ablations après C2-X1 |
| ouverture aléatoire / epsilon / décroissance | **C2-X1 prochain bloc** |
| homme:dame, L2, replay | DoE graine/fit |
| 8cf | fixe pendant les écrans ; 32cf rouvert seulement au scale |
| frontière mobile | **close** : verdict C0 `0795` plat (Δglobal −0,023, P3 −0,070) → v1 retirée |

## 5. Fork C1-Q1 : calibré, lancé, complété

Les quatre cellules sont un factoriel 2×2 menace×sacrifices. Elles partent
toutes de G0, graine `271828`, deux générations de 150 k records, d8, 8cf,
aucun teacher et aucune frontière.

**Calibration (0796/0797)** : sur les deux box, `--wdl-zero-score` et
`--search-params-play` (63 clés) validés, invariant `label_score_searches=0`
prouvé par shard, fit OK. Rate cpx62 **64 k/min**, ccx33 **48 k/min** →
~17-18 min/cellule.

**Bug runner v4 (corrigé, develop `e6787b8ac`)** : le manifest final comptait
`glob("g*.pjtw.gz")` contre `ngen`, mais `g0-material.pjtw.gz` (graine de jeu)
matchait aussi → 3 ≠ 2 → les quatre cellules v1 (`0798/0799/0800/0801`) ont
aborté sur `missing generation model artifacts` **après** avoir produit des
students G1/G2 sains. Filtre corrigé en `g[1-9]*.pjtw.gz` ; re-run v2 propre.

| Cellule | Job v2 | Box | Menace | Sacs | État |
|---|---|---|---:|---:|---|
| `Q00_CAPTURE` | `ccx33-0802-c1q1-q00-v2` | ccx33 | 0 | 0 | complet, manifest ✓ |
| `Q10_THREAT` | `cpx62-0804-c1q1-q10-v2` | cpx62 | 1 | 0 | complet, manifest ✓ |
| `Q01_SACS` | `cpx62-0805-c1q1-q01-v2` | cpx62 | 0 | 1 | complet, manifest ✓ |
| `Q11_THREAT_SACS` | `ccx33-0803-c1q1-q11-v2` | ccx33 | 1 | 1 | complet, manifest ✓ |

Forcing, promotion et récursion des sacrifices sont restés à zéro/`depth0_only`
pendant Q1. Faute de lead, Q2 n'est ni préparé ni autorisé.

### 5.1 Réserve sur le verdict `0806`

Laisser `0806` terminer est utile pour le diagnostic, mais son agrégateur ne
constitue pas le verdict normatif Q1 :

- ses gates « common » passent seulement `qs_forcing_depth=6,qs_promo_depth=6`
  et héritent 61 clés, alors que Q1 exige 63 clés explicites et forcing/promo à
  zéro ;
- la vue native-search à temps égal manque ;
- les sorties de conversion ne conservent pas l'issue par position, donc les IC
  bootstrap appariés et les effets factoriels appariés sont impossibles ;
- l'écran inline ne vérifie ni P3/les autres strates, ni la branche coût −20 %.

La correction v2 réutilise strictement les G2 de `0802/0804/0805/0803`, relance
seulement les évaluations, publie les deux fingerprints par match et interdit
tout enchaînement automatique vers Q2.

## 6. Trame de résultats C1-Q1

Les nombres produits par `0806` doivent être rangés, s'ils sont publiés, sous
le label `legacy_diagnostic`. Seul le verdict schema 2 complet peut remplir les
colonnes normatives ci-dessous.

### 6.1 Santé de génération

| Cellule | G | Statut | Records | Ply-cap | Holdout N | Log-loss | Records/min | SHA modèle |
|---|---:|---|---:|---:|---:|---:|---:|---|
| Q00 | G1 | — | — | — | — | — | — | — |
| Q00 | G2 | — | — | — | — | — | — | — |
| Q10 | G1 | — | — | — | — | — | — | — |
| Q10 | G2 | — | — | — | — | — | — | — |
| Q01 | G1 | — | — | — | — | — | — | — |
| Q01 | G2 | — | — | — | — | — | — | — |
| Q11 | G1 | — | — | — | — | — | — | — |
| Q11 | G2 | — | — | — | — | — | — | — |

### 6.2 Conversion fixe — Δ appariés vs Q00 (bootstrap 10 000, IC 95 %)

Source : `cpx62-0812-c1q1-verdict-v2` (verdict schema 2, exit 143 = SIGTERM au
cleanup ~2 h ; `c1q1-verdict.json` intact, récupéré via `0814`). Défenseur gen2
fixe. `n` appariés : global 861, P1 365, P2 202, **P3 179**, P4 115.

| Δ vs Q00 | Global | P1 net | P2 moyen | **P3 mince** | P4 égal |
|---|---:|---:|---:|---:|---:|
| Q10 (menace) | −0,010 [−0,031;+0,009] | +0,005 | −0,030 | −0,039 [−0,095;+0,017] | +0,017 |
| Q01 (sacs) | −0,015 [−0,035;+0,005] | +0,000 | −0,045 | −0,006 [−0,056;+0,045] | −0,026 |
| Q11 (m+s) | −0,003 [−0,024;+0,017] | +0,003 | −0,054 | +0,034 [−0,028;+0,095] | +0,009 |

Tous les Δ ont un IC apparié recouvrant 0 ; aucune cellule n'atteint +0,02 en
global. Le seul point positif (Q11 P3 +0,034) reste non significatif.

### 6.3 Effets factoriels

| Effet (global) | Estimation | IC apparié 95 % | Lecture |
|---|---:|---:|---|
| menace | +0,0006 | [−0,015 ; +0,017] | nul |
| sacs | −0,0041 | [−0,018 ; +0,010] | nul |
| interaction menace×sacs | +0,011 | [−0,002 ; +0,024] | nul (IC franchit 0) |

### 6.4 Force

| Vue | Comparaison | N | Rate | IC95 | Elo | Lecture |
|---|---|---:|---:|---:|---:|---|
| common-search (Q00 fingerprint) | Q10 vs Q00 | 600 | 0,485 | [0,445;0,525] | −10 | ≈ |
| common-search | Q01 vs Q00 | 600 | 0,519 | [0,479;0,559] | +13 | ≈ |
| common-search | Q11 vs Q00 | 600 | 0,517 | [0,478;0,557] | +12 | ≈ |
| native movetime 0,1 s | Q10 vs Q00 | 600 | 0,500 | [0,460;0,540] | 0 | ≈ |
| native movetime 0,1 s | Q01 vs Q00 | 600 | **0,541** | [0,501;0,581] | +28 | souffle `search_gain` |
| native movetime 0,1 s | Q11 vs Q00 | 600 | 0,507 | [0,468;0,547] | +5 | ≈ |

Q01 montre un léger `search_gain` à movetime natif (0,541, IC>0,5) mais **sans
conversion** (Δ global −0,015) → ne passe pas l'écran.

## 7. Gates pré-engagés

Un lead passe en confirmation seulement si :

- tous les artefacts et les 63 paramètres sont vérifiés ;
- `label_score_searches=0` dans chaque shard ;
- pas de régression établie en common-search ;
- gain conversion ponctuel ≥ +0,02, ou coût −20 % à force/conversion tenues ;
- aucune régression établie sur P1–P4, P3 explicitement inclus, d'après l'IC
  bootstrap apparié ;
- vues common-search et native-search à temps égal toutes deux publiées.

La promotion finale exige l'IC de conversion au-dessus de zéro et la réplication
depuis G0 avec la seconde graine `161803`.

**Verdict Q1 contract-grade (`0812`) : `q1_no_lead`, `selected_lead: null`.**
Effets menace/sacs/interaction tous nuls (IC appariés franchissant 0) ; aucun Δ
conversion ≥ +0,02 ; gates common et native ≈ 0,5 ; `gain_classification` : Q01
`search_gain`, Q10/Q11 `no_established_strength_gain`. La quiescence
(menace × sacrifices sélectifs) est **confirmée levier mort**, contract-grade —
le plateau ~0,67 tient. Q2 non déclenché.

## 8. Bloc préparé : C2-X1 exploration

Le design est un demi-factoriel résolution III (`C=AB`) plus centre. Toutes
les cellules repartent de G0, utilisent Q00, deux générations de 150 k, d8,
8cf, graine `271828`, aucun teacher et aucune frontière.

| Cellule | Ouverture | Epsilon | Décroissance | Box wrapper | État |
|---|---:|---:|---:|---|---|
| `X_LLH` | 4 | 4 % | 60 | cpx62 | préparé hors queue |
| `X_HLL` | 8 | 4 % | 30 | cpx62 | préparé hors queue |
| `X_LHL` | 4 | 8 % | 30 | cpx62 | préparé hors queue |
| `X_HHH_CONTROL` | 8 | 8 % | 60 | cpx62 | contrôle courant, préparé |
| `X_CENTER` | 6 | 6 % | 45 | cpx62 | centre, préparé |

Le runner v5 publie par génération deux diagnostics supplémentaires :

- dose réalisée : coups d'ouverture, plies, événements epsilon, changements du
  meilleur coup et parties touchées ;
- profil du corpus : jeux/ouvertures/positions uniques, WDL, phases et P1–P4.

La conversion calculée dans le corpus est marquée diagnostique (records
corrélés). Le verdict utilise après génération une jauge fixe, des résultats
appariés et `X_HHH_CONTROL` comme référence.

### 8.0 Verdict C2-X1 — `x1_no_lead`

Les cinq cellules ont été générées (`cpx62-0817..0821`, tous rc=0, deux
générations chacune, G2 publiés). Le job d'évaluation `cpx62-0824`
(`l3-pure-x1-verdict-v1.sh` + `l3_x1_verdict.py`, pin `42caa2e6`) a produit le
verdict contract-complete en 47 min de science ; teardown SIGTERM 143 (comme
`0812`), verdict intact, récupéré par `cpx62-0825`.

`n` appariés : global **860**. Effets factoriels aliasés (Δconversion, bootstrap
10 000, IC 95 %) : A (ouverture) −0,0023 [−0,017 ; +0,013] ; B (epsilon) +0,0023
[−0,012 ; +0,017] ; C (décroissance) +0,0012 [−0,012 ; +0,015] ; courbure
centre-vs-coins +0,0041 [−0,012 ; +0,021]. **Tous nuls.**

Conversion globale par cellule : CONTROL 0,671 · X_LLH 0,671 · X_HLL 0,667 ·
X_LHL 0,672 · X_CENTER 0,674. Aucun coin n'atteint Δ+0,02 ; gates common/native
≈ 0,5. **`x1_no_lead`** : l'exploration (dose et calendrier) est un **levier
mort**, le plateau ~0,67 tient. Aucune confirmation lancée.

### 8.1 Trame de résultats C2-X1

| Cellule | G | Records | Epsilon réalisé | Positions uniques | P3 records | Ply-cap | Log-loss | SHA |
|---|---:|---:|---:|---:|---:|---:|---:|---|
| X_LLH | 1–2 | — | — | — | — | — | — | — |
| X_HLL | 1–2 | — | — | — | — | — | — | — |
| X_LHL | 1–2 | — | — | — | — | — | — | — |
| X_HHH_CONTROL | 1–2 | — | — | — | — | — | — | — |
| X_CENTER | 1–2 | — | — | — | — | — | — | — |

## 9. Prochaines actions

1. ✅ `0792` diagnostiqué et relancé en `0795` : verdict C0
   `retire_frontier_v1_flat` obtenu et enregistré (§2bis) ;
2. ✅ PR C1-Q1 (#351) revue et mergée ;
3. ✅ micro-calibration des deux box (0796/0797) : flags neufs validés, rate
   cpx62 64 k/min, ccx33 48 k/min ;
4. ✅ bug manifest runner v4 corrigé (`e6787b8ac`) ; les quatre cellules v2
   `completed` avec manifests ;
5. ✅ `0806` archivé `legacy_diagnostic` (non-contractuel) ;
6. ✅ verdict v2 (#352) relu et mergé (pin `88ab7eb5`) ;
7. ✅ verdict v2 `0812` exécuté sur les quatre G2 existants → **`q1_no_lead`**
   (§6.2-6.4/§7). Aucun lead, pas de confirmation, Q2 non déclenché.
8. ✅ quiescence close ; Q00 retenu, Q2 non déclenché ;
9. → faire revoir puis merger la PR C2-X1 ; aucun job n'est lancé par la merge ;
10. micro-calibrer les cinq profils sur leur box, publier débit/ETA/disque,
    épingler le SHA et demander le go explicite ;
11. lancer seulement après go, puis préparer l'évaluation sur les cinq URIs G2.
    En parallèle, le track Gen2-MMTO (tête P3) reste indépendant sur ccx33.
