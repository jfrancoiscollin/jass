# CURRENT — source de vérité active (programme « battre Scan »)

> **1 page, à jour à CHAQUE verdict.** Le détail vit ailleurs : [BOUCLE_VIRTUEUSE.md](BOUCLE_VIRTUEUSE.md) (système
> actif), [JOURNAL_DE_BORD.md](JOURNAL_DE_BORD.md) §0 (faits/chronologie), [SCAN_METHODOLOGY_GAP.md](SCAN_METHODOLOGY_GAP.md)
> (règles permanentes), [ARBRE_DECISION.md](ARBRE_DECISION.md) (principe). MAJ : **2026-06-20**.

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
`train_stream`, vers 30-100M), self-jugée. **NNUE (type A, apprentissage de représentation) UNIQUEMENT SI** ça plateaute
encore **à gros volume + profondeur** (cf BOUCLE_VIRTUEUSE §1 : A invente des features, B optimise des poids fixes = nous).

## Defaults actuels (build/recherche) — vérifier via le manifeste d'artefact
| flag | valeur | source |
|---|---|---|
| `JASS_ENDGAME_FEATURES` | **ON** (NUM_EXTRAS=110) | baké 0311 |
| `JASS_KING_MOBILITY` / `JASS_KING_PATTERNS` | OFF / OFF (0360 : rois ≠ levier finale) | 0311 / 0240 / 0360 |
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
  (32cf = 8,5M ⊃ Scan 2,1M = 8cf). 32cf vs 8cf = la question ouverte, à trancher **à gros volume**.
- **Infra (cf BOUCLE §6)** : `gen_patterns --emit` pas reset-proof → build de suite + `JASS_PATTERNS_DIR` hors-tree +
  garde-fou ×32 ; runner **nettoie l'untracked du tree mid-job** → **travailler HORS-tree** ; pjtw full-fold 136 Mo → **gzip** (cap git 95 Mo) ;
  cross-box fragile → boucle **self-contained une box**.

## Branches MORTES / à REVISITER
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
| **FM/MLP (NNUE)** | reporté (principe) | plateau confirmé **à gros volume + profondeur** |
| Drawish ÷8/÷2 | NEUTRE en jeu (0353), codé défaut 0 | — |

## Jobs en cours (2026-06-20)
- **cpx62** : **0381** (boucle vertueuse autonome AUTO-STOP, self-contained hors-tree, juge parallèle N≈1000, bake-off
  32cf/8cf tous les 2 tours) → puis **0383** (test scale-du-fit : minibatch 5M vs 2M).
- **ccx33** : **0382** (diversité d12, additif non-bloquant ; la prochaine boucle piochera).
- **PC perso** : éteint.
- **Acquis** : 0373/0374 (boucles profondes grimpent) · 0378 (capitalisation : champion poolé bat les 2 boxes) ·
  `train_stream.py` livré · auto-stop câblé.
