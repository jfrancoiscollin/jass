# Proposition CLS G0 V2 — validation à trois états

**Statut : `PROPOSAL_ONLY_CASE_FEASIBILITY_PENDING_NOT_ACTIVATED`**

Cette note prépare un contrat prospectif séparé. Elle n'active pas G0 V2 et
n'autorise aucun fit, search, match, promotion, bake, rollout ou élément de file.
La décision jointe publiée reste
`G0_PANEL_LARGE_LOSS_DISCORDANCE_REPLICATED_V1`, avec la décision opérationnelle
`STOP_INTERPRET_NO_AUTO_G0_V2_NO_PROMOTION`.

La proposition est fondée sur le reçu joint authentifié, SHA-256
`556744fe2857c5f9af9ff593d8c7ee57d579b0a28b3f7ab88a36d25f73344d66`, et renvoie
au [résultat joint](CLS_G0_REJECTION_PANEL_V1_RESULTS_20260921.md). Les FAIL G0 V1
historiques LOCAL, WDL et HIER, leurs identités et leurs décisions sont conservés.
Les cas LOCAL, WDL et HIER, leurs tables G0 et leurs parties servent uniquement à
concevoir la proposition. Ils sont exclus du choix de seuil ou d'effectif et de
la validation V2. Le JSON compagnon fixe les identités des cas et du contrat V1.

## Question et règle proposée

La question est de savoir si G0 peut conserver son écran de catastrophe sans
transformer l'absence d'un reçu G0-C Exact/full-root valide en preuve de catastrophe.
La proposition conserve les définitions G0-A, G0-B et G0-D ainsi que tous leurs
seuils gelés. Lorsque tous les reçus G0-C existent, la définition V1 et le seuil
`1.50` restent inchangés.

La seule modification d'interprétation est la suivante :

- identité, parité des traces et exécution de recherche valides, mais reçu G0-C
  Exact/full-root requis absent, sans autre seuil observé en échec :
  `ABSTAIN_REQUIRES_SEPARATE_STRENGTH_ADJUDICATION` ;
  cet état ne peut jamais devenir PASS ni FAIL scientifique ;
- dérive d'identité, provenance de trace malformée/incomplète ou recherche non
  exécutée : blocage `TECHNICAL` ;
- échec observé d'un seuil A/B/D, ou échec du seuil G0-C avec données complètes :
  `FAIL` selon la règle gelée ;
- PASS reste réservé au chemin complet conforme aux seuils gelés et n'ouvre que
  l'étape de force déjà préenregistrée.

Une provenance invalide bloque d'abord l'adjudication technique ; parmi les cas
techniquement valides, un seuil observé en échec conserve FAIL, même si C est absent.
La seule absence du reçu Exact ne permet aucun verdict de réussite ou d'échec scientifique.

L'abstention ne fait avancer aucun candidat. Toute adjudication de force liée à
une abstention devra être préenregistrée séparément, avant lecture des sorties.

## Conditions d'indépendance et barrière d'information

Le contrat devra fixer une liste finie de cas réellement nouveaux, issus d'un
mécanisme scientifique séparément préenregistré. Aucun refit, aucune dose et aucun
dérivé choisi pour réparer le résultat LOCAL/WDL/HIER ne sera admissible. La règle
de génération, le parent direct, le sentinelle CURRICULUM immuable, les entrées de
fit et les identités candidates devront être scellés avant toute lecture G0 V2.

Il faudra aussi un holdout runtime/racines aveugle aux scores, disjoint des racines
G0 V1 FULL-512 et des ouvertures de force du panel. Sa source, sa sélection, sa
graine, ses exclusions, son équilibre de phases et sa route de référence profonde
seront scellés avant la recherche candidate. Les sorties G0 et les labels de force
indépendants resteront aveugles jusqu'au scellement de la liste complète des cas
et à l'achèvement de toutes leurs sorties requises.

Pour chaque cas, le contrat devra préengager l'algorithme A/B/C/D, la carte PASS /
FAIL / TECHNICAL / ABSTAIN et, pour ABSTAIN seulement, l'adjudication appariée de
force avec adversaire, ouvertures, censure, taille, marge, alpha, budgets et
terminal. Le score G0 ne pourra modifier cette adjudication. Aucune promotion,
aucun bake et aucun scale-up ne pourra suivre de G0 V2 ou de son adjudication.

## Audit de faisabilité borné

La préparation immédiate est documentaire : inventorier les manifestes authentifiés
locaux, les lignées candidates et les exclusions, puis établir la faisabilité du
roster et du holdout. Aucun payload scientifique nouveau ne doit être lu ; aucun
fit, search, match ou élément de file ne doit être créé. Les champs dépendant de
l'inventaire, de la taille prospective, de l'alpha, des budgets et de la marge
restent `pending`/`null` jusqu'à un dossier indépendant. L'audit fait un seul passage
sur les métadonnées CLS locales énumérées dans `docs/experiments/` et les répertoires
CLS de `jass-control/specs/`, avec au plus 40 fichiers ouverts. Il consigne les chemins
et empreintes lus ; il n'étend pas la recherche à de nouveaux payloads ou à R2.

Si l'inventaire local ne permet pas d'établir simultanément un roster fini et
disjoint, un holdout vierge avec route de référence, une justification prospective
de l'effectif, et une adjudication ABSTAIN compatible avec un budget borné, le
terminal de préparation est :
`G0_V2_PROPOSAL_BLOCKED_INDEPENDENT_CASES_UNAVAILABLE`.

## Conditions d'activation ultérieure

Une activation séparée devra publier le terminal joint et son SHA-256, les contrats
V1 et tous les FAIL historiques, l'inventaire et la preuve d'indépendance, le
holdout, l'algorithme à trois états, les seuils inchangés, la justification de
l'effectif, la revendication statistique, alpha et plafonds, l'adjudication ABSTAIN,
le SHA d'implémentation, les tests, le profil de lancement, la provenance, la
relecture fail-closed et une décision explicite d'activation. La publication de
cette proposition ne remplit aucune de ces conditions et ne modifie pas
`STOP_INTERPRET_NO_AUTO_G0_V2_NO_PROMOTION`.
