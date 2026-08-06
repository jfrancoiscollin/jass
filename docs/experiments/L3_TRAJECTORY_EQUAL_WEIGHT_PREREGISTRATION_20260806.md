# L3 — TRAJ-EQUAL : une partie, une masse de gradient

> Date : 6 août 2026
> Statut : préenregistré avant exécution ; mise en œuvre autorisée par JFC le
> 6 août 2026 ; mise en file suspendue à la validation du sizing ré-ancré ;
> aucun résultat TRAJ-EQUAL consulté.
> Promotion : interdite ; aucun enchaînement automatique.

## 1. Question

À positions, étiquettes, ordre, split, features, parent, géométrie et recette de
fit identiques, donner la même masse totale de vraisemblance à chaque partie
représentée produit-il un modèle plus fort que le poids uniforme par record ?

Le générateur conserve historiquement une position avec une probabilité proche
de `1/4`. Sur `home-1311`, M1 compte 12 000 000 records pour 374 818 parties,
soit environ 32 records par partie. Après conversion des WDL en POV noir par le
trainer, les records d'une partie portent tous le même résultat terminal. La
loss actuelle donne donc mécaniquement plus de masse aux parties qui ont plus de
records retenus.

Ce facteur était explicitement encore ouvert dans `L3_PURE_PLAN.md` :
« échantillonnage ≈1 ply sur 4 — à instrumenter puis tester ». JSM2 fournit
désormais le `game_id` aligné nécessaire pour l'isoler après coup.

## 2. Facteur unique

Pour une partie représentée `g`, soit `m_g` le nombre de ses records dans la
partie TRAIN du corpus retenu.

Contrôle `ROW` :

```text
w(g,i) = 1
```

`ROW` reçoit explicitement ce vecteur de uns par la même interface
`--sample-weights` que `GAME`. Le trainer certifie ensuite
`uniform_after_normalization=true` et conserve `sw_all=None` : l'objectif et
l'ordre de sommation restent byte-compatibles avec le chemin historique non
pondéré.

Traitement `GAME` :

```text
w_raw(g,i) = 1 / m_g
```

`train_stream.py` normalise ensuite les poids TRAIN à moyenne 1. La masse
normalisée de chaque partie vaut donc exactement `N_train / G_train`, tandis que
la somme totale des poids reste `N_train`. L'échelle de la likelihood et la
force relative du `l2`/prior restent ainsi celles du contrôle.

Les lignes HOLDOUT reçoivent un poids brut neutre `1`. Le trainer n'applique
jamais les poids au holdout.

⚠️ `m_g` désigne les records **retenus dans le corpus de 2 M**, pas tous les
records historiques de la partie dans le pool source de 12 M. Le montage ne
prétend pas reconstruire les lignes écartées par le sous-échantillonnage. Les
deux bras lisent exactement le même fichier retenu ; le contraste porte sur la
masse donnée à chaque partie qui y est représentée.

## 3. Invariants et gardes fail-closed

Les deux bras partagent :

- le même JNNW de 2 M records et le même JSM2, hashes publiés ;
- le même ordre et la même frontière train/holdout par `opening_id` ;
- le même dump FEAT, partagé physiquement ;
- WDL terminal, `exact-fold`, tempo-stage, 8cf/Q00 ;
- le même artefact parent authentifié que les refits M3/L2LOW comme
  `--prior-mean`, avec `--prior-decay 0` ;
- `l2=1e-5`, `lbfgs-gtol=1e-4`, même `max_iter`, `maxcor`, chunk et pile
  NumPy/SciPy ;
- le même prune map, puisque les positions sont identiques.

Le job échoue avant le fit si :

1. le sidecar n'est pas JSM2 ou les comptes JNNW/JSM2 divergent ;
2. un `game_id` ou un `opening_id` traverse la frontière train/holdout ;
3. le contexte JSM2 varie à l'intérieur d'une partie ;
4. un poids n'est pas `float32`, fini et strictement positif ;
5. après la normalisation prévue, les masses totales des parties ne sont pas
   égales dans la tolérance float32 ;
6. un fit ne termine pas sur `PGTOL` ;
7. `ROW` n'emprunte pas le chemin historique exact ou `GAME` n'active pas la
   pondération non uniforme ;
8. les deux modèles sont byte-identiques.

Le rapport obligatoire publie notamment : distribution des records retenus par
partie, masse portée par les 10 % de parties les plus longues, distributions de
résultats au niveau parties et au niveau records, longueur des parties par
résultat, histogramme du nombre de parties par ouverture, plage des poids et
erreur maximale de masse après normalisation.

Ces diagnostics expliquent le mécanisme ; aucun ne sélectionne un bras.

## 4. Réplication fixée avant lecture

Les deux réplications sont décidées avant le premier résultat :

| réplication | pool d'entraînement | graine génération | graine sous-échantillonnage | volume retenu |
|---|---|---:|---:|---:|
| A | `home-1311` | 1618034 | 3141592 | 2 M |
| B | `home-1312` | 2718281 | 2236067 | 2 M |

Les pools proviennent de parties indépendantes. Le même algorithme et le même
split sont appliqués aux deux ; les graines de sous-échantillonnage distinctes
sont fixées ci-dessus. Chaque réplication produit `ROW` et `GAME`, puis un job
de porte séparé oppose `GAME - ROW` sur des ouvertures d'évaluation appariées :
`big3000` pour A, `big3000b` pour B, ensembles dont la disjonction a déjà été
vérifiée. Les deux vues restent Q00 et cadence native.

Les deux réplications sont exécutées même si A est plate ou négative : il n'y a
qu'une hypothèse, aucune sélection de cellule, et l'objectif est précisément de
ne plus présenter un pool unique comme estimation de l'effet.

## 5. Règle de décision

Le readout autoritatif est celui de `l3-model-gate-v1.sh`, avec le posterior de
la porte A utilisé comme prior de la porte B. Il doit vérifier la disjonction des
pools et la garde d'hétérogénéité.

- **signal établi** : pools compatibles et `P(Elo > 0) > 95 %` après chaînage ;
- **rejet** : effet combiné négatif ou contradiction des pools ;
- **non concluant** : tout autre résultat.

Les probabilités `P(Elo > 0/3/5/10/17)` et les IC95 restent toutes publiées.
Un petit effet positif peut être réel sans constituer l'ingrédient dominant :
la taille de l'effet est interprétée séparément de son signe.

Même en cas de signal :

```text
promotion_authorized=false
automatic_next_job=null
```

Une confirmation à 12 M et toute modification du sampler de génération exigent
un nouveau go et un nouveau préenregistrement. Aucun exposant intermédiaire
(`1/sqrt(m_g)`, `1/m_g^alpha`) n'est autorisé si le contraste binaire est plat.

## 6. Sizing et ordre dans Signal Factory

Sur instruction explicite de JFC, la box cible est **HOME**, malgré le défaut
cpx62 du registre opérationnel. La pile numérique est exigée à `current` dans
les deux réplications. Ancres mesurées sur cette box : `home-1314`, même double
fit 2 M, a duré **7 h 36 min 28 s** ; `home-1315`, porte à 12 000 parties, a
duré **1 h 03 min 55 s**. TRAJ-EQUAL retire un build EGDB et le relabel de
`1314`, mais conserve par prudence son temps total comme borne :

- refit `ROW` + `GAME` d'un pool : **≤ 7 h 40** ;
- porte d'un pool : **~1 h 05** ;
- total par pool : **~8 h 45** ; deux pools séquentiels : **~17 h 30**.

Il n'y a ni génération ni shard ; le `nproc` réel imprimé par le job ne change
pas le volume et sert uniquement au build. Chaque fit garde un timeout de 6 h,
le job complet un timeout de 12 h, et aucune seconde réplication n'est lancée
automatiquement par la première.

TRAJ-EQUAL est une nouvelle cellule de **validation M3**, pas M4 : elle valide
contre l'Elo une propriété mesurable de la structure du corpus sans composer ni
générer un nouveau corpus. Elle arrive après les résultats plats de C2 sur deux
pools (`+3,04`, puis `−1,01`), de C1+C2 (`−2,63`) et de NB0 (`−2,17`).

L'expérience ne rouvre aucune de ces cellules. Elle teste si l'unité de loss
masque le signal des trajectoires déjà produites. Le changement de professeur
vers un mélange Scan/self-play reste une hypothèse distincte et exige son propre
A/B.

## 7. Implémentation

- poids et rapport : `jobs/tools/l3_trajectory_equal_weights.py` ;
- tests : `jobs/tests/test_l3_trajectory_equal_weights.py` ;
- fit A/B d'un pool : `jobs/templates/l3-trajectory-equal-ab-refit-v1.sh` ;
- porte et chaînage : `jobs/templates/l3-model-gate-v1.sh`.
