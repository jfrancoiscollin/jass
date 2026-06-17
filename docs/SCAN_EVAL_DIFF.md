# Audit éval — jass vs Scan vs Kingsrow : trouver ce qui manque (LINÉAIRE)

> Rédigé **2026-06-17** sous le [PRINCIPE DIRECTEUR](ARBRE_DECISION.md) (même classe que
> Scan → on doit l'égaler DEDANS ; le gap = ce qui MANQUE, pas la capacité). Audit
> source-à-source des trois moteurs pour localiser l'ingrédient manquant. À lire avec
> [JOURNAL_DE_BORD.md](JOURNAL_DE_BORD.md) §0 et [EGDB_SELFPLAY_PLAN.md](EGDB_SELFPLAY_PLAN.md).

## Les trois évals, côte à côte

| | **Scan** (Letouzey) | **jass** (nous) | **Kingsrow** (Gilbert) |
|---|---|---|---|
| Classe | linéaire (somme de poids) | linéaire | hand-tuned (récemment ML) |
| Patterns | 4 groupes × **12 cases**, **ternaire {vide, pion-blc, pion-noir}** — **ROIS EXCLUS** | 32 × **12 cases**, **ternaire idem** — **ROIS EXCLUS** (défaut) | matériel + features positionnelles |
| Rois | **king-PST + king_mob (mobilité SÛRE − cases interdites) + roi surnuméraire** | **king-PST (100) + mobilité LUMPÉE pions+rois (brute)** | features + **DB WLD/DTW/MTC** |
| Phase | paire (mg,eg) par feature, interpolée par `stage` (continu) | 2 banks (mg,eg) interpolés par `pièces/40` (continu) | — |
| Cible train | **logistic** sur résultats de parties | **logistic WDL** (recette Scan) | — |
| Conversion finale | **via le GRADIENT de king_mob** (pas de MTC dans l'éval) | — (manque) | **via les DB DTW/MTC** |

**Ce qui MATCHE Scan (à ne plus chercher là) :** la classe (somme additive), la géométrie
des patterns (pions-only ternaire — **Scan exclut les rois des patterns AUSSI**), le modèle
de phase (mg/eg interpolé continu), la cible d'entraînement (logistic WDL). Notre géométrie
est même un *dead lever* prouvé (0203-0236 : enrichir ne paie pas, importance uniforme,
pruning lose-lose). **Donc le gap n'est ni la classe, ni les patterns, ni la phase.**

## Le gap est UNE famille de features rois — et c'est le signal de conversion

Scan et jass gèrent tous deux les rois **hors patterns**, par des features structurelles.
La différence est dans **lesquelles** :

| Feature roi | Scan | jass | Verdict |
|---|---|---|---|
| King-PST (placement/centralité par case) | ✅ | ✅ (100 one-hot, 2 banks) | **MATCH** |
| **King MOBILITY = cases SÛRES − cases INTERDITES par l'adversaire** | ✅ `king_mob` | ❌ (mobilité brute, lumpée pions+rois, **sans sûreté/déni**) | **MANQUE** ⭐ |
| Roi surnuméraire (matériel roi explicite) | ✅ | ❌ (implicite via PST) | manque (mineur) |
| Confinement / roi adverse acculé | ✅ (via king_mob) | ❌ | **MANQUE** ⭐ |
| Opposition, men-vs-king, back-row, tempo | partiel | ❌ (extras gated 106-109 = centralité + proximité Chebyshev, crus, **OFF par défaut**) | manque |

### 💡 Pourquoi `king_mob` est LE point
Notre feature de mobilité (extras 102/103) **additionne pions + glissés-de-roi en un seul
nombre brut par camp**, sans tenir compte des cases **sûres** ni des cases **interdites** par
l'adversaire. Scan calcule `king_mob` = **mobilité de roi SÛRE moins cases déniées** — c'est-
à-dire **le confinement** : roi adverse plus acculé ⇒ moins de cases sûres ⇒ score plus haut.

> **C'est un GRADIENT de conversion, structurel, dans la classe linéaire.** Scan gagne les
> finales sans MTC **parce que cette feature pousse la recherche à confiner le roi adverse.**
> 0306 a échoué parce qu'il cherchait le gradient dans le *label* (cible MTC) ; il était dans
> la *feature* (l'entrée de l'éval). **Voilà ce qu'on rate.**

## Pistes priorisées (toutes 100 % linéaires)

### ⭐ LEAD 1 — Feature king-mobility/confinement à la `king_mob` (LE candidat)
Ajouter des extras dédiés, séparés des pions :
- `BK_KING_SAFE_MOB` / `WK_KING_SAFE_MOB` : nb de cases où chaque roi peut aller **sans être
  capturé** (cases non attaquées par l'adversaire).
- `BK_CONFINE` / `WK_CONFINE` : nb de cases d'évasion **déniées** au roi adverse (symétrique).
- option : indicateur **roi piégé** (0 case sûre) = grosse pénalité.
Entraîner logistic WDL sur données enrichies egdb (coverage ≤7p), mesurer **endgame-rois vs
Scan + Elo**. Coût : ~4-6 extras + retrain. **Teste directement l'hypothèse conversion-par-
feature** que 0306 aurait dû tester. → job dédié.

### LEAD 2 — Ré-évaluer les bricks gated (déjà codées, OFF par défaut) — le quick win
`JASS_KING_PATTERNS` (rois dans patterns, men|kings base-3 ; **+37 Elo en distillation, job
0240**) et `JASS_ENDGAME_FEATURES` (extras 106-109) sont **OFF par défaut**. A/B propre dans
le régime actuel (logistic WDL + données 0297 + coverage egdb) : défaut vs king-patterns-ON
vs endgame-features-ON. Coût quasi nul (flags de build + retrain).

### LEAD 3 — Densité de données finale (PAS le `--phase-weight`, mort)
≤7p = **11.3 %** des données → le bank `eg` (king-PST/mobilité) est **sous-peuplé**. Le
re-poids (`--phase-weight`) est mort (−210 Elo). La bonne voie = **enrichir la COUVERTURE**
de positions de finale exactes (`--gen-egdb-wld`) pour peupler le bank eg. Lié à **0310** : si
le linéaire fitte la finale SEULE (mse bas), c'est bien un problème de densité/équilibre, pas
de classe → entraîner le bank eg sur données finale-denses.

### LEAD 4 — Matériel roi explicite (trivial, Scan l'a)
`BK_KING_COUNT` / `WK_KING_COUNT` en extras (actuellement implicite via PST). 2 features,
coût nul.

### LEAD 5 (parallèle, recherche pas éval) — profondeur en finale
Le bleed deep-eg à mt0.5 est en partie **search-bound** (cf 0251 : la classe range bien la
finale sous labels parfaits, spearman 0.73-0.79 → les features rangent, mais ne *jouent* pas
la conversion). Extension de recherche / plus de profondeur en basse densité de pièces.
Compatible linéaire ; complémentaire de LEAD 1.

## Tension à garder en tête (honnêteté)
Job 0251 : sous labels PARFAITS, la classe linéaire **range déjà bien** la finale (spearman
0.73-0.79). Donc les features actuelles ne sont pas *nulles* — mais **ranger une position ≠
jouer la conversion** (qui exige le gradient de king_mob pour guider la recherche vers le
confinement). L'échec de 0306 (cible MTC) est la preuve que **le signal de conversion est
absent de l'éval**. LEAD 1 l'ajoute là où Scan l'a. C'est l'hypothèse la plus probable —
mais elle se *teste* (job LEAD 1), elle ne se décrète pas.

## Ce qu'on NE fait PAS
Pas de FM/MLP (PRINCIPE DIRECTEUR). Pas de nouvelle géométrie de patterns (dead lever). Pas
de `--phase-weight` (mort). Pas de cible-gradient MTC (0306, cul-de-sac). Le levier est
**des features rois manquantes + densité de données finale**, dans la classe de Scan.
