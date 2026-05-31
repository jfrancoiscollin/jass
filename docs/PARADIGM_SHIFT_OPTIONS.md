# Paradigm shift options — beyond the cheap pattern axis

> Rédigé le 2026-05-30 après ~13 hypothèses cheap pattern toutes
> réfutées (cf. `SCAN_METHODOLOGY_GAP.md` + `SESSION_LOG_*.md`). Capture
> les pistes de **paradigm shift** discutées avec l'utilisateur pour
> ne pas les perdre. À ré-évaluer périodiquement selon les évolutions
> du projet (verdict G4-prod si tenté, nouvelles idées, etc.).
>
> À lire avec `docs/SCAN_METHODOLOGY_GAP.md` (ce qui ne marche pas
> cheap) et `docs/ROADMAP.md` (état actuel des axes).

---

## Contexte

L'axe pattern dans notre infrastructure actuelle a été exhausté avec
~13 hypothèses cheap (G1→G3b, G4-diag, G5/H1, H1+H3, H3-isolated,
H1+H3+H4, H2 volume, V4 long, TD-leaf, MLP head). Toutes flat win-rate
vs v6 d10. Pearson grandit avec volume/sophistication mais ne se
traduit jamais en wins (probable problème de calibration absolue).

Pour franchir cette barrière, il faut probablement un **paradigm shift**
— changer fondamentalement soit le format d'entrée, soit la structure
du modèle, soit la méthodologie de training.

Ces options sont **dormantes** : à reprendre quand on accepte de
sortir du framework actuel (lookup-tables-plus-linear).

---

## (A) Pattern indices → embeddings dans une MLP end-to-end

**Idée** : remplacer la lookup-table de poids par une vraie embedding
layer. Chaque pattern reçoit un embedding (e.g., dim 8). Les N embeddings
sont concaténés (8N dims) puis passés à un MLP standard
(8N → 128 → 64 → 1) avec ReLU, training Adam standard.

**Format**:
- Input : N indices catégoriels (un par pattern), valeurs ∈ [0, base^K)
- Embeddings : `nn.Embedding(base^K, embed_dim)` × N
- Concat → MLP → score

**Pourquoi ça pourrait débloquer** :
- Toutes nos tentatives utilisent une combinaison LINÉAIRE des lookup
  values (poids scalaires). Ici les embeddings sont des vecteurs.
- Les vecteurs sont composés non-linéairement par un MLP qui peut
  apprendre des interactions cross-pattern.
- Format proche de NNUE classique → on hérite des outils éprouvés.
- Calibration différente : beaucoup plus de degrés de liberté par
  pattern (embed_dim×base^K vs 1×base^K).

**Effort** : ~1 jour dev (modèle PyTorch + format save) + ~€2 compute.
Pas besoin de toucher `pattern_network.cpp` initialement (Python-only
prototype, port C++ pour inference après validation).

**Risque** : moyen. Toujours la même info en entrée que pattern v3
mais transformation très différente. Si même avec embeddings le modèle
ne discrimine pas en bench, c'est preuve forte que l'info pattern
seule (sans HalfMen) est intrinsèquement insuffisante.

**My recommendation** : **top pick** des paradigm shifts cheap.

---

## (B) MLPNetworkQ enrichi avec features structurelles

**Idée** : ajouter au feature set HalfMen (450 features) des features
explicites Scan-style :
- Material count (1)
- King count (1)
- Balance L/R (1)
- King PST (50 binary one-hots × 2 colors = 100)
- Mobility (2)
- Total : +154 features → input dim 604

Garder MLPNetworkQ archi 256-128 ou bump à 384-192.

**Pourquoi ça pourrait aider** : on a vu v8 atteindre un plateau.
Le bottleneck est peut-être le manque de structural features dans
HalfMen. Cette approche enrichit l'INPUT du NNUE qu'on sait qui marche.

**Effort** : ~1 jour C++ + Python (feature extraction côté gen-data +
côté NNUE forward), ~€5 compute training.

**Risque** : faible. C'est du "more of the same" sur l'axe data avec
un twist. ROI faible-moyen mais probable de gagner +20-30 ELO (v9).

**My recommendation** : back-up sûr en parallèle de (A).

---

## (C) Convolution 2D sur le board

**Idée** : représenter le board comme un tenseur 10×10×K (K = nombre
de planes, e.g., 4 pour W-men/W-kings/B-men/B-kings). Appliquer des
conv layers 5×5 ou 7×7. Pooling + dense head.

**Pourquoi ça pourrait débloquer** :
- Translation-invariance native — un pattern sur le flanc gauche
  utilise les mêmes poids que sur le flanc droit (vs pattern-based
  où chaque position a ses propres poids).
- Capacité de représentation très différente.
- Reception field exact contrôlable via la taille du kernel.

**Effort** : ~2-3 jours dev (PyTorch standard, bcp de tutoriels).
C++ inference plus complexe (conv quantization, BLAS-like ops). Pourrait
rester Python-only pour le prototype initial. Effort C++ port : +3-5
jours.

**Risque** : moyen. Approche très différente du NNUE qui marche.
Pourrait être strictement inférieur sur l'espace d'états des dames
internationales (qui est petit et "tabular"-friendly).

**My recommendation** : intéressant intellectuellement, à essayer si
(A) et (B) ne suffisent pas. ~3-5 jours total avec C++ port.

---

## (D) AlphaZero-style MCTS + ResNet

**Idée** : abandonner alpha-beta + eval. Adopter MCTS + value/policy
ResNet (à la AlphaZero). Self-play massive en parallèle, ne nécessite
pas d'évaluateur externe pour labelliser.

**Pourquoi** :
- C'est l'état de l'art pour les jeux à information parfaite
- Approche prouvée qui scale
- Pas de dépendance sur un évaluateur "teacher" pré-existant

**Effort** :
- ~2-3 semaines dev (refonte search complète + nouvelle infra
  d'entraînement + MCTS implementation propre)
- **~€100-300 compute** sur plusieurs semaines pour atteindre
  un niveau intéressant
- Pas certain qu'on atteigne Scan-level même avec ça en quelques
  semaines (AlphaGo a tourné sur des dizaines de TPUs pendant des
  jours)

**Risque** : élevé en scope dev, faible en incertitude technique
(méthodologie connue, plein d'open source AlphaZero clones existent).

### Compute platform pour D — détail honnête

**CCX33 (notre setup actuel, CPU 8 cores ~€60/mois)** :
- ✅ **Viable pour prototype**. Petit ResNet (6-8 blocs × 64-128 channels),
  MCTS 50-100 sims/coup. ~3-4 semaines pour atteindre un niveau
  intéressant.
- ❌ Trop lent pour production sérieuse (training 1 epoch sur 100K
  positions = ~1-2h CPU vs ~5-10 min GPU).
- ✅ Intégration naturelle avec notre runner / git workflow existant.

**GPU dedicated (Hetzner / vast.ai / runpod ~€100-300/mois)** :
- ✅ **Recommandé pour scale-up production** post-prototype.
- ✅ Batched MCTS leaf evaluation = ~10-100× speedup vs CPU (la "killer
  feature").
- ❌ Implem batched MCTS plus complexe (virtual loss, batch collection).
- Hetzner cloud n'a PAS de GPU on-demand facile ; il faut louer un
  dedicated server (engagement mensuel) ou utiliser vast.ai/runpod
  pour du tarif horaire.

**Colab Pro / Kaggle (gratuit ou ~$10/mois)** :
- ❌ **PAS adapté à notre setup** pour production AlphaZero.
- Notebook interactif, session limitée 6-24h, disconnect quand idle.
- Pas de cron / orchestration native. Upload du binary jass + data à
  chaque session.
- ❌ Pas adapté à un training multi-jours sans surveillance, ni à un
  self-play loop continu.
- ✅ **OK pour proof-of-concept ponctuel** : "est-ce qu'un ResNet 6×64
  sur board 10×10 converge sur master games WDL en 1h ?" — parfait
  Colab. Le self-play loop continu reste à faire sur CCX33 ou GPU
  dedicated.
- ✅ Quotas : Free Colab ~3-4h GPU/jour T4 ; Pro ~$10/mois prioritaire ;
  Kaggle gratuit 30h/semaine T4 ou P100. "Fair use" pour Colab — si tu
  pousses fort, accès dégradé pendant quelques jours.

### Recommandation phasée pour D

**Phase 1 — Prototype CCX33 (~2-3 semaines, ~€60-100)** :
1. Petit ResNet (6 blocs × 64 channels) en PyTorch
2. MCTS implementation simple, 50 sims/coup
3. Self-play loop sur CCX33 + training Python local
4. Bench vs v8 + handcrafted pour valider la méthodo

Optionnellement : utilisation ponctuelle de **Colab Pro** pour tester
des hyperparamètres NN training en isolation (~1-3h sessions).

**Phase 2 — Scale-up GPU (~2-4 semaines, ~€200-400) — si Phase 1
sort un signal** :
1. Rent vast.ai T4 ou Hetzner dedicated GPU
2. Implém batched MCTS (virtual loss + batch leaf eval)
3. ResNet plus gros (10-12 blocs × 128 channels), MCTS 200-400 sims
4. Self-play massive 24/7 sur plusieurs semaines

**Verdict pratique** : ne pas commit GPU avant Phase 1 validation
sur CCX33. Risque d'engager €200-400 sur une méthodo qui ne marche
pas pour notre jeu/scale.

**My recommendation** : engagement major. À considérer SEULEMENT si
on décide de pivoter le projet vers un effort multi-mois (genre :
"jass v2 = AlphaZero clone"). Pas un cheap test.

---

## (E) Bigger MLPNetworkQ + v8 dataset

**Idée** : v9 = MLPNetworkQ 1024-512 entraîné sur v8 dataset (1M
v7-labelled-depth-16). Bump capacité du MLP existant qui marche.

**Effort** : juste un job script (infra existante). ~€5 compute.

**Risque** : très faible. On a vu v8 (512-256) déjà avec quirks
(non-transitivité vs v6). Bigger archi pourrait sur-fitter encore
plus.

**My recommendation** : "safe pick" si on veut un v9 sans grand
risque mais ROI marginal. Probablement +10-30 ELO vs v8 si ça marche.

---

## (F) MLPNetworkQ + têtes auxiliaires multi-tâches (proposé 2026-05-31)

**Idée** : garder l'archi MLPNetworkQ v8 inchangée (HalfMen 450 →
256 → 128 → 1) mais ajouter des **têtes de prédiction supervisées
sur les couches cachées** pendant le training. Chaque tête prédit
une feature explicite (mobilité par pièce, contrôle de cases clés,
structure de chaîne, distance à promotion, etc.) calculée
analytiquement à la prep des données.

```
HalfMen 450 → Linear(256) → ReLU → [h1] ──► Linear(N_aux1) ← aux_head_1
                              h1 →  Linear(128) → ReLU → [h2] ──► Linear(N_aux2) ← aux_head_2
                                              h2 → Linear(1)        ← main_head (eval principal)
```

Loss totale : `L_main + λ₁·L_aux1 + λ₂·L_aux2`.

À l'inference, les têtes auxiliaires sont prunées — **zéro overhead
runtime** (binaire quantisé identique à v8/v9). Seul le training
diffère.

**Pourquoi c'est différent des 15 hypothèses pattern + (B) + (E)** :
* On n'attaque ni l'input (que (B) enrichit), ni l'archi (que (A)/(E)
  changent). On attaque la **représentation interne**.
* Hypothèse : si le plafond eval-only est dû à "le MLP n'apprend pas
  les bonnes features tout seul à partir du signal score+WDL", forcer
  les hidden layers à encoder explicitement la mobilité / structure
  pourrait débloquer.
* Classe AlphaZero-like two-head / BERT-like aux objectives. Bien
  documenté en deep learning mais **non testé chez nous**.

**Tâches auxiliaires candidates** (toutes calculables analytiquement
au sampling) :
1. King mobility map — 50 outputs (free diag neighbors par square)
2. Man mobility count W/B — 2 outputs
3. Promotion proximity — 2 outputs (min distance to promo row par couleur)
4. Center control — 4 outputs (occupation des 4 cases centrales par côté)
5. Chain structure — count of supported men (men défendus par voisin diag arrière)

Total ~60-80 sorties auxiliaires. Trivial en Python.

**Effort** : ~3-5 jours dev (extend train_v3.py + Python feature helpers
+ bench harness pour comparer multi-task vs mono-task sur même dataset).
~€5-10 compute.

**Risque** :
* Gradient interference si λ trop fort → main task dégrade. À tuner.
* Capacité hidden insuffisante pour absorber main + aux signals.
  Mitigation : tester sur 1024-512 si 256-128 sature.

**Gain estimé** :
* Best : +30-50 ELO si la représentation interne était le bottleneck
* Median : +10-20 ELO (utile)
* Worst : 0 à -10 ELO si gradient interference

**My recommendation** : excellente piste à tester après 0072 SMP delta.
Origine non-évidente (proposée par l'utilisateur) — ne tombe pas dans
le piège "variante des 14+1 déjà refutées".

---

## Synthèse — recommandations par profil d'engagement

### "Curiosité cheap" (~€10, ~1-2 semaines wall)

1. **(A) Pattern→embeddings end-to-end** — vrai paradigm shift dans
   le pattern axis, cheap, ~1 jour
2. **(B) MLPNetworkQ enrichi** en parallèle — back-up sur axe data
3. **(E) Bigger MLP NNUE** — si on veut juste shipper un v9 vite
4. **(F) MLPNetworkQ + têtes aux multi-tâches** — attaque la
   représentation interne, original, ~3-5j

### "Investment moyen" (~€30, ~3-4 semaines wall)

1. (A) + (B) ci-dessus
2. **(C) CNN board** — vrai nouveau paradigme, plus coûteux mais
   différent fondamentalement
3. Éventuellement G4-prod minimal (~€7, 2 jours) en parallèle pour
   borner l'axe pattern actuel

### "Engagement major" (~€150-300, 2-3 mois)

1. **(D) AlphaZero-style** — refonte majeure, état de l'art, prouvé
2. Ou continuer à itérer sur (A)/(C) avec datasets plus gros

---

## Notes de revue périodique

À chaque session future où l'on reprend l'axe pattern/eval :
1. Re-lire ce doc + `SCAN_METHODOLOGY_GAP.md`
2. Vérifier si une de ces options a déjà été activée (move templates
   → queue + verdict)
3. Mettre à jour les estimations effort/coût avec les mesures
   récentes (CCX size, infra speed, etc.)
4. Évaluer si de nouvelles idées sont apparues (publications, idées
   utilisateur, etc.)

L'**erreur à éviter** : ré-essayer (de manière déguisée) une variante
des 13 hypothèses cheap déjà réfutées. Si la prochaine idée se résume
à "more patterns / more volume / different label source / different
optimizer", probable qu'elle soit du more-of-same.
