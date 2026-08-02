# `--hier-l2` seul — règle de décision PRÉENREGISTRÉE

Écrit le 2 août 2026 **avant tout refit HIER sous le protocole courant et avant
toute porte**. Aucun chiffre issu de cette expérience n'a été vu au moment où
les bras et la règle ci-dessous ont été fixés.

## La question

Dans le fit courant, le ridge ordinaire ajoute `l2·||w||²/2` : sans donnée, un
bucket est donc ramené vers zéro. `--hier-l2` ajoute un second terme qui ramène
chaque bucket vers la moyenne des buckets retenus de son pattern, séparément en
milieu et en fin de partie. Il **ne remplace pas** le ridge ordinaire et ne
reprend pas les poids du champion.

La question de ce test est strictement causale : à recette EXACT inchangée,
l'ajout d'un backoff de force égale au ridge (`hier_l2 = l2 = 3e-5`) améliore-t-il
la force ?

## Les deux bras du refit

| propriété | CONTROL | HIER |
|---|---|---|
| corpus / split | TURNOVER 1:1, `2 000 000` / holdout `199 204` | identique |
| parent / départ | F2M, `--warm-start` | identique |
| fold | `--exact-fold` | identique |
| features | 8cf, `n_ext = 120` | identique |
| `l2` | `3e-5` | `3e-5` |
| `hier_l2` | `0` | **`3e-5`** |
| L-BFGS | maxiter `1000`, maxcor `20`, gtol `1e-4` | identique |

Le coefficient historique de `cpx62-0517` n'est pas repris : ses trois cellules
utilisaient `hier_l2 = 1e-3`, `3e-3` ou `1e-2` (33 à 333 fois le ridge) et deux
d'entre elles changeaient aussi `l2`. Leur résultat négatif ne répond donc pas à
ce bouton unique sous EXACT, mais interdit de choisir a posteriori une dose parmi
plusieurs. Ici il n'y a **qu'une dose**, fixée avant les chiffres.

Ce refit est une exception expérimentale à la recette de production centrée sur
PRIOR : il mesure HIER **seul** sur le même parent que le test du prior. Un HIER
positif n'est pas un candidat à la succession ; il autorise seulement une autre
expérience préenregistrée, `PRIOR+HIER` contre `PRIOR`, dans la représentation
retenue après la conclusion du test king-aware.

## Porte et taille

- pool immuable : les `3 000` ouvertures de `cpx62-1154`, une partie par couleur ;
- deux vues co-primaires : `q00` à profondeur 9 et `native` à movetime 0,1 s ;
- `6 000` parties par vue, compteurs bruts additionnés, donc **`n = 12 000`** ;
- A = HIER, B = CONTROL ; même binaire EXACT et mêmes paramètres de recherche
  dans chaque vue ;
- l'intervalle est calculé sur les compteurs bruts `wins_a`, `draws`, `wins_b`.

À `n=12 000`, le sizing enregistré dans le backlog donne environ **84 % de
puissance pour +9 Elo**. Le test n'est pas dimensionné pour établir proprement
un effet beaucoup plus petit ; augmenter `--pairs` sur ces mêmes ouvertures ne
créerait que des doublons déterministes.

## Règle de décision, fixée avant les chiffres

1. **Réouverture** de la famille HIER si et seulement si l'IC95 combiné du score
   de HIER est entièrement au-dessus de `0,5` **et** si les deux estimations de
   vue sont chacune strictement au-dessus de `0,5`.
2. **Régression établie** si l'IC95 combiné est entièrement sous `0,5`.
3. Tout autre résultat est **absence de gain établi** et ferme le test HIER seul
   sous cette dose et ce protocole. Il n'y a ni seconde dose opportuniste ni
   prolongation automatique.
4. Une réouverture autorise uniquement la préinscription de `PRIOR+HIER` contre
   `PRIOR`. **Aucune promotion**, aucune continuation et aucun job de succession
   ne sont autorisés par cette porte.

Le holdout, le nombre d'itérations et la norme du gradient sont des contrôles de
validité du fit. Ils ne remplacent pas la porte de force et ne peuvent pas
renverser sa règle.

## Séquencement et coordination

La préparation du refit, de la porte et du readout peut être poussée pendant le
fit king-aware de Claude. Aucun budget scientifique HIER n'est engagé avant son
verdict et un go explicite de JFC. Les jobs éventuels seront exclusivement
`home-12xx-codex-*`, avec pin immuable visible `at-<sha8>` ; aucun template en
vol (`l3-exact-fold-refit-v1.sh`, `l3-model-gate-v1.sh`,
`l3-succession-guards-v1.sh`) n'est modifié.
