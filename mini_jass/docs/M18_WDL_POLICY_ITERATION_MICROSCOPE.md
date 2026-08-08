# M18 — microscope causal de la boucle WDL auto-améliorante

## Question scientifique

M14 a montré que la tête value peut apprendre lorsque la cible est exacte. M15
et M16 ont étudié des cibles alternatives. M17 vérifie enfin si plusieurs tours
de boucle composent. M18 se place un cran plus profond :

> Par quel mécanisme une boucle fondée uniquement sur les résultats W/D/L peut-elle
> améliorer progressivement la qualité de ses propres étiquettes, sans oracle ?

La boucle étudiée est la policy iteration implicite :

```text
évaluation E_k
  → recherche Search(E_k)
  → parties et WDL_k
  → entraînement de E_{k+1}
  → confrontation et sélection
  → nouveau générateur
```

L'oracle Mini-Jass ne participe jamais à cette chaîne. Il sert seulement de
microscope post-hoc pour mesurer si les WDL produits se rapprochent de la vérité.

## Pourquoi M17 ne suffit pas

M17 mesure une échelle de 1, 2, 4 et 8 générations. Une hausse éventuelle montre
que l'itération compose, mais ne permet pas d'identifier la cause. Une courbe
peut monter parce que :

- le générateur devient réellement meilleur et produit de meilleurs WDL ;
- le learner accumule simplement des mises à jour sur des données stationnaires ;
- la recherche transforme une évaluation faible en politique plus forte ;
- un gate de promotion évite des régressions ;
- la distribution des positions visitées devient seulement plus facile.

M18 introduit des contrôles causaux pour séparer ces explications.

## Les quatre bras

Tous les bras partent de la recette L1/M17 gelée, utilisent 8 générations, les
mêmes 5 graines fraîches et les mêmes schedules de positions de départ.

| Bras | Générateur des WDL | Recherche | Promotion | Question isolée |
|---|---|---|---|---|
| `evolving_arena_gate` | champion courant | recette M17 | arena uniquement | boucle complète, sans oracle causal |
| `frozen_generator` | modèle initial à chaque génération | recette M17 | arena uniquement | les données stationnaires suffisent-elles ? |
| `shallow_search` | champion courant | profondeur 1, budget inchanfé | arena uniquement | la recherche est-elle le cliquet ? |
| `forced_advance` | champion courant | recette M17 | toujours | le gate protège-t-il des régressions ? |

### Contrôle du générateur figé

Le learner peut encore être entraîné et promu, mais chaque nouvelle génération
de données est produite par une copie immuable du modèle initial. La différence
avec `evolving_arena_gate` isole donc le feedback :

```text
meilleur champion → meilleurs WDL → meilleur champion
```

### Contrôle de recherche

Le bras `shallow_search` conserve le même moteur, le même budget de nœuds, la
même policy target et les mêmes graines, mais limite le lookahead à une ply.
Il mesure le canal complet par lequel la recherche améliore le joueur qui produit
les étiquettes.

### Contrôle du gate

Le bras `forced_advance` remplace systématiquement le parent par le candidat.
Il montre si la sélection arena est un stabilisateur nécessaire ou si elle bloque
inutilement une amélioration cumulative.

## Une boucle réellement sans oracle

Le gate historique de `execute_loop` exige à la fois un progrès sur le jeu de
développement résolu et un succès arena. Ce serait incompatible avec la question
« comment Scan a-t-il appris sans oracle ? ».

M18 rend donc le test développement mathématiquement toujours vrai avec un seuil
inférieur à la plage possible du score, puis vérifie après chaque génération :

```text
provisional_advance == arena_pass
```

Dans `forced_advance`, les deux seuils sont rendus toujours vrais et chaque
génération doit avancer. L'oracle peut toujours calculer des métriques après coup,
mais aucune de ses valeurs ne peut modifier l'entraînement, une trajectoire ou le
choix du champion.

## Mesure primaire : probe fixe de qualité WDL

Comparer la précision des labels sur les trajectoires d'entraînement peut être
trompeur : un moteur différent visite des positions différentes.

M18 rejoue donc, à G0, G1, G2, G4 et G8, un probe hors entraînement avec :

- exactement les mêmes positions de départ ;
- exactement les mêmes graines ;
- le même nombre de parties ;
- la recherche propre au bras ;
- aucune lecture oracle pendant le jeu.

Après que toutes les parties sont terminées, l'oracle mesure sur les positions de
départ :

- taux d'accord W/D/L exact ;
- MAE WDL ;
- matrice de confusion vrai W/D/L → label W/D/L ;
- surtout les confusions `vrai W → D` et `vrai L → D`.

Les positions de départ sont appariées, donc une amélioration ne peut pas être
expliquée par une distribution plus facile.

## Métriques secondaires

Pour chaque génération et chaque graine :

- qualité WDL des données réellement consommées ;
- qualité WDL sur les seuls débuts de partie appariés ;
- précision de signe et masse optimale du champion déployé ;
- nombre et emplacement des promotions ;
- couverture des états/actions ;
- arena finale champion G8 contre modèle initial ;
- courbe de faux nuls parmi les positions réellement décisives.

## Contrastes préenregistrés

### 1. La boucle améliore-t-elle ses propres labels ?

```text
probe_exact(evolving, G8) - probe_exact(evolving, G0)
```

### 2. Le feedback du générateur est-il causal ?

```text
(probe_exact(evolving, G8) - probe_exact(evolving, G0))
- (probe_exact(frozen_generator, G8) - probe_exact(frozen_generator, G0))
```

### 3. La recherche est-elle le cliquet ?

```text
(probe_exact(evolving, G8) - probe_exact(evolving, G0))
- (probe_exact(shallow_search, G8) - probe_exact(shallow_search, G0))
```

### 4. Le gate stabilise-t-il ?

```text
(probe_exact(evolving, G8) - probe_exact(evolving, G0))
- (probe_exact(forced_advance, G8) - probe_exact(forced_advance, G0))
```

Ces trois contrôles utilisent une différence-de-différences : ils isolent ce que chaque mécanisme ajoute à la progression, au lieu de confondre la qualité initiale de la recherche avec la composition.

Le quatrième contraste est diagnostic : un forced arm supérieur ne nie pas la
boucle, mais indique que le gate historique est trop conservateur.

## Gate scientifique

Le résultat est **INCONCLUSIVE** si le bras principal n'avance pas réellement le
parent. Sinon, M18 passe uniquement si :

1. le gain G8−G0 est d'au moins 3 points et son IC95 apparié est entièrement positif ;
2. le bras évolutif dépasse le générateur figé d'au moins 2 points avec IC95 positif ;
3. le bras évolutif dépasse la recherche une-ply d'au moins 2 points avec IC95 positif ;
4. le champion final améliore value et policy sur le développement observateur ;
5. son score arena moyen contre le modèle initial dépasse 0,50 ;
6. les schedules de positions de départ sont identiques entre bras ;
7. les cinq runs de chaque bras se terminent sur CPX62.

Une réussite n'autorise qu'une réplication à graines fraîches. Aucun modèle M18
n'est promouvable, aucun changement Jass 10×10 n'est autorisé.

## Interprétation attendue

- **Evolving monte, frozen reste plat** : preuve de la boucle vertueuse endogène.
- **Evolving et frozen montent ensemble** : l'apprentissage compose, mais pas grâce
  à l'amélioration du générateur ; le volume/multi-update suffit.
- **Full bat shallow** : la recherche est bien le cliquet de policy improvement.
- **Forced régresse** : le gate arena stabilise la boucle.
- **Forced monte, gated reste plat** : le gate bloque l'itération ; il faut le
  recalibrer avant de conclure sur WDL.
- **Aucun bras ne monte** : la recette actuelle ne possède pas de boucle Scan-like ;
  il faudra alors tester accumulation de corpus, représentation ou bootstrap.
