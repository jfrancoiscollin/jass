# Scan methodology gap — ce qui nous sépare, et comment fermer le gap itérativement

> ## 🔒 RÈGLES PERMANENTES (2026-06-19) — la BOUCLE VIRTUELLE (cf [BOUCLE_VIRTUEUSE.md](BOUCLE_VIRTUEUSE.md))
> 1. **On NE se compare PLUS à Scan tant qu'on n'a pas convergé.** Au plancher, vs-Scan est perdant ET bruité
>    (même config = 0.028 ↔ 0.083 d'un run à l'autre). **Métrique = SOI-MÊME en DIRECT** (`benchmark-nnue-vs-nnue`,
>    `gen_k vs gen_{k-1}`, bande ~0.5 = sensible). Scan ne ressort qu'**au plateau** (`vs gen_{k-1} ≈ 0.5`).
> 2. **DÉCISIF ≠ VÉRIDIQUE — jouer PROFOND (≥10).** Le self-play peu profond (d4) est *décisif* (77 %) mais
>    **blunder-driven** → l'eval apprend la value-function d'un faible (0363 grimpe en interne, plat vs Scan ; 0365).
>    Le levier = **force du self-play (profondeur) + volume**, PAS la décisivité. Bootstrapper d4 = branche morte.
> 3. **Le jeu profond est ~gratuit** : 24k pos/min @ d10 (cpx62), ~2× d4 seulement (pruning). Qualité+volume ensemble.
> 4. **`--minibatch` est L2-only** (≠ logistique) ; à d10 le goulot = génération pas RAM → **full-batch `--lowmem`**.
> 5. **Géométrie reset-proof** : `gen_patterns --emit` réverté mid-run par le runner → build de suite + `JASS_PATTERNS_DIR`
>    hors-tree + garde-fou « ×32 » (0359/0362 invalidés sans ça).
> 6. **La gen data WDL est arch-indépendante = actif durable** → pool distribué via git (fenêtre glissante ≤2M).
> 7. **Nos verdicts « géométrie morte » (0230/0234/0239/0359) sont CONFONDUS par `full-fold`** : il impose une
>    invariance par TRANSLATION (fausse en dames) qui écrase chaque famille de translates (verticales→1, etc.).
>    Comparer des géométries = au repli position-préservant **`--color-fold`**, jamais full-fold. Capacité (poids) :
>    32+color-fold = 8,5M (surensemble de Scan) ; 8+color-fold = 2,1M (= Scan) ; 32+full-fold = 1M (squishé).
>    Test propre cross-arch = `tools/jass_vs_jass_arch.py` (2 binaires, NUM_PATTERNS ≠). Cf [BOUCLE_VIRTUEUSE.md §7](BOUCLE_VIRTUEUSE.md).

> ## 🔒 RÈGLE PERMANENTE (2026-06-18) — comment on COMPARE à Scan
> **NE JAMAIS comparer à Scan à TEMPS FIXE ÉGAL.** Un `--movetime` égal confond
> la **qualité d'éval** avec la **vitesse de recherche** : jass a un NPS ≪ Scan,
> donc à temps égal jass voit *moins de plies* et perd quelle que soit l'éval
> (0327/0329 : −387/−545, *toutes* défaites « no legal move », jass broyé). Le
> standard est :
> 1. **PROFONDEUR FIXE** : `--depth D` (les deux), ou asymétrique `--jass-depth`/
>    `--scan-depth` (combien de plies en plus il faut à jass pour égaler Scan = la
>    taille du gap d'éval *en plies*). C'est la mesure d'**éval pure**.
> 2. **MOVETIME COMPENSÉ-NPS** : donner au plus lent un budget proportionnel au gap
>    de NPS — jass 2× plus lent → `--jass-movetime 1.0 --scan-movetime 0.5`. C'est la
>    mesure **fair en conditions de jeu réelles**. (`calibrate_vs_scan.py` expose
>    `--jass-movetime`/`--scan-movetime` + un garde-fou qui avertit sur le temps égal.)
>
> Le temps égal ne sert QU'À une chose : **mesurer le handicap de vitesse** (le diff
> entre temps-égal et depth-égale = ce que la recherche nous coûte). `cpx62-0330`
> isole éval vs recherche par cette méthode.
>
> ## 🔒 RÈGLE PERMANENTE (2026-06-18) — RÉGLER LA RECHERCHE À TEMPS FIXE
> **Ne jamais régler/juger la recherche à PROFONDEUR FIXE.** Un benchmark à depth fixe sous-évalue
> *structurellement* tout pruning qui **achète de la profondeur** (probcut/razor/multicut/iid/LMR) : à
> depth fixe la profondeur est gratuite → on ne voit que le *risque* du pruning, jamais son *bénéfice*.
> C'est pour ça que ces techniques étaient désactivées à tort (0333 : combo = 0.639 à temps fixe, ≈ +100
> Elo). **Régler/juger à TEMPS FIXE** : self-play A/B `jass --benchmark-search-params <eval> "<A>" "<B>"
> <depthcap> <pairs> <threads> <movetime_ms>` ; `A-rate > 0.5` = le réglage achète de la profondeur nette.
> (NMP reste l'exception OFF : −97 Elo, zugzwang — cf 0256/0259.)
>
> ## 🔒 RÈGLE PERMANENTE (2026-06-18) — le POOL de données
> Ni 100 % Scan-self-play (fort mais **quiet/peu de contraste** → *nuit* au fit
> linéaire, 0327), ni 100 % jass-self-play (divers mais **faible**, covariate-shift).
> **MIXER** : un pool avec un **% garanti de qualité forte** (Scan-self-play) ET de la
> **diversité** (jass-self-play + coverage). Outil : `tools/jnnw_mix.py` (parts
> contrôlées). Diversité du Scan-self-play forcée par `tools/scan_selfplay_gen.py
> --weak-depth` (Scan fort vs Scan affaibli → parties décisives) et `--depth-jitter`.

> Rédigé le 2026-05-26 après les 4 tentatives D0-D2 sur l'archi pattern
> (jobs 0046/0047/0048/0049, tous flat à 0/54 vs v5 d10). Synthèse
> honnête de POURQUOI notre supervised cheap ne reproduit pas Scan, et
> proposition d'un plan itératif pour fermer le gap progressivement.
>
> **Révisé 2026-05-28** suite à la note de relecture du code Scan +
> méthodo Letouzey/Gilbert (cf. `docs/SCAN_ARCHITECTURE_NOTES.md`
> révision 2026-05-28). Ajoute une étape **G2-WDL** entre G2 et G3 :
> notre G2 distille un score depuis v7, alors que Scan utilise
> exclusivement des labels WDL avec régression logistique. La variante
> WDL pure aligne exactement la méthodo Scan, sans coût C++ (juste
> `--lambda 0.0` dans le trainer).
>
> À lire avec `docs/SCAN_ARCHITECTURE_NOTES.md` (analyse statique du
> code Scan + méthodo training) et `docs/SESSION_LOG_2026_05.md`
> (verdicts empiriques).

---

## 1. Ce qu'on sait avec certitude

### 1.1 Scan : ce qu'on a observé dans son code

- ~2.1M poids pattern (8 patterns × 3^12 buckets × 2 phases mg/eg, int16)
- ~50 poids structurels (material count, king PST, mobility, balance)
- Encoding base-3 dans les patterns (no king distinction inside patterns)
- 2 phases (mg/eg) interpolées par game_stage
- Géométrie : 8 colonnes verticales × 12 squares (pas 4×4 blocks)
- Fichier weights binaire chargé au startup, training NON inclus dans
  le repo public

### 1.2 jass : ce qu'on a essayé empiriquement

| Setup | Total poids | Phase split | Skeleton | Base | vs v5 d10 |
|---|---|---|---|---|---|
| 0046 pure pattern | 6.25M | non | non | 5 | 0/54 |
| 0047 + quiet data | 6.25M | non | non | 5 | 0/54 |
| 0048 + skeleton (D1) | 6.25M | non | mat+king | 5 | 0/54 (mais 6/54 d6) |
| 0049 + base-3 (D2) | 105K | non | mat+king | 3 | 0/54 |

**Toutes les variantes supervised plafonnent au même endroit** : aucune
ne capte de signal positionnel exploitable, le trainer optimise vers le
mean trivial sur des labels score bruités.

### 1.3 Diagnostic empirique convergent

Sur D1 et D2, `man_value` et `king_value` convergent vers EXACTEMENT
30.7 / 228.2 cp (vs init 100 / 300). Ce n'est pas un bug : c'est ce
que la loss MSE *préfère* sur depth20-1M, parce que les scores sont
trop bruités pour justifier de plus grosses valeurs structurelles.
Adam trouve correctement ce minimum local. **C'est la formulation
supervised cheap qui est inadéquate, pas le code**.

---

## 2. Le gap : 5 choses que Scan fait et qu'on ne fait pas

Par ordre de probable impact croissant.

### 2.1 Phase split mg/eg (gap modéré)

Scan stocke 2 weights par feature, interpolés par game_stage. Sans ce
split, un même pattern doit représenter sa valeur à la fois en
ouverture (homme avancé ~50cp) et en finale (~200cp), donc le réseau
apprend la moyenne et perd les deux signaux.

**Effort pour combler** : ~6h dev (doubler les tables + ajouter
game_stage extraction). C'est du travail mécanique.

### 2.2 Géométrie pattern (gap modéré)

Notre v2 = 16 blocs 4×4. Scan = 8 colonnes verticales de 12 squares.
Les colonnes capturent des relations longue-distance (forward push,
breakthrough threats) que les blocs 4×4 ratent. C'est un choix de
design empiriquement validé chez Letouzey.

**Effort pour combler** : ~3-4h dev (nouveau pattern set "v3-scan",
+ tests parity). Le code est paramétré sur les listes de squares ;
il suffit de définir les bonnes listes.

### 2.3 Feature engineering complet (gap large)

Scan ajoute : material count, king PST par square, mobility (safe vs
denied moves), balance L/R. Notre D1 hybrid n'a que material + king
count (2 features). Le PST seul ajoute ~50 features (1 weight × 50
squares × 2 phases × 2 colors = 200 weights).

**Effort pour combler** : ~1-2 jours dev (extraire features depuis
bitboards, étendre PatternNetwork et trainer, JPAT v4).

### 2.4 Méthode de training (gap dominant probable)

C'est l'écart le plus fondamental ET le plus opaque. Scan utilise
quasi-certainement (basé sur Buro GLEM + littérature dames) :

- **Régression linéaire full-batch** (pas Adam minibatch) sur la loss
  convexe. L-BFGS converge en dizaines d'itérations vs des époques
  d'Adam qui osciller. Notre `train_pattern.py` utilise Adam parce
  que c'est le default — mais notre loss est *exactement* convexe
  (linear in pattern weights), donc on devrait L-BFGS.
- **TD-leaf** ou **TD-Lambda** : self-play, propager la valeur réelle
  observée depuis le PV-leaf vers les positions de la racine. Cela
  régularise massivement les labels bruités du depth-20-supervised.
  Buro l'utilise pour Logistello, Wiering et al. pour les dames intl.
- **Multi-pass refinement** : entraîner v1, l'utiliser pour jouer,
  régénérer data, entraîner v2, …, sur N=10-100 itérations. C'est
  ce qu'on appelait "Phase 2 self-play" dans `PATTERN_ROADMAP.md`.

**Effort pour combler** : variable — L-BFGS = ~2h dev, TD-leaf =
~1-2 semaines dev + 10 itérations compute, multi-pass = idem.

### 2.5 Décennies de tuning + recipes propriétaires (gap fondamental)

Letouzey a sorti la 1ère version de Scan en 2008. Itéré pendant
~15 ans. Les heuristiques de feature design, les pré-traitements
sur le dataset, les schedules de training, sont des artisanat
accumulé qu'on ne peut pas répliquer en lisant le code (qui ne
montre que l'inférence).

**Effort pour combler** : impossible sans soit décompiler le pipeline
Scan (pas disponible), soit réinventer indépendamment via plusieurs
mois de R&D dédiée.

---

## 3. Plan itératif de fermeture du gap

Idée centrale : on attaque les écarts dans l'ordre **certitude
d'impact décroissante** × **coût croissant**. À chaque étape, decision
gate clair : si l'étape ne bouge pas l'aiguille, on arrête là plutôt
que d'enchaîner les pertes.

### Étape G1 — L-BFGS sur la loss convexe (~€0.5, ~4h dev)

**Pourquoi en premier** : c'est gratuit ET ça teste l'hypothèse la
plus fondamentale (notre Adam est-il en cause ?). La loss
`λ·MSE + (1-λ)·BCE` sur des poids linéaires (pattern lookup =
embedding) est globalement convexe. L-BFGS converge en dizaines
d'itérations sur l'ENTIER du dataset (full-batch), pas en époques
minibatch oscillantes.

Implementation : remplacer Adam par `torch.optim.LBFGS` dans
`train_pattern.py`, retirer warmup/cosine (inadaptés à LBFGS), batch
= full dataset. ~50 lignes Python.

**Decision gate G1** :
- rate vs v5 d10 ≥ 0.10 sur D1 hybrid avec L-BFGS → **Adam était en
  cause, continuer avec L-BFGS pour les étapes suivantes**.
- < 0.05 → Adam n'était pas le problème, pivot vers G2.

### Étape G2 — Knowledge distillation depuis v6 (~€1, ~6h dev)

**Pourquoi** : si patterns peuvent en principe imiter une eval qui
marche, c'est un signal fort que l'archi est viable, juste que les
labels score depth-20 sont trop bruités. La distillation utilise les
*sorties de v6 sur ces mêmes positions* comme labels (cibles plus
propres), pas le score search.

Implementation : tool `tools/generate_v6_targets.py` qui passe le
1M dataset à travers v6 et output un dataset avec score = v6.evaluate(pos).
Puis train_pattern.py classique sur ce nouveau dataset.

**Decision gate G2** :
- rate vs v6 d10 ≥ 0.40 (distillation devrait facile imiter le master) →
  **archi pattern peut représenter une eval ; bug actuel = labels
  bruités** ; pivot vers G3 ou G4.
- ∈ [0.20, 0.40] → partial signal, essayer **G2-WDL** (cf ci-dessous)
  avant de conclure.
- < 0.20 → l'archi pattern ne peut pas représenter l'eval v6 ;
  essayer G2-WDL aussi pour borner ; sinon abandon honnête.

### Étape G2-WDL — Scan-aligned : pure logistic regression sur WDL (~€1, ~3h dev)

**Pourquoi cette variante** : la note `docs/SCAN_ARCHITECTURE_NOTES.md`
§5 (révision 2026-05-28) confirme que Scan n'utilise PAS de label score
de recherche. **Cible = WDL de partie + régression logistique sur
features sparses**. Notre G2 (distillation depuis v7) est une approche
score-based différente. Si G2 plateau < 0.40, G2-WDL réplique la méthodo
Scan exacte.

Implementation :
- Re-train pattern v2 hybrid avec `--lambda 0.0` (pure BCE WDL, no score
  MSE) sur le dataset 1M self-play (WDL labels présents) + master games
  Lidraughts (WDL réel = signal le plus propre).
- Optimizer L-BFGS (G1 a montré qu'il converge proprement, juste qu'il
  manque un signal utile à minimiser) — la log-loss WDL est convexe et
  pas dégénérée vers pred=0.

**Decision gate G2-WDL** : même grille que G2 (rate vs v6 d10).

### Étape G3 — Feature engineering complet (~€2, ~2j dev)

**Pourquoi** : ajouter king PST 50-square + mobility + balance + phase
split MG/EG. Aligne la spécification sur Scan exactement (§4bis du
doc archi). Notre D1 hybrid avait juste 2 scalaires (man_value,
king_value) — Scan a en plus :
- King PST : 50 vars (× 2 phases = 100 weights)
- King mobility : 2 vars (× 2 phases = 4 weights)
- Balance L/R : 1 var (× 2 phases = 2 weights)
- Phase split MG/EG sur TOUS les paramètres : ×2 le compte total

Combiné avec G1 (L-BFGS), G2 (distillation) ou G2-WDL si ceux-ci ont
décollé.

Implementation : JPAT v4 = v3 + king_PST[50] + king_mobility[2] +
balance[1] + game_stage threshold (Scan utilise `Stage_Size = 300`,
stage dérivé du matériel restant). PatternNetwork extend evaluate(),
trainer étend les modèles.

**Decision gate G3** :
- rate vs v5 d10 ≥ 0.30 → **archi viable**, on a la baseline pour
  Phase 2 self-play (G4).
- < 0.15 → feature engineering n'est pas le facteur dominant ; pivot
  G4 ou abandon.

### Étape G4 — TD-leaf self-play (révision coût 2026-05-28)

**Note de révision** : l'estimation initiale (~€20-40, ~3-4 semaines)
était héritée de `PATTERN_ROADMAP.md` écrit AVANT qu'on ait mesuré la
vitesse pattern eval (~130 M evals/s, ~300× plus rapide que
MLPNetworkQ). Recalcul honnête en deux modes :

#### G4-diag — diagnostic minimal (~€2-3, ~1-2 jours wall)

Objet : voir si la méthodo self-play TD-leaf débloque quelque chose,
SANS prétendre converger vers une eval compétitive. Sert de cheap-check
final de la chain G avant abandon ferme.

| Composant / iter | Wall |
|---|---|
| Self-play 10K games depth 4 (4 vCPU parallel) | ~30 min |
| Train pattern v2 hybrid + extras + phase split | ~30-45 min |
| Bench vs v6 d10 | ~15 min |
| Total / iter | **~1-1.5h** |

10 itérations = ~15h wall = ~1-2 jours sur 1× CCX23. Compute coût ~€2-3.

**Decision gate G4-diag** : si rate vs v6 d10 ≥ 0.20 après 10 iter →
self-play marche, monter en G4-prod ; sinon abandon ferme.

#### G4-prod — production training (~€10-20, ~1 semaine wall)

Objet : si G4-diag a montré du signal, train un réseau pattern
sérieux. 100K-300K games par iter, depth 6, 20 itérations.

| Composant / iter | Wall |
|---|---|
| Self-play 100K games depth 6 | ~5-8h |
| Train + bench | ~1-1.5h |
| Total / iter | ~6-9h |

20 itérations ≈ 1 semaine wall, ~€10-20 compute.

**Decision gate G4-prod** : si après 20 iter le rate ne dépasse pas
0.40 vs v6, abandon ferme de l'axe pattern pour cette ère du projet.

#### Implementation (commune G4-diag et G4-prod)

- Nouveau mode C++ `--self-play-pattern N out.jnnw` qui joue N games
  pattern-vs-pattern, log positions + WDL observé + score intermédiaire
  (TD-leaf : valeur depuis le PV-leaf propagée vers les positions root).
- Loop script `0055-g4-self-play-pattern.sh` qui itère `self-play →
  train → bench-vs-previous → keep-winner`.
- Effort dev : ~1-2 jours (mode self-play C++ + loop orchestration).

### Étapes H1-H5 — espace DESIGN (hypothèses non-testées par G1-G4)

> Ajouté 2026-05-28 après le verdict G4-diag (0055) FLAT. La chain
> G1→G4-diag a couvert l'espace **méthodologie** (optimizer, labels,
> features skeleton, phase awareness, self-play) avec géométrie v2
> figée. L'espace **design** reste largement non-testé : géométrie
> pattern, bootstrap, volume self-play, mobilité features, métriques.
> Ce sont les hypothèses suivantes par ordre de probable racine ×
> coût croissant.

#### H1 — Géométrie pattern (probable racine, jamais testée)

Notre v2 = 16 blocs **4×4 horizontaux**. Scan = 8 colonnes **verticales
de 12 squares** + Trits/Perm reindexing. Ces géométries capturent des
choses fondamentalement différentes : 4×4 = adjacence locale 2D ; 12-sq
verticaux = forward-push, breakthrough threats, opposition de files
(critique pour dames internationales où les hommes n'avancent QUE).

**Test G5-diag** (job 0057, ~€1, ~3-4h CCX33) : reproduire la self-play
loop de G4-diag (10 iter × 20K records, pure BCE WDL, LBFGS) MAIS avec
géométrie v3 = 8 patterns × 12 squares verticaux. Si rate vs v6 d10 ≥
0.10 → **géométrie était la racine**, escalader G5-prod. Si flat
aussi → géométrie pas la racine non plus.

**G5-prod** (~€10-20, ~1 semaine) : volume scale-up sur géométrie v3
si G5-diag montre signal.

#### H2 — Volume self-play insuffisant (medium-cost test)

G4-diag = 200K positions totales. Scan a probablement utilisé millions
à milliards de games. Notre 20K/iter ne suffit peut-être pas à
distinguer good patterns de bad au bruit du gradient.

**Test** (~€5-10, ~1-2 jours wall CCX33) : même setup G4-diag/G5-diag
mais 200K records/iter × 10 iter = 2M total. À déclencher si H1
montre signal mais G5-diag rate vs v6 d10 stagne.

#### H3 — Bootstrap depuis 0 trop noisy (cheap test)

On a démarré self-play depuis skeleton-only (man=100, king=300,
patterns=0). Premiers iters de self-play produisent des games très
bruitées (le réseau v0 joue ~random). Scan/Kingsrow démarrent souvent
d'un état déjà tuné (régression initiale GLM sur master games avec
features fixes) — pas d'un random.

**Test** (~€2, ~3-4h CCX33) : G3-like régression de v3 patterns sur
master games WDL (corpus 0014, 4.7M positions), produit v3-bootstrap.
Puis self-play depuis ce starter (au lieu de g5-v0 skeleton-only).
Si v3-bootstrap-then-self-play >> v3-skeleton-then-self-play, le
bootstrap est critique. À tester après H1 si signal partiel.

#### H4 — Mobilité features (skipped pour cost en G3a/b)

Scan a king_mobility = 2 vars (cases sûres vs attaquées). On l'a
sauté pour éviter d'appeler generate_legal_moves dans le hot path.
Mais c'est probablement critique pour les positions tactiques (qu'on
filtre via --quiet-only mais qui restent présentes en self-play).

**Test** (~€3, ~1j dev + ~3-4h CCX33) : étendre PatternNetwork +
trainer avec mobility (compté à l'eval via generate_legal_moves
appelé une fois). JPAT v6 avec 2 nouvelles vars. À tester si H1 et H3
sont flat.

#### H5 — Métrique de progrès trop binaire (cosmétique, cheap)

On benche binaire (rate vs v6 d10). Pattern v* progresse peut-être
sur la val_loss / l'eval-correlation-vs-v7 sans encore se traduire en
wins vs un MLP cycle 9 fully-trained. Une métrique non-binaire
révélerait peut-être du progrès qu'on rate.

**Test** (~€1, ~1h dev) : ajouter à chaque iter de la self-play loop
un log de Pearson-correlation(pattern.evaluate(pos), v7.evaluate(pos))
sur un sample de 1000 positions. À ajouter dans G5-diag pour qu'on
ait cette métrique side-by-side avec le bench rate.

### Étape G_final — Réplication Scan exacte (~€?, ~3-6 mois)

Hors scope pratique. Implique de répliquer 15 ans d'itérations de
Letouzey. Listée pour mémoire ; n'a pas de plan concret. Seulement
envisageable si on identifie un volontaire dédié + budget compute
sur plusieurs mois.

---

## 4. Recommandation finale honnête

**Court terme (cette session ou suivante)** :

- v7 (job 0050) sur axe data — gains éprouvés, ROI clair.
- Si excédent d'envie/budget, **G1 (L-BFGS)** sur D1 pour vérifier
  l'hypothèse Adam. ~€0.5, peut-être décisif.

**Moyen terme (si on relance pattern axis)** :

- G1 → G2 → G2-WDL → G3 dans cet ordre. À chaque gate, accepter d'arrêter.
- Budget total pessimiste : ~€5 + ~1 semaine dev.
- ROI si G3 réussit : avoir une baseline pattern viable pour Phase 2.

**Long terme — post G4-diag FLAT (2026-05-28)** :

La chain G1→G4-diag a couvert l'espace méthodologie. La suite est
l'espace **design** :

- **H1 G5-diag** (géométrie v3 verticaux Scan-style, ~€1, ~3-4h) — le
  test design le plus distinctif. À tester en premier après G4-diag.
- **H3 bootstrap** (~€2, ~3-4h) — si H1 partiel/flat, essayer init
  pattern depuis régression sur master games.
- **H2 volume** (~€5-10, ~1-2 jours) — si H1+H3 partiels, scale-up
  self-play à 200K records/iter.
- **H4 mobilité** (~€3, ~1j dev) — si H1-H3 flat.
- **H5 métrique** (cosmétique, ~€1) — à ajouter à toutes les variantes
  H pour détecter du progrès non-binaire.
- G_final (réplication Scan complète) ignoré sauf décision explicite.

L'**erreur à éviter** : refaire D2/D3 variants sans avoir testé G1.
La piste "supervised pur sur archi pattern" est exhaustée par les 4
expériences. Le gap suivant est méthodologique, pas paramétrique.
