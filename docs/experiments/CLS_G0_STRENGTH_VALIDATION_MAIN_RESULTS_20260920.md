# CLS G0 — résultat de l'étude de force HIER / CURRICULUM (2069)

Date : 20 septembre 2026. Statut : **étude de cas terminée ; `SUBSTANTIAL_LOSS_EXCLUDED`**.

Ce document rapporte le résultat existant. Il ne modifie aucun contrat, verdict G0, candidat, cadence, ouverture ou règle statistique. CURRICULUM reste champion.

## 1. Source terminale et traçabilité

Source principale : [statut terminal 2069 au commit de contrôle 4a5b2e73](https://github.com/jfrancoiscollin/jass-control/blob/4a5b2e7379f5a0072b9d3c44558286992238a664/status/cpx62-2069-l3-cls-g0-strength-main-production-v1.json).

- Job : `cpx62-2069-l3-cls-g0-strength-main-production-v1`.
- Tentative : `20260920T094538Z-0304fc16`.
- Code d'exécution : `0304fc16bf4c80f6e008a329b28e3e5ea86f5938`.
- Début : 20 septembre 2026, 09:45:43 UTC / 11:45:43 Europe/Paris.
- Fin : 20 septembre 2026, 10:35:24 UTC / 12:35:24 Europe/Paris.
- État : `completed`, `exit_code=0`.
- Terminal : `CLS_G0_STRENGTH_MAIN_COMPLETE_V1`.
- Classification : `SELECTED_CANDIDATE_CASE_STUDY`.
- Verdict statistique et scientifique publié : `SUBSTANTIAL_LOSS_EXCLUDED`.
- Blob Git du statut : `56760c8048efa72411b3da9202419500ce7a927d`.
- Reçu de lancement indiqué par le résumé : `b24bff3426acb91c8d526f82e002104830850a608f95db60ec9e95df91154633`.
- Spécification normalisée : `a5e649643d516ce47939f6653b9c9d249584a98854c9e37fd31f43068203f315`.
- Sélection : `0a9497f68387b1e0b65a36a9d0da538e9cfd7932167c0d2b0f664e15b81c53c1`.

Le résumé Launch-V2 indique `mode=production`, `production_admitted=true`, `publisher_roundtrip_verified=true`. La présente lecture contrôle le statut GitOps et la cohérence de son résumé : elle ne prétend pas être une relecture indépendante des 576 trajectoires R2.

Préfixe d'archive déclaré :
`r2:jass-data/runs/cpx62-2069-l3-cls-g0-strength-main-production-v1/20260920T094538Z-0304fc16`.

L'inventaire terminal référence notamment `stage-games.json.gz` (2 001 245 octets), `study-report.json`, `opening-freeze.json`, `runtime-identity.json`, `execution-evidence.json`, `launch-receipt.json`, `scientific-summary.json` et `RESULTS.md`.

## 2. Question et conditions inchangées

[Annexe principale préenregistrée](CLS_G0_STRENGTH_VALIDATION_MAIN_V1_20260920.md), implémentée au code d'exécution ci-dessus. [#1048](https://github.com/jfrancoiscollin/jass/pull/1048) a défini une admission opérationnelle séparée de 3 000 secondes de travail projeté, sans changer les plafonds durs, la cadence, les modèles, les ouvertures, le nombre de parties ou l'inférence. Le lancement principal est [jass-control #776](https://github.com/jfrancoiscollin/jass-control/pull/776).

**288 ouvertures, une paire avec couleurs inversées chacune : 576 parties HIER/CURRICULUM.** 100 ms nominales par coup avec plafond de réponse bout-à-bout de 120 ms après initialisation ; ce n'est pas un contrôle de temps avec chute du drapeau stricte à 100 ms. Même binaire natif, mêmes paramètres compilés, livre désactivé, un thread par joueur, TT 16 MiB et même EGDB ; quatre travailleurs.

HIER : `95bed3ac9fac4368809609fb1a981ee863401a30ca623fb7bfa3caf7eaddf628`.

CURRICULUM : `319d174f4b548b1655aad4bb30d4c6dc86c08dd715c9c23f8b19ba1937dc0be1`.

Les ouvertures sont celles scellées avant les parties, générées par trajectoires légales sans filtrage par score. Les exclusions documentées portent sur les diagnostics et la calibration, pas sur la totalité historique des données d'entraînement. Ni représentativité des ouvertures humaines ni calibration générale de G0 ne sont revendiquées.

## 3. Résultat publié

| Mesure | Valeur |
|---|---:|
| Paires complètes | 288 |
| Parties entre les deux modèles | 576 |
| Recherches démarrées, initialisations comprises | 62 005 |
| Parties censurées au plafond administratif | 10 |
| Score descriptif HIER, plafond compté à 0,5 uniquement pour cette description | 0,5026041666666666 (50,2604 %) |
| Bornes moyennes de score dues à la censure | [0,4939236111111111 ; 0,5112847222222222] |
| Intervalle préenregistré à 95 % | [0,41389671183445104 ; 0,5913116214988823] |
| Frontière correspondant à une perte de 100 Elo logistiques | 0,35993500019711494 |
| Verdict | `SUBSTANTIAL_LOSS_EXCLUDED` |

Distribution pentanomiale **des paires**, avec demi-point descriptif pour les plafonds :

| Total de points HIER sur les deux couleurs | Paires |
|---|---:|
| 0 | 34 |
| 0,5 | 14 |
| 1 | 189 |
| 1,5 | 17 |
| 2 | 34 |

Ces cinq comptes totalisent 288 paires. Ils ne permettent pas de reconstruire à eux seuls les victoires/nulles/défaites individuelles : une paire à 1 point peut être deux nulles ou une victoire et une défaite. Aucun compte individuel non publié n'est inféré ici.

## 4. Pourquoi le verdict est celui-ci

Le calcul reste celui de l'annexe, sans nouvel essai statistique :

- `r = sqrt(log(2/0.05)/(2*288)) = 0.08002689927666005` ;
- une partie au plafond de 160 demi-coups reste de score inconnu dans [0,1] pour l'inférence ;
- `CI = [max(0, mean(L)-r), min(1, mean(U)+r)]` ;
- la borne basse 0,41389671183445104 est strictement supérieure à la frontière 0,35993500019711494.

Donc une perte de **100 Elo logistiques ou davantage** est exclue dans les conditions et sous les hypothèses d'échantillonnage du protocole. La confiance nominale est de 95 %, au niveau des unités appariées, pas de 576 parties supposées indépendantes. Le budget d'erreur propre à cette étude est `alpha_spent=0.05` ; il n'efface aucun budget historique CLS/ED4.

## 5. Interprétation et limites

Le score descriptif est proche de 50 %, mais **ni supériorité, ni égalité de force, ni non-infériorité à petite marge ne sont démontrées**. L'intervalle est large et le protocole visait explicitement une perte importante, pas quelques Elo. Le traitement pessimiste des dix plafonds est conservé dans le verdict.

HIER a échoué au filtre G0 V1 et n'a pas montré une perte d'au moins 100 Elo dans cette étude. Cela distingue le rejet technique/de recherche du filtre d'une preuve de catastrophe en parties à cette cadence. Cela ne démontre ni que G0 est inutile ou défectueux, ni son taux de faux rejets sur d'autres candidats. Un seul candidat sélectionné et une seule cadence ne calibrent pas l'ensemble du filtre.

## 6. Contrôles effectivement réalisés lors de cette lecture

- Copie locale du statut terminal dont la reconstruction UTF-8 reproduit exactement le blob Git `56760c8048efa72411b3da9202419500ce7a927d`.
- Vérification des identités job/tentative/code/modèles/sélection, état final, admission déclarée, 288 paires/576 parties et compteurs d'effets.
- Recalcul du score à partir des cinq comptes, des bornes de censure, du rayon de Hoeffding, de l'intervalle et du verdict : concordance à 1e-12 près.
- Dix tests synthétiques locaux du vérificateur réussis, couvrant notamment les trois conclusions, un statut encore actif, un échantillon incomplet, une incohérence de censure, un intervalle erroné et une admission non vérifiée. Ces tests ne sont pas de nouvelles parties ni une exécution native du match.
- Pas de lecture indépendante du contenu de `stage-games.json.gz` pendant cette clôture documentaire ; les affirmations sur les résultats complets sont celles du résumé terminal publié et du code gelé.

## 7. Décision et point de reprise

**L'étude 2069 est terminée et son interprétation est consignée.** Ne pas relancer la calibration, la répétition ou le même match. Ne pas prolonger l'échantillon ni changer la marge après ce résultat.

`INTERPRET_NO_AUTOMATIC_PROMOTION` reste l'étape terminale. Zéro nouvel entraînement, recherche Scan, promotion, bake ou réinjection n'a été effectué. **Le FAIL G0 V1 reste acquis ; CURRICULUM reste champion.**

Aucune nouvelle étude n'est lancée par ce rapport. Une éventuelle validation prospective d'une version future du filtre constituerait un autre protocole, avec plusieurs cas et une preuve de force adaptée ; ce résultat ne l'autorise pas automatiquement. La clôture de cette étude n'est pas une déclaration de clôture globale de CLS.
