# Revue Codex v3 — stratégie d’apprentissage de la conversion

> **Date : 2026-07-15**  
> **Statut : accord de conception figé, exécution suspendue au diagnostic de `cpx62-0724`**  
> **Relation aux versions précédentes :** cette v3 ne remplace ni `codex_review.md` ni `codex_review_v2.md`. La v1 conserve le diagnostic initial, la v2 intègre les amendements structurants de Claude/Fable, et cette v3 clôt l’aller-retour de revue en transformant l’accord en protocole d’exécution strict.  
> **Périmètre :** améliorer la conservation et la réalisation des positions gagnantes sans changer de classe de modèle.  
> **Règle projet :** aucun NNUE ; rester dans l’évaluation linéaire-patterns tant que son meilleur fit n’est pas atteint.

---

## 0. Résumé exécutif

Le diagnostic central est désormais **clos et adopté** : le trou principal de Jass n’est plus la détection du premier coup tactique, mais la capacité à **conserver puis réaliser un avantage déjà obtenu**.

Le self-play WDL actuel produit surtout un crédit global de partie : toutes les positions visitées héritent de l’issue finale. Ce signal ne localise pas suffisamment la décision qui a abandonné un gain et ne révèle pas le frère jamais joué qui aurait conservé ce gain.

Le mécanisme manquant est donc un **crédit causal du coup de conversion** :

```text
parent certifié WIN
├── coup réellement joué       → enfant DRAW ou LOSS
└── frère jamais joué           → enfant WIN
```

Le véritable actif produit par le futur `conversion_teacher` est l’**information contrefactuelle** : l’oracle énumère et étiquette des enfants que la trajectoire n’a jamais visités.

La forme d’apprentissage de cette information n’est plus présupposée. Elle sera tranchée par un smoke à quatre cellules :

```text
A   baseline WDL adjudicated seule
B1  A + frères oracle ajoutés comme enregistrements WDL ordinaires
B2  A + rank-finetune STATIQUE sur les paires good > bad
B3  A + rank-finetune THROUGH-SEARCH / leaf-mode sur les mêmes décisions
```

Cette conception sépare :

- la valeur de l’information contrefactuelle ;
- la calibration absolue par WDL ;
- la préférence statique ;
- la préférence à travers les feuilles réellement consultées par la recherche.

Toutefois, l’exécution de ce plan est **temporairement suspendue au diagnostic de `0724`**.

`0724` n’a pas produit de verdict scientifique sur le gymnase. Le job a correctement :

- exécuté les tests ;
- construit les corpus appariés ;
- effectué le relabel profond ;
- construit et vérifié les quatre cellules du DOE labels × gymnase ;
- fitté les quatre candidats.

Il a ensuite échoué dans la première mesure de conversion WDL-grounded :

```text
cellule   = onp_g1
n_pos     = 284
n_win     = 195
n_draw    = 6
n_loss    = 83
n_errors  = 152
conv      = 0.6866
abort     = trop d'erreurs conversion : 152 > 8
```

La valeur `0.6866` ne doit **pas** être consommée comme résultat. Avec 152 erreurs pour 284 parties comptabilisées, l’échantillon effectif peut être fortement biaisé. Le prochain travail doit diagnostiquer et corriger ces erreurs avant toute conclusion GYM, toute sonde multi-tours ou tout développement de teacher.

### Verdict opérationnel v3

```text
1. Diagnostiquer et réparer la jauge / le harnais de 0724.
2. Récupérer les artefacts déjà produits si leur intégrité est démontrée.
3. Terminer le DOE WDL-grounded et rendre le verdict GYM propre.
4. Exécuter la sonde T1-bis→T3 sans teacher.
5. Miner les événements pendant la sonde, sans fitter le teacher avant son verdict.
6. Exécuter le smoke A/B1/B2/B3.
7. Confirmer le bras gagnant.
8. Intégrer seulement ensuite la recette dans une campagne longue.
```

Le risque principal n’est plus la conception. Il est désormais double :

- **consommer un résultat techniquement invalide** ;
- **ouvrir plusieurs fronts avant d’avoir terminé le précédent**.

---

## 1. Décisions désormais figées

Les décisions suivantes ont été examinées par Codex puis Claude/Fable. Elles constituent le cadre de référence et ne doivent plus être redébattues sans nouvelle donnée expérimentale.

### 1.1 Le trou est en aval de la détection

Le thermomètre PC Blues montre que Jass et Scan sont proches sur la détection du premier coup, tandis que l’écart de conversion reste massif. La ligne principale « chercher une nouvelle correction générique de search pour trouver les combinaisons » est close.

Le territoire actif est :

- value-function de conversion ;
- technique de finale ;
- qualité des trajectoires ;
- labels profonds ;
- oracles ;
- crédit d’action ;
- éventuellement capacité linéaire spécialisée en deep endgame, mais uniquement après preuve que le signal existe et ne transfère pas.

### 1.2 Les labels profonds sont nécessaires

`0722` a donné un résultat solide sur corpus strictement apparié : le relabel d14+EGDB modifie environ 61,5 % des labels et récupère environ +49 Elo relativement à l’on-policy.

Cela ne suffit pas encore à améliorer la conversion dès T1, mais cela protège la boucle contre l’apprentissage de la value-function erronée d’un pilote jeune.

La recette L3 ne doit donc plus revenir à des labels finaux on-policy non contrôlés comme source principale de vérité.

### 1.3 Le verdict du gymnase est ouvert, pas négatif

La formulation de la v1 « gymnase statique ×4 insuffisant » était trop forte.

La conclusion correcte de `0722` est :

> Le gymnase ×4 n’a pas apporté de gain généraliste mesurable à T1 dans les cellules testées.

En revanche, `conv_self.py` déterminait le camp gagnant à partir de l’avantage matériel. Il mesurait mal ou ignorait les positions `p4_egal`, alors que celles-ci constituent la strate dominante du nouveau tip.

Il n’est donc pas établi que le gymnase n’améliore pas la conversion. Le DOE WDL-grounded devait précisément lever cette ambiguïté. `0724` ayant échoué techniquement pendant la mesure, le verdict reste **en attente**.

### 1.4 L’information est séparée de la forme de loss

Le `conversion_teacher` n’est pas défini par la rank-loss. Il est défini par sa capacité à extraire une information locale et contrefactuelle :

```text
WIN conservé par un frère non joué
>
WIN abandonné par le coup joué
```

Le ranking statique reste une forme historiquement dangereuse :

- jusqu’à −847 Elo sur le bras statique ;
- pairwise accuracy en forte hausse sans transfert en jeu.

Le through-search a, lui, produit un signal positif confirmé : environ +33 au premier test et +23 sur confirmation, et non +47 comme cité initialement de mémoire.

Cela justifie le DOE à quatre cellules, sans préjuger du gagnant.

### 1.5 Sonde courte et campagne longue sont deux régimes distincts

La sonde T1-bis→T3 sert à mesurer une **direction rapide** avec une recette minimale propre.

Elle ne clôt pas la possibilité d’une campagne longue. Une sonde plate signifie seulement :

```text
pas de signal rapide avec cette recette et ce budget
```

Elle ne signifie pas :

```text
impossibilité de la boucle L3
```

La campagne complète reste gouvernée par la doctrine long terme du projet : derniers barreaux de professeur, gymnase réellement saturé, régime établi et plateau confirmé pendant plusieurs tours.

### 1.6 La hiérarchie oracle est fondée sur la preuve

La hiérarchie de référence est :

```text
TB exact
>
CERT-PROOF versionné
>
SEARCH-STABLE
>
AMBIGUOUS / quarantaine
```

Une ancienne certification d14 ne domine pas automatiquement un nouveau calcul simplement parce qu’elle porte le nom `CERT`.

L’autorité vient de la preuve embarquée :

- position hashée ;
- moteur et SHA ;
- paramètres d’oracle ;
- profondeur ;
- score et marge ;
- POV / STM ;
- version et chemin EGDB ;
- éventuelle PV atteignant une TB ;
- stabilité entre profondeurs.

### 1.7 La séquence est stricte

Les briques conditionnelles ne doivent pas être développées ou lancées « en parallèle pour gagner du temps ».

Ordre figé :

```text
DOE WDL-grounded valide
→ sonde sans teacher
→ teacher quatre cellules
→ confirmation du bras gagnant
→ campagne longue
```

Conditionnels en attente d’un signal amont :

- profondeur-par-phase d16/d18 ;
- objectif joint WDL + rank ;
- banque `DEEP_EG` ;
- classement MTC entre enfants tous gagnants.

---

## 2. Statut technique précis de `0724`

### 2.1 Ce que le job a correctement produit

Le log de `cpx62-0724-doe-labels-gym-2x2` montre que les étapes de préparation ont abouti.

#### Corpus de base

```text
base sélectionnée             = 120 000 positions
labels changés                = 73 714
pourcentage labels changés    = 61,428 %
labels décisifs après relabel = 78 764
```

#### Corpus gymnase

```text
pool initial                  = 52 682 positions
labels changés                = 35 849
pourcentage labels changés    = 68,048 %
kept_decisive                 = 35 849
dropped_draw                  = 16 833
```

#### Évaluation stratifiée

```text
sélection demandée            = 800
strates annoncées             = p1/p2/p3/p4
labels changés                = 436
kept_decisive                 = 436
dropped_draw                  = 364
```

#### Cellules construites

```text
onp_g1  = 155 849 records
adj_g1  = 155 849 records
onp_g4  = 263 396 records
adj_g4  = 263 396 records
```

Les cellules ont été vérifiées et les quatre fits ont été lancés puis terminés avant l’entrée dans la phase de métriques.

### 2.2 Point d’échec

Le premier appel de conversion, sur `onp_g1`, a retourné :

```text
n_pos     = 284
n_win     = 195
n_draw    = 6
n_loss    = 83
n_errors  = 152
conv      = 0.6866197183
```

Le runner a correctement abandonné, car la tolérance était de 8 erreurs.

### 2.3 Ce qui ne doit pas être conclu

Il est interdit de conclure à partir de ce log que :

- `onp_g1` convertit à 68,66 % ;
- le gymnase aide ou n’aide pas ;
- l’adjudication aide ou n’aide pas sur la jauge saine ;
- la strate `p4_egal` est résolue ;
- le DOE confirme ou réfute `0722`.

Le sous-échantillon réussi peut ne pas être aléatoire. Par exemple, si les erreurs touchent surtout les positions longues, difficiles, à matériel égal ou sujettes au timeout, le taux calculé sera artificiellement optimiste.

### 2.4 Ce qui peut éventuellement être récupéré

Les artefacts de `0724` peuvent éviter un nouveau coût de génération et de fit **uniquement si** leur intégrité est démontrée.

À conserver et hasher :

- corpus base on-policy ;
- corpus base adjudicated ;
- gymnase décisif ;
- les quatre cellules ;
- les quatre candidats PJTW ;
- manifests ;
- SHA des positions et records ;
- configuration du fit ;
- logs complets ;
- ordre des shards.

Avant réutilisation :

1. confirmer que tous les fits ont écrit un fichier complet ;
2. charger chaque PJTW avec Jass ;
3. exécuter une évaluation de sanité ;
4. vérifier les mêmes hashes que dans le log ;
5. confirmer que l’échec de métrique n’a pas déclenché de nettoyage partiel ;
6. consigner les chemins dans un manifest de reprise.

Si un seul de ces points est incertain, refaire la phase concernée plutôt que d’utiliser un artefact opaque.

---

## 3. Diagnostic exigé avant tout nouveau run scientifique

Le diagnostic de `0724` doit être un job court et instrumenté, pas une simple augmentation de tolérance.

### 3.1 Première règle : ne pas desserrer aveuglément le seuil

Passer de `max(8, 2 %)` à 152 erreurs rendrait le job vert sans rendre la mesure vraie.

Un seuil de tolérance sert à absorber quelques erreurs d’infrastructure indépendantes. Il ne doit jamais masquer une défaillance touchant plus d’un tiers des tentatives.

### 3.2 Taxonomie obligatoire des erreurs

`conv_fixed_wdl.py` ou le harnais appelé doit écrire une catégorie pour chaque échec :

```text
timeout_engine
engine_exit_nonzero
engine_protocol_error
illegal_move
referee_error
no_legal_move_incoherent
max_plies_reached
process_spawn_error
broken_pipe
missing_outcome
invalid_fen
invalid_label_or_pov
egdb_error
other
```

Pour chaque catégorie, le manifest doit contenir :

```text
count
position_ids
strate p1/p2/p3/p4
nombre de pièces
STM
camp testé
candidat
couleur du candidat
plies atteints
temps consommé
message d'exception compact
```

### 3.3 Ventilation par strate

Les erreurs doivent être ventilées au minimum par :

```text
p1_net
p2_moyen
p3_mince
p4_egal
```

Question centrale : les 152 erreurs sont-elles concentrées dans `p4_egal` ?

Si oui, la nouvelle jauge révèle peut-être une faiblesse du harnais sur les positions précisément absentes de l’ancienne métrique : parties longues, répétitions, défenses techniques, captures complexes ou absence de camp matériellement évident.

### 3.4 Reproduction minimale

Avant de relancer les quatre cellules :

1. sélectionner 20 positions ayant échoué ;
2. rejouer chaque position en mono-processus ;
3. capturer stdout, stderr et transcript des coups ;
4. rejouer avec timeout augmenté ;
5. rejouer avec le même binaire mais un candidat de contrôle ;
6. comparer comportement single-thread et sharded ;
7. isoler le premier mécanisme commun.

Puis créer un test de non-régression reproduisant au moins un exemplaire réel de chaque catégorie trouvée.

### 3.5 Hypothèses à tester dans l’ordre

#### H724-A — timeout ou budget trop serré

Indices attendus :

- erreurs tardives ;
- concentration sur p3/p4 ;
- disparition en mono-processus ou avec timeout accru ;
- processus encore vivants au moment de l’abandon.

Correction : distinguer le budget de coup du timeout de sécurité du processus. Le timeout externe doit inclure une marge pour le referee, les entrées/sorties et la fin de partie.

#### H724-B — protocole / fermeture de processus

Indices : broken pipe, EOF, moteur fermé trop tôt, erreurs corrélées au sharding.

Correction : audit du cycle de vie des `JassEngine`, collecte de stderr, redémarrage contrôlé après crash sans silently skip.

#### H724-C — max plies interprété comme erreur

Une position gagnante difficile peut atteindre le cap sans qu’un résultat propre soit disponible. Il faut distinguer :

- draw réglementaire ;
- cap de test ;
- timeout ;
- crash.

Le cap de test ne doit ni devenir automatiquement une défaite ni être mélangé aux erreurs techniques.

#### H724-D — incohérence POV / camp certifié

La jauge WDL-grounded ne doit plus inférer le gagnant par matériel. Elle doit lire le camp certifié dans le sidecar oracle.

À vérifier :

- label vu du bon POV ;
- transformation parent/enfant ;
- couleurs assignées au champion et au défenseur ;
- interprétation de `W`, `D`, `L` par le referee ;
- symétrie position retournée / couleur retournée.

#### H724-E — FEN ou décisions légales problématiques

À rechercher :

- position sans coup légal mais label WIN ;
- capture obligatoire mal transmise ;
- séquence de capture multiple ;
- FEN valide pour le miner mais non pour le referee ;
- position déjà terminale.

#### H724-F — saturation de ressources persistante

Le cache a été réduit de 2 048 à 512 Mo par shard, ce qui a évité l’OOM de préparation. Il reste possible que le parallélisme de 16 matchs provoque une autre pression : fichiers, processus, mémoire EGDB, I/O ou CPU oversubscription.

À comparer : 1, 4, 8 puis 16 workers sur les mêmes 20 positions.

### 3.6 Critères de réparation

La jauge est admise uniquement si :

- toutes les catégories d’erreur sont rapportées ;
- le jeu de reproduction réel passe ;
- le taux d’erreur est sous le seuil pré-engagé ;
- les erreurs restantes ne sont pas concentrées dans une strate ;
- deux candidats de contrôle produisent un N comparable ;
- le même ensemble de positions est effectivement joué par chaque cellule ;
- les positions non terminées sont traitées par une règle explicite, identique entre cellules ;
- le calcul de `conv` est apparié ou au minimum basé sur un sous-ensemble commun consigné.

### 3.7 Sous-ensemble commun recommandé

Le DOE doit idéalement produire :

```text
eligible_positions
successful_positions_by_cell
intersection_successful_all_cells
```

La métrique principale doit être calculée sur l’intersection réussie des quatre cellules, afin qu’un candidat ne soit pas avantagé parce qu’il échoue précisément sur les positions difficiles.

Les métriques par cellule sur leur N individuel peuvent être rapportées en diagnostic secondaire, jamais comme verdict principal si les ensembles diffèrent.

---

## 4. Séquence d’exécution stricte après réparation

## Phase 0a — finir le DOE WDL-grounded

Objectif : mesurer proprement les effets :

```text
LABEL = on-policy vs d14+EGDB
GYM   = G1 vs G4
interaction LABEL×GYM
```

Sorties obligatoires :

- conversion appariée WDL-grounded ;
- gate généraliste de chaque cellule vs bootstrap ;
- contrastes directs entre cellules lorsque rentables ;
- ventilation p1-p4 ;
- taux d’erreur et N commun ;
- effect sizes, pas seulement verdict binaire.

Lecture :

### Cas 1 — GYM monte la conversion sur jauge saine

Le gymnase fournit déjà un signal réel. Cela ne rend pas le teacher inutile, mais sa priorité immédiate baisse légèrement. La sonde doit vérifier si ce signal compose sur plusieurs tours.

### Cas 2 — GYM reste plat sur jauge saine

La répétition de positions certifiées ne suffit pas. La priorité du crédit causal par frères augmente.

### Cas 3 — GYM monte conversion mais dégrade généraliste

Le signal est réel mais entre en conflit avec la calibration globale ou la représentation de phase. Le teacher peut permettre un signal plus ciblé et moins volumique ; `DEEP_EG` reste conditionnel et prématuré.

### Cas 4 — interaction LABEL×GYM forte

Le gymnase n’est utile qu’avec labels profonds ou inversement. La recette de sonde doit conserver la combinaison et éviter d’interpréter les effets principaux seuls.

## Phase 0b — audits courts

Après le DOE valide, exécuter uniquement les audits peu coûteux :

- SHA exact du binaire et des outils ;
- `terminate-at-TB` réellement actif ;
- `JASS_EGDB_MTC_PATH` réellement défini ;
- MTC-in-search actif ou non ;
- disjonctions train/eval ;
- jauges figées ;
- intégrité des pools et sidecars ;
- flag canonique de quota par positions.

Aucun fit expérimental nouveau pendant ces audits.

## Phase 1 — sonde T1-bis→T3 sans teacher

Recette minimale :

```text
champion précédent
→ self-play frais
→ labels hiérarchisés TB / CERT-PROOF / SEARCH-STABLE
→ gymnase contrôlé par quota de positions
→ fit WDL
→ métriques et promotion exploratoire
```

La sonde mesure ce que le relabel profond et le quota de conversion captent déjà sans frères contrefactuels.

### Règles de la sonde

- pas de teacher dans les fits ;
- pas de nouvelle banque `DEEP_EG` ;
- pas d’objectif joint ;
- pas d16/d18 introduit dans le même tour qu’un autre changement ;
- même fenêtre et mêmes jauges à chaque tour ;
- turnover réel des données ;
- artefacts conservés même si non promus.

### Mining autorisé en parallèle

Le mining des événements de conversion peut lire les parties de la sonde et écrire des événements bruts. Cela ne modifie pas la recette de la sonde.

Autorisé :

```text
parties sonde → événements candidats stockés
```

Interdit avant le verdict de sonde :

```text
événements → fit teacher → nouveau pilote de sonde
```

## Phase 2 — construction du teacher

Après la sonde, construire 5k–20k décisions validées.

Chaque décision contient :

```text
parent WIN
chosen child DRAW ou LOSS
au moins un sibling WIN
même oracle parent/enfants
même profondeur et draw-band
provenance complète
```

Les événements WIN→DRAW et WIN→LOSS sont inclus dès la v1. Leur distinction est conservée pour l’audit et le regret, pas pour créer deux pipelines.

## Phase 3 — smoke quatre cellules

Même baseline, mêmes décisions, mêmes splits et même budget logique :

```text
A   baseline WDL seule
B1  frères-en-WDL
B2  ranking statique
B3  ranking through-search
```

## Phase 4 — confirmation du bras gagnant

Le premier smoke sert à sélectionner une famille. Une confirmation plus large doit ensuite utiliser :

- plus de parties ;
- plusieurs jeux d’ouvertures ;
- conversion appariée ;
- holdout parents ;
- jauges généralistes ;
- une comparaison directe contre A ;
- idéalement un second seed de fit.

## Phase 5 — campagne longue

Le bras confirmé est intégré dans la boucle de campagne. L’arrêt est gouverné par la doctrine long terme, pas par les stop-rules de la sonde.

## Phase 6 — conditionnels

Uniquement après données positives :

- profondeur-par-phase ;
- objectif joint ;
- `DEEP_EG` ;
- classement MTC entre enfants tous WIN.

---

## 5. Lecture pré-engagée du smoke A/B1/B2/B3

Cette section complète et fige la lecture du DOE teacher. Elle évite une interprétation opportuniste après résultats.

### 5.1 Rôle de A

A mesure la baseline exacte sans information contrefactuelle.

Toute comparaison doit partir du même modèle, du même corpus WDL et de la même configuration générale.

### 5.2 Rôle de B1

B1 injecte l’information contrefactuelle dans le canal historiquement le plus robuste du projet : des labels WDL ordinaires.

```text
C_good = WIN
C_bad  = DRAW ou LOSS
```

La BCE implique un ordre sans rank-loss explicite.

B1 teste :

> L’information des frères suffit-elle lorsqu’elle est injectée comme valeurs absolues ordinaires ?

### 5.3 Rôle de B2

B2 n’est pas seulement un candidat. C’est le **témoin de décalibration de la forme préférence statique**.

L’historique donne un prior négatif fort. Sa présence est néanmoins indispensable pour comprendre B3.

### 5.4 Rôle de B3

B3 teste si le through-search permet de porter l’ordre local aux feuilles réellement consultées par la recherche sans reproduire la décalibration historique.

B3 peut réussir là où B1 échoue si :

- la valeur de l’enfant immédiat n’est pas la variable décisionnelle réelle ;
- la recherche atteint une distribution de feuilles différente ;
- l’ordre relatif est exprimable mais pas la calibration absolue ;
- l’enfant statique ne contient pas encore les motifs visibles quelques plies plus tard.

Mais B3 peut aussi échouer comme les préférences humaines leaf-mode si la rank-loss déforme la value-function générale.

### 5.5 Lecture conjointe B2/B3

```text
B2 régresse ET B3 compose
→ le THROUGH-SEARCH neutralise ou évite la pathologie du statique.
→ B3 est un levier réel, pas une rechute triviale de 0691.

B2 régresse ET B3 régresse
→ la forme préférence décalibre dans les deux variantes.
→ seul B1 reste admissible parmi les canaux teacher testés.

B2 ≈ B3 et les deux sont plats
→ le leaf-mode n'apporte pas de signal suffisant.
→ préférer B1 s'il est non négatif, car moins cher et plus simple.

B2 ≈ B3 et les deux gagnent
→ la nouvelle information contrefactuelle change la donne même en statique.
→ confirmer fortement avant de rouvrir la famille rank.

B1 ≈ B3 > B2
→ l'information est utile ; le ranking statique est inutile ou dangereux.
→ préférer B1 sauf avantage robuste de B3 sur conversion réelle.

B3 > B1 > A
→ le crédit a besoin de la distribution through-search.
→ confirmer que le gain excède le coût et n'est pas dû à une mise à jour plus forte.

B1 > B3
→ la calibration WDL est préférable à la préférence.
→ ne pas complexifier avec rank-loss.
```

### 5.6 Conditions d’équité entre B2 et B3

Pour attribuer `B3 − B2` au through-search, contrôler :

- mêmes parents ;
- mêmes décisions good/bad ;
- mêmes splits train/holdout ;
- même plafond d’exemples par parent ;
- mêmes strates ;
- grille d’anchor comparable ;
- budget d’optimisation comparable ;
- même nombre de passages ;
- normes de déplacement des poids rapportées ;
- mêmes gates après fit.

### 5.7 Contrôle conditionnel si B1 gagne

Si B1 compose, exécuter un cinquième contrôle seulement ensuite :

```text
B1-causal
  frères ciblés sur les jets de gain

B1-control
  enfants oracle propres échantillonnés sans jet identifié
```

Ce contrôle distingue :

- la valeur du ciblage causal ;
- l’effet générique « ajouter plus de labels propres ».

Il n’est pas un préalable au smoke initial.

---

## 6. Implémentation du `conversion_teacher`

## 6.1 Entrées

Le teacher consomme :

- parties ou trajectoires avec positions et coups ;
- candidat/champion exact ;
- binaire Jass exact ;
- EGDB ;
- configuration oracle ;
- liste des jauges interdites ;
- manifest de campagne ;
- éventuellement sidecar de certification du tip.

## 6.2 Détection du jet de gain

Pour chaque trajectoire :

1. évaluer ou lire le verdict du parent avant le coup joué ;
2. évaluer l’enfant choisi ;
3. chercher la première transition :

```text
parent WIN → enfant DRAW ou LOSS
```

4. énumérer tous les coups légaux frères ;
5. évaluer chaque enfant avec le même canal oracle ;
6. conserver l’événement s’il existe au moins un frère WIN ;
7. rejeter si verdict instable ou ambigu.

Le « premier jet » est prioritaire afin d’éviter de produire plusieurs exemples corrélés après que la partie est déjà sortie de la zone gagnante.

Une variante ultérieure peut miner plusieurs jets indépendants si un nouveau gain a été rétabli, mais pas dans la v1.

## 6.3 Oracle commun parent/enfants

Règle absolue : même profondeur, même bande, même binaire et mêmes conventions de POV pour le parent, l’enfant joué et les frères d’une décision.

Hiérarchie :

### TB

Verdict exact directement disponible ou atteint par une preuve traçable.

### CERT-PROOF

Admis si au moins une condition forte est remplie :

- PV qui atteint une TB avec verdict cohérent ;
- verdict stable d14/d16 avec marge pré-engagée ;
- autre preuve versionnée et reproductible explicitement admise.

### SEARCH-STABLE

Même signe sur profondeurs définies, marge suffisante, pas de preuve TB.

### AMBIGUOUS

Désaccord, faible marge, timeout, instabilité ou provenance incomplète. L’exemple est mis en quarantaine, pas forcé dans le train.

## 6.4 Schéma d’événement proposé

```json
{
  "event_id": "sha256",
  "game_id": "...",
  "ply": 87,
  "parent_fen": "...",
  "parent_stm": "W",
  "parent_verdict": "WIN",
  "parent_channel": "CERT_PROOF",
  "chosen_move": "...",
  "chosen_child_fen": "...",
  "chosen_verdict": "DRAW",
  "chosen_channel": "SEARCH_STABLE",
  "siblings": [
    {
      "move": "...",
      "child_fen": "...",
      "verdict": "WIN",
      "channel": "TB",
      "score": 0,
      "margin": null
    }
  ],
  "pieces": 10,
  "stratum": "p4_egal",
  "oracle_manifest": "...",
  "engine_sha": "...",
  "source_split": "train"
}
```

## 6.5 Déduplication et splits

Dédupliquer par décision, pas uniquement par ligne enfant :

```text
hash(parent normalisé + move choisi + ensemble des siblings retenus)
```

Split train/holdout par :

- partie source ;
- parent ;
- racine de gymnase ;
- famille de symétrie si nécessaire.

Jamais répartir plusieurs enfants du même parent entre train et holdout.

## 6.6 Échantillonnage par parent

Pour le smoke, aucun support natif de poids par parent n’est requis.

Le contrôle se fait par échantillonnage :

- plafond de bons frères par parent ;
- plafond de paires par parent ;
- stratification ;
- déduplication ;
- rapport de la distribution.

Un parent avec dix bons frères ne doit pas dominer mécaniquement le corpus.

## 6.7 Construction B1

B1 ajoute des enfants comme WDL ordinaires :

```text
bons frères       → WIN
coup joué jetant  → DRAW ou LOSS
```

Consigner :

- nombre de lignes ;
- nombre de parents ;
- proportion WIN/DRAW/LOSS ;
- poids du teacher dans le corpus total ;
- nombre moyen d’enfants par parent ;
- strates et pièces ;
- taux de doublons avec le WDL de base.

## 6.8 Construction B2

Paires statiques :

```text
[better_child, worse_child]
```

Le contrat POV de `rank_finetune.py` doit être vérifié par tests réels.

## 6.9 Construction B3

B3 doit générer les feuilles ou représentations through-search avec le mode leaf déjà validé dans MMTO.

Les décisions racines restent identiques à B2. Seule la représentation injectée dans le ranking change.

## 6.10 Métriques teacher natives

- pairwise accuracy holdout ;
- win-preservation one-ply ;
- regret de verdict ;
- proportion où le coup préféré conserve WIN ;
- calibration WDL sur enfants ;
- norme du déplacement de poids ;
- transfert en conversion réelle ;
- Elo généraliste.

Aucune métrique interne ne suffit seule à promouvoir.

---

## 7. Métriques et gates

## 7.1 Jauges maîtresses

### Conversion WDL-grounded appariée

Même ensemble de positions, même défenseur, même règle de résultat et camp certifié par oracle.

### Thermomètre PC Blues 224

Strictement hors entraînement.

### Match direct candidat vs parent

Mesure principale de non-régression générale.

### Match cumulé vs T0

Évite qu’une suite de petits wash masque une dérive cumulée.

## 7.2 Indicateurs avancés teacher

### Win preservation

Sur parents holdout ayant au moins un coup qui conserve et un coup qui jette :

```text
P(coup choisi par le moteur conserve WIN)
```

### Regret de verdict

```text
WIN → WIN   = 0
WIN → DRAW  = 1
WIN → LOSS  = 2
```

### Stalls

- répétitions ;
- règle des 25 coups ;
- cap technique ;
- plies avant TB ;
- gain abandonné puis récupéré ;
- première transition WIN→non-WIN.

## 7.3 Ce qui ne suffit pas

- baisse de train loss ;
- hausse pairwise accuracy seule ;
- meilleure calibration sur train ;
- gain sur une jauge dont le N diffère entre cellules ;
- conversion calculée après exclusion asymétrique d’erreurs ;
- un seul run de petit N ;
- gain vs bootstrap sans contraste direct contre A.

## 7.4 Promotion

Un candidat teacher doit montrer :

- non-régression générale ;
- amélioration de conversion appariée ;
- win-preservation cohérente ;
- absence de contamination ;
- résultat reproduit ou confirmé à N supérieur.

Une amélioration locale sans transfert conserve l’artefact pour diagnostic mais ne remplace pas le pilote.

---

## 8. Sonde versus campagne : règles d’arrêt

## 8.1 Abort technique

Immédiat si :

- corruption ;
- fuite ;
- POV faux ;
- oracle incohérent ;
- artefact manquant ;
- erreurs de jauge au-dessus du seuil ;
- ensembles non comparables.

`0724` appartient à cette catégorie. Il n’est ni positif, ni négatif, ni plat : il est **invalide techniquement**.

## 8.2 Arrêt de sonde

La sonde peut s’arrêter à T3 si elle ne montre pas de direction exploitable. Cela réoriente le poids vers le teacher, mais ne clôt pas la campagne potentielle.

## 8.3 Non-promotion

Un tour peut être non promu pour régression générale sans fermer la recette de campagne.

## 8.4 Clôture scientifique

La campagne ne se clôt que selon la doctrine :

- recette complète ;
- dernier barreau de professeur ;
- gymnase saturé ;
- métriques stables ;
- plateau confirmé pendant plusieurs tours ;
- budget réellement monté.

---

## 9. Pistes conditionnelles, explicitement gelées

## 9.1 Profondeur par phase

Idée adoptée mais non lancée maintenant.

Avant introduction : microbenchmark séparé.

```text
P0 profondeur actuelle
P1 finale d14 / deep finale d16
P2 finale d16 / deep finale d18
```

Mesurer coût, throughput, entrée TB, plies, stalls et labels.

Introduction à un tour dédié, jamais empilée avec teacher.

## 9.2 MTC

Audit immédiat autorisé en Phase 0b : vérifier si `JASS_EGDB_MTC_PATH` est réellement actif.

- MTC-in-search : admissible pour de meilleures trajectoires ;
- MTC comme métrique : admissible ;
- MTC-as-target : fermé ;
- MTC pour ordonner deux frères tous WIN : reporté après validation du teacher v1.

## 9.3 Objectif joint

Ne pas implémenter WDL + rank dans une loss commune avant qu’un fine-tune séquentiel ait montré un signal positif.

## 9.4 Banque `DEEP_EG`

Déclencheur durci :

- signal teacher réel pendant au moins deux tours ;
- win-preservation en hausse ;
- conversion playout plate ;
- plat concentré dans la zone 8–12 pièces ;
- non-explication par les jauges ou le search.

Avant cela, `DEEP_EG` est gelé.

---

## 10. Ce qu’il ne faut pas faire en attendant le diagnostic de `0724`

Ne pas :

- lancer la sonde T1-bis ;
- développer une nouvelle banque d’évaluation ;
- lancer les fits B1/B2/B3 ;
- augmenter la tolérance à 152 erreurs ;
- interpréter `conv=0.6866` ;
- conclure que le gymnase marche ;
- conclure que le gymnase ne marche pas ;
- modifier simultanément profondeur, teacher et quota ;
- créer une loss jointe ;
- réutiliser les candidats 0724 sans audit d’intégrité ;
- rouvrir les lignes search closes ;
- remplacer le WDL-grounded par l’ancienne jauge matériel pour obtenir un chiffre rapidement.

Travail autorisé :

- préserver les artefacts 0724 ;
- instrumenter la taxonomie d’erreurs ;
- reproduire 20 erreurs ;
- écrire les tests de non-régression ;
- auditer MTC et terminate-TB ;
- préparer un manifest de reprise ;
- documenter le diagnostic.

---

## 11. Livrable attendu du diagnostic `0724`

Le diagnostic doit rendre un court document ou `RESULTS.txt` contenant :

### 11.1 Cause racine

Une phrase falsifiable :

```text
Les 152 erreurs viennent principalement de X, déclenché par Y,
reproduit sur N positions, corrigé par Z.
```

### 11.2 Distribution

Tableau par catégorie et strate.

### 11.3 Preuve de correction

- mêmes 20 positions avant/après ;
- taux d’erreur ;
- transcript ou test ;
- absence de biais de strate ;
- N commun entre cellules.

### 11.4 Politique de reprise

Décider explicitement :

```text
rejouer métriques seulement
ou
rejouer métriques + gates
ou
refaire fits
ou
refaire le DOE complet
```

La décision doit être fondée sur l’intégrité des artefacts, pas sur le désir d’économiser du calcul.

### 11.5 Nouveau numéro de job

Le job réparé doit avoir un nouveau numéro et référencer :

- `0724` comme invalide ;
- le commit de correction ;
- les hashes repris ;
- la raison pour laquelle certaines étapes sont ou non rejouées.

---

## 12. Questions finales adressées à Claude/Fable pour le diagnostic

Ces questions ne rouvrent pas la conception. Elles ciblent uniquement la réparation de `0724`.

1. Quelle exception exacte est comptée dans les 152 `n_errors` ?
2. Les erreurs sont-elles des timeouts, des caps, des crashes ou des résultats impossibles à interpréter ?
3. Pourquoi `n_pos=284` et `n_errors=152` : le dénominateur total tenté est-il 436, 400, 800 ou autre ?
4. Les erreurs se concentrent-elles sur `p4_egal` ?
5. Le script joue-t-il les 436 positions décisives ou une sélection de 200 par palier avant filtrage ?
6. Les mêmes positions sont-elles tentées pour les quatre cellules ?
7. Un échec est-il dépendant du candidat, et donc potentiellement informatif plutôt que purement technique ?
8. Le timeout externe tient-il compte du temps du referee et de l’I/O ?
9. Le cap `max_plies` est-il classé comme erreur ?
10. Le défenseur fixe est-il identique dans les quatre cellules ?
11. Les moteurs sont-ils redémarrés après une erreur ou laissés dans un état corrompu ?
12. Les artefacts PJTW des quatre fits existent-ils encore et passent-ils un load test ?
13. Peut-on rejouer uniquement les métriques et gates sans régénérer ni refitter ?
14. Le calcul principal peut-il être fait sur l’intersection des succès des quatre cellules ?
15. Quelle tolérance résiduelle est scientifiquement acceptable après correction ?

---

## 13. Conclusion finale

L’aller-retour de revue est clos. Le consensus de conception est :

1. le trou principal est un manque de crédit causal du coup de conversion ;
2. le teacher doit miner les frères non joués ;
3. l’information contrefactuelle doit être séparée de la forme de loss ;
4. le smoke A/B1/B2/B3 tranche WDL, ranking statique et through-search ;
5. B2 et B3 doivent être lus conjointement pour isoler la décalibration ;
6. la sonde courte ne remplace pas la doctrine de campagne longue ;
7. la hiérarchie des labels dépend de preuves versionnées ;
8. les leviers conditionnels restent gelés jusqu’à signal amont.

Mais aucune de ces étapes ne doit maintenant contourner le fait suivant :

> `0724` a échoué dans la jauge WDL-grounded avec 152 erreurs. Il ne fournit aucun verdict GYM consommable.

La seule action scientifique immédiate est donc :

```text
préserver → classifier → reproduire → corriger → valider → reprendre
```

Puis seulement :

```text
DOE valide
→ sonde sans teacher
→ teacher quatre cellules
→ confirmation
→ campagne longue
```

**En une phrase :** la conception est figée ; le prochain progrès ne viendra pas d’une nouvelle idée, mais d’une mesure `0724` réparée, appariée et techniquement irréprochable.