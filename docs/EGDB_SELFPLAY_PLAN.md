# Plan d'expérience — boucle self-play exacte (egdb) contre le verrou finale

> Rédigé **2026-06-16**. Consolide l'attaque du **verrou roi-finale** (le saignement
> ~3.6 vs Scan, cf JOURNAL §finales) avec la bitbase egdb scellée. Architecture de
> la boucle cible + matrice d'expériences + règles de décision. À lire avec
> [BITBASE_INTEGRATION.md](BITBASE_INTEGRATION.md) (procédure base) et
> [JOURNAL_DE_BORD.md](JOURNAL_DE_BORD.md) (faits).

## Le problème

L'éval **range bien** la finale (spearman 0.73-0.79, 0250) mais le self-play y est
**mal entraîné** : la recherche jouait les finales avec une éval imparfaite → parties
atteignant de mauvais résultats → l'éval s'entraîne sur ses propres erreurs. Verrou =
**couverture/qualité des labels de finale**, pas la classe d'éval. Deux directions
testées :
- **B (représentation)** : features king-interaction → **+28 Elo** (0276) mais le
  bleed roi reste ~3.06 ; aide, ne casse pas le verrou.
- **A (couverture)** : densifier les labels de finale. 0274 tentait des labels
  **depth-16** (recherche imparfaite, bruités). **Supplanté par la bitbase** : labels
  **WLD EXACTS** ≫ depth-16.

## La bitbase egdb (scellée 2026-06-16)

WLD 2→7 pièces (Kingsrow, via egdb_intl). **Self-test natif 164/164** + conversion
bit-à-bit validée + **guard <3 pièces** (le slice db2 rend un décisif faux sur
quelques KvK ; sous 3 pièces on défère aux tables internes, KvK=Draw exact).
`probe_endgame` consulte egdb d'abord. Détails : BITBASE_INTEGRATION.md.

## Boucle cible — par génération

```
GÉNÉRATION (egdb ON : JASS_EGDB_PATH sur --gen-data-wdl)
  parties self-play ; à tout nœud ≤7 pièces → probe TB → JEU PARFAIT en finale
  + TERMINATE-AT-TB : la partie FINIT au résultat TB exact dès qu'elle atteint ≤7p
    → fini le STALL (0295 : ~50% des finales gagnées finissaient nulles → labels faux)
        │
        ▼
RELABEL (--egdb-relabel)        rôle (2) : positions ≤7p du flux → label WDL
        │                       ÉCRASÉ par la vérité egdb (≫ résultat-de-partie)
        ▼
+ COVERAGE (--gen-egdb-wld)     rôle (3) : injecter des positions ≤7p ALÉATOIRES
        │                       quiètes labelisées WLD exact → couverture dense
        ▼
TRAIN (train.py --minibatch)    L-BFGS plein-batch EXACT, pic RAM borné → le
        │                       cumulatif peut dépasser ~7M (plafond lowmem/32GB)
        ▼
ÉVAL (egdb OFF)                 Elo vs hc + autopsie vs Scan → endgame-rois :
        │                       mesure si l'ÉVAL a APPRIS la finale (généralise)
        └──► gen(g) pilote gen(g+1)
```

**Les 3 rôles de la bitbase** (valeur croissante) : (1) jeu parfait en génération
(0287) ; (2) relabel exact des positions ≤7p du flux ; (3) coverage dense aléatoire.
(2)+(3) sont *exactement* ce que 0274 visait — mais exact et gratuit.

**Discipline egdb ON/OFF** : ON en génération (labels exacts), OFF aux benchmarks
(on mesure l'éval pure, pas le TB qui triche).

**Synergie profondeur×TB** : sur l'entre-deux 8-21 pièces (above bitbase), une
recherche profonde (`--play/--label-depth-by-phase endgame=16`) **mord dans la TB**
(atteint des feuilles ≤7p → valeurs exactes remontées) → labels de transition
ancrés-TB. egdb rend cette recherche profonde *moins chère* (cutoffs TB).

## Outils (codés, validés 0292)

| Outil | Rôle | CLI |
|---|---|---|
| `--egdb-relabel <in> <db> [out]` | (2) réécrit WDL ≤7p par egdb | idempotent, STM-POV |
| `--gen-egdb-wld <N> <out> <db>` | (3) coverage aléatoire quiète | ≥1/côté, 3-7p, men hors promo |
| `--egdb-selfcheck <db> <n>` | garde-fou invariant (KvK no-cap=Draw) | egdb=vérité |

## Conversion : le GRADIENT (cible MTC offline — sans MTC au jeu)

terminate-at-TB corrige la *valuation* (les labels), **pas la conversion en match**.
Rappel : **Scan convertit sans MTC**, via le **gradient de son éval** (une position
gagnée "plus convertie" — roi adverse plus acculé, moins de matériel — score plus
haut). Notre cible **WLD est PLATE** (gain = 1 partout) → l'éval **ne peut pas** apprendre
"plus proche de la conversion". Le gradient doit venir d'un **signal de distance dans la
CIBLE** :

> **(a) MTC comme CIBLE D'ENTRAÎNEMENT (offline)** — labelliser les positions ≤8p avec
> leur distance-à-la-conversion (MTC) → cible graduée → l'éval **APPREND le gradient et
> le GÉNÉRALISE à 8-21** → **pas de MTC au jeu** (≠ Scan qui n'en a pas non plus ; nous
> on l'utilise juste pour *enseigner*). `egdb_intl` lit le MTC (`is_mtc`, `egdb_lookup`
> unifié). Coût : download offline (recon 0298). **Choisi.**
> (b) DTW « maison » ≤5-6 par rétro-analyse du WLD — zéro download, gradient exact mais
> petites tranches seulement. (c) cible-proxy (confinement/matériel) — cheap, heuristique.

### Implémenté (option a + proxy) — la chaîne

1. **MTC sur disque** (0300/0301) : Kingsrow MTC 2-8 (≤8p, ~29 GB extrait) sur les 2 boxes.
   `egdb::init_mtc / probe_mtc` (handle séparé, `is_mtc`-vérifié). CLI `--egdb-mtc-probe`.
2. **MTC est COARSE** (0302) : `egdb_lookup` MTC rend `1` si <10 plies (la base ne stocke pas
   <10 → **plat** : 99.75 % des gains), sinon la distance réelle (≥10, ~0.25 %). Le gradient
   MTC n'existe que dans la zone de manœuvre **≥10 plies** (= la zone de stall).
3. **HYBRIDE proxy+MTC** (`--egdb-mtc-relabel <in> <wld> <mtc>`) — comble le <10 plat :
   ```
   winp = 1 − ALPHA·(pièces adverses) − GAMMA·(centralité rois adverses) − BETA·max(0, MTC−10)
        clampé [0.55, 1.0]   (perte symétrique ; nul/hors-WLD → fallback WDL)
   ```
   PROXY (matériel + confinement) = gradient fin dans le <10 ; MTC = exact dans le ≥10.
   Stocké en `score = prob×10000`. `ALPHA=0.04, GAMMA=0.008, BETA=0.03` (tunables).
4. **`train.py --target prob`** : loss logistique sur `score/10000` → **garde le régime
   WDL-logistique prod** pour la masse, injecte le gradient en finale.
5. **Chaîne validée end-to-end** (0303) : `gen-egdb-wld → mtc-relabel → train --target prob`.

**Reste** : vrai run gradient (coverage **enrichie en positions ≥10-MTC** + finales-rois +
self-play) → train `--target prob` → mesurer la **conversion vs Scan** ; caler ALPHA/GAMMA/BETA.

## Matrice d'expériences

| Job | Hypothèse | VERDICT |
|---|---|---|
| **0276** ✅ | features finale en self-play | +28 Elo ; endgame-rois 3.06. Aide, ne casse pas. |
| **0287** ✅ | egdb-perfect (depth-8 unif) casse le verrou | NON : rois 3.22, vs Scan −741. *Mais labels pollués par stalls (0295) + depth-8 sous-teste (0293).* |
| **0293** ✅ | depth-ramp 12/16 sur l'entre-deux | OUI : rois **2.86→2.04 (−29 %) +74 Elo** → classe linéaire PAS saturée. |
| **0291/0294** ✅ | minibatch = outil exact + ½ RAM | OUI : train_loss identique à convergence ; outil de scaling >7M. |
| **0295** ✅ | quantifier le stall / fix distance-aware | **~50 % des finales décisives stallent** ; fix `−ply` corrige ~12 %. → motive terminate-at-TB. |
| **0296** ✂️ | FM (non-linéaire) | ANNULÉ — prématuré (Scan linéaire ; déjà tranché 0184). |
| **0297** ⚠️ | saturer le linéaire (labels PROPRES) | **PLAFOND + RÉGRESSION du loop.** gen6 60p vs hc **+234** (= 0287/0276, aucun gain) ; vs Scan **−800** (0/54, pire que 0287 −741) ; endgame-rois deep-eg **3.06** — **le loop 6-gen RÉGRESSE sous le 2.04 du depth-ramp 1-gen 0293**. Le loop dégrade : Elo culmine gen1-3 (+253)→↘+194 ; **endgame_mse ↑ 1.8→5.4** monotone (labels finale exacts *augmentent* l'erreur). → SOIT saturation linéaire, SOIT le loop pollue/dégrade. **0309 tranche.** |
| **0298** ✅ | recon taille MTC (pour le gradient (a)) | MTC 2-8 (~29 GB extrait) téléchargé sur les 2 boxes (0300/0301). |
| **0306** ⏳ | gradient conversion greffé sur 0297 | A/B WDL vs `--target prob` (0.12/0.04). Après 0301. **Prochaine vraie mesure.** |
| **0307** ⏳ | livre d'ouverture à la Scan (drop-out) | A/B self-play jass±livre + vs Scan + audit (0308). |
| **0309** ⏳ | drift 0297 : bug (pollution) vs saturation | ablation FULL/NO-EG/EG-ONLY + scan de contradictions WDL. Après 0306. |

## Règles de décision (à jour 2026-06-17)

- **0297 a plafonné** : scaler des cycles **ne marche plus** (le loop régresse même). Le
  point de bascule est passé → **gradient + capacité priment** sur « plus de données ».
- **MAIS** : le depth-ramp 1-gen (0293) avait atteint 2.04, le loop l'a perdu → **avant de
  conclure « saturation »**, `0309` doit séparer **bug de loop** (cumul pollué → nettoyer/
  ré-itérer proprement, le 2.04 serait récupérable) de **saturation représentationnelle**
  (le linéaire ne descend pas même sur finales-seules → capacité).
- **Conversion en match** : `0306` a tranché — le **gradient proxy+MTC NE TRANSFÈRE PAS**
  (Elo −20, deep-eg 2.91→3.78, vs Scan inchangé) car 99,9 % proxy / 148 vrais signaux MTC.
  Cul-de-sac comme cible. *Ce n'est PAS un appel à la non-linéarité.*
- **⛔ PAS de FM/MLP** (cf. PRINCIPE DIRECTEUR, ARBRE_DECISION) : on a la classe de Scan, on doit
  l'égaler DEDANS. Le verrou deep-eg-rois (perte ~3) = **ce qui MANQUE au linéaire**, pas une
  preuve de saturation. Pistes, par ordre : **(1) patterns/features de finale-rois manquants**
  (Scan capture la conversion via ses patterns) ; **(2) équilibre d'entraînement** (≤7p = 11.3 %
  des données → la finale est écrasée 9:1 par le midgame ; re-pondérer / phase-split — `0310`
  teste si le linéaire fitte la finale SEULE) ; **(3) recherche** (profondeur/temps en finale).

## Décisions en attente (pas du code)

1. Flip `JASS_ENDGAME_FEATURES` défaut→ON (acquis +28 Elo ; en attente verdict 0287).
2. Schedule profondeur retenu (selon 0293).
3. Assemblage de la boucle (job dédié).
