> ⚠️ **ARCHIVE — NE PAS PRENDRE COMME CONSIGNE ACTIVE.** Doc historique (ère pré-fit-volume / NNUE).
> Source de vérité unique = [CURRENT.md](../L3_CURRENT.md) (+ docs système : BOUCLE_VIRTUEUSE, SCAN_METHODOLOGY_GAP,
> DIAGNOSTIC_VS_SCAN, BIAIS_FIT_VOLUME, PROGRESSION_LITTERATURE). Conservé pour l'historique seulement. _(Classé archive 2026-06-24.)_

# Note de synthèse — optimisation de la génération de données (gen-data-wdl)

> Rédigée le 2026-05-23 (Claude exploration) après lecture du code
> (`src/main.cpp`, `src/search.cpp`, `src/engine.cpp`,
> `src/nnue_accumulator.{hpp,cpp}`). Sauvegardée ici le 2026-05-24 pour
> ne pas la perdre. Objet : que reste-t-il à optimiser dans le labelling
> depth-20, et que faut-il NE PAS optimiser.
> À lire avec `ANALYSE_VEILLE_NNUE.md`, `REFERENCES_BIBLIOGRAPHIE.md` et
> `ROADMAP.md`.

-----

## 0. Cadre — la question derrière la question

Le coût mesuré : **1M @ depth-20 = 138 h sur 4 vCPU = 2,0 rec/s** (job `0010`),
et **~×13 plus lent** quand le labelleur est le MLP v5 (pilote Cycle 9 `0025a`).

Deux axes distincts, à ne pas confondre :

- **(A)** rendre une recherche depth-20 plus rapide → quasi épuisé (voir §1).
- **(B)** générer le dataset moins cher sans toucher à la profondeur → il reste
  du vrai gain (voir §2). C'est là qu'il faut regarder.

**Mise en garde de priorisation (rappel de l'analyse) :** le meilleur réseau
actuel fait **0.009 vs Scan** (ELO ≈ −812). Optimiser le coût d'un run 10M
depth-20 pour un « v6 » marginal pendant que la force absolue est à ce niveau,
c'est peut-être optimiser une étape qu'il ne faut pas financer maintenant. Les
leviers ci-dessous sont classés en tenant compte de ça : **L1 vaut le coup même
si on réduit le volume self-play ; L2/L3 n'ont de sens que si on décide de faire
un gros run self-play.**

-----

## 1. Axe A — accélérer une recherche depth-20 : DÉJÀ FAIT (ne pas y retoucher)

### 1.1. Accumulateur NNUE incrémental — ✅ implémenté ET câblé

Le commentaire d'en-tête de `nnue_accumulator.hpp` **était périmé** au moment
de cette note (« fast path is a stub », « 1-2 weeks remaining »). Il dit la
réalité depuis PR #83 (2026-05-24). La réalité du code :

- `AccumulatorPair::apply_move` (nnue_accumulator.cpp) est **entièrement
  implémenté** : coups simples, captures (jusqu'à 22 changements), promotions,
  et changement d'ancre via `shift_anchor`.
- `search.cpp` l'utilise déjà : stack `AccumulatorPair[MAX_PLY+2]`,
  `refresh_from` à la racine, `apply_move` + repli `refresh_from` par nœud,
  `evaluate_with_accumulator` aux feuilles.
- → Le « ×13 » du MLP **n'est PAS** un défaut d'accumulateur. La couche 1 est
  déjà incrémentale. Le surcoût résiduel du MLP = couches 2-3 + sortie
  (non incrémentales par nature) + éventuels replis `refresh_from`.

**Action recommandée :** ~~corriger le commentaire d'en-tête de
`nnue_accumulator.hpp`~~ → fait en PR #83.

### 1.2. Reste de l'axe A — rendement décroissant

Search a déjà LMR, null-move, aspiration, TT. Ce qui resterait (tuning des
marges d'élagage, SIMD sur couches 2-3 du MLP, ProbCut) = travail d'expert
pour ~20-40%, pas un facteur. À depth-20 l'exponentielle domine. **Hors scope
pour un gain rapide.**

### 1.3. TT réutilisée entre positions — ✅ déjà optimal

`new_game()` vide la TT (engine.cpp:25) ; les `search()` successifs d'un même
game font `tt.new_search()` (incrément de génération), PAS de clear. Les
sous-arbres recouvrants des positions consécutives sont donc déjà amortis.
**Rien à gagner.**

-----

## 2. Axe B — générer moins cher : 2 leviers réels restants

### 🟢 L1 — Multi-extraction par arbre (LE gisement, facteur ~3-5)

**Constat (main.cpp, boucle gen-data-wdl).** Pour chaque ply échantillonné :

1. `e.search(eval_depth=20)` → ne sert qu'à produire **UN seul** `s.score`,
   puis l'arbre entier (centaines de milliers de nœuds) est jeté.
1. juste après, `e.search(play_depth)` → **deuxième** recherche pour choisir
   le coup joué. Donc un ply samplé = **deux** recherches.

**Optimisation (technique `gensfen` Stockfish).** Extraire plusieurs paires
(position, score) d'un même arbre depth-20 : typiquement le long de la PV
et/ou des premières variantes, avec leur score de sous-arbre. Amortir une
recherche sur 3-5 labels au lieu d'un.

**Gain :** ~×3 à ×5 sur le débit, **sans toucher à la profondeur ni dégrader
la qualité** des labels.

**Pourquoi c'est le meilleur levier :** il s'applique AUSSI à un petit dataset
depth-20 de qualité → il survit au scénario « on réduit le volume self-play et
on mise sur master games + qualité ». C'est le seul levier B à coder quasi
inconditionnellement.

**Points d'attention impl :**

- Éviter les positions trop corrélées (deux nœuds adjacents de la PV se
  ressemblent) → sous-échantillonner la PV, ou ne prendre que des positions
  espacées de ≥2 plies.
- Le score d'un nœud interne est en POV-STM de ce nœud : attention au signe
  (negamax) lors de l'écriture du record.
- Filtrer les positions de capture (voir L3) avant de les retenir comme label.
- Le format record actuel (32o bbs + 1o stm + 4o score + 1o wdl) est réutilisable
  tel quel ; seul le WDL de fin de partie devra être propagé aux positions
  extraites en cours d'arbre (ou laissé à 0 si la position n'est pas sur la
  trajectoire jouée — choix à trancher).

### 🟡 L2 — Budget en nodes plutôt que depth fixe (gain variable)

**Constat.** `lim.max_depth = eval_depth` (profondeur fixe). Sur position
tactique à fort branchement (rafles multiples, fréquentes aux dames), depth-20
explose en nœuds.

**Optimisation.** Limite en `nodes` (ou time) → budget constant par label :
positions calmes vont profond, positions touffues s'arrêtent au budget.
C'est ce que fait la référence Stockfish (`depth 9, nodes 5000` : les deux à
la fois). `SearchLimits` supporte déjà `movetime_ms` (vu dans search.cpp) ;
vérifier s'il existe une limite `nodes`, sinon l'ajouter.

**Gain :** borne les pires cas, coût plus prévisible et souvent plus bas à
qualité égale. Mais change légèrement la distribution des scores → **à
valider** (comparer val-loss / calibration avant-après).

**Risque :** modifie la sémantique du label. À tester sur petit échantillon
avant de l'adopter pour un gros run.

### 🟢 L3 — Filtrage des positions quiètes (gain coût + qualité) — DÉJÀ FAIT

**Status au 2026-05-24** : implémenté en PR #81 (flag `--quiet-only` dans
`run_gen_data_wdl_mode`). Job 0043-quiet-filter-experiment active en queue
runner pour valider empiriquement.

**Constat initial.** Aucun filtre : une position était samplée même si le STM
était en pleine rafle obligatoire. Or `generate_legal_moves(ml)` était déjà
appelé juste au-dessus du point de sampling.

**Optimisation.** Ne pas lancer la recherche depth-20 (ni retenir le label) si
une capture est forcée au trait. Coût d'ajout trivial.

**Double bénéfice :**

- **coût** : on n'use pas de recherche depth-20 sur des positions qu'on
  jetterait de toute façon à l'entraînement ;
- **qualité** : littérature unanime (arXiv 2412.17948, fil TalkChess nnue-pytorch,
  option `ensure_quiet` de Stockfish) — entraîner sur positions non-quiètes
  dégrade le réseau. Précédent direct : les nets nnue-pytorch sur 10M d5 non
  filtrés faisaient ~−700 ELO, corrigés par volume + filtrage quiet.

-----

## 3. Ordre d'implémentation recommandé

|Ordre|Levier                                       |Effort |Gain          |Statut au 2026-05-24            |
|-----|---------------------------------------------|-------|--------------|--------------------------------|
|1    |**L3 filtrage quiet**                        |trivial|coût + qualité|✅ PR #81, job 0043 en flight   |
|2    |**L1 multi-extraction**                      |moyen  |×3-5 débit    |🚧 en cours (claude/l1-multi-…) |
|3    |L2 budget nodes                              |faible |variable      |⏳ après L1 + verdict 0043      |
|—    |corriger commentaires/doc périmés (détail §4)|trivial|clarté        |🟡 partiellement (cf. §4)       |

**Mais avant tout ça (rappel analyse) :** le test **master-games → calibrate
vs Scan** est à coût de recherche nul (issue de partie réelle = label gratuit)
et dit si la branche self-play depth-20 mérite encore l'investissement. Si ce
test débloque la calibration, L1/L2/L3 deviennent secondaires ; s'il ne change
rien, le problème est l'architecture (patterns vs MLP dense — cf
`REFERENCES_BIBLIOGRAPHIE.md` axe 1) et aucune optimisation de gen ne le résoudra.

-----

## 4. Commentaires/doc à corriger (ne reflètent plus le code)

### 🔴 Priorité haute — `src/nnue_accumulator.{hpp,cpp}` — ✅ FAIT (PR #83)

L'en-tête entier décrivait l'accumulateur comme un échafaudage non câblé,
alors que `apply_move` est implémenté ET utilisé par `search.cpp`. Corrigé
2026-05-24.

### 🟡 Priorité moyenne — `docs/EXTENDING.md`

- **l.116-119** : `A real NNUE pipeline (sparse incremental updates, hidden layers, clipped-ReLU) requires more substantial framework changes — the single-layer LinearNetwork is the proof-of-concept...` → périmé. Le NNUE
  réel existe (`MLPNetworkQ` quantifié, couches cachées, accumulateur
  incrémental). `LinearNetwork` n'est plus « le » PoC mais une éval de repli
  parmi d'autres. Reformuler pour décrire l'état réel (plusieurs `INetwork` :
  Linear, MLP float, MLP quantifié + accumulateur, Pattern).
- **l.111-114** : l'instruction « swap the `evaluate(pos)` call … pour
  `evaluate_nnue(pos)` » décrit un câblage manuel qui ne correspond plus à la
  sélection runtime via `dynamic_cast<const MLPNetworkQ*>` dans `search.cpp`.
  À revoir si le reste de la section est mis à jour.

### 🟢 Priorité basse — `src/main.cpp`

- **l.232-236** : le commentaire de `eval_depth = 12` dit `bumped from 8 for the WDL pipeline: ~3-5× more compute per label`. → factuellement ok, mais
  l'`eval_depth` par défaut (12) **ne correspond pas** au dataset de référence
  `0010` qui a été produit à depth-20. Ajouter une ligne clarifiant que le 1M
  de référence est à 20, pas à la valeur par défaut.

### Note transverse

Le fait que ces commentaires soient périmés **dans le même sens** (sous-estiment
l'avancement) est cohérent avec ce qu'on a vu ailleurs : le projet est plus mûr
que ce que sa propre doc interne déclare. Quand Claude Code planifie, **se fier
au code, pas aux blocs STATUS/TODO des en-têtes** tant que cette passe de
nettoyage n'est pas faite.

-----

## 5. Résumé en une phrase

Côté « recherche depth-20 plus rapide » il ne reste rien d'évident (accumulateur
+ TT déjà faits) ; côté « générer moins cher » il restait **filtrage quiet**
(fait, PR #81) et surtout **multi-extraction par arbre (×3-5)** — mais le
levier qui prime sur tous reste le test master-games à coût nul, qui décide si
on doit financer ce run depth-20 du tout.
