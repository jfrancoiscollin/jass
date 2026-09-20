# CLS — suivi et reprise du match principal 2069

Date : 20 septembre 2026. Document opérationnel, pas un nouveau protocole.

## État terminal vérifié

Le match est **terminé** depuis le 20 septembre 2026 à **10:35:24 UTC / 12:35:24 Europe/Paris**, état `completed`, `exit_code=0`. Les **288 paires / 576 parties HIER-CURRICULUM** sont complètes. Terminal : `CLS_G0_STRENGTH_MAIN_COMPLETE_V1`. Verdict publié : **`SUBSTANTIAL_LOSS_EXCLUDED`**.

[Rapport terminal et portée de la vérification](../experiments/CLS_G0_STRENGTH_VALIDATION_MAIN_RESULTS_20260920.md).

Source immuable : [statut au commit de contrôle 4a5b2e73](https://github.com/jfrancoiscollin/jass-control/blob/4a5b2e7379f5a0072b9d3c44558286992238a664/status/cpx62-2069-l3-cls-g0-strength-main-production-v1.json), blob `56760c8048efa72411b3da9202419500ce7a927d`.

Les observations précédentes de 450 puis 518 parties démarrées étaient des points de progression non terminaux, désormais dépassés. Elles n'ont pas servi à une décision statistique ou à une modification du match.

## Identités de reprise

- Job : `cpx62-2069-l3-cls-g0-strength-main-production-v1`.
- Tentative : `20260920T094538Z-0304fc16`.
- Code du match : `0304fc16bf4c80f6e008a329b28e3e5ea86f5938`.
- Lancement : [jass-control #776](https://github.com/jfrancoiscollin/jass-control/pull/776), fusion `d289a6f8e7adab76ef7979128d8826b8f44e7d32`.
- Prérequis : `cpx62-2068-l3-cls-g0-strength-main-rehearsal-v2`, tentative `20260920T092427Z-0304fc16`.
- Reçu de répétition : `cc2507e9863e8cb2ac5e05d6f7293cc4a5f92befa00fd7715a510c36a2e78b37`.
- Reçu de production indiqué par le résumé : `b24bff3426acb91c8d526f82e002104830850a608f95db60ec9e95df91154633`.
- Spécification normalisée : `a5e649643d516ce47939f6653b9c9d249584a98854c9e37fd31f43068203f315`.
- Sélection : `0a9497f68387b1e0b65a36a9d0da538e9cfd7932167c0d2b0f664e15b81c53c1`.
- HIER : `95bed3ac9fac4368809609fb1a981ee863401a30ca623fb7bfa3caf7eaddf628`.
- CURRICULUM : `319d174f4b548b1655aad4bb30d4c6dc86c08dd715c9c23f8b19ba1937dc0be1`.

## Résultat et portée

62 005 recherches, initialisations comprises. Dix parties censurées au plafond administratif. Score HIER descriptif avec demi-point pour les plafonds : **50,2604 %**. Intervalle préenregistré à 95 %, censure comprise : **[41,3897 % ; 59,1312 %]**. Sa borne basse dépasse **35,9935 %**, frontière d'une perte de **100 Elo logistiques**.

Le contrôle local du résumé a reproduit les comptes pentanomiaux, le score, les bornes de censure, l'intervalle et le verdict. La copie source est byte-identique au blob Git publié. Ce contrôle n'est pas une relecture indépendante de l'archive R2 des 576 trajectoires.

Le résultat exclut une perte d'au moins 100 Elo dans la population/cadence et sous les hypothèses du protocole. Il **ne démontre ni supériorité ni égalité de force ni absence de petite régression**, et ne calibre pas globalement G0 sur un seul cas. Le FAIL G0 est un résultat du filtre, pas un échec technique d'exécution ; il n'est pas réécrit.

## Contrat conservé

[Annexe principale](../experiments/CLS_G0_STRENGTH_VALIDATION_MAIN_V1_20260920.md), implémentation `jobs/tools/cls_g0_strength_main.py` et profil `jobs/launch_profiles/cls-g0-strength-main-resource-v2.json` au code scellé. L'admission opérationnelle séparée [#1048](https://github.com/jfrancoiscollin/jass/pull/1048) ne change ni cadence ni échantillon.

288 paires, 576 parties, 100 ms nominales par coup et plafond bout-à-bout de 120 ms après initialisation. Quatre travailleurs, un thread par joueur, même binaire/paramètres/EGDB, TT 16 MiB, livre désactivé, ouvertures reprises exactement de la répétition. Marge 100 Elo, intervalle fixe de Hoeffding par paire, alpha propre à l'étude 0,05, censure des plafonds de 160 demi-coups. Aucun changement après résultat.

## Prochaine reprise

**Ne pas recommencer 2066, 2068 ou 2069. L'étude est terminée et interprétée.** Relire le rapport terminal ci-dessus avant toute nouvelle décision.

`INTERPRET_NO_AUTOMATIC_PROMOTION` reste la frontière. Aucun nouveau job n'est autorisé par cette note ; une éventuelle version future du filtre demanderait son propre protocole. La clôture de cette étude ne clôt pas automatiquement toute CLS.

**Le FAIL G0 V1 de HIER demeure acquis. CURRICULUM reste champion. Pas de promotion, bake, réinjection, nouvelle dose, nouvelle cadence ou nouvelle direction scientifique automatique.**
