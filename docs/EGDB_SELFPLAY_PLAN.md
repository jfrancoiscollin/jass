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

## Matrice d'expériences

| Job | Hypothèse | Verdict / règle |
|---|---|---|
| **0276** ✅ | features finale en self-play | +230 vs hc (+28 vs 0266) ; endgame-rois 3.06. Aide, ne casse pas. |
| **0287** ⏳ | jeu-parfait-finale (egdb ON gen) casse le verrou | endgame-rois ≪ 3.06 → couverture-par-jeu = clé ; ≈3.06 → verrou = capacité éval (archi). |
| **0293** ⏳ | depth-ramp `late-mid=12,endgame=16` sur l'entre-deux | A(unif-8) vs B(ramp) ; B-rois < A → approfondir l'entre-deux aide (labels ancrés-TB). |
| **0291** ✅ | minibatch = outil mémoire | moitié RAM (11.6 vs 21.9 GB). 0274-wedge ≠ thrash (lowmem 5M = 4 min). |
| **0294** ⏳ | minibatch EXACT (convexe → optimum unique) | train_loss égaux à convergence → exact ; différents → divergence chunké. |
| **assemblage** 🔜 | boucle complète (1)+(2)+(3)+minibatch[+ramp] | une fois 0287/0293/0294 verts. |

## Règles de décision

- **0287 casse le verrou** (endgame-rois ≪ 3.06) → la couverture-par-labels-exacts
  était la clé → assembler la boucle complète (relabel+coverage+ramp), egdb dans la
  prod, re-baseline vs Scan.
- **0287 plafonne** (≈3.06) → le jeu-parfait seul ne suffit pas. Deux sous-cas :
  - 0293 (ramp) aide → les labels de **transition** étaient le maillon → intégrer le
    schedule + coverage.
  - 0293 n'aide pas → verrou = **capacité de l'éval** (PST/features ne représentent
    pas la finale-rois) → piste **architecture éval** (au-delà du linéaire king-aware).
- **minibatch** : intégré au train prod **après** 0294 vert (exactitude confirmée) ;
  nécessaire seulement quand le cumulatif (gonflé par coverage) dépasse ~7M.

## Décisions en attente (pas du code)

1. Flip `JASS_ENDGAME_FEATURES` défaut→ON (acquis +28 Elo ; en attente verdict 0287).
2. Schedule profondeur retenu (selon 0293).
3. Assemblage de la boucle (job dédié).
