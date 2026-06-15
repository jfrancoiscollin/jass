# jass — feuille de route post-bibliographie

> 🧭 **Décision en cours → voir [ARBRE_DECISION.md](ARBRE_DECISION.md)** (arbre
> vivant : quel chemin selon quel verdict ; branches élaguées vs à explorer) et
> [JOURNAL_DE_BORD.md](JOURNAL_DE_BORD.md) (ancres + faits établis). Ce
> document-ci est la feuille de route *historique* (2026-05-24).

> ⚠️ **AVERTISSEMENT 2026-06-06 — chiffres « vs Scan d10 » INVALIDÉS.** Les
> mentions de **0.870 / +330 vs Scan d10** (« meilleur score vs Scan jamais »,
> « bottleneck = vitesse d'inférence, éval déjà bonne ») reposent sur une
> mesure **fausse** : bug de buffer dans `tools/calibrate_vs_scan.py` →
> Scan forfaitait en depth-fixe → Jass gonflé (46/54 forfaits, job 0137).
> Le raisonnement « speed-first » (éval supérieure à prof. égale, il suffit
> d'accélérer) est donc **non prouvé**. Bug corrigé ; vraie mesure par le
> **job 0139**. Le **vs Scan en movetime** (north-star −685 ELO) et les
> benchmarks internes restent valides.

> Rédigé le 2026-05-24. Supersede l'ordering de `PATTERN_ROADMAP.md` à la
> lumière de la bibliographie annotée `docs/REFERENCES_BIBLIOGRAPHIE.md`.
> À lire en complément de `ANALYSE_VEILLE_NNUE.md` (motivation) et
> `SESSION_LOG_2026_05.md` (ce qui a été testé jusqu'ici).

---

## Méthodologie — plan d'expérience (adopté 2026-06-12)

> Pourquoi : 0203/0204 ont conclu sur du **bruit** (benches 18 parties, ±0.08) et
> des **facteurs confondus** (replay buffer changé en même temps que la boucle
> continuée). On adopte une discipline de plan d'expérience pour ne plus.

**Puissance d'abord.** Le taux de victoire a une variance binomiale
`σ = √(p(1−p)/N)`. Pour résoudre un écart Δ de win-rate :
`N ≈ (2·1.96·√(p(1−p))/Δ)²`. À p≈0.1, Δ=0.05 → **~550 parties**. En-dessous, on
mesure du bruit. **Toujours fixer l'effet minimal détectable AVANT de lancer.**

**Pilier 1 — réponse à faible variance.**
- *Courbe d'apprentissage* (cheap, déterministe) : **`tools/eval_proxy.py`** —
  accord de l'eval avec une référence forte (Scan-d10/champion) sur un **set
  FIXE** de positions (Spearman/Pearson/sign des scores). Pas de bruit de
  parties ; haute résolution. ⚠️ mesure la *proximité d'eval*, pas la force de
  jeu — à valider contre 2-3 ancres (handcrafted/champion/v15).
- *Jalons absolus* (force réelle) : **`tools/sprt_elo.py`** — Elo ± IC 95 % et
  **SPRT** (test séquentiel façon fishtest : décide « A > B » au minimum de
  parties, erreurs α/β contrôlées). Openings fixes (blocking), couleurs
  équilibrées, IC **systématique**.

**Pilier 2 — design des facteurs (sans confusion).**
- Facteurs : profondeur de jeu, volume/gen, seed, replay buffer, l2, nb de gens.
- **Plan fractionnaire / screening** (Plackett-Burman) plutôt que OFAT → effets
  principaux + interactions sans confondre, en peu de runs (évalués au proxy).
- **Réplication** (seeds RNG) pour la variance run-to-run ; pour la boucle
  (autocorrélée) répliquer des **lignées entières**.

**Pragmatique (budget 1 box).** 1) corriger la mesure (proxy + SPRT) ; 2) petit
screening sur les facteurs au proxy ; 3) confirmer les gagnants par SPRT en
parties. PAS de gros factoriel répliqué.

**Set de référence canonique** : `0141-pattern-reeval/.../master-clean-scan-d10.jnnw`
(scores Scan-d10). Évaluer les eval sur un **sous-ensemble tenu à l'écart** de
leur training pour éviter la fuite.

**Règles ajoutées (2026-06-14).**
- **Sélection de modèle = val-loss ; verdict = parties.** Le proxy est **retiré**
  comme juge de force (B4/0216 : il sous-lit). Pour un fit de régression (distillation),
  choisir l2/variante par la **val-loss** de `train.py` (gratuite, déterministe), pas
  par le proxy ; trancher la force par **Elo réel** (vs hc / vs Scan).
- **TOUJOURS borner les matchs vs Scan au movetime, jamais en profondeur fixe non
  plafonnée.** Notre éval pattern est lente ; un match `--depth N` peut partir en
  recherche interminable sur une position de milieu (`0235` : **figé ~8h** sur l'arme
  d9, jamais fini). Utiliser `--movetime` (+ `--pairs` modeste). NB `calibrate_vs_scan`
  joue **9 ouvertures × pairs × 2** parties → `--pairs` multiplie par ~18.
- **⚠️ UNITÉS movetime — incohérentes entre outils, source du hang `0237`/`0243`** :
  `calibrate_vs_scan.py --movetime` est en **SECONDES** (0.5 = 0.5 s/coup) ; mais
  `jass --depth-at-movetime <ms>` et le HUB `go movetime <ms>` sont en **MILLISECONDES**.
  Passer `--movetime 500` à calibrate (en pensant ms) = **500 s/coup ≈ 16 h/partie**, 0
  partie finie, log à 0 octet (gaspillage 4 h). **Garde-fou ajouté (2026-06-14)** :
  calibrate refuse `--movetime>30` (`--allow-long-movetime` pour forcer). Pour Scan :
  toujours **`--movetime 0.5` ou `1`** (secondes).
- **Annulation d'un job** : poser `jobs/state/kill-in-flight` (le runner tue l'in-flight).
  Flag **global** (consommé par la 1ʳᵉ box qui le lit) → n'armer que quand les autres box
  n'ont rien de précieux en cours ; re-armer (« rounds ») si besoin.
- **Géométrie reset-proof** : le runner reset le tree vers main en cours de job. Pour une
  géométrie/variante non committée, l'épingler hors du tree (`JASS_PATTERNS_DIR` pour
  train.py) ; le binaire (compilé) survit au reset, seul `patterns.py` est réverti.

**Règles ajoutées (2026-06-15, campagne 0254-0263).**
- **Vérifier le SIGNAL d'entraînement AVANT d'ajouter un levier.** La boucle self-play
  s'entraîne sur le **WDL** (résultat), pas le `score`. La moitié de la campagne finale a
  buté là-dessus : `--label-depth-by-phase` (approfondit le score, inutilisé) = no-op nocif,
  `--phase-weight` = mort. Toujours tracer le levier jusqu'à la **cible de loss** réelle.
- **Tester ISOLÉ, jamais combiné.** Le combiné « NMP+LMP+LMR off » washait à +2 (le +29 du
  NMP masqué par le −13 du LMR) ; isolé, chaque mécanisme se lit. Un facteur par A/B.
- **La RECHERCHE est un levier de 1er plan** (révise le « recherche = close ») : NMP net-négatif
  = +97 Elo (3× la brique rois +37). Re-tuner les features gated par A/B, pas les présumer bonnes.
- **Ablation systématique d'une régression** : isoler par re-entraînement sur la MÊME donnée
  (0257 phase-weight, 0258 lowmem) avant d'accuser un facteur. Cheap, décisif.
- **Confirmer une cadence avant de figer un défaut search structurant** : un gain mesuré à
  mt0.2 peut être TC-dépendant (le bénéfice de profondeur de NMP grandit avec le temps) →
  re-A/B à mt0.5 avant d'adopter (`0262`).

### RÉVISION (2026-06-13) — le proxy MENT, l'Elo réel devient la mesure primaire

Le job **0216 (B4)** a montré que le proxy (accord-score vs Scan-d10) **SOUS-LIT
la force réelle** : la boucle WDL a gagné **+80 Elo réels** (gen0→gen5, parties vs
handcrafted, IC disjoints) pendant que le proxy STAGNAIT à ~0.43. Tous les « murs »
mesurés au proxy (data, profondeur, rois) étaient des **artefacts de mesure**.
Conséquences pour le plan d'expérience :
- **Mesure primaire = Elo RÉEL** vs un adversaire commun pas cher (le handcrafted,
  via `jass --benchmark-scan-eval <eval.pjtw> hc <depth> <pairs>`), + SPRT/Elo
  (`tools/sprt_elo.py`). Jalon absolu = vs Scan à profondeur égale
  (`calibrate_vs_scan.py`).
- **Le proxy reste un co-indicateur** (cheap, déterministe) mais NE tranche PLUS un
  verdict de force — il plafonne là où un eval STATIQUE peut s'accorder avec une
  recherche d10, pas où la force de jeu plafonne.
- **Design A/B « échelle » (adopté pour la symétrie)** : N bras IDENTIQUES (même
  boucle WDL cumulée, même data/profondeur, `--prune`) ne différant QUE par le
  facteur testé (men-only vs `--color-fold` vs `--rot-fold` vs `--trans-fold` vs
  `--full-fold`), chacun mesuré en **Elo vs hc par génération** → trajectoires
  directement comparables. L'adversaire commun rend le facteur isolé. C'est un
  OFAT propre sur un facteur structurel, répliqué en lignées.
- **Gauge de la couverture** : `tools/bucket_coverage.py` (Chao1 + accumulation)
  pour dimensionner la data ; `tools/bucket_census.py` pour l'élagage dense.

### JALON — Optimisation de la GÉOMÉTRIE (sélection de patterns, après l'A/B symétrie)

Le repliement par symétrie densifie les POIDS ; ce jalon trouve les bonnes FORMES
(nb/placement de patterns) → géométrie LEAN = moins de lookups (eval plus rapide,
vers la légèreté de Scan) SANS perdre d'Elo. Évite de copier Scan : on optimise pour
NOTRE data.
- **Outil** : `tools/pattern_importance.py` (livré) — par pattern (ou par orbite de
  symétrie) sur un set tenu à l'écart : `std(c_p)` (combien il bouge l'eval),
  `corr(c_p, ref)` (alignement avec Scan-d10/WDL), redondance `max|corr(c_p,c_q)|`.
  Range par `std·|corr|`.
- **Méthode** : (1) entraîner la géométrie pleine (foldée) ; (2) classer ; (3) élaguer
  la queue ; (4) ré-entraîner + **valider en Elo** (RFE récursif → trouver le GENOU =
  set minimal qui garde l'Elo). Alternative one-shot : **group-lasso** (L1 sur la norme
  du bloc de chaque pattern → sélection éparse en un seul train).
- **Caveats** : importance dépend de l'eval entraîné (itérer / group-lasso) ;
  redondance (patterns corrélés → forward-selection) ; **l'Elo tranche**, pas le score
  d'importance (discipline B4). Résout quantitativement la question 32-vs-54 patterns.
- **Séquencement** : APRÈS que l'A/B symétrie (0220-0226) confirme que le fold lève l'Elo.

### VERDICT GÉOMÉTRIE (2026-06-14) — ✂️ levier MORT, on passe aux rois + data

Le jalon géométrie est **clos, négatif**, sous 3 angles convergents :
- **importance UNIFORME** (`0230`) : aucun pattern mort, redondance ≤ 0.40 ;
- **élaguer = lose-lose** (RFE `0234`, drop-8 → 24 pat) : **−31 Elo ET 0 gain de
  vitesse** (knps 0.653→0.648) — la lenteur d'eval est dans les **106 extras**, pas
  les lookups de patterns ;
- **richesse géométrique inutile sous labels parfaits** (`0239`) : val-loss PLATE
  (0.600–0.617) de **15 à 54 patterns**.

→ Le morceau manquant n'était NI la géométrie NI (seulement) la data, mais **les ROIS** :
nos patterns étaient men-only (une case à roi = vide) alors que **Scan compte un roi
comme « pièce »** — une *divergence* avec Scan, pas une limite de la classe. **Brique
rois** codée (`-DJASS_KING_PATTERNS=ON` + `train.py --king-patterns`, base-3 men|kings,
= Scan, 100 % linéaire) et **validée `0240` : +37 Elo vs hc**. **Le push courant** = loop
full-fold **king-aware + scalé** (`0241`, 600k/gen) pour pousser la classe LINÉAIRE à
son max (kings + couverture). Toujours **sans pivot non-linéaire** (directive).

### VERDICT FINALES (2026-06-14) — densification à DEUX fronts (éval + recherche)

Deux diagnostics ont localisé puis caractérisé le saignement en finale (autopsies
`0249`/`0250` : ouverture/milieu ≈Scan perte ~0.05, finale à rois ~3.6) :
- **`0251` (plafond de classe par phase)** : sur labels Scan-d10 **parfaits**, la classe
  linéaire king-aware **RANGE bien la finale** (spearman 0.73–0.79, sa meilleure phase).
  → **PAS class-limited** ; notre éval self-play est juste **mal entraînée** en finale.
- **`0252` (éval vs recherche)** : la finale est **SEARCH-BOUND** — éval pure (depth-1)
  catastrophique (perte 7.25), la recherche profonde rattrape (mt2.0 = 1.71) ; deep-eg
  **plafonne** ~mt0.5 (plancher éval résiduel).

→ Levier = **densifier la finale sur DEUX fronts**, jamais de non-linéarité :
1. **éval** : labels profonds en finale (`--label-depth-by-phase endgame=12,deep-eg=14`,
   cf `0252`) + sur-pondération des lignes finale (`train.py --phase-weight`, cf `0251`) ;
2. **recherche** : finale search-bound → time-management/profondeur en finale, tuning
   LMR/LMP par popcount, et à terme **bitbases 3-4 pièces** (profondeur effective infinie).

**Tier-1 recherche (2026-06-14, `0253`)** : A/B des features codées-mais-OFF sur la
championne king-aware (mt0.2, 450 parties). `use_improving` = **+21.6 Elo** [CI
−10.5,+53.8] → **activé par défaut** (meilleur signal, standard +15-30 ; non SPRT-
significatif à ce budget mais cohérent). `use_conthist` = −11 → **laissé OFF**. Régime
recherche FINALE (popcount-gated NMP/LMP/LMR, `0255`) testé séparément sur CCX33.

**Régime recherche FINALE (2026-06-14, `0255`)** : A/B isolé des 3 mécanismes désactivés
sous 12 pièces. **`eg_no_nmp` = +29.4 Elo** [CI −2.8,+61.6] — LE plus gros signal search
de la session, confirme le zugzwang (l'assomption « passer est sûr » de NMP est fausse en
finale) → **activé par défaut** (`eg_pieces=12, eg_no_nmp=true`). `eg_no_lmr` = **−13**
(LMR achète la profondeur dont la finale search-bound a besoin → gardé ON), `eg_no_lmp` ≈ 0
(gardé ON). Le combiné « tout off » = +2.3 (washout) → **tester ISOLÉ était décisif** (le
+29 du NMP était masqué par le −13 du LMR). Suivi possible : balayer le seuil (8/14).

### VERDICT CAMPAGNE FINALES + RECHERCHE (2026-06-15, 0254-0263) — supersède la règle phase-weight ci-dessus

> **⚠️ La « RÈGLE `--phase-weight` » est CADUQUE — phase-weight est MORT.** La densif `0254`
> (`--phase-weight` + `--label-depth-by-phase`) a fait **−80 Elo** vs 0241. Ablations : `0257`
> innocente phase-weight, `0258` innocente lowmem → cause = la **donnée** (label-depth = no-op
> qui pollue la TT). Puis `0261` (distill score) : phase-weight = **−210 Elo** sur de BONS labels.
> → **`--phase-weight` et `--label-depth-by-phase`-en-boucle-WDL = cimetière.**

**Ce qui MARCHE / le plan vivant :**
1. **Levier finale (éval) = `--play-depth-by-phase`** : la boucle s'entraîne sur le **WDL**, donc
   on ne pondère pas et on n'approfondit pas le *label* — on **JOUE les finales profond** →
   WDL de finale fiables → la boucle apprend la finale. Boucle `0263` (= 0241 + play profond
   finale, sans phase-weight/label-depth). Cible : battre +229 ET val_endgame_mse bas. À valider
   à l'**autopsie** (perte finale < 3.6 de 0250) et **vs Scan**.
2. **Distillation sur SCORE** (`--target score`, PAS logistic) = **+141 vs hc** (> distill-WDL 0237
   +90) → bonne **source** de finale, sous le self-play. Blend éventuel (anchor anti-forget, banc
   EG vers distill / banc MG libre) si Chemin B insuffisant.
3. **Recherche = gros levier** : **NMP net-négatif en jass** (zugzwang omniprésent). Sweep
   `0256`/`0259` **monotone** → désactiver NMP = +97 à thr36 ; **confirmation `0262` à mt0.5 :
   thr40 (NMP OFF partout) = +106 Elo** [CI +67,+146], gain qui GRANDIT à cadence longue. →
   **NMP DÉSACTIVÉ PAR DÉFAUT** (`eg_pieces=40`). `use_improving` = +22. Tous déployés. Suite :
   re-tuner LMR/LMP/RFP **avec NMP off** (l'arbre a changé) + confirmer le combiné **vs Scan**.

**Leçons de méthode (→ plan d'expérience)** : (a) **vérifier le SIGNAL d'entraînement** (WDL vs
score) avant d'ajouter un levier — la moitié de la campagne a buté dessus ; (b) **tester ISOLÉ**,
jamais combiné (le combiné « NMP+LMP+LMR off » washait le +29 du NMP) ; (c) un **levier de search
peut valoir 3× un levier d'éval** (NMP +97 >> brique rois +37) — la recherche n'est PAS un domaine
clos.

---

## Point de départ — ce que la biblio recadre

`ANALYSE_VEILLE_NNUE.md` posait la thèse : l'archi MLP dense plafonne, il faut
basculer sur du pattern-based Scan-style. La biblio annotée confirme cette
thèse à long terme MAIS introduit deux directions cheap-and-fast à essayer
**avant** la bascule architecturale :

1. **[9] TalkChess** : précédent direct du syndrome jass (Stockfish a vu
   -700 ELO sur un dataset équivalent, fixé sans changer d'archi).
2. **[5] arXiv 2412.17948** + **[8] Stockfish nnue-pytorch wiki** : le fix
   en question est **filtrer les positions non-quiètes** au moment du
   sampling — quasi-gratuit à coder, validé empiriquement.
3. **[4] Wiering et al.** : pour les dames spécifiquement, master games
   battent self-play seul. Notre v5 les utilise déjà via BCE hybride mais
   le ratio est peut-être sous-optimal.

La conclusion révisée : avant d'investir dans l'axe pattern (Phase 1+ de
`PATTERN_ROADMAP.md`), épuiser deux quick-wins sur l'axe données.

---

## Plan d'actions — ordering révisé

### Phase 0 — Quiet filter dans gen-data-wdl  (LE plus haut ROI attendu)

**Hypothèse** : un échantillon ~1-ply-sur-4 sans filtre attrape beaucoup de
positions tactiques (capture obligatoire au trait), dont le label `score` est
trompeur (vrai score = après la rafle, pas celui que l'eval voit). Filtrer
ces positions = signal training plus propre = NNUE plus forte sans changer
ni l'archi ni le volume.

**Précédent biblio** : Stockfish nnue-pytorch est passé de **-700 ELO**
(« 10M parties d5 ») à compétitif essentiellement avec ce filtre + volume
[9]. arXiv 2412.17948 [5] décrit la méthodo. Smart fen skipping de Stockfish
[8] = même idée.

**Concrètement pour jass** :

1. Modifier `run_gen_data_wdl_mode` (`src/main.cpp`) : avant d'ajouter un
   sample, vérifier si `generate_legal_moves(pos)` retourne au moins une
   capture. Si oui (position tactique), **skip ce sample** et passe au
   prochain ply. Si non (position calme), record normalement.
2. Régénérer un corpus 100K-500K avec ce filtre (~5h-1 jour sur 1× CCX23).
3. Retrain `train_v3.py` avec le même recipe que 0018/v5.
4. Bench vs v5.

**Decision gate** :
- rate vs v5 d10 > 0.55 → quiet filter est LA réponse, généraliser et
  retrain sur volume complet.
- rate vs v5 d10 ∈ [0.50, 0.55] → léger gain, vaut le coup combiné avec
  Phase 0b (volume).
- rate vs v5 d10 ≈ 0.50 → quiet filter neutre, passer à Phase 0b.
- rate vs v5 d10 < 0.45 → régression inattendue, debug.

**Coût** : ~€1-2 (1 jour gen-data + retrain + bench).

**Code à écrire** :
- `src/main.cpp` : ~15-30 lignes (filtre de quiétude dans la boucle de
  sampling).
- `jobs/templates/0043-quiet-filter-experiment.sh` : pipeline complet.

### Phase 0b — Volume master games × 2-3

**Hypothèse** : Wiering et al. [4] valide pour les dames que les master
games portent un signal training fort. Notre `master-1600.jnnw` actuel a
~4.7M positions issues de 43K games Lidraughts ≥1600 ELO. Lidraughts produit
~30-150K nouvelles parties ≥1600/mois ; en re-fetch incrémental on peut
doubler ou tripler le corpus sur quelques semaines.

**Le cap `--max-master-records 2000000`** actuel limite l'utilisation à
2M même si on a plus. **MAIS** plus de records bruts = plus de diversité
dans le sampling de 2M, ce qui devrait améliorer la qualité du subset
échantillonné à chaque epoch.

**Concrètement** :

1. **Refresh hebdomadaire master games** : nouveau job
   `0044-refresh-master-data.sh` qui appelle `fetch_lidraughts_games.py`
   en incrémental + `pdn_to_jnnw.py` pour produire `master-1600-vN.jnnw`
   à jour.
2. **Activer le scraper FMJD** : compléter le probe 0024 (l'endpoint
   `fmjd.space/game_open.php` est identifié) pour ajouter ~5-10K games
   FMJD top-niveau au corpus. Effort ~1-2 jours code.
3. Quand `master-*.jnnw` a doublé : retrain jass v5 recipe, bench vs v5
   actuel. Si gain, le ratio master/self-play actuel est sous-optimal.

**Decision gate** :
- rate vs v5 d10 > 0.55 → volume master compte, continuer le refresh.
- rate vs v5 d10 ≈ 0.50 → le cap 2M est le vrai bottleneck (ou rien à
  gagner sur le ratio actuel). Passer à Phase 1.

**Coût** : ~€2-3 (training + bench). Scraping FMJD : 1-2 jours dev,
0 € compute si on est respectueux du serveur.

### Phase 1 — Pattern training fixes (anciennement Phase 1 de PATTERN_ROADMAP)

Si Phase 0 et 0b n'ont pas cassé le plafond, on passe à l'axe architecture.
Le détail est dans `PATTERN_ROADMAP.md` — résumé : améliorer `train_pattern.py`
avec warmup, lr schedule, L2 weight decay, augmentation par symétrie,
normalisation des scores. Re-train v2 et voir si rate vs v5 d10 dépasse 0.20.

### Phase 2 — Pattern self-play iteration (anciennement Phase 2)

Co-évolution façon Scan : auto-jeu, données générées, retrain, itérer. Voir
`PATTERN_ROADMAP.md` pour détail.

### Phase 3 — Scale up pattern set (anciennement Phase 3)

32-64 patterns ou patterns plus longs (12-16 squares). Voir `PATTERN_ROADMAP.md`.

---

## Pourquoi cet ordering est plus rationnel

Le doc de veille `ANALYSE_VEILLE_NNUE.md` arguait que l'archi était le plafond
probable. La biblio confirme cette thèse théorique MAIS introduit un précédent
empirique critique :

> Stockfish nnue-pytorch dev a cru à un problème d'archi (≈-700 ELO), a en
> fait diagnostiqué un problème de data preparation, l'a fixé avec un
> filtrage quiet, et est devenu compétitif.

C'est exactement le genre de piège dans lequel on pourrait tomber : passer
des semaines à reconstruire un pattern engine alors qu'une vingtaine de
lignes de C++ dans `--gen-data-wdl` font le job.

**L'ordering Phase 0 → 0b → 1 → 2 → 3** maximise le ratio gain/risque :
on dépense d'abord les fixes triviaux qui ont un précédent empirique,
on remonte vers les changements d'architecture seulement si nécessaire.

---

## Effort sequencing

| Phase | Effort code | Effort training | Effort wall total | Coût | Decision si succès |
|---|---|---|---|---|---|
| **0** quiet filter | 30 min C++ | ~1 jour gen + 1h train + bench | ~1-2 jours | ~€2 | Généraliser, retrain full volume |
| **0b** master volume | ~2 jours (fetch refresh + FMJD scraper) | 1h train + bench | ~3-7 jours wall (api rate-limited fetch) | ~€3 | Setup refresh continu |
| **1** pattern tuning | ~3-5h Python | 1h train + bench | ~1 semaine wall | ~€5 | Phase 2 |
| **2** self-play loop | ~5-10h C++/Python | 24-48h × 10 iter ~ 2-3 sem wall | 3-4 sem | ~€20-40 | Phase 3 |
| **3** scale up | ~5-15h | weeks | 1-2 mois | ~€50-100 | Ship as new default |

---

## Quick-wins indépendants (toujours activables en parallèle)

Inchangés depuis `PATTERN_ROADMAP.md` :

- Refresh continu master Lidraughts (Phase 0b couvre)
- Scraping FMJD (Phase 0b couvre)
- Améliorations du runner (cleanup branches obsolètes, etc.)

---

## Pistes paradigm shift dormantes

Si tous les axes cheap (data v8/v9 + pattern G1-G4-diag + H1-H4 + MLP
head v7) s'épuisent, le projet aurait besoin d'un paradigm shift pour
franchir le plateau. Cinq pistes capturées dans
[`docs/PARADIGM_SHIFT_OPTIONS.md`](PARADIGM_SHIFT_OPTIONS.md) :

| # | Piste | Effort dev | Coût compute |
|---|---|---|---|
| **(A)** | Pattern indices → embeddings dans MLP end-to-end | ~1j | ~€2 |
| **(B)** | MLPNetworkQ enrichi (HalfMen + features Scan) | ~1j | ~€5 |
| **(C)** | Convolution 2D sur le board | ~2-3j | ~€5-10 |
| **(D)** | AlphaZero-style MCTS + ResNet | ~2-3 semaines | ~€100-300 |
| **(E)** | Bigger MLPNetworkQ (1024-512) sur v8 dataset | ~30 min | ~€5 |
| **(F)** | MLPNetworkQ + têtes aux multi-tâches (force la représentation hidden) | ~3-5j | ~€5-10 |
| **(G)** | Distillation depuis Scan (eval direct, pas self-play) — **option dominante** | ~1-2j | ~€5-10 |

À reprendre quand : 0066 verdict tombe, ou G4-prod si tenté, ou tout
moment où l'axe data cesse de progresser.

---

## Plan A++ priorisé — small arch + SIMD optim (2026-06-03)

> Découverte 0090 transforme la stratégie. **128-64 Scan-distilled vs
> Scan d10 = 0.870** = notre meilleur score vs Scan jamais. À depth fixe,
> notre eval est SUPÉRIEURE à Scan. Le gap movetime est purement vitesse
> d'inférence, pas qualité eval.

### Verdict 0090

| Arch | vs Scan d10 | vs Scan mt500 | vs v8 mt500 |
|---|---|---|---|
| **128-64** | **0.870** | 0.028 | 0.528 |
| 192-96 | 0.111 | 0.019 | 0.537 |
| 256-128 | 0.083 | 0.019 | 0.565 |
| v11 1024-512 (réf) | 0.194 | 0.009 | — |

Toutes les small archs battent v8 en movetime. **128-64 a la meilleure
eval qualité (vs Scan d10 = 0.870)**. Le bottleneck = vitesse d'inference.

### Phase A++ — séquence

**1. Ship v15 = 128-64 baseline (acquis)**
- Modèle déjà trained dans 0090
- À promouvoir comme baseline officielle (remplace v11 1024-512)

**2. Phase H Tier 1 restant (~1 semaine)**
- ✅ CMH + LMP (PR #140 mergé)
- ⏳ SPSA tuning constantes LMR/NMP/futility/aspiration (~3-5j)
- ⏳ Razoring (~1j)

**3. Inference SIMD optim (~1-2 semaines)**
- int8 SIMD AVX2 sur la 128-64 archi
- Cache-aligned weight layout
- Prefetch + loop unrolling
- Cible : 3M NPS → 6-10M NPS = **Scan parity**

**4. Re-bench vs Scan movetime**
- 100ms / 500ms / 2s / 5s pour scaling characterization
- Cible : rate > 0.20 en mt500 = Scan-tier accessible

### Estimation

| Étape | Gain ELO mt500 | FMJD |
|---|---|---|
| v15 base (acquis) | inconnu mais ≥ v8 | 2050+ |
| + Phase H Tier 1 search | +50-100 | ~2150-2200 |
| + SIMD optim NPS-parity | +100-200 | ~2300-2400 |
| + eval supériorité × depth-parity | **+200-300** | **~2500-2600** |

**Total Phase A++ : ~2-3 mois pour ~2500-2600 FMJD.**

### Pourquoi A++ vs Plan B pattern from scratch

| Aspect | A++ small arch + SIMD | Plan B pattern from scratch |
|---|---|---|
| Durée | 2-3 mois | 3-5 mois |
| Risque | Low (extension MLP existante) | Moyen (infra à valider via Othello) |
| Indépendance Scan | Encore dépendant (distill labels) | True indépendance après self-play |
| Apport unique | Engine MLP CPU bien optimisé | Engine pattern from-scratch jass |

**A++ est l'option pragmatique court terme.** Plan B reste documenté
comme alternative si A++ s'épuise.

---

## Plan post-distillation Scan — feuille de route consolidée (2026-06-02)

> Mis à jour après cycle distillation Scan (jobs 0073-0087). v11 =
> MLPNetworkQ 1024-512 sur 1M v8 Scan-distilled = **+330 ELO vs baseline
> original** (vs Scan rate 0.194, ~-361 ELO vs Scan).

### État actuel

* **v11 = baseline shipped** (0083, 1024-512 sur 1M v8 Scan-distilled)
* Pattern paradigm épuisé (18 hypothèses flat, dont distillation Scan
  vers pattern eval 0077-0082)
* Data axis épuisé : 0084 (mix 6.5M) et 0086 (v11 self-play 500K) ont
  tous deux régressé. Augmentation data ≠ amélioration.
* 0087 (master opening targeted, en cours) = dernier test data ; si flat,
  data axis définitivement clos.

### Trajectoire visée

Cible long terme : **2500-2700 FMJD** (vs ~2150 actuel), atteignable par
exploitation à fond de l'archi MLP existante avant de pivoter (D)
AlphaZero. Refonte AlphaZero **dormante**, à activer si plan ci-dessous
ne suffit pas.

### Phase H — Search tuning + SMP (Mois 1)

Objectif : extraire +100-200 ELO sans toucher au NNUE.

**Tier 1 cheap wins (~1 semaine, +50-100 ELO)** :
* SMP default `threads=8` partout (validé par 0088 si delta > 0.10)
* Countermove heuristic (~1j C++)
* Continuation history CMH (~1-2j C++)
* Late Move Pruning LMP (~quelques heures)
* SPSA tuning constantes LMR/NMP/futility/aspiration (~3-5j)

**Tier 2 moyen (~2-3 semaines, +30-60 ELO additionnel)** :
* Razoring (~1j)
* Probcut (~2-3j)
* Singular extension tuning (~1-2j)
* TT optimization (prefetch, sizing, replacement) (~1-2j)
* Time management amélioré (~3-5j, time control matches uniquement)

**Tier 3 specifique draughts (~1 semaine, +20-40 ELO)** :
* Promotion extensions (~1j) : extend si pion à 1 coup du roi
* King mobility extensions (~1j)
* Quiescence améliorée (forcing moves au-delà des captures) (~1-2j)

Total Phase H : **~+150-300 ELO sur 1 mois**, jass passe à
~**2300-2450 FMJD**.

### Phase I — Stockfish-style cycles (Mois 2-3)

Une fois Phase H stable, exploiter le moteur renforcé pour générer
data plus profonde + plus volumineuse via self-play.

**Cycle type** :
1. Gen-data 10M positions via v11+SMP self-play à PLAY_DEPTH=12-16
   (~50-100h compute, abordable grâce à SMP)
2. Label par v11 lui-même au même depth (pure self-distillation, pas
   de Scan re-label qui a échoué en 0086)
3. Train v12 = 1024-512 ou bump à 1536-768
4. Bench vs Scan + v11
5. Si v12 > v11 : itérer cycle v12→v13→v14

Gain attendu : **+30-80 ELO par cycle, asymptote à 3-5 cycles**.

Mitigation distribution biaisée (leçon 0086) : **mixer 50/50 self-play +
master-opening Scan-distilled** (de 0087, si validé). Force diversité
humaine + apporte volume self-play cohérent.

Total Phase I : **+80-200 ELO**, jass à ~**2400-2650 FMJD**.

### Pivot (D) AlphaZero — Mois 4+

À activer **uniquement** si Phase H + Phase I ne ferment pas le gap
Scan (cible : rate vs Scan > 0.40, ~-100 ELO). Sinon ship jass v14
comme baseline finale + projet considéré "fort amateur expert".

---

## Plan B — pivot pattern from scratch (si 0090 MLP plafond confirmé)

> Mis à jour 2026-06-02. Pivot stratégique si small-arch MLP (0090) ne
> donne pas de gain réel en time control. **Principe directeur :
> jass doit avoir son identité de moteur, pas être un Scan-clone.**

### Posture stratégique

Distillation Scan = **bootstrap technique uniquement**, pas dépendance
permanente. Le but final = **jass-pattern indépendant de Scan**,
évolué par self-play.

| Aspect | Pas acceptable | Acceptable |
|---|---|---|
| Réutiliser pattern code Scan | ❌ (GPL + clone) | — |
| S'inspirer de la géométrie pattern Scan (4×12 verticals) | — | ✅ (idea is public) |
| Bootstrap avec Scan labels temporaire | — | ✅ si suivi de self-play co-evolution |
| Final eval qui mime exactement Scan | ❌ (pas d'apport) | — |
| Final eval évolué par self-play depuis bootstrap | — | ✅ (vrai engine indépendant) |

### Phase Pattern-1 — Othello POC (1 semaine)

Valide infra pattern lookup propre, sans aucune dépendance externe.

* Move generator Othello 8×8 (~200-400 lignes C++)
* Pattern canonique Logistello-style (corners 3×3, edges, diagonals)
* Logistic regression sur self-play WDL
* Cible : 2000-2200 ELO Othello = infrastructure validée

**Gate 1** : pattern Othello bat random à >95% → infra OK. Sinon
debug avant de continuer.

### Phase Pattern-2 — Pattern jass minimaliste (3-5 jours)

* 8 features Scan-geometry mais code from scratch
* Régression linéaire sur master Lidraughts 2200+ (humain, source
  externe NON-Scan)
* Bench vs **Network_HC** (handcrafted, baseline fixe)

**Gate 2** : ≥55% vs handcrafted → infra pattern jass fonctionne.

### Phase Pattern-3 — Bootstrap Scan distillation (1-2 semaines)

Géométrie Scan complète + L-BFGS sur Scan labels.

* Pattern weights initialisés via Scan distillation (cheap, démarre fort)
* C'est **un point de départ**, pas la destination

**Gate 3** : pattern bootstrap ≥75% vs handcrafted ET ≥30% vs v8 →
continuer évolution. Sinon plafond pattern confirmé, drop.

### Phase Pattern-4 — Self-play co-evolution (1-2 mois)

**Le coeur du process d'indépendance.**

1. jass-pattern joue contre soi-même (1-5M parties)
2. Sampling positions à 1/4 ply, labels par WDL résultat + own deep search
3. **Replace progressivement Scan labels par jass's own labels**
4. Retrain pattern weights sur nouveau dataset (mix master + self-play)
5. Cycles itératifs v(N) → v(N+1)
6. 3-5 cycles avant plateau

Modèle évolue indépendamment. **À la fin, jass-pattern n'utilise plus
aucune sortie Scan à l'inférence.**

### Phase Pattern-5 — Decision finale

| Outcome | Décision |
|---|---|
| jass-pattern ≥ Scan en time control | **Indépendant ET fort** — ship comme baseline |
| jass-pattern ≈ Scan-distill-only (n'évolue pas) | Bootstrap a marché mais évolution flat → ship comme "Scan-class" sans dépendance runtime |
| jass-pattern < Scan | Indépendance acquise, force plafonnée. Acceptable comme exercise pédagogique |

### Estimation Plan B

* Phase Pattern-1 (Othello) : ~1 semaine
* Phase Pattern-2 (minimal) : ~3-5j
* Phase Pattern-3 (bootstrap) : ~1-2 semaines
* Phase Pattern-4 (self-play 3 cycles) : ~1-2 mois
* Phase Pattern-5 (decision) : ~3-5j

**Total : 3-4 mois, coût ~€100-200 compute.**

### Pourquoi PAS MCTS-light

MCTS sans GPU = node throughput beaucoup plus faible que Scan (8M alpha-beta
nodes/sec). Estimation realistic ~100-500 sims/move. **Plus lent ET moins
performant que alpha-beta sans batching**. Pas d'intérêt si Scan prouve
qu'alpha-beta+pattern est viable (vu dans Scan source : PVS, LMR, TT,
lazy SMP, BUT, pas de MCTS).

Si MCTS marchait sur draughts CPU, Scan/Kingsrow/Maximus l'auraient
adopté. Ils n'ont pas. → drop MCTS-light de la roadmap.

---

### Estimation cumulative finale

| Étape | ELO vs Scan | FMJD estimé | Indépendance Scan |
|---|---|---|---|
| v11 baseline acquis (fixed d10) | -361 | ~2150 | ❌ (distilled from Scan) |
| **v11 baseline en time control réel (0088)** | **-817** | **~2050** | ❌ |
| + Phase H search Tier 1-3 | -700 à -600 | ~2150-2200 | ❌ |
| + Phase A small arch (0090) | -500 à -400 | ~2300-2350 | ❌ |
| + Phase I cycles MLP | -400 à -300 | ~2400-2450 | partial |
| **Plan B pattern from scratch + self-play** | **-300 à -100** | **~2500-2700** | **✅ après Phase Pattern-4** |
| + (D) AlphaZero (si activé, GPU coûteux) | 0 à +100 | ~2600-2750 | ✅ (self-play pure) |

### Coût total estimé

* Phase H : ~1 mois dev + ~€50 compute
* Phase I : ~2 mois dev léger + ~€200-400 compute (cycles 10M)
* (D) AlphaZero : ~3-5 mois + ~€200-500 compute additionnel
* **Hors AlphaZero : ~3 mois + ~€250-450 pour atteindre ~2450 FMJD**

### Axes dormants

* Opening book (note `LIVRE_OUVERTURE.md`) : ~+30-50 ELO en tournoi
  officiel, 0 dans nos benchs no-book. Implémenter avant compétitions.
* Diversification self-play (note `DIVERSIFICATION_SELFPLAY.md`) :
  alternative à Phase I, complémentaire si Phase I s'épuise.
* Pattern eval distillation : abandonné définitivement (18 hypothèses
  flat, structural bottleneck eval→search confirmé).

---

## Notes méthodo

1. Tous les benchs vs v5 doivent utiliser **depth 10** comme signal principal
   (depth 6 est trop bruyant per nos verdicts antérieurs).
2. La référence absolue reste `calibrate_vs_scan` — quand un cycle franchit
   un decision gate, vérifier qu'il bouge aussi le score vs Scan, pas
   seulement vs v5.
3. Documenter chaque verdict dans un nouveau bloc de `SESSION_LOG_*.md` au
   fur et à mesure.
