# Phase Pattern-1 Othello POC — Verdict final

> Bilan de la POC pattern Logistello-style sur Othello 8×8.
> Démarré PR #170 (2026-06-04), terminé PR #176 + bench Day 7.

## Objectif (rappel)

Valider une infra pattern lookup propre — encoding base-3, eval
linéaire, training L-BFGS — sur un domaine où Logistello est
documenté A à Z. Avant de transposer le paradigme sur draughts
(où nos 18 tentatives ont échoué), confirmer que **notre code**
n'est pas le problème.

Cible README (`othello/README.md` §2 Day 7) :
> **Gate 1** : si pattern eval Othello bat random à ≥95% → infra
> pattern propre fonctionne. Continuer Phase Pattern-2 (jass).

## Pipeline implémenté

| Day | PR | Composant | Validation |
|---|---|---|---|
| 1 | #170 | board + movegen 8 directions | perft(8)=390216 match Edax |
| 2 | #172 | 10 patterns Logistello (40K buckets) | 7 tests pattern (signs, symmetries) |
| 3 | #173 | eval (basic + pattern) + alpha-beta | Gate 1 basic vs random 100% |
| 4 | #174 | gen-data WDL binary | 6.7 games/s @ depth 4 |
| 5 | #175 | training Python L-BFGS | sign_acc 0.79 sur 500g |
| 6 | #176 | weights loader C++ + bench eval_vs_eval | infra end-to-end OK |

## Résultats finaux Day 7

### Gen-data 10K games

```
gen_data : n_games=10000 out=/tmp/gen_10k.bin random_plies=8 search_depth=4 sample_stride=4 seed=42
done : 129916 records, B/W/D=4809/4998/193, wall=69s
```

Throughput : ~145 games/sec depth 4 sur 8 vCPU (single thread).

### Training L-BFGS (10K games, 500 iters, λ=1e-5)

```
loading dataset /tmp/gen_10k.bin
  129916 records
extracting pattern indices
  shape (129916, 10) buckets=39690
split : train=116925 val=12991
L-BFGS  l2=1e-05  max_iter=500
  train_loss=0.314749  iters=500  (23.77s)
val   : mse=0.681969  sign_acc=0.7029
quant : scale=1000  range=[-1312,1362]  nnz=13145
```

Coverage : 13145 / 39690 ≈ 33% des buckets touchés par le dataset.

### Bench vs random (Gate 1)

| Engine | Win | Loss | Draw | Rate | Verdict |
|---|---|---|---|---|---|
| basic (handcrafted) | 100 | 0 | 0 | **1.000** | baseline |
| pattern 2K-train  |  97 | 2 | 1 | **0.975** | ✅ Gate 1 |
| pattern 10K-train | 100 | 0 | 0 | **1.000** | ✅ Gate 1 |

**Gate 1 dépassé largement** (cible 0.95, atteint 0.975 dès 2K games,
1.000 dès 10K games).

### Bench pattern vs basic (extension)

| Pattern (A) | Basic (B) | Wins/Losses/Draws (A POV) | Rate |
|---|---|---|---|
| 2K-train  | basic | 41 / 57 / 2 | 0.42 |
| 10K-train | basic | **67 / 32 / 1** | **0.675** |

Le pattern entraîné sur 10K games **bat le handcrafted basic à 67.5%**
(≈ +125 ELO). C'est au-delà de l'objectif POC — on a non seulement
validé l'infra mais aussi **dépassé l'eval handcrafted** avec seulement
~1 minute de gen-data + 25 secondes de training.

## Verdict global

### Infra pattern propre : **VALIDÉE** ✅

- Encoding base-3 : fonctionne (39690 buckets indexés correctement)
- Linear eval `sum(w[idx[i]])` : fonctionne (compatible sign-flip stm)
- Training L-BFGS sparse CSR : fonctionne (24s pour 130K records × 500 iters)
- Round-trip Python ↔ C++ via OTHW binary : fonctionne (loader testé)

### Implications pour Phase Pattern-2 (draughts)

Le code pattern **fonctionne**. Nos 18 tentatives draughts ont donc
échoué pour des raisons autres que l'infra : probablement
**géométrie pattern + signal de training** spécifiques au draughts.

Hypothèses à tester sur draughts (Phase Pattern-2) :
1. Patterns mal choisis (vs Logistello qui a 30 ans d'optims)
2. Encoding inadapté (men vs kings, capture-forcée, etc.)
3. Volume training insuffisant pour la dimensionnalité
4. Plafond intrinsèque du paradigme linéaire pour draughts

L'erreur n'est PAS dans le code pattern lookup. Le pipeline complet
gen → train → eval → bench est éprouvé end-to-end sur Othello.

## Méta-leçons techniques

1. **Random opening obligatoire dans les benches eval-vs-eval**.
   Sans ça, engines déterministes → toutes les parties identiques par
   color-swap → résultats 50/50 artefactuels.
2. **stdbuf -oL ou flush explicite pour benches dans pipes**. Pas un
   problème ici car bench rapide, mais pattern observé sur jass (cf
   PERF_JOURNEY §15).
3. **Sign-accuracy comme métrique de training** : MSE seul peut être
   trompeur ; sign-acc sur validation set capte mieux "le modèle
   prédit-il le vainqueur" (binaire), pertinent pour l'usage en search.
4. **Coverage des buckets** : 33% de touches à 130K records — il y a
   du grain à moudre avec plus de données. Mais déjà supérieur à basic
   en pratique, donc rendement décroissant.

## Prochaine étape

Phase Pattern-2 du roadmap (`docs/ROADMAP.md:362`) : "Pattern jass
minimaliste (3-5 jours)". Appliquer le pipeline éprouvé d'Othello à
8 features Scan-geometry mais code from scratch + régression sur
master Lidraughts 2200+.

**Gate 2** : ≥55% vs handcrafted → infra pattern jass fonctionne.

L'infra C++ + Python est transposable directement (board → Position,
patterns → géométrie draughts, training pipeline identique).
