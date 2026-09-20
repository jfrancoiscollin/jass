# CLS — validation bornée des rejets G0 : panel V1

Date : **20 septembre 2026**. Statut : **PREREGISTRATION_ONLY_NO_EXECUTION**.
Base documentaire : `2d20e39b58694c2702336c29c79c04f4c58d1eff`.
Contrat machine compagnon : `CLS_G0_REJECTION_PANEL_V1_20260920.json`.

## 1. Mandat et portée exacte

JFC a approuvé la préparation d'une PR de validation prospective de G0, avec
panel limité, budget et critères de sortie, après la clôture du 2069. Cette PR
livre ce protocole et ses tests de contrat. **Elle ne fournit aucun lanceur,
aucun profil Launch-V2 et ne met aucun job en file.** La fusion ne constitue
pas à elle seule une admission de calcul distant.

Ce protocole est un **nouvel essai sur deux cas sélectionnés**, pas une étape
qui aurait déjà été définie par le plan maître CLS. Il fige les choix ci-dessous
avant toute nouvelle partie comparative. Les paramètres historiques ne sont
ni réécrits, ni corrigés pour faire passer un candidat.

Question : sur deux autres modèles déjà rejetés par G0 V1, ce rejet correspond-il
à une perte d'au moins **100 Elo logistiques** à la cadence définie ? Il ne s'agit
ni d'un test de petit gain, ni d'une mesure générale de sensibilité/spécificité,
ni d'une validation de G0 V2. Deux cas issus du même fit sont apparentés : ils
ne constituent pas deux tirages représentatifs de l'ensemble des moteurs.

## 2. Faits acquis, séparés des choix nouveaux

Sources primaires du dépôt, connues avant ce protocole :

- Le [plan CLS](L3_CLOSED_LOOP_STRENGTH_CAMPAIGN_V1_20260910.md) demande une preuve
  de force à temps fixé avant toute adoption.
- Le [contrat G0 V1](L3_CLS_G0_RUNTIME_CATASTROPHE_CONTRACT_V1_20260916.md), blob
  `8e02bbf1d6ec83abec84ab0ae8c3e9ea38038eb7`, contient quatre filtres conjoints,
  dont les reçus exacts de profondeur obligatoires et l'accord au parent profond.
- Le [contrat HIER](L3_CLS_HIER_L2_NEXT_CANDIDATE_V1_20260918.md) rappelle les
  rejets LOCAL/WDL et interdit leur continuation ordinaire ou leur retuning.
- Le [match 2069](https://github.com/jfrancoiscollin/jass-control/blob/4a5b2e7379f5a0072b9d3c44558286992238a664/status/cpx62-2069-l3-cls-g0-strength-main-production-v1.json)
  a terminé 288 paires/576 parties, 10 censures, avec
  `SUBSTANTIAL_LOSS_EXCLUDED`. Son intervalle publié est
  `[0.41389671183445104, 0.5913116214988823]`. Il n'établit pas la supériorité.
- Le rapport de clôture #1049 distingue la cohérence du résumé GitOps d'une
  relecture indépendante des trajectoires R2 : cette dernière reste à effectuer.

**Choix nouveaux de cette PR :** panel LOCAL/WDL, nouvelles exclusions et seeds,
contrôle, budget, multiplicité et règles de sortie. Ces choix ne sont pas
présentés comme des résultats acquis ou comme une exigence ancienne de CLS.

## 3. Panel fermé et exception d'étude

| Rôle | Comparaison | Usage |
|---|---|---|
| Contrôle de dispositif | CURRICULUM / CURRICULUM | Symétrie déterministe ; aucune inférence de force |
| Cas prospectif 1 | LOCAL / CURRICULUM | 288 paires, résultat principal séparé |
| Cas prospectif 2 | WDL / CURRICULUM | 288 paires, résultat principal séparé |
| Contexte historique | HIER / CURRICULUM, 2069 | Audit et interprétation seulement ; aucune nouvelle partie HIER |

LOCAL et WDL sont **les deux bras techniquement valides scellés par 2041**,
retenus ensemble, sans classement d'après un nouveau score. MIXED est exclu :
il n'existe pas ici comme candidat techniquement valide. Aucun autre modèle,
réglage, dosage ou substitution n'est admis dans ce panel.

Empreintes des modèles bruts décompressés :

```text
CURRICULUM 319d174f4b548b1655aad4bb30d4c6dc86c08dd715c9c23f8b19ba1937dc0be1
LOCAL      197998003db3d221d38e81577cfa381e8227d67705efc1c86b87205ddebbe450
WDL        eabe71068dbc6aeb519a61c730d18586e75c8b72308ecd340de08fe2e18deed6
HIER       95bed3ac9fac4368809609fb1a981ee863401a30ca623fb7bfa3caf7eaddf628
```

Une **exception limitée aux matchs de cette étude** est proposée pour LOCAL et
WDL, qui restent interdits de continuation ordinaire sous G0 V1. Elle ne devient
exécutable qu'après implémentation revue, autorisation de lancement et admission
Launch-V2 de cette étude précise. Elle ne transforme aucun FAIL en PASS, ne
rouvre pas CLS-S/E pour promotion et ne modifie pas la dérogation HIER historique.
**CURRICULUM demeure champion, quel que soit le résultat.**

## 4. Première porte : audit indépendant sans nouvelle recherche

Avant la moindre nouvelle partie, un lecteur indépendant doit authentifier les
manifestes de publication, tuples job/attempt/code et empreintes du JSON
compagnon, puis lire les objets réels. Le statut GitOps seul ne suffit pas.

Pour 2069, contrôler les 288 identités de paires, les 576 parties et leurs couleurs,
les modèles chargés, la sélection d'ouvertures, les trajectoires, l'identité
exacte des captures, les fins de partie, la cadence et les dix censures. Rejouer
les coups pour vérifier leur légalité **sans lancer de recherche moteur**.
Recalculer les scores, les cinq effectifs pentanomiaux et l'intervalle avec une
implémentation indépendante, sans appeler l'analyseur historique `analyze_main`.
Un checksum seul ou le recalcul depuis le résumé ne valent pas audit des parties.

Pour LOCAL/WDL, vérifier les fichiers modèles 2041 et les publications 2047/2049.
Relire les 512 lignes `probe.tsv` de chaque cas, pas seulement les rejets, et
figer une table descriptive avant toute nouvelle partie comparative. Distinguer
`profondeur_cible_non_atteinte`, `profondeur_atteinte_sans_reçu_exact` et
`information_insuffisante`. Une absence de reçu Exact/full-root **ne prouve pas**
à elle seule que le nombre de nœuds requis est censuré à droite. Ne pas imputer
un coût de 200k, ne pas supprimer ces lignes, ni recalculer un PASS G0.

Vérifier également la continuité sémantique des sources natives et des options
de construction entre les G0 historiques et le moteur de matchs. Si une différence
sémantique empêche d'attribuer la comparaison aux mêmes moteurs, bloquer : ne pas
substituer silencieusement un code récent. Les enveloppes historiques et celles
du match doivent être publiées ; nœuds fixes et temps fixe restent distincts.

Livrables obligatoires : `historical-2069-raw-audit.json`,
`source-and-model-authentication.json`, `native-continuity.json`,
`historical-g0-all-roots.tsv` et manifeste SHA256. L'état initial est
**NON AUDITÉ** ; cette PR ne prétend pas avoir lu les archives R2.
Un désaccord d'audit bloque la suite et ouvre un incident/erratum explicite,
sans écraser un résultat antérieur. Lectures historiques et rejeux de légalité
sont comptés séparément ; aucun entraînement, aucune nouvelle recherche.

## 5. Ouvertures prospectives, sans choix fondé sur les scores

Avec le générateur natif inchangé, exécuter deux fois et exiger les mêmes octets :

```text
--gen-opening-pool 2048 <fichier> 8 32 20 2026092011
```

Même population structurelle que le 2069 : trajectoires légales aléatoires,
positions calmes à 8–32 demi-coups, au moins 20 pièces. Aucun évaluateur chargé,
aucune recherche, aucun équilibrage selon le score. Le nouveau seed est fixé ici,
sans essai préalable de plusieurs seeds.

Exclusions par identité canonique plateau+trait avec rotation 180°/échange des
couleurs (`tb_frontier_symmetry_dedup`) : tous les 2 000 parents 1651 ; toutes les
positions des trajectoires 2066, 2067, 2068, 2069 ; toutes les ouvertures principales
et représentatives scellées pour 2069 ; position standard de préchauffage.
Les identités des publications d'exclusion sont fixées dans le JSON.

Dédupliquer, trier par SHA256 du JSON canonique `[2026092012, empreinte_canonique]`
(UTF-8, clés triées, séparateurs compacts, newline final, puis empreinte comme
briseur d'égalité). Retenir les **288 premières ouvertures principales et les
huit suivantes comme représentatives**. Les mêmes 288 départs servent aux deux
contrastes. Pas de remplacement, nouveau seed, filtrage ou régénération en production.
Moins de 296 départs admissibles bloque la version.

Sceller toutes les identités, FEN et exclusions avant les premières parties de
répétition. Un départ principal apparaissant dans une trajectoire de répétition
bloque les matchs : on ne le remplace pas après observation. L'identité de
sélection et les preuves d'exclusion deviennent des prérequis de production.
Cette fraîcheur concerne les sources énumérées : **aucune disjonction globale
avec les corpus d'entraînement ni représentativité des ouvertures humaines
n'est revendiquée**. Les transpositions ultérieures entre nouvelles parties ne
sont pas filtrées à partir des résultats.

## 6. Dispositif et répétition non comparative

Même source native que `7b789a0c675ce08868fe4a8fcef0becaa4193286`, empreinte du
binaire et modèles contrôlés ; paramètres de recherche compilés inchangés,
livre désactivé, un thread/joueur, TT 16 MiB, EGDB `/root/egdb_extracted/app`
cache 256 MiB. CPX62 doit confirmer **16 processeurs disponibles** ; quatre
travailleurs de paires, sans autre match concurrent du panel.

Processus joueurs/arbitre neufs par partie ; exactement un préchauffage profondeur 1
à la position standard par joueur, puis reset. Toutes les demandes de match sont
**100 ms nominales**, plafond bout-à-bout **120 ms**. Ce n'est pas un match avec
horloge bancaire et chute de drapeau à 100 ms strictes. Un dépassement du plafond
est TECHNICAL, jamais une nulle/perte. Aucune augmentation après échec.

Sur les départs représentatifs seulement :

- quatre premières ouvertures : contrôle déterministe CURRICULUM/CURRICULUM,
  profondeur 3, couleurs inversées, **8 parties** ; même trajectoire attendue à
  permutation des rôles, score descriptif par paire exactement 0,5 ;
- huit ouvertures : CURRICULUM/CURRICULUM, LOCAL/LOCAL et WDL/WDL à temps fixé,
  couleurs inversées, **48 parties**, pour le dispositif et les ressources.

Total : **56 parties**, aucun LOCAL/CURRICULUM, WDL/CURRICULUM ou nouveau HIER.
Les auto-matchs chronométrés ne sont pas obligés d'obtenir exactement 50 % :
la variation d'ordonnancement ne doit pas être confondue avec un bug de score.
Le contrôle identique n'est pas un candidat modifié ayant prouvé un G0 PASS.

Chaque modèle est chargé/authentifié ; aucun monkey-patch des anciens helpers
HIER/CURRICULUM n'est permis. L'implémentation future utilise une adaptation
propre à cette étude et conserve les versions historiques intactes.

Mesurer la durée complète par travailleur/paires, démarrages compris. Pour le
bloc de 24 paires chronométrées, définir
`F=max(1, 4*T_bloc/somme(durees_paires))`. Pour chaque candidat A, la projection
est `F*max(moyenne(A/A),moyenne(C/C))*288/4`, qui doit être <= **3 000 s**.
C'est une règle d'admission de ressources, pas une durée promise ; un échec
n'autorise ni volume réduit ni relâchement du plafond. Répétition réelle,
lecture après publication R2, même code/profil/spécification normalisée et
régressions non vides sont obligatoires avant tout match principal.

## 7. Deux matchs bornés et analyse fixée

Deux cellules déjà décidées : **LOCAL/CURRICULUM puis WDL/CURRICULUM**, chacune
288 paires, soit 576 parties. Les deux couleurs d'une ouverture ne sont jamais
traitées comme deux observations indépendantes. Pas de HIER rejoué, de modèle
choisi après le premier résultat, de test LOCAL/WDL, d'extension, de seconde cadence
ou d'arrêt pour avantage observé. Le premier résultat ne doit modifier ni l'exécution
ni l'analyse du second. Lecture inférentielle conjointe seulement après les deux
cellules complètes et techniquement valides.

Marge de cette vérification grossière : **100 Elo logistiques**, frontière
`b = 1/(1+10**(100/400)) = 0.35993500019711494`. Une perte plus petite peut rester
importante ; elle n'est pas certifiée acceptable par ce test.

Nouvelle famille de deux comparaisons : budget d'erreur **0,05**, partagé à
**0,025 par contraste**, soit 0,0125 par extrémité. Aucun recyclage de l'alpha du
2069 ; HIER et les contrôles n'entrent ni dans les effectifs ni dans cette famille.
Bonferroni ne suppose pas l'indépendance des deux contrastes sur les mêmes départs.

Une fin légitime vaut 0/0,5/1 pour le candidat. Un plafond administratif de
160 demi-coups donne les bornes [0,1], pas une nulle certaine. Les autres règles
de fin sont celles du dispositif validé ; aucun changement implicite.
Pour chaque paire, moyenner les bornes de ses deux parties : `L_i, U_i`.
Pour chacun des deux contrastes séparément :

```text
N = 288
r = sqrt(log(2/0.025)/(2*N)) = 0.08722204497512172
IC = [max(0, moyenne(L_i)-r), min(1, moyenne(U_i)+r)]
```

Sous l'hypothèse d'unités ouverture-paire indépendantes selon le modèle
aléatoire d'échantillonnage déclaré, la couverture conjointe est au moins 95 %.
Le générateur à seed fixé est traité selon son modèle pseudo-aléatoire ; la seule
absence de doublons ne prouve pas l'indépendance. La dépendance liée à la machine
partagée et le choix de ce panel limitent l'extrapolation. Ne pas présenter cette
couverture comme inconditionnelle sur n'importe quel ordonnancement ou population.

Décision par contraste, sans égalité forcée en faveur d'une conclusion :

- borne supérieure < b : `SUBSTANTIAL_LOSS_SUPPORTED` ;
- borne inférieure > b : `SUBSTANTIAL_LOSS_EXCLUDED` ;
- sinon, y compris égalité : `INDETERMINATE`.

Les résultats sous convention demi-point aux plafonds et les pentanomiales sont
**descriptifs**, distincts de ces bornes. Aucun IC post-hoc plus favorable ne remplace
celui-ci ; aucun cumul de 576 paires pour simuler une seule comparaison plus précise.

## 8. Budget maximal et sortie obligatoire

| Étape future | Parties nouvelles max | Recherches joueurs max | Plafond stage / dispatcher |
|---|---:|---:|---:|
| Audit des sources et rejeu de légalité | 0 | 0 | 900 / 1 500 s |
| Répétition de dispositif | 56 | 9 072 | 1 800 / 2 400 s |
| LOCAL / CURRICULUM | 576 | 93 312 | 3 600 / 4 200 s |
| WDL / CURRICULUM | 576 | 93 312 | 3 600 / 4 200 s |
| **Total maximal** | **1 208** | **195 696** | **9 900 / 12 300 s cumulés** |

Chaque partie compte au maximum 160 recherches jouées + 2 préchauffages.
Toutes les parties de répétition sont comptées, même à modèles identiques.
Zéro fit, nouveau probe G0, recherche Scan, self-play d'entraînement,
promotion, bake ou réinjection. Les plafonds sont des budgets prospectifs,
**pas un coût déjà engagé ni une estimation de fin**.

Les 288 paires historiques du 2069 ont pris 2 981 s entre démarrage et publication,
préparation comprise. C'est un repère historique, pas un débit transportable à
LOCAL/WDL ; la répétition doit établir leur admissibilité réelle.

Timeout partie 60 s, groupe de processus d'une paire 180 s ; scratch hors Git,
3 GiB libres, comptages démarré/terminé distincts et progression au plus toutes
les cinq minutes. Nettoyage des seuls processus/fichiers possédés par le job.
Pas de surveillance ChatGPT en arrière-plan promise. Les compteurs doivent être
produits par le runner/job ; la présente PR ne les implémente pas.

**Aucun retry automatique**, aucune paire supprimée ou imputée après un incident.
Les tentatives et répétitions échouées comptent dans le budget. Une réparation
technique ultérieure demande une décision explicite et conserve les données
consommées ; elle ne transforme pas les résultats partiels en verdict.
Les deux cellules sont requises pour le terminal conjoint. Un travail incomplet
reste bloqué, non « neutre » ; pas d'alpha recyclé vers le seul bras disponible.

## 9. Critères de sortie : décision utile, pas calibration sans fin

Lorsque les deux cellules sont complètes et valides :

| Résultats nouveaux | Terminal de panel | Interprétation et action |
|---|---|---|
| Au moins un `SUBSTANTIAL_LOSS_EXCLUDED` | `G0_PANEL_LARGE_LOSS_DISCORDANCE_REPLICATED_V1` | Nouveau cas de rejet ne correspondant pas à cette grosse perte ; peut justifier une proposition G0 V2, pas son activation |
| Deux `SUBSTANTIAL_LOSS_SUPPORTED` | `G0_PANEL_LOSS_CONCORDANT_ON_TWO_CASES_V1` | Concordance sur ces deux cas ; ne valide pas la fiabilité générale de G0 |
| Sinon | `G0_PANEL_INDETERMINATE_V1` | Budget clos, aucune prolongation improvisée |
| Audit, technique, ressources ou effectifs invalides | `G0_PANEL_BLOCKED_NO_JOINT_VERDICT_V1` | Documenter le blocage ; aucun verdict conjoint |

La répétition d'un décalage concerne uniquement la marge de 100 Elo, cette
cadence et ces cas. Elle ne démontre pas qu'un candidat rejeté méritait une
promotion. HIER reste contexte connu : pas de méta-analyse présentée comme une
nouvelle confirmation à 95 % sur trois modèles.

Ce panel contient des candidats non identiques tous déjà rejetés : il ne peut
estimer la sensibilité, la spécificité ou l'utilité générale de G0, ni apprendre
un seuil fiable. Il ne comporte pas de candidat modifié déjà démontré meilleur
et passant G0. Le contrôle identique ne comble pas cette lacune.

**À la sortie, arrêter et publier une recommandation unique.** Aucune troisième
cellule, nouvelle dose ou nouvelle cadence. Une future G0 V2 requerrait un contrat
séparé, figé avant ses nouveaux candidats et évalué sur d'autres cas que ceux
utilisés pour la concevoir. Aucun seuil G0 V1 ne change dans cette PR.

## 10. Handoff d'implémentation — non exécuté ici

La suite technique est définie : lecteur d'audit borné et indépendant ; adaptation
locale du chargeur/match aux modèles exacts ; tests d'identité, censure et refus ;
scellement des nouveaux départs ; vrai rehearsal/roundtrip ; admission explicite
des deux matchs ; readout conjoint et mise à jour du registre de décision.
Le SHA d'implémentation et les nouveaux IDs de jobs devront être scellés à cette
étape, jamais inventés dans ce document. Les tuples des anciennes publications
sont déjà fixés dans le JSON. Toute preuve manquante bloque l'admission.

Les tests ajoutés ici valident les constantes et règles de ce protocole sur
fixtures. Ils ne sont ni des tests natifs, ni une lecture R2, ni une mesure de
force. Aucun ancien contrat, code natif, verdict, modèle ou fichier de contrôle
n'est modifié. **Pas de réhabilitation de HIER ; pas de nouveau fit.**
