# Jass MegaCorpus — bras D et comparaison A/B/C/D

Date : 2026-08-14. Statut : préenregistré avant le fit D et avant toute partie
de comparaison A/B/C/D.

## Question et bras opérationnels

Les trois premiers bras proviennent du fit comparatif déjà scellé :

| bras | données | rôle causal |
|---|---|---|
| A `CURRENT_2M` | TURNOVER 2M + CONTEXT_30 | référence récente retenue |
| B `MEGA_EQ_2M` | UNIFORM post-fix, échantillon par parties ≈2M | corpus à volume égal |
| C `MEGA_FULL_4M` | même source, échantillon imbriqué ≈4M | contraste de volume |
| D `C_PRIOR_THEN_CURRENT_2M` | Current, avec C comme prior | préentraînement puis recentrage |

PatternEval est un modèle linéaire convexe. Un simple warm-start depuis C,
optimisé jusqu'à convergence avec la même ridge centrée en zéro, retournerait à
l'optimum de A et ne mesurerait aucune mémoire du préentraînement. D change donc
explicitement le prior, sans changer l'architecture ni les données Current :

```text
L_D(w) = CE(Current CONTEXT_30 ; w) + 0.5 × 1e-5 × ||w - C||²
```

Le fit conserve exact-fold 8cf, tempo-stage, 120 extras, L-BFGS maxcor 20,
`gtol=1e-4`, `maxiter=2000`, chunk 20 000 et le holdout par ouverture. Il doit
converger ; un budget artificiellement court ne peut pas fabriquer l'effet D.

## Readout statique commun

Les quatre modèles sont évalués sur le même holdout Current, disjoint du train
par `opening_id`, avec deux cibles diagnostiques : CONTEXT_30 Current et W/D/L
terminal. Les différences de loss sont accompagnées d'une IC95 bootstrap par
ouverture. Cette lecture décrit le mécanisme, mais ne sélectionne aucun modèle.

Contrastes causaux primaires :

- B − A : changement de corpus à volume approximativement égal ;
- C − B : volume imbriqué, même source et même règle d'échantillonnage ;
- D − A : valeur du curriculum Mega puis Current ;
- D − C : valeur du recentrage Current après Mega.

Contrastes secondaires : C − A et D − B. Un effet positif signifie ici une
loss plus faible pour le premier bras.

## Force jouée primaire

La force utilise les 250 premières ouvertures non commentées d'un pool
indépendant immuable de 500 ouvertures, dont le SHA source est vérifié. Chaque
ouverture est jouée avec couleurs inversées. Les six contrastes sont mesurés
dans deux vues identiques pour les deux joueurs : Q00 à profondeur 9 et native
à 0,1 seconde par coup.

Chaque contraste contient 500 parties. L'IC95 primaire rééchantillonne les
ouvertures, et non les parties prises comme indépendantes, afin de conserver le
couplage des couleurs. Le readout publie aussi le score agrégé historique.

Tout point estimé positif est conservé comme expérience positive, même si son
IC recouvre 0,5. Un gain est dit établi uniquement si la borne basse de l'IC
par ouverture dépasse 0,5 dans les deux vues. Symétriquement, une régression
est établie uniquement si la borne haute est sous 0,5 dans les deux vues. Les
résultats statiques ne peuvent pas sauver une régression de force.

## Garde-fous

- aucun `frozen_test` n'est lu ;
- aucun nouveau self-play n'est généré ;
- mêmes ouvertures, moteur, paramètres et budgets pour les deux joueurs ;
- aucune promotion automatique ;
- aucune sélection post-hoc de demi-vie, de prior ou de sous-cohorte ;
- B/C ne prétendent pas tester une pondération par récence : le catalogue
  authentifié exploitable ne contient ici qu'une source générale post-fix.

Le verdict terminal attendu est
`JASS_MEGACORPUS_ABCD_COMPARISONS_READY`. Il publie séparément la direction,
l'incertitude et le statut établi/non établi de chaque mécanisme.
