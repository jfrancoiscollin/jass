# Arbre de décision — programme « battre Scan »

> **Doc VIVANT.** À chaque verdict de job, on **élague** (✂️ une branche morte,
> avec sa raison) ou on **active** (🟢) la branche à explorer. Lire avec
> [JOURNAL_DE_BORD.md](JOURNAL_DE_BORD.md) (ancres + faits) et
> [ROADMAP.md](ROADMAP.md). Mise à jour : **2026-06-12** (0203 en cours).
>
> **Légende** : 🟢 chemin actif · 🔵 branche ouverte (à explorer) · ✂️ élaguée
> (morte, raison donnée) · ⭐ candidat le plus probable · 📍 position actuelle.

---

## Acquis (racine — déjà tranché)

- **Levier = l'EVAL.** ✂️ Recherche (complète, cf. ARCHITECTURE.md) · ✂️ vitesse
  pure (0201 : +4 plies ne ramènent pas à parité Scan) → secondaires.
- **Juge = Scan** à profondeur égale (✂️ v15 : flatteur, ≈ 0 vs Scan).
- **Cible label = WDL itéré.** ✂️ deep-score (distillation, plafonné au
  générateur — 0200/0202) · ✂️ WDL 1-cycle (0196 : sans itération ça ne monte pas).

---

## L'arbre

```
RACINE : atteindre le niveau Scan (idéalement INDÉPENDANT)
│
├─ Levier eval établi · cible = WDL itéré établie
│
└─ NŒUD 1 — La boucle WDL ITÉRÉE monte-t-elle ?  🔵 NON TRANCHÉ (mesure trop bruitée)
   │   0203 : 0→0.167→0.25 (semblait monter) ; 0204 : retombe à ~0.06 (bruit).
   │   ⚠️ confondu : (a) benches 18 parties (±0.08 → on lit du bruit) ;
   │   (b) replay buffer en 0204 a tiré vers les gens passées (plus faibles).
   │   → re-test PROPRE : 0205 (sans buffer, +gens, benches ~54 parties).
   │
   ├─ 🔵 si OUI (montée propre confirmée)
   │   └─ NŒUD 2 — Le RECUIT DE PROFONDEUR relève-t-il le point fixe vers Scan ?  (après 0205)
   │       │   (mt30 → 60 → 100 → 200, quelques cycles/palier, ~500k)
   │       │   ⚠️ replay buffer : NE PAS utiliser en régime montant (ancre au passé).
   │       │
   │       ├─ 🔵 OUI, grimpe vers Scan  →  ✅ VOIE GAGNANTE : scaler, bencher vs Scan
   │       │      à chaque palier, s'arrêter quand un palier plafonne et le suivant
   │       │      ne bouge plus. (indépendance PRÉSERVÉE)
   │       │
   │       └─ 🔵 NON, plafonne sous Scan malgré la profondeur  →  NŒUD 3
   │
   └─ ⚠️ NON, plat / descend
       └─ NŒUD 1bis — Profondeur ou BUG ?  (discriminateur cheap)
           │   test : rejouer la boucle avec jeu PLUS PROFOND (mt100+)
           │   ⚠️ DIRECTIVE (user) : « si plat PROFOND, on cherche le BUG, PAS de
           │   pivot non-linéaire — c'est la MÊME infra que Scan, donc ça DOIT monter ».
           │
           ├─ 🔵 grimpe avec profondeur  →  rejoint NŒUD 2 / voie gagnante
           └─ 🔵 toujours plat  →  NŒUD 2ter (DEBUG), PAS Nœud 3


NŒUD 2ter — DEBUG du pipeline  📍⭐  (la classe N'EST PAS le suspect)
   │   Scan prouve que pattern-linéaire + WDL self-play itéré MONTE. Si la nôtre
   │   est plate, l'infra diverge de Scan quelque part. Suspects vérifiés / à vérifier :
   │
   ├─ ✂️ B1 — « le self-play n'utilise pas l'eval qui évolue » → FAUX (2026-06-13).
   │        set_nnue() + recherche pilotent bien le jeu ; un échec de load est
   │        BRUYANT (return 1 → le job abort), pas silencieux ; les valeurs proxy
   │        réelles de 0205b prouvent que les .pjtw frais se chargent. Test #1 clos.
   │
   ├─ ⭐ B2 — FAMINE DE DONNÉES (le suspect n°1, mesuré 2026-06-13).
   │        Table = 17 006 112 buckets (32 patterns × 3¹²). À 30k positions :
   │        SEULS ~1.0 % des buckets sont touchés ; 62 % des touchés ont ≤2 visites
   │        (poids = bruit tiré au prior l2 ≈ 0). À 300k/gen (0205b) la table reste
   │        ~97 % non-estimée → l'eval ≈ matériel + petite tête fréquente → proxy
   │        PLAT à ~0.41 PAR CONSTRUCTION. Et chaque gen régénère 300k FRAIS (pas
   │        d'accumulation) → couverture constante gen-après-gen → aucun compounding.
   │        Scan « même infra » monte parce qu'il estime DENSÉMENT sa table (corpus
   │        énorme). FIX (reste linéaire, reste Scan) : VOLUME/gen ×10–50 (millions)
   │        et/ou corpus CUMULÉ dominé par les gens récentes. → job sweep-volume.
   │
   ├─ 🔵 B3 — Rois invisibles aux patterns (extract_indices lit men-only ;
   │        31 % des positions ont un roi). C++ et Python sont COHÉRENTS (pas un
   │        bug de correctness) ; les rois entrent via les extras (compte+mobilité).
   │        Limite représentationnelle, pas une panne. À garder en réserve — NE PAS
   │        confondre avec « enrichir la classe » (ce serait le pivot interdit).
   │
   └─ 🔵 B4 — Mesure : le proxy lit l'accord avec les SCORES Scan-d10, pas la FORCE
            en parties. Confirmer un palier au SPRT/Elo (tools/sprt_elo.py) avant de
            conclure « plat = n'apprend pas ».

NŒUD 3 — (seulement APRÈS Nœud 2ter épuisé) la classe linéaire plafonne vraiment
   │   ⚠️ verrouillé tant que le DEBUG (Nœud 2ter) n'a pas été mené à terme.
   │
   ├─ 🔵 C1 — Géométrie plus RICHE (plus / meilleurs patterns, à la Scan).
   │        Reste linéaire & rapide. Incertain : nos tests géométrie passés
   │        (v6 diagonale, régions) étaient ~neutres ou instables en profondeur.
   │
   ├─ 🔵 C2 — Modèle NON-LINÉAIRE (NNUE à entrées-patterns). ⚠️ DÉPRIORISÉ par
   │        directive user : NE PAS pivoter avant d'avoir épuisé le DEBUG (Nœud 2ter).
   │        Coûte du NPS ; doit battre la pattern-eval (v15-NNUE naïf était PIRE).
   │
   └─ 🔵 C3 — Scan comme PROF (renoncer à l'indépendance pour un seed fort).
            Distiller Scan plus profond/proprement, ou bootstrap Scan → fine-tune
            self-play. Fallback si le teacher-free plafonne trop bas.


NŒUD 4 (transverse) — Indépendance vs force
   Si teacher-free plafonne mais Scan-distill (champion) reste le meilleur,
   trancher : l'indépendance est-elle un hard-requirement, ou accepte-t-on
   Scan-bootstrap-puis-self-play ? (décision produit, pas technique)
```

---

## Détail des nœuds (statut · critère · job qui tranche · action)

| Nœud | Statut | Critère de décision | Tranché par | Action si vrai |
|---|---|---|---|---|
| **1** boucle WDL monte | ⚠️ plate au proxy (0205b mt30 ~0.41) | courbe propre (sans buffer, ~54 parties) ↑ | 0205b PLAT → Nœud 1bis | si plat → DEBUG |
| **1bis** profondeur ou bug | 🔵📍 en cours | grimpe à mt100 ? | 0207/0208 (mt100) | si plat → Nœud 2ter |
| **2ter·B1** eval pas utilisée | ✂️ FAUX (2026-06-13) | self-play change avec --nnue | inspection + load-bruyant + proxy 0205b | clos |
| **2ter·B2** famine de données ⭐ | 🔵📍 suspect n°1 | proxy(gen1) ↑ avec le VOLUME | **sweep-volume à créer** | scaler volume/cumul |
| **2ter·B3** rois invisibles | 🔵 réserve | — (cohérent C++/Py) | inspection 2026-06-13 | limite, pas panne |
| **2ter·B4** mesure proxy≠force | 🔵 | palier confirmé au SPRT | tools/sprt_elo.py | valider avant verdict |
| **3** classe linéaire plafonne | 🔒 verrouillé | APRÈS Nœud 2ter épuisé | — | ne pas pivoter avant |
| **4** indépendance | 🔵 décision | — | humain | trancher le requirement |

---

## Cimetière — branches ✂️ ÉLAGUÉES (ne JAMAIS re-tester)

| Branche | Pourquoi morte | Preuve |
|---|---|---|
| Ajouter des techniques de **recherche** | déjà complète | ARCHITECTURE.md |
| **Vitesse / NPS** comme levier principal | +4 plies ne compensent pas l'eval | 0201 |
| **Deep-score relabel** (labels = score de recherche) | distillation → plafonné au générateur | 0200/0202 |
| **WDL 1-cycle** (sans itérer) | ne monte pas ; un cycle ≠ compounding | 0196 |
| **Sweep l2** sur self-play | optimum établi ∈ [3e-4, 3e-3] | 0196/0198/0200/0202 |
| **Bencher contre v15** comme juge de force | v15 ≈ 0 vs Scan (flatteur) | 0197/0199 |
| Plus de **data** / teacher plus **profond** (distill) | neutre une fois labels propres | historique (4.7M≈1.4M, d16≈d10) |
| **Gros MLP** (1024-512) | overfit ; 0.009 movetime vs Scan | 0071/0088 |
| **Corpus master 10M** | €700+ pour +30-80 ELO vs déficit −800 | SESSION_LOG |
| **quiet-filter** (post-score-drop) · **augmentation symétrie** · **self-distillation itérée** | nuisent / dérivent | historique (0185, etc.) |
| **Replay buffer en régime MONTANT** | ancre l'eval vers les gens passées (plus faibles) → tire vers le bas | 0204 (0.25→0.06) |
| **Benches 18 parties** pour juger des taux faibles | bruit ±0.08 → on lit du bruit comme un signal ; viser ≥54 parties | 0203/0204 |
| **« Le self-play ignore l'eval qui évolue »** (hypothèse bug) | FAUX : set_nnue+recherche pilotent ; load échoue BRUYAMMENT (job abort), pas en silence | inspection + test 2026-06-13 |
| **Pivot non-linéaire AVANT debug** | directive user : même infra que Scan → ça doit monter ; chercher le bug d'abord | 2026-06-13 |
| **Charger les .pjtw champions COMMITTÉS** (pattern_clean, A, …) | format périmé : n_pat=4 251 528 (8 patterns) ≠ TOTAL_BUCKETS=17 006 112 (32) ; la géométrie a ×4 depuis | loader 2026-06-13 |

---

## Comment on met à jour
À chaque finalize de job : (1) marquer le nœud testé ✂️ ou 🟢/🔵 ; (2) déplacer
le 📍 ; (3) si une nouvelle impasse apparaît, l'ajouter au cimetière avec sa
preuve (job). Garder l'arbre **court** — le détail va au JOURNAL.
