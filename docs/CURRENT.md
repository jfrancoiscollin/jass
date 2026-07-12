# CURRENT — source de vérité active (programme « battre Scan »)

> # ⛔⛔ RÈGLE GRAVÉE DANS LE MARBRE (2026-06-23, JFC) — AUCUN NNUE ⛔⛔
> **ZÉRO NNUE, ZÉRO réseau, ZÉRO changement de classe TANT QUE la classe LINÉAIRE n'est pas POUSSÉE À FOND.**
> Justification empirique : on a **8,5M poids vs 2,1M pour Scan** et on ne l'a **même pas égalé** → la classe linéaire
> est **LOIN d'être épuisée** ; notre FIT est juste moins bon que celui de Scan. Leviers linéaires à épuiser AVANT toute
> évocation de NNUE : **distillation depuis Scan au scale** (Scan = prof dispo), itération, géométrie, qualité de data,
> recherche. **NNUE = INTERDIT** jusqu'à preuve d'un vrai plafond linéaire (best-linear-fit atteint ET < Scan). Non négociable.

> **1 page, à jour à CHAQUE verdict.** Le détail vit ailleurs : [BOUCLE_VIRTUEUSE.md](BOUCLE_VIRTUEUSE.md) (système
> actif), [JOURNAL_DE_BORD.md](JOURNAL_DE_BORD.md) §0 (faits/chronologie), [SCAN_METHODOLOGY_GAP.md](SCAN_METHODOLOGY_GAP.md)
> (règles permanentes), [ARBRE_DECISION.md](ARBRE_DECISION.md) (principe). MAJ : **2026-07-12**.

## 🧭 CHANTIER ACTIF 2026-07-12 — ADJUDICATION PAR PRÉDICATS notés par la TB (MEMO_ADJUD_PREDICATS)
> Objectif : étendre l'adjudication au-delà du matériel brut (là où le ply-cap pollue) via des **prédicats structurels
> déterministes** composés depuis les primitives **dilf** (`pedagogy/features`), **notés par la TB** (egdb WLD ≤7 pièces,
> exact). Admission ≥ **99,9%** de précision, sinon rejet. Détail → [MEMO_ADJUD_PREDICATS.md](MEMO_ADJUD_PREDICATS.md).

**Infra livrée (jass-first)** :
- jass **`--dump-legal`** (émetteur batch de coups légaux) sur `develop` → back l'`EngineProtocol` dilf (`DumpEngine`).
- Module **`pattern_jass/tools/adjud/`** (engine + prédicats) sur `develop`. dilf cloné/importé sur la box (pont FEN validé).
- **Harnais §2 (0680)** : le juge TB tourne. **Baseline matérielle vs TB** (200k pos uniformes ≤7pc) :
  marge nette `M` men-eq (dame=3) → WIN : **M=4 → prec 81% / faux-WIN 16k** ; **M=12 → prec 99,977% mais fire 2,2%**.
  ⇒ le matériel seul est soit couvrant-imprécis, soit précis-marginal → **il FAUT des prédicats structurels**.

**Verdict 0681 — v0 P2/P3 REJETÉS** (le harnais a tué de mauvais priors) : P3 veto (dame enfermée) **prec 38,9%**,
P2 draw (mobilité faible) **prec 45-48%** — ≪ 99,9%. Diagnostic : en finale creuse, « dame piégée » reste souvent
gagnante et « peu de coups » est souvent décisif → priors écrits-main faux.

**➡️ Minage (0682)** : les nulles-exceptions = **finales de dames** (`def_has_king` 22,6%→69,1% WIN→DRAW). Aucun cran
engine-free ≥99,9% (best 78,6%). **A1 veto `def_has_king` mesuré = recall 69%** des nulles.

**Verdict 0683 — P1 percée→WIN REJETÉ** (prec 75-76% ≪ 99,9%). **CONCLUSION 3× confirmée : aucun prédicat structurel
(matériel/géométrie) n'atteint le seuil verdict** — la vérité y est TB-profonde (raison d'être des TB). **⇒ programme
prédicats = VETOS SEULEMENT** : escalier = TB-exact (≤7pc, outillé) + rungs veto (`def_has_king` &co, coût nul), **pas
d'étage verdicts**. Pivot productif = mémo §B (TB-direct en gen) + veto `def_has_king`.

**Track parallèle livré — PROF DE PRÉFÉRENCES ÉLITE (mémo D)** : pipeline `clean_pdn.py` + jass **`--replay-moves`** →
`--gen-siblings --played-moves` (master : coup-élite préféré, sœurs dominées) → `rank_finetune`. Testé bout-en-bout, WDL
jeté (préférences only). Acquisition : bulk Bouma OU fetcher FMJD (recon 0684 : joignabilité box).

## 🔬 DIAGNOSTIC 2026-06-23 — on perd vs Scan par COMBINAISONS en milieu de partie (pas finale, pas profondeur)
> 📋 Détail → [DIAGNOSTIC_VS_SCAN.md](DIAGNOSTIC_VS_SCAN.md). Match eval-pur no-DB, champion 3e-5 vs Scan (0435).

**Échelle handicap** : jass d11/d13/d15 vs Scan d11 = 0,056 / 0,000 / 0,028 → **la profondeur ne rattrape PAS**.
**Analyse des défaites** : **17/17 par COMBINAISON** (shot : ≥2 matériel en ≤2 plies), en **plein milieu (26 pièces, move ~27, men-only)**, **0/17 dérive lente**. On se fait **cueillir par des coups**, pas user en finale.

**VERDICT A/B (0436)** : élagage OFF = 0,028 ≈ ON = 0,056 → **ce n'est PAS la recherche, c'est l'EVAL.** MAIS (logique clé) **Scan a 2,1M poids, nous 8,5M, et il nous bat** ⇒ **PAS un plafond de capacité** : notre best-linear-fit possible est ≥ le sien, **notre FIT est juste moins bon** (self-play borné par notre pilote faible → point fixe trop bas). **Prochain levier LINÉAIRE = distiller depuis Scan au scale** (le prof est dispo) pour atteindre son point fixe. ⛔ **NNUE INTERDIT** (cf règle gravée en tête).

## 🔴 RÉVISION 2026-06-23 — « scaler vers les milliards » est INFIRMÉ par la littérature (rapport documenté)
> 📚 Détail + sources → [PROGRESSION_LITTERATURE.md](PROGRESSION_LITTERATURE.md) (6 angles, vérifié).

**Le mythe tombe** : Scan **n'a PAS** utilisé des milliards de data. Son eval = **~2,1M poids** (code source lu, *plus
petit* que notre 32cf 8,5M ≈ notre 8cf) ; volume d'entraînement **non documenté** ; la famille Kingsrow = **~1M parties /
145-231M positions** = **NOTRE ordre de grandeur**. Donc on n'est **pas** « 3 ordres sous Scan ».

**Théorie (vérifiée, scikit-learn + TD linéaire)** : un modèle **linéaire à features fixes** converge vers un **point
fixe UNIQUE** en **peu d'itérations** ; le **plafond = les features**, et **le volume ne fait que de la PRÉCISION**
(variance des poids), pas le biais de classe. ⇒ **un plateau rapide / petits gains près du plafond = NORMAL**, et
**scaler au-delà de ~50-100M n'est PAS un levier de force** (couverture déjà saturée, cf BOUCLE §10).

**Les deux SEULS leviers pour dépasser** (révise le principe directeur ci-dessous) :
1. **géométrie linéaire PLUS RICHE que Scan** (32cf 8,5M ⊃ 8cf 2,1M), bien fittée → relève notre point fixe au-dessus du sien ;
2. **NNUE** (non-linéaire) = lève-plafond documenté → **⛔ INTERDIT tant que le linéaire n'est pas épuisé** (règle gravée en tête).

## ✅ VERDICT 2026-06-21 (quater) — rois TRANCHÉS : men-only gagne, king-aware perd (GATE 2b / 0409)
> Sur **36,2M**, 32cf color-fold, fit `train_stream --king-patterns` (extension livrée + validée), juge cross N=252.

**king-aware vs men-only = 0,306** (−6σ) → les rois dans l'occupancy des patterns **DILUENT**. Le verdict 0240/0360 **TIENT au scale** (PAS confondu par le fit-volume) — re-testé exprès à 36M, men-only confirmé meilleur. Les rois restent servis par les **extras** (king-PST/mobilité), pas par les patterns.

**→ Archi VALIDÉE au scale sur 3 axes** : 32cf>8cf (0401) · color-fold>no/full-fold (0408) · men-only>king-aware (0409) ⇒ **32cf color-fold men-only verrouillé, dé-confondu**. Plus de question d'archi ouverte → place à l'**ITÉRATION**.

## ✅ VERDICT 2026-06-21 (ter) — fold TRANCHÉ : color-fold gagne, no-fold/full-fold perdent (GATE 2a / 0408)
> Sur **33,4M**, 32 patterns, 3 fits `train_stream`, juge cross N=252.

| fold vs color-fold | score | lecture |
|---|---|---|
| **no-fold** (17M poids pleins) | **0,417** | perd (−2,6σ) — capacité en + **non justifiée**, encore affamé |
| **full-fold** (translation) | **0,306** | perd — contrôle OK (mauvaise invariance) |

**→ `color-fold` VERROUILLÉ** comme géométrie de prod. Cohérent avec la couverture (verdict bis) : no-fold double les poids → buckets rares à <2 % du jeu → **inutile de le rechercher à 100M**. Le levier n'est ni le fold ni le volume brut → **itération**.

## ✅ VERDICT 2026-06-21 (bis) — la couverture utile est DÉJÀ gagnée → le moteur, c'est l'ITÉRATION (pas + de volume)
> Mesuré sur **8,4M de nos parties** (color-fold, TB=8 503 072) : distribution réelle des visites de buckets.

| seuil visites | % des **buckets** | % du **JEU réel** (activations) |
|---|---|---|
| ≥5 | 62 % | **99,7 %** |
| ≥30 (bien déterminés) | 34 % | **98,1 %** |
| ≥100 | 20 % | **94,8 %** |

**« 47 % de buckets bien déterminés » TROMPE** : les 66 % mal déterminés pèsent **1,9 % du jeu réel** (configs rarissimes). **98 % de ce qui se joue tombe déjà sur des buckets bien déterminés dès ~8M.** Le volume fait 2 choses : **COUVERTURE** (≈ saturée à **10-30M**) + **PRÉCISION** des fréquents (rendements **décroissants**). Donc :
- **NE PAS courir après le volume** (80M/round inutile : on ne couvrirait que la queue à <2 % du jeu). **Socle ~30-60M suffit.**
- **Le moteur de progression = ITÉRER** (pilote améliorant → concentre les visites là où ça compte, y c. nos finales de rois faibles), **pas grossir la fenêtre**. → fenêtre boucle figée **35M** (98 %+ de couverture, +turnover) ; gen **mix d10/d12 5:1 par compte** (≈2:1 en temps car d12 ~2,5× plus lent : d12 = 17 % des positions / ~33 % du compute — minorité réelle, d10 décisivité+volume domine).
- ⚠️ **tempère** l'optimisme « viser 100M » du 0401 : le **60M vs 29M** (GATE progression) montrera un gain **MODESTE** (précision), pas un nouveau 0,69. Le gros gain (2M→30M) est **encaissé**.

**Pruning VÉRIFIÉ** : `--prune-min-visits=1` **lossless** ; ~1,16M buckets actifs à 8,4M (→ ~1,77M à 60M) ; **86 % des 8,5M jamais vus** (configs illégales → 0). **Fit 60M en streaming OK** (bloc prunée ~1,8M, ~2 Go RAM). **L2** (calé ≤2M, 0176) **re-swept au scale** (3e-5/1e-4/3e-4) dans le GATE progression. `train_stream --king-patterns` **livré + validé byte-compat**.

## ✅ VERDICT 2026-06-21 — fit-volume CONFIRMÉ, la géométrie riche s'INVERSE au scale (GATE 0401)
> Matrice 2×2 (volume × archi) sur le corpus **29M** (17 shards), fits `train_stream` (gradient exact), juge cross-arch N=252/case.

| | mesure | score A vs B | signif. |
|---|---|---|---|
| **V32** | 32cf@29M vs 32cf@2M | **0.694** | +6.2σ — le **volume paie** (archi riche) |
| **V8** | 8cf@29M vs 8cf@2M | 0.472 | ns — volume **inutile** (archi pauvre sature à 2M) |
| **A29** | 32cf@29M vs 8cf@29M | **0.583** | +2.6σ — au scale la **riche gagne** |
| **A2** | 32cf@2M vs 8cf@2M | **0.306** | +6.2σ (8cf) — à 2M la riche **perd** |

**L'INVERSION est réelle** : A2=0.31 (riche perd affamée) → A29=0.58 (riche gagne nourrie). **La même archi passe de perdante à gagnante juste en la nourrissant.** ⇒ « géométrie morte / 8=32 / full-fold » = **CONFONDUS confirmés**. **Archi gagnante = 32cf**, figée pour la boucle de prod (`train_stream` sur corpus accumulé, plus de fenêtre 2M). Note : 32cf encore sous-nourrie à 29M (3.4 visites/poids vs ~30-50 idéal) → son avantage **croîtra** avec 100M+.

## 🎯 Hypothèse active (2026-06-20) — on était limité par le FIT, pas par l'archi
> 📘 **Système actif → [BOUCLE_VIRTUEUSE.md](BOUCLE_VIRTUEUSE.md)** (boucle vertueuse profonde + scale du fit).

**LA découverte (JFC) : depuis le début on fittait sur ~2M positions max** (limite full-batch RAM). Donc on jugeait
l'archi linéaire **affamée**. → plusieurs verdicts (« géométrie morte » 0230/0234/0239, « plafond linéaire ») sont
**confondus** par cette famine et **à revisiter**. Scan : milliards de positions ; nous : millions = 3 ordres en dessous.
**Les deux vrais leviers** : (1) **jeu profond** (d≥10 → issues véridiques, pas blunder-driven, 0363/0365) ; (2) **scaler
le FIT** (volume d'entraînement). Plan = boucle vertueuse profonde, self-jugée, **fit qui grossit avec la data**.

### Scale du fit — 3 tiers (le mur historique levé)
| tier | méthode | volume | état |
|---|---|---|---|
| 0 | full-batch `--lowmem` | ~2,4M | le mur (OOM 3,4M) |
| 1 | **`--minibatch --loss logistic`** (RAM, design streamé) | ~10-15M | **dispo, 0 code** (le « L2-only » visait les ancres) — test 0383 |
| 2 | **`tools/train_stream.py`** (disque, gradient EXACT 3e-15) | **15-100M+** | **livré + unit-validé, byte-compatible C++** |

⚠️ **Un plateau de la fenêtre 2M ≠ le vrai plafond** (elle expulse les buckets rares avant leurs 30-50 visites). Avant
de « ressortir Scan » : **test scale-du-fit** (gros fit sur le cumul). Nouveau pacing = la **génération** (~1,4M/h →
30M ≈ ~21h). Acquis : boucles profondes GRIMPENT (0373/0374) ; champion poolé bat d10 ET d12 (0378) ; **d10 > d12** (0.75, volume gagne).

## ⛔ Principe directeur (MAJ 2026-06-20)
**Scaler le fit linéaire AVANT tout pivot.** Scan = même classe (linéaire-patterns) et plus fort ⇒ **pas de plafond de
classe** là où on est ; notre fit était juste **affamé**. Donc : boucle vertueuse profonde + fit qui grossit (minibatch →
`train_stream`, vers 30-100M), self-jugée. **NNUE = INTERDIT** (règle gravée en tête) tant que le LINÉAIRE n'est pas
épuisé — et on a **plus de poids que Scan sans l'égaler**, donc il ne l'est pas. (cf BOUCLE_VIRTUEUSE §1 : A invente des
features, B optimise des poids fixes = nous ; on reste en B jusqu'à preuve d'un vrai plafond linéaire.)

## Defaults actuels (build/recherche) — vérifier via le manifeste d'artefact
| flag | valeur | source |
|---|---|---|
| `JASS_ENDGAME_FEATURES` | **ON** (NUM_EXTRAS=110) | baké 0311 |
| `JASS_KING_MOBILITY` / `JASS_KING_PATTERNS` | OFF / OFF (rois ≠ levier ; **confirmé au scale 36M, 0409**) | 0311 / 0240 / 0360 / 0409 |
| `JASS_SCAN_PARITY` / `JASS_TEMPO_STAGE` | ON (builds boucle) | 0323 |
| search NMP (`eg_no_nmp`) | **OFF partout** (garder) | +97 Elo 0256/0259 (zugzwang) |
| search **multicut**(min6,moves8,cuts2) + **razor**(max4) | **BAKÉ ON** (~+50 Elo, seul gain recherche) | 0336/0338/0343 |
| search probcut / iid / conthist / history-malus / TT>16Mo | OFF (plats, cf SEARCH_TUNING) | 0334-0344 |

## Métrique (pivot 2026-06-19)
**Juge = SOI-MÊME, EN DIRECT** : `benchmark-nnue-vs-nnue` (même archi) ou `tools/jass_vs_jass_arch.py` (cross-archi, shardé
parallèle), bande ~0.5 = sensible. **Scan ne ressort qu'au PLATEAU *après* scale-du-fit** — jamais au plancher (bruité,
run-to-run ±0.05, insensible). SCREEN_ONLY : `endgame_mse`/`val_mse`/Elo_hc (⚠️ ⟂ force, 0311/0312). Auto-stop boucle :
champ_k vs champ_{k-1} ≤ 0,52 (≈1σ@1000) 3 tours + cumulé ≤0,53, par archi (cf BOUCLE_VIRTUEUSE).

## 🔒 Règles permanentes (détail → [SCAN_METHODOLOGY_GAP.md](SCAN_METHODOLOGY_GAP.md))
- **Jeu profond ≥10** : décisif ≠ véridique (d4 = blunder-driven → value-function d'un faible, 0363/0365).
- **Scaler le fit** : la fenêtre 2M plafonne *artificiellement* ; `--minibatch` **supporte la logistique**, puis `train_stream`.
- **Géométrie/fold** : `--full-fold` impose une invariance par TRANSLATION **fausse en dames** → écrase les familles de
  translates → **nos verdicts « géométrie » sont CONFONDUS**. Comparer au repli position-préservant **`--color-fold`**
  (32cf = 8,5M ⊃ Scan 2,1M = 8cf). **TRANCHÉ au scale** : 32cf > 8cf (0401) ET color-fold > no-fold > full-fold (0408) → **color-fold 32cf verrouillé**.
- **Infra (cf BOUCLE §6)** : `gen_patterns --emit` pas reset-proof → build de suite + `JASS_PATTERNS_DIR` hors-tree +
  garde-fou ×32 ; runner **nettoie l'untracked du tree mid-job** → **travailler HORS-tree** ; pjtw full-fold 136 Mo → **gzip** (cap git 95 Mo) ;
  cross-box fragile → boucle **self-contained une box**.

## Branches MORTES / à REVISITER
> 📋 **État des lieux complet des verdicts CONFONDUS par le fit-volume → [BIAIS_FIT_VOLUME.md](BIAIS_FIT_VOLUME.md)** (géométrie, fold, hash, rois, WDL, méta « plafond linéaire »).
| Levier | Statut | reviendrait si… |
|---|---|---|
| **Rallumer NMP** | MORT −97 Elo (zugzwang) | — |
| **TT >16 Mo / movegen captures / probcut-iid-conthist** | MORT (plats, cf SEARCH_TUNING) | — |
| `--phase-weight` | MORT −210 Elo (0261) | — |
| Gradient MTC comme CIBLE | MORT (99,9 % proxy, 0306) | densité MTC massive |
| Covariate-shift PUR (data forte seule) | MORT (0327/0329/0331) | pool mixte |
| Distillation via jass-self-play | MORT (0362/0364 : dégrade) | — |
| WDL/bootstrap depuis data DÉJÀ forte/drawish | MORT (0356/0357 : cible ≈0.5) | départ faible décisif |
| **« Géométrie morte » / « élaguer la capacité »** | ⚠️ **CONFONDU par le fit-volume** (testé à ≤2M) | **À REVISITER** (color-fold + 30M+) |
| **FM/MLP (NNUE)** | ⛔ **INTERDIT** (règle gravée 2026-06-23) | best-linear-fit ATTEINT **et** prouvé < Scan (linéaire épuisé : distill-Scan, itération, géométrie) |
| Drawish ÷8/÷2 | NEUTRE en jeu (0353), codé défaut 0 | — |

## Pipeline actif (2026-06-21) — socle 60M → gates → ITÉRATION
> 📘 Mécanique détaillée → [BOUCLE_VIRTUEUSE.md](BOUCLE_VIRTUEUSE.md) §7 (boucle d'itération 60M).

**En cours** : cpx62 termine **0405** (boucle prod 32cf, **retirée** ensuite — accumulation +0,8M/round sous le bruit) ;
ccx33 **gen pure** (0415+). **Queue cpx62 (auto-enchaînée)** : `0408` GATE 2a (fold : color vs **no-fold** vs full) →
`0409` GATE 2b (**rois** king-aware vs men, via `train_stream --king-patterns`) → `0411-0414` **gen pure** (+11,2M).
**ccx33** : `0415-0418` gen pure (+5,6M). Tous **pilote figé `w32_full`**, vers le **doublement ~60M**.

**Prêts, non déployés (lancés au bon moment)** :
- `0410` **GATE progression + sweep L2** (challenger@~60M vs baseline 29M) → au doublement. Mesure le gain de PRÉCISION
  du volume (attendu **modeste**) et **fige le L2 au scale**. Auto-gardé (no-op si <55M).
- `0420` **BOUCLE D'ITÉRATION 60M** (le MOTEUR) : régénère une large fenêtre fraîche **pilotée par le champion courant**
  (mix d10/d12 5:1 par compte) → fenêtre glissante FIFO 35M → refit → juge **champ_k vs champ_{k-1}** → auto-stop. Data box-local (régénérable) ;
  champions committés. Se lance une fois le socle 60M là.

**Object store** : dormant, **non bloquant jusqu'à ~70-80M** (git porte ; `.git`≈1,7 Go). Diagnostic + activation →
[OBJSTORE_SETUP.md](OBJSTORE_SETUP.md). **Acquis** : `train_stream` (+king) livré · pruning lossless vérifié · gen pure
(pilote figé) remplace le théâtre de mesure de 0405.
