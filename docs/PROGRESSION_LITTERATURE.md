# Progression d'une eval linéaire-patterns par self-play — ce que dit la littérature (2026-06-23)

> **Rapport de recherche documentée** (6 angles, multi-sources, vérifié). Il **RÉVISE une hypothèse centrale**
> de notre programme (« scaler la data vers les milliards à la Scan »). À lire avec [CURRENT.md](CURRENT.md) et
> [BOUCLE_VIRTUEUSE.md](BOUCLE_VIRTUEUSE.md).
>
> ⚠️ **Limite de sourcing** : la policy réseau a bloqué la plupart des PDF primaires (403). Les agents se sont
> rabattus sur les résumés de recherche, SAUF : le **code source de Scan** (lu directement → ground-truth) et les
> **docs scikit-learn / VC-dim** (récupérées directement). Confiance flaggée par item.

## 1. Théorie : un modèle LINÉAIRE à features fixes a un plafond fixé par les FEATURES, pas par les itérations
- **Tsitsiklis & Van Roy 1997** (convergence du TD linéaire) : converge vers un **point fixe UNIQUE**. Le plafond =
  la portée des features ; le **volume de data ne déplace pas le point fixe**, il réduit la **variance** des poids
  (précision). [textbook] arXiv via mit.edu/~jnt/Papers/J063-97-bvr-td.pdf
- **Stat-learning theory** (sources VÉRIFIÉES, scikit-learn) : complexité d'échantillon **∝ nb de paramètres** (O(d),
  VC-dim) ; un modèle à **biais élevé (classe simple) sature vite** — *« plus de data n'améliore pas significativement »* ;
  décomposition `erreur = biais² + variance + bruit` → **seule la variance baisse avec la data**, pas le biais de classe.
  [textbook, vérifié] raw.githubusercontent.com/scikit-learn/scikit-learn/main/doc/modules/learning_curve.rst
- **Itérations pour converger = PEU** : KnightCap/TDLeaf **1650→2150 Elo en 308 parties** (Baxter et al., arXiv cs/9901001).
- **Lever le plafond a TOUJOURS exigé un changement de REPRÉSENTATION**, jamais "plus d'itérations" : Multi-Stage TD
  (2048), **NNUE non-linéaire** (échecs). Plateaux n-tuple documentés : 2048 sature ~1M parties ; Connect-4 ~84-90 %
  (2-4M parties, Thill 2012). [documented-paper]

## 2. 🔴 RECADRAGE : Scan n'a PAS utilisé "des milliards de data épurées"
- **Eval de Scan = ~2 125 820 poids** (patterns base-3 12 cases, 8 rectangles), MG/EG. → **plus PETIT que notre 32cf
  (8,5M)** ; ≈ notre **8cf**. [ground-truth, code source `src/eval.cpp` lu directement]
- Seed = **matériel seul** ("1 dame=3 pions"+règles), reste par self-play, **régression logistique sur WDL**, gradient
  mini-batch, *"quelques heures sur un cœur"*. [lidraughts, chessprogramming/Draughts]
- **Volume d'entraînement de Scan : NON documenté.** Le "milliards" est **infirmé / introuvable**.
- Proxy le mieux chiffré = réplication **Kingsrow (Ed Gilbert)** : **~1M parties** self-play, **+72 Elo** sur l'eval
  hand-tuned (16 000 parties) ; archives **145M / 231M positions**. [Checker Maven ; talkchess t=75190]
- **⇒ Notre ~50M est dans le MÊME ordre de grandeur** que les archives Kingsrow (145-231M), avec un modèle **plus riche**.

## 3. Rendements décroissants + découplage loss↔Elo (Texel-tuning, Österlund)
- Historique de tuning de Texel ≈ **99,6 Elo cumulés** : gros gain initial, puis gains qui rétrécissent ; **les derniers
  gros sauts venaient d'une MEILLEURE DATA, pas de plus de paramètres**. [chessprogramming/Texel's_Tuning_Method]
- **Découplage MSE↔Elo** : au-delà de ~40 passes, la loss baisse mais **l'Elo régresse** (sur-ajustement à la loss).
  → **valide qu'on juge par MATCH, pas par val_loss.**
- Data Texel typique **725k → 10M** positions ; sur-ajustement **non limitant** à peu de paramètres.
- ⚠️ **Aucune courbe "Elo vs itérations" propre publiée** pour le HCE self-play (la méthode originale = descente de
  coordonnées sur heures/jours, pas "quelques itérations" ; le "rapide" vaut pour les variantes gradient).

## 4. Le NN (non-linéaire) = le seul "lève-plafond" documenté
- AlphaZero : **Elo ∝ log(compute)**, montée raide puis asymptote ; le papier dit *« approximation non-linéaire vs
  l'approximation LINÉAIRE des programmes d'échecs typiques »* → le NN **invente ses features** → plafond plus haut.
  [arXiv 1712.01815]
- **NNUE** : couches cachées ClippedReLU = **non-linéarité** = ce qui a dépassé l'eval linéaire hand-crafted
  (Stockfish 12, 2020). [nnue-pytorch docs, vérifié]
- GLEM/Logistello (Buro, Othello, cousin direct de Scan) : linéaire sur n-tuples, ~13 phases, **~1,2M poids**,
  ~millions de positions. Itération de re-fit + courbe data↔précision **non documentées**. [chessprogramming, snippets]

## 5. Conséquences pour NOUS (révision stratégique)
| Croyance d'avant | Ce que dit la doc |
|---|---|
| "Scan = milliards de data, on est 3 ordres dessous" | ❌ Scan ~2,1M poids, volume non-doc ; Kingsrow ~1M parties/145-231M pos = **notre ordre**. |
| "Scaler la data vers les milliards comblera l'écart" | ⚠️ Près du plafond, **le volume ne fait que de la précision** (point fixe figé). Peu probable que ce soit le gain. |
| "La boucle doit grimper longtemps" | ❌ Convergence **rapide**, **petits gains près du plafond** — un plateau rapide est **NORMAL**, pas un échec. |

**Deux leviers réels pour dépasser (pas un troisième) :**
1. **Linéaire mais géométrie PLUS RICHE que Scan** (notre 32cf 8,5M ⊃ son 8cf 2,1M), *bien fittée* → relève NOTRE
   point fixe au-dessus du sien. (Cohérent GATE 0401 : 32cf>8cf au scale.)
2. **NNUE** (non-linéaire) → le seul lève-plafond universellement documenté. Décision à reposer **au plateau confirmé**.

**Scaler la data au-delà de ~50-100M n'est PAS soutenu comme levier de FORCE** une fois la couverture saturée
(cf [BOUCLE_VIRTUEUSE.md §10](BOUCLE_VIRTUEUSE.md)) — ça ne fait que de la précision marginale.

## Sources clés
- Tsitsiklis & Van Roy 1997 (TD linéaire) · scikit-learn `learning_curve.rst` (biais-variance, vérifié) · Baxter et al.
  cs/9901001 (KnightCap) · Thill 2012 (Connect-4) · Szubert-Jaśkowski 2014 (2048) · arXiv 1712.01815 (AlphaZero) ·
  nnue-pytorch docs · chessprogramming.org (Texel, Draughts, Logistello) · Scan `src/eval.cpp` · Checker Maven
  (Kingsrow +72 Elo) · talkchess t=75190 (145M/231M archives).
