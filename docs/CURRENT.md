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
- **cpx62** : **0327** (covariate-shift A/B — distribution Scan-self-play vs 0314) — *le test décisif*.
- **ccx33** : **0328** (corpus Scan-self-play réutilisable, génération seule, committé).
  *0326 (alignment A/B) TUÉ 2026-06-18 : il jugeait sur la distribution suspecte 0314/0313.*
- **PC perso** : éteint ; egdb WLD+MTC ✅, self-play ✅

## Prochain verdict attendu
**0327** : `new (Scan self-play) vs_Scan ≫ old (0314)` → **covariate-shift confirmé**, le verrou
historique → bascule sur pipeline de génération Scan-self-play (corpus 0328) + co-évolution.
