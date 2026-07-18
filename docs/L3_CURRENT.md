# L3-PURE — état courant et registre de résultats

> **Mis à jour : 18 juillet 2026**
> **Statut scientifique : `c0_retire_frontier_v1_flat; c1_q1_no_lead (verdict v2 contract-grade, 0812)`**
> **Spécification normative :** [L3_PURE_PLAN.md](L3_PURE_PLAN.md)
> **Ancien état C0 :** [L3_CURRENT_C0_RUNNING_20260718.md](archives/l3/L3_CURRENT_C0_RUNNING_20260718.md)
> **Mémoire du projet :** [PROJECT_RESULTS.md](PROJECT_RESULTS.md)

## 1. État en une phrase

Le job haut-N `0792` (échec technique `not enough fixed openings`, 750 requis
vs 305 disponibles) a été relancé corrigé en `0795` (NOPEN=300, assert de gate
`n=2·NOPEN`) : le verdict C0 pré-engagé est **`retire_frontier_v1_flat`** — la
frontière mobile v1 n'améliore pas la conversion (Δglobal −0,023, P3 mince
−0,070, toutes IC recouvrant 0) et le bras A pur est à parité avec `gen2-mmto`.
La revue des paramètres L3 (#351) est mergée. Le fork **C1-Q1 a été calibré,
lancé et complété** : après un bug de manifest du runner v4 (corrigé, cf §5),
les quatre cellules v2 sont `completed` avec leurs students G1/G2 manifestés.
L'audit du job de verdict `cpx62-0806-c1q1-verdict` a toutefois trouvé un écart
entre son script et le contrat §7 : son résultat éventuel reste **diagnostique**
et ne peut ni sélectionner un lead, ni autoriser Q2. Un verdict v2, sans nouvel
entraînement, est préparé pour réévaluer les quatre G2 immuables.

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
fork-a/fork-c/teacher avant). Prochain axe = C1-Q1 (quiescence), sans frontière.

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
| menace / sacrifices sélectifs | DoE C1-Q1 immédiat |
| forcing, promotion, récursion des sacs | C1-Q2 conditionnel |
| pruning/réductions/history et budget | profil + ablations après Q |
| ouverture aléatoire / epsilon / décroissance | DoE exploration |
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

Forcing, promotion et récursion des sacrifices restent à zéro/`depth0_only`
pendant Q1, réservés au bloc Q2 (ne pas confondre cinq facteurs au premier
écran).

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

## 8. Prochaines actions

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
8. → quiescence close ; prochain levier L3 hors quiescence (DoE exploration /
   graine-fit) à décider. En parallèle, track gen2-mmto (tête P3) sur ccx33.
