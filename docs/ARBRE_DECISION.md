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
       └─ NŒUD 1bis — Profondeur ou features ?  (discriminateur cheap)
           │   test : rejouer la boucle avec jeu PLUS PROFOND (mt100+)
           │
           ├─ 🔵 grimpe avec profondeur  →  rejoint NŒUD 2 / voie gagnante
           └─ 🔵 toujours plat  →  NŒUD 3


NŒUD 3 — La CLASSE LINÉAIRE plafonne sous Scan → changer de capacité
   │
   ├─ 🔵 C1 — Géométrie plus RICHE (plus / meilleurs patterns, à la Scan).
   │        Reste linéaire & rapide. Incertain : nos tests géométrie passés
   │        (v6 diagonale, régions) étaient ~neutres ou instables en profondeur.
   │
   ├─ ⭐🔵 C2 — Modèle NON-LINÉAIRE (NNUE à entrées-patterns : casse
   │        l'additivité entre patterns — le vrai plafond de la classe linéaire).
   │        Coûte du NPS, MAIS 0201 dit que la vitesse n'est pas bloquante →
   │        une eval plus précise même un peu plus lente vaut le coup.
   │        ⚠️ doit être > la pattern-eval (v15-NNUE naïf était PIRE) :
   │        entrées = patterns incrémentaux + petite tête int8/AVX2.
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
| **1** boucle WDL monte | 🔵📍 non tranché | courbe propre (sans buffer, ~54 parties) ↑ | 0203/0204 ambigus → **0205** | si ↑ → Nœud 2 |
| **2** recuit profondeur | 🔵 après 0205 | grimpe par palier de profondeur | jobs à créer | scaler = voie gagnante |
| **3·C1** géométrie riche | 🔵 | bat la linéaire de base vs Scan | job à créer | étendre patterns |
| **3·C2** non-linéaire ⭐ | 🔵 | NNUE-pattern > pattern-eval vs Scan | job à créer | basculer archi eval |
| **3·C3** Scan-prof | 🔵 fallback | distill profond > teacher-free | job à créer | abandonner l'indépendance |
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

---

## Comment on met à jour
À chaque finalize de job : (1) marquer le nœud testé ✂️ ou 🟢/🔵 ; (2) déplacer
le 📍 ; (3) si une nouvelle impasse apparaît, l'ajouter au cimetière avec sa
preuve (job). Garder l'arbre **court** — le détail va au JOURNAL.
