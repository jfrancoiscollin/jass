# jass — feuille de route post-bibliographie

> Rédigé le 2026-05-24. Supersede l'ordering de `PATTERN_ROADMAP.md` à la
> lumière de la bibliographie annotée `docs/REFERENCES_BIBLIOGRAPHIE.md`.
> À lire en complément de `ANALYSE_VEILLE_NNUE.md` (motivation) et
> `SESSION_LOG_2026_05.md` (ce qui a été testé jusqu'ici).

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

### Estimation cumulative finale

| Étape | ELO vs Scan | FMJD estimé |
|---|---|---|
| v11 baseline (acquis) | -361 | ~2150 |
| + Phase H search | -211 à -161 | ~2300-2350 |
| + Phase I cycles | -131 à -61 | ~2380-2450 |
| + (D) AlphaZero (si activé, 3-5 mois) | 0 à +100 | ~2600-2750 |

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
