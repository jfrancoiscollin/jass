# Rapport de clôture et de traçabilité — Revue Codex v3.2

> **Date du rapport : 18 juillet 2026**  
> **État observé : 18 juillet 2026, 07:05 UTC / 09:05 CEST**  
> **Spécification de référence :** [`docs/codex_review_v3_2.md`](https://github.com/jfrancoiscollin/jass/blob/develop/docs/codex_review_v3_2.md), datée du 15 juillet 2026  
> **Périmètre :** sonde `ADJ + G1` T1-bis → T2 → T3, mining passif, teacher causal A/B1/B2/B3, audits et expériences postérieures nécessaires pour établir la situation actuelle.  
> **Règle de lecture :** ce rapport distingue ce qui a été **implémenté et testé**, ce qui a été **réellement exécuté**, ce qui a seulement été **observé après coup**, et ce qui n’a volontairement **pas été lancé en raison d’un gate négatif**.

## 1. Conclusion exécutive

La séquence scientifique centrale prévue par la v3.2 a été menée jusqu’à son terme :

```text
T1-bis ADJ+G1
→ T2
→ T3
→ verdict de sonde
→ mining/certification des erreurs de conversion
→ smoke teacher A/B1/B2/B3
```

Elle se termine **sans signal positif de conversion** :

1. **La sonde multi-tours ne compose pas.** T1-bis, T2 et T3 sont tous non régressifs selon le régime `young`, mais la force contre la référence fixe reste compatible avec le neutre et la conversion globale reste autour de 66–67 %.
2. **Le principal défaut localisé reste P3 mince.** Sa conversion baisse de 51,67 % à 49,44 %, puis 48,89 %.
3. **Le teacher causal ne débloque pas le plafond.** B1 préserve la force mais baisse la conversion ; B2 apporte seulement +0,71 point de conversion dure avec une régression généraliste ; B3, la variante MMTO through-search, régresse sur les deux axes.
4. **La confirmation du teacher n’a pas été lancée, conformément au plan.** Aucun bras n’étant éligible, les jobs 0781/0782 doivent rester non soumis.
5. **Le fork (c) à départ affaibli est lui aussi rejeté.** Le refit faible perd −32,5 Elo contre le fort et baisse la conversion dure de 1,11 point.
6. **Les audits MTC sont maintenant verts sur les deux boxes**, mais ils ont été exécutés après la sonde. Ils valident l’environnement pour la suite sans requalifier rétroactivement T1–T3.
7. **Le seul mécanisme majeur non encore jugé scientifiquement est le sparring réel contre Scan.** La Phase 0 `0784`, destinée à valider la tuyauterie, vient d’être réclamée ; elle n’a pas encore rendu de résultat dans `jass-control` à l’heure de coupure du rapport.

Le verdict global à date est donc :

```text
programme expérimental v3.2 exécuté jusqu'au teacher
→ sonde = complete_probe mais plate
→ teacher = complete_no_signal
→ aucune campagne longue ADJ+G1 ou teacher autorisée
→ pivot actif = résultats réels de parties contre Scan
```

Cela ne prouve pas que toute la classe linéaire-patterns est mathématiquement épuisée. En revanche, les résultats ferment désormais de façon assez solide la famille suivante :

```text
re-fit linéaire ancré
+ données auto-générées par Jass
+ labels WDL adjudicated / oracle d14+EGDB
+ gymnase léger ou préférences causales internes
```

## 2. Légende des statuts

| Statut | Sens dans ce rapport |
|---|---|
| ✅ Conforme/exécuté | Exigence implémentée et résultat live disponible. |
| 🧪 Testé seulement | Couverture unitaire ou d’intégration disponible, mais pas de démonstration live substantielle. |
| ⚠️ Partiel | Exécuté avec une réserve, après coup, ou avec une publication incomplète. |
| ❌ Négatif/manquant | Hypothèse falsifiée, exigence non exécutée ou preuve attendue absente. |
| ⏭️ Non lancé à raison | Étape conditionnelle correctement bloquée par un gate négatif. |
| 🔄 En cours | Job réclamé ou lancé, verdict non disponible à l’heure de coupure. |

## 3. Sources de vérité utilisées

### 3.1 Spécification et documentation

- [`codex_review_v3_2.md`](https://github.com/jfrancoiscollin/jass/blob/develop/docs/codex_review_v3_2.md) : contrat scientifique et opérationnel initial.
- [`probe_multi_turn_runner_v3.md`](https://github.com/jfrancoiscollin/jass/blob/develop/docs/probe_multi_turn_runner_v3.md) : filiation et invariants T1-bis → T2 → T3.
- [`CURRENT.md`](https://github.com/jfrancoiscollin/jass/blob/develop/docs/CURRENT.md) : verdicts scientifiques consolidés.
- [`forkc_teacher_execution_20260717.md`](https://github.com/jfrancoiscollin/jass/blob/develop/docs/forkc_teacher_execution_20260717.md) : plan post-T3 et contrats du fork (c) et du teacher.
- [`forkc_c0_verdict_20260717.md`](https://github.com/jfrancoiscollin/jass/blob/develop/docs/forkc_c0_verdict_20260717.md) : verdict détaillé du fork (c).

### 3.2 Résultats runner-v3 et R2

| Étape | Job / résultat |
|---|---|
| T1-bis | [`ccx33-0756-t1bis-adj-g1-native-full-v2`](https://github.com/jfrancoiscollin/jass-control/blob/main/status/ccx33-0756-t1bis-adj-g1-native-full-v2.json) — `r2:jass-data/runs/ccx33-0756-t1bis-adj-g1-native-full-v2/20260717T074749Z-6d90e72d` |
| T2 | [`ccx33-0762-probe-t2-adj-g1-v2`](https://github.com/jfrancoiscollin/jass-control/blob/main/status/ccx33-0762-probe-t2-adj-g1-v2.json) — `r2:jass-data/runs/ccx33-0762-probe-t2-adj-g1-v2/20260717T115602Z-f5410cbf` |
| T3 | `r2:jass-data/runs/ccx33-0769-probe-t3-adj-g1-v1/20260717T145848Z-1b907771` — tentative scientifique réussie ; le fichier de statut courant pointe ensuite sur le doublon échoué |
| Mining teacher | [`ccx33-0776-teacher-mine-t3-v1`](https://github.com/jfrancoiscollin/jass-control/blob/main/status/ccx33-0776-teacher-mine-t3-v1.json) |
| Teacher smoke | [`ccx33-0777-teacher-smoke-v1`](https://github.com/jfrancoiscollin/jass-control/blob/main/status/ccx33-0777-teacher-smoke-v1.json) |
| Audit MTC ccx33 | [`ccx33-0778-mtc-audit-v1`](https://github.com/jfrancoiscollin/jass-control/blob/main/status/ccx33-0778-mtc-audit-v1.json) |
| Audit MTC cpx62 | [`cpx62-0779-mtc-audit-v1`](https://github.com/jfrancoiscollin/jass-control/blob/main/status/cpx62-0779-mtc-audit-v1.json) |
| Diagnostic T3 | [`cpx62-0780b-t3-attempt-diagnostic-v1`](https://github.com/jfrancoiscollin/jass-control/blob/main/status/cpx62-0780b-t3-attempt-diagnostic-v1.json) |
| Sparring Phase 0 | [`cpx62-0784-sparring-scan-smoke-v1`](https://github.com/jfrancoiscollin/jass-control/commit/fe4385b93527460dbc13d3b09fa503aa936919eb), réclamé mais résultat non encore publié à l’heure de coupure |

## 4. Séquence prévue contre séquence réellement exécutée

| Séquence v3.2 | Réalisation | Statut | Conclusion |
|---|---|---|---|
| Implémenter labels, promotion, manifests, cache, mining et runner | PRs de migration/runner puis chaîne multi-tours ; tests exécutés au préflight de chaque tour | ✅/⚠️ | Socle fonctionnel. Le mining était testé mais pas encore appelé par les runs historiques. |
| T1-bis ADJ+G1 | `0756`, rc=0 | ✅ | Promu, petit point positif généraliste mais non significatif ; conversion au plafond. |
| T2 si T1-bis passe | `0762`, rc=0 | ✅ | Promu ; aucun début de composition. |
| T3 si T2 passe | tentative `145848Z-1b907771`, rc=0 | ✅ | Promu, `complete_probe` ; chaîne plate. |
| Verdict de sonde | Cas D de la section 8 | ✅ | Généraliste neutre/incertain et conversion plate. |
| Mining passif par tour | Pas invoqué dans les SHAs historiques ; mining T3 post-hoc `0776` | ⚠️ | Corpus teacher obtenu, mais pas d’inventaire contemporain séparé T1-bis/T2/T3. |
| Smoke teacher A/B1/B2/B3 | `0777`, rc=0 | ✅ | `complete_no_signal`, aucun gagnant. |
| Confirmation du bras gagnant | 0781/0782 préparés mais conditionnés à un gagnant | ⏭️ | Non-lancement correct ; aucun bras n’était éligible. |
| Campagne longue | Conditionnée à un signal confirmé | ⏭️ | Non autorisée par les résultats. |

## 5. Résultats de la sonde T1-bis → T2 → T3

Chaque comparaison généraliste porte sur 600 parties. Tous les intervalles de confiance recouvrent 50 %.

| Tour | Vs parent | Vs référence fixe T0 | Conversion globale | Décision opérationnelle | Statut scientifique |
|---|---:|---:|---:|---|---|
| T1-bis | 51,25 % ; IC [47,3 ; 55,2] | 51,25 % ; même parent/référence | 66,71 % | `promote` | `continue_probe` |
| T2 | 47,25 % ; IC [43,3 ; 51,2] | 49,00 % ; IC [45,0 ; 53,0] | 65,74 % | `promote` | `continue_probe` |
| T3 | 49,67 % ; IC [45,7 ; 53,7] | 50,33 % ; IC [46,3 ; 54,3] | 66,94 % | `promote` | `complete_probe` |

Lecture : les règles de promotion `young` ont fonctionné comme prévu. Elles autorisaient un résultat neutre ou incertain et ne rejetaient que si `ci_high < 0,5`. Aucun tour n’a démontré une régression statistiquement établie. En revanche, aucun tour ne démontre non plus un gain Elo certain.

### 5.1 Conversion par strate

| Strate | T1-bis | T2 | T3 | Évolution T1→T3 | Lecture |
|---|---:|---:|---:|---:|---|
| P1 net | 83,56 % | 82,42 % | 84,11 % | +0,55 pt | Stable, niveau élevé. |
| P2 moyen | 57,43 % | 55,45 % | 60,89 % | +3,46 pts | Amélioration ponctuelle à T3, non suffisante pour déplacer le global. |
| P3 mince | 51,67 % | 49,44 % | 48,89 % | **−2,78 pts** | Principal signal défavorable ; conversion fine non apprise. |
| P4 égal | 53,04 % | 56,52 % | 51,30 % | −1,74 pt | Bruité/non monotone. |

Le global plat masque donc un échange entre strates plutôt qu’une progression homogène. P3 est la réserve scientifique la plus nette.

### 5.2 Verdict prévu par la section 8

La v3.2 définissait cinq cas. Le résultat correspond au **cas D** :

```text
généraliste neutre
+ conversion plate
→ sonde rapide close sans signal
→ smoke teacher comme expérience causale suivante
```

Le routage prévu a donc été respecté.

## 6. Matrice exhaustive de conformité à la v3.2

### 6.1 Sections 1–3 — faits de référence, labels et draw-band

| Exigence v3.2 | Preuve/résultat | Statut | Commentaire |
|---|---|---|---|
| Utiliser `ADJ + G1`, issu du DOE 0726 | Recette identique dans les trois tours | ✅ | Aucun retour à G4. |
| Hiérarchie `TB_EXACT > CERT_PROOF > SEARCH_STABLE > ON_POLICY` | `oracle_cert.py`, `apply_label_policy.py` et tests associés | 🧪 | Implémentation et invariants unitaires présents. |
| TB_EXACT et CERT_PROOF vérifiés survivent au draw-band | Tests `test_tb_exact_blocks_and_survives`, `test_cert_proof_verified_blocks` | 🧪 | Le comportement est testé. |
| CERT_PROOF non vérifié rejeté/déclassé | Test dédié vert | 🧪 | Conforme au contrat. |
| SEARCH_STABLE ne peut pas bloquer le draw-band | Test dédié vert et rejet d’un claim incohérent | 🧪 | Conforme au contrat. |
| Résolution identique parent/enfant/sibling | Test dédié vert | 🧪 | Conforme en code. |
| Compteurs de survie par tier/strate/provenance/tour | Structure et tests présents | ⚠️ | Les résumés live T1–T3 ne publient pas cette ventilation. |
| 100 % des certificats valides protégés pendant la sonde | Aucun sidecar de certificats non vide n’est démontré dans les résultats publiés ; seuil runtime historique par défaut `MIN_PROTECTED_TIP_RATE=0.0` | ⚠️ | Invariant testé en code, mais pas démontré sur un flux live non vide. Le d14+EGDB strict a bien tourné, ce qui ne constitue pas à lui seul un `CERT_PROOF`. |

**Conclusion sur les labels :** la politique est correctement implémentée et testée, mais la campagne n’apporte pas une démonstration empirique complète du canal certificat/tip. Cela limite la preuve de conformité, pas le constat de plateau de la recette effectivement exécutée.

### 6.2 Section 4 — promotion inter-tours

| Exigence v3.2 | Preuve/résultat | Statut | Commentaire |
|---|---|---|---|
| Régimes `young` et `established` séparés | `promotion_gate.py` et tests | ✅/🧪 | `young` exécuté live ; `established` seulement testé. |
| Comparer candidat au parent et à T0 fixe | Deux gates présents à T2/T3 ; T1 parent=T0 | ✅ | Protection contre le random walk effectivement exercée. |
| Accepter neutre/incertain en `young` | Trois promotions live malgré IC recouvrant 50 % | ✅ | Comportement conforme. |
| Rejeter si `ci_high < 0,5` | Tests unitaires ; utilisé ensuite par C0 fork (c) | ✅ | Le fork (c) a réellement été rejeté par cette règle. |
| Limiter `young` à T1-bis/T2/T3 | Test T4 rejeté ; T3 produit `complete_probe` | ✅ | Aucun T4 lancé. |
| Manifests avec SHAs exacts candidat/parent/fixed | Filiation vérifiée par les chargeurs T2/T3 | ✅ | Chaîne mécaniquement solide. |
| Régime établi = non-régression + hausse sur deux tours | Tests unitaires présents | 🧪 | Non exécuté, car la campagne longue n’a jamais été autorisée. |
| d9 contre Scan comme télémétrie | Aucun résultat d9-vs-Scan par tour publié ; les gates depth 9 sont Jass-vs-Jass | ❌ | Point de télémétrie manquant. Ce n’était pas un veto de promotion. |

### 6.3 Sections 5–6 — recette T1-bis et répétition T2/T3

| Exigence v3.2 | Résultat observé | Statut | Commentaire |
|---|---|---|---|
| Génération T1-bis depuis T0 figé | 300 parties d10, 206 648 positions | ✅ | Entrées R2 immuables vérifiées. |
| G1 léger avec quota en positions | 3 848 positions G1 à T1-bis ; quota fail-closed | ✅ | G1 a réellement tiré. |
| Cap-arbiter actif | `--cap-arbiter d14` dans la recette | ✅ | Identique entre les tours. |
| Sidecars provenance et trajectoires | Générés et archivés | ✅ | Ont permis le mining post-hoc T3. |
| Relabel d14+EGDB strict | Exécuté sur tous les tours | ✅ | Nombre de records conservé et contrôlé. |
| Garde cache×processus avant lancement | `cache_guard.py` dans le runner | ✅ | Audits ultérieurs : 9 216 Mio agrégés pour ~21 930 Mio de budget. |
| Restart-on-death | Implémenté dans la jauge | ✅ | T2 a subi un timeout moteur sur une position ; redémarrage réussi, erreur comptabilisée. |
| Fit `wdl_finetune`, anchor 0,05 | Exécuté à chaque tour | ✅ | Recette stable. |
| Cellule de contrôle à lambda très élevée | Pas de candidat de contrôle ni verdict structuré publié dans la chaîne live | ❌ | Garde-fou demandé par la v3.2 non démontré dans le runner exécuté. |
| z-stats obligatoires | Possiblement dans les logs de fit, mais aucun artefact structuré ou résumé par tour n’est publié | ⚠️ | Non vérifiable depuis `jass-control` et les rapports consolidés. |
| Déplacement des poids global + EXTRA/PST/patterns | Non publié par tour | ❌ | Dette de diagnostic/traçabilité. |
| Jauge 1 600 figée, p1–p4 | Même gauge R2 et quatre strates à chaque tour | ✅ | Résultats lisibles et comparables. |
| N/W/D/L, erreurs, redémarrages et hashes | Présents dans les artefacts R2 de jauge ; publication GitOps ancienne limitée | ⚠️ | T2 documente une erreur/restart ; tous les détails ne sont pas remontés dans les anciens statuts. |
| Même recette entre T1-bis, T2 et T3 | Seul `parent.pjtw.gz` est remplacé après vérification | ✅ | C’est le point de conformité le plus fort de la chaîne. |
| Publication complète par tour | Conversion/gates/promotion disponibles ; tip, z-stats, poids, d9-Scan et mining par tour incomplets | ⚠️ | Verdict scientifique possible, audit exhaustif de la dynamique du fit incomplet. |

### 6.4 Section 7 — mining passif

| Exigence v3.2 | Résultat observé | Statut | Commentaire |
|---|---|---|---|
| Mining strictement hors boucle | Architecture et tests interdisent imports fit/gen/promotion | ✅ | Aucun impact causal sur T1–T3. |
| Invocation pendant chaque tour | Absente des SHAs exécutés `6d90e72`, `f5410cbf` et `1b907771` | ❌ historique | Le mineur existait et était testé, mais le runner historique ne l’appelait pas. |
| Correction pour les futurs runs | Runner courant appelle explicitement `probe_mining.py` après relabel et avant fit | ✅ actuel | Omission corrigée par la suite. |
| WIN→DRAW et WIN→LOSS dès v1 | Tests présents ; mining T3 réel : 1 262 WIN→DRAW et 119 WIN→LOSS | ✅ | Les deux catégories sont bien représentées. |
| Unité = parent, cap par parent | `cap-per-parent=1` passif ; corpus teacher = 1 381 parents | ✅ | Pas de pseudo-réplication par sibling. |
| Split futur par parent/game | Teacher : 1 131 train / 250 holdout, split par partie | ✅ | B2/B3 alignés sur les mêmes parents/paires/split. |
| Inventaire par tour | T3 post-hoc seulement | ⚠️ | T1-bis et T2 n’ont pas leurs inventaires passifs contemporains. |
| Distribution pièces/p1–p4/tier et hashes | Prévue dans les outils et artefacts R2 ; non entièrement remontée dans le statut | ⚠️ | Engine SHA et weights SHA sont publiés ; ventilations détaillées non visibles dans le résumé GitOps. |

Le correctif d’intégration ne modifie pas rétroactivement les résultats T1–T3. Il garantit seulement que la prochaine lignée ne reproduira pas cette perte d’observabilité.

### 6.5 Sections 8–9 — verdict de sonde et teacher causal

| Exigence v3.2 | Résultat observé | Statut | Commentaire |
|---|---|---|---|
| Router le cas D vers le teacher | T1–T3 plats, puis mining 0776 et smoke 0777 | ✅ | Séquence conforme. |
| Teacher post-sonde uniquement | Mining et fits teacher lancés après T3 | ✅ | Pas de contamination de la sonde. |
| A baseline WDL adjudicated | Cellule A exécutée | ✅ | Hard-conversion 50,0966 %. |
| B1 siblings oracle en WDL ordinaire | Cellule B1 exécutée | ✅ | Force non régressive, conversion −0,99 point. |
| B2 préférence statique | Cellule B2 exécutée | ✅ | Conversion +0,71 point, mais régression vs A et référence absolue. |
| B3 préférence through-search/leaf-mode | Cellule B3 exécutée | ✅ | Conversion −1,86 point et régression. |
| Oracle symétrique d14+EGDB | Parents/children/siblings certifiés par le pipeline teacher | ✅ | 2 048 parents causaux avant oracle sibling, 1 381 retenus. |
| B2/B3 mêmes parents, paires, splits et budgets | Contrat publié : 1 381 parents/paires, alignement exact | ✅ | Comparaison causalement propre. |
| Caps par parent et split par partie | Maximum 4 siblings inspectés ; split 1 131/250 | ✅ | Contrôles principaux respectés. |
| Mouvement des poids et distributions détaillées | Artefacts non résumés dans le statut | ⚠️ | Diagnostic secondaire incomplet. |
| Gagnant ≥ +0,02 sans régression | Aucun bras éligible | ❌ scientifique | `decision=reject`, `scientific_status=complete_no_signal`. |
| Confirmation du seul gagnant | Aucun gagnant | ⏭️ | 0781/0782 correctement non soumis. |

### 6.6 Sections 10–11 — MTC, ressources et tests obligatoires

| Exigence v3.2 | Résultat observé | Statut | Commentaire |
|---|---|---|---|
| Audit MTC avant la sonde | T1-bis/T2/T3 ont utilisé `ALLOW_MTC_SKIP=1` et consigné l’ignorance | ❌ temporel | Principale déviation méthodologique de lancement. |
| MTC actif, lisible, version/inventaire consigné | Audits 0778 et 0779 après coup | ✅ actuel | 138 entrées, ~30,17 Go, même empreinte d’inventaire sur les deux boxes. |
| Smoke MTC concurrent | Deux processus concurrents, succès sur ccx33 et cpx62 | ✅ actuel | Environnement prêt pour les futurs jobs fail-closed. |
| Cache agrégé sous budget | 24 × 384 Mio = 9 216 Mio ; budget ~21 930 Mio | ✅ | Marge suffisante sur les deux boxes. |
| Tests labels/draw-band | Tests unitaires présents et exécutés au préflight | ✅ | Couverture conforme à la section 11.1. |
| Tests promotion | Tests unitaires présents et exécutés | ✅ | Neutralité, rejets, double gate, T4 interdit, established. |
| Tests mining hors boucle | Tests présents et exécutés | ✅ test | L’intégration live historique manquait malgré eux. |
| `n_restarts` agrégé | Outil et agrégateur testés | ✅ | T2 fournit un cas réel de récupération. |
| Artefacts intermédiaires chargeables | T2 et T3 n’acceptent que le résultat précédent vérifié | ✅ | La filiation réussie est une preuve live forte. |
| Reprise depuis checkpoint vérifiée | Aucun exercice live de reprise à partir d’un checkpoint scientifique n’est documenté | ❌ | Le doublon T3 n’est pas une reprise de checkpoint. |
| Erreurs et timeouts séparés | Outils structurés ; timeout T2 comptabilisé | ✅ | Conforme. |
| Batterie actuelle après PR 342 | 111 tests jobs + 15 tests runner-v3 annoncés verts | ✅ actuel | Couverture renforcée après la sonde. |

### 6.7 Sections 12–13 — livrables et bon pour lancement

| Livrable/checklist | État | Statut |
|---|---|---|
| Règle `blocks_draw_band` + vérificateur | Livré et testé | ✅ |
| Compteurs de survie tip | Livrés/testés, publication live incomplète | ⚠️ |
| `promotion_gate.py young|established` | Livré/testé | ✅ |
| Parent + référence fixe | Exécuté sur les trois tours | ✅ |
| Manifests JSON et hashes | Suffisants pour la filiation fail-closed | ✅ |
| Audit MTC avant lancement | Non ; effectué après | ❌ temporel |
| Garde cache×processus | Exécutée | ✅ |
| Tests unitaires/intégration | Exécutés | ✅ |
| Runner T1-bis reproductible | Exécuté avec succès | ✅ |
| T1-bis/T2/T3 et verdict | Terminés | ✅ |
| Mining passif par tour | T3 post-hoc ; T1/T2 absents ; intégration future corrigée | ⚠️ |
| Rapport final de sonde | Résumé dans CURRENT ; le présent document complète la matrice formelle v3.2 | ✅ à date |
| Confirmation/campagne longue | Bloquées par absence de signal | ⏭️ |
| Aucun teacher/DEEP_EG avant T3 | Respecté | ✅ |

## 7. Résultat détaillé du teacher A/B1/B2/B3

Le corpus était suffisamment large pour un smoke : 2 490 parties inspectées, 210 078 transitions, 2 048 parents causaux avant certification des siblings, puis 1 381 parents teacher retenus.

| Cellule | Conversion dure | Delta vs A | Gate vs A | Gate vs référence absolue | Éligible |
|---|---:|---:|---|---|---|
| A | 50,0966 % | — | baseline | baseline | non applicable |
| B1 | 49,1063 % | −0,9903 pt | pass | pass | non |
| B2 | 50,8092 % | +0,7126 pt | régression | régression | non |
| B3 | 48,2367 % | −1,8599 pt | régression | régression | non |

Le seuil pré-engagé était un delta d’au moins +2 points sans régression. Le verdict est donc sans ambiguïté : `reject`, `complete_no_signal`, `winner=null`.

Interprétation par hypothèse :

- **B1** : l’information contrefactuelle peut être absorbée sans coût généraliste détecté, mais elle ne se transforme pas en meilleure conversion.
- **B2** : une faible hausse ponctuelle de conversion existe, mais elle est trop petite et associée à une régression ; ce n’est pas un candidat à scaler.
- **B3** : le through-search/MMTO n’apporte pas la protection espérée contre la décalibration. Il est ici plus mauvais que B2 en conversion et régresse également en force.
- **B2/B3 ensemble** : le témoin prévu par la v3.2 conclut contre un bénéfice spécifique du leaf-mode. La préférence causale telle qu’encodée ne compose pas.

## 8. Extensions postérieures à la v3.2

### 8.1 Fork (c) — départ matériel affaibli

Cette expérience n’était pas la ligne principale figée de la v3.2, mais elle a testé l’explication « le bootstrap fort sature la logistique ».

| Mesure | Résultat | Seuil | Verdict |
|---|---:|---:|---|
| Refit faible vs fort | −32,5 Elo ; rate 45,33 %, IC [41,35 ; 49,32] | `ci_high ≥ 0,5` | Régression établie |
| Delta hard-conversion | −1,11 pt | ≥ +2 pts | Négatif |
| Divergence policy brute | 5,5 % | ≥ 5 % | Différence réelle |
| Divergence après refit | 13,67 % | ≥ 5 % | Différence accrue, sans bénéfice |

Conclusion : changer le bassin de départ fait jouer le modèle différemment mais pas mieux. Le T1-C `0775` a été correctement annulé.

### 8.2 Diagnostic du doublon T3

La tentative scientifique réussie reste autoritaire. Le doublon ultérieur a fini avec `exit_code=-1`. Le diagnostic `0780b` conclut :

```text
probable_cause = wrapper_lost_without_exit_status
scientific_result_preserved = true
replay_science_required = false
```

La cause infrastructurelle précise reste à investiguer, car les logs n’apportent pas d’indice positif et les deux tentatives n’avaient pas le même code SHA. Le runner a depuis été durci pour publier un diagnostic plus explicite lorsqu’un wrapper disparaît.

### 8.3 Sparring-vs-Scan Phase 0

Le job `0784` est le premier pas hors de la famille de données auto-générées/oracle interne. Il doit vérifier de bout en bout :

```text
Gen2-MMTO vs Scan d9
→ vrais résultats W/D/L de parties
→ labels STM-POV
→ corpus JNNW valide
→ round-trip
→ mini-fit WDL consommable
```

Le smoke utilise 10 ouvertures × 2 couleurs. Il ne mesure pas encore un gain scientifique et ne peut pas autoriser L3 à lui seul. Un smoke vert autorisera seulement la préparation d’un C0 puissant avec corpus, holdout P3/P4 et gates généralistes.

## 9. Ce qui est scientifiquement fermé à date

| Hypothèse | Évidence | Statut |
|---|---|---|
| Un seul tour ADJ+G1 suffit | DOE 0726, conversion ~0,67 | Fermée : plateau un tour |
| Répéter ADJ+G1 sur trois tours compose | T1/T2/T3 plats | Fermée pour cette recette et ce budget |
| G4 augmente la conversion | DOE 0726, baisse d’environ 1 point | Fermée |
| Un départ 0,3× dé-sature et apprend mieux | C0 fork (c), force et conversion en baisse | Fermée |
| Les erreurs causales WIN→DRAW/LOSS suffisent via WDL B1 | B1 −0,99 point, force pass | Fermée en v1 |
| La préférence statique B2 débloque la conversion | +0,71 point mais régression | Fermée en v1 |
| MMTO/leaf-mode B3 protège la préférence et compose | −1,86 point + régression | Fermée en v1 |
| Une campagne longue peut être lancée sur le signal actuel | Aucun signal confirmé | Non autorisée |

## 10. Ce qui reste ouvert

1. **Labels issus de vraies parties contre un adversaire plus fort.** C’est la différence causale majeure du sparring-vs-Scan : le signal ne dépend plus uniquement de la politique et des angles morts de Jass.
2. **Effet spécifique sur P3 mince.** Le prochain C0 doit être dimensionné et stratifié pour détecter un gain réel sur les avantages fins, pas seulement un déplacement global bruité.
3. **Usage de MTC comme amélioration de recherche terminale.** L’environnement est maintenant validé ; cela peut améliorer le chemin de conversion à faible nombre de pièces, sans constituer à lui seul un nouvel apprentissage de P3.
4. **Classe linéaire spécialisée éventuelle.** La v3.2 ne l’autorisait qu’après preuve qu’un signal existe mais ne transfère pas. Cette preuve n’existe toujours pas : les teachers n’ont pas produit de signal positif à transférer.

## 11. Où en est réellement le programme L3

### 11.1 Côté ingénierie

La plateforme nécessaire est largement disponible : runner-v3, entrées R2 immuables, filiation fail-closed, double gate, conversion stratifiée, mining, teacher, audits MTC, diagnostics de tentative et publication de petits verdicts scientifiques.

Les correctifs post-sonde réduisent plusieurs risques pour la prochaine lignée :

- le mining est désormais appelé par le runner courant ;
- les audits MTC peuvent être exigés fail-closed ;
- les petits JSON scientifiques remontent dans `jass-control` ;
- la perte du statut de sortie est mieux diagnostiquée.

### 11.2 Côté scientifique

Une nouvelle lignée L3 fondée sur ADJ+G1, le départ faible ou le teacher causal v1 **n’est pas justifiée**. Le blocage n’est plus principalement l’outillage ; il est l’absence d’un mécanisme ayant franchi simultanément :

```text
gain de conversion pertinent
+ non-régression généraliste
+ confirmation indépendante
```

Le prochain point de décision est le suivant :

```text
0784 Phase 0 technique
├── rouge → corriger uniquement la tuyauterie, puis rejouer à l'identique
└── vert  → concevoir/lancer un vrai C0 sparring-vs-Scan
             ├── sans signal → pas de nouvelle L3 sur cette voie
             └── signal + non-régression → confirmation indépendante
                                             └── seulement alors : amorcer L3
```

## 12. Dettes de conformité et actions recommandées

### Priorité 1 — avant tout nouveau C0 scientifique

1. Rendre l’audit MTC fail-closed dans le job scientifique concerné (`ALLOW_MTC_SKIP=0`) et vérifier le même host/path/inventaire au moment de la consommation.
2. Exiger et publier un manifeste complet contenant les métriques réellement demandées par la v3.2 : z-stats, mouvements de poids par groupe, sources de labels et survie du tip.
3. Ajouter une télémétrie d9-vs-Scan explicite si elle reste jugée utile ; ne pas la confondre avec le gate Jass-vs-Jass à depth 9.
4. Conserver l’appel live à `probe_mining.py` et vérifier que les sorties de chaque tour sont effectivement présentes dans l’inventaire R2.

### Priorité 2 — design du C0 sparring-vs-Scan

1. Figer version et budget de Scan.
2. Utiliser des résultats réels de parties et un split par partie/ouverture.
3. Équilibrer ou pondérer les issues W/D/L afin que les nombreuses défaites contre Scan ne dominent pas mécaniquement le fit.
4. Construire un holdout P3/P4 frais, sans recouvrement avec la jauge historique ni le corpus d’entraînement.
5. Ancrer le premier candidat à Gen2-MMTO et tester le WDL avant d’ajouter un éventuel finisher MMTO.
6. Pré-engager les gates : non-régression vs Gen2-MMTO et référence absolue, delta P3 utile, garde P4, mesure vs Scan.

### Priorité 3 — hygiène de preuve

1. Ne pas qualifier une exigence de « conforme live » sur la seule base d’un test unitaire.
2. Distinguer systématiquement un artefact absent de `jass-control` d’un artefact absent de R2.
3. Publier un résumé scientifique compact pour chaque job ancien ou futur, afin d’éviter de dépendre des logs complets.

## 13. Verdict final au 18 juillet 2026

La v3.2 a correctement organisé la décision : elle a empêché une dérive cumulative, borné la sonde, routé le cas plat vers une expérience causale et empêché une campagne longue sans signal confirmé.

Son résultat scientifique est négatif mais utile :

```text
ADJ+G1 multi-tours : non régressif, mais ne compose pas
teacher causal v1 : aucun bras éligible
fork départ faible : régression
```

Les écarts de conformité identifiés — audit MTC tardif, mining historique non invoqué, télémétrie Scan et diagnostics de fit incomplets — doivent être corrigés pour la prochaine campagne, mais ne fournissent pas une explication plausible au plateau observé :

- le mining était hors boucle et ne pouvait pas changer les candidats ;
- le d9-vs-Scan n’était pas un veto de promotion ;
- l’audit MTC vérifie l’environnement et non l’objectif d’apprentissage ;
- les trois tours utilisent néanmoins une recette, une jauge, une référence et une filiation cohérentes.

À date, **il ne faut donc pas démarrer une nouvelle L3 sur les mécanismes v3.2 déjà testés**. Il faut terminer la validation technique du sparring-vs-Scan, puis exiger un C0 positif et confirmé avant de lancer une nouvelle lignée.
