# Revue Codex v3.1 — stratégie d’apprentissage de la conversion

> **Date : 2026-07-15**  
> **Statut : accord de conception figé, DOE `0726` clos, sonde multi-tours `ADJ + G1` prioritaire**  
> **Relation aux versions précédentes :** cette v3.1 ne remplace pas les fichiers `codex_review.md`, `codex_review_v2.md` et `codex_review_v3.md`. Elle conserve leur historique et met à jour le protocole après le diagnostic de `0724` et le verdict complet de `cpx62-0726-doe-labels-gym-2x2`.  
> **Périmètre :** améliorer la conservation et la réalisation des positions gagnantes sans changer de classe de modèle.  
> **Règle projet :** aucun NNUE ; rester dans l’évaluation linéaire-patterns tant que son meilleur fit n’est pas atteint.

---

## 0. Résumé exécutif

Le diagnostic central des versions précédentes est maintenu : le trou principal de Jass est situé **en aval de la détection**, dans la capacité à conserver puis réaliser un avantage déjà obtenu.

Le self-play WDL produit principalement un crédit global de partie. Il corrige la valeur des positions effectivement visitées, mais ne révèle pas directement le frère jamais joué qui aurait conservé le gain :

```text
parent certifié WIN
├── coup réellement joué       → enfant DRAW ou LOSS
└── frère jamais joué           → enfant WIN
```

Le futur `conversion_teacher` reste donc justifié par l’information contrefactuelle qu’il peut produire. En revanche, son développement et son fit ne sont pas l’étape immédiate.

Le DOE `0726` a maintenant tranché l’ambiguïté laissée par `0722` et l’échec technique de `0724` :

- le relabel profond `d14 + EGDB` est le seul facteur présentant une direction positive sur la force générale ;
- multiplier par quatre le gymnase actuel ne monte pas la conversion WDL-grounded ;
- le gymnase G4 baisse même la conversion d’environ 0,9 à 1,0 point par rapport à G1 ;
- aucune interaction utile `LABEL × GYMNASE` n’est démontrée ;
- le meilleur choix opérationnel du DOE est `adj_g1` ;
- le plafond à un seul tour est réel pour la recette testée.

### Résultats centraux de `0726`

| Cellule | Conversion WDL-grounded | N conversion | Gate vs bootstrap | N gate |
|---|---:|---:|---:|---:|
| `onp_g1` | 0,672986 | 422 | −8,11 Elo | 600 |
| `adj_g1` | 0,671362 | 426 | **+18,55 Elo** | 600 |
| `onp_g4` | 0,662679 | 418 | −29,02 Elo | 600 |
| `adj_g4` | 0,662679 | 418 | +16,23 Elo | 600 |

Contrastes directs :

```text
LABEL à G1       : +7,53 Elo ; conversion −0,0016
LABEL à G4       : +23,20 Elo ; conversion +0,0000
GYM sous ONP      : −2,90 Elo ; conversion −0,0103
GYM sous ADJ      : +5,79 Elo ; conversion −0,0087
interaction Elo   : non utile démontrée
interaction conv  : +0,0016
```

Ces chiffres imposent la recette suivante pour la prochaine étape :

```text
labels = adjudicated d14 + EGDB
 gym   = G1, sans répétition ×4
```

### Verdict opérationnel v3.1

```text
1. DOE 0726 clos : ne plus rediscuter G4 avant une nouvelle information.
2. Lancer la sonde multi-tours ADJ + G1, sans teacher.
3. Miner passivement les jets de gain pendant la sonde.
4. Ne pas fitter ni injecter le teacher avant le verdict de la sonde.
5. Après la sonde, exécuter le smoke teacher A/B1/B2/B3.
6. Lire B2 et B3 conjointement comme témoin/test de décalibration.
7. Confirmer le bras gagnant par un A/B élargi.
8. Intégrer ensuite seulement la recette dans la campagne longue.
```

Le risque principal n’est plus un mauvais diagnostic. Il est désormais la **dispersion expérimentale** : ouvrir teacher, profondeur par phase, `DEEP_EG` ou loss jointe avant d’avoir consommé la sonde multi-tours.

---

## 1. Ce qui change par rapport à la v3

### 1.1 Le diagnostic `0724` est clos

La v3 était suspendue à l’identification des 152 erreurs de conversion. La preuve committée par `0725` a montré un profil net :

- plusieurs shards avaient `n_pos = 0` et uniquement des `Broken pipe` ;
- les shards dont les moteurs avaient survécu jouaient normalement avec `n_errors = 0` ;
- un moteur pouvait également mourir en cours de shard avec `Jass: stdout closed`, après quoi toutes les positions suivantes échouaient en cascade.

La cause directement démontrée est donc la mort de processus Jass et l’absence de récupération dans `conv_fixed_wdl.py`. Une race d’ouverture EGDB sous forte concurrence est l’explication la plus probable, mais la preuve stricte porte sur la mort des moteurs et la cascade de pipes cassés.

Le correctif committé est :

```text
BrokenPipe / EOF / OSError / TimeoutError
→ fermer champion, défenseur et arbitre
→ recréer les trois processus
→ incrémenter n_restarts
→ abandonner seulement la position fautive
→ poursuivre le shard
```

Le problème OOM de `0723` avait été corrigé séparément en abaissant le cache par processus. Les incidents doivent rester historiquement distingués :

```text
0723 : OOM due au cache agrégé
0724 : cascade d’erreurs après mort moteur
0725 : preuve et diagnostic des shards
0726 : DOE robuste, terminé rc=0
```

Aucun incident n’a été masqué par un relâchement arbitraire de seuil.

### 1.2 Le verdict du gymnase n’est plus ouvert

La v3 disait que le verdict GYM restait en attente. Ce point est maintenant fermé pour la **forme et la dose testées**.

`G4` signifie ici la répétition accrue du gymnase certifié existant dans un fit à un tour. Dans ce cadre :

- la conversion baisse sous ONP et sous ADJ ;
- le contraste direct G4 contre G1 est neutre en force ;
- l’interaction avec les labels n’apporte pas de signal utile ;
- le coût en records augmente fortement sans amélioration de la métrique cible.

Conclusion de référence :

> **La répétition ×4 du gymnase existant est un cul-de-sac opérationnel pour la prochaine sonde.**

Cette conclusion ne signifie pas que toute donnée de conversion est inutile. Elle signifie que **répéter plus fortement les mêmes positions WDL** n’apporte pas l’information causale manquante.

### 1.3 `ADJ + G1` devient la recette minimale de la sonde

`adj_g1` est le meilleur compromis observé :

- meilleure valeur ponctuelle contre le bootstrap : +18,55 Elo ;
- conversion équivalente à `onp_g1` ;
- corpus plus petit et moins coûteux que G4 ;
- labels fondés sur l’oracle plutôt que sur l’issue fragile d’un pilote jeune.

Il faut toutefois conserver une nuance statistique : le gate individuel de `adj_g1` à 600 parties a un intervalle de taux `[0,4920 ; 0,5613]`, donc reste compatible avec le neutre. Le choix de `adj_g1` est **opérationnel et directionnel**, pas une proclamation de gain Elo définitivement établi à T1.

La décision repose sur la convergence de plusieurs observations :

- `0722` : bénéfice relatif net du relabel profond ;
- `0726` : direction positive des labels dans les deux niveaux G1/G4 ;
- absence de bénéfice de G4 sur la conversion ;
- coût plus faible et meilleure performance absolue de `adj_g1`.

### 1.4 Le plafond à un tour est désormais confirmé

Le DOE a retiré les deux principales excuses possibles du résultat précédent :

- la jauge n’est plus fondée sur le matériel ;
- `p4_egal` n’est plus ignoré par construction.

Malgré cela, aucune cellule ne montre une hausse de conversion par le gymnase, et les labels profonds n’augmentent pas directement la conversion à T1.

La conclusion correcte est :

> **Les labels profonds améliorent la qualité générale du fit, mais un seul tour ne suffit pas à transformer cette meilleure vérité WDL en technique de conversion supérieure.**

Cela justifie la sonde multi-tours avant d’introduire une nouvelle brique.

---

## 2. Décisions de conception toujours figées

### 2.1 Le trou est en aval de la détection

Le thermomètre PC Blues montre que Jass est proche de Scan sur la détection initiale, mais très loin sur la conversion. La ligne principale « corriger le search générique pour trouver les combinaisons » reste close.

Le territoire actif reste :

- value-function de conversion ;
- qualité et vérité des trajectoires ;
- technique de finale ;
- labels profonds ;
- crédit causal d’action ;
- oracles ;
- capacité linéaire spécialisée uniquement après preuve d’un signal non transféré.

### 2.2 Les labels profonds sont nécessaires

Les résultats `0722` et `0726` convergent : les labels on-policy d’un pilote jeune sont une source de vérité inférieure aux labels d14+EGDB.

Le relabel profond ne doit plus être considéré comme une option exploratoire. Il constitue le régime de référence de la prochaine sonde.

Hiérarchie de labels :

```text
TB exact
>
CERT-PROOF versionné
>
SEARCH-STABLE d14/d16
>
on-policy final
>
ambigu / quarantaine
```

### 2.3 L’information est séparée de la forme de loss

Le `conversion_teacher` reste défini par l’information extraite, non par la rank-loss utilisée pour l’injecter :

```text
WIN conservé par un frère non joué
>
WIN abandonné par le coup joué
```

Le DOE teacher devra toujours comparer quatre cellules :

```text
A   baseline WDL adjudicated
B1  A + frères oracle comme enregistrements WDL ordinaires
B2  A + rank-finetune statique good > bad
B3  A + rank-finetune through-search / leaf-mode
```

Le but n’est pas de prouver que le ranking est bon en général. Le but est de déterminer comment injecter une information contrefactuelle identique avec le moins de décalibration.

### 2.4 B2 est le témoin de décalibration de B3

La lecture pré-engagée du smoke reste :

```text
B2 régresse ET B3 compose
→ le through-search neutralise une pathologie du ranking statique
→ B3 est un vrai levier

B2 régresse ET B3 régresse
→ la forme préférence décalibre, même through-search
→ seul B1 reste crédible

B2 ≈ B3
→ le leaf-mode n’apporte rien de suffisant
→ préférer B1, moins cher et mieux éprouvé

B1 compose
→ l’information contrefactuelle suffit dans le canal WDL ordinaire
```

Pour que la différence `B3 − B2` soit attribuable au through-search, B2 et B3 doivent partager :

- exactement les mêmes décisions parentales ;
- les mêmes paires good/bad ;
- les mêmes splits train/holdout ;
- le même plafond d’exemples par parent ;
- une intensité d’optimisation comparable ;
- une grille d’anchor documentée ;
- les mêmes gates et les mêmes seeds.

### 2.5 La hiérarchie CERT est fondée sur la preuve

Une ancienne ligne appelée `CERT` n’a aucune autorité automatique.

Un `CERT-PROOF` doit embarquer :

- hash de position ;
- moteur et SHA ;
- paramètres d’oracle ;
- profondeur atteinte ;
- score, signe et marge ;
- side-to-move et convention de POV ;
- version/chemin EGDB ;
- PV éventuelle ;
- atteinte TB éventuelle ;
- stabilité entre profondeurs ;
- date et version du certificat.

### 2.6 Sonde et campagne longue restent deux régimes différents

La prochaine sonde multi-tours ne doit pas être confondue avec une preuve d’épuisement de L3.

Une sonde plate signifie :

```text
pas de signal rapide avec ADJ + G1 et ce budget
```

Elle ne signifie pas :

```text
impossibilité d’une campagne plus longue
ou impossibilité du teacher
```

La campagne longue reste gouvernée par les règles du projet : régimes établis, professeur monté, métriques stables et plateau confirmé au dernier barreau pertinent.

---

## 3. Lecture détaillée du DOE `0726`

### 3.1 Design

DOE factoriel strictement apparié :

```text
facteur LABEL : ONP vs ADJ d14+EGDB
facteur GYM   : G1 vs G4
base          : 120 000 positions uniques
pool gym      : 35 849 positions décisives après relabel
évaluation    : WDL-grounded, gagnant issu du relabel profond
```

Cellules :

```text
onp_g1 = 155 849 records
adj_g1 = 155 849 records
onp_g4 = 263 396 records
adj_g4 = 263 396 records
```

Les positions, records et cellules ont été hashés et vérifiés.

### 3.2 Résultats absolus

```text
onp_g1 : conv 0.672986 ; gate −8.11 Elo
adj_g1 : conv 0.671362 ; gate +18.55 Elo
onp_g4 : conv 0.662679 ; gate −29.02 Elo
adj_g4 : conv 0.662679 ; gate +16.23 Elo
```

Lecture :

- ADJ protège ou améliore la force générale ;
- ADJ ne change quasiment pas la conversion à T1 ;
- G4 ne monte pas la conversion ;
- le meilleur point absolu est ADJ+G1 ;
- la cellule la plus mauvaise est ONP+G4.

### 3.3 Effet LABEL

À G1 :

```text
adj_g1 − onp_g1 = +7,53 Elo direct
conversion       = −0,0016
```

À G4 :

```text
adj_g4 − onp_g4 = +23,20 Elo direct
conversion       = +0,0000
```

L’effet LABEL est cohérent sur la force, mais pas encore sur la métrique de conversion. Cela suggère que le bénéfice des labels vrais commence par empêcher une dégradation générale du modèle, avant de se traduire éventuellement en meilleure technique après plusieurs tours.

### 3.4 Effet GYM

Sous ONP :

```text
onp_g4 − onp_g1 = −2,90 Elo direct
conversion       = −0,0103
```

Sous ADJ :

```text
adj_g4 − adj_g1 = +5,79 Elo direct
conversion       = −0,0087
```

La répétition G4 n’améliore pas la cible. Même lorsque son contraste Elo ponctuel est légèrement positif sous ADJ, la conversion recule et l’intervalle reste compatible avec le neutre.

### 3.5 Interaction

```text
interaction conversion = +0,0016
interaction Elo        = label-diff +15,7 / gym-diff +8,7
```

Le job conclut correctement : aucune interaction utile n’est démontrée. Il ne faut pas lancer une campagne combinée `ADJ + G4`.

### 3.6 Ce que le DOE prouve

Le DOE prouve, dans le périmètre testé :

1. que l’ancienne jauge matériel n’était pas seule responsable du plateau observé ;
2. que G4 ne débloque pas la conversion à T1 ;
3. que les labels profonds sont préférables aux labels on-policy ;
4. que la recette minimale rationnelle est ADJ+G1 ;
5. qu’il faut tester la composition sur plusieurs tours avant d’ajouter une nouvelle brique.

### 3.7 Ce que le DOE ne prouve pas

Le DOE ne prouve pas :

- que toute donnée de conversion est inutile ;
- que tout gymnase futur est condamné ;
- que le teacher est redondant ;
- que +18,55 Elo est déjà statistiquement acquis ;
- que trois tours suffiront à fermer L3 ;
- que le modèle linéaire est épuisé.

Le teacher apporte un type d’information absent de G4 : le frère non joué. La répétition G4 et le crédit causal ne sont donc pas interchangeables.

---

## 4. Prochaine expérience : sonde multi-tours `ADJ + G1`

### 4.1 Objectif

Tester si la meilleure vérité WDL observée à T1 compose lorsqu’elle est réinjectée sur plusieurs générations.

Question principale :

> Les labels profonds améliorent-ils progressivement la conversion et la force lorsque le pilote qui génère les trajectoires devient lui-même plus compétent ?

### 4.2 Recette figée

```text
point de départ : recette validée du projet / bootstrap prévu par CURRENT
labels          : d14 + EGDB selon hiérarchie de preuve
poids gym       : G1 uniquement
teacher         : OFF
rank-loss       : OFF
DEEP_EG         : OFF
profondeur phase: inchangée
loss jointe     : OFF
```

Une seule variable scientifique doit évoluer : le numéro du tour et donc la qualité du pilote générateur.

### 4.3 Horizon

La sonde courte cible :

```text
T1-bis → T2 → T3
```

Le nom exact des tours doit suivre la convention du repo, mais le principe est trois états successifs suffisamment documentés pour voir une tendance.

### 4.4 Mesures à chaque tour

#### Force générale

- gate contre le parent direct ;
- gate contre le bootstrap ou ancre historique ;
- Elo et intervalle ;
- W/L/D ;
- taux de score ;
- durée et incidents.

#### Conversion WDL-grounded

- conversion globale ;
- conversion `p1_net` ;
- conversion `p2_moyen` ;
- conversion `p3_mince` ;
- conversion `p4_egal` ;
- N par strate ;
- erreurs et redémarrages ;
- win-preservation ;
- WIN→DRAW ;
- WIN→LOSS ;
- regret moyen si disponible.

#### Data et labels

- records générés ;
- positions uniques ;
- taux de labels modifiés par d14+EGDB ;
- répartition WIN/DRAW/LOSS ;
- répartition par nombre de pièces ;
- part TB exacte ;
- part CERT-PROOF ;
- part SEARCH-STABLE ;
- part ambiguë/quarantaine ;
- coût du relabel.

#### Stabilité du modèle

- nombre de poids modifiés ;
- normes `L1/L2/L∞` du déplacement ;
- déplacement EXTRA vs patterns ;
- saturation/logits ;
- loss train et holdout ;
- calibration WDL si disponible.

### 4.5 Lecture pré-engagée de la sonde

#### Cas S1 — Elo et conversion montent

```text
ADJ+G1 compose naturellement
```

Action : poursuivre la campagne longue. Le teacher reste intéressant comme accélérateur ou amplificateur, mais sa priorité baisse légèrement.

#### Cas S2 — Elo monte, conversion reste plate

```text
les labels vrais améliorent le général mais pas le crédit causal
```

Action : priorité forte au teacher quatre cellules. C’est le scénario le plus directement compatible avec le diagnostic « frère non joué manquant ».

#### Cas S3 — conversion monte, Elo reste plate ou baisse

```text
le modèle apprend la finale mais échange encore du milieu
```

Action : ne pas conclure que le teacher résoudra automatiquement la composition. Auditer le déplacement des poids, la distribution de data et la séparation milieu/finale avant toute campagne longue.

#### Cas S4 — Elo et conversion restent plats

```text
le relabel seul ne suffit pas au budget testé
```

Action : lancer le smoke teacher comme prévu. La priorité de l’information contrefactuelle augmente fortement.

#### Cas S5 — dégradation franche

```text
la boucle multi-tours dérive malgré les labels vrais
```

Action : arrêter la sonde, auditer le corpus et le fit. Ne pas empiler teacher ou profondeur pour masquer la dérive.

### 4.6 Stop de sonde et clôture scientifique

La sonde peut être interrompue pour :

- bug ou dérive technique ;
- régression forte et répétée ;
- métrique invalide ;
- corruption ou perte d’appariement ;
- changement involontaire de recette.

Une sonde arrêtée ne clôt pas automatiquement l’axe L3.

La clôture scientifique exige un plateau confirmé dans un régime établi et au dernier budget pertinent, conformément à la doctrine longue du projet.

---

## 5. Mining passif pendant la sonde

### 5.1 Autorisé

Le mining des événements de conversion peut tourner pendant la sonde, car il n’altère pas les candidats testés.

Il doit produire un inventaire, pas un nouveau modèle.

### 5.2 Interdit avant le verdict de sonde

- fitter B1/B2/B3 ;
- modifier la loss ;
- injecter les frères dans le corpus actif ;
- sélectionner un bras teacher ;
- changer la profondeur de jeu ;
- ouvrir `DEEP_EG` ;
- lancer une loss jointe.

### 5.3 Événement à miner

Premier événement causal par trajectoire :

```text
parent oracle = WIN
coup joué     → enfant oracle = DRAW ou LOSS
au moins un frère non joué → WIN
```

Inclure dès la première version :

- WIN→DRAW ;
- WIN→LOSS.

La distinction DRAW/LOSS doit être un tier d’analyse, pas deux pipelines séparés.

### 5.4 Unité d’échantillonnage

L’unité scientifique est le **parent**, pas la paire.

Règles :

- un seul premier jet par partie et par camp, sauf étude dédiée ;
- plafond de frères par parent ;
- poids total constant par parent ;
- déduplication par hash de position et coup ;
- split train/holdout au niveau parent ;
- aucun parent partagé entre train et holdout.

### 5.5 Oracle parent/enfants

Même régime d’oracle pour le parent et les enfants d’une décision :

- même profondeur ;
- même draw-band ;
- même version moteur ;
- même EGDB ;
- même convention de POV ;
- même politique de stabilité.

Une asymétrie parent/enfant constituerait une fuite de verdict.

### 5.6 Livrables du mining

```text
conversion_events.jsonl
conversion_pairs.jsonl
conversion_siblings.jnnw
conversion_manifest.json
conversion_holdout.jsonl
```

Champs minimaux :

- game id ;
- ply ;
- parent hash/FEN ;
- camp à jouer ;
- coup joué ;
- résultat oracle parent ;
- résultat oracle enfant joué ;
- liste des frères ;
- résultat oracle de chaque frère ;
- provenance oracle ;
- strate ;
- nombre de pièces ;
- score/marge/profondeur ;
- TB hit ;
- version moteur ;
- SHA des données.

### 5.7 Taille du premier lot

Le premier lot cible doit rester un smoke :

```text
5 000 à 20 000 parents causaux propres
```

La qualité et la diversité importent davantage que le nombre brut de paires.

---

## 6. Smoke teacher après la sonde

### 6.1 Bras

```text
A   baseline issue de la sonde, WDL adjudicated
B1  A + frères WIN comme lignes WDL ordinaires
B2  A + rank statique good > bad
B3  A + rank through-search / leaf-mode
```

Les quatre bras doivent partir du même checkpoint et utiliser les mêmes événements.

### 6.2 Contrôle conditionnel B1

Si B1 gagne, lancer un cinquième contrôle :

```text
C1 : frères ciblés sur jets causaux
C2 : enfants oracle propres ajoutés sans ciblage de jet
```

Ce contrôle sépare :

- le bénéfice de « plus de labels propres » ;
- le bénéfice spécifique du ciblage causal.

### 6.3 Métriques principales

Priorité :

1. win-preservation ;
2. conversion WDL-grounded ;
3. WIN→DRAW ;
4. WIN→LOSS ;
5. regret ;
6. gate généraliste ;
7. calibration WDL ;
8. pairwise accuracy holdout ;
9. déplacement des poids ;
10. coût de fit et coût runtime.

La pairwise accuracy seule ne constitue jamais un succès.

### 6.4 Gates du smoke

Un bras teacher ne peut être déclaré gagnant que s’il :

- améliore la métrique causale cible ;
- ne provoque pas une régression généraliste majeure ;
- survit à une confirmation indépendante ;
- conserve une calibration acceptable ;
- ne dépend pas d’une poignée de parents ;
- ne concentre pas son effet sur une seule strate sans explication.

### 6.5 Prior scientifique

B1 est le bras ayant le meilleur prior, car les seuls canaux historiquement robustes de Jass sont des canaux WDL ordinaires à labels vrais.

Ce prior ne doit pas influencer le verdict. Le DOE tranche par mesure.

---

## 7. Conditionnels explicitement différés

### 7.1 Profondeur par phase d16/d18

Ne pas l’introduire pendant la sonde ni pendant le smoke teacher.

Avant activation : microbenchmark dédié sur les mêmes seeds et positions :

```text
P0 : profondeur actuelle
P1 : EG d16 / deep-EG d18
P2 : EG d14 / deep-EG d16
```

Rapporter :

- wall time ;
- records/s ;
- games/hour ;
- profondeur réellement atteinte ;
- TB hits ;
- nombre de positions activées ;
- stalls ;
- labels modifiés ;
- coût marginal par label utile.

### 7.2 `DEEP_EG`

Déclencheur dur :

- signal teacher/ranking réel ;
- absence de transfert en jeu pendant au moins deux tours ;
- plateau concentré principalement sur 8–12 pièces ;
- capacité linéaire globale insuffisante démontrée localement.

Pas de déclenchement sur intuition.

### 7.3 Loss jointe

Une loss combinée WDL + préférence ne devient admissible qu’après :

- smoke séquentiel positif ;
- canal gagnant identifié ;
- calibration auditée ;
- besoin résiduel clairement mesuré.

### 7.4 MTC comme cible

MTC-in-search peut rester actif s’il est audité.

MTC-as-target reste fermé tant que :

- le WDL n’est pas maîtrisé ;
- les enfants ne sont pas tous certifiés gagnants ;
- la distance de conversion n’est pas une cible prouvée fiable.

---

## 8. Discipline de séquence définitive

```text
ÉTAPE 1 — 0726 CLOS
  verdict labels/gym consommé
  recette ADJ+G1 choisie

ÉTAPE 2 — SONDE MULTI-TOURS
  ADJ+G1
  aucun teacher
  mining passif uniquement

ÉTAPE 3 — VERDICT SONDE
  lire Elo + conversion + strates + stabilité

ÉTAPE 4 — SMOKE TEACHER
  A / B1 / B2 / B3
  B2 témoin de B3

ÉTAPE 5 — CONFIRMATION
  A/B élargi du bras gagnant

ÉTAPE 6 — CAMPAGNE LONGUE
  recette validée seulement

CONDITIONNELS
  profondeur par phase
  DEEP_EG
  loss jointe
  MTC-target
```

Règle : **un fil scientifique à la fois**.

Le mining peut être parallèle parce qu’il est observationnel. Le fit teacher ne l’est pas.

---

## 9. Critères de qualité et invariants

### 9.1 Reproductibilité

Chaque job doit consigner :

- SHA main ;
- SHA develop ;
- moteur utilisé ;
- poids parent/candidat ;
- hashes corpus ;
- seeds ;
- paramètres de génération ;
- paramètres de relabel ;
- paramètres de fit ;
- paramètres de gate ;
- versions EGDB/MTC ;
- temps CPU et wall ;
- host ;
- incidents/restarts.

### 9.2 Robustesse du harnais conversion

Conserver le restart-on-death.

Rapporter pour chaque cellule :

```text
n_requested
n_pos
n_errors
error_rate
n_restarts
conv
```

Distinguer :

- mort moteur au startup ;
- EOF/BrokenPipe ;
- timeout ;
- illegal move ;
- referee error ;
- max plies ;
- erreur inconnue.

Un timeout de partie peut être corrélé à la difficulté et doit être séparé d’une mort au startup.

### 9.3 Tolérance d’erreurs

Lecture recommandée :

```text
0–2 %   : mesure propre
2–8 %   : consommable avec audit de répartition
≈8 %    : analyse de sensibilité obligatoire
>8 %    : abort, pas de nouveau desserrage automatique
```

### 9.4 Appariement

- mêmes positions pour les contrastes ;
- mêmes ouvertures et couleurs ;
- mêmes seeds ;
- mêmes budgets ;
- corpus de base disjoint du gymnase et de l’évaluation ;
- splits au niveau position/parent ;
- aucune fuite train/eval.

### 9.5 Quota par position

La répétition brute de records ne doit pas permettre à quelques positions de dominer la loss.

Utiliser un quota canonique au niveau position ou parent, documenté dans le manifest.

---

## 10. Questions désormais closes

Les points suivants ne doivent plus être réouverts sans nouvelle donnée :

- le trou principal est la conversion, pas la détection ;
- les labels profonds sont préférables à l’on-policy ;
- G4 n’est pas la recette de la prochaine sonde ;
- `ADJ + G1` est le choix opérationnel ;
- le plateau T1 n’était pas seulement un artefact de la jauge matériel ;
- `0724` était un incident de harnais, pas un résultat scientifique ;
- le teacher doit comparer WDL, rank statique et through-search ;
- B2 doit être lu comme témoin de B3 ;
- la hiérarchie CERT repose sur la preuve ;
- `DEEP_EG`, profondeur par phase et loss jointe sont conditionnels.

---

## 11. Questions restant ouvertes

1. La boucle ADJ+G1 compose-t-elle entre T1-bis et T3 ?
2. Le gain directionnel Elo des labels se confirme-t-il à plus grand N ?
3. La conversion progresse-t-elle avec la maturité du pilote malgré l’absence d’effet à T1 ?
4. Quelle strate limite la progression : p1, p2, p3 ou p4 ?
5. Combien de jets causaux propres la sonde produit-elle par million de positions ?
6. B1 suffit-il ou le through-search B3 apporte-t-il un transfert supplémentaire ?
7. B3 échappe-t-il réellement à la décalibration historique de 0691 ?
8. Le bénéfice teacher est-il du ciblage causal ou seulement de nouveaux labels propres ?
9. Le modèle linéaire global transfère-t-il le signal de finale sans banque spécialisée ?
10. À quel moment une campagne longue, plutôt qu’une sonde, devient-elle justifiée ?

---

## 12. Décision finale v3.1

Le DOE `0726` ne réfute pas le diagnostic du crédit causal. Il précise l’ordre des travaux.

Le gymnase G4 a testé l’hypothèse :

```text
répéter davantage des positions de conversion déjà connues
```

Cette hypothèse n’a pas amélioré la conversion.

Le teacher testera une hypothèse différente :

```text
révéler le frère non joué qui conservait le gain
et localiser le coup joué qui l’a abandonné
```

Avant de payer cette nouvelle brique, le projet doit mesurer ce que les labels vrais seuls accomplissent sur plusieurs tours.

### Ligne d’exécution de référence

```text
0726 clos
→ sonde multi-tours ADJ+G1
→ mining passif des jets
→ verdict sonde
→ smoke teacher A/B1/B2/B3
→ confirmation du bras gagnant
→ campagne longue
```

### Travaux autorisés immédiatement

- préparer/queuer la sonde ADJ+G1 ;
- figer ses manifests, gates et seeds ;
- instrumenter le mining passif ;
- auditer MTC path et provenance oracle ;
- vérifier le reporting `n_restarts` ;
- conserver les artefacts et hashes 0726.

### Travaux non autorisés immédiatement

- réintroduire G4 ;
- fitter le teacher avant la sonde ;
- ajouter d16/d18 au même tour ;
- créer `DEEP_EG` ;
- combiner WDL et rank ;
- changer simultanément point de départ, anchor, profondeur et data ;
- conclure que +18,55 Elo est déjà une victoire statistiquement définitive.

## En une phrase

`0726` confirme un vrai plafond à un tour : les labels profonds sont le seul levier directionnel positif, le gymnase ×4 n’améliore pas la conversion et `ADJ + G1` devient la recette minimale de la sonde multi-tours ; le `conversion_teacher` reste la brique causale candidate, mais il ne sera fitté qu’après cette sonde, selon le smoke pré-engagé A/B1/B2/B3 où B2 sert de témoin de décalibration pour B3.