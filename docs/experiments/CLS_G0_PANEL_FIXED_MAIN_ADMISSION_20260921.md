# CLS panel — admission des deux comparaisons fixes

Date : **21 septembre 2026**. Statut : **FIXED_MAIN_PANEL_COMPLETED**.

L'autorité et la preuve sont fusionnées dans Jass #1059
(`4612a655c9aed252715756dba7c1135146b18912`) ; les deux admissions sont scellées
dans control #783 (`011d0d75bcb1f9cafe6af6a3892adda5b0188210`) après CI verte.
LOCAL 2075 a démarré à **11:08:24 heure de Paris** (09:08:24 UTC) et s'est terminé
techniquement à **11:57:00 heure de Paris** (09:57:00 UTC), tentative
`20260921T090819Z-e00900ff`, code immuable e00900ff, avec sortie 0. Le readback technique
authentifie 576 parties, 59 804 recherches et zéro autre effet ; il ne lit aucun score,
intervalle, verdict ou résultat scientifique. WDL 2076 a été libéré par control #784
(`ea7f6854051211725fbfd68c46ed0ebff6d56fc4`) après CI verte et authentification
de la seule dépendance technique. Il a démarré à **12:04:38 Paris** (10:04:38 UTC),
tentative `20260921T100434Z-e00900ff`, sous le même code immuable. WDL a terminé et publié à **12:53:56 Paris**. Le [résultat conjoint authentifié](CLS_G0_REJECTION_PANEL_V1_RESULTS_20260921.md)
est `G0_PANEL_LARGE_LOSS_DISCORDANCE_REPLICATED_V1` ; cette admission est consommée.

Le mandat utilisateur répété autorise la poursuite autonome des évaluations préenregistrées.
La dernière instruction est : « oh punaise oui j'autorise allez enchaine c'est pénible arrête de me demander ».
L'admission explicite séparée requise par le panel est une condition du contrôle de lancement,
remplie par les enregistrements ci-dessous sous cette autorisation acquise. Elle ne constitue
pas une nouvelle demande de consentement. La règle propre à la readiness et son terminal
`CLS_G0_PANEL_READINESS_V2_COMPLETE_MAIN_NOT_AUTHORIZED` restent conservés tels quels.

## Preuve préalable et identités

La [readiness 2074](../operations/CLS_PANEL_READINESS_2074_RESULTS_20260921.md) est publiée,
authentifiée et relue : 56 parties, 5 635 recherches, 49 tests de lancement réussis, zéro
autre effet. Son code immuable `e00900ff38e71afa88201871713d4765409c2ac4` contient déjà
les trois branches du panel. Aucun nouveau code ni nouvelle répétition n'est nécessaire.

Les deux admissions sont scellées **avant LOCAL** dans le même répertoire de contrôle
`specs/cls-readiness-v2-2074`, à côté du plan existant, sans le réécrire :

| Identité | Valeur |
|---|---|
| Plan commun | `ce341746adaf142a36c80db2b83cc3e2086515e6ef9db3313c8455a053b0dcee` |
| Activation conjointe | `d3837694b871e363d1c2d68d28b06d525c6b6d8638e5a539988a8bbfb02ea519` |
| LOCAL | `cpx62-2075-l3-cls-g0-panel-local-main-v1` |
| Admission LOCAL | `b3c7757517d02fc8bf44ad7e18d4412f3450d2c920578ea3b079afdc73971279` |
| WDL | `cpx62-2076-l3-cls-g0-panel-wdl-main-v1` |
| Admission WDL | `1ab61d3b609adcf601630b8b9e4f969c6a6c82140b23f1b394809591e143dbcf` |
| Scellement des ouvertures | `b5a728c580ddb481663c0d6a336b45c4cf1c36f89d4fce368818d5a9a5a24aaf` |

Chaque admission lie le tuple complet de readiness : job 2074, tentative
`20260921T083944Z-e00900ff`, reçu `19c33657d2946e4f6d1aa85cdc08ba477bb0db2486bff627c608919a9b459c8b`,
manifeste du publisher `d4726bd7415d9e8cfd2589a6132085e23053be5ca51207efa05fdbb1318326ac`
et ouverture scellée ci-dessus. WDL pré-lie le job LOCAL et l'empreinte de son admission.

## Exécution et barrière de lecture

LOCAL / CURRICULUM puis WDL / CURRICULUM : **576 parties chacun**, mêmes 288 paires
d'ouvertures, couleurs inversées, quatre travailleurs, un thread par joueur, cadence
100/120 ms. Le code, profil, modèles, seeds, exclusions, alpha, seuils et verdicts du
[panel gelé](CLS_G0_REJECTION_PANEL_V1_20260920.md) sont inchangés.

Seul LOCAL entre d'abord en attente. Le dispatch WDL est déjà scellé hors de la file active.
Après publication LOCAL, la continuation consulte seulement son authenticité, sa complétude
technique et ses compteurs. Aucun score, intervalle ou verdict LOCAL n'est lu pour décider
de WDL. Le gate WDL authentifie lui-même la dépendance pré-liée ; l'inférence est conjointe
après les deux cellules valides. Un échec technique consomme son admission, sans retry implicite.

## Dimensionnement et cumul

CPX62 a 16 CPU ; la readiness mesure 230,439672 s pour le bloc chronométré. La formule gelée
projette **2 793,111 s LOCAL** et **2 780,973 s WDL**, sous le plafond de projection de 3 000 s.
Estimation annoncée : **50–55 minutes par comparaison**, préparation et publication incluses,
ancrée aussi sur les 513 s réelles entre démarrage et terminal de readiness. Le volume fixe
est conservé ; aucune extension n'est ajoutée. Les plafonds restent 3 600 s de stage et
4 200 s extérieures chacun, 60 s par partie et 180 s par paire.

Le nouveau ledger additionne les charges conservées de 2070/2071, les mesures authentifiées
2072/2073/2074 et les deux réservations principales complètes : **8 398,229175 / 9 900 s**
de stage, **10 411 / 12 300 s** extérieures. Les anciennes réservations expirées sont remplacées
par les mesures réelles ; le travail consommé n'est jamais effacé. Plafonds globaux inchangés :
1 208 parties et 195 696 recherches. Aucun entraînement, nouvelle sonde G0, Scan, promotion,
bake, substitution de CURRICULUM ou scale-up.

À la libération WDL, la mesure réelle LOCAL remplace sa réservation :
**7 573,212516 / 9 900 s** de stage et **9 127 / 12 300 s** extérieures, réservation
WDL complète incluse. Déjà consommés : 632 parties et 65 439 recherches ; maximum
avec WDL : 1 208 parties et 158 751 recherches, sous le plafond gelé de 195 696.
Le dispatch WDL est une copie exacte de celui scellé avant LOCAL, SHA256
`46446d83f5fc932e097cbfe244914da96347861252a3fe5d1c0ebb1a63348344`.
Les sept tests du dispatcher Linux, la syntaxe et la vérification réelle de sa dépendance
pré-liée ont réussi, sans stage ni partie supplémentaires. Le nouveau contrôle CPX
confirme 16 CPU et 572 520 MiB libres ; estimation WDL inchangée de 50–55 minutes.

Les validations préalables requises sont la CI publique, les sept tests du dispatcher sur
Linux CPX, la projection exacte des deux spécifications, le contrôle de tout l'historique
et la relecture réelle de la même publication de readiness. La réussite technique de 2074
ne prouve aucun gain d'évaluation. Le terminal conjoint reste à établir.
