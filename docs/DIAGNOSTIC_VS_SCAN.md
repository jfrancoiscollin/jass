# Diagnostic vs Scan — POURQUOI on perd (2026-06-23)

> Analyse des parties champion 32cf (fit L2=3e-5@35M) vs **Scan**, **eval pur (no-DB des 2 côtés)**, depth fixe.
> Source : job `ccx33-0435-scan-handicap-ladder` (18 parties/rung, déterministe → ordre de grandeur). À lire avec
> [PROGRESSION_LITTERATURE.md](PROGRESSION_LITTERATURE.md).

## Résultats bruts
**Échelle de handicap** (jass-depth vs Scan d11, no-DB, 18 parties) :
| jass-depth | score vs Scan d11 |
|---|---|
| 11 | 0,056 (1 gagnée / 17 perdues) |
| 13 | 0,000 |
| 15 | 0,028 |

→ **La profondeur ne rattrape PAS** (plat à ~0 même +4 plies). Ce n'est **pas** un manque de recherche.

**Analyse des 17 défaites (d11)** :
- **17/17 par COMBINAISON** : ≥2 pions-équ perdus en ≤2 plies (un *shot*). **0/17 dérive lente.**
- Phase : **plein milieu de partie**, **26 pièces** sur le damier (médiane), move ~27 (ply 54), **pions seulement** (rois présents seulement 4/17).
- Ampleur médiane : 2 pions-équ (un coup net qui gagne une pièce).

## Conclusion
**On se fait cueillir par des COMBINAISONS en plein milieu de partie men-only — pas en finale, pas par dérive
positionnelle, pas par manque de profondeur.** (Ma 1ʳᵉ lecture « blocage finale » était FAUSSE : *no legal move*
est juste la fin normale d'une partie de dames.)

## Hypothèse forte (à tester) : notre ÉLAGAGE nous rend tactiquement aveugles
Normalement, chercher plus profond évite les combinaisons. Or la profondeur ne rattrape pas → le coupable probable
est notre **élagage forward** (`multicut` min6/moves8/cuts2 + `razor` max4, bakés ON, **+50 Elo EN SELF-PLAY** 0336/0343).
Il **coupe les lignes tactiques défensives** : à toute profondeur nominale la ligne est élaguée → la défense n'est jamais vue.
**Invisible en self-play** (les 2 côtés élaguent pareil), **mais une vraie faiblesse contre un adversaire tactiquement
aiguisé comme Scan.**

- **Test décisif** : rejouer avec **élagage OFF** (`--jass-search-params "multicut_min_depth=0,razor_max_depth=0"`).
  - Si le score **monte** → c'est l'élagage (faiblesse de **RECHERCHE**, réparable, **pas NNUE**).
  - Si le score **reste ~0** → c'est l'**EVAL** (elle guide dans des positions shot-vulnérables) → richesse linéaire / NNUE.
- Job A/B : `ccx33-0436-scan-pruning-ab` (élagage ON vs OFF, d11, no-DB, même champion).

## Ce que ça change au cadre stratégique
- Avant ce diagnostic : « eval-limité → NNUE » semblait la seule issue.
- Maintenant : **une part de l'écart à Scan pourrait être de la RECHERCHE** (élagage trop agressif vs adversaire fort),
  **récupérable sans changer de classe**. À trancher par l'A/B avant toute décision NNUE.
- ⚠️ Réserves : 18 parties déterministes, champion mi-itération, no-egdb (mais le décrochage est en **milieu** de partie
  à 26 pièces → l'egdb n'y change rien).

## VERDICT A/B (0436, 2026-06-23) — c'est l'EVAL, et le linéaire n'est PAS épuisé
- élagage **ON** = 0,056 · élagage **OFF** = 0,028 → **B ≈ A : ce n'est PAS la recherche.** Hypothèse élagage RÉFUTÉE.
- Donc l'écart est dans l'**EVAL**. MAIS **Scan = 2,1M poids, nous = 8,5M, et il nous bat** ⇒ **PAS un plafond de
  capacité** : notre best-linear-fit possible est **≥** le sien ; **notre FIT est moins bon** (self-play borné par notre
  pilote plus faible → point fixe trop bas).
- **⇒ Prochain levier LINÉAIRE : distiller depuis Scan au scale** (Scan dispo en binaire ; `relabel_with_scan.py`,
  `scan_selfplay_gen.py` → fit train_stream → juger vs Scan) pour atteindre SON point fixe **dans la classe linéaire**.
  C'était classé MORT (0073-0084) mais **à ≤2M = confondu par le fit-volume** → à revisiter au scale.
- ⛔ **NNUE INTERDIT** tant que ce levier (et les autres linéaires) ne sont pas épuisés (RÈGLE GRAVÉE, cf CURRENT.md).

## MESURE TACTIQUE CHIFFRÉE (0440, 2026-06-23) — combinaisons de livre, jass vs Scan
Job `ccx33-0440-dilf-tactical` : champion 3e-5 **vs Scan**, **depth 11, eval pur (no-DB)**, joué **depuis 305
combinaisons de livre** (dilf `ALL_DIAGRAMS` → `data/dilf_combinations.fen`, médiane 26 pièces = plein milieu).
Chaque position jouée 2× (jass au trait / Scan au trait via swap). Métrique = **taux de conversion du camp AU TRAIT**
(celui qui a le coup gagnant). Verdict reconstruit depuis les 610 parties dumpées (`artefacts/games/`) :

| Camp **au trait** (a la combinaison gagnante) | Conversion |
|---|---|
| **JASS** | **0,246** (75 / 305) |
| **SCAN** | **0,954** (291 / 305) |
| **Écart** | **−0,708** |

- **Scan trouve+convertit 95 % des combinaisons ; jass seulement 25 % de LES MÊMES.** Pire : **499/610** parties
  finissent par « jass sans coup légal » (maté/bloqué) vs 67 pour Scan ⇒ **jass change régulièrement une position
  GAGNÉE en DÉFAITE.**
- À depth 11 ces combinaisons (2-6 plis) sont **dans l'horizon** : jass devrait les voir. S'il ne convertit pas,
  **c'est son éval qui le détourne du bon coup** (shot-vulnerable) — cohérent avec le verdict A/B (l'éval, pas la recherche).
- Caveat : la métrique mêle attaque (jass vs défense forte de Scan) et défense (Scan vs défense faible de jass) ;
  les deux pointent dans le même sens, donc −0,708 majore le pur trou d'attaque, mais la direction est certaine.
- **C'est notre meilleure cible MESURABLE** : refaire ce match (25 % → ?) après chaque champion = la jauge de progrès.

## CADRE STRATÉGIQUE COURANT (2026-06-23, après décisions JFC)
- ❌ **Distillation Scan ABANDONNÉE** (la ligne « distiller depuis Scan » ci-dessus est CADUQUE) : Scan est monté
  **sans** distillation, on doit pouvoir grimper sans (plafond = Scan ; dépendance Scan). Règle gravée.
- ✅ **Plan de base : self-play 100 % ÉPURÉ 25M, diversifié** (`cpx62-0442-freshmix-loop`) — chaque boucle régénère
  un corpus neuf avec une **composition de μ distincte** (profondeur de jeu d8/d10/d12 + seeds combinaisons dilf /
  milieux lidraughts + `--random-open-plies` + `--explore-eps`). Pilote = meilleur champion connu. Jugé vs base 3e-5 ;
  une recette qui passe `vs_base > 0,55` = composition de μ qui **casse le point fixe** (self-play à son point fixe = 0,50,
  cf `cpx62-0428` iter1/2 = 0,50). La cible directe : le trou tactique 25 %→ ci-dessus.
- 🅱️ **Réserve si stagnation : value-target distillation INDÉPENDANTE** (label = recherche profonde jass d18-20 + EGDB,
  PAS Scan). Outillage prêt et dormant : `--deep-relabel` (src/main.cpp) + `train_stream --target value` ;
  sonde `ccx33-0443-deeplabel-probe` en `jobs/paused/`. Failles connues (à corriger avant un vrai run) : filtre quiet
  / valeur-feuille, clip des scores de mat, contrôle WDL-vs-valeur, et **itérer** le relabel (sinon plafond sous notre
  propre force). Ne casse PAS un éventuel plafond de features (seul risque que rien de linéaire ne corrige).
- ⛔ **NNUE toujours INTERDIT** tant que le linéaire n'est pas poussé à fond (RÈGLE GRAVÉE).

## BRANCHE SEARCH/PROMOTION FERMÉE (2026-06-24, verdicts 0444-0452)
Investigation « et si l'écart combinaisons était de la RECHERCHE (élagage) ou un mur de promotion ? » → **non, cul-de-sac.**
- **0446 (ablation)** : LMR(27 %)+LMP(26 %) cachent ~40 % des combinaisons ratées **à profondeur fixe d11** → fix
  `no_reduce_forcing` construit (gaté, exempte les coups forçants de LMR/LMP).
- **0451 (décideur, A/B vs Scan à MOVETIME 300 ms)** : le fix **n'apporte rien à temps réel** — conversion combinaisons
  baseline **0,519** vs fix **0,506** (≈), jeu général légèrement pire. À movetime jass atteint **d14-16** → il trouve
  DÉJÀ les combos que le dé-élagage récupérait à d11 → bénéfice redondant + coût −1,6 plies. **Param gardé OFF par défaut.**
  ⇒ Le « gain search » était un **mirage du test à profondeur fixe d11** ; le d11 de 0440 **sous-estimait jass** (0,246
  vs 0,519 réel à movetime). Le résidu (0,52 vs Scan 0,95) est l'**ÉVAL**, pas la recherche.
- **0450/0453 (valeur du roi)** : l'éval valorise déjà le roi à **~3,5 hommes** → le mur promotion n'est PAS la valeur du roi.
- **0452 (promo egdb, 37 686 finales gagnantes)** : **0 sacrifice-de-promotion** trouvé → ce motif est du **MILIEU de partie**,
  pas de la finale (≤7 pièces) ; egdb ne peut pas le tester. (Branche promotion abandonnée — JFC, option B.)
- **CONCLUSION** : la recherche/l'élagage n'est PAS le levier. Le mur est l'**ÉVAL au milieu de partie** (combinaisons
  positionnelles shot-blind). Seuls leviers restants : **données/μ** (`0442`) et, à terme, **features linéaires plus riches**.

