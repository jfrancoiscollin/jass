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
