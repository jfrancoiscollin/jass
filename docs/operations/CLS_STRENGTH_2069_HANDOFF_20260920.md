# CLS — suivi et reprise du match principal 2069

Date de cette note : 20 septembre 2026. Document opérationnel, pas un nouveau protocole.

## Dernière observation, non terminale

Au statut publié le 20 septembre 2026 à **10:28:04 UTC / 12:28:04 Europe/Paris**, le job est `running`, phase `execute-paired-stage`. Le compteur d'effets rapporte **518 parties démarrées**, et non 518 parties nécessairement terminées, sur 576 prévues ; 55 885 recherches ont été démarrées. Aucun verdict scientifique n'est publié à cet instant.

Source immuable : [statut au commit de contrôle 46a51381](https://github.com/jfrancoiscollin/jass-control/blob/46a513814b881e010e584eb4ec7193b597b98c03/status/cpx62-2069-l3-cls-g0-strength-main-production-v1.json).

Ne pas présenter cette observation comme un état temps réel après son horodatage. Relire le statut courant avant toute action.

## Identités de reprise

- Job : `cpx62-2069-l3-cls-g0-strength-main-production-v1`.
- Tentative : `20260920T094538Z-0304fc16`.
- Code du match : `0304fc16bf4c80f6e008a329b28e3e5ea86f5938`.
- Lancement : [jass-control #776](https://github.com/jfrancoiscollin/jass-control/pull/776), fusion `d289a6f8e7adab76ef7979128d8826b8f44e7d32`.
- Prérequis : `cpx62-2068-l3-cls-g0-strength-main-rehearsal-v2`, tentative `20260920T092427Z-0304fc16`.
- Reçu de répétition : `cc2507e9863e8cb2ac5e05d6f7293cc4a5f92befa00fd7715a510c36a2e78b37`.
- Spécification normalisée : `a5e649643d516ce47939f6653b9c9d249584a98854c9e37fd31f43068203f315`.
- Sélection des ouvertures : `0a9497f68387b1e0b65a36a9d0da538e9cfd7932167c0d2b0f664e15b81c53c1`.
- HIER : `95bed3ac9fac4368809609fb1a981ee863401a30ca623fb7bfa3caf7eaddf628`.
- CURRICULUM : `319d174f4b548b1655aad4bb30d4c6dc86c08dd715c9c23f8b19ba1937dc0be1`.

## Contrat déjà gelé

[Annexe principale](../experiments/CLS_G0_STRENGTH_VALIDATION_MAIN_V1_20260920.md), implémentation `jobs/tools/cls_g0_strength_main.py` et profil `jobs/launch_profiles/cls-g0-strength-main-resource-v2.json` au code ci-dessus. L'admission opérationnelle séparée de [#1048](https://github.com/jfrancoiscollin/jass/pull/1048) autorise 3 000 secondes de travail projeté, dans les plafonds durs inchangés de 3 600/4 200 secondes ; elle ne change ni cadence ni échantillon.

288 paires avec couleurs inversées, 576 parties. 100 ms nominales par coup, plafond bout-à-bout de 120 ms après initialisation ; quatre travailleurs, un thread par joueur, même binaire, mêmes paramètres compilés, même EGDB, TT 16 MiB, livre désactivé. Ouvertures consommées exactement depuis la répétition authentifiée, jamais régénérées en production.

Marge de perte substantielle : 100 Elo logistiques, frontière de score `1/(1+10**(100/400))`. Intervalle fixe de Hoeffding au niveau des 288 paires avec alpha propre à l'étude de 0,05. Une partie au plafond administratif de 160 demi-coups est censurée, avec bornes de score [0,1] pour l'inférence, pas une nulle certaine. Aucune inférence intermédiaire ni extension optionnelle.

## Suite exacte

1. Si le même job est sain et actif, ne pas le dupliquer, le redémarrer, modifier son code, son échantillon ou ses seuils.
2. À la fin seulement, vérifier `completed/exit_code=0`, la tentative, les modèles, les 288 paires/576 parties, la sélection, l'admission de production et les identités de reçus.
3. Relire le rapport publié, contrôler la cohérence des comptes pentanomiaux, de la censure, de l'intervalle et du verdict sous le contrat inchangé. Distinguer un contrôle du résumé GitOps d'une relecture indépendante des 576 trajectoires R2 ; ne pas prétendre avoir effectué cette dernière sans l'avoir réellement faite.
4. En cas d'échec technique, préserver les données consommées, diagnostiquer le défaut prouvé, consigner l'incident central et ne jamais transformer une erreur en nulle/perte ni assouplir une limite après résultat.
5. Publier l'interprétation bornée et le point de reprise. Les terminaux possibles sont `SUBSTANTIAL_LOSS_SUPPORTED`, `SUBSTANTIAL_LOSS_EXCLUDED`, `INDETERMINATE` ; aucun ne vaut supériorité, G0 PASS ou promotion.

**Le FAIL G0 V1 de HIER est immuable. CURRICULUM reste champion. Pas de promotion, réinjection, nouvelle dose, nouvelle cadence ou nouvelle direction scientifique automatique.**
