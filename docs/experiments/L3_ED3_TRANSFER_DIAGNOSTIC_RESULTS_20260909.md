# ED3-T1 — diagnostic descriptif des classements et décisions

9 septembre 2026. Le [protocole gelé](L3_ED3_TRANSFER_DIAGNOSTIC_V1_20260909.md)
a été committé avant le calcul des nouveaux diagnostics, puis intégré avec
l'implémentation par la [PR #882](https://github.com/jfrancoiscollin/jass/pull/882).
Ce résultat porte exclusivement sur les archives déjà consommées.

## Décision et portée

`ED3_TRANSFER_DIAGNOSTIC_COMPLETE_V1`, classification
`EXPLORATORY_CONSUMED_DATA`, `scientific_verdict=null`, `next_stage=STOP_ED3`.
Le terminal de confirmation reste **`ED3_SOFT_CONFIRMATION_NOT_SUPPORTED_V1`**.
Le diagnostic décrit les changements entre les modèles gelés ; il ne constitue
ni une nouvelle confirmation, ni une preuve causale de transfert, ni une mesure
de force en jeu. `CURRICULUM` reste champion.

SOFT change 44 des 512 choix de HARD sur la confirmation consommée : neuf entrent
dans l'ensemble des meilleurs coups de référence et sept en sortent. Les
réductions de regret restent rares et d'amplitudes inégales. Sur la garde WDL
historique consommée, la logloss observée reste moins bonne que BASE et meilleure
que HARD. Ces observations n'établissent pas le gain décisionnel avec calibration
préservée recherché par
la confirmation.

## Exécution et publication

Code exécuté dans les deux modes :
`22ee9cd1c362eec62882b50a8cdda6fbd276054a` ; merge dans `develop` :
`ec4a27ef8a05366da662a9249d1a740207e3b1ae`.
Le commit du gel prospectif est `7016df288e6c3114a7ab1de06df2d31cabba4992`.

- Répétition : `cpx62-1885-l3-ed3-transfer-diagnostic-rehearsal-v1`, tentative
  `20260909T061014Z-22ee9cd1`, exit 0, stage 36,165987 s ;
  [control #583](https://github.com/jfrancoiscollin/jass-control/pull/583).
- Production : `cpx62-1886-l3-ed3-transfer-diagnostic-production-v1`, tentative
  `20260909T062530Z-22ee9cd1`, exit 0, stage 36,430047 s ;
  [control #584](https://github.com/jfrancoiscollin/jass-control/pull/584).
- Reçu de répétition authentifié :
  `8b6017a0997c87677cc453b3ec5862866c07657717808273a97a2a086b16b69e`.
- Reçu de production : `81cf15164533360413f75e99485605defb0784a9d4de5bb409cadc4fe5734b08`.
- Spécification commune :
  `653aabdc00d80139958ae44a181f0c114b036253add466f83ec1087a8e589fb8`.
  Seul `LAUNCH_MODE` diffère ; code, profil et runtime sont identiques.

Les deux tentatives ont passé les 29 régressions enregistrées, sans erreur,
échec ou test ignoré. Les cinq contrats du dispatcher Linux sont passés avant
chaque mise en file. Le contrôle de production a authentifié la répétition
publiée avant son stage. Après chaque publication, la relecture a vérifié
`_SUCCESS`, manifeste externe, inventaire, sommes de contrôle, reçu et sorties.
Les agrégats de paires, choix, marges, regrets et contributions WDL ont été
recalculés depuis les JSONL publiés.

Chaque stage a calculé ses sorties deux fois avec identité des octets. Les
sept fichiers scientifiques immuables de production sont aussi identiques à
ceux de la répétition. SHA256 du manifeste interne commun :
`efc50d726220af5812303c056c54965f404d3eba9d7f26750ffd2060910725f2`.
Répétition et production ne sont pas deux observations scientifiques indépendantes.

## TRAIN — support PARTIAL retenu Q5k/Q50k

512 parents et 4 976 enfants archivés ; 17 622 paires non terminales retenues
sur 477 parents. Les 35 parents sans paire restent dans le dénominateur 512.
La masse totale vaut 477/512 = 0,931640625. Chaque paire du parent p pèse
`1/(512*k_p)` ; les tableaux donnent effectif puis masse complète.

Lignes = état HARD ; colonnes = état SOFT.

| TRAIN | Correct | Ex æquo | Inversé |
|---|---:|---:|---:|
| Correct | 10 456 / 0,537070773 | 103 / 0,007470842 | 211 / 0,019942735 |
| Ex æquo | 79 / 0,004004781 | 52 / 0,002264334 | 89 / 0,004547161 |
| Inversé | 178 / 0,014053590 | 88 / 0,004676922 | 6 366 / 0,337609488 |

Les choix TRAIN sont un diagnostic sur les seuls enfants non terminaux.
Sur 510 parents avec choix défini : 450 choix identiques, cinq changements
entre deux meilleurs coups, sept entrées parmi les meilleurs, 19 sorties,
29 changements entre deux coups hors du meilleur ensemble. Deux parents n'ont
pas de choix défini. Ce calcul ne reconstruit pas une politique de production.

La marge meilleur-contre-reste est définie sur 495 parents ; 17 n'ont pas de
reste. La variation SOFT−HARD a une moyenne de −0,765657, une médiane nulle,
190 valeurs positives, 227 négatives et 78 nulles, dans l'échelle native entière.

## Confirmation consommée — toutes les paires strictes Q200k

Cette population utilise une définition de paires différente de TRAIN.
**Aucune différence entre populations, aucun taux de transfert ni test de leur
écart n'est calculé.** Les modèles et la cohorte 1884 restent exactement gelés.

512 parents, 4 702 enfants et 21 806 paires strictes sur 482 parents ; 30 parents
sans paire. La masse totale est 482/512 = 0,94140625.

| Confirmation | Correct | Ex æquo | Inversé |
|---|---:|---:|---:|
| Correct | 12 171 / 0,508796691 | 130 / 0,005078354 | 262 / 0,015558094 |
| Ex æquo | 119 / 0,006635337 | 50 / 0,001833334 | 121 / 0,004997217 |
| Inversé | 269 / 0,014039741 | 114 / 0,006759986 | 8 570 / 0,377707496 |

Les 11 paires impliquant un terminal proviennent d'un parent : trois restent
correctes, huit restent inversées, masse héritée 0,001953125. Ces états décrivent
les scores bruts des paires ; ils ne modifient pas la politique de priorité
terminale, qui s'applique à six parents dans la population complète. Les 21 795
autres paires sont non terminales, masse 0,939453125. Les deux composantes réconcilient
la matrice primaire sans renormalisation. Aucun type sémantique de score n'est
déduit de sa magnitude.

La règle effective garde la première ligne terminale si elle existe ; sinon
elle maximise le score natif opposé, avec la première ligne en cas d'ex æquo.
Six parents ont cette priorité terminale. La marge brute ne décrit pas leur
règle de choix. Elle est définie sur 482 parents ; sa variation moyenne est
+0,624481, médiane nulle, 208 valeurs positives, 191 négatives et 83 nulles.

| Passage du choix HARD au choix SOFT | Parents / 512 |
|---|---:|
| Même ligne | 468 |
| Ligne différente, deux choix parmi les meilleurs | 4 |
| Hors du meilleur ensemble vers un meilleur coup | 9 |
| Meilleur coup vers un coup hors du meilleur ensemble | 7 |
| Ligne différente, deux choix hors du meilleur ensemble | 24 |

Le meilleur ensemble conserve tous les ex æquo de référence. Les 44 changements
de choix donnent 18 regrets réduits, 20 augmentés et six égaux ; les nombres
globaux de regret égal incluent aussi les 468 choix inchangés.

## Répartition du regret sur les 512 parents consommés

La réduction est `regret_comparateur − regret_SOFT` : positive = amélioration.
L'échelle est celle de la référence publiée Q200k, pas une mesure Elo ni une
perte uniforme interprétable en centipions sur toutes les familles de scores.

| Comparateur | Moyenne | Réduits / augmentés / égaux | Médiane | p05 / p95 | Min / max |
|---|---:|---:|---:|---:|---:|
| BASE | +19,818359 | 43 / 48 / 421 | 0 | −9,9 / +10 | −8 909 / +9 467 |
| HARD | +32,404297 | 18 / 20 / 474 | 0 | 0 / 0 | −331 / +8 298 |

Les deltas sont nuls sur 421/512 parents face à BASE et 474/512 face à HARD ;
les deux médianes sont nulles. Les moyennes positives ne décrivent donc pas une
amélioration sur la majorité des parents. Toutes les cellules originales
de 64 parents sont conservées ci-dessous, sans sélection a posteriori.

| Cellule (n=64) | Réduction BASE−SOFT | Réduction HARD−SOFT | Choix changés BASE / HARD |
|---|---:|---:|---:|
| P0_stm0 | +0,500000 | -0,265625 | 11 / 2 |
| P0_stm1 | -2,218750 | +2,968750 | 12 / 6 |
| P1_stm0 | +11,546875 | +10,015625 | 16 / 6 |
| P1_stm1 | -2,125000 | -3,859375 | 18 / 7 |
| P2_stm0 | -3,781250 | +242,531250 | 14 / 8 |
| P2_stm1 | +154,312500 | -6,203125 | 14 / 5 |
| P3_stm0 | -138,328125 | +0,000000 | 11 / 2 |
| P3_stm1 | +138,640625 | +14,046875 | 9 / 8 |

Les regrets moyens, meilleurs coups et comptages reproduisent exactement 1884.
Les IC95 antérieurs sont authentifiés et recopiés dans le reçu, sans nouveau
bootstrap ni réinterprétation : [résultat de confirmation](L3_ED3_CONFIRMATION_RESULTS_20260909.md).

## Garde WDL — contributions des lignes et ouvertures

Les 8 192 lignes et 2 394 groupes d'ouvertures sont ceux de 1884, dans leur ordre
scellé. Les valeurs positives SOFT−comparateur indiquent une perte plus élevée.

| Perte SOFT−comparateur | Moyenne | Lignes négatives / nulles / positives | Médiane | p05 / p95 |
|---|---:|---:|---:|---:|
| logloss SOFT−BASE | +0,001397132 | 4294 / 208 / 3690 | -0,000120127 | -0,039853 / +0,054424 |
| logloss SOFT−HARD | -0,000739457 | 3369 / 392 / 4431 | +0,000129473 | -0,029102 / +0,024131 |
| brier SOFT−BASE | +0,000412502 | 4294 / 208 / 3690 | -0,000000876 | -0,016431 / +0,020250 |
| brier SOFT−HARD | -0,000254711 | 3366 / 392 / 4434 | +0,000001012 | -0,011589 / +0,009812 |

Pour la logloss SOFT−BASE, les contributions d'ouverture sont positives sur
1 086 groupes, négatives sur 1 297 et nulles sur 11. La contribution de chaque
groupe à la moyenne globale est `somme_des_deltas_du_groupe/8192` ; leur somme
redonne +0,0013971322415515085 à 1e-15 près. Les ouvertures ne sont pas
équipondérées. Une majorité de deltas négatifs ne suffit pas à rendre la perte
moyenne négative : les amplitudes comptent aussi.

Les distributions complètes des lignes, sommes par ouverture, moyennes par
ouverture et contributions additives sont conservées dans le reçu et les tables
publiées. Aucun groupe n'est retiré, aucun seuil ni nouvel intervalle n'est ajusté.
La garde reste historique ; elle ne fournit pas de nouvelles issues de partie.

## Sensibilité à la conversion entière finale

Les logits natifs non arrondis appartiennent aux mêmes modèles déjà quantifiés.
Ils ne permettent pas d'isoler l'effet de la quantification des poids.

Sur TRAIN, ils donnent 250 paires inversées→correctes et 310 correctes→inversées,
ainsi que 54 changements de choix sur 510 parents définis (sept entrées parmi
les meilleurs, 16 sorties). Sur la confirmation consommée, ils donnent
394 paires inversées→correctes et 380 correctes→inversées ; 45 changements
de choix sur 512, avec neuf entrées parmi les meilleurs et sept sorties.
Les scores entiers restent l'analyse principale, et la priorité terminale est
conservée dans la sensibilité de confirmation. Aucun résultat n'est sélectionné
entre les deux représentations.

## Preuves conservées et limites finales

- [Relecture authentifiée 1885](receipts/ed3-transfer-1885-readback.json).
- [Relecture authentifiée 1886 et distributions complètes](receipts/ed3-transfer-1886-readback.json).
- SHA256 du rapport scientifique commun :
  `2e7c66ebba09a12b58567f03a464fc96804f3b1758a664892bd93974a843abf9`.
- SHA256 de la synthèse terminale de production : `f47e2cae383a2337f0868de3dfd38712094c23087cdbc5056d16fbe530b3c0b3`.

Chaque invocation a relu 12 894 cibles déjà consommées et 9 952 cellules TRAIN,
soit 25 788 et 19 904 sur les deux stages, et 68 264 lignes de prédiction native
par stage. Les relectures de publication recalculent à partir des sorties
publiées, sans nouvelles cibles de confirmation.
Aucun fit, moteur, recherche, nouvelle position, partie, bootstrap, ajustement,
promotion ou bake n'a été exécuté. `runtime_authorized=false` et
`automatic_continuation=false`. Le diagnostic ne rouvre pas ED3.
