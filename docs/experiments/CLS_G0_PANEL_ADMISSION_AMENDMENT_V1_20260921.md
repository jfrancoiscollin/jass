# CLS panel — amendement d'admission V1

Date : **21 septembre 2026**. Statut : **IMPLEMENTED_READINESS_2073_FAILED_NO_RETRY**.
Compagnon : `CLS_G0_PANEL_ADMISSION_AMENDMENT_V1_20260921.json`.

## Décision approuvée

Introduire une admission propre au panel, versionnée et distincte de Launch V2,
qui authentifie un plan commun contenant **les trois étapes et leurs plafonds
exacts**. Un sélecteur explicite choisit une étape déjà définie dans ce plan.
Cette version approuvée prime uniquement sur la règle d'identité
de spécification/délai de Launch V2 pour ce panel. Le préenregistrement du
20 septembre restera intact comme historique gelé ; ses autres exigences et
le comportement de toutes les admissions V2 existantes resteront applicables.

Le « Ok go » du 21 septembre autorise la préparation et la validation des
56 parties de readiness. Après présentation du conflit et de la PR #1056,
JFC a explicitement approuvé cet amendement par **« Je valide »**, le même jour.
Cette approbation permet son implémentation et la readiness déjà demandée, une
fois ses vérifications achevées. La tentative unique 2073 a échoué avant le stage,
dans un test de transport synthétique : **zéro partie et zéro recherche natives**.
Sa publication d'échec est authentifiée ; aucune preuve de readiness n'existe.
Elle porte sur la règle d'admission ; les modèles, parties et analyses restent
gelés. Les matchs principaux gardent leur admission explicite séparée.

## Conflit démontré avant consommation du budget

[Launch V2](../operations/LAUNCH_ADMISSION_V2_20260908.md) exige la même commande,
le même profil et la même spécification normalisée entre répétition et
production. `common_spec` dans `jobs/tools/launch_gate_v2.py` retire uniquement
`LAUNCH_MODE` ; les délais restent dans l'empreinte. Le dispatcher vérifie le
délai de cette spécification augmenté de 600 secondes. Un reçu ne couvre pas
une autre commande, un autre profil ou une autre spécification.

Le [panel gelé](CLS_G0_REJECTION_PANEL_V1_20260920.md), sections 6 et 8, exige
une répétition réelle de 56 parties, puis deux comparaisons séparées, avec :

| Étape | Parties | Recherches joueurs max | Stage / dispatcher |
|---|---:|---:|---:|
| Readiness | 56 | 9 072 | 1 800 / 2 400 s |
| LOCAL / CURRICULUM | 576 | 93 312 | 3 600 / 4 200 s |
| WDL / CURRICULUM | 576 | 93 312 | 3 600 / 4 200 s |

Ces spécifications ont nécessairement des empreintes V2 différentes. Une
répétition autonome ne pourra donc pas autoriser les deux spécifications de
match. Augmenter son délai extérieur pour partager une spécification relâcherait
son plafond ; refaire des répétitions consommerait des parties supplémentaires.
Choisir implicitement un bras selon le nom du job contournerait l'identité
normalisée. Aucune de ces solutions n'est adoptée.

L'audit 2072 reste terminé et authentifié ; ses reçus ne sont ni invalidés ni
réinterprétés. Il ne fournit pas une répétition de matchs.

## Contrat technique approuvé

1. Avant readiness, sceller un plan commun complet : SHA du code, commande,
   profil, identité native, modèles, toutes les sources, recette d'ouvertures,
   ressources, sorties, suites de régression et définition exacte des trois
   étapes. Le plan fixe le schéma et la sérialisation canonique, l'implémentation
   du gate, les règles d'authentification, l'identité du runtime et les plafonds
   d'effets tentés par phase et cumulés. Il contient trois templates fermés de
   spécification, dont les délais et effets maximaux ci-dessus. Tout changement
   du plan change son empreinte ; aucun champ libre de budget n'est éliminé du
   contrôle.
2. Le sélecteur explicite `PANEL_PHASE` vaut exclusivement `readiness`, `local`
   ou `wdl`. Sa valeur est incluse dans le template de chaque rôle et n'est
   jamais effacée de l'empreinte. La spécification concrète doit être exactement
   la projection de ce rôle dans le plan scellé. Le rôle détermine le mode
   répétition/production ; aucun autre choix de modèle, paramètre ou budget
   n'est admis.
3. Pendant readiness, générer deux fois le pool, authentifier toutes les
   exclusions et sceller les 288 + 8 ouvertures **avant la première partie**.
   Le plan préalable fixe la recette et un unique emplacement de dépendance
   typé `authenticated_readiness` dans chaque template principal. Le gate le
   résout uniquement depuis la publication authentifiée : job, tentative,
   reçu de lancement, manifeste du publisher et empreinte de l'ouverture
   scellée. Il enregistre l'empreinte de chaque spécification matérialisée et
   prouve qu'aucun autre champ n'a changé. On ne prétend pas connaître cette
   sortie avant son calcul et on ne la régénère pas en production. La readiness
   écrit le scellement une seule fois et checkpoint son empreinte avant tout
   effet de partie ; un échec ou une tentative partielle bloque la version.
4. Exécuter exactement les 8 contrôles CURRICULUM/CURRICULUM à profondeur 3 et
   les 48 auto-matchs chronométrés CURRICULUM, LOCAL et WDL. Relever les durées
   des paires, démarrages inclus, et la durée indépendante du bloc parallèle.
   Conserver la formule `F=max(1,4*T_bloc/somme(durees_paires))`, le plafond de
   projection de 3 000 secondes par comparaison et le contrôle d'absence de
   départ principal dans les trajectoires de readiness.
5. N'émettre une preuve réutilisable qu'après publication réussie et relecture
   R2 des reçus, sorties, identités, régressions, compteurs et empreintes. Avant
   LOCAL, les deux admissions principales doivent être scellées contre le même
   plan, le même tuple job/tentative/reçu/manifeste de readiness et les mêmes
   ouvertures. Les sorties répètent ces identités. Toutes les branches de
   production et leurs tests doivent déjà exister dans le SHA de readiness.
   Exécuter ensuite ce SHA immuable, même si de la documentation est fusionnée
   ailleurs ; tout changement de code/profil demanderait une nouvelle
   répétition, interdite par le budget de 56 parties et l'absence de retry.
6. Exécuter LOCAL puis WDL dans des étapes séparées, chacune avec son plafond
   extérieur propre. L'admission WDL lie à l'avance l'identité du job LOCAL et
   l'empreinte de son admission, ainsi que le code, le plan et le rôle attendus.
   Sa règle de dépendance résout ensuite l'unique tentative autorisée publiée
   et ne consulte que sa complétude technique et ses compteurs, jamais le score,
   l'intervalle ou le verdict. Aucun résultat inférentiel
   intermédiaire ne choisit, ne remplace ou ne modifie WDL ; la lecture
   inférentielle reste conjointe après les deux cellules valides.
7. Refuser tout reçu V2 ordinaire comme équivalent implicite de cette nouvelle
   preuve. La future implémentation utilisera une version explicitement
   enregistrée de l'admission et du dispatcher canonique, sans affaiblir V2 ni
   lui fabriquer des reçus rétroactifs.

## Invariants et validation avant activation

Restent inchangés : modèles et source native, seeds et exclusions, 56 + 576 +
576 parties, couleurs, cadence 100/120 ms, quatre travailleurs, contrôles de
censure, alpha, seuils, verdicts, enveloppe totale 9 900/12 300 secondes incluant
l'audit, zéro retry automatique, zéro entraînement, aucune promotion et
CURRICULUM champion. Les plafonds par partie (60 s) et paire (180 s), le comptage
du travail tenté et les garde-fous de publication restent obligatoires.

Avant tout lancement : approbation de cet amendement, implémentation complète
des trois branches sous le même code/profil, tests synthétiques du pipeline et
du transport, refus des dérives de chaque champ/phase/budget, limites extérieures
distinctes effectivement appliquées, CI du SHA exact, dimensionnement et
admission canonique de la readiness. Aucun reçu synthétique ne vaut publication
réelle et aucun contrôleur absent n'est présenté comme déjà implémenté.

L'implémentation du gate, du stage et des trois branches a été fusionnée dans
la PR #1056 ; le dispatcher et l'admission unique dans les PR control #780/#781.
Le [résultat 2073](../operations/CLS_PANEL_READINESS_2073_RESULTS_20260921.md)
consigne l'échec technique et sa correction de test. L'autorisation unique a
été exercée ; aucune relance automatique ni aucun match principal n'est admis.
Les conditions scientifiques et les plafonds ci-dessus restent inchangés.
