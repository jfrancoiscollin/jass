# Journal de bord — programme « battre Scan »

> **À LIRE AVANT DE (RE)CHERCHER.** Registre court et tenu à jour à chaque
> verdict. Ancres mesurées + faits établis (à ne pas re-litiger) + index des
> jobs. Pour l'analyse détaillée → [PATTERN_PROGRAM_NOTES.md](PATTERN_PROGRAM_NOTES.md).
> Pour ce qui est **codé** → [ARCHITECTURE.md](ARCHITECTURE.md).
> Pour **comment on en est arrivé là** → [§6 Historique](#6-historique-du-projet--le-cheminement-0001--0202).
> Pour **quel chemin prendre selon quel verdict** → [ARBRE_DECISION.md](ARBRE_DECISION.md).
>
> Mise à jour : **2026-06-14** (BRIQUE ROIS — le bug structurel vs Scan, corrigé.
> Géométrie close (levier mort). Le push en cours = loop full-fold **king-aware + scalé** 0241).

---

## 0. Dernier verdict — 2026-06-17 (saturation apparente + gradient mort + PRINCIPE)

> ## ⛔ PRINCIPE DIRECTEUR — NON NÉGOCIABLE (redit par JFC, 2026-06-17)
> **On a la MÊME architecture que Scan (éval LINÉAIRE sur patterns). On DOIT donc
> pouvoir l'égaler DANS la classe linéaire. Le gap n'est PAS un manque de capacité :
> c'est quelque chose qui nous MANQUE** (d'abord les **patterns/features de
> finale-rois** — Scan capture la conversion via ses patterns ; puis l'**équilibre
> d'entraînement** finale/midgame ; puis la **recherche**). **INTERDIT de reproposer
> FM/MLP** tant que la voie linéaire n'est pas *prouvée épuisée* (= on a trouvé et
> corrigé ce qui manque, pas « le loop plafonne »). Détail : [ARBRE_DECISION.md](ARBRE_DECISION.md).

**Faits établis (à ne pas re-litiger) :**

- **0297 (saturer le linéaire, 6 gen) — AUCUN GAIN + le loop RÉGRESSE.** gen6 60p vs hc
  **+234** (= 0287/0276) ; vs Scan **−800** (0/54) ; endgame-rois deep-eg **3.06** — le loop
  6-gen **perd le 2.04 du depth-ramp 1-gen 0293**. Elo culmine gen1-3 (+253)→↘+194 ;
  endgame_mse ↑ 1.8→5.4. → *apparente* saturation, **mais voir le principe : c'est un
  indice qu'il manque quelque chose, pas une preuve.**
- **0306 (gradient conversion proxy+MTC) — NE TRANSFÈRE PAS.** Cible mieux ajustée
  (endgame_mse 5.39→3.79) mais **joue la finale plus mal** (deep-eg 2.91→3.78, Elo −20,
  vs Scan inchangé). Cause : **148 vrais signaux MTC sur 3,7 M** (99,9 % proxy
  matériel/centralité → mauvais maître). **Gradient-cible = cul-de-sac.**
- **0309/0310 (diagnostic du drift) — VERDICT : PAS de saturation, c'est un CONFLIT DE PHASE
  (linéaire-réparable).** 0 contradiction ≤7p (labels propres). Ablation : **NO-ENDGAME Elo
  +268 ≫ FULL +222** (les finales TIRENT le fit global −46 Elo) ; **ENDGAME-ONLY deep-eg mse
  3.27 ≪ FULL endgame mse 5.39** (le linéaire fitte la finale BIEN mieux **seul**). Donc la
  classe linéaire **n'est PAS le goulot** — le midgame (89 % des données) écrase la finale dans
  les poids partagés. **Fix linéaire** : (a) séparer le fit finale/midgame (phase-split plus
  dur) ; (b) **donner à la finale ses propres features** (king-mobility, LEAD 1, job 0311) pour
  qu'elle cesse de distordre les men-patterns. ⇒ **confirme le PRINCIPE : pas la capacité,
  c'est ce qui MANQUE + l'équilibre.**
- **0311 (king-features A/B, LEAD 1+2)** : les features rois AIDENT vs hc — kmob (+33), **endg
  (+87, le meilleur arm)**, kingpat ~neutre. MAIS endgame_mse *monte* et vs Scan reste 0/54.
  → **`endg` (JASS_ENDGAME_FEATURES) BAKÉ par défaut (ON)** [NUM_EXTRAS 106→110]. *Caveat : bench
  60-parties bruité (base +171 vs +234 ailleurs) → réversible si une mesure propre déçoit.*
- **0312 (phase-split, fix-b 0310)** : raidir la rampe (8/18) **fait tomber endgame_mse à 3.03**
  (< plancher 3.27 → **PAS de saturation, re-confirmé**) MAIS **l'Elo baisse** (+184→+158 : sacrifie
  le midgame). Rampe gardée au défaut 0/40.
- **⚠️ LEÇON MÉTHODO (0311+0312)** : `endgame_mse` et Elo bougent **en sens INVERSE** dans les deux
  → **`endgame_mse` est un mauvais proxy de force.** Arrêter le mse-chasing ; mesurer la FORCE
  (plus de parties + **autopsie endgame-rois vs Scan**), seul juge réel de la finale.
- **LEAD 3 en cours (0313, ccx33)** : dataset finale-enrichi (coverage ≤7p + self-play egdb-perfect,
  ~45% finale vs 11%) pour nourrir le run COMBINÉ king-features + phase-split.
- **Livre d'ouverture à la Scan** (0307/0308) : valeurs de feuilles SAINES (spearman 0.844, 0 piège)
  mais **trop plat** (max ply 10) et **accord-coup vs Scan faible (42%)** car construit sur l'éval
  jass → s'améliorera avec l'éval. Secondaire. *(0307 tué à 11h : matchs sur-dimensionnés.)*

## 0bis. Verdict précédent — 2026-06-16 (BITBASE egdb + outils self-play exact)

**Faits établis (à ne pas re-litiger) :**

- **Bitbase egdb SCELLÉE** : WLD Kingsrow 2→7 pièces téléchargée+extraite sur les 2
  boxes, **self-test natif 164/164**, conversion bit-à-bit validée, **guard <3 pièces**
  (le slice db2 rend un décisif faux sur quelques KvK → on défère à KvK=Draw exact).
  egdb a aussi **révélé que nos tables internes 2v1/3v1 sur-revendiquent** les gains.
  → Procédure : [BITBASE_INTEGRATION.md](BITBASE_INTEGRATION.md). Plan d'usage :
  [EGDB_SELFPLAY_PLAN.md](EGDB_SELFPLAY_PLAN.md).
- **VERDICT 0287 + 0293 — le verrou finale = la classe linéaire PAS ENCORE SATURÉE
  (training/labels), PAS la capacité.** ⚠️ *correction d'un verdict 0287 trop hâtif.*
  - **0287** (egdb-perfect, **profondeur-8 uniforme**) : val endgame-mse ÷3.5 (2.98→0.84)
    mais endgame-rois vs Scan inchangé (3.22), vs Scan −741. J'en avais conclu « capacité ».
  - **0293 le DÉMENT** : à labels exacts ≤7 identiques, **approfondir l'entre-deux 8-21**
    (`--play/--label-depth-by-phase late-mid=12,endgame=16`) fait chuter endgame-rois
    **2.86→2.04 (−29 %)** ET **+74 Elo** (+106 vs +32). Donc un levier **données/labels**
    (la recherche profonde mord dans la TB → labels de transition ancrés) **marche encore**
    → la classe linéaire **n'est pas saturée**. 0287 sous-testait (depth-8 n'atteint pas la
    TB depuis 8-21).
  - **Stratégie actée (PATTERN_PROGRAM_NOTES) confirmée** : **Scan est dans notre classe**
    (logistique linéaire sur patterns). Pour l'ÉGALER → saturer la classe linéaire (cycles,
    patterns, data, bitbases), **PAS de FM/MLP** (= au-delà de Scan, prématuré ; FM déjà
    rangé là en 0184). ✂️ **Branche "capacité/FM" rétractée** (0296 FM annulé). 🟢 **Levier
    actif = saturer le linéaire** : egdb-perfect + depth-ramp + coverage + multi-gen.
- **Features de finale = +28 Elo** (0276) — un levier données qui aide (classe pas saturée).
  Code intact (`JASS_ENDGAME_FEATURES`, NUM_EXTRAS 110).
- **Outils labels exacts codés+validés (0292)** : `--gen-egdb-wld` (coverage aléatoire
  quiète ≤7p, distribution saine, 0 one-sided) et `--egdb-relabel` (réécrit WDL ≤7p,
  idempotent). Les briques (2)+(3) de la boucle cible.
- **⭐ STALL POLLUTION (0295) + fix `terminate-at-TB`.** 0295 a MESURÉ que **~50 % des
  positions de finale DÉCISIVES en self-play STALLENT** : finale gagnée non convertie (le
  moteur tourne en rond) → règle de nul → partie enregistrée NULLE → **label de finale
  FAUX**. Ça polluait TOUT l'entraînement finale **depuis le début, y compris 0287**
  ("egdb-perfect" jouait ≤7 parfait coup-par-coup mais la PARTIE stallait quand même →
  étiquette nulle). → Fix **`terminate-at-TB`** (codé `gen-data-wdl`) : dès qu'une partie
  atteint une position egdb-résolue ≤7, on la **termine au résultat TB EXACT** (les
  positions de transition 8-21 héritent du bon résultat). Labels de finale enfin propres,
  **sans MTC**. **0297** = 1er run qui en profite. (Le fix distance-aware `search.cpp`
  score-TB `−ply` ne corrigeait que ~12 % des stalls — 0295.)
- **0294 — minibatch EXACT** : à convergence (300 it), `train_loss` lowmem **0.569193** ≡
  minibatch **0.569173**, et **moitié RAM** (11.6 vs 21.9 GB). Validé comme outil de scaling
  quand le cumulatif dépasse **~7M** (plafond lowmem/32GB) ; en dessous, lowmem suffit.
- **🟢 GRADIENT de conversion — CODÉ + chaîne validée (le "comment convertir").**
  terminate-at-TB corrige la *valuation* mais PAS la *conversion en match*. **Scan convertit
  SANS MTC**, via le **GRADIENT de son éval** ; notre cible **WLD est PLATE** (gain=1 partout)
  → l'éval ne peut pas apprendre "plus proche de la conversion". Solution : un signal de
  distance dans la **CIBLE**, appris offline, qui **généralise à 8-21** → **pas de MTC au jeu**.
  - **MTC téléchargé+extrait sur les 2 boxes** (2-8 pièces, ~29 GB ; download 0300/0301 après
    gros nettoyage disque). `egdb::init_mtc/probe_mtc` (handle séparé, `is_mtc`-vérifié, 0302).
  - **MTC est COARSE** (0302) : 99.75 % des gains sont à <10 plies (MTC=1, plat — la base ne
    stocke pas <10) ; seulement 0.25 % ont une distance réelle (≥10). → gradient seulement
    dans la zone de manœuvre ≥10 (= la zone de stall), rien dans le <10.
  - **→ HYBRIDE proxy+MTC** (`--egdb-mtc-relabel`) : `winp = 1 − ALPHA·pièces_adverses −
    GAMMA·centralité_roi_adverse − BETA·max(0,MTC−10)`, clampé [0.55,1], STM-POV. Le **proxy**
    (matériel+confinement) comble le <10 plat, le **MTC** donne l'exact ≥10. Stocké en
    `score=prob×10000`, entraîné par **`train.py --target prob`** (loss logistique sur
    score/10000) → garde le **régime WDL-logistique prod** pour la masse, injecte le gradient
    en finale. ALPHA=0.04, GAMMA=0.008, BETA=0.03 (tunables).
  - **Chaîne validée end-to-end (0303)** : `gen-egdb-wld → mtc-relabel → train --target prob`
    tourne. Reste : vrai run gradient (coverage enrichie ≥10-MTC + self-play) → mesurer la
    conversion vs Scan. (Alternatives écartées : (b) DTW maison ≤5-6 ; (c) proxy seul.)
- **minibatch vs lowmem (0291)** : minibatch = **moitié RAM** (11.6 vs 21.9 GB sur 5.1M)
  → l'outil mémoire pour scaler (crossover lowmem ≈ 7M lignes/32GB). **Le wedge 5h de
  0274 n'était PAS un thrash lowmem** (lowmem 5M = 4 min, tient à 22 GB) → one-off.
  Exactitude minibatch (problème convexe → optimum unique) **à confirmer à convergence
  (0294)** : à 80 it, mse 2.94 vs 3.03 (sous-convergé).
- **Micro-optims movegen mergées en prod** : `MoveList::reserve(48)` + promo-split
  bitboard (coups identiques, 6428 tests incl. perft). Géométrie pattern_jass 54
  **fermée** (✂️ 32 déjà optimal). Test scan_eval king-aware **corrigé** (était rouge
  dans tout build king-aware — bug de test, pas d'éval).

**En cours :** `0287` (jeu-parfait-finale egdb casse-t-il le verrou ?) · `0293` (A/B
profondeur `late-mid=12,endgame=16` sur l'entre-deux 8-21p) · `0294` (exactitude minibatch).

**Index jobs (session bitbase)** : 0274 (coverage depth-16, **tué** — supplanté par
egdb) · 0276 (features self-play, +28) · 0277-0286 (download/extract/build/scellé
bitbase) · 0287 (self-play egdb-perfect) · 0288-0290 (prep cpx62 + guard) · 0291
(contrôle minibatch) · 0292 (outils egdb) · 0293 (A/B profondeur) · 0294 (convergence
minibatch).

---

## 1. Ancres mesurées (durables)

### vs Scan — la VRAIE référence (profondeur égale, no bitbases, harness corrigé)
| | d7 | d9 | d11 | mt 0.5s | source |
|---|---|---|---|---|---|
| **champion** (pattern, distill Scan-d10) | 0.028 | 0.000 | 0.000 | 0.000 | 0199 |
| **v15** (NNUE 128-64) | 0.028 | 0.056 | 0.056 | 0.019 | 0197/0137 |

Handicap de profondeur (champion vs **Scan-d9**) : +0 → **0.000**, +2 → **0.194**,
+4 → **0.083** (0201). v15 vs Scan-d9 : +0 = +4 = 0.056 (plat). → **l'eval est le
gap dominant ; +4 plies ne ramènent pas à parité** (la part « efficacité de
recherche » ≈ 2 plies est mineure).

### vs v15 — sparring-partner INTERNE (commode mais FLATTEUR : v15 ≈ 0 vs Scan)
| eval / cible | d9 vs v15 | source |
|---|---|---|
| master + WDL 1.4M | 0.22 | 0194 |
| self-play + WDL 1M | 0.22 | 0196 |
| self-play + score @30ms (superficiel) | 0.08–0.17 | 0198 |
| **self-play + score deep d12** | **0.31–0.33** (band l2∈[3e-4,3e-3] ; best 3e-3=0.333) | 0200/0202 |
| champion (master + score Scan-d10) | 0.39 | 0141 |

### Vitesse / divers
- NPS : v15-128-64 = **0.92 Mnps** ; Scan ≈ **×8** v15 (0189).
- champion en relabel **d12 = 0.026 s/pos** → 1M/8 cœurs ≈ 0.9 h (relabel cheap).
- Self-play (champion @mt30) : **59.2 % de nulles** vs **18.6 %** master.
- v15 a été entraîné sur labels **Scan-distillés** (0078, `v10-distilled-1M`).

---

## 2. Faits établis — NE PAS re-litiger

1. **La recherche de jass est complète** (TT, ID, aspiration, PVS, LMR, LMP,
   null-move, IID, extensions singulières/promo, multi-cut, killers, history,
   countermoves, quiescence). Cf. checklist [ARCHITECTURE.md](ARCHITECTURE.md).
   **Ne JAMAIS déduire « ça manque » d'un grep par mots-clés** (noms variables).
2. **Bencher contre Scan** (profondeur égale), pas contre v15 — v15 ≈ 0 vs Scan
   donc « X vs v15 » flatte (champion 0.39 vs v15 = ~0 vs Scan).
3. **Le levier est l'EVAL** : la recherche est complète, et la profondeur/vitesse
   ne compensent pas (0201) → la vitesse (×8 NPS) est **secondaire**.
4. **WDL (issue de partie) vs SCORE de recherche — distinction CAPITALE** (corrige
   une fausse piste) : le **score de recherche** (deep-d12) bat WDL en *1 cycle*
   (0.33 > 0.22) MAIS c'est de la **DISTILLATION** — borné par l'eval qui génère
   les labels → **ne peut PAS dépasser son générateur** (d'où le plateau ~champion
   en 0200/0202). Le **WDL** (issue réelle) est borné par **RIEN** → **le seul
   label qui peut compounder jusqu'à Scan**. **Scan = self-play + WDL + logistique
   ITÉRÉ, JAMAIS de score d'eval** (SCAN_ARCHITECTURE_NOTES.md). → la cible pour
   atteindre Scan est le **WDL itéré**, pas le deep-score (= cul-de-sac).
5. **Point fixe WDL** : la boucle WDL converge vers un niveau (~0.22 vs v15 en 1
   cycle mt30). Le champion (0.39, distillé Scan) est **au-dessus** → le WDL le
   tire **vers le bas** (≠ « WDL toxique », on était juste du mauvais côté).
   Scan part de **zéro** (sous le point fixe) → il **monte**. Reste à savoir
   pourquoi notre point fixe est bas : **profondeur de jeu** (mt30 superficiel ?),
   **géométrie**, ou **volume/itérations** — 0203 teste la montée, puis on isole.
6. **WDL plafonne ~0.22** en **1 cycle** quelle que soit la source (master =
   self-play) — mais c'est un palier de cycle-unique, PAS forcément le plafond de
   la boucle itérée (jamais testée avant 0203).
7. **Un cycle de DISTILLATION ≈ le prof, pas au-delà** (deep-d12 0.31-0.33 ≈
   champion 0.39 *dans le bruit*, **0.000 vs Scan**) → ✅ on récupère le champion
   teacher-free, ❌ mais c'est de la distillation (cf. fait 4) → pas de
   compounding possible. Le bon levier est le **WDL itéré** (fait 4), pas ça.
8. **Régularisation par cible** (à ne plus re-balayer) : self-play → **l2 ∈
   [3e-4, 3e-3]** (1e-4 et 1e-2 s'effondrent ; 0196/0198/0200/0202) ;
   master-distill (champion) → l2=1e-4.

---

## 3. Index des jobs (récents)

| job | objet | finding 1-ligne |
|---|---|---|
| 0196 | self-play 1M WDL @mt30 + logistic | WDL plafonne 0.22 (= master) ; volume aidait |
| 0197 | v15 vs Scan profondeur égale | 0.028/0.056/0.056 ; harness corrigé (fin des coups illégaux) |
| 0198 | même data, cible score @30ms | 0.08–0.17 < WDL → score superficiel = mauvais prof |
| 0199 | **ré-ancrage** champion vs Scan | champion ≈ v15 ≈ 0 → 0.39 vs v15 était flatté |
| 0200 | relabel 1M **d12** teacher-free + train | **levier deep confirmé** : 0.306 vs v15 (< champion 0.39, 0 vs Scan) |
| 0201 | handicap de profondeur vs Scan-d9 | **l'eval est le gap** (+4 plies ne ramènent pas à parité) |
| 0202 | **sweep12** (l2 sur deep-d12) | plafond cycle-1 ≈ **0.33** ≈ champion, **0 vs Scan** → deep-score = distillation, plafonné |
| 0203 | boucle WDL itérée depuis seed faible | 0→0→0.167→**0.25** vs v15 — *semblait* monter, mais ⚠️ benches 18 parties (bruit) |
| 0204 | continuation (gen4→7) **+ replay buffer** | ⚠️ **retombe ~0.06** : le 0.25 NON reproduit. Confondu : buffer (ancre au passé) + bruit 18 parties. **Nœud 1 non tranché** |
| 0205 | re-test PROPRE : boucle SANS buffer, +gens, benches ~54 parties | *à lancer* — la boucle monte-t-elle vraiment, mesurée correctement ? |
| 0227 | boucle full-fold itérée (8 gens, sym complet, 17M→1M) | **+175 vs hc** (gen8) — meilleur de la classe linéaire via la boucle (vs hc) |
| 0230 | pattern_importance (std·\|corr\| + redondance) sur full-fold | **importance UNIFORME** : aucun pattern mort, redondance ≤0.40 |
| 0231 | RFE bras témoin 32-pat (réplique 0227) | **+142 vs hc** (60p) ; vitesse knps/hc=0.653 ; reproduit 0227 |
| 0234 | RFE bras élagué 24-pat (drop-8, reset-proof) | **+110 vs hc** = **−31 Elo** et **0 vitesse** (0.648) → élaguer = lose-lose |
| 0235 | ancre Scan réelle (d9 + mt1s) | ✂️ **FIGÉ ~8h** sur l'arme depth-9 sans plafond temps → tué (`kill-in-flight`) ; leçon : **borner au movetime** |
| 0237/0239 | plafond distillation + sweep géométrie | val-loss men-only **plate ~0.60** de 15→54 patterns → ni data ni géométrie : représentationnel |
| 0240 | **BRIQUE ROIS** (men-only vs king-aware sous distillation) | **+37 Elo vs hc** (+78→+115), val-loss 0.613→0.602 → les rois = le bug structurel, corrigé |
| 0238 | autopsie men-only vs Scan (`game_autopsy.py`) | *en vol* — où on perd (phase × rois) ; le « avant » du fix rois |
| 0241 | **loop full-fold KING-AWARE + scalé** (600k/gen) 📍 | *en vol* — LE push : pousser la classe linéaire à son max (kings + data) |

---

## 4. Outils ajoutés
- `jass --rewrite-scores-with-search <in> <out> --nnue <eval> [--depth D]
  [--start S] [--count C]` — relabel par recherche profonde, teacher-free
  (`eval ← recherche(eval)`), shardable. Cf. ARCHITECTURE.md.
- `tools/calibrate_vs_scan.py --jass-depth N --scan-depth M` — profondeur
  asymétrique (diagnostic eval-vs-recherche).
- **Mesure / plan d'expérience** (adopté 2026-06-12, cf. ROADMAP.md §Méthodologie) :
  - `tools/eval_proxy.py` — proxy de force **déterministe** (accord eval vs
    référence forte sur set fixe : Spearman/Pearson/sign). Courbe d'apprentissage
    cheap et sans bruit. `jass --rewrite-scores-with-nnue` accepte désormais `.pjtw`.
  - `tools/sprt_elo.py` — Elo ± IC 95 % et **SPRT** (W/D/L) pour confirmer les
    jalons en parties au minimum de jeu.
  - **Règle** : fixer l'effet minimal détectable AVANT (≈550 parties pour Δ=0.05) ;
    courbe au proxy, jalons au SPRT ; un seul facteur changé à la fois (ou plan
    fractionnaire). NE PLUS conclure sur des benches de 18-54 parties.

---

## 5. Prochaines étapes — DEBUG du pipeline (post-0205b)

**Statut 2026-06-13.** La boucle WDL itérée propre (`0205b`, mt30, mesurée au
PROXY déterministe) est **PLATE ~0.41 = niveau matériel** de gen0→gen6 (alors
qu'une eval compétente fait 0.64-0.67 ⇒ le proxy discrimine). **Directive user :**
« si plat même PROFOND, on cherche le BUG, **pas** de pivot non-linéaire — c'est la
**même infra que Scan** donc ça **doit** monter ». On debug, on ne pivote pas.

**Debug mené (2026-06-13) :**
- **Test #1 — le self-play utilise-t-il l'eval qui évolue ? → OUI (hypothèse bug
  ÉCARTÉE).** `run_gen_data_wdl_mode` fait `e.set_nnue(custom_nnue.get())` puis
  pilote chaque coup par `e.search()` (main.cpp:368-369, 507-511). Un échec de
  chargement `--nnue` est **bruyant** (`error: cannot load` + `return 1` → le job
  abort), donc PAS de repli silencieux sur le réseau embarqué ; et les valeurs
  proxy réelles de 0205b prouvent que les `.pjtw` frais se chargent. → ✂️ B1.
- **⭐ Suspect n°1 — FAMINE DE DONNÉES (mesuré).** Table = **17 006 112 buckets**
  (32 patterns × 3¹²). Sur 30k positions self-play : **~1.0 % des buckets touchés**,
  **62 % des touchés ont ≤2 visites** (poids = bruit tiré au prior l2≈0), 44.6 % une
  seule visite. À 300k/gen (0205b), la table reste **~97 % non-estimée** ⇒ l'eval ≈
  **matériel + petite tête de buckets fréquents** ⇒ **proxy plat à 0.41 PAR
  CONSTRUCTION**. Pire : chaque gen régénère 300k FRAIS (aucune accumulation) ⇒
  couverture constante ⇒ **aucun compounding**. Scan « même infra » monte parce
  qu'il estime DENSÉMENT sa table (corpus énorme). **FIX (reste linéaire, reste
  Scan)** : volume/gen ×10–50 (millions) et/ou **corpus cumulé** dominé par les
  gens récentes. → **job sweep-volume à lancer** (proxy(gen1) vs 0.3M→1M→3M→10M).
- **Rois invisibles aux patterns** : `extract_indices`/`extract_all` lisent
  **men-only** (31 % des positions ont un roi). C++ et Python COHÉRENTS (pas un bug
  de correctness) ; rois pris via les extras (compte+mobilité). Limite
  représentationnelle, **pas** une panne — réserve, ne pas confondre avec « enrichir
  la classe » (= le pivot interdit).
- **Régression annexe** : les `.pjtw` champions **committés** (pattern_clean, 0152
  A, …) ne se chargent plus : `n_pat=4 251 528` (8 patterns) ≠ `TOTAL_BUCKETS=
  17 006 112` (32) — la géométrie a ×4 depuis. Sans impact sur la boucle (evals
  frais = géométrie courante) ni sur le proxy (référence = JNNW, scores lus direct).

**Root cause confirmé du « plat » 0205b (2026-06-13) :** chaque gen ré-entraîne sur
**300k FRAIS** (aucune accumulation) → couverture constante ~1 % de la table 17M
gen-après-gen → **zéro compounding** par construction. Le fix = **ACCUMULER** le
self-play (couverture qui grandit) et/ou **gros volume**.

**Combien de data ? (reverse-engineering 2026-06-13, 1.2M positions self-play depth-play)**
La table de 17M est surtout FANTÔME (compte combinatoire 32×3¹²). Le self-play réel
ne TOUCHE qu'une petite fraction :
- distinct touchés à 1.2M pos = 774 588 (**4.6 % de 17M**) ;
- **ensemble OCCURRENT (Chao1) ≈ ≥1.0M buckets (~6 % de 17M)** — estimateur encore
  croissant avec l'échantillon (queue lourde ⇒ borne basse) ;
- couverture de masse (Good-Turing) = **99.4 %** (la masse est concentrée sur la tête).
Courbe d'accumulation `distinct(D)=R(1−e^{−D/τ})`, **τ≈1.0M** ⇒ pour avoir **95 % de
l'ensemble occurrent** : **~3.0M positions** ; à **≥8 visites** sur 95 % : ~10–20M ;
à **≥30–50 visites** (bien estimé) : ~30–60M. **Réaliste** (échelle Scan), donc le fix
est le VOLUME/cumul, pas un changement de classe. Conséquences : 0205b (300k frais ≈
2 % de 17M ≈ ~46 % de l'occurrent, ≤2 visites) → matériel ⇒ plat ✔. Bonus dispo plus
tard : comme seuls ~1M buckets occurrent, on peut ÉLAGUER/hasher la table à ~1M (×17),
et le repliement par symétrie (à la Scan) diviserait encore le besoin par bucket ~4–8×.
Tooling : `tools/bucket_coverage.py <selfplay.jnnw>` (accumulation + Chao1 + Good-Turing
+ extrapolation Poisson ; lit le nb d'enregistrements par TAILLE de fichier → marche
sur shards en cours).

**Élagage = remap dense COLLISION-FREE (validé 2026-06-13, `tools/bucket_census.py`).**
Comme ~16M buckets sont fantômes, on peut élaguer vers une table dense (occurrent →
slot 1..K, jamais-vu → slot 0 fallback). Sur 1.08M positions de census :
- min-visits=1 → **K=751 872 (×22.6 plus petit)**, .pjtw 136MB→6MB, design train 34M→1.5M
  colonnes, **taux de fallback hold-out = 0.62 %** des activations (→ quasi sans perte ;
  les buckets fantômes valent ≈0 de toute façon) ;
- min-visits=2 (drop singletons bruit) → K=537k (×31.6), fallback 1.16 %.
⚠️ CE N'EST PAS le bucket-hashing LOSSY de 0190 (collisions rares→communs, casse la
profondeur, cimetière) : ici zéro collision sur l'ensemble gardé. Gain = EFFICACITÉ
(train ×~22 moins cher → plus de data/gens), PAS de la force en soi.
**Intégré + validé (2026-06-13) : `train.py --prune` [--prune-min-visits N].** Entraîne
sur 2×(K+1) colonnes denses puis SCATTER vers le .pjtw 17M standard (C++ inchangé).
A/B sur 30k (mêmes data/iters) : full = 584s, pruned = **11.4s (×51 plus vite)** ;
`pat_mg` corr = **0.999962** (max|Δ|=2 = bruit de quant.) ; proxy full 0.0180 vs pruned
0.0174 (**parité**). Lossless confirmé. L'écart de vitesse CROÎT avec la data (full =
L-BFGS 34M params ; pruned ∝ K). Incompatible anchors/freq-reg/fm (gardé). Le levier force =
**partage de poids par symétrie** (Piste 3, à implémenter : ~×4-8 data/poids). Dérive :
re-census tous les N gens ou dimensionner K avec marge (le fallback grandit sinon).
**Séquencement : on branche l'élagage APRÈS le verdict volume (0210/0211).**

**Décision (2026-06-13) :** on TUE les deux boucles mt100 starvées (300k/gen ne peut
que reproduire la famine) et on lance la famine en test direct sur les DEUX box, en
boucles à **corpus CUMULÉ** (gen_g s'entraîne sur l'union de tout le self-play) :
- **`cpx62-0211-cumulative-loop-1M`** (box 32GB/16c) — **1M/gen** cumulé, 5 gens
  (→ ~5M), couverture+proxy par gen.
- **`ccx33-0210-cumulative-loop`** (box 16GB/8c) — **300k/gen** cumulé, 6 gens
  (→ ~1.8M), couverture+proxy par gen.
**VERDICT (2026-06-13) — famine CONFIRMÉE mais 2e mur.**
- **ccx33-0210** (cumul 300k/gen, depth4) : 0.398→**0.462** puis PLATEAU ~0.46 (gen4-6,
  1.88M cumulés, couverture 6.1 %).
- **cpx62-0211** (cumul 1M/gen, depth4) : 0.406→**0.449** puis PLATEAU ~0.45 (dès gen1,
  5.2M cumulés, couverture 7.8 %, ≤2visites 33 %).
- Lecture : (1) la FAMINE est réelle et réglable — les deux MONTENT +0.05 vs 0205b PLAT
  (fresh 300k) ⇒ l'accumulation compounde ✔ B2. (2) MAIS **2e mur ~0.45-0.46 que PLUS de
  data ne casse PAS** (0211 a 2.8× la data de 0210 et plafonne PLUS BAS ; couverture
  saturée ~1.3M buckets occurrents). Le gap restant **n'est pas la data**. Suspect n°1 =
  **profondeur de jeu** (les deux jouent en **depth4** → parties/labels faibles →
  l'eval plafonne en accord avec Scan-d10 fort). Autres : B3 (rois invisibles aux
  patterns), B4 (le proxy = accord-SCORE Scan, pas l'Elo en parties → SPRT). →
  **prochain test = PROFONDEUR de jeu** (boucle cumulée mt30/60, maintenant abordable
  via --prune + harnais 2-box).

**Outils/infra livrés (2026-06-13) :** `train.py --prune` (×51 train, lossless),
`tools/bucket_census.py`, `tools/bucket_coverage.py`. **Harnais 2-box** `ccx33-0212` +
`cpx62-0213` : génération parallèle CCX33+CPX62 → UN corpus (shards via git ≤95MB,
barrière en LISANT origin/main que le runner rafraîchit → zéro op git côté job, zéro
contention), fusion + train --prune. Limite boucle ITÉRÉE 2-box : transporter l'eval
entre gens (136MB>95MB cap → format dense C++ ~6MB, ou object store).

**Harnais 2-box PROUVÉ (cpx62-0213, 2026-06-13) :** corpus de **3M fusionné des DEUX box**
(CPX62 2M@16c + CCX33 1M@8c) via git ; barrière (lecture origin/main) résolue en 60s ;
train --prune 176s ; total ~7 min. Couverture firmée : occurrent **≥1.25M** (95 % à ~7M
positions). → on peut cumuler la puissance des deux box pour UN jeu de données.

**B3 king-aware patterns = NEUTRE (A/B 2026-06-13).** Patterns piece-presence (men|kings)
vs men-only sur 1.2M, même split, --prune : val_mse 1.088 (men) vs 1.097 (king-aware,
LÉGÈREMENT pire), sign_acc +0.0007 (bruit). Aucun gain. 3 signaux convergents : rois
DÉJÀ dans l'eval (PST+mobilité), 0145 neutre, et cet A/B pattern neutre ⇒ **les rois ne
sont PAS le mur ~0.46**. Ne PAS investir l'intégration C++ king-pattern. Toggle dispo :
`train.py --king-patterns`. → reste le levier non testé : **PROFONDEUR de jeu** (les deux
boucles murées jouaient en depth4 → labels WDL faibles ; aucun changement de code requis).

**VERDICT B4 (0216, 2026-06-13) — LE « MUR 0.46 » EST UN ARTEFACT DU PROXY. 🎯**
Parties RÉELLES (1440 parties, CI serrés) des evals de la boucle mt30 (0214) :
- gen0 (seed) vs handcrafted : 659-41-740 → **Elo −20** [−37,−2]
- gen5 vs handcrafted        : 830-26-584 → **Elo +60** [+42,+78]
⇒ la boucle a gagné **+80 Elo RÉELS** (gen0→gen5), CI DISJOINTS = significatif, ALORS
QUE le proxy stagnait (0.40→0.43). **Le proxy SOUS-LIT massivement la force réelle.** On
n'était PAS muré : l'eval continue de se renforcer pendant que l'accord-score-vs-Scan-d10
plafonne. Tous les « murs » (data/rois/profondeur) étaient mesurés AU PROXY → trompeurs.
Revers : gen5 vs **Scan** d9 = **0/1080** (perd TOUT) → on est encore ÉNORME ément loin de
Scan en absolu ; +80 Elo = vrai progrès mais goutte d'eau vs l'écart à Scan.
**Conséquences (réorientation) :**
1. **RETIRER le proxy comme métrique primaire** (cause de tous les faux murs). Mesurer en
   **Elo réel** : adversaire commun pas cher (hc) + SPRT périodique vs Scan (tools/sprt_elo.py).
2. **La recette COMPOUNDE en force réelle** → reprendre le SCALING de la boucle WDL (data +
   itérations), train --prune (pas cher) + pooling 2-box.
3. **Réévaluer la PROFONDEUR en Elo** (le verdict « depth pire » était au proxy ; mt30/60
   sont peut-être PLUS forts en parties malgré un proxy plus bas).

**AUDIT ARCHI vs SCAN (2026-06-13) — BRIQUE MANQUANTE = PARTAGE DE POIDS PAR SYMÉTRIE.**
Vérifié sur la source `rhalbersma/scan` (`src/eval.cpp`). Scan = MÊME classe linéaire
(patterns 12 cases men-only 3-états, phase MG/EG, extras king-PST/matériel/mobilité/balance,
logistique WDL) SAUF qu'il **lie ses poids** : couleur (`index=Trits[N]−Trits[B]`, antisym),
rotation 180° (bottom = tables inversées `−index,−1`), réflexion (`Perm_0/Perm_1`),
translation (1 bande glissée `wm>>0..3`) → **4 tables, P=2 125 820 poids DENSES**. Nous =
**32 tables indépendantes, 17M poids AFFAMÉS** (38 % des touchés ≤2 visites). Archi linéaire
MAL MONTÉE, pas un besoin de non-linéaire. Détail+plan : **docs/SYMMETRY_SHARING.md**.
Décision user : tuer le scaling (montée sur archi incomplète = sans intérêt), implémenter le
partage par symétrie MAINTENANT, tester ASAP en **Elo réel** (le proxy ment, B4). Phases :
1 = antisym COULEUR (17M→8.5M, ×2 data) → 2 = rotation 180° → 3 = réflexion + translation.

**IMPLÉMENTATION SYMÉTRIE — TOUTES LES BRIQUES FAITES + VÉRIFIÉES (2026-06-13).**
Mécanique : on REPLIE les poids à l'entraînement (`pattern_jass/tools/symmetry.py` +
`train.py` flags) puis on les RÉ-ÉTEND vers un `.pjtw` v3 17M standard → **le C++
est inchangé**. Chaque brique compose et préserve les symétries EXACTES (vérifié
numériquement, 0 violation) :
- `--color-fold` : antisym couleur `W[swap]=−W` (approx). 17M→**8.5M**.
- `--rot-fold` : + rot180∘couleur (**EXACT**, l'eval négatif). 17M→**4.9M**.
- `--trans-fold` : + translation (7 classes, **approx**). 17M→**1.2M**.
- `--full-fold` : + réflexion gauche-droite (inversion intra-rangée, **EXACT** ;
  un miroir-fichier naïf échange noir↔blanc). 17M→**1.0M**.
- **géométrie LR-CLOSE** (`gen_patterns.py --lr-close`, 32→**54 patterns**, fermée
  sous {rot180,LR}, 0 orphelin) + full-fold → **0.6M poids ≈ échelle Scan** ;
  C++ build + tests OK ; proxy 0.33 sur le probe 30k bidon (vs ~0 pour tout
  32-pattern → la régularisation lourde tue l'overfit).
Échelle des poids : men-only 17M → couleur 8.5M → rot 4.9M → trans 1.2M → réflexion
1.0M → **LR-close 0.6M**. On est passé de 17M poids INDÉPENDANTS affamés à ~600k
DENSES partagés = l'archi linéaire « bien montée » à l'échelle de Scan, 100 % linéaire.
**A/B en Elo réel** (5 bras identiques, ne différant que par le fold, mesurés vs hc/gen) :
`0220` men-only · `0221` couleur · `0222` rot · `0223` trans · `0224` full (en cours).
LR-close (`0225` men-only / `0226` full) **prêt sur la branche, HORS main** (déployé
après l'A/B 32-pattern pour ne pas confondre). ⚠️ caveat : 54 patterns = eval ~1.7×
plus lente (opti future : calculer chaque orbite une fois). Détail : docs/
SYMMETRY_SHARING.md + ARCHITECTURE.md.

**VERDICT A/B SYMÉTRIE (2026-06-13) — le fold lourd MARCHE, +~30 Elo, modeste mais RÉEL.**
Elo précis gen8 vs hc (60 paires, IC ±17), boucle cumulée depth4 8 gens (~2.6M) :
men-only +147.6 · color +144.5 · rot +153.8 · **trans +177.4 · full +175.3**. Les deux
folds LOURDS (trans 1.2M, full 1.0M) **concordent indépendamment** (~+176) → le **+30
vs men-only est RÉEL** (pas du bruit). Les folds légers (color/rot) = NULS. Le gain vient
de la **TRANSLATION** (32 tables → 7, le gros saut de densité), pas des petits folds.
Bonus : meilleur SEED (full gen0 = +34 vs men-only −32). **Lecture honnête** : +30 est
MODESTE (pas le bond du probe val-MSE) — à depth4/2.6M la table 17M n'est pas ASSEZ
affamée pour que la densité paie plus. Le gros payoff attendu = **fold + plus de data +
profondeur** (régime où le 17M non-foldé est vraiment affamé). PROCHAIN : (1) déployer
LR-close full (0.6M, 0225/0226) ; (2) scaler data+profondeur AVEC full-fold ; (3)
optimiser la géométrie (`pattern_importance.py`) pour récupérer la vitesse.

**VERDICT LR-CLOSE + PROFONDEUR (2026-06-13) — ON A SUR-FOLDÉ ; sweet spot = 32-pat full-fold.**
Elo précis gen8 vs hc : 32-pat full-fold (0227) **+175.3** · **54-pat LR-close full-fold
(0229) +134.0** · full-fold @mt30 54-pat (0228) +135.8. La géométrie LR-CLOSE (54 patterns,
0.6M poids) est **−41 Elo PIRE** que le 32-pat full-fold (1.0M) — à chaque gen, seed inclus
(gen0 −32 vs +33). On a **SUR-FOLDÉ** : 0.6M passe SOUS l'optimum ~1.0M, les folds
approximatifs/agressifs mordent (exactement le risque théorique). **OPTIMUM = 32-pat
full-fold (+175, soit +30 vs men-only).** → main REVERTÉ en 32-pat. La PROFONDEUR (mt30)
n'a rien donné ici (+136≈+134) mais c'est CONFONDU (testé sur la mauvaise géométrie 54-pat)
→ re-tester mt30 sur 32-pat (la bonne) pour trancher. ✂️ LR-closed geometry = impasse
(sur-fold). Leçon : il y a un OPTIMUM de fold ~1.0M ; plus n'est pas mieux.

- **NE PLUS** relancer : deep-score relabel (distillation), WDL 1-cycle, sweep l2
  sur self-play (optimum = [3e-4,3e-3] établi), **pivot non-linéaire avant debug**.
- Tenir ce journal à jour **après chaque verdict**.

---

## 6. Historique du projet — le cheminement (0001 → 0202)

> Reconstruit depuis les docs de phase + le registre des jobs. But du projet
> (**jass** = *Just Another Scan System*) : un moteur de dames 10×10 **aussi bon
> que Scan** (Letouzey, ~2500 FMJD), mais **indépendant** (pas de code Scan ;
> Scan sert de mètre-étalon via `tools/calibrate_vs_scan.py` sur HUB). Tout
> tourne en file de jobs GitOps (`jobs/queue` → `jobs/results`).
>
> **Le fil rouge** : pendant ~190 jobs on a benché **contre v15** — un
> sparring-partner qui est lui-même **≈ 0 vs Scan**. Quasiment tout le
> « cheminement » est la lente correction de cette erreur de mesure.

### Phase 0 — Bring-up & baseline handcrafted (pré-0001 → ~0009)
Moteur (board, movegen, alpha-beta) + eval handcrafted (matériel + PST + roi +
mobilité) + plomberie data/train. **Décision** : un moteur correct et rapide
d'abord, Scan strictement comme juge externe (propreté de licence). **Marché** :
movegen validé par **perft** (valeurs FMJD exactes) ; recherche alpha-beta
complète. **Pivot** : le levier devient l'**eval** → NNUE.

### Phase 1 — Naissance NNUE : v5 (~0010-0018)
`0014` récupère les **master games** Lidraughts (`master-1600.jnnw`, 4.74M,
WDL réels) ; `0018` entraîne **v5** (MLP 256-128, HalfMen 450, int8). **Marché** :
v5 = **0.852 vs handcrafted** ; recherche **×1.57** (SIMD + accumulateur).
**Échec** : vs Scan (fair) = **0.009 (≈ −812 ELO)**. **Pivot** : un seul passage
supervisé ne ferme pas −812 → itérer la qualité des données.

### Phase 2 — Lignée data-quality NNUE : v6 → v7 → v8 (~0043-0056)
Revue de littérature → **filtre quiet** (`--quiet-only`) + **`--pv-extract`**.
**v6** (0045) = 0.556 vs v5 ; **v7** (0050) = 0.667 vs v6, 0.944 vs hc ;
**v8** (0056, arch 512-256, **v7 comme labeller** = bootstrap) = 0.722 vs v5
(+258 ELO cumulés). **Échec** : **non-transitivités** (v8 perd vs v6) =
rendements décroissants ; chaque cycle hérite des biais du précédent. **Pivot** :
axe corpus jugé épuisé ; le **run 10M (€700+) gelé définitivement** (mauvais ROI
vs le déficit −800) → prioriser l'**architecture** (patterns façon Scan).

### Phase 3 — Première tentative pattern & le « methodology gap » (~0025a, 0046-0057)
`PatternNetwork` (base-5, jusqu'à 16×8 = 6.25M poids). **Décision** : patterns
~285× plus rapides à évaluer que le MLP — vrai avantage structurel ; Scan prouve
que c'est puissant. **Échec** : **tout variant supervisé plafonne à ~0/54 vs v5
d10** ; `man/king_value` converge au **même minimum local** (la MSE préfère
rétrécir le squelette pour coller au bruit). `SCAN_METHODOLOGY_GAP.md` liste les
5 pièces manquantes (phase-split MG/EG, géométrie, feature engineering, méthode
= TD-leaf/self-play, 15 ans de tuning Letouzey). **Pivot** : axe pattern gelé.

### Phase 4 — Distillation de Scan : v10/v11 (~0073-0088)
Reframe : « battre Scan » → « **approximer une fonction connue** » (relabelliser
avec l'eval de Scan et l'imiter). `0078` : 1M relabellisé **Scan-d12** → **v10**
(256-128) ; `0083/0084` : capacité **v11** (1024-512) sur 2.37M. **C'est la
lignée des labels de v15.** **Échec** : v11 au movetime vs Scan = **0.009** (la
capacité ne se convertit pas) ; set distillé **suspect** (labels ±9989 « won/lost »
— le poison diagnostiqué en Phase 9). **Pivot** : ce n'est pas la capacité, c'est
le NPS → optimiser la vitesse sur une petite archi.

### Phase 5 — Choix de v15 (128-64) & le perf journey (0090-0106)
`0090` balaie les archis **au movetime** (pas en profondeur fixe, qui flatte les
gros nets) ; **128-64 gagne le rapport NPS/force → devient v15, la baseline
production** (917K NPS). Longue chasse perf : **capture pre-filter (0101, +29.7%)**
+ **SIMD quantize (0103, +8.5%)** = **+40.7 % NPS**, qualité préservée ; SMP 4t
= +50-80 ELO. **Échecs instructifs** : hybrid cheap-eval (0096) casse la
cohérence alpha-beta (rate→0.056, reverti) ; lazy accumulator (0098) inutile
(>90 % des nœuds touchent l'eval). **Verdict honnête** : en **profondeur fixe**
jass *paraît* dominant (le fameux **0.870 / +331 vs Scan-d10**), mais au
**movetime** le gap est **−500 à −550 ELO, structurel**. **Pivot** : valider
d'abord l'**infra pattern** ailleurs → Othello.

### Phase 6 — Détour POC Othello (#170)
Moteur Othello 8×8 autonome + 10 patterns Logistello + **L-BFGS**. **Décision** :
avant de transposer aux dames (où 13-18 essais ont échoué), prouver que **notre
code pattern n'est pas le problème**. **Marché** : pattern bat random **1.000**,
bat le handcrafted **0.675** (+125 ELO) en ~1 min de gen. **Conclusion** :
**infra validée** → les échecs pattern aux dames = **géométrie + signal
d'entraînement propres aux dames**, pas le code.

### Phase 7 — pattern_jass : standalone échoue, hybride passe (~0118-0137)
Module `pattern_jass` (12-square base-3, géométrie façon Scan). **Tout standalone
≈ 0.000-0.056 vs hc**, mais `0129` **hybride** (`eval = squelette handcrafted +
correction pattern`) = **0.667 vs hc (+120 ELO)**. **Leçon : le pattern doit
AUGMENTER le handcrafted, pas le remplacer** — même forme que Scan. (`0131`
distillation = 0.000, empoisonné par ~18 % de faux labels du bug de prise forcée,
depuis corrigé.)

### Phase 8 — Les 4 confondants & l'eval Scan-style standalone (~0141-0152)
4 confondants empilés derrière « les patterns sont faibles » : (1) ~18 % de
labels sales ; (2) jugé en **profondeur fixe** (cache le ×100 de vitesse) ; (3)
recherche tunée pour le NNUE ; (4) entraînement non-search-aware. Construction de
`src/scan_eval.{hpp,cpp}` (phase-split MG/EG, 32 patterns + 106 extras denses).
**Marché** : material-anchor (0152) passe le standalone de **0.000 → 0.444 vs hc**.
**Échec** : TD-leaf self-play d'une eval faible **s'effondre (0.056)** — « le
self-play d'une eval faible n'enseigne pas mieux qu'elle-même ; la méthode n'est
pas le levier ». **Pivot** : il faut un **programme d'apprentissage multi-cycles**,
pas une régression unique ; le levier = **features (capacité)**.

### Phase 9 — Saturer la classe linéaire & le déblocage `--score-drop` (~0154-0193)
**LE tournant : `--score-drop`.** ~2 % des scores Scan étaient des ±9989
« won/lost » qui **dominaient la perte L2** (5000² même après clip). Les
supprimer : **val_mse 38→1.8, jeu 0.42→0.94 vs hc**. **Toutes les « régressions »
passées étaient ce poison.** Le **champion** cristallise : 32 patterns + 106
extras, phase-split, distillé Scan-d10 + `--score-drop 4900` + l2=1e-4 +
material-anchor → **0.39 vs v15** (d9) / 0.38-0.42 (movetime). `0157` renverse
l'hypothèse vitesse : le champion est **plus rapide que v15** et cherche **2.5
plies plus profond**, et perd quand même → **le déficit vs v15 est la QUALITÉ
d'eval par nœud, pas la vitesse.** **Mais la carte des leviers est neutre ou
NÉGATIVE partout** (voir Impasses). `0189` : Scan ≈ **×8 NPS** ; gains réels
+26 % mais « la vitesse seule n'aide pas, on perd déjà à profondeur égale ».
**Pivot — le grand** : les leviers incrémentaux sont épuisés → **faire ce que
Scan a fait : self-play + WDL + régression logistique, ITÉRÉ**, sur géométrie
correcte. Multi-cycles.

### Phase 10 — Exécution recette Scan & le RÉ-ANCRAGE (0194-0202)
Détaillé en [§3](#3-index-des-jobs-récents) et dans
[PATTERN_PROGRAM_NOTES.md](PATTERN_PROGRAM_NOTES.md). En bref : WDL plafonne 0.22
(label, pas data) ; **ré-ancrage 0199 : champion ≈ v15 ≈ 0 vs Scan** (le 0.39
était flatté) ; **deep-relabel d12 = 0.306** (levier confirmé, teacher-free) ;
**0201 : l'eval est le gap** (la recherche est complète, la vitesse secondaire).

### Phase 11 — Symétrie full-fold & CLÔTURE de la géométrie (0203-0236)
**Le pli full-fold.** Fermer le jeu de patterns sous {couleur, rot180, translation,
réflexion} et lier les poids → **17M → 1M poids distincts (17×)**, sans nouveau
paramètre libre (que des lookups en plus). Boucle self-play WDL itérée (8 gens,
self-play depth4, 300k/gen, cumulé, `logistic --prune --full-fold`) → **+175 vs hc**
(`0227` gen8), reproduit **+142** (`0231`, 60 paires). ⚠ **vs hc seulement** (faible,
cf. la leçon de mesure de la phase 10) — **pas encore ancré à Scan** (`0235` en vol).

**Géométrie close — 3 angles convergents, c'est un levier mort :**
- **(a) enrichir ne paie pas** — 54-pat LR-closed = **+134 < +175** du 32-pat ;
  v5/v6/v7 (phases antérieures) idem. Plus/mieux de patterns ≠ plus de force.
- **(b) importance UNIFORME** (`0230`) — les 32 patterns ont std 30-54, corr_ref
  vs Scan minuscule (0.02-0.04), redondance ≤ 0.40. Aucun pattern mort, aucun doublon.
- **(c) élaguer = LOSE-LOSE** (`0231` vs `0234`, RFE drop-8 reset-proof) — retirer
  les 8 patterns les moins importants **coûte −31 Elo** (+142 → +110) **ET ne gagne
  AUCUNE vitesse** (knps pattern/hc 0.653 → 0.648, depth@1s 20 → 19.4). Donc la
  lenteur d'eval n'est **pas** dans les lookups de patterns mais dans les **106
  extras Scan-style + l'overhead de recherche** — l'élagage ne l'attaque même pas.

**Signature data-limited (re-confirmée).** Le proxy vs Scan **plafonne ~0.47** sur
TOUTE la trajectoire self-play (gen1 0.456 → gen8 0.471, quasi plat) alors que l'Elo
vs hc, lui, bouge → vs Scan on n'apprend quasiment plus. Couplé à la **sparsité 90×**
des buckets (187k utilisés / 17M) : on ne remplit pas la capacité qu'on a déjà. Cohérent
avec deep-d12 0.306 ≫ WDL 0.22 (phase 10). **Hypothèse de travail : data/label-limited,
pas geometry-limited** — la classe additive-sur-patterns est la *bonne* (celle de Scan).

**Outillage durable :** géométrie **reset-proof** via `JASS_PATTERNS_DIR` (copie hors
du tree git ; le runner reset le tree vers main en cours de job et révertait sinon la
géométrie émise au démarrage — bug qui a tué `0232`) ; `tools/pattern_importance.py`
(std·|corr| + redondance) ; `gen_patterns.py --drop` ; métrique vitesse knps(pattern)/knps(hc),
indépendante de la machine.

**En vol (à trancher) :** `0235` = ancre **réelle vs Scan** (depth9 = qualité d'eval
pure, mt1s = force réelle, sans bitbases) ; `0236` = **plafond de distillation** (full-fold
entraîné sur 1.0M labels Scan-d10). Lecture : plafond ≫ 0.47 ⇒ **label-limited** (recette =
distiller Scan / labels profonds) ; plafond ~ 0.5 ⇒ **class-limited** (éval non-linéaire requise).

### Phase 12 — LA BRIQUE ROIS : le bug structurel vs Scan (0237-0241, 2026-06-14)
**Le diagnostic.** On a cherché « pourquoi la classe linéaire ne monte pas comme Scan »
par élimination, en restant linéaire (directive : *pas de pivot ; si plat = bug*) :
- **géométrie = levier MORT** (3 angles) : importance uniforme (`0230`), élaguer = **−31
  Elo ET 0 vitesse** (`0234`), richesse géométrique **plate sous labels parfaits** (`0239` :
  val-loss 0.600-0.617 de 15→54 patterns). → le trou n'est pas la forme.
- **plafond de distillation men-only ~0.60** (`0239`/`0237`) : même avec le prof PARFAIT
  (master Scan-d10 dense, donc PAS la famine), la classe men-only plafonne → c'est
  **représentationnel**, pas data ni géométrie.

**Le bug (enfin trouvé).** Nos patterns lisaient **men-only** → une case occupée par un
**roi se lisait VIDE**. Scan, lui, compte un roi comme « **pièce** » sur sa case (base-3
amalgamé man|king ; la *valeur* du roi vit dans les extras PST/mobilité). Donc **« même
infra que Scan » était FAUX** : une vraie **divergence**, exactement le « bug » pressenti.
Ce n'était pas une limite de la classe linéaire — c'était une *régression* vs Scan.

**Le fix (100 % linéaire, = Scan).** Brique rois : `-DJASS_KING_PATTERNS=ON` (occupation
`men|kings` côté binaire, `src/scan_eval.hpp`) + `train.py --king-patterns`. Base-3
amalgamé (PAS base-5 = jass v2 raté, buckets king trop creux). `update_all` gère coups de
roi ET promotions (man→king même case = toujours « pièce » → index inchangé). Default OFF =
no-op exact (6408/6408 tests). **VALIDÉ `0240`** : sous distillation Scan-d10, men-only
**+78** → king-aware **+115 Elo vs hc** (= **+37**, ~1080 parties, IC serré), val-loss
0.613→0.602. Le gain Elo > gain val-loss : voir les rois change surtout la **sélection de
coups** en jeu réel (moins de bévues à rois), comme l'autopsie le prédit.

**Le push (en cours).** `0241` = loop full-fold **king-aware + SCALÉ** (600k/gen cumulé vs
300k) — pousser la classe LINÉAIRE à son max (kings + couverture), trajectoire vs les
baselines men-only (0227 +175 / 0231 +142). Garde-fou : +37 ≠ tout le gap à Scan ; la
**famine de données** reste un mur indépendant → kings ET data ensemble.

**Outillage + hygiène.** `tools/game_autopsy.py` (autopsie coup-par-coup vs Scan-oracle :
accord + perte d'éval par phase × rois × tactique + galerie de bévues — `0238`). Piège
mesure corrigé : les matchs vs Scan en **profondeur fixe sans plafond temps** explosent
(`0235` figé ~8h sur l'arme d9, tué via le flag `jobs/state/kill-in-flight`) → **toujours
borner au movetime**. Proxy : confirmé **retiré** comme juge de force (B4/0216) ; sélection
de modèle par **val-loss**, verdict par **parties réelles**.

### Phase 13 — Campagne FINALES (éval) + RECHERCHE (0249-0263, 2026-06-15)
**Le diagnostic finale (deux microscopes).** Les autopsies phase×rois (`0249` men-only /
`0250` king-aware) localisent le saignement : éval **≈Scan en ouverture/milieu** (perte
oracle 0.05) mais **finale à rois ~3.6** (×50). Deux jobs tranchent le *pourquoi* :
- **`0251` (plafond de classe par phase)** : sur labels Scan-d10 PARFAITS, la classe
  king-aware **range très bien la finale** (spearman 0.73-0.79, sa meilleure phase) →
  **PAS class-limited** ; notre éval self-play est juste **mal entraînée** en finale.
- **`0252` (éval vs recherche)** : la finale est **SEARCH-BOUND** — éval pure (depth-1)
  catastrophique (perte 7.25), la recherche profonde rattrape (mt2.0 = 1.71).

**La densification finale — 3 leviers, 2 morts.** Tentative `0254` (boucle king-aware +
`--label-depth-by-phase` + `--phase-weight`) : **−80 Elo vs 0241** (+149 vs +229). Ablations
décisives : `0257` innocente phase-weight, `0258` innocente lowmem (full-batch = même +149)
→ la cause est la **DONNÉE** : `--label-depth-by-phase` est un **no-op** (la boucle s'entraîne
sur le **WDL**, pas le score) qui en plus **corrompt les parties** (la recherche de label
profonde pollue la TT partagée). Puis `0261` (distillation SCORE + phase-weight) : phase-weight
**−210 Elo** sur de BONS labels → **`--phase-weight` est MORT** (cimetière). MAIS la distillation
sur **score** marche : **+141 vs hc** (> distill-WDL `0237` +90) → le score est le bon signal
de teacher, sous le self-play en force globale. **Le vrai levier finale** (codé `0263`) :
`--play-depth-by-phase` — **JOUER les finales profond** pendant le self-play → WDL de finale
fiables → la boucle apprend la finale sans pondérer ni distiller. *Leçon de méthode : vérifier
le SIGNAL d'entraînement (WDL vs score) avant d'ajouter un levier ; tester ISOLÉ (le combiné
0255 « tout off » washait le +29 du NMP).*

**La RECHERCHE redevient un levier (gros gain).** Features gated activées : `use_improving`
**+22** (`0253`, conthist −11 laissé off). Surtout le **régime finale NMP** : sweep du seuil
(`0256`+`0259`) **monotone croissant** jusqu'à thr36 = **+97 Elo** (≈ NMP désactivé partout) →
**NMP est net-négatif en jass** (zugzwang omniprésent : « passer est sûr » est faux en
permanence ; + captures obligatoires). Confirmation à mt0.5 en cours (`0262`). Déployés :
`use_improving=true`, régime `eg_pieces`/`eg_no_nmp` (code search_params.hpp, default path
byte-identique quand off). Outillage : `tools/phase_proxy.py` (accord statique par phase),
`--phase-weight`/`--label-depth-by-phase`/`--play-depth-by-phase` (gated, rétro-compatibles).

### Lignée des modèles
| Nom | Job | Données / labeller | Archi | Résultat phare |
|---|---|---|---|---|
| handcrafted | pré-0001 | — | matériel+PST+roi | ancre ELO ; perft-correct |
| **v5** | 0018 | 1M self-play d20 + master, BCE | MLP 256-128 | 0.852 vs hc ; **0.009 vs Scan** |
| **v6** | 0045 | 500K quiet+pv-extract | 256-128 | 0.556 vs v5 |
| **v7** | 0050 | 1M quiet+pv, v5-labellisé | 256-128 | 0.667 vs v6 |
| **v8** | 0056 | 1M, **v7-labellisé** (bootstrap) | 512-256 | 0.722 vs v5 (+258 cum) |
| **v9** | 0071 | dataset v8 | 1024-512 | overfit, plafonne vs v8 |
| **v10** | 0078 | 1M **Scan-d12 distillé** | 256-128 | prior de distillation |
| **v11** | 0083/4 | 2.37M Scan-distillé | 1024-512 | **0.009 movetime vs Scan** |
| **v15** | 0090/1 | lignée Scan-distillée | **128-64** (best NPS/force) | **baseline prod**, 917K NPS ; ≈0 vs Scan |
| hybride pattern | 0129 | master, squelette+pattern | 12-sq base-3 | **0.667 vs hc** (Gate 2) |
| **champion** | 0141/0170 | master+**Scan-d10**, score-drop | 32 patterns+106 extras | 0.39 vs v15 d9 / 0.38-0.42 mt ; **0 vs Scan** |
| géométrie v6 | 0166/0186 | diagonale dense | 40 patterns | d9=0.556 (bat v15 fixe) mais **se dégrade en profondeur** |
| deep-d12 | 0200 | self-play, **relabel d12 teacher-free** | archi champion | 0.306 vs v15 |
| **full-fold** | 0227/0231 | self-play WDL **itéré** (8 gens d4), pli sym complet | 32 patterns+106 extras (17M→1M poids) | **+175 / +142 vs hc** (gen8) ; men-only (rois invisibles) |
| **king-aware** | 0240/0241 | distill Scan-d10 + loop full-fold scalé, patterns **men\|kings** | 32 pat king-aware +106 extras | **+37 vs men-only** (0240, distill) ; loop scalé 0241 en cours |

### Impasses (raison en une ligne)
- **Corpus 10M** — gelé, €700+ pour +30-80 ELO vs un déficit −800.
- **Gros MLP (v9/v11)** — overfit ; v11 = 0.009 movetime vs Scan.
- **Cheap/hybrid eval Tier-1** — casse la cohérence alpha-beta (0096).
- **Lazy accumulator** — >90 % des nœuds touchent l'eval (0098).
- **Pattern standalone (5 variants)** — doit augmenter, pas remplacer (0118-0127).
- **TD-leaf d'une eval faible** — s'effondre 0.056 ; méthode ≠ levier (0149).
- **Plus de data / teacher plus profond** — neutre une fois labels propres (4.7M≈1.4M, d16≈d10).
- **Géométrie comme levier** — close sous 3 angles (0230/0231/0234) : enrichir ne paie
  pas (54-pat +134 < 32-pat +175), importance uniforme (aucun gras), **élaguer = −31 Elo
  ET 0 vitesse** (la lenteur d'eval est dans les 106 extras, pas les lookups patterns).
- **`--phase-weight`** (densifier la finale en pondérant les lignes) — **MORT** : −210 Elo
  sur bons labels score (0261), neutre/négatif sur WDL (0254/0257). Sur-pondérer les scores
  de grande magnitude de finale dé-calibre l'éval du gros du jeu ; le phase-split ne protège pas.
- **`--label-depth-by-phase` en boucle WDL** — no-op (cible = WDL, pas score) ET nocif
  (recherche de label profonde → pollue la TT → corrompt les parties jouées), −80 Elo (0254/0258).
- **Extras structurels** (0172), **augmentation symétrie** (0185, 0.42→0.28),
  **filtre quiet** (post-score-drop) — **nuisent**.
- **Self-distillation itérée** — dérive ; **WDL self-play** — toxique.
- **Cible WDL** — plafonne 0.22 quelle que soit la source (0194/0196) ;
  score @30ms pire (0.08, 0198).
- **Bucket-hashing / freq-reg** (0190/0193) — cassent v6 d9 (les buckets rares
  portent la connaissance).
- **Le « 0.870 / +331 vs Scan-d10 »** — INVALIDÉ : bug de buffer dans
  `calibrate_vs_scan.py` faisait forfait Scan sur coups illégaux en profondeur
  fixe (0137/0139, corrigé).

### Pourquoi on en est là aujourd'hui
Tout l'arc est la correction d'**une erreur de mesure** : pendant ~190 jobs on a
benché **contre v15**, qui est lui-même **≈ 0 vs Scan** — donc un champion
« flatteur » à 0.39 vs v15 vaut **0.000 vs Scan à profondeur égale** (0199). Le
parcours a prouvé, par élimination, que la **recherche est complète** et que la
**vitesse est secondaire** (le ×8 NPS ne compte pas quand on perd déjà à
profondeur égale, 0201) ; le **seul levier dominant est la qualité d'eval**, et
son meilleur prof est le **label de recherche profonde** (deep-d12 0.306 ≫ WDL
0.22 ≫ score superficiel 0.08). Le `--score-drop` et le champion qui en découle
furent un vrai progrès **dans la classe linéaire**, mais un seul cycle de
bootstrap **rejoint le prof sans le dépasser** — d'où la route actuelle :
**programme multi-cycles teacher-free de relabel profond** (regénérer avec l'eval
améliorée → re-relabel deep → retrain), que `0202`/`0203` amorcent.
