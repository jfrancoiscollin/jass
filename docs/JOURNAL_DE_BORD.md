# Journal de bord — programme « battre Scan »

> **À LIRE AVANT DE (RE)CHERCHER.** Registre court et tenu à jour à chaque
> verdict. Ancres mesurées + faits établis (à ne pas re-litiger) + index des
> jobs. Pour l'analyse détaillée → [PATTERN_PROGRAM_NOTES.md](PATTERN_PROGRAM_NOTES.md).
> Pour ce qui est **codé** → [ARCHITECTURE.md](ARCHITECTURE.md).
> Pour **comment on en est arrivé là** → [§6 Historique](#6-historique-du-projet--le-cheminement-0001--0202).
> Pour **quel chemin prendre selon quel verdict** → [ARBRE_DECISION.md](ARBRE_DECISION.md).
>
> Mise à jour : **2026-06-12** (après 0202 ; lance 0203 = boucle WDL itérée).

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

**Décision (2026-06-13) :** on TUE les deux boucles mt100 starvées (300k/gen ne peut
que reproduire la famine) et on lance la famine en test direct sur les DEUX box, en
boucles à **corpus CUMULÉ** (gen_g s'entraîne sur l'union de tout le self-play) :
- **`cpx62-0211-cumulative-loop-1M`** (box 32GB/16c) — **1M/gen** cumulé, 5 gens
  (→ ~5M), couverture+proxy par gen.
- **`ccx33-0210-cumulative-loop`** (box 16GB/8c) — **300k/gen** cumulé, 6 gens
  (→ ~1.8M), couverture+proxy par gen.
Verdict : le proxy MONTE au-dessus de 0.41 quand la couverture grandit ⇒ famine
confirmée + accumulation/volume = le fix (linéaire, Scan). (La boucle « volume
sweep » mono-gen a été remplacée par ces boucles cumulées sur décision user.)

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

### Impasses (raison en une ligne)
- **Corpus 10M** — gelé, €700+ pour +30-80 ELO vs un déficit −800.
- **Gros MLP (v9/v11)** — overfit ; v11 = 0.009 movetime vs Scan.
- **Cheap/hybrid eval Tier-1** — casse la cohérence alpha-beta (0096).
- **Lazy accumulator** — >90 % des nœuds touchent l'eval (0098).
- **Pattern standalone (5 variants)** — doit augmenter, pas remplacer (0118-0127).
- **TD-leaf d'une eval faible** — s'effondre 0.056 ; méthode ≠ levier (0149).
- **Plus de data / teacher plus profond** — neutre une fois labels propres (4.7M≈1.4M, d16≈d10).
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
