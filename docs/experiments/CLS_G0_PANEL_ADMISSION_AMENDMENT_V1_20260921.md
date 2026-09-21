# CLS panel â€” amendement d'admission V1

Date : **21 septembre 2026**. Statut : **IMPLEMENTED_VALIDATION_PENDING**.
Compagnon : `CLS_G0_PANEL_ADMISSION_AMENDMENT_V1_20260921.json`.

## DÃ©cision approuvÃ©e

Introduire une admission propre au panel, versionnÃ©e et distincte de Launch V2,
qui authentifie un plan commun contenant **les trois Ã©tapes et leurs plafonds
exacts**. Un sÃ©lecteur explicite choisit une Ã©tape dÃ©jÃ  dÃ©finie dans ce plan.
Cette version approuvÃ©e prime uniquement sur la rÃ¨gle d'identitÃ©
de spÃ©cification/dÃ©lai de Launch V2 pour ce panel. Le prÃ©enregistrement du
20 septembre restera intact comme historique gelÃ© ; ses autres exigences et
le comportement de toutes les admissions V2 existantes resteront applicables.

Le Â« Ok go Â» du 21 septembre autorise la prÃ©paration et la validation des
56 parties de readiness. AprÃ¨s prÃ©sentation du conflit et de la PR #1056,
JFC a explicitement approuvÃ© cet amendement par **Â« Je valide Â»**, le mÃªme jour.
Cette approbation permet son implÃ©mentation et la readiness dÃ©jÃ  demandÃ©e, une
fois ses vÃ©rifications achevÃ©es. **Aucune de ces parties n'a encore Ã©tÃ© lancÃ©e.**
Elle porte sur la rÃ¨gle d'admission ; les modÃ¨les, parties et analyses restent
gelÃ©s. Les matchs principaux gardent leur admission explicite sÃ©parÃ©e.

## Conflit dÃ©montrÃ© avant consommation du budget

[Launch V2](../operations/LAUNCH_ADMISSION_V2_20260908.md) exige la mÃªme commande,
le mÃªme profil et la mÃªme spÃ©cification normalisÃ©e entre rÃ©pÃ©tition et
production. `common_spec` dans `jobs/tools/launch_gate_v2.py` retire uniquement
`LAUNCH_MODE` ; les dÃ©lais restent dans l'empreinte. Le dispatcher vÃ©rifie le
dÃ©lai de cette spÃ©cification augmentÃ© de 600 secondes. Un reÃ§u ne couvre pas
une autre commande, un autre profil ou une autre spÃ©cification.

Le [panel gelÃ©](CLS_G0_REJECTION_PANEL_V1_20260920.md), sections 6 et 8, exige
une rÃ©pÃ©tition rÃ©elle de 56 parties, puis deux comparaisons sÃ©parÃ©es, avec :

| Ã‰tape | Parties | Recherches joueurs max | Stage / dispatcher |
|---|---:|---:|---:|
| Readiness | 56 | 9 072 | 1 800 / 2 400 s |
| LOCAL / CURRICULUM | 576 | 93 312 | 3 600 / 4 200 s |
| WDL / CURRICULUM | 576 | 93 312 | 3 600 / 4 200 s |

Ces spÃ©cifications ont nÃ©cessairement des empreintes V2 diffÃ©rentes. Une
rÃ©pÃ©tition autonome ne pourra donc pas autoriser les deux spÃ©cifications de
match. Augmenter son dÃ©lai extÃ©rieur pour partager une spÃ©cification relÃ¢cherait
son plafond ; refaire des rÃ©pÃ©titions consommerait des parties supplÃ©mentaires.
Choisir implicitement un bras selon le nom du job contournerait l'identitÃ©
normalisÃ©e. Aucune de ces solutions n'est adoptÃ©e.

L'audit 2072 reste terminÃ© et authentifiÃ© ; ses reÃ§us ne sont ni invalidÃ©s ni
rÃ©interprÃ©tÃ©s. Il ne fournit pas une rÃ©pÃ©tition de matchs.

## Contrat technique approuvÃ©

1. Avant readiness, sceller un plan commun complet : SHA du code, commande,
   profil, identitÃ© native, modÃ¨les, toutes les sources, recette d'ouvertures,
   ressources, sorties, suites de rÃ©gression et dÃ©finition exacte des trois
   Ã©tapes. Le plan fixe le schÃ©ma et la sÃ©rialisation canonique, l'implÃ©mentation
   du gate, les rÃ¨gles d'authentification, l'identitÃ© du runtime et les plafonds
   d'effets tentÃ©s par phase et cumulÃ©s. Il contient trois templates fermÃ©s de
   spÃ©cification, dont les dÃ©lais et effets maximaux ci-dessus. Tout changement
   du plan change son empreinte ; aucun champ libre de budget n'est Ã©liminÃ© du
   contrÃ´le.
2. Le sÃ©lecteur explicite `PANEL_PHASE` vaut exclusivement `readiness`, `local`
   ou `wdl`. Sa valeur est incluse dans le template de chaque rÃ´le et n'est
   jamais effacÃ©e de l'empreinte. La spÃ©cification concrÃ¨te doit Ãªtre exactement
   la projection de ce rÃ´le dans le plan scellÃ©. Le rÃ´le dÃ©termine le mode
   rÃ©pÃ©tition/production ; aucun autre choix de modÃ¨le, paramÃ¨tre ou budget
   n'est admis.
3. Pendant readiness, gÃ©nÃ©rer deux fois le pool, authentifier toutes les
   exclusions et sceller les 288 + 8 ouvertures **avant la premiÃ¨re partie**.
   Le plan prÃ©alable fixe la recette et un unique emplacement de dÃ©pendance
   typÃ© `authenticated_readiness` dans chaque template principal. Le gate le
   rÃ©sout uniquement depuis la publication authentifiÃ©e : job, tentative,
   reÃ§u de lancement, manifeste du publisher et empreinte de l'ouverture
   scellÃ©e. Il enregistre l'empreinte de chaque spÃ©cification matÃ©rialisÃ©e et
   prouve qu'aucun autre champ n'a changÃ©. On ne prÃ©tend pas connaÃ®tre cette
   sortie avant son calcul et on ne la rÃ©gÃ©nÃ¨re pas en production. La readiness
   Ã©crit le scellement une seule fois et checkpoint son empreinte avant tout
   effet de partie ; un Ã©chec ou une tentative partielle bloque la version.
4. ExÃ©cuter exactement les 8 contrÃ´les CURRICULUM/CURRICULUM Ã  profondeur 3 et
   les 48 auto-matchs chronomÃ©trÃ©s CURRICULUM, LOCAL et WDL. Relever les durÃ©es
   des paires, dÃ©marrages inclus, et la durÃ©e indÃ©pendante du bloc parallÃ¨le.
   Conserver la formule `F=max(1,4*T_bloc/somme(durees_paires))`, le plafond de
   projection de 3 000 secondes par comparaison et le contrÃ´le d'absence de
   dÃ©part principal dans les trajectoires de readiness.
5. N'Ã©mettre une preuve rÃ©utilisable qu'aprÃ¨s publication rÃ©ussie et relecture
   R2 des reÃ§us, sorties, identitÃ©s, rÃ©gressions, compteurs et empreintes. Avant
   LOCAL, les deux admissions principales doivent Ãªtre scellÃ©es contre le mÃªme
   plan, le mÃªme tuple job/tentative/reÃ§u/manifeste de readiness et les mÃªmes
   ouvertures. Les sorties rÃ©pÃ¨tent ces identitÃ©s. Toutes les branches de
   production et leurs tests doivent dÃ©jÃ  exister dans le SHA de readiness.
   ExÃ©cuter ensuite ce SHA immuable, mÃªme si de la documentation est fusionnÃ©e
   ailleurs ; tout changement de code/profil demanderait une nouvelle
   rÃ©pÃ©tition, interdite par le budget de 56 parties et l'absence de retry.
6. ExÃ©cuter LOCAL puis WDL dans des Ã©tapes sÃ©parÃ©es, chacune avec son plafond
   extÃ©rieur propre. L'admission WDL lie Ã  l'avance l'identitÃ© du job LOCAL et
   l'empreinte de son admission, ainsi que le code, le plan et le rÃ´le attendus.
   Sa rÃ¨gle de dÃ©pendance rÃ©sout ensuite l'unique tentative autorisÃ©e publiÃ©e
   et ne consulte que sa complÃ©tude technique et ses compteurs, jamais le score,
   l'intervalle ou le verdict. Aucun rÃ©sultat infÃ©rentiel
   intermÃ©diaire ne choisit, ne remplace ou ne modifie WDL ; la lecture
   infÃ©rentielle reste conjointe aprÃ¨s les deux cellules valides.
7. Refuser tout reÃ§u V2 ordinaire comme Ã©quivalent implicite de cette nouvelle
   preuve. La future implÃ©mentation utilisera une version explicitement
   enregistrÃ©e de l'admission et du dispatcher canonique, sans affaiblir V2 ni
   lui fabriquer des reÃ§us rÃ©troactifs.

## Invariants et validation avant activation

Restent inchangÃ©s : modÃ¨les et source native, seeds et exclusions, 56 + 576 +
576 parties, couleurs, cadence 100/120 ms, quatre travailleurs, contrÃ´les de
censure, alpha, seuils, verdicts, enveloppe totale 9 900/12 300 secondes incluant
l'audit, zÃ©ro retry automatique, zÃ©ro entraÃ®nement, aucune promotion et
CURRICULUM champion. Les plafonds par partie (60 s) et paire (180 s), le comptage
du travail tentÃ© et les garde-fous de publication restent obligatoires.

Avant tout lancement : approbation de cet amendement, implÃ©mentation complÃ¨te
des trois branches sous le mÃªme code/profil, tests synthÃ©tiques du pipeline et
du transport, refus des dÃ©rives de chaque champ/phase/budget, limites extÃ©rieures
distinctes effectivement appliquÃ©es, CI du SHA exact, dimensionnement et
admission canonique de la readiness. Aucun reÃ§u synthÃ©tique ne vaut publication
rÃ©elle et aucun contrÃ´leur absent n'est prÃ©sentÃ© comme dÃ©jÃ  implÃ©mentÃ©.

L'implÃ©mentation du gate, du stage et des trois branches est en cours dans la
PR #1056. L'approbation ne vaut pas reÃ§u d'exÃ©cution ni dispense des vÃ©rifications
ci-dessus. Aucun match principal n'est autorisÃ© par cette approbation.
