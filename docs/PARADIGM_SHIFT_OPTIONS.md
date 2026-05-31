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

## Synthèse — recommandations par profil d'engagement

### "Curiosité cheap" (~€10, ~1-2 semaines wall)

1. **(A) Pattern→embeddings end-to-end** — vrai paradigm shift dans
   le pattern axis, cheap, ~1 jour
2. **(B) MLPNetworkQ enrichi** en parallèle — back-up sur axe data
3. **(E) Bigger MLP NNUE** — si on veut juste shipper un v9 vite

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
