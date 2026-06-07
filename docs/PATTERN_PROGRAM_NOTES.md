# Programme « pattern compétitif » — notes & items de suivi

> Rédigé 2026-06-06. Consolide la réévaluation de l'approche pattern et les
> points à surveiller. But : ne pas refaire / ne pas oublier.

## Contexte

Le verdict historique « le pattern est faible » reposait sur **4 confondants
empilés**, tous corrigés dans cette série :

| # | Confondant | Corrigé par |
|---|---|---|
| 1 | Labels de distillation sales (~18 % de faux labels, captures forcées) | relabel fixé (#203) → 0141 |
| 2 | Jugé en **profondeur fixe** (la vitesse ~100× du pattern est invisible) | bench **movetime** (0141/0142) |
| 3 | Recherche réglée pour le **NNUE** (marges cp ≠ distribution pattern) | SPSA **pour le pattern** (#206/#209) → 0141 |
| 4 | Training **non search-aware** (scores statiques) | **TD-leaf(λ)** (#207) → 0142 |

Chaîne de jobs : **0141** (pattern propre + SPSA complet) → **0142** (TD-leaf
jusqu'à convergence) → **0143** (vs Scan, *en pause*, déclenché délibérément
après convergence).

## Couplage search↔éval : état

- ✅ **Toutes les marges cp** de la recherche (RFP, razoring, singular,
  probcut, NMP, LMP, LMR, fenêtre d'aspiration) sont dans le set SPSA →
  tunées **pour le pattern** par 0141 (#209). razoring/probcut/ext inclus :
  le pattern décide lui-même s'ils l'aident (pas le verdict NNUE de 0138).
- ✅ **Quiescence** : purement structurelle (captures forcées), **aucune**
  marge éval → rien à adapter.

## Items de suivi (watch-list)

### 1. Time-management à HAUTE profondeur  *(à surveiller — déclencheur ci-dessous)*

Le pattern (~100× plus rapide) atteint des profondeurs bien supérieures au
NNUE en movetime (depth 25-35+). Or deux heuristiques ont été pensées pour
le régime de profondeur du NNUE, **pas** pour ce régime :
- le **saut d'itération** (« projette la prochaine itération à ~2× le coût »),
- le **doublement d'aspiration** sur fail-high/low.

Ce ne sont **pas** des marges en cp (le SPSA ne les couvre pas) — c'est un
régime de profondeur.

**Déclencheur** : si, pour le pattern, `rate(vs v15 @ movetime) <
rate(vs v15 @ depth fixe)`. Un pattern rapide devrait faire **mieux** en
movetime (il creuse plus) ; s'il fait **pire**, sa recherche profonde ne
paie pas → suspecter (a) le time-mgmt/aspiration inadaptés à la haute
profondeur, ou (b) une instabilité de l'éval en profondeur.

**Action si déclenché** : tuner saut-d'itération + aspiration pour le régime
haute profondeur (ou diagnostiquer la stabilité de l'éval). 0141 et 0142
émettent un avertissement automatique si la condition est vue.

### 2. Échelle/distribution des scores du pattern  *(risque faible, géré)*

Calibrée par le training (le pattern apprend des cibles en cp) + le SPSA
absorbe le résiduel dans les marges. À monitorer, pas d'action a priori.

### 3. Accumulateur NNUE incrémental  *(non applicable)*

Le pattern n'emprunte pas le fast-path `MLPNetworkQ` (chemin éval générique).
Pas un problème de calibration ; aucune action (le pattern est déjà rapide).

## Briques que Scan a et nous non (prochaines marches — CONDITIONNELLES)

Audit architectural 2026-06-06. **Ne rien construire avant** d'avoir le
verdict 0141/0142 : ces briques ne valent le coût que si le pattern de base
(labels propres + TD-leaf + search tuné) se révèle compétitif. Sinon on
optimiserait dans le vide.

### A. Phase-split éval MG/EG  *(spécifique pattern — brique éval #1)*

Scan stocke **2 poids par feature** (midgame + endgame) interpolés par stade,
**patterns inclus** :
```
eval_scan = material + king_PST + mobility + balance + pattern_sum
          + game_phase_interpolation(mg, eg)
```
**Notre pattern_jass (8×12) est mono-phase** (un poids/bucket ; squelette
handcrafted mono-phase aussi) → un même pattern moyenne MG et EG.
**Closeable** : doubler la table (mg/eg) + interpolation par stage.
**Déclencheur** : si 0141/0142 montrent un pattern *proche mais pas tout à
fait* compétitif → c'est la 1re brique éval à ajouter.
*(NB : `src/pattern_network.hpp` v5/v6 a déjà l'infra phase-split pour le
squelette scalaire — patterns encore mono-phase ; à porter sur pattern_jass.)*

### B. Bitbases endgame 2-6 pièces  *(général — données DISPONIBLES en ligne)*

- Nous : **KvK + KKvK** seulement (rois, 2-3 pièces).
- Scan : **2-6 pièces** (WLD only, ~2 GiB RAM à bb-size=6 ; 7 pour BT).

Pénalise les finales (fréquentes en draughts) quel que soit l'éval (pattern
ou NNUE). **Mise à jour 2026-06-06 : la donnée est TÉLÉCHARGEABLE** (juste
pas bundlée dans le repo GitHub vu la taille). Readme de Scan : *« bitbases
require a separate copy or download »*.

**Source** (site officiel Scan : hjetten.home.xs4all.nl/scan/scan.html, lié
depuis rhalbersma/scan) — variante standard = international (matche) :
- `bb.zip` **706 MiB** (tables 2-6, → `data/bb/{2,3,4,5,6}`)
- ou séparément : **5 pièces 26 MiB**, **6 pièces 720 MiB**.
- Format WLD (win/loss/draw, pas de distance-au-mat) ; lisible dans le source
  GPL3 de Scan.

→ Brique re-classée « la plus dure » → **MODÉRÉE**, deux chemins :
- **A. Intégrer la base externe** : reader du format Scan + câblage probe.
  Rapide pour « avoir » la donnée. ⚠️ ~2 Go RAM/stockage + **licence à
  vérifier** (moteur GPL3 ; usage des fichiers data).
- **B. Générer les nôtres** : étendre la rétro-analyse KvK/KKvK
  (`bitbase.cpp`) jusqu'à 5-6 pièces. Notre format, zéro licence, mais gros
  job compute/mémoire.

**Déclencheur** : si on plafonne spécifiquement en **finale**. La barrière
est bien plus basse qu'estimé initialement.

#### Équité du bench vs Scan (IMPORTANT — acté 2026-06-07)

Tant qu'on n'a pas nos bitbases, bencher contre **Scan-avec-bitbases** est
inéquitable : ça mélange l'écart éval+search et l'avantage *données de
finale*. Protocole à **deux passes**, contrôlé par `--scan-bb-size` :

| Passe | `--scan-bb-size` | Mesure |
|---|---|---|
| **Équitable** (défaut, 0143) | `0` | parité **éval+search** pure — *le* test honnête |
| **Handicap** (plus tard) | `6` | ce que les bitbases nous coûtent → vaut-il le coup |

`calibrate_vs_scan.py` envoie désormais `set-param bb-size` **explicitement**
(même à 0) → on ne dépend plus du défaut du `scan.ini` ni de la présence des
fichiers ; le bench **logue** le réglage (auditable). NB : les fichiers
bitbases (~706 Mo) **ne sont PAS** dans le repo `rhalbersma/scan` (un ancien
commentaire du code le prétendait à tort) — donc la passe handicap n'a d'effet
qu'une fois ces fichiers téléchargés. Notre côté n'a qu'un KvK/KKvK trivial
(négligeable), donc la passe équitable est bien « éval+search contre
éval+search ».

### C. Raffinements search incrémentaux  *(général — IMPLÉMENTÉS 2026-06-07)*

Les 4 briques manquantes vs un top engine sont **codées** dans
`src/search.cpp`, **gated + neutres par défaut** (l'invariant
`SearchParams{}` = comportement inchangé est préservé, vérifié par
`test_1b_defaults_are_behaviour_neutral`) :
- **continuation history (CMH)** — 2e table d'histoire keyée
  `[opp_prev_to][from][to]`, ajoutée à l'ordering des coups quiets
  (`use_conthist`). ~+15-30 ELO typique.
- **improving heuristic** — eval statique vs 2 plies plus haut ; quand on
  n'« improve » pas, LMP fire plus tôt + LMR réduit 1 ply de plus
  (`use_improving`).
- **IID** — recherche réduite pour obtenir un coup d'ordering quand pas de
  TT-move (`iid_min_depth`, `iid_reduction`).
- **multi-cut** — scout les premiers coups à profondeur réduite ; si assez
  fail-high → cut (`multicut_min_depth`, `multicut_reduction/moves/cuts`).

Toutes ajoutées au set SPSA (toggles ON/OFF + seuil profondeur). Job **0148**
les A/B isolément (vs défaut, sur v15 + v3, depth + movetime) pour décider
lesquelles flipper en défaut. Sous-knobs ajustables par spec.

### Ce qu'on a déjà au niveau de Scan (pas un écart)

- Patterns **men-only** + kings via PST dédié (même découpage que Scan).
- Géométrie **8 colonnes × 12 cases** (≈ Scan, base-3).
- Search : alpha-bêta complet + PVS + pruning tuné + Lazy SMP.

## Éval Scan-style complète — IMPLÉMENTÉE (PJTW v3, 2026-06-07)

Brique demandée explicitement : *« tout comme Scan, King pst mobilité split
phase. Tout codé nickel en C++ peu importe les résultats des evals. »* —
construite indépendamment du verdict fit-check (0144/0145/0146 : le résidu
Scan−handcrafted est ~93 % non-fittable par des features statiques, mais
l'archi est montée quand même, proprement et testée).

**`src/scan_eval.{hpp,cpp}`** — éval linéaire structurée, standalone,
**tout phase-split MG/EG** (interpolé par `game_stage = min(pièces,40)/40`,
exactement comme Scan §3) :
```
eval_black = wmg·(patterns_mg + extras_mg) + weg·(patterns_eg + extras_eg)
```
- **patterns** : 8 bandes × 12 cases ternaires (pattern_jass, men only),
- **extras (106, dense)** = material (men counts) + **king PST** (one-hot
  50×2) + **mobilité** (men step + king slide, **bitboard rapide, sans
  movegen**) + **balance** (L/R men), tout en black-POV.

**Contrat de consistance (clé)** : `compute_extras()` est la **source
unique** du vecteur extras — appelée à la fois par le dump d'entraînement
(`jass --dump-eval-features`) et par `ScanEvalNetwork::evaluate()`. Le
trainer Python (`pattern_jass/tools/train.py --scan-eval`) consomme le dump
**verbatim** (valeurs RAW, pas de standardisation), donc l'éval jouable et
les features d'entraînement sont **identiques par construction**. La mobilité
utilise des shifts bitboard (rapide) → même fonction des deux côtés, donc
exacte sans devoir matcher `generate_legal_moves`.

**Format PJTW v3** : `magic, version=3, scale, n_pat, n_ext`, puis int32
`[pat_mg | pat_eg | ext_mg | ext_eg]`. Loader + dispatch (`load_eval_network`
peeke la version → v3 = ScanEvalNetwork, v1/v2 = PatternJassNetwork). Câblé
dans `--pattern` (HUB), `--benchmark-search-params` (SPSA) et le nouveau
`--benchmark-scan-eval`.

**Validation** (faite avant tout gros run) :
- `tests/test_scan_eval.cpp` : extras (start pos symétrique, king one-hot),
  interpolation MG/EG, flip de signe stm, round-trip v3, rejet v1.
- cross-check numérique **Python prédiction == C++ eval** exact sur 10
  positions (midgame + endgame, W & B au trait) — verrouille layout +
  indexation patterns + phase + signe + quantification + format.

Job **0147** : entraîne la v3 complète sur les labels propres 1.4M (0141) +
bench vs v15 (depth + movetime) + SPSA. → étape « ajouter les briques
manquantes (brique A, §A) » de la roadmap ci-dessous, faite.

## Résultat 0147 + apprentissage du mode standalone (acté 2026-06-07)

**Fait dur** : le prior v3 **standalone** (distillation Scan, une passe) perd
**0/90 vs v15** (depth 8, movetime, tuné). Fit ~29 % de variance ; un v3 jouet
perd aussi vs handcrafted → hypothèse : **standalone PIRE que le baseline**,
probable **sous-évaluation du matériel** (homme/roi mal appris depuis des
scores Scan écrêtés ±5000cp). Diagnostic en cours : **0151** (triangle v3/hc/
v15 + sonde des poids matériel). 0149/0150 en pause le temps de trancher.

**Décision de cadrage** : un éval **standalone** ne peut pas être bon après
*une seule* régression naïve — il lui faut un **programme d'apprentissage**,
quitte à itérer plusieurs cycles avant d'avoir une bonne base, *puis* une
distillation **mieux adaptée**. Deux branches selon 0151 :

- **Si `v3 < hc` par sous-éval matériel (réparable en training)** → garder le
  standalone mais lui donner sa boucle d'apprentissage :
  1. **distillation « plus adaptée »** : moins d'écrêtage (le clip ±5000cp
     compresse le matériel), **ancrage/prior matériel** (homme≈100cp,
     roi≈300cp) ou **fit étagé** (matériel d'abord, gelé, puis positionnel) ;
     éventuellement blend WDL+score.
  2. **bootstrap self-play (TD-leaf)** itéré : le self-play enseigne « perdre
     une pièce perd la partie » → la notion de matériel/positionnel émerge des
     résultats, sur plusieurs cycles.
  3. **re-distiller** une fois la base décente (cible mieux adaptée).
  Itérer 1↔2↔3 jusqu'à une base standalone compétente.
- **Si l'écart est plus profond (résiduel non-représentable)** → repli
  **HYBRIDE** (`eval = squelette handcrafted + correction structurée`), comme
  l'approche pattern d'origine : base matériel solide + correction apprise.

> NB : c'est l'analogue des « 15 ans » de Scan — son éval standalone est le
> fruit d'itérations, pas d'une régression unique. Notre standalone aura sa
> propre (mais bien plus courte) boucle.

## Roadmap post-validation (plan acté 2026-06-06)

Séquence **conditionnelle** : ne démarrer que **si 0141/0142/0143 confirment
un pattern prometteur** (compétitif ou proche vs v15, pas effondré vs Scan).
Si le pattern de base s'effondre malgré les 4 confondants corrigés → on
re-décide, ces étapes ne le sauveraient pas.

### Étape 1 — Ajouter les briques manquantes (HORS bitbases)

1a. **Phase-split MG/EG sur pattern_jass** (brique éval #1, cf §A).
    Doubler la table (poids mg + eg par bucket) + interpolation par
    `game_stage`. Porter l'infra déjà présente dans `src/pattern_network.hpp`
    (v5/v6 : phase-split du squelette ; étendre aux patterns eux-mêmes).
    Re-train sur les labels propres.
1b. **Raffinements search** (cf §C) : continuation history (CMH), IID,
    improving heuristic, multi-cut. ✅ **FAIT 2026-06-07** — codés gated +
    neutres par défaut, ajoutés au set SPSA, A/B par 0148 pour flipper les
    défauts.

> Bitbases (§B) **exclus** de cette vague (trop lourd) — à reconsidérer
> seulement si on plafonne spécifiquement en finale.

### Étape 2 — Fine-tune + boost en self-play  *(infra prête, job 0149)*

Sur l'archi **enrichie** (v3 phase-split + search 1b), TD-leaf(λ) self-play
**search-aware** par-dessus le prior distillé (0147). Infra réutilisée :
`--gen-tdleaf` (rendu v3-capable + movetime + search-spec) → `td_leaf_targets.py`
(λ-return) → `--dump-eval-features` → `train.py --scan-eval`. La régression
linéaire re-fit sur les cibles bootstrappées = 1 pas de TD-leaf ; itérer.

Décisions actées (2026-06-07) :
- **2 bras comparés** : *pur* (re-fit libre) vs *ancré-Scan* (L2 des poids
  vers le prior, `--anchor-weights/--anchor-l2`, anti-oubli). Le bench vs v15
  tranche.
- **budget mixte** : itérations courtes (depth) pour dégrosser, puis
  profondes (movetime, la v3 est rapide) pour affiner.
- **1b en génération** = briques validées par 0148 (cohérence search/train).

Puis **re-tuner les constantes** (SPSA) pour l'archi finale, re-bench vs v15
puis **vs Scan** (0143). Itérer 1↔2 si gain. Objectif : éval alpha-bêta qui
tient le plus possible face à Scan en time-search.

> Séquencement : 0147 (prior) → 0148 (quelles 1b) → 0149 (TD-leaf pur vs
> ancré) → SPSA archi finale → vs Scan.

## Distillation de Scan : pourquoi ça a échoué, et quand la re-tester

### Hypothèse sur l'échec passé (0131=0.000, 0132)

Deux causes empilées :
1. **~18 % de labels faux** (bug captures forcées) → on fittait du bruit. **Corrigé** (relabel fixé, #203).
2. **Inadéquation de représentation** : le diagnostic « résidu (Scan − squelette) non fittable » s'explique probablement parce que **Scan est phase-split (MG/EG)** et **notre pattern est mono-phase**. Un modèle mono-phase **ne peut pas** représenter une fonction dépendante du stade → le résidu phase-dépendant de Scan est **non-fittable par construction** (limite de classe de fonction, pas du bruit).

### Test décomposé (lecture de 0140/0141)

`0140`/`0141` distillent sur **labels propres** mais **encore mono-phase** :
- remonte nettement vs 0131 (0.000) → **les labels** étaient un gros facteur ;
- reste bas / plafonne malgré labels propres → c'est la **représentation**
  (mono-phase) qui bloque → **phase-split sera décisif** pour la distillation.

→ Lire 0140/0141 sous cet angle : ils disent *pourquoi* la distillation
échouait, donc si phase-split la débloquera.

### Prédiction

Sur l'archi **enrichie** (phase-split + features matchées), la distillation
a de **bien meilleures chances** : Scan EST un moteur à pattern, donc mettre
notre pattern dans **sa classe de fonction** rend « copier l'éval de Scan »
tractable (la cible est *dans* notre classe). C'est *le* bon moment pour la
re-tester — pas avant phase-split.

**Réserves** : nos features ≠ exactement celles de Scan (balance, mobilité,
définition de `game_stage`) → on **approxime**, on ne **réplique** pas
(résidu non nul). Et la distillation ferme le gap **éval**, pas le moteur
complet (bitbases, tuning search).

### Règle de séquencement (IMPORTANT)

La distillation est un **prior** (injecte la connaissance de Scan), le
self-play (TD-leaf) **raffine pour notre recherche**. Donc l'ordre correct :

> **distiller (prior Scan) → fine-tuner en self-play (TD-leaf)**, ou blender
> les deux cibles.

**Ne PAS** distiller *après* le boost self-play (étape 2 de la roadmap) — ça
**écraserait** les gains du self-play. Quand on intègrera la distillation à
la roadmap, elle vient **avant/pendant** le self-play, pas après.
