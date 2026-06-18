# CURRENT — source de vérité active (programme « battre Scan »)

> **1 page, tenue à jour à CHAQUE verdict.** Le reste des docs = archive/historique.
> But : empêcher qu'un passage périmé relance une **branche morte** (cf le quasi-incident
> `--play-depth-by-phase` de l'audit 2026-06-17 : marqué « mort » dans une vieille ligne,
> en fait VIVANT). Lire avec [ARBRE_DECISION.md](ARBRE_DECISION.md) (principe + arbre) et
> [JOURNAL_DE_BORD.md](JOURNAL_DE_BORD.md) §0 (faits). MAJ : **2026-06-18**.

## Hypothèse active n°1 (2026-06-18) — COVARIATE-SHIFT : la DISTRIBUTION, depuis le départ
**Conviction JFC : « depuis le départ, on ne décolle pas à cause de ça ».** Le verrou n'est ni
les features, ni la capacité, ni le label — c'est la **distribution des positions d'entraînement**.
Toute notre data vient du **self-play de jass avec sa propre éval faible** (ou de coverage ≤7p
*aléatoire*) → on apprend l'éval (la nôtre OU celle de Scan en distillation) sur **les positions que
jass visite**, pas sur celles que **Scan traverse**. Covariate-shift classique.

**Pourquoi ça mord un LINÉAIRE plus fort que tout.** Un MLP a la capacité de bien fitter *partout* ;
un linéaire **partage les mêmes poids sur toutes les positions** → la distribution d'entraînement
*EST* la pondération de l'objectif. Mauvaise distribution = le fit linéaire **alloue ses poids au
mauvais endroit**, on n'optimise pas « là où ça compte ». Distiller Scan sur des positions que Scan
ne joue jamais = apprendre Scan dans ses angles morts à nous.

**Preuves convergentes (toute l'histoire la corrobore) :**
- Plateau **constant** 0/54 · −741 · −800 quels que soient les features → suspect commun = data.
- **`endgame_mse` ⟂ force** (0311/0312) : signature *exacte* du mismatch (on fitte les positions
  données, ça ne transfère pas au jeu).
- **0309/0310** « linéaire fitte la finale à mse 3.03, 0 contradiction ≤7p » : on sait fitter les
  positions qu'on a — elles sont juste **les mauvaises**. Renforce, ne contredit pas.
- **Champion Scan-distillé** ne bat jamais Scan : distillé sur distribution faible.
- **0306** (gradient ne transfère pas, 99,9 % proxy) : encore couverture/distribution.

**Test décisif — 0327 (cpx62)** : A/B chirurgical, seule la SOURCE des positions change. ARM-OLD =
distribution 0314 ; ARM-NEW = **jeu propre de Scan** (Scan joue les deux côtés, on dumpe son chemin —
`tools/scan_selfplay_gen.py`). Même archi FULL Scan-alignée, même relabel Scan d9, même train, même
taille, même juge vs Scan mt1.5. **`new ≫ old` → conviction DÉMONTRÉE** (reframe tout le programme) ;
`new ≈ old` → seul résultat qui l'infirme → regarder recherche/temps ou terme d'éval tuné manquant.

**Conséquence si confirmé** : on ne « rajoute » plus rien. On **régénère toute la data depuis du jeu
fort**, puis on **co-évolue la distribution** (AlphaZero-style) : éval distillée-forte → self-play
avec *cette* éval (visite des positions quasi-fortes) → re-distille → … La distribution monte avec
l'éval au lieu de tourner sur les angles morts de jass. Corpus `ccx33-0328` = 1re brique.

## Hypothèse active n°2 (subordonnée) — verrou finale-rois
Fermer le verrou **finale-rois DANS la classe linéaire**. Le gap n'est **PAS la capacité**
(0309/0310 : *conflit de phase*, pas saturation). Leviers : features rois (`king_mob`/`endg`),
phase-split. ⚠️ **Réinterprété par n°1** : si même la finale est mal *distribuée* (coverage ≤7p
aléatoire ≠ finales que Scan atteint), ce verrou n'est qu'une *facette* du covariate-shift. Jugé à
la **CONVERSION exacte**, jamais au `endgame_mse`.

## ⛔ Principe (prior fort, pas dogme)
**Aucun pivot non-linéaire (FM/MLP) tant que la parité features/données/recherche avec
Scan n'est pas fermée.** (cf ARBRE_DECISION)

## Defaults actuels (build) — vérifier via le manifeste d'artefact
| flag | valeur | source |
|---|---|---|
| `JASS_ENDGAME_FEATURES` | **ON** (NUM_EXTRAS=110) | baké 0311 |
| `JASS_KING_MOBILITY` | OFF | 0311 +33 Elo, attente mesure propre |
| `JASS_KING_PATTERNS` | OFF | 0240 +37 distill, off en prod |
| `JASS_PHASE_LO/HI` | vide = **0/40** (legacy) | 0312 (sharp testé, gardé 0/40) |
| search `eg_pieces` / `eg_no_nmp` | **40 / true** (NMP off partout) | `src/search_params.hpp` |

## 🔒 Comparaison vs Scan — RÈGLE PERMANENTE (2026-06-18)
**Jamais à temps fixe ÉGAL** (confond éval et vitesse : jass NPS ≪ Scan → broyé quelle
que soit l'éval). Standard = **profondeur fixe** (`--depth`/`--jass-depth`/`--scan-depth`)
OU **movetime compensé-NPS** (jass 2× plus lent → `--jass-movetime 1 --scan-movetime 0.5`).
Temps égal = uniquement pour *mesurer* le handicap de vitesse. `calibrate_vs_scan.py` :
`--jass-movetime`/`--scan-movetime` + garde-fou. Détail : SCAN_METHODOLOGY_GAP.md.

## 🔒 Pool de données — RÈGLE PERMANENTE (2026-06-18)
**Mixer** Scan-self-play (qualité, mais quiet → *nuit* seul au linéaire, 0327) + jass-self-play
(diversité) + coverage. `tools/jnnw_mix.py` (parts contrôlées). Diversité Scan forcée :
`scan_selfplay_gen.py --weak-depth` (fort vs affaibli = parties décisives) / `--depth-jitter`.

## Verdict 0332 (2026-06-18) — la RECHERCHE NE SCALE PAS (le multiplicateur)
NPS jass vs Scan à profondeur égale : **d9 = 1,1×** (même vitesse !), **d12 = 4,2×**, **d15 = 18,4×**.
Facteur de branchement effectif : **jass ≈ 2,0/ply, Scan ≈ 1,28/ply** → l'arbre de jass explose, celui de
Scan reste plat. C'est du **move-ordering / réductions** faibles, PAS de la vitesse d'éval (égale à d9).
**Conséquence** : jass ne peut PAS obtenir les +2-4 plies que 0330 réclame (à temps égal il voit ~d11-12
quand Scan voit d15). La recherche est le **levier dominant** — c'est le multiplicateur qui empêche de
compenser l'éval. ⚠️ **PAS via NMP** : NMP est OFF *à dessein* (sweep 0256/0259 = **+97 Elo** à désactiver,
zugzwang draughts). Le gain doit venir d'un **meilleur ordonnancement / réductions saines** (comme Scan, qui
tient 1,28/ply SANS NMP). Note : une éval plus nette améliore aussi l'ordering → éval (0331) et recherche liées.

## Verdict 0330 (2026-06-18) — le mur = ÉVAL faible MAIS gap PETIT (~2 plies)
Isolation éval/recherche, même éval distillée Scan, jugée par profondeur : **C2 depth-égale d9 = 0.056**
(jass perd même à depth égale → l'éval est vraiment plus faible/ply, PAS qu'un problème de vitesse) ;
**C3 jass d11 vs Scan d9 (+2 plies) = 0.333** (×6 le score) ; C1 temps-égal mt1.5 = 0.111. → l'éval de
jass est **~2-4 plies derrière** celle de Scan (gap petit, closeable), et jass **compense déjà par la
profondeur**. **Deux leviers additifs** : (a) rapprocher l'éval (pool mixte + méthodo), (b) gagner du NPS
(atteindre +2-4 plies à temps égal). Suite : **0331** (levier éval, jugé depth-égale) + **0332** (mesure NPS).

## Verdict 0327/0329 (2026-06-18) — covariate-shift PUR : NON
A/B contrôlé (même archi, même relabel Scan, juge mt1.5) : NEW (Scan self-play) **pire** que OLD
(0314) — vs Scan −545 vs −387, Elo_hc +182 vs +318 ; champion 500k self-play = −545 aussi. La
« bonne » distribution *seule* n'a pas fait décoller (au contraire). MAIS : toutes les défaites =
« no legal move » (jass broyé) → forte présomption que le mur à temps égal est la **RECHERCHE**, pas
l'éval. `0330` (éval vs recherche, depth-fixe) tranche. → d'où les 2 règles permanentes ci-dessus.

## Métriques — SCREEN vs DECISION (un proxy priorise, ne décide JAMAIS seul)
- **DECISION_GATE** : Elo réel/SPRT vs adversaire fort · autopsie **endgame-rois vs Scan**
  (sur parties) · conversion `--egdb-conversion-test` (playout) / `--egdb-mtc-regret` (≤7p exact).
- **SCREEN_ONLY** : `endgame_mse`, `val_mse`, fit-check, MTC-regret 1-ply, quick autopsy.
- ⚠️ **Leçon 0311/0312** : `endgame_mse` est **ANTI-corrélé à la force**. Jamais décider dessus.
- Pour chaque candidat sérieux, produire les **slices** (phase, phase×rois, quiet/tactique,
  ≤7p/>7p, WDL, contradictions, autopsie Scan) — un Elo global masque le signal finale-rois.

## Branches MORTES (NE PAS relancer — + condition de revival)
| Levier mort | Preuve | Reviendrait légitime si… |
|---|---|---|
| Saturer le linéaire par cycles | 0297 plafonne/régresse | — |
| Gradient MTC comme **CIBLE** d'entraînement | 0306 (99,9 % proxy, ne transfère pas) | densité ≥10-MTC massivement enrichie |
| `--phase-weight` (densif par poids) | −210 Elo (0261) | repro only |
| label-depth / **play-depth-finale SEUL** (boucle WDL) | 0254/0265 (−80/−30) | — |
| Géométrie de patterns (enrichir) | 0203-0236 (flat) | — |
| **FM/MLP** | prématuré (principe) | parité features/données/recherche fermée |

> ⚠️ **NE PAS confondre** : le **depth-RAMP** `--play-depth-by-phase late-mid=12,endgame=16`
> en **régime egdb-exact** est **VIVANT** (revival 0293 **+74 Elo**, utilisé 0297/0313/0314).
> Seul « play-depth-finale SEUL » (pré-egdb) est mort.

## Garde-fou artefacts
Tout `.pjtw`/`.jnnw` produit → **manifeste** (`jobs/lib/manifest.sh : manifest_write` :
commit, host, flags, NUM_EXTRAS, dataset hash). **Avant tout A/B** de deux `.pjtw` :
`manifest_assert_comparable` (ABORT si flags/NUM_EXTRAS/dataset diffèrent — évite le
footgun « deux 110-extras de layouts différents »). Pré-flight compute : `jobs/lib/preflight.sh`.

## Jobs en cours
- **cpx62** : **0331** (pool MIXTE Scan-divers+jass, jugé depth-égale — levier ÉVAL).
- **ccx33** : **0332** (mesure NPS jass vs Scan — levier RECHERCHE).
- **PC perso** : éteint ; egdb WLD+MTC ✅, self-play ✅
- *0326/0327/0329/0330 finis. Baseline depth-juge : C2=0.056, C3(jass+2)=0.333.*

## Prochain verdict attendu
**0327** : `new (Scan self-play) vs_Scan ≫ old (0314)` → **covariate-shift confirmé**, le verrou
historique → bascule sur pipeline de génération Scan-self-play (corpus 0328) + co-évolution.
