# Arbre de décision — programme « battre Scan »

> **Doc VIVANT.** À chaque verdict de job, on **élague** (✂️ une branche morte,
> avec sa raison) ou on **active** (🟢) la branche à explorer. Lire avec
> [JOURNAL_DE_BORD.md](JOURNAL_DE_BORD.md) (ancres + faits) et
> [ROADMAP.md](ROADMAP.md). Mise à jour : **2026-06-15** (campagne finales + recherche 0249-0263).
>
> **Légende** : 🟢 chemin actif · 🔵 branche ouverte (à explorer) · ✂️ élaguée
> (morte, raison donnée) · ⭐ candidat le plus probable · 📍 position actuelle.

---

## 🟢 Branche ACTIVE 2026-06-16 — verrou finale par bitbase egdb exacte

📍 **Position** : bitbase egdb **scellée** (WLD 2→7, 164/164) → on attaque le verrou
roi-finale avec des **labels EXACTS** (≫ depth-16). Cf [EGDB_SELFPLAY_PLAN.md](EGDB_SELFPLAY_PLAN.md).

- ✂️ **0274 (coverage depth-16)** — ÉLAGUÉE : labels par recherche imparfaite,
  **supplantés** par le WLD exact de la bitbase. Job tué.
- ✂️ **Jeu-parfait-finale / couverture (0287)** — VERDICT : endgame-rois **3.22 ≈ 3.06**
  (PAS mieux) malgré labels EXACTS (val-mse ÷3.5), vs Scan **−741**. → **la couverture
  N'EST PAS le verrou**. ÉLAGUÉE comme levier finale.
- 🟢⭐ **ARCHI / CAPACITÉ ÉVAL** (activée par 0287) : l'éval linéaire ne représente pas la
  relation roi-roi. Ordre : (1) **features king-king riches** (table déplacement relatif
  roi-roi — la 1ère, moins risquée) → (2) **tête non-linéaire MLP** sur positions de rois
  → (3) **MTC** (court-circuit éval, Scan ne l'a pas). Cible : endgame-rois ≪ 3.06.
- 🟢 **Relabel + coverage exacts** (`--egdb-relabel`, `--gen-egdb-wld`, validés 0292) :
  briques (2)+(3) de la boucle — densité finale exacte et gratuite.
- 🔵 **Depth-ramp sur l'entre-deux 8-21p (0293)** : `late-mid=12,endgame=16` → la
  recherche mord dans la TB → labels de transition ancrés-TB. ⏳ A/B vs uniforme-8.
- 🟢 **minibatch = outil mémoire** (0291 : moitié RAM) pour scaler le cumulatif
  gonflé par la coverage. Exactitude ⏳ (0294, convexe → doit converger au même optimum).
- ⭐ **Candidat le plus probable** : si 0287 casse → boucle complète egdb + minibatch ;
  si plafonne → archi éval (le linéaire king-aware ne représente pas la finale-rois).

## Acquis (racine — déjà tranché)

- **Levier = l'EVAL** (principal) **+ la RECHERCHE** (réactivé 2026-06-15). La
  recherche n'est PLUS un levier mort : **NMP est net-négatif en jass** (zugzwang
  omniprésent → −% Elo ; sweep 0256/0259 : désactiver NMP = jusqu'à **+97 Elo**) et
  l'**improving-heuristic** = +22 (0253). Vitesse pure reste secondaire (0201).
- **Juge = Scan** à profondeur égale (✂️ v15 : flatteur, ≈ 0 vs Scan).
- **Cible label = WDL itéré** (production). La **distillation sur SCORE** n'est PAS
  morte comme source de qualité (0261 : +141 vs hc, > distill-WDL 0237 +90) mais reste
  sous le self-play en force globale ✂️ comme éval unique. ✂️ WDL 1-cycle (0196).
- **Phase faible = la FINALE** (autopsies 0249/0250 : ≈Scan en ouverture/milieu, saigne
  en finale à rois). Attaquée par : (a) **play profond en finale** (`--play-depth-by-phase`,
  Chemin B) pour des WDL de finale fiables ; (b) la recherche (NMP off). PAS par pondération.

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
   ├─ 🟢⭐ B3 — Rois invisibles aux patterns → **LE BUG STRUCTUREL, CORRIGÉ (2026-06-14).**
   │        Nos patterns lisaient men-only → une case avec un roi = VIDE. Scan, lui,
   │        compte un roi comme « pièce » (base-3 amalgamé man|king). Donc « même infra
   │        que Scan » était FAUX : c'était une DIVERGENCE, pas une simple limite « en
   │        réserve ». Le fix (`-DJASS_KING_PATTERNS=ON` + `train.py --king-patterns`,
   │        occupation = men|kings, valeur du roi toujours dans les extras) est 100 %
   │        LINÉAIRE (= Scan, PAS base-5 = jass v2 raté) → ce n'est PAS le pivot interdit.
   │        VALIDÉ `0240` : **+37 Elo vs hc** sous distillation (+78 → +115), val-loss
   │        0.613→0.602. → embarqué dans le loop scalé `0241` (📍 le push en cours).
   │
   └─ 🔵 B4 — Mesure : le proxy lit l'accord avec les SCORES Scan-d10, pas la FORCE
            en parties. Confirmer un palier au SPRT/Elo (tools/sprt_elo.py) avant de
            conclure « plat = n'apprend pas ».

NŒUD 3 — (seulement APRÈS Nœud 2ter épuisé) la classe linéaire plafonne vraiment
   │   ⚠️ verrouillé tant que le DEBUG (Nœud 2ter) n'a pas été mené à terme.
   │
   ├─ 🟢📍⭐ C1 — **PARTAGE DE POIDS PAR SYMÉTRIE** (la brique manquante, cf docs/
   │        SYMMETRY_SHARING.md + ARCHITECTURE.md). Audit vérifié sur la SOURCE Scan :
   │        Scan lie ses poids par couleur + rot180 + réflexion (translation = 4
   │        positions distinctes) → 2.1M poids DENSES ; nous = 17M INDÉPENDANTS,
   │        affamés. Reste 100 % LINÉAIRE. **BRIQUES IMPLÉMENTÉES + VÉRIFIÉES
   │        (2026-06-13)** dans train.py (fold puis EXPAND vers .pjtw 17M standard,
   │        C++ inchangé) :
   │          color-fold (17M→8.5M) → rot-fold (4.9M, rot∘cs EXACT) → trans-fold
   │          (1.2M, approx) → full-fold +réflexion LR EXACTE (1.0M) →
   │          **géométrie LR-CLOSE 54 patterns (gen_patterns.py --lr-close) → 0.6M
   │          ≈ échelle Scan**, 0 orphelin, symétries exactes vérifiées, tests OK.
   │        Mesuré en **Elo RÉEL** (A/B échelle, 5 bras, 0220-0224 en cours ; LR-close
   │        0225/0226 prêt, déployé après l'A/B 32-pattern pour ne pas confondre).
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
| **2ter·B2** famine de données ⭐ | 🟢 CONFIRMÉE (partiel) | proxy ↑ avec couverture | **0210 (0.40→0.46) + 0211 (0.41→0.45)** vs 0205b PLAT | data = un mur (réglé +0.05) |
| **2ter·B5** 2e mur ~0.46 (PAS data) | ✂️ ARTEFACT (résolu) | — | rois NEUTRE · profondeur NON · **B4 = proxy sous-lit** | métrique, pas un mur |
| **2ter·B4** proxy ≠ Elo réel ⭐ | 🟢 CONFIRMÉ (0216) | gen0→gen5 = −20→+60 Elo vs hc (**+80**, CI disjoints) alors que proxy plat 0.40→0.43 | parties réelles 1440 | **RETIRER le proxy** ; mesurer en Elo réel (SPRT) ; SCALER |
| **gap absolu** | 📍 énorme | gen5 vs Scan d9 = **0/1080** | 0216 | encore très loin de Scan → scaler longtemps |
| **2ter·B3** rois invisibles ⭐ | 🟢 **BUG CORRIGÉ (0240)** | divergence vs Scan (men-only vs piece-presence) ; king-aware **+37 Elo vs hc** (+78→+115), val-loss 0.613→0.602 | 0240 | `-DJASS_KING_PATTERNS=ON` + `--king-patterns` ; embarqué dans le loop scalé 0241 |
| **2ter·B4** mesure proxy≠force | 🔵 | palier confirmé au SPRT | tools/sprt_elo.py | valider avant verdict |
| **3·C1** partage de poids par symétrie ⭐ | 🟢 VALIDÉ (modeste) | A/B Elo précis : **trans +177 · full +175 vs men-only +148** (2 folds lourds concordent → +30 RÉEL ; color/rot nuls) | 0220-0227 (depth4, 2.6M) | full-fold adopté ; **géométrie = levier MORT** (prune 0234 −31 Elo & 0 vitesse ; sweep 0239 plat 0.60-0.62 de 15→54 pat) → reste : kings (B3) + data |
| **géométrie LEAN** (prune/élagage) | ✂️ MORTE | RFE drop-8 (0234) = **−31 Elo ET 0 vitesse** ; sweep distillation (0239) plat | 0234/0239 | la lenteur d'eval est dans les 106 extras, pas les lookups ; importance uniforme |
| **3·C1b** loop scalé KING-AWARE 📍⭐ | 🟢 EN COURS | trajectoire vs baselines men-only 0227 +175 / 0231 +142 | 0241 (king-aware + 600k/gen) | LE push : pousser la classe linéaire à son max (kings + data) |
| **3·C2** non-linéaire | 🔒 DÉPRIORISÉ | seulement si la symétrie+linéaire plafonne en Elo | — | ne pas pivoter avant |
| **3·C3** Scan-prof (fallback) | 🔵 | teacher-free plafonne sous Scan | — | abandonner l'indépendance |
| **4** indépendance | 🔵 décision | — | humain | trancher le requirement |

---

## Cimetière — branches ✂️ ÉLAGUÉES (ne JAMAIS re-tester)

| Branche | Pourquoi morte | Preuve |
|---|---|---|
| ~~Techniques de recherche « déjà complète »~~ | **RÉVISÉ 2026-06-15** : NON — NMP net-négatif (+97 à désactiver), improving +22. La recherche est un LEVIER VIVANT. | 0253/0256/0259 |
| **`--phase-weight`** (densifier la finale en pondérant les lignes) | **MORTE** : −210 Elo sur bons labels score (0261), neutre/négatif sur WDL (0254/0257). Sur-pondérer les scores de grande magnitude de finale dé-calibre l'éval du gros du jeu. | 0254/0257/0261 |
| **Filtre de STABILITÉ de recherche** (garder les positions où le score converge) | **INUTILE en finale** : nos erreurs de finale sont SYSTÉMATIQUES (stables), pas du bruit — éval confiante ET fausse en finale à rois. accord(stable)=0.917 ≈ accord(instable)=0.938 (gain −0.021). Filtre le bruit, pas le biais. | 0267 |
| **Densif finale CIBLÉE dans la boucle WDL** (poids / label-depth / play-depth-finale) | **MORTE** (3 confirmations) : phase-weight −210, label-depth −80, play-depth-finale −30. Le WDL est trop grossier pour la précision de finale ; play-finale-seul = incohérence. | 0254/0261/0265 |
| **`--label-depth-by-phase`** dans la boucle WDL | **MORTE** : no-op (la boucle s'entraîne sur le WDL, pas le score) ET nocif (la recherche de label profonde pollue la TT → corrompt les parties jouées, −80 Elo). | 0254/0258 |
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
