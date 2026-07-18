> ⚠️ **ARCHIVE — NE PAS PRENDRE COMME CONSIGNE ACTIVE.** Doc historique (ère pré-fit-volume / NNUE).
> Source de vérité unique = [CURRENT.md](../L3_CURRENT.md) (+ docs système : BOUCLE_VIRTUEUSE, SCAN_METHODOLOGY_GAP,
> DIAGNOSTIC_VS_SCAN, BIAIS_FIT_VOLUME, PROGRESSION_LITTERATURE). Conservé pour l'historique seulement. _(Classé archive 2026-06-24.)_

# Pattern eval roadmap — feuille de route axe architecture

> **Note 2026-05-26 — Phase 1 frozen** : 4 expériences supervised ont
> exhausté Phase 1 (cf. `docs/SESSION_LOG_2026_05.md` annexe et
> `docs/SCAN_METHODOLOGY_GAP.md`). Le meilleur résultat (D1 hybrid
> base-5, job 0048) plafonne à 6/54 vs v5 d6 et 0/54 d10. Aucun setup
> supervised ne franchit le gate Phase 2 (rate ≥ 0.30 vs v5 d10).
>
> **Conclusion empirique** : le supervised cheap ne mène pas notre
> archi pattern à un niveau compétitif. Pattern axis frozen jusqu'à
> ce qu'on décide d'investir un nouveau leverage (TD-leaf, knowledge
> distillation depuis v6/v7, pattern geometry alignée Scan). Voir
> `docs/SCAN_METHODOLOGY_GAP.md` pour le plan itératif.
>
> Le reste de ce document reste valide comme plan **historique** des
> phases si on relance l'axe ultérieurement.

> **Note 2026-05-24 — ordering révisé** : ce doc reste valide pour les
> phases pattern elles-mêmes, mais l'**ordering global** des prochaines
> expériences est désormais piloté par `docs/ROADMAP.md` (post-bibliographie).
> L'axe pattern y est repositionné en **Phase 1+ après** deux phases data
> (quiet filter + volume master) qui ont un précédent empirique fort
> [TalkChess, arXiv 2412.17948]. À lire dans l'ordre : ROADMAP.md →
> PATTERN_ROADMAP.md (ce doc) pour le détail des phases pattern.

> Rédigé fin de session 2026-05. Décrit où on en est sur l'axe pattern
> et comment continuer. À lire en complément de `docs/ANALYSE_VEILLE_NNUE.md`
> (qui pose la motivation), `docs/REFERENCES_BIBLIOGRAPHIE.md` (qui
> recadre l'ordering des phases) et `docs/SESSION_LOG_2026_05.md` (qui
> documente les expériences déjà tentées).

---

## État actuel de l'axe pattern

### Ce qui marche déjà côté code (en main)

- **`src/pattern_network.{hpp,cpp}`** : classe `PatternNetwork` implémentant
  `INetwork`. Stocke N patterns (chacun K squares + 5^K weights int32).
  Plugged dans le search via le même chemin que MLPNetworkQ.
- **Format on-disk JPAT** : magic + N patterns + bias, self-describing.
  Auto-détecté par `load_network()`.
- **`default_v1()`** : 8 patterns × 4 squares (5K weights total).
- **`default_v2()`** : 16 patterns × 8 squares (6.25M weights total), full
  coverage 50/50 squares.
- **`tools/train_pattern.py`** : trainer PyTorch via `nn.Embedding` tables.
  Loss : `lambda * score_MSE + (1-lambda) * 50000 * wdl_BCE`. Quantize fp32
  → int32 cp à la save.
- **Tests** : `test_pattern_network_*` (default_v1 layout, evaluate avec
  poids connus, save/load roundtrip, load_dispatch via load_network).

### Bench raw eval — un gain énorme déjà acquis

| Archi | Evals/sec | Speedup vs MLPNetworkQ |
|---|---|---|
| MLPNetworkQ 256-128 (v5, AVX2 + accumulator) | ~469 K | 1× (référence) |
| PatternNetwork v1 (8×4) | ~134 M | **~285×** |
| PatternNetwork v2 (16×8) | similaire (lookup tables plus grosses mais cache-friendly) | ordre de grandeur identique |

Même à qualité égale, search à depth 20 en pattern ≈ depth 24 en MLP. C'est
un acquis structurel à exploiter.

### Ce qui ne marche pas — le diagnostic à porter

| Tentative | Résultat | Diagnostic |
|---|---|---|
| `0025a-3` v1 (5K weights, lambda=0.7) | 0/54 | Sous-paramétré + coverage 32/50 |
| `0025a-6` v2 (6.25M weights, lambda=0.5) | 0/54 | Loss MSE-dominée → pred=0 trivial |
| `0025a-7` v2 pure WDL (lambda=0, lr=1.0) | 3/54 vs v5 d6 (rate 0.056) | Archi viable, training sous-tuné |

**Le pattern eval marche.** Train log de 0025a-7 montre val_mse 91M → 81M
(−11%), prouvant que les weights apprennent. Mais 30 epochs avec
hyperparams basiques ne suffisent pas pour rivaliser avec un MLP qui a eu
plusieurs cycles de tuning.

---

## Le vrai problème — training pipeline sous-investi

Les engines pattern-based forts (Scan, Kingsrow) utilisent des techniques
training significativement plus sophistiquées que notre `train_pattern.py`
actuel :

1. **Co-évolution / self-play reinforcement** : le moteur joue contre
   lui-même, les positions visitées + leurs résultats deviennent les data
   d'entraînement. Itéré sur N générations.
2. **Tablebase seeding** : les positions endgame avec résultat connu
   (KvK, KKvK, plus loin) initialisent les patterns concernés avec les
   poids exacts. Bootstrap le training.
3. **Reinforcement learning à proprement parler** : TD-leaf, Q-learning
   ou des dérivés, pas du supervised flat sur un corpus fixe.
4. **Augmentation par symétrie** : flip horizontal du board (dame
   internationale est symétrique gauche/droite), double effectivement
   le dataset.
5. **Quantisation-aware training** : entraîner directement en int8 ou
   int16 plutôt que fp32 → int32 (round at save). Évite la perte de
   précision finale.
6. **Filtrage de quiescence** : skip les positions où un coup obligatoire
   est pending (rafle imminente) — leur label score est trompeur. Cf. doc
   de veille section arXiv 2412.17948.

Notre `train_pattern.py` ne fait AUCUN de ces points. C'est un trainer
naïf qui marchait OK pour les MLP denses (parce qu'ils saturent vite à
leur capacité) mais pas pour les patterns sparse.

---

## Roadmap proposée (par phase / coût croissant)

### Phase 1 — Améliorer le training, cheap (~€5, ~1 semaine wall)

Objectif : faire converger v2 pattern à ≥0.20 vs v5 d10 (preuve que
l'archi est viable end-to-end).

| Tâche | Effort | Hypothèse |
|---|---|---|
| Augmentation par symétrie (mirror) | ~1-2 h code | Double effectivement le dataset, bonne baseline. |
| Filtrage quiescence dans `--gen-data-wdl` | ~2 h code | Label moins bruité = training plus stable. |
| Trainer : warmup + lr schedule + L2 weight decay + grad clipping | ~2-3 h code | Convergence plus saine pour 6M params sparse. |
| Trainer : multi-seed averaging (3 runs, average final weights) | ~1 h code | Réduit l'overfit sur 1M records. |
| Trainer : option `--score-scale 0.01` (normalisation score MSE) | ~30 min code | Évite que MSE domine et écrase le BCE. |
| Job `0043-train-pattern-v2-tuned.sh` | ~30 min | Re-train avec tous ces ajustements. |
| Bench → décision : signal pour continuer ou pas | ~1 h wall | – |

**Decision gate** : si après ces fixes le pattern v2 reste sous 0.15
vs v5 d10, l'approche "trainer supervised cheap" est inadéquate pour
ce type de modèle. Passer en phase 2.

### Phase 2 — Self-play iteration (révision coût 2026-05-28)

**Note de révision** : l'estimation initiale (~€20-40, ~3-4 semaines)
était basée sur le coût d'eval MLPNetworkQ (~470K evals/s). Pattern eval
est ~300× plus rapide (~130M evals/s mesuré PR #73-86). Recalcul honnête
en deux modes (cf. `docs/SCAN_METHODOLOGY_GAP.md` §G4 pour le détail) :

**Mode G4-diag** (~€2-3, ~1-2 jours wall) : 10K games × 10 iter, depth 4.
Suffit à diagnostiquer si self-play débloque l'archi. À lancer si
G3-supervised n'a pas franchi son gate.

**Mode G4-prod** (~€10-20, ~1 semaine wall) : 100K-300K games × 20 iter,
depth 6. À lancer si G4-diag montre du signal (rate ≥ 0.20 vs v6 d10).

| Tâche | Effort | Hypothèse |
|---|---|---|
| C++ `--self-play-pattern N out.jnnw` | ~3-5 h code | – |
| Trainer modifié (existe déjà) | ~1 h wire | – |
| Loop script `0055-g4-self-play-pattern.sh` | ~4-6 h code | – |
| G4-diag : 10 itérations × ~1.5h sur 1× CCX23 | ~€2-3 compute | Cheap-check méthodo |
| G4-prod : 20 itérations × ~6-9h | ~€10-20 compute | Convergence vers eval forte par self-improvement |
| Bench final vs v5/v6/v7 et vs Scan | ~1 h | – |

**Decision gate G4-diag** : rate vs v6 d10 ≥ 0.20 après 10 iter → G4-prod ;
sinon abandon ferme (la self-play n'unlock pas la méthodo).

**Decision gate G4-prod** : rate vs v6 d10 stagne < 0.40 après 20 iter →
abandon, l'archi 16×8 n'est probablement pas suffisante pour le 10×10
international draughts. Passer en phase 3.

### Phase 3 — Scale up pattern set (commitment, ~€50-100, ~1-2 mois)

Objectif : approcher la complexité du pattern set Scan.

Pistes :
- **Plus de patterns** : passer de 16 à 32-64 patterns. Ajouter des
  patterns ligne (diagonales 5-7 squares) + colonnes en plus des
  4×4 régions. Total weights 30M-100M.
- **Patterns plus longs** : 4×5 ou 5×5 régions (12-16 squares). 5^12 =
  244M weights par pattern — exige une gestion mémoire careful. Ou
  factorisation : compresser les buckets vides via hashing.
- **Hybrid pattern + dense head** : entrée = embedding patterns,
  hidden layer dense au-dessus. Combine localité (patterns) et
  combinaisons (dense). Plus proche du Stockfish HalfKAv2-NNUE moderne
  qui mixe les deux paradigmes.

Decision gate : viser ≥0.50 vs Scan. Si atteint, c'est un changement
de paradigme acquis pour jass.

---

## Quick-wins indépendants (à activer en parallèle quand pratique)

- **Refresh continu master-games Lidraughts** : un job `0042-refresh-master`
  hebdomadaire qui appelle `fetch_lidraughts_games.py` + `pdn_to_jnnw.py`
  en mode incrémental. Bénéfice à long terme pour tous les futurs cycles.
  Coût trivial.
- **Scraping FMJD** : l'endpoint identifié est `fmjd.space/game_open.php`
  (job `0024-probe-fmjd-spa` a trouvé ça). Coder un scraper respectueux,
  ~3-5K games top-FMJD ajoutés au corpus. Effort ~1-2 jours.
- **Filtrage de quiescence dans gen-data-wdl** : utile pour pattern ET
  pour MLP, pas seulement pour la phase 1 pattern.

---

## Templates dormants disponibles

Tous dans `jobs/templates/` post-consolidation :

| Famille | Fichiers | Utilité résiduelle |
|---|---|---|
| Cycle 9 1M cheap | `0034`, `0035`, `0036` | Re-validate si on revient au corpus axis |
| Cycle 9 10M full | `0030a-d`, `0031`, `0032`, `0033` | Probablement jamais — €700+ pour gain marginal |
| Depth-10 experiment | `0039`, `0040`, `0041` | Si on veut tester l'hypothèse Stockfish "low depth + volume" |
| Bigger MLP | `0037`, `0038` (en queue déjà exécuté) | Reference — bigger MLP perd, vérifié |
| Pattern v1 | (job déjà exécuté) | Référence historique |

À supprimer / archiver dans une session de housekeeping.

---

## Méta-recommandation

L'axe pattern est la **seule direction non-exhaustée** capable potentiellement
de casser le plafond -812 ELO vs Scan. La littérature dame est unanime
là-dessus. Mais ce n'est PAS un quick-fix : ça demande de l'investissement
en training infrastructure, pas juste un nouveau dataset.

**Si la prochaine session démarre sur cet axe** : commencer par Phase 1
(training fixes). C'est cheap, c'est self-contained, et ça donnera un
signal clair sur la viabilité avant d'engager Phase 2.

**Si une autre direction émerge** (ex : refresh continu Lidraughts + retrain
sur corpus doublé) : noter qu'on accepte de plafonner sur l'archi MLP
actuelle, et l'estimé +5-15 ELO par refresh est marginal.
