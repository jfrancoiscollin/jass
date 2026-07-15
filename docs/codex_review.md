# Revue Codex — stratégie d’apprentissage de la conversion

> **Date : 2026-07-15**  
> **Statut : proposition technique pour revue détaillée par Claude Code**  
> **Périmètre : améliorer la conversion des positions gagnantes sans changer de classe de modèle**  
> **Règle projet : aucun NNUE ; rester dans l’évaluation linéaire-patterns tant que son meilleur fit n’est pas atteint.**

## 0. Résumé exécutif

Le problème principal de Jass n’est plus la détection des combinaisons. Le thermomètre PC Blues a montré que Jass détecte les premiers coups à peu près comme Scan, mais convertit très mal les gains obtenus : la faiblesse est en aval, dans la conservation et la réalisation du gain.

Les expériences récentes apportent deux résultats solides :

1. **Les labels on-policy produits par un jeune pilote sont de mauvaise qualité.**  
   Le relabel d14+EGDB corrige une forte proportion des issues et récupère environ **+49 Elo** sur un corpus strictement apparié (`0722`), en passant d’un candidat on-policy à environ −46 Elo contre le bootstrap à un candidat adjudicated à environ +3 Elo.

2. **Un gymnase statique fortement répété ne suffit pas au premier tour.**  
   Sur `0722`, ajouter le gymnase certifié avec une multiplicité ×4 ne fait pas monter la conversion et n’ajoute pas de force : environ −6 Elo relativement à l’adjudication seule, avec une conversion légèrement plus basse. Le DOE 2×2 de la PR #329 reste utile pour une mesure factorielle complète, mais il est raisonnablement en pause car les effets principaux sont déjà très informatifs.

**Verdict :**

- Il faut tester une courte campagne **T1→T2→T3** de self-play avec labels propres, mais **pas enchaîner des boucles classiques en aveugle**.
- Une simple répétition de positions gagnées ne donne pas au fit le crédit causal nécessaire pour apprendre la conversion.
- La brique de développement la plus importante qui manque est un **professeur de conversion par préférences de coups**, capable de transformer chaque gain abandonné en exemples objectifs :
  
  `coup qui conserve WIN > coup qui transforme WIN en DRAW/LOSS`.

Une grande partie de l’infrastructure existe déjà : self-play piloté par le champion, EGDB, deep-relabel, génération de frères, format JNNW, `rank_finetune.py`, métriques de conversion et runners GitOps. Le manque principal n’est donc pas une nouvelle architecture d’apprentissage générale, mais le **pont entre les échecs de conversion et un signal local d’action**.

---

## 1. Faits établis à ne plus rediagnostiquer

### 1.1 La détection/search n’est pas le trou principal

Le thermomètre PC Blues a comparé Jass et Scan sur 224 combinaisons réelles figées :

- détection du premier coup : Jass et Scan sont proches ;
- conversion du camp au trait : Jass est très loin derrière Scan ;
- l’augmentation de profondeur ne lève pas fondamentalement la détection.

Conclusion déjà adoptée dans `CURRENT.md` : Jass trouve souvent l’idée tactique, puis ne sait pas conserver et réaliser l’avantage. Il faut donc travailler la value-function et la technique de finale, pas relancer une campagne générale sur LMR, pruning ou profondeur uniforme.

### 1.2 Les labels profonds sont un levier réel

`0721` a donné un premier signal, mais avec des défauts méthodologiques :

- shards réassemblés hors ordre pour le calcul du pourcentage de labels changés ;
- perte de shards sur cpx62 ;
- candidats comparés séparément au bootstrap plutôt qu’en contraste direct apparié.

`0722` a réparé le cœur du problème :

- 105 000 positions communes aux deux cellules ;
- exclusion symétrique des shards échoués ;
- relabel d14+EGDB aligné ;
- mesure valide de **61,5 % de labels changés** ;
- on-policy : conv ≈ 0,488, gate ≈ −46 Elo ;
- adjudicated : conv ≈ 0,458, gate ≈ +3 Elo ;
- effet label propre : **environ +49 Elo**.

Lecture : l’adjudication ne donne pas encore une meilleure conversion au premier tour, mais elle évite que le fit apprenne la value-function erronée d’un pilote jeune. Elle est un préalable à toute boucle L3 sérieuse.

### 1.3 Le gymnase statique ×4 ne débloque pas T1

Toujours dans `0722` :

- `adjudW0` : 105k positions, environ +3 Elo ;
- `adjudWhi` : même base + 31 383 positions décisives du gymnase répétées ×4, environ −3 Elo ;
- conversion : légère baisse supplémentaire.

Ce résultat ne démontre pas que la conversion est inenseignable. Il démontre que :

- répéter les mêmes positions n’est pas la même chose que produire de meilleures trajectoires ;
- le WDL plat ne dit pas quel coup conserve le gain ;
- un corpus plus lourd en finales peut créer un conflit avec la force générale ;
- à T1, le bootstrap matériellement fort reste un plafond difficile à dépasser avec une simple régression WDL.

### 1.4 Les boucles multiples ont déjà régressé dans le passé

L’historique EGDB contient un avertissement important :

- jouer les finales plus profondément dans une génération a apporté un gain réel : environ **+74 Elo** et une nette amélioration de la composante finales de rois ;
- une boucle de plusieurs générations sur de la data finale a ensuite culminé puis régressé ;
- le problème avait été diagnostiqué comme un conflit de phase / mélange des objectifs, et non comme une saturation certaine de la classe linéaire.

Conclusion : **« plus de tours » n’est pas automatiquement meilleur**. Une boucle doit avoir :

- des trajectoires réellement plus fortes ;
- des labels propres ;
- un corpus avec turnover suffisant ;
- des gates de force générale et de conversion séparés ;
- un arrêt automatique dès que la conversion ou la force générale régresse.

### 1.5 Les anciennes pistes à ne pas rouvrir telles quelles

Ces pistes ont déjà produit un verdict négatif ou non transférable :

- simple augmentation de volume avec le même pilote ;
- pondération générale des lignes de finale ;
- approfondissement du champ `score` sans modifier les coups réellement joués ;
- MTC/proxy comme cible graduée de masse ;
- préférences humaines positives fittées directement ;
- ensemencement statique par combinaisons ;
- anchor plus serré ;
- changement de logit-scale comme levier principal ;
- répétition statique du gymnase.

Elles peuvent servir comme outils secondaires ou métriques, mais ne doivent pas être présentées comme la prochaine solution principale.

---

## 2. Pourquoi le WDL seul apprend mal la conversion

Le pipeline actuel propage le résultat final de la partie à toutes les positions visitées :

- victoire : `WIN` pour le camp qui finira gagnant ;
- nulle : `DRAW` ;
- défaite : `LOSS`.

Cette cible est utile pour apprendre une value-function globale, mais elle est très peu informative sur la conversion.

### 2.1 Cible plate dans les positions gagnantes

Les positions suivantes peuvent toutes recevoir `WIN` :

- gain immédiat et forcé ;
- gain conservé mais difficile ;
- gain qui demande 40 coups précis ;
- position dans laquelle une majorité des coups jettent le gain mais où un seul coup gagne.

La loss WDL ne distingue pas la proximité de conversion ni la robustesse du gain.

L’ancienne tentative MTC voulait créer ce gradient dans la cible. Elle a échoué car le signal MTC réellement gradué était extrêmement rare et le proxy dominait. La leçon correcte est de ne pas fabriquer un pseudo-gradient global, mais d’exploiter les **comparaisons locales objectives entre coups**.

### 2.2 Absence de crédit d’action

Considérons une trajectoire :

- parent `P` : l’oracle dit `WIN` ;
- Jass joue `m_bad` ;
- enfant `C_bad` : l’oracle dit `DRAW`;
- la partie termine nulle.

Le relabel profond peut corriger les valeurs de `P` et `C_bad`. Mais le fit WDL ne voit pas forcément le bon coup `m_good` qui aurait conservé `WIN`. Il doit reconstruire indirectement cette information à partir d’autres parties.

Le signal qui manque est explicite :

`value(C_good) > value(C_bad)` depuis le POV du parent.

Cette paire est beaucoup plus informative que quatre copies de `P` étiquetées `WIN`.

### 2.3 La conversion est une propriété de trajectoire

Une bonne technique de conversion consiste notamment à :

- préserver le verdict gagnant ;
- réduire les ressources de nulle ;
- éviter les répétitions et les régimes de 25 coups ;
- pousser vers une tranche de tablebase ;
- choisir des positions où la recherche future dispose de coups gagnants robustes ;
- parfois préférer un gain plus simple à un gain théoriquement équivalent.

Ce savoir ne se résume pas à la valeur statique d’une position isolée. Pour l’enseigner à une évaluation linéaire, il faut au minimum lui fournir des **contrastes d’enfants** observés sur des parents critiques.

---

## 3. Réponse à la question « faut-il enchaîner les boucles ? »

### 3.1 Oui, mais seulement comme expérience courte et instrumentée

La prochaine expérience logique est une campagne T1→T2→T3. Son but n’est pas de supposer que l’auto-amélioration finira forcément par marcher, mais de répondre à une question précise :

> Un pilote légèrement moins corrompu grâce aux labels d14+EGDB produit-il, au tour suivant, des trajectoires assez meilleures pour que la conversion commence à monter ?

Trois tours suffisent pour voir la direction. Il ne faut pas engager une campagne longue avant ce signal.

### 3.2 Conditions obligatoires de la boucle

Chaque tour doit :

1. partir du champion promu au tour précédent ;
2. générer une fraction significative de corpus frais ;
3. jouer les finales plus profondément que le milieu ;
4. utiliser EGDB pour terminer les parties dès qu’une tranche exacte est atteinte ;
5. relabelliser les positions par d14+EGDB ;
6. conserver un témoin de conversion figé et indépendant ;
7. comparer directement `champion_k` à `champion_{k-1}` ;
8. arrêter si la force générale ou la conversion régresse.

### 3.3 Proposition de profondeur

Point de départ raisonnable, à adapter aux débits mesurés :

```text
opening / midgame : d10
late-midgame      : d12
endgame           : d16
deep-eg           : d18 ou résolution EGDB
```

Le point important est d’approfondir les **coups joués**, pas seulement le champ de score de chaque enregistrement. La documentation historique du moteur a déjà établi que `--play-depth-by-phase` est le levier utile pour améliorer la vérité des issues de finale.

### 3.4 Point de départ recommandé

Utiliser comme T0 la recette de type `adjudW0` :

- bootstrap matériel-conscient ;
- corpus généraliste ;
- labels d14+EGDB ;
- pas de multiplication statique agressive du gymnase au premier test.

Le gymnase peut rester comme source de départs, mais sa part doit être pilotée en **nombre de positions produites**, pas seulement en nombre de parties.

---

## 4. Brique de développement principale : `conversion_teacher`

## 4.1 Objectif

Construire un pipeline qui mine automatiquement les décisions où Jass abandonne ou fragilise un gain, puis produit des paires d’entraînement compatibles avec `rank_finetune.py`.

Exemple :

```text
parent P : oracle(P) = WIN
move choisi par Jass       -> C_bad  : oracle(C_bad)  = DRAW
meilleur move alternatif   -> C_good : oracle(C_good) = WIN

paire d’apprentissage : C_good > C_bad
```

Le signal est objectif et local. Il n’enseigne pas « jouer comme un humain » ni « jouer comme Scan » ; il enseigne « conserver le verdict gagnant ».

## 4.2 Oracle hiérarchique

Pour chaque parent et chaque enfant légal :

1. **EGDB exact** si la position est dans la tranche disponible ;
2. sinon **recherche d14/d16 avec EGDB aux feuilles** ;
3. rejeter les cas instables ou ambigus.

Au-dessus de la tablebase, d14+EGDB n’est pas une vérité mathématique. Le pipeline doit donc distinguer :

- `EXACT` : verdict EGDB ;
- `STABLE_SEARCH` : même verdict à deux profondeurs ou avec marge suffisante ;
- `AMBIGUOUS` : rejet.

Proposition de règle initiale pour les positions >7 pièces :

- évaluer à d12 puis d14 ;
- accepter seulement si le signe WDL est identique ;
- éventuellement exiger une marge minimale dans l’évaluation profonde ;
- rejeter les enfants dont le verdict oscille.

Le premier smoke peut être limité aux parents dont au moins un enfant est EGDB-exact afin de réduire le risque.

## 4.3 Détection des événements critiques

Le mineur doit analyser des parties de conversion jouées depuis des positions certifiées gagnantes.

Événements prioritaires :

### A. Jet direct du gain

```text
oracle(parent) = WIN
oracle(enfant choisi) ∈ {DRAW, LOSS}
au moins un enfant alternatif = WIN
```

C’est le hard negative principal.

### B. Mauvais choix dans une position gagnante fragile

```text
plusieurs coups légaux
un petit sous-ensemble conserve WIN
le coup choisi conserve WIN mais entre dans une zone beaucoup moins robuste
```

À ne traiter qu’après le succès du cas A. Le premier pipeline doit éviter d’introduire un proxy de « simplicité » non validé.

### C. Gain non converti sans jet unique identifiable

Une partie peut rester théoriquement gagnante longtemps puis finir par répétition, 25 coups ou cap. Il faut retrouver le **premier ply** où le verdict profond passe de WIN à DRAW/LOSS. S’il existe, ce ply devient un exemple A. Sinon la partie est un stall sans faute locale nette et doit rester une métrique, pas un exemple de ranking.

## 4.4 Énumération des coups

Infrastructure réutilisable :

- `jass --dump-legal` pour les coups légaux ;
- `jass --gen-siblings --played-moves` pour produire les enfants/frères ;
- `--deep-relabel` pour noter des lots ;
- EGDB pour les enfants exacts.

Amélioration possible pour l’efficacité :

```text
jass --score-legal-children <parents.jnnw> <out.jnnw> \
     --depth 14 --egdb <path>
```

Ce nouveau mode C++ serait utile si le prototype Python devient trop lent, mais il n’est pas indispensable au smoke. Le prototype peut orchestrer les primitives existantes.

Important : ne pas exclure systématiquement les captures. Dans les dames, plusieurs séquences de prise obligatoires peuvent constituer une décision réelle de conversion. Il faut seulement exclure :

- les positions à un seul coup légal ;
- les paires où les deux enfants ont le même verdict et aucun signal secondaire fiable.

## 4.5 Format des paires

Réutiliser le contrat de `rank_finetune.py` :

- deux enregistrements JNNW consécutifs ;
- premier : enfant préféré ;
- second : enfant dominé ;
- même parent logique ;
- le champ `score` porte le STM du parent si `--leaf-pov` est utilisé ;
- le WDL peut porter le verdict oracle de l’enfant pour audit, même si la loss de ranking ne l’utilise pas directement.

Ajouter un sidecar JSONL ou Parquet léger pour l’audit :

```json
{
  "parent_fen": "...",
  "chosen_move": "31-27",
  "better_move": "32-28",
  "parent_verdict": "WIN",
  "better_verdict": "WIN",
  "worse_verdict": "DRAW",
  "oracle_better": "EGDB",
  "oracle_worse": "D14_STABLE",
  "game_id": "...",
  "ply": 63,
  "pieces": 9,
  "tier": "throw_win"
}
```

Le corpus binaire sert au fit ; le sidecar sert aux diagnostics et aux tests.

## 4.6 Déduplication et séparation train/validation

Dédupliquer par :

- bitboards du parent ;
- STM du parent ;
- enfant préféré ;
- enfant dominé.

Éviter les fuites :

- split par parent, jamais par paire isolée ;
- idéalement split par partie/graine ;
- le thermomètre de conversion et les 1600 positions d’évaluation doivent rester strictement hors entraînement ;
- exclure également les positions PC Blues utilisées comme jauge si elles sont dans le pool de départ.

Stratifier le holdout par :

- nombre de pièces ;
- présence de dames ;
- palier de conversion ;
- origine de l’oracle ;
- type d’événement.

## 4.7 Équilibrage

Ne pas laisser des milliers de variantes presque identiques d’une même finale dominer.

Limiter par parent :

- au maximum un ou quelques hard negatives ;
- choisir le meilleur enfant gagnant et le pire enfant réellement joué ;
- éventuellement un second enfant négatif si son mécanisme est distinct.

Échantillonner les catégories :

- 3–7 pièces exact EGDB ;
- 8–12 pièces transition TB ;
- 13–20 pièces late-mid/endgame ;
- homme(s) contre dame(s) ;
- dames des deux côtés ;
- matériel égal mais gain positionnel ;
- gains avec promotion ;
- gains menacés par répétition/25 coups.

## 4.8 Loss d’entraînement

### Première version recommandée : deux étapes

Pour isoler la causalité :

1. fit WDL adjudicated normal ;
2. rank-finetune conversion, ancré sur le candidat WDL.

C’est déjà supporté conceptuellement par `rank_finetune.py`.

Avantages :

- peu de code ;
- A/B propre ;
- mesure directe du gain apporté par le professeur de conversion ;
- rollback simple.

Attention : l’ancienne expérience de préférences humaines a amélioré la pairwise accuracy mais perdu beaucoup d’Elo. La pairwise accuracy interne n’est donc qu’un test de pipeline, jamais un critère de promotion.

### Deuxième version éventuelle : objectif joint

Si la version deux étapes montre un transfert réel, intégrer :

```text
L = L_WDL_generaliste
  + lambda_conv * L_rank_conversion
  + lambda_anchor * ||w - w0||²
```

Le joint training permettrait d’éviter que le fine-tune de ranking oublie la calibration globale. Mais il augmente la complexité et ne doit venir qu’après un smoke positif.

## 4.9 Fichiers proposés

Prototype minimal :

```text
jobs/tools/conversion_teacher.py
jobs/tests/test_conversion_teacher.py
jobs/queue/cpx62-XXXX-conversion-teacher-smoke.sh
```

Responsabilités de `conversion_teacher.py` :

- lire parties/FEN/moves ;
- interroger l’oracle par lots ;
- repérer le premier jet de gain ;
- énumérer et noter les frères ;
- écrire paires JNNW ;
- écrire manifeste et sidecar ;
- vérifier POV, ordre et verdicts.

Évolution possible :

```text
src/main.cpp
```

avec un mode batch de scoring des enfants si le coût de processus Python devient dominant.

Extension générateur :

```text
tools/scan_selfplay_gen.py
```

Options proposées :

```text
--conversion-events-out <jsonl>
--conversion-record-frac <0..1>
--conversion-oracle-depth 14
--conversion-egdb-dir <path>
```

Le générateur ne doit pas forcément faire tout le mining en ligne. Il peut émettre les trajectoires et laisser un job séparé construire les paires.

---

## 5. Deuxième brique utile : quota par positions, pas par parties

Le `seed_frac` actuel pilote une fraction de parties. Une finale est courte, donc une fraction élevée de parties de gymnase peut ne produire qu’une faible fraction des enregistrements.

Ajouter une cible du type :

```text
--conversion-record-frac 0.10
```

Le système continue de générer des parties de conversion jusqu’à ce que leur part réelle dans le JNNW atteigne la cible.

Garde-fous :

- compteur de positions, pas de parties ;
- plafond par position source ;
- dédup des positions uniques ;
- rapport `n_records`, `n_unique`, `n_games`, `mean_plies`;
- aucune duplication brute destinée seulement à gonfler la loss.

Cette brique seule ne résoudra probablement pas la conversion, comme le suggère `0722`. Elle devient utile lorsqu’elle alimente des trajectoires fraîches et des hard negatives.

---

## 6. MTC : rôle recommandé

### 6.1 Ne pas réutiliser MTC comme cible globale

Le run historique a montré que :

- le MTC réellement gradué couvrait très peu de positions ;
- le proxy dominait ;
- la métrique interne pouvait s’améliorer sans transfert Elo ;
- la cible a dégradé le moteur.

Cette voie reste fermée.

### 6.2 Utiliser MTC dans la recherche et comme métrique

Le moteur possède une intégration MTC dans le score terminal TB afin de préférer une conversion plus rapide. Cela peut :

- améliorer directement les play-outs dans la tablebase ;
- produire de meilleures trajectoires-professeur ;
- aider à distinguer plusieurs enfants tous gagnants dans un mode secondaire.

Action préalable :

- auditer les jobs L3 pour vérifier que `JASS_EGDB_MTC_PATH` est réellement défini ;
- valider MTC-on vs MTC-off sur un test de conversion exact ;
- ne pas confondre ce gain search avec un apprentissage de l’éval.

Dans le premier `conversion_teacher`, MTC ne doit pas décider des paires principales `WIN > DRAW`. Il peut servir plus tard à classer deux enfants `WIN`, après validation séparée.

---

## 7. Troisième piste conditionnelle : banque linéaire `DEEP_EG`

L’évaluation principale interpole deux banques MG/EG. Les expériences historiques ont montré un conflit :

- spécialiser la finale peut améliorer les métriques de finale ;
- le mélange complet peut sacrifier le milieu ;
- l’Elo général et certaines métriques de finale deviennent anti-corrélés.

Si le professeur de conversion produit de bons hard negatives, améliore la pairwise accuracy holdout et le win-preservation oracle, mais ne transfère pas en playout réel, la représentation peut manquer de séparation de phase.

Proposition entièrement linéaire :

```text
MG <-> EG <-> DEEP_EG
```

Activation possible :

- `DEEP_EG` à pleine force sous 8 pièces ;
- interpolation EG→DEEP_EG entre 12 et 8 pièces ;
- mêmes patterns ou uniquement extras ciblées selon coût.

Option plus prudente :

- garder les patterns MG/EG ;
- ajouter une banque `deep-eg` uniquement pour les extras ;
- commencer par king mobility, trapped king, proximité, promotion, contrôle de diagonales et ressources de nulle mesurables.

Cette piste ne doit être ouverte qu’après avoir testé le crédit d’action. Sinon on risque d’ajouter de la capacité sans signal de supervision adapté.

---

## 8. Plan expérimental recommandé

## Phase 0 — audit et gel des instruments

Avant nouveau calcul long :

- confirmer le SHA exact de `develop` et des outils L3 ;
- vérifier `--play-depth-by-phase` avec le binaire utilisé ;
- vérifier `terminate-at-TB`;
- vérifier `JASS_EGDB_MTC_PATH`;
- figer les 1600 positions de conversion ;
- figer le thermomètre PC Blues 224 ;
- vérifier absence d’intersection train/eval ;
- conserver PR #329 en pause, non supprimée.

## Phase 1 — boucle T2/T3 WDL adjudicated

### Bras unique initial

T0 = candidat `adjudW0` ou reconstruction exacte de sa recette.

Pour chaque tour :

```text
champion_{k-1}
  -> self-play frais, profondeur par phase
  -> terminate EGDB
  -> relabel d14+EGDB
  -> fit WDL
  -> conv fixe + direct match
  -> promotion conditionnelle
```

Volume de smoke :

- assez petit pour obtenir T1/T2/T3 rapidement ;
- mais mêmes paramètres et même fenêtre entre tours ;
- au moins 20–25 % de turnover réel si une fenêtre glissante est utilisée.

Ne pas ajouter quatre fois le même gymnase. Garder une couverture de départ de conversion raisonnable et mesurer la part réelle de positions.

### Gates

À chaque tour :

1. intégrité corpus ;
2. direct `champion_k vs champion_{k-1}`;
3. direct `champion_k vs T0`;
4. conversion sur positions identiques ;
5. thermomètre PC Blues ;
6. taux d’entrée TB et stalls ;
7. distribution des verdicts par phase.

Proposition de promotion exploratoire :

- pas de régression générale nette ;
- amélioration conversion positive et reproduite sur au moins deux métriques ;
- aucun échec d’intégrité ;
- si le résultat est ambigu, conserver l’artefact mais ne pas en faire le pilote du tour suivant.

## Phase 2 — smoke `conversion_teacher`

Construire 5k–20k paires de hard negatives.

Contrôles :

- 100 % des parents sont WIN selon l’oracle retenu ;
- 100 % des enfants préférés conservent WIN ;
- 100 % des enfants dominés sont DRAW/LOSS pour la v1 ;
- aucun parent à un seul coup ;
- POV validé sur un échantillon manuel et automatisé ;
- train/holdout disjoints par parent et partie.

Fit :

```text
baseline = candidat WDL adjudicated
candidate = rank_finetune(baseline, paires conversion)
```

## Phase 3 — A/B propre

Même baseline, même binaire, mêmes ouvertures :

- A : WDL adjudicated seul ;
- B : WDL adjudicated + rank conversion.

Mesures principales :

- match direct B vs A, au moins 1200 parties si le smoke passe ;
- conversion fixe appariée ;
- win-preservation one-ply sur parents holdout ;
- thermomètre PC Blues ;
- taux de stalls ;
- Elo général vs bootstrap ou champion courant.

## Phase 4 — combinaison avec T2/T3

Si B gagne :

- utiliser B comme pilote du tour suivant ;
- miner les nouveaux jets de gain du champion amélioré ;
- recréer les paires avec turnover ;
- refaire WDL + ranking.

Le curriculum devient alors :

```text
joue -> échoue à convertir -> oracle localise la faute
-> apprend le contraste -> rejoue mieux
```

C’est une véritable boucle d’apprentissage de conversion, contrairement à la répétition d’un gymnase figé.

## Phase 5 — banque `DEEP_EG` seulement si nécessaire

Déclencheur :

- pairwise holdout monte nettement ;
- win-preservation oracle monte ;
- mais playout conversion et match restent plats.

Cela signifierait que le signal est bon mais que la classe/phase actuelle ne l’exprime pas suffisamment.

---

## 9. Métriques et règles de décision

## 9.1 Métriques indispensables

### Force générale

- match direct contre le parent ;
- score et intervalle de confiance ;
- match cumulé contre T0.

### Conversion réelle

- `conv_fixed_wdl` sur le même témoin ;
- défenseur fixe ;
- mêmes positions et couleurs ;
- comptage des erreurs et des labels filtrés.

### Win preservation local

Sur parents holdout :

- proportion où le meilleur coup statique choisi par l’éval conserve WIN ;
- proportion sur les parents critiques ayant au moins un move qui jette ;
- regret de verdict :
  - `WIN -> WIN` = 0 ;
  - `WIN -> DRAW` = 1 ;
  - `WIN -> LOSS` = 2.

### Stalls

- partie gagnante qui termine nulle par répétition/25 coups/cap ;
- plies avant entrée TB ;
- part des parties où le premier jet de gain est identifiable.

### Généralisation tactique

- thermomètre PC Blues 224 ;
- strictement hors entraînement.

## 9.2 Ce qui ne suffit jamais à promouvoir

- baisse de train loss ;
- hausse de pairwise accuracy seule ;
- amélioration d’une métrique MSE finale ;
- hausse de score sur corpus d’entraînement ;
- un seul run conv de petit N ;
- un gain contre bootstrap sans contraste direct contre la baseline expérimentale.

L’expérience des préférences humaines montre explicitement qu’une pairwise accuracy en hausse peut accompagner une forte perte Elo.

## 9.3 Règles d’arrêt

Arrêter ou pivoter si :

- deux tours successifs n’améliorent pas la conversion ;
- la force générale régresse clairement ;
- la part de nouveaux événements critiques chute sans progrès ;
- le teacher apprend le holdout mais pas le playout ;
- les paires sont dominées par une seule famille de finales ;
- d14 et d16 sont trop souvent en désaccord au-dessus d’EGDB.

---

## 10. Tests demandés

## 10.1 Tests unitaires `conversion_teacher`

- parsing JNNW ;
- inversion correcte du POV ;
- parent WIN / enfant choisi DRAW ;
- sélection d’un frère WIN ;
- rejet parent à un seul coup ;
- rejet si aucun frère ne conserve WIN ;
- rejet des verdicts instables ;
- dédup ;
- split sans fuite ;
- ordre `[better, worse]`;
- champ `score` compatible `--leaf-pov`;
- captures multiples non rejetées arbitrairement.

## 10.2 Tests d’intégration

Petit jeu synthétique :

- quelques parents EGDB exacts ;
- résultats enfants connus ;
- génération des paires ;
- `rank_finetune.py` doit augmenter la pairwise accuracy ;
- round-trip PJTW chargeable par Jass ;
- `--eval-position` cohérent avec le calcul Python.

## 10.3 Smoke runner

Le job doit abandonner si :

- EGDB absent ;
- un shard oracle manque ;
- nombre de paires inférieur au minimum ;
- fuite train/eval ;
- POV gate < seuil ;
- enfant préféré non WIN ;
- enfant dominé non DRAW/LOSS dans la v1 ;
- candidate PJTW invalide ;
- match ou conv incomplet au-delà de la tolérance définie.

---

## 11. Risques techniques

### 11.1 d14 n’est pas exact au-dessus des TB

Ne jamais documenter `d14+EGDB` comme vérité absolue au-dessus de 7 pièces. Utiliser des niveaux de confiance et rejeter l’ambigu.

### 11.2 Biais vers les finales faciles

Si le corpus teacher vient surtout de positions proches de la TB, il peut apprendre à entrer dans la TB mais pas à convertir les transitions 12–20 pièces. Stratifier par nombre de pièces.

### 11.3 Oubli de la calibration globale

Un rank-finetune agressif peut améliorer les paires et détériorer le jeu. Commencer avec un lambda faible, plusieurs bras, et des gates généralistes durs.

### 11.4 Corrélation des paires

Des milliers de paires issues du même parent donnent une illusion de volume. Dédupliquer et limiter par parent.

### 11.5 Contamination des jauges

Les positions utilisées pour le thermomètre et `conv_self` doivent être interdites dans les seeds, le teacher et les paires.

### 11.6 Coût oracle

Noter tous les enfants à d14 peut coûter cher. Optimisations :

- filtrer d’abord les parents où le coup choisi semble jeter ;
- EGDB batch ;
- cache par hash de position ;
- d10/d12 screen puis d14 confirmation ;
- parallélisation par parent ;
- mode C++ batch seulement si nécessaire.

---

## 12. Points de revue demandés à Claude Code

Merci de challenger particulièrement :

1. **Hypothèse centrale** : le manque principal est-il bien le crédit d’action `preserve WIN > throw WIN`, ou une brique existante fournit-elle déjà ce signal de manière équivalente ?
2. **Réutilisation de `rank_finetune.py`** : le format des paires et le contrat `--leaf-pov` sont-ils correctement compris ?
3. **POV** : enfant, parent et STM sont-ils cohérents dans toutes les transformations ?
4. **Oracle** : quelle politique robuste pour combiner EGDB exact et recherche d14/d16 ?
5. **Premier jet de gain** : comment le localiser sans faire exploser le coût ?
6. **Captures multiples** : comment les conserver comme décisions réelles ?
7. **MTC** : est-il réellement actif dans les jobs actuels et peut-il améliorer les trajectoires sans contaminer la cible ?
8. **Profondeur par phase** : quelle recette minimale rentable sur cpx62/ccx33 ?
9. **Quota par enregistrements** : modification correcte de `scan_selfplay_gen.py` sans casser le sharding et les paires couleurs.
10. **Loss** : commencer par fine-tune séquentiel ou implémenter directement un objectif joint ?
11. **Gates** : seuils suffisants pour éviter une répétition de l’échec des préférences humaines.
12. **Représentation** : dans quelles conditions factuelles ouvrir la banque `DEEP_EG` ?
13. **PR #329** : la garder en pause comme outil de confirmation factorielle ; ne pas la confondre avec le teacher.
14. **Reproductibilité** : SHA des outils, corpus, seeds, manifests, ordre des shards, dédup et splits.
15. **Économie de calcul** : proposer un smoke qui tranche avant tout run long.

---

## 13. Conclusion finale

La conversion ne doit plus être abordée comme un simple problème de quantité de finales dans le corpus.

`0722` montre :

- **labels profonds : utiles et nécessaires** ;
- **gymnase statique ×4 : insuffisant à T1**.

La prochaine séquence rationnelle est :

1. lancer une courte boucle T2/T3 avec jeu de finale plus profond et labels d14+EGDB ;
2. développer en parallèle un `conversion_teacher` qui mine les jets de gain ;
3. entraîner l’éval sur des paires objectives `conserve WIN > jette WIN`;
4. promouvoir uniquement sur conversion réelle **et** non-régression générale ;
5. n’ajouter une banque linéaire `DEEP_EG` que si le signal de ranking est bon mais ne transfère pas.

La brique manquante n’est donc probablement pas une nouvelle boucle de self-play générique. Jass sait déjà générer, relabelliser et fitter. Ce qui lui manque est un mécanisme de **crédit causal du coup de conversion**.

C’est ce mécanisme qui peut transformer la boucle :

```text
ancienne boucle :
position gagnée -> partie nulle -> label global ambigu

boucle proposée :
position gagnée -> coup qui jette -> oracle localise la faute
-> frère qui conserve le gain -> paire de ranking
-> nouvelle eval -> nouvelle trajectoire
```

Cette voie reste intégralement compatible avec l’évaluation linéaire-patterns et avec la règle « aucun NNUE ».
