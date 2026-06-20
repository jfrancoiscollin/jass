# Choix techniques BIAISÉS par la limitation du fit-volume — à REVISITER (2026-06-20)

> **Le critère de tri.** Le **défaut** et la **grande majorité** des verdicts A/B (géométrie, replis, élagage, rois…)
> ont été jugés sur un fit **≤2M** (full-batch RAM, OOM à ~3.4M). **TOUT verdict éval/data/archi jugé sur un fit ≤2M
> est potentiellement CONFONDU** : on a comparé des modèles **affamés**, dont les plus riches (plus de poids) étaient
> *structurellement* désavantagés (sous-fittés). Maintenant que le fit scale (minibatch 15M → `train_stream` 100M,
> cf [BOUCLE_VIRTUEUSE.md §8](BOUCLE_VIRTUEUSE.md)), il faut **re-juger** cette classe de décisions. Les choix
> **recherche/méthodo/infra** ne sont PAS touchés (indépendants du fit).

> **⚠️ Nuance factuelle (corrigée 2026-06-20) — on N'a PAS *toujours* été à ≤2M.** On a **visé 6.7-10.7M plusieurs
> fois** avec le pattern-eval (chargé via `--nnue`) : 0317 (6.7M, **FAILED**), **0318 (6.7M, COMPLETED → +253 Elo vs
> hc)**, 0319 (sweep data-scaling 1M/2M/6.7M, **FAILED** au `subset 1000000`), 0320 (10.7M, **FAILED**). Soit **3 fits
> sur 4 ont CRASHÉ** (OOM/instabilité de l'ancien pipeline minibatch) — *le crash est lui-même le symptôme du cap*.
> Le seul réussi (0318) n'a **jamais** été comparé en tête-à-tête à un petit fit du même setup ⇒ **aucune courbe de
> data-scaling propre n'existe** (celle qui devait la produire, 0319, a planté). Et les **vrais réseaux** (1024-512,
> 128-64) ont plafonné à **~2.37M** (0084). **Bilan : on a *touché* 10M mais (a) non fiable (3/4 crashés), (b) jamais
> contrôlé, (c) jamais >10.7M (vs 30-100M visés), (d) sur l'ancien pipeline distillation, pas la géométrie actuelle.**
> **GATE 0 = la version qui MARCHE de 0319-qui-a-planté** : `train_stream` streame du disque (gradient exact) là où
> les vieux minibatch crashaient.

## A. Le biais mécanique (pourquoi « plus riche perdait » à bas volume)
Plus de poids = plus de data nécessaire pour bien les estimer. À 2M, un modèle à 8,5M poids voit ~0,24 visite/poids :
sa **longue traîne de buckets rares** n'est jamais estimée → il joue *moins bien* qu'un modèle pauvre bien fitté. Donc
à bas volume : **moins de capacité = mieux** (artefact). À gros volume, ça **s'inverse** (la richesse paie). **Tous nos
choix « lean / replier / élaguer / hasher » étaient des réponses à la famine, pas des vérités.**

## B. Verdicts CONFONDUS — à revisiter (par priorité)

| # | Verdict / choix | Preuve (bas volume) | Pourquoi confondu | À re-tester (au scale) |
|---|---|---|---|---|
| 1 | **« Géométrie = levier mort »** | 0230/0234/0239/0359 | géométrie riche jugée à ≤2M, jamais nourrie | **32cf vs 8cf** (color-fold) à 30M+ |
| 2 | **`--full-fold` = le bon repli** | 0224/0227 (+175 vs hc) | full-fold = partage de poids = data-efficient → gagne *à bas volume* ; il impose une invariance-translation FAUSSE qui jette de l'info position | **color-fold / no-fold** (position-préservant) à gros volume |
| 3 | **« Élaguer / réduire la capacité » + « 8=32 »** | 0234 (−31 Elo), 0359 (8=32) | capacité jugée affamée ; 8=32 *au plancher* | capacité 32 vs 8 **bien fittée** |
| 4 | **Bucket-hashing / `PATTERN_HASH` < 3¹² « casse la profondeur »** | 0190/0193 | hasher = pooler les buckets rares = nécessaire SEULEMENT par famine ; les rares « portent la connaissance » → à gros volume on les estime au lieu de les pooler | **no-hash (3¹² plein)** à gros volume |
| 5 | **Partage de poids par symétrie (Piste 3)** | tout l'axe color/rot/trans-fold | motivé explicitement par « ÷4-8 data/poids » = anti-famine | **moins de fold** quand la data abonde |
| 6 | **Rois dans les patterns OFF** | 0240 (+37 distill) / 0360 (men≈king) | men\|kings = index plus riche = PLUS de buckets = encore plus affamé à 2M (0360 jugé à 2M) | **`JASS_KING_PATTERNS`** re-jugé à gros volume |
| 7 | **« Distillation > WDL », « WDL plafonne 0.22 »** | 0194/0196/0356/0357 | WDL = 1 bit/partie = haute variance → exige BEAUCOUP plus de volume que la distillation (score dense) ; jugé à bas volume + jeu peu profond | **WDL profond à gros volume** (la vraie recette Scan ; en cours) |
| 8 | **« Distillation plafonne », teacher d12 n'aide pas** | 0346 | le *student* était capé à 2M | distillation **student bien fitté** |
| 9 | **« Extras structurels / aug symétrie / quiet nuisent »** | 0172 / 0185 / quiet | +features ou +data = +params = +sous-fit à bas volume | re-tester chaque à gros volume |
| 10 | **mg/eg phase-split (double les poids)** | standard | double les params → plus affamé | (faible) re-confirmer au scale |

## C. La méta-conclusion confondue (la plus importante)
> **« On est au plafond de la classe LINÉAIRE → il faut NNUE. »**

Revenue plusieurs fois (0237/0239, distillation plafonnée, plats vs Scan). **Confondue** : on n'a JAMAIS fitté la classe
linéaire à l'échelle où Scan l'a fittée (milliards). Scan = même classe, bien plus fort ⇒ la classe n'est pas le mur.
**Décision NNUE GELÉE** tant qu'on n'a pas un plateau confirmé **à gros volume + profondeur + bonne géométrie/repli**.

> **Le pendant symétrique (les DEUX méta-conclusions sont confondues par la même racine).** Côté **réseau** aussi :
> nos vrais NNUE (1024-512, 128-64) ont été entraînés sur **≤2.37M** (0084 ; le reste à 1M, ex. 0090). Un réseau est
> **non-convexe** et plus gourmand qu'un linéaire ⇒ il a besoin d'**ordres de grandeur PLUS** de data (Scan/SF : 10⁸-10⁹).
> Donc le verdict **« le NNUE n'ajoute rien »** (0132 Phase 5b : pattern-résidu **0/54** vs 128-64) est **au moins aussi
> CONFONDU** que « linéaire au plafond ». On a comparé deux affamés, le plus gourmand (le net) le plus pénalisé.
> **Conséquence** : quand on dégèlera la question NNUE, **le réseau est le candidat qui profite le PLUS du 30M+** — il
> faudra le **réentraîner au scale** (trainer streaming, comme `train_stream` côté linéaire) **avant tout verdict**.

## D. Choix de DESIGN à corriger (conséquences directes)
- **Fenêtre glissante 2M dans la boucle** : posée *à cause* du cap fit → expulse les buckets rares. → **accumuler** sur
  disque + `train_stream` (le fit grossit avec la data).
- **`--lowmem` full-batch** comme défaut → **minibatch / streaming**.
- **Sous-échantillonnage à 2M** dans les jobs (0376/0377/0378) → contournement du cap, plus nécessaire au-delà via streaming.
- **Tout l'outillage de symétrie/hash** (gen_patterns folds, bucket_census, freq-reg) = pensé anti-famine → **dé-prioriser**.

## E. NON confondus — restent valides (indépendants du fit)
- **Recherche** : NMP off (zugzwang, +97 Elo) ; combo multicut+razor baké ; probcut/iid/conthist/history-malus/TT>16Mo/movegen plats. Jugés *côté recherche*, à temps fixe.
- **Méthodo** : juger l'éval à profondeur-égale / self-DIRECT ; régler la recherche à temps fixe ; `endgame_mse ⟂ force`.
- **egdb** (finales exactes ≤7p), **drawish NEUTRE en jeu** (0353, la recherche résout déjà les finales).
- **Jeu profond ≥10** (décisif ≠ véridique) — *récent et orthogonal* au fit-volume ; les deux leviers se cumulent.

## F. Priorisation du re-test (quand on a le scale)
1. **Scale-du-fit** lui-même (0383 : 5M>2M ? puis 30M via `train_stream`) — le préalable.
2. **Géométrie × repli** : 32cf vs 8cf, color-fold vs full-fold, à 30M+ (#1, #2, #3).
3. **No-hash / no-fold** : la richesse plein-format paie-t-elle ? (#4, #5).
4. **Rois dans patterns** à gros volume (#6).
5. **WDL profond vs distillation** à gros volume (#7) — déjà la voie active.
6. Seulement **après** tout ça, si plateau franc : la question NNUE (méta C).
