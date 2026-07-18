> ⚠️ **ARCHIVE — NE PAS PRENDRE COMME CONSIGNE ACTIVE.** Doc historique (ère pré-fit-volume / NNUE).
> Source de vérité unique = [CURRENT.md](../L3_CURRENT.md) (+ docs système : BOUCLE_VIRTUEUSE, SCAN_METHODOLOGY_GAP,
> DIAGNOSTIC_VS_SCAN, BIAIS_FIT_VOLUME, PROGRESSION_LITTERATURE). Conservé pour l'historique seulement. _(Classé archive 2026-06-24.)_

# Références utiles pour jass — bibliographie annotée

> Compilée le 2026-05-23. Sélection de publications et ressources techniques
> directement actionnables pour le projet jass (moteur de dames 10×10,
> éval NNUE/MLP, entraînement par self-play + master games).
> Chaque entrée indique POURQUOI elle est pertinente et CE QU'ON EN FAIT.
> À lire en complément de `ANALYSE_VEILLE_NNUE.md`.

Les références sont classées par axe de décision du projet, dans l'ordre où
elles devraient peser sur la priorisation.

-----

## Axe 1 — Architecture : patterns locaux vs MLP dense (LE point critique)

C'est l'hypothèse la plus lourde de conséquences de l'analyse : les moteurs
de dames/Othello les plus forts n'utilisent PAS un MLP dense global, mais une
somme de scores de **patterns locaux** (modèle linéaire sur features booléennes
de petites zones). jass utilise un MLP dense type échecs. Ces références
établissent la base théorique et empirique de l'alternative.

### [1] Michael Buro — "Improving Heuristic Mini-Max Search by Supervised Learning"

*Artificial Intelligence 134 (2002) 85–99.*
PDF : <https://www.sciencedirect.com/science/article/pii/S0004370201000935>

- **Quoi** : introduit GLEM (Generalized Linear Evaluation Model) — combine
  linéairement des conjonctions de features booléennes (patterns). C'est la
  fondation théorique de toutes les évals à patterns (Othello, puis dames).
- **Pourquoi pertinent** : Logistello a battu le champion du monde d'Othello
  6-0 en 1997 avec ~1,2 M de poids ajustés par régression linéaire sur
  **plusieurs millions de positions** labellisées par valeur minimax ou une
  approximation. Modèle exactement transposable aux dames : features = motifs
  de cases, poids = régression. Pas de couches denses.
- **À en faire** : c'est le blueprint si on teste une éval pattern-based dans
  jass. La leçon clé : l'extraction de features + fit linéaire bat un réseau
  profond à coût CPU égal, parce que « la connaissance tient dans la première
  couche ».

### [2] Fabien Letouzey — Scan (moteur de dames de référence = la cible)

Code : <https://github.com/rhalbersma/scan>
Explication patterns (Lidraughts blog) :
<https://lidraughts.org/blog/XQlZORAAACEA2knq/scan-learns-frisian-and-antidraughts>

- **Quoi** : Scan évalue en additionnant les scores de **16 carrés 4×4
  chevauchants** (vision locale du damier). C'est l'application directe de
  l'idée GLEM aux dames 10×10. Letouzey fournit aussi une version PST (faible)
  de l'éval — utile comme baseline.
- **Pourquoi pertinent** : c'est l'adversaire de calibration de jass (0.009 vs
  Scan). Comprendre *pourquoi* Scan est fort = comprendre ce qui manque à jass.
  Le code est GPL v3, lisible, et la structure pattern→poids→somme est
  directement étudiable.
- **À en faire** : lire `eval.cpp` de Scan pour voir la définition exacte des
  patterns 4×4 et le format des poids. Source d'inspiration n°1 pour une
  entrée pattern-based dans `src/nnue.hpp`.

### [3] World Draughts Forum — "NNUE" (Bert Tuyt et al., 2020)

<https://damforum.nl/viewtopic.php?t=8298>

- **Quoi** : taxonomie des approches d'éval pour dames/checkers par des auteurs
  de moteurs. Classe explicitement : **Patterns** (Scan, Kingsrow, Maximus =
  les plus forts) > Raw board + FC (GuiNN) > NNUE KP type échecs.
- **Pourquoi pertinent** : confirme par des praticiens du domaine que le NNUE
  dense « échecs » n'est PAS l'état de l'art en dames. Mentionne la
  factorisation (KP + K + P) comme amélioration.
- **À en faire** : argument externe pour justifier de tester l'archi patterns
  avant de continuer à investir dans le MLP dense.

-----

## Axe 2 — Données : master games + filtrage de positions calmes

L'analyse recommande de prioriser le Cycle 8 (master games Lidraughts) et de
filtrer les positions. Ces références appuient ce choix.

### [4] Wiering et al. — "Learning to Play Draughts using TD learning with NN and databases"

<https://www.academia.edu/3673337/>

- **Quoi** : TD-learning + NN pour les dames internationales, AVEC bases de
  parties. Résultat : l'entraînement sur **parties de bases de données** donne
  un meilleur jeu que le self-play contre un joueur faible ; niveau correct
  atteint en quelques heures.
- **Pourquoi pertinent** : validation empirique, sur LE jeu de jass, du point
  #2 de l'analyse (master games > self-play seul). Note aussi la difficulté
  spécifique de la **phase d'ouverture** pour les NN (peu de patterns, variance
  d'issue forte) — à garder en tête pour le mix dataset.
- **À en faire** : justifie d'activer `0014-fetch-master-games` + entraînement
  WDL-dominant AVANT le run 10M self-play.

### [5] "Study of the Proper NNUE Dataset" — arXiv:2412.17948 (2024)

<https://arxiv.org/pdf/2412.17948>

- **Quoi** : méthodologie dédiée à la *construction* du dataset NNUE (sujet mal
  documenté ailleurs). Insiste sur : sélectionner des positions **quiètes**,
  filtrer les positions bruitées/tactiquement instables (forks, captures,
  menaces), partir de parties de maîtres + self-play multi-moteurs.
- **Pourquoi pertinent** : jass échantillonne ~1 ply/4 sans filtre de quiétude
  explicite côté `gen-data-wdl`. Or « collecter des paires position/score
  aléatoires donne un entraînement sous-optimal ». C'est un levier qualité
  gratuit (filtrage), orthogonal à la profondeur.
- **À en faire** : ajouter un filtre « position calme » (pas de capture
  obligatoire au trait) au sampler de `run_gen_data_wdl_mode`, et/ou ne
  sampler que des positions post-quiescence.

-----

## Axe 3 — Ingénierie NNUE : ce que jass fait déjà bien, et les pièges connus

### [6] Stockfish nnue-pytorch — docs/nnue.md (la référence d'ingénierie)

<https://github.com/official-stockfish/nnue-pytorch/blob/master/docs/nnue.md>

- **Quoi** : la doc canonique NNUE — accumulateur incrémental, quantification
  int8/int16, topologie « wide & shallow », formulation de loss avec lambda
  (blend eval/résultat), scaling.
- **Pourquoi pertinent** : (a) valide le `nnue_accumulator.hpp` en chantier
  dans jass (le schéma deux-accumulateurs/HalfMen est l'analogue correct du
  HalfKP deux-perspectives) ; (b) la formule de loss lambda-blend est
  exactement celle de `train_v3.py` — bon signe, jass est aligné.
- **À en faire** : référence pour finir l'accumulateur incrémental (le fast
  path `apply_move` encore en stub) et pour la quantification.

### [7] Stockfish wiki — "Training datasets" (LE point sur depth vs volume)

<https://github.com/official-stockfish/nnue-pytorch/wiki/Training-datasets>

- **Quoi** : « de meilleures évaluations ne donnent pas toujours de meilleurs
  résultats — compromis qualité/apprenabilité ». Dernier bon dataset self-play
  Stockfish = **16 milliards de positions à depth 9**. Ordre de
  datasets : d'abord Stockfish (depth 9, nodes 5000), PUIS retrain sur données
  Lc0.
- **Pourquoi pertinent** : tranche directement le débat « depth-20 + 1M » de
  jass. La pratique de référence est volume énorme + depth faible, pas
  l'inverse. Et l'ORDRE des datasets compte (curriculum).
- **À en faire** : argument pour ne PAS financer le 10M @ depth-20, et pour
  envisager un curriculum (self-play léger d'abord, master games ensuite).

### [8] Stockfish wiki — "Basic training procedure" + smart fen skipping

<https://github.com/official-stockfish/nnue-pytorch/wiki/Basic-training-procedure-(train.py)>

- **Quoi** : ~400 époques pour maturer un net (compétitif dès ~100) ;
  `--random-fen-skipping` et le « smart fen skipping » (sauter les positions
  non-quiètes) ; comparaison d'archis via la val-loss (en gardant dataset +
  loss fixes).
- **Pourquoi pertinent** : `train_v3.py` compare déjà plusieurs archis à
  dataset/HP fixes — méthodo correcte. Le fen-skipping est le pendant pratique
  du filtrage [5].
- **À en faire** : implémenter un skipping de positions non-quiètes ; vérifier
  le nombre d'époques (si jass tourne court, sous-entraînement possible).

### [9] TalkChess — "Pytorch NNUE training" (fil de dev, pages 2 & 6)

<https://talkchess.com/viewtopic.php?t=75724&start=10>

- **Quoi** : journal de bord du développement de nnue-pytorch. **Anecdote
  cruciale** : leurs premiers nets sur « 10M parties d5 » ont donné **~−700
  ELO** (désastreux), corrigé en passant à ~256M positions + en n'entraînant
  que sur positions quiètes (option `ensure_quiet`). Discussion q'search à
  l'inférence et factoriseur.
- **Pourquoi pertinent** : c'est *presque exactement* la situation de jass
  (−812 ELO vs Scan). Le forum montre que ce trou ELO vient typiquement de
  (a) volume trop faible et (b) positions non-quiètes, PAS de la profondeur
  des labels. Précédent empirique très proche.
- **À en faire** : prioriser volume (master games) + filtrage quiet ; surveiller
  que la position évaluée à l'entraînement correspond bien à une position
  calme (comme le qsearch de jass aux feuilles).

-----

## Synthèse : ce que la bibliographie dit de faire, dans l'ordre

1. **Filtrage quiet (gratuit, fort)** — [5][8][9] : ne sampler/entraîner que
   sur positions sans capture obligatoire. Précédent direct du −700→OK.
1. **Master games + volume** — [4][7][9] : signal WDL réel, zéro coût de
   recherche, valide spécifiquement en dames par [4]. Calibrate-vs-Scan ensuite.
1. **NE PAS** financer 10M @ depth-20 — [7] : la référence est volume↑/depth↓.
1. **Tester l'archi patterns** — [1][2][3] : si après 1+2 le plafond tient,
   c'est l'archi (MLP dense vs patterns locaux à la Scan) qu'il faut changer.
   C'est le seul levier susceptible de combler un trou de ~800 ELO.

> Lecture honnête : [1][2][3] convergent fortement vers « l'archi est le
> plafond probable ». Mais 1 et 2 sont nettement moins chers à tester et
> peuvent déjà déplacer l'aiguille — d'où l'ordre. À valider empiriquement,
> pas à croire sur parole.

-----

## Notes de fiabilité

- [1][4][5] sont des publications (revue / arXiv). [2] est du code + billet de
  blog officiel Lidraughts. [3][9] sont des forums d'auteurs de moteurs :
  fiables sur le plan technique mais ce sont des témoignages de praticiens, pas
  du peer-review — à pondérer comme tels.
- Le chiffre « 16 milliards depth 9 » [7] et « −700 ELO sur 10M d5 » [9] sont
  spécifiques aux échecs ; l'ordre de grandeur transfère aux dames avec
  prudence (espace d'états plus petit, mais règle de prise obligatoire qui rend
  la quiétude encore plus déterminante).
