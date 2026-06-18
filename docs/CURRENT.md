# CURRENT — source de vérité active (programme « battre Scan »)

> **1 page, tenue à jour à CHAQUE verdict.** Le reste des docs = archive/historique.
> But : empêcher qu'un passage périmé relance une **branche morte** (cf le quasi-incident
> `--play-depth-by-phase` de l'audit 2026-06-17 : marqué « mort » dans une vieille ligne,
> en fait VIVANT). Lire avec [ARBRE_DECISION.md](ARBRE_DECISION.md) (principe + arbre) et
> [JOURNAL_DE_BORD.md](JOURNAL_DE_BORD.md) §0 (faits). MAJ : **2026-06-17**.

## Hypothèse active
Fermer le verrou **finale-rois DANS la classe linéaire** (celle de Scan). Le gap n'est
**PAS la capacité** (0309/0310 : *conflit de phase*, pas saturation — le linéaire fitte la
finale à mse 3.03). Leviers, sur **données finale-enrichies** : **(a)** features rois
manquantes (`king_mob`/`endg`), **(b)** phase-split. Jugé à la **CONVERSION exacte**, pas
au `endgame_mse`.

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

## Hypothèse fraîche (2026-06-18) — COVARIATE-SHIFT
La distillation est **plafonnée par la DISTRIBUTION des positions**, pas par le label : si les
positions de base sont **peu instructives** (self-play faible + coverage ≤7p aléatoire = le dataset
0314), Scan a beau labeliser parfaitement, l'éval n'apprend Scan que là où ça ne compte pas — quelle
que soit la depth/mt. **Test (0327)** : A/B chirurgical, seule la SOURCE des positions change —
ARM-OLD = distribution 0314 ; ARM-NEW = positions issues du **jeu propre de Scan** (Scan joue les
deux côtés, on dumpe tout son chemin). Même archi FULL Scan-alignée, même relabel Scan d9, même
train, même taille, même juge vs Scan mt1.5. Outil : `tools/scan_selfplay_gen.py`.

## Jobs en cours
- **cpx62** : **0327** (covariate-shift A/B — distribution Scan-self-play vs 0314)
- **ccx33** : 0326 (alignment A/B distillation — l'alignement Scan aide-t-il ?)
- **PC perso** : éteint ; egdb WLD+MTC ✅, self-play ✅

## Prochain verdict attendu
**0327** (la distribution est-elle le verrou ?) + **0326** (l'alignement Scan aide-t-il ?).
new vs_Scan > old → covariate-shift confirmé → pipeline de génération Scan-self-play.
