# ED5 — tentative k=2, choice-set avec teacher TRAIN Q200k

Date : 2026-09-14. Préenregistrement prospectif de la tentative `k=2` de `L3_EVAL_SEARCH_CANDIDATE_CAMPAIGN_V1_20260909.md`.

Ce document est écrit **après** le terminal ED4 `CAMPAIGN_ATTEMPT_SCIENTIFIC_NOT_SUPPORTED_V1` et **avant** toute génération des nouveaux labels TRAIN Q200k, tout nouveau fit ED5, toute nouvelle source confirmatoire k=2 et toute lecture de cible de confirmation k=2.

## 1. Signal motivant et hypothèse falsifiable

ED4 a remplacé la perte ordinale par le choice-set, mais le set admissible `A_p` était dérivé des arêtes PARTIAL construites à partir de Scan Q5k/Q50k. Sur la cohorte D fraîche de 512 parents, le candidat ED4 n'a pas établi le gain décisionnel requis : l'amélioration moyenne face à BASE est `-13.486328125` avec borne inférieure `-68.400390625`, et la borne inférieure face à HARD est `-73.77223307291666`. Ce constat sert uniquement à choisir l'axe suivant ; il ne règle aucun seuil ED5.

Hypothèse ED5 : **le principal défaut testable est la fiabilité du teacher de TRAIN**, pas la forme choice-set elle-même. Les ensembles admissibles issus de deux budgets Q5k/Q50k peuvent laisser dans `A_p` plusieurs coups que le teacher profond distinguerait. Si l'on conserve exactement le même objectif choice-set, les mêmes features, la même régularisation et le même WDL replay, mais que `A_p` est construit à partir d'un teacher Scan Q200k directement sur TRAIN, alors un unique candidat ED5 peut obtenir un gain décisionnel frais robuste face à BASE et HARD.

Cette hypothèse est falsifiée pour la tentative k=2 si le premier bloc confirmatoire D ne passe pas tous ses gates prospectifs. Dans ce cas ED5 s'arrête immédiatement ; W et S ne sont pas lus.

## 2. Intervention unique : teacher reliability

**Seul l'axe teacher/label de TRAIN change par rapport à ED4.**

Immuables par rapport à ED4-P1 :

- architecture PJTW v3 et tout le prefix pattern/header ;
- les 120 extras / 240 coordonnées MG-EG, dans le même ordre ;
- BASE SHA256 `e4d510fbb9b81cbe74574d92da48e8de6f61d8f98de6472eeb409713785f0de0` ;
- population TRAIN512 et source score-free ED2-P0 ;
- replay WDL historique de 8192 lignes déjà gelé comme **entrée de fit**, coefficient WDL `1` ;
- coefficient choice `1` ;
- ridge `0.0005 * ||beta||^2` ;
- initialisation beta zéro ;
- même signe parent-POV ;
- même loss choice-set ED4 : `logsumexp(V_p) - logsumexp(A_p)` ;
- même solveur `trust-exact`, float64, maxiter 500, gtol `1e-6`, trust radius initial 1, maximum 1000, eta 0.15 ;
- un seul solve par exécution, aucun restart/fallback ;
- mêmes critères de stationnarité, Hessien et objectif ;
- quantification scale 1000 ties-to-even, même double reload natif ;
- mêmes contrôles BASE/HARD/SOFT en confirmation ;
- aucune feature nouvelle, aucun changement search, aucun coefficient réglé, aucune température, marge, clipping, sweep, sélection de checkpoint ou tuning sur confirmation.

Le seul changement est la construction du set admissible `A_p`.

### Teacher TRAIN gelé

Pour chaque enfant non terminal de TRAIN512, obtenir un score de référence avec l'exact Scan déjà authentifié pour ED4-FRESH D :

- binaire Scan SHA256 `96b80c6aec1592f856a78ad7617ca6224b26be926800a6e37ede3b26f4e9cfa1` ;
- mêmes `scan.ini` et data authentifiés ;
- book OFF, bb-size 0, threads 1 ;
- fresh `new-game` par enfant ;
- `go analyze` à budget `200000` nœuds demandés ;
- 8 workers maximum, mapping déterministe `row_index mod 8` ;
- aucun appel Jass search.

Convertir chaque score selon le même contrat parent-POV que la confirmation ED4. Pour un parent `p`, `V_p` reste l'ensemble de ses enfants non terminaux. Définir :

`A_p = { i in V_p : Q200k_parent_pov(i) = max_{j in V_p} Q200k_parent_pov(j) }`.

Les ex æquo Q200k restent tous admissibles. `V_p` vide contribue zéro comme ED4. Les terminaux restent exclus du terme appris exactement comme ED4. Aucun epsilon ou marge n'est ajouté autour du maximum Q200k.

Ainsi, **la forme du loss n'est pas changée** ; seul le teacher qui détermine `A_p` change.

## 3. Données de fit et barrières

Réutiliser TRAIN512 et replay8192 est permis par le contrat de campagne parce que ce sont des entrées d'apprentissage gelées, pas des cibles confirmatoires k=1. En revanche :

- aucune ligne D 1937 Q200k de confirmation ED4 ne peut être réutilisée pour fit ou sélection ED5 ;
- aucune cible W1959 ou S1949 ne peut être lue pour ED5 ;
- le readout 1970 peut motiver l'axe teacher reliability, mais aucune valeur de celui-ci ne règle coefficient, seuil, volume ou gate ED5.

Le stage teacher TRAIN publie les scores Q200k, identités, coût, hash de Scan, hash source et un seal. Il doit finir avant le fit. Un échec technique se répare sans changer l'intervention. Un support manquant ne peut pas être remplacé par un autre parent.

## 4. Préflight, répétition et candidat

Avant fit réel :

1. test synthétique de la construction `A_p` avec maxima uniques et ex æquo ;
2. parité exacte du loss/gradient/Hessien ED4 pour un `A_p` donné ;
3. test du contrat parent-POV ;
4. build et double reload du probe natif ;
5. sizing CPX62 montrant <=45 min, 16 CPU max et >=3 Gio libres.

Le fit réel est exécuté deux fois sur le même code et les mêmes entrées : rehearsal puis production, une optimisation chacune. Les charges scientifiques pures (beta float64, objectif, gradient, Hessien, quantification, bytes du modèle) doivent être identiques. Aucune exécution n'est choisie selon une métrique de confirmation.

Le candidat positif est nommé `ED5_Q200K_CHOICE.pjtw`. Son SHA256 n'existe qu'après seal production et devient alors immuable pour toutes les confirmations k=2.

## 5. Multiplicité k=2

Tentative `k=2` :

- `alpha_k = 0.05 / 2^2 = 0.0125` ;
- chaque bloc D/W/S reçoit `alpha_k/3 = 0.004166666666666667` ;
- chaque assertion obligatoire d'un bloc utilise un intervalle unilatéral de niveau `0.9958333333333333` ;
- aucune renormalisation post-hoc ;
- aucun second seed/bootstrap/look après lecture.

Bootstraps gelés :

- D vs BASE : `202609141101` ;
- D vs HARD : `202609141102` ;
- D vs SOFT descriptif : `202609141103` ;
- W logloss : `202609141201` ;
- W Brier : `202609141202` ;
- S candidat vs BASE : `202609141301` ;
- sanities S séparées sans sélection.

Chaque bootstrap utilise `20000` réplications et l'unité groupée définie ci-dessous.

## 6. Nouvelles sources confirmatoires k=2

Aucune source confirmatoire k=1 n'est réutilisable comme preuve ED5. Générer trois sources fraîches score/target-blind puis établir leur disjointness canonique avant toute cible :

- D primaire seed `202609140501`, réserve `202609140511` ;
- W primaire seed `202609140502`, réserve `202609140512` ;
- S primaire seed `202609140503`, réserve `202609140513`.

Une réserve n'est utilisable que si le primaire rencontre avant cible un échec mécanique/source ou une collision canonique avec l'union historique/consommée. Aucun résultat scientifique ne peut déclencher une réserve.

Les trois nouvelles sources doivent être pairwise disjointes et disjointes des unions consommées, notamment D1937, W1959, S1949 et toutes les confirmations historiques authentifiées. Un échec de disjointness est technique/source, jamais une permission de modifier les gates.

### D — décision statique fraîche

- 512 parents, 64 par cellule phase × STM ;
- enfants score-free scellés avant cible ;
- teacher Scan Q200k, même configuration que 1970 ;
- unité bootstrap : parent, stratifiée phase × STM ;
- gates obligatoires : borne inférieure du gain de regret candidat vs BASE >0 ; borne inférieure vs HARD >0 ; top-hit candidat non inférieur au meilleur contrôle obligatoire ; harmed <= improved face à BASE ;
- SOFT descriptif.

Premier bloc exécuté. S'il échoue scientifiquement : `CAMPAIGN_ATTEMPT_SCIENTIFIC_NOT_SUPPORTED_V1`, cohorte D consommée, **STOP ED5**, aucune cible W/S.

### W — calibration WDL indépendante

Seulement après D PASS. Nouvelle génération d'issues, jamais CURRENT_2M. Même shape gelée que ED4-FRESH W sauf nouvelle seed :

- 512 `opening_id` indépendants ;
- exactement 2 games représentées par opening ;
- 8 lignes par game ;
- 8192 positions sélectionnées score-blind ;
- unité bootstrap : `opening_id` ;
- bornes supérieures unilatérales candidat−BASE `<=0.002` pour logloss et Brier ;
- aucun fit sur W.

Échec W : terminal campagne non-supported et stop avant S.

### S — transfert search à budget égal

Seulement après D PASS et W PASS. 512 racines fraîches, même exécutable Jass et mêmes bytes/config hors évaluateur, même cache/threads, même budget de nœuds candidat et BASE, teacher de référence gelé avant target. Gate primaire : borne inférieure du gain de regret de choix racine candidat−BASE >0. BASE/BASE doit être exact et aucune divergence nodes/config n'est tolérée. HARD secondaire, SOFT descriptif.

## 7. Issues terminales

- fit/serialization non reproductible ou technique : réparer même contrat, aucune science changée ;
- support/source/disjointness insuffisant avant cible : `CAMPAIGN_ATTEMPT_INSUFFICIENT_V1` ou technique selon cause ;
- premier gate confirmatoire obligatoire en échec : `CAMPAIGN_ATTEMPT_SCIENTIFIC_NOT_SUPPORTED_V1`, cohorte correspondante consommée, arrêt de la tentative ;
- D/W/S tous verts : `CAMPAIGN_REAL_CANDIDATE_GATE_GREEN_V1`, puis **STOP** sur `PREREGISTER_SCALE_UP_REVIEW`.

Aucune promotion, bake, Pool2, remplacement de `CURRICULUM`, match de force ou scale-up automatique n'est autorisé par ED5.

## 8. Ordre d'exécution autorisé

1. merge de ce préenregistrement ;
2. implémentation + tests du teacher TRAIN Q200k et du constructeur `A_p` ;
3. preflight/sizing sans cible confirmatoire ;
4. génération/scellement teacher TRAIN Q200k ;
5. rehearsal fit puis production candidate ;
6. génération/scellement des nouvelles sources D/W/S score/target-blind ;
7. disjointness D/W/S + historique ;
8. D confirmation ;
9. si et seulement si D PASS, W ;
10. si et seulement si W PASS, S ;
11. all-green -> stop review ; toute défaite scientifique -> stop tentative.

Aucune étape intermédiaire ne demande d'approbation manuelle tant qu'elle reste exactement dans ce contrat.
