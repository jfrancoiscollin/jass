> ⚠️ **ARCHIVE — NE PAS PRENDRE COMME CONSIGNE ACTIVE.** Doc historique (ère pré-fit-volume / NNUE).
> Source de vérité unique = [CURRENT.md](../L3_CURRENT.md) (+ docs système : BOUCLE_VIRTUEUSE, SCAN_METHODOLOGY_GAP,
> DIAGNOSTIC_VS_SCAN, BIAIS_FIT_VOLUME, PROGRESSION_LITTERATURE). Conservé pour l'historique seulement. _(Classé archive 2026-06-24.)_

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

### Petite tête non-linéaire (mini-MLP) — ADDITIF, gated (acté 2026-06-07)

Levier de **capacité** (au-delà du linéaire) : un mini-MLP sur les activations
de patterns. **Pas rejeté**, mais **additif** : on l'investigue *seulement
après* avoir bien ajusté le standalone linéaire — jamais à sa place.

⚠️ **Gate « fausse bonne idée » — à vérifier AVANT d'investir.** Le danger : un
MLP ralentit l'éval → moins de profondeur en time-search → on optimise un
*depth fixe* puis on se fait éclater en **conditions réelles vs Scan** (où
c'est la cadence qui compte). Protocole obligatoire :

1. **Profiler** la part de l'éval dans le coût d'un nœud (`JASS_TIME_BREAKDOWN`
   existe). Éval minoritaire (movegen/make/TT dominent) → marge pour la
   ralentir sans tuer le NPS. Éval dominante → un MLP coûte directement de la
   profondeur = danger.
2. **Chiffrer** le coût du MLP (MACs → ns → impact NPS), en réutilisant le
   chemin **SIMD int8 (AVX2)** déjà en place pour le garder *cheap*.
3. **Gate décisif** : bench MLP-éval vs patterns-only **au même MOVETIME**
   (jamais depth fixe). `--depth-at-movetime` montre explicitement la
   profondeur perdue. **Ship le MLP UNIQUEMENT s'il gagne en time-search.**
4. S'il gagne à depth fixe mais **perd en movetime** → fausse bonne idée,
   **rejet**.

> C'est précisément à ça que servent `--depth-at-movetime` et la discipline
> « benchs décisifs en movetime » : attraper ce piège dès le départ.

### Leviers de capacité entre le linéaire et le NNUE (acté 2026-06-07)

Notre éval n'est pas « linéaire » partout : chaque **pattern** est une table
3¹² (non-paramétrique, max expressif **localement**). La linéarité est (1) sur
les **features denses** (mobilité, balance, king-PST), (2) dans la combinaison
**additive**. Déficit réel : **(a)** non-linéarité par-feature sur les denses,
**(b)** **interactions croisées** (le gros morceau — cf 0146, résidu
« dynamique »). Entre-deux candidats, classés capacité/coût-vitesse :

| Levier | Ce qu'il ajoute | Coût inférence | Verdict |
|---|---|---|---|
| **Régression pénalisée** (L1/elastic-net) | rien (reste linéaire) ; élague les buckets-bruit sparses | nul | *généralisation*, pas capacité |
| **Game-stage spline fine** (4-8 bancs) | extension de MG/EG, non-lin. en stade | ~nul (cuit en poids) | gratuit, à prendre |
| **Denses binnées** (one-hot de bins) = GAM | non-lin. **par-feature** | ~nul (cuit en table) | gratuit, additif (pas d'interactions) |
| **Factorization Machine** `Σ⟨v_i,v_j⟩x_i x_j` | **interactions par-paires** (rang-k) | faible, quantifiable | **dépasser Scan**, post-saturation linéaire |
| **Mini-MLP** | non-lin. générale | élevé | dépasser Scan, gated vitesse |
| ~~GBDT~~ | interactions | mauvais par-nœud (pas SIMD) | écarté (contrainte vitesse) |

**⚠️ SCAN EST DANS NOTRE CLASSE** (confirmé docs/SCAN_ARCHITECTURE_NOTES :
*« régression logistique sur features sparses (patterns), pas un réseau ;
représentation linéaire sur patterns »*). Donc :
- **FM/mini-MLP nous emmènent AU-DELÀ de Scan** — pas « rattraper Scan ».
- **Pour ÉGALER Scan, pas besoin de FM** : il faut faire ce que Scan a fait —
  bons patterns + **beaucoup de cycles de training (WDL/self-play)** + bitbases,
  dans la **même classe linéaire**.
- Or on est aujourd'hui **au niveau du handcrafted** → **très loin** d'avoir
  saturé la classe linéaire. **Notre goulot actuel n'est PAS la capacité du
  modèle, c'est le training/les patterns/les cycles** dans la classe linéaire.

→ **FM est donc PRÉMATURÉ.** Forme prévue (pour plus tard) :
`eval = linéaire(patterns) + linéaire(extras) + FM(extras + scalaires-résumé
patterns)`. Splines/binning = polish quasi-gratuit (additif, comme Scan).

**Ordre (reclassé 2026-06-07)** :
1. **Saturer la classe linéaire** = la stratégie Scan : cycles d'apprentissage
   (0149+), patterns plus riches, training plus volumineux, bitbases → viser
   le niveau Scan **dans sa classe**. (+ spline/binning, offerts.)
2. **Seulement après saturation**, pour **dépasser** Scan vers le territoire
   NNUE : **FM** (interactions, cheap) → mini-MLP si FM plafonne.
Chacun **derrière le gate movetime**.

> L'évidence du domaine : ce qui a **battu Scan** = les moteurs **NNUE**
> (non-linéaires). FM est un pas modeste sur ce chemin « dépasser Scan » — pas
> « égaler Scan ». Le résidu non-fitté (0146) est dynamique/interactions →
> FM (ou la profondeur de recherche) peut le grignoter, pas les splines.

### Programme de saturation de la classe linéaire (acté 2026-06-07)

Barre : **atteindre le niveau Scan *dans sa classe*** (mesuré au bench équitable
vs Scan bb-off + vs v15). On part du niveau handcrafted (0152 : 0.444 vs hc) →
beaucoup de marge dans la classe avant que la capacité (FM) soit le goulot.

**Levier 1 — pousser la boucle d'apprentissage à convergence** *(étape immédiate
si 0149 progresse)*. 0149 = petit cycle (3 it × 800 parties, depth-8). S'il
monte : **scaler** (plus de volume/cycles), passer la génération en **movetime**
sur la fin (cibles plus profondes), garder l'**ancrage matériel** chaque cycle.
Itérer jusqu'au **plateau** vs-hc/vs-v15.

**Levier 2 — virage cibles self-play WDL (≠ distillation)**. Scan s'est entraîné
sur **self-play + WDL**, pas en copiant un moteur. La distillation Scan était
notre *prior/warm-start* ; la vraie saturation = **nos propres cycles self-play
WDL** (relabel→retrain). Bonus : **élimine le risque GPL3** (on n'apprend plus
des scores de Scan).

**Levier 3 — patterns plus riches** *(levier STRUCTUREL le plus fort)*. Dans une
classe additive, **les features fixent le plafond de fit**. Nos 8 bandes × 12
cases << le set de Scan. → plus de bandes/géométries, fenêtres chevauchantes,
fenêtres un peu plus grandes (⚠️ 3¹²=531k → 3¹³⁺ explose). **Si scaler les
cycles plafonne bas, c'est ICI qu'on agit.**

**Levier king-aware** *(nos patterns sont men-only ; rois via PST seulement)*.
Les rois sont puissants aux dames et leur interaction avec les pions échappe au
modèle. Deux chemins, du moins cher au plus lourd :
- **Extras denses king** *(cheap, 0155)* : mobilité des rois, ratio rois/pions,
  rois actifs/piégés — additif, quasi gratuit, à inclure dans les extras
  structurels.
- **Petites tables 5-state king-patterns** *(plus tard)* : ajouter QUELQUES
  patterns à encodage 5-state (vide/pion-N/roi-N/pion-B/roi-B) **à côté** des 32
  men-only, sur **petites fenêtres** (5⁸=390k ; 5¹²=244M infaisable). Hybride :
  contexte-roi là où il compte sans faire exploser les patterns men. Réf
  d'implémentation base-5 : branche `claude/0121-pattern-jass-variant-C-kings`
  (PR #186 fermée — module séparé non validé, géométrie dépassée par v4, mais
  l'`extract_index` 5-state reste consultable).

**Leviers de support** : elastic-net/L1 (élague les buckets-bruit → généralise) ;
**bitbases 2-6** (finales exactes, complément de Scan — si plafond *en finale*) ;
**re-tune SPSA** du search pour l'éval améliorée.

**Logique de diagnostic** : scaler les cycles → *plafonne ?* → limiteur =
**features** → enrichir patterns → re-cycler. Perte surtout *en finale* →
**bitbases**. Continue de monter → continuer à cycler.

**Jobs esquissés (si 0149 ✅)** :
- **0153** — boucle self-play **WDL** scalée (gros volume, +cycles, movetime sur
  la fin) → convergence + bench vs hc/v15.
- **0154** — **patterns enrichis** (set élargi) + re-train → mesure du nouveau
  plafond.
- puis elastic-net / bitbases / SPSA selon le diagnostic.

Boucle d'ensemble : *cycles WDL à convergence → si plafond < Scan, patterns plus
riches → re-train → re-cycler*, jusqu'au niveau Scan-dans-sa-classe (ou son
plateau). **Alors seulement** : FM (cf ci-dessus) pour dépasser.

### Journal de bord — saturation de la classe linéaire (2026-06-07)

Tout vs handcrafted (hc) au bench rapide ; v15 = NNUE 128-64 (réf forte).

| Jalon | Résultat | Lecture |
|---|---|---|
| **0151** diagnostic | v3 standalone perd 0/N vs hc | matériel mal signé en MG (colinéarité men-count↔patterns) |
| **0152** ancrage matériel | **0.444** vs hc (de 0.000) | fix : épingler homme=±1, roi=±3 → matériel sain, plus de gaffes |
| **0149/0153** fine-tuning | TD-leaf s'effondre (0.056) ; anti-oubli récupère 0.36 mais **< 0.444** | self-play d'une éval faible n'enseigne pas mieux qu'elle ; **méthode ≠ levier** |
| **0154** patterns riches v4 (8→32) | **0.75** vs hc ; vs v15 mt **0.083** (de 0.056) | géométrie (diagonales+horiz) = grand saut, **survit au gate movetime** |
| **0156** ablation | *(en cours)* | quelle orientation porte le gain → élaguer pour la vitesse |

**Insight 0154** : la val_mse a à peine bougé (36.8→36.0) alors que le jeu a
bondi (0.444→0.75) → la MSE moyenne est un proxy faible ; la géométrie corrige
des angles morts tactiques qui comptent *en partie*. **Confirme** que le levier
est les **features** (capacité), pas la méthode d'entraînement.

État : standalone passé de **sous-handcrafted** à **+191 ELO vs hc**, en
survivant au movetime. Toujours loin de v15 (mt 0.083, ~−350 ELO) mais montée
réelle dans la classe linéaire. Prochaines marches : ablation (0156) → élaguer/
enrichir ciblé → extras structurels (0155) → re-cycler.

### Axe QUALITÉ — le vrai goulot vs v15 (acté 2026-06-07, cf 0157)

0157 a renversé une hypothèse : **on n'est PAS speed-bound**. En recherche
réelle, l'éval 32-patterns (~1549 knps) est **plus rapide** que le NNUE v15
(~1280 knps) et cherche **2,5 plies plus profond** (16.8 vs 14.2) — et pourtant
on **perd** vs v15. Donc :

> **Le déficit vs v15 = QUALITÉ d'éval par nœud, pas vitesse/profondeur.** On
> voit plus loin que v15, on évalue moins bien. Le levier est la qualité.

Accumulateur pattern (0158) : construit quand même (« pour de bon »), pour
**relever le plafond de richesse abordable** — l'éval devient cheap, donc on
peut empiler features/patterns sans payer la vitesse. C'est l'**activateur** de
l'axe qualité, pas une fin.

**Leviers qualité, ordonnés** (chacun benché vs hc + vs v15, en movetime) :
1. **Géométrie diag-enrichie** (0159) : 0156 → diagonales = orientation la plus
   contributive. L'accumulateur rend abordable d'**ajouter de la densité
   diagonale** (les deux sens — l'asymétrie D≫A de 0156 est probablement du
   bruit sur 36 parties, board symétrique). Re-distiller, mesurer.
2. **Extras structurels** (0155) : mobilité des rois (séparée), pions
   percée/bloqués, intégrité rangée de fond, tempo + **king-aware dense**
   (ratio rois/pions, rois actifs/piégés). Additif, cheap.
3. **Meilleure distillation / plus de données** : moins d'écrêtage, fit étagé,
   plus de positions (sparsité ×N avec les patterns riches → besoin de data).
4. **Capacité (FM)** : seulement si la classe additive sature (cf supra).

Synergie : accumulateur (vitesse) **débloque** géométrie+extras (richesse) →
qualité. La sparsité (plus de buckets) devient la contrainte, pas la vitesse.

### Inventaire DATA + stratégie (acté 2026-06-07, cf 0159→0163)

**Leçon clé (0161)** : *plus de data ≠ mieux — c'est la QUALITÉ/diversité qui
compte.* Le self-play **handcrafted depth-4** (0160) est de la **mauvaise** data
(étroite, faible) : v5+extras a régressé 0.25 → **0.11**, avec val_mse qui
*baisse* (31) mais nnz qui *tombe* (3.6%→2.1% : il fitte une distribution
étroite hors-jeu). Ne JAMAIS générer de la data avec un éval faible à faible
profondeur.

**Datasets stockés (vérifiés)** — beaucoup plus que le 1.5M utilisé jusqu'ici :

| Dataset | Records | Labels natifs | Statut |
|---|---|---|---|
| `master-1600.jnnw` (0014) | **4.74M** | WDL (résultats réels) | jeux maîtres ; **0162** le relabel Scan-d10 (propre) |
| `gen-2M-depth20.bin` (0106) | **2.0M** | v15 eval (depth 20) | self-play **FORT** ; **0163** le relabel Scan-d10 |
| `v11-distilled-2M.bin` (0084) | **6.74M** | Scan-distill | distrib **suspecte** (range [-30000,+10000] asymétrique) → à VÉRIFIER avant usage |
| augmenté h1-h3 (0059/0062) | **9.48M** | **WDL** (BCE) | « le 10M » ; pour notre distillation par score → **relabel Scan requis** |
| `master-clean-scan-d10` (0141) | ~1.4M | Scan-d10 (propre) | le set actuel (sous-échantillon nettoyé) |

**Bonne data = joueur fort + recherche profonde + diversité.** master (humains
1600+) et v15-depth20 self-play qualifient ; handcrafted-d4 non.

**Plan data, par étapes** :
1. **En cours (0162→0163)** : master-FULL (4.74M) + v15-depth20 (2M), tous
   Scan-d10 → **~6.7M propre**. Re-distille v5 (40 pat + 112 extras). Test :
   la bonne data débloque-t-elle la richesse (> 0.75) ?
2. **Si oui & on veut plus** : ajouter le **9.48M WDL** (relabel Scan-d10, façon
   0160) + le **6.74M v11** (après vérif distribution) → **~15-20M**. Permet des
   géométries bien plus riches (50+ patterns) sans sur-apprendre.
3. **Si non** (≤0.75 même sur bonne data) : le mur n'est pas la data → revenir
   à **v4 (32, sweet spot 0.75)** et chercher ailleurs (cible de distillation,
   conditionnement des extras à grande échelle, FM).

> Rappel attribution : géométrie (0154→0159), extras (0159→0155), data
> (0155→0163) — chaque axe isolé. v4(32,1.4M)=0.75 reste la référence à battre.

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

---

## Route Scan — enrichissement de la géométrie (préparé)

Constat : nos 32 patterns v4 sont des **bandes verticales génériques, non
partagées, sur 1.4M positions** → tables affamées. Scan (même classe linéaire)
est fort grâce au *feature engineering* (placement + partage) + data self-play.
Trois pistes, hiérarchisées, à lancer si le FM (0184) ne convertit pas. Le FM
reste le **capstone** : on le re-mesure SUR la géométrie finale (gain
sous-additif), pas sur la base pauvre actuelle.

### Piste 1 — diagonale dense  *(prêt : 0186, variant v6, 40 patterns)*
Aligner les fenêtres sur les axes de jeu (diagonales) + densifier le pavage →
les interactions tombent *dans* une fenêtre (mécanisme Scan). Remplace les
bandes verticales par toutes les bandes+blocs diagonaux/anti-diagonaux.

### Piste 2 — régions spécialisées  *(prêt : 0187, variant v7, 15 patterns)*
Dépenser les fenêtres où l'info est dense : bandes de promotion (rangées 0-2 /
7-9), longues diagonales centrales, bords (pions faibles), centre. « Moins mais
mieux placé. »

### Piste 3 — partage de poids par TRANSLATION  *(design — à implémenter)*
Le vrai gain data-efficacité (façon CNN/Scan) : **une** forme de pattern
appliquée à plusieurs positions translatées **partageant la table**. La
translation n'étant PAS une symétrie de l'éval (un pion près de la promotion ≠
au centre), partage **partiel** :

    score_pattern(instance i) = SHARED_TABLE[bucket_i] + BIAS[i]

c.-à-d. table de *forme* partagée entre toutes les instances translatées + un
biais scalaire (ou petit) par instance pour la dépendance positionnelle.

Implémentation requise (≠ simple set de patterns) :
  * `pattern.hpp` : `pattern_offsets()` mappe plusieurs patterns sur le MÊME
    offset de table (groupes de partage) + un tableau de biais par instance ;
    `extract_all`/`update_all` inchangés (l'index bucket est le même).
  * `train.py` : la matrice de design tie les colonnes des instances d'un même
    groupe (somme), + colonnes de biais one-hot par instance.
  * `scan_eval` : v3/v4 — `pat_mg[col]` lit la table partagée ; ajouter le biais.
  * Gain : N instances d'une forme → 1 table (÷N params, ×N data/poids) + N biais.

Combo cible (si les briques paient isolément) : **géométrie diagonale dense +
régions + partage par translation + augmentation symétrique (0185)**, puis FM en
capstone. = réinventer la géométrie de Scan, dérivée pour notre layout.

---

## MILESTONE — état du programme & pivot vers la recette Scan (juin 2026)

Après ~50 jobs (0141→0193) + un chantier vitesse, l'espace des leviers
*incrémentaux* est épuisé. Consolidation avant le pivot.

### Le champion (livrable actuel)
`v4` : 32 patterns men-only (12 cases base-3, géométrie enrichie) + 106 extras
(material/king-PST/mobilité/balance), phase-split MG/EG, **distillé sur
Scan-d10** avec `--score-drop 4900` + `l2=1e-4` + material-anchor.
- vs hc ≈ 1.0 ; **vs v15 ≈ 0.47 à depth-fixe, ~0.38-0.42 à movetime**.
- Éval rapide (accumulateur incrémental), simple, AGPL-propre. Compétitive avec
  v15 sans le battre au temps réel.

### Le tournant qui a tout débloqué : `--score-drop`
~2% de scores Scan extrêmes (±9989 "won/lost") dominaient la perte L2
(5000²=25M même après clip). Les retirer : val_mse 38→1.8, play 0.42→0.94 vs hc.
**Toutes les "régressions" antérieures venaient de ce poison** (amplifié par les
modèles à plus de capacité).

### Carte complète des leviers ÉVAL (tout testé proprement post-score-drop)
NEUTRE ou NÉGATIF, sans exception :
- Volume de data (4.7M ≈ 1.4M) ; teacher plus profond (d16 ≈ d10) ;
- Géométrie : v5 blocs diagonaux (neutre), v6 diagonale-dense (**d9=0.556, BAT
  v15 à depth-fixe** — mais DÉGRADE en profondeur → 0.389 d13), v7 régions ;
- Extras structurels (0172 : nuisent) ; FM / interactions (gate +13% held-out
  mais NE CONVERTIT PAS à movetime + coût vitesse) ;
- Cible WDL (s'effondre) ; filtre quiet (nuit) ; augmentation symétrie (nuit) ;
- Self-distillation itérée (dérive/dégrade) ; WDL self-play (toxique) ;
- **Stabilité profondeur** : hashing de buckets (0190) ET freq-reg (0193)
  ÉCROULENT d9 — les buckets "rares" portent la connaissance, pas du garbage.
  L'instabilité en profondeur de v6 n'est PAS de la sous-représentation simple ;
  non corrigeable à bas coût.

**Conclusion éval** : la connaissance pour battre v15 EXISTE (v6 d9=0.556) mais
ne se stabilise/convertit pas au temps réel par des moyens incrémentaux.

### Carte des leviers VITESSE (notre seul avantage structurel vs v15)
Diagnostic 0189 : Scan ≈ ×8 NPS vs v15 et le pulvérise au movetime ; nous ×1.3.
Le ×6 manquant = implémentation. Breakdown (0189) : movegen 33%, eval 13%,
TT 10%, reste ~13%, ordering 5%, accumulator 4%.
- perft (filet de correction, `--perft`) : movegen CORRECT (valeurs FMJD
  exactes) ; ~24M→34M nodes/s après l'étape 2.
- **Gains réels (mémoire/cache)** : génération man-steps en bitboard (+19%),
  prefetch TT (+5.4%) → **cumul +26% (1762→2215 knps)**.
- Neutres : compact Move, cleanup captures, scan répétition (compute micro-opts
  de buckets déjà bon marché ; certains % du breakdown = overhead BD_TIME).
- Match de Scan (×8) = effort moteur soutenu, pas un levier unique.

### Infra self-play (dé-risquée, prête)
`--gen-data-wdl` accepte un `.pjtw` (self-play piloté par le pattern) ;
`--wdl-scale` + ancrage anti-oubli ; la boucle génère→étiquette→réentraîne sans
s'effondrer. Manque : l'itération depuis une base forte avec la bonne cible.

### LE PIVOT — recette Scan complète (option 4)
Le seul chemin restant vers « aussi bon que Scan, indépendant » = ce que Scan a
fait : **self-play depuis zéro + WDL + régression logistique, ITÉRÉ**, sur
géométrie correcte. Pré-approuvé. Chantier majeur multi-cycles. C'est l'endgame.

---

## EXÉCUTION recette Scan (0196 → 0201) + RÉ-ANCRAGE sur Scan (juin 2026)

> Ce qui suit a été **réellement testé** dans cette série de jobs. À lire avant
> toute nouvelle interprétation : plusieurs conclusions « intuitives » ont été
> **réfutées** par la mesure.

### Le piège n°1 : on benchait contre v15, qui est trop faible

Tout le passé (0141→0198) mesure les eval **contre v15** (NNUE 128-64). Or v15
est lui-même **très loin de Scan** : à profondeur ÉGALE (harness corrigé), v15
vs Scan = **0.028 / 0.056 / 0.056** (d7/d9/d11) et **0.019** au movetime 0.5s
(jobs `0197`, `0137`). Donc un score « 0.39 contre v15 » peut valoir **~0 contre
Scan**. **v15 est un sparring-partner commode mais un mauvais mètre-étalon.**

`0199` (ré-ancrage) mesure enfin le **champion vs Scan** à profondeur égale :

| vs Scan (profondeur égale, no bitbases) | d7 | d9 | d11 | mt 0.5s |
|---|---|---|---|---|
| **champion** (pattern, distill Scan-d10) | 0.028 | **0.000** | **0.000** | **0.000** |
| **v15** (NNUE 128-64) | 0.028 | 0.056 | 0.056 | 0.019 |

→ **Le champion n'est PAS meilleur que v15 contre Scan** (les deux ≈ 0 ; l'écart
est dans le bruit de 16 parties). Le `0.39 vs v15` du champion était **flatté**.
Chargement `--pattern` vérifié (hub `return 2` sur échec ; les parties ont joué
52 min → l'eval était bien chargée), donc le `0.000` est **réel**.

### Le piège n°2 : « WDL vs score » — c'est la PROFONDEUR du label qui compte

Triangulation (toutes les mesures **vs v15**, l'ancre faible) :

| données × cible | d9 vs v15 |
|---|---|
| master + WDL 1.4M (`0194`) | 0.22 |
| self-play + WDL 1M (`0196`, best l2=3e-4) | 0.22 |
| self-play + score @movetime-30ms 1M (`0198`) | **0.08–0.17** ← le pire |
| master + score Scan-d10 = **champion** (`0141`) | 0.39 |

- WDL plafonne à **0.22 quelle que soit la source** (master = self-play) → c'est
  le **label** qui plafonne, pas la classe linéaire (qui atteint 0.39 via score),
  ni les données. La meilleure qualité de jeu du self-play (**59.2 % de nulles**
  vs 18.6 % master) **n'aide pas** pour la cible WDL.
- Le score self-play **tel quel** (recherche 30 ms, bruité : range ±30000,
  std ~5000) est un **plus mauvais prof que le résultat de partie** (0.08 < 0.22).
- Le 0.39 du champion vient de labels **profonds** (Scan-d10). → **Levier eval =
  la PROFONDEUR/qualité du prof, pas « score vs WDL » en soi.**

### Le piège n°3 : « la recherche est un levier » — FAUX, elle est déjà complète

Tentation : champion ≈ v15 ≈ 0 vs Scan à profondeur égale ⇒ « c'est la recherche
de jass qui est faible ». **Réfuté par le code.** La recherche de jass possède
**déjà** tout l'arsenal moderne (cf. [ARCHITECTURE.md](ARCHITECTURE.md) §*A
move's life inside the search*) : TT, iterative deepening, **aspiration, PVS,
LMR, LMP, null-move, IID, extensions singulières/promotion, multi-cut**, killers,
history, countermoves, **quiescence** (résout les prises forcées). **Il n'y a
aucune technique de recherche manquante à ajouter.**

> ⚠️ **Leçon de méthode** : ne JAMAIS déduire « telle technique manque » d'un
> `grep` par mots-clés sur `search.cpp` (les noms varient : `null_pos` pas
> `null_move`, réduction via variable `r` pas « LMR »…). **Consulter
> ARCHITECTURE.md**, qui fait foi sur ce qui est codé.

Raisonnement correct : à profondeur **nominale égale**, avec alpha-beta sain +
quiescence, la qualité du coup est gouvernée par l'**eval des feuilles** (LMR,
ordering, null-move ne changent que la *vitesse*). Deux eval ≈ 0 vs Scan = **les
deux sont loin sous l'eval de Scan** (effet plancher). → **Le gap à Scan est
l'EVAL, pas la recherche.** Reste à chiffrer la part eval vs efficacité de
profondeur : job `0201` (handicap de profondeur — voir ci-dessous).

### Vitesse (rappel, inchangé)
`0189` : Scan ≈ **×8 NPS** vs v15, le pulvérise au movetime ; le ×6 manquant =
implémentation (movegen 33 %, eval 13 %, TT 10 %…). Mais comme on perd **déjà à
profondeur égale**, fermer l'eval passe avant la vitesse.

### Outillage ajouté pendant cette série
- **`jass --rewrite-scores-with-search <in.jnnw> <out.jnnw> --nnue <eval>
  [--depth D] [--start S] [--count C]`** — relabel d'un JNNW par **recherche
  profonde** (eval pattern `.pjtw` ou NNUE `.bin`), score STM-POV, shardable.
  C'est la brique du **bootstrap teacher-free** (`eval ← recherche(eval)`), sans
  Scan. Vérifié par smoke round-trip ; `jass_tests` passent.
- **`tools/calibrate_vs_scan.py --jass-depth N --scan-depth M`** — profondeur
  **asymétrique** (rétro-compatible) pour le diagnostic eval-vs-recherche.

### État des jobs de la série
| job | objet | verdict |
|---|---|---|
| `0196` | self-play 1M WDL @mt30 + logistic | WDL plafonne 0.22 (= master) ; volume aidait (160k→1M) |
| `0197` | v15 vs Scan profondeur égale | 0.028/0.056/0.056 — instrument corrigé (plus de coups illégaux) |
| `0198` | même data, cible score @30ms | 0.08–0.17 < WDL → le score superficiel est un mauvais prof |
| `0199` | **ré-ancrage** champion vs Scan | **champion ≈ v15 ≈ 0** — le 0.39 vs v15 était flatté |
| `0200` | relabel 1M @ **d12** teacher-free + train | **levier deep CONFIRMÉ** : 0.306 vs v15 (l2=3e-4) ≫ shallow 0.08 & WDL 0.22 — mais < champion 0.39, et **0.000 vs Scan**. l2=1e-4 s'effondre (0) → régularisation sensible. champion d12 = **0.026 s/pos** (~0.9h/1M, relabel cheap → itérable) |
| `0201` | handicap de profondeur jass vs Scan-d9 | *préparé* — combien de plies pour égaler Scan ? (eval vs efficacité) |

### Où on en est (synthèse honnête)
1. **Distance réelle à Scan = grande** (≈ 0 à profondeur égale). L'ancre v15
   nous flattait. **Bencher désormais contre Scan** (profondeur égale, harness
   corrigé), pas contre v15.
2. **Le levier est l'EVAL** (la recherche est complète, la vitesse est seconde).
3. **Cible eval = labels profonds** (pas WDL, pas score superficiel) — **confirmé
   par `0200`** : relabel d12 = 0.306 vs v15, ≫ shallow (0.08) et WDL (0.22).
4. Mais **un cycle ≈ le prof, pas au-delà** (`0200` : 0.306 < champion 0.39, et
   0.000 vs Scan). Dépasser exige d'**enchaîner les cycles** (regénérer avec
   l'eval améliorée → re-relabel deep → retrain) ; relabel cheap (~1h) → faisable
   mais long. Le gap Scan ne se ferme pas en un coup.
