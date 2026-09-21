# CLS — résultat conjoint du panel G0 V1

Date : **21 septembre 2026**. Terminal : **`G0_PANEL_LARGE_LOSS_DISCORDANCE_REPLICATED_V1`**.
Décision gelée : **`STOP_INTERPRET_NO_AUTO_G0_V2_NO_PROMOTION`**.

Les deux comparaisons préenregistrées sont complètes, publiées, authentifiées et recalculées
depuis leurs paires brutes. **LOCAL et WDL excluent chacun la perte majeure de 100 Elo
logistiques visée à cette cadence**, alors que G0 V1 les avait rejetés. Ce résultat ne démontre
la supériorité d'aucun des deux modèles. Les deux intervalles contiennent 0,5 ; aucun candidat
n'est promu, aucun rejet G0 historique n'est transformé en PASS et CURRICULUM reste champion.

## Protocole et résultat

Le [protocole gelé](CLS_G0_REJECTION_PANEL_V1_20260920.md) compare deux cas déjà rejetés,
sélectionnés ensemble avant leurs nouveaux scores. Chaque contraste comporte **288 paires
d'ouvertures avec couleurs inversées, soit 576 parties**, contre le même CURRICULUM.
Les deux contrastes utilisent les mêmes 288 ouvertures fraîches au sens des exclusions
déclarées, quatre travailleurs, un thread par joueur, cadence nominale 100 ms et plafond
de réponse 120 ms. Aucune nouvelle preuve de disjonction avec tout l'entraînement n'est revendiquée.

| Mesure | LOCAL / CURRICULUM | WDL / CURRICULUM |
|---|---:|---:|
| Paires / parties | 288 / 576 | 288 / 576 |
| Parties censurées à 160 demi-coups | 7 | 9 |
| Bornes moyennes des scores de paire | [0,5017361111 ; 0,5138888889] | [0,4913194444 ; 0,5069444444] |
| Intervalle préenregistré | **[0,4145140661 ; 0,6011109339]** | **[0,4040973995 ; 0,5941664894]** |
| Verdict de contraste | `SUBSTANTIAL_LOSS_EXCLUDED` | `SUBSTANTIAL_LOSS_EXCLUDED` |
| Score descriptif avec demi-point aux plafonds | 50,78125 % | 49,91319 % |
| Recherches joueurs récomptées | 59 804 | 60 686 |

Les parties administrativement censurées contribuent **[0,1]**, jamais une nulle certaine,
aux bornes inférentielles. Le score descriptif de la dernière convention ne remplace pas ces
bornes. Le rayon Hoeffding gelé vaut `0.08722204497512172`, avec alpha 0,025 par contraste
et budget familial 0,05. Les bornes inférieures dépassent toutes deux la frontière gelée
`0.35993500019711494` correspondant à −100 Elo logistiques.

La couverture conjointe d'au moins 95 % est conditionnelle au modèle d'échantillonnage
déclaré pour les unités ouverture-paire indépendantes. Bonferroni n'exige pas l'indépendance
des deux contrastes partageant les départs. Ni la seed fixée ni la seule absence de doublons
ne prouvent une indépendance générale ; la population choisie et l'ordonnancement sur une
machine partagée limitent l'extrapolation. Les données historiques HIER 2069 n'entrent pas
dans ce nouvel effectif, cet intervalle ou son alpha.

## Exécution et barrière d'information

| Phase | Job / tentative | Départ → publication (UTC) | Stage / total |
|---|---|---|---:|
| LOCAL | `cpx62-2075-l3-cls-g0-panel-local-main-v1` / `20260921T090819Z-e00900ff` | 09:08:24 → 09:57:00 | 2 774,983341 / 2 916 s |
| WDL | `cpx62-2076-l3-cls-g0-panel-wdl-main-v1` / `20260921T100434Z-e00900ff` | 10:04:38 → 10:53:56 | 2 780,892512 / 2 958 s |

Les deux sorties sont normales, sans timeout. Les **49 régressions de lancement** passent
dans chaque invocation, sans erreur ni skip. Aucun fit, Scan, self-play d'entraînement,
lecture de cible de test, promotion ou bake n'a eu lieu.

Les deux admissions ont été scellées avant LOCAL dans control #783. La libération de WDL
(control #784) a copié exactement son dispatch pré-lié après la seule authentification
technique LOCAL : aucun score, intervalle ou verdict LOCAL n'a déterminé la continuation.
La relecture conjointe indépendante a ouvert les résultats à **10:55:45 UTC**, après
authentification des deux publications complètes. Elle n'a ajouté aucune partie ni recherche.

Code immuable : `e00900ff38e71afa88201871713d4765409c2ac4`.
Plan : `ce341746adaf142a36c80db2b83cc3e2086515e6ef9db3313c8455a053b0dcee`.
Activation : `d3837694b871e363d1c2d68d28b06d525c6b6d8638e5a539988a8bbfb02ea519`.
Ouvertures scellées : `b5a728c580ddb481663c0d6a336b45c4cf1c36f89d4fce368818d5a9a5a24aaf`.
Les modèles, le binaire, les paramètres et les identités de runtime sont identiques à ceux
de la readiness 2074 ; toutes leurs empreintes figurent dans le reçu ci-dessous.

## Preuve et coût réellement consommé

La [relecture publique compacte](../operations/CLS_PANEL_JOINT_2075_2076_READBACK_20260921.json)
conserve les deux manifestes, toutes les empreintes sélectionnées, les reçus, la barrière
de lecture et les résultats exacts. Son reçu source complet, recopié et rehashé indépendamment,
a pour SHA256 `556744fe2857c5f9af9ff593d8c7ee57d579b0a28b3f7ab88a36d25f73344d66`.
Ce SHA désigne le reçu source, pas la sérialisation compacte publique.

Les identités des 288 paires, couleurs, ouvertures, correspondances de trajectoires,
télémétrie, compteurs de recherches et règles de censure ont été vérifiées. Une implémentation
d'intervalle distincte donne les mêmes bornes et verdicts que les rapports publiés. Les
rapports de contraste recomputés reproduisent exactement le rapport et le résumé conjoints.
La relecture n'est pas présentée comme un nouveau rejeu natif de légalité de ces parties :
le rejeu natif complet requis sur l'historique 2069 avait été effectué dans l'audit 2072.

En conservant les charges des tentatives antérieures, le panel consomme **6 754,105028 s
de stage sur 9 900**, **7 885 s extérieures sur 12 300**, **1 208 parties sur 1 208** et
**126 125 recherches sur 195 696**. Les réservations ont été remplacées par les mesures
authentifiées sans effacer de travail consommé. Aucune troisième cellule ni prolongation
n'est admise. TI-088 est clos sur la preuve réelle du plan commun et de ses trois
phases aux plafonds distincts ; cette clôture technique ne vaut pas réussite d'un candidat.

## Portée et décision suivante

Le décalage observé concerne la marge de 100 Elo, cette cadence et ces deux cas apparentés.
Il ne mesure ni sensibilité/spécificité générale de G0 ni un petit gain de force, et ne rend
pas une éventuelle perte plus petite acceptable. HIER demeure un contexte historique,
sans méta-analyse confirmatoire à trois candidats. Les cohortes de ce panel sont consommées.

Le panel est clos avec sa décision gelée. La revue scientifique recommande une seule
suite distincte : la [proposition prospective G0 V2 à trois états](CLS_G0_V2_THREE_STATE_VALIDATION_PROPOSAL_V1_20260921.md).
Elle conserve les seuils numériques et propose une abstention lorsqu'une recherche valide
ne fournit pas le reçu Exact requis par G0-C. Cette abstention exigerait une adjudication
de force séparément préenregistrée ; elle ne vaudrait jamais PASS à elle seule.
La préparation immédiate vérifie uniquement les métadonnées de cas et de cohortes
indépendants. Les cas du panel servent à concevoir la proposition et sont exclus de sa
validation. Aucun seuil G0 V1 ne change et aucune G0 V2 n'est activée par ce résultat.
