# L3 — accord des vues Q00/native et puissance réelle des écrans

Analyse rétrospective du 26 juillet 2026, conduite **entièrement sur les
cellules de force déjà publiées dans l'object store**. Aucune partie nouvelle
n'a été jouée, aucun verdict passé n'est modifié.

Origine : au cours de l'écran L2, la vue native a porté seule le signal
directionnel de `home-0987` (+10,1 Elo) puis s'est effondrée en `home-0989`
(−2,3 Elo), pendant que la vue Q00 faisait le chemin inverse. Il fallait savoir
si les deux vues mesurent deux choses différentes, ou la même chose bruitée.

## Corpus analysé

65 cellules de force issues de douze runs (`home-0963` à `home-0989`), dont
**31 matchups mesurés dans les deux vues sur le même pool d'ouvertures**, dans
des tailles de 400 à 2 000 parties.

## Résultat 1 — les deux vues mesurent la même chose

| grandeur | valeur |
|---|---|
| écart moyen `native − Q00` | `+0,25 pp` |
| écart médian | `+0,55 pp` |
| écart-type de l'écart | `2,03 pp` |
| corrélation Q00 / native | **`r = +0,885`** |
| accord de signe (même côté de 50 %) | 25/31 = 81 % |
| taux de nulles moyen | Q00 `1,35 %`, native `1,58 %` |

Test formel, en normalisant chaque écart par sa propre erreur type :

```text
z moyen        = +0,143      (0 attendu s'il n'y a pas de biais systématique)
variance des z =  0,766      (1 attendu si l'écart n'est que du bruit)
chi2           = 24,4 sur 31 ddl   → chi2/ddl = 0,787   → p ≈ 0,88
```

**Aucun effet de vue n'est détectable.** La dispersion observée entre Q00 et
native est intégralement compatible avec le bruit d'échantillonnage, et se situe
même légèrement en dessous. Les deux vues estiment la même force sous-jacente.

## Résultat 2 — la vue native n'est pas reproductible, la Q00 l'est

`home-0986` et `home-0987` ont joué **les mêmes modèles sur le même pool** :

| bras | vue | 0986 → 0987 | écart |
|---|---|---|---|
| `L2_1E5` | Q00 | 50,15 % → 50,15 % | **identique au bit près** |
| `L2_1E5` | native | 53,00 % → 51,45 % | `1,55 pp` |
| `L2_1E4` | Q00 | 47,45 % → 47,45 % | **identique au bit près** |
| `L2_1E4` | native | 48,30 % → 46,40 % | `1,90 pp` |

L'erreur type binomiale à `n=1000` vaut `1,58 pp`. La vue native, **à entrées
strictement identiques**, se déplace donc d'autant que l'erreur
d'échantillonnage complète : son indéterminisme `movetime` injecte à lui seul
un bruit comparable à celui du tirage des parties. La vue Q00, à profondeur
fixe, est exactement reproductible.

Conséquence : à budget de parties égal, **Q00 est un estimateur strictement
moins bruité que native**. La vue native ne se justifie que comme condition de
jeu réaliste, jamais comme arbitre de précision.

## Résultat 3 — la règle « les deux vues » double le plancher de bruit

Les protocoles exigeaient jusqu'ici qu'un bras établisse sa supériorité
**séparément dans chaque vue**. Puisque les vues mesurent la même chose, cette
règle n'ajoute aucune information : elle impose deux fois le même test à moitié
moins de données chacun, au lieu d'un test sur l'ensemble.

Additionner les vues est statistiquement légitime et resserre l'intervalle d'un
facteur `√2`. Vérification post-hoc sur `L2_1E5` contre son contrôle — **cette
lecture ne rouvre aucun verdict, elle mesure le coût de la règle** :

```text
0987  Q00                n=1000  50,15 %  IC95 [47,09 ; 53,21]
0987  native             n=1000  51,45 %  IC95 [48,38 ; 54,52]
0987  vues additionnées  n=2000  50,80 %  IC95 [48,63 ; 52,97]
0989  Q00                n=2000  53,02 %  IC95 [50,86 ; 55,19]   établie
0989  native             n=2000  49,68 %  IC95 [47,51 ; 51,84]
0989  vues additionnées  n=4000  51,35 %  IC95 [49,82 ; 52,88]
tout cumulé              n=6000  51,17 %  IC95 [49,91 ; 52,42]   NON établie
```

Sur 6 000 parties, l'estimateur le plus puissant disponible **ne conclut pas
davantage** : la clôture du facteur L2 sur `3e-5` est confirmée, pas fragilisée.
La règle préenregistrée et l'estimateur efficace donnent ici la même réponse.

## Résultat 4 — la puissance réelle de nos écrans

Parties par cellule nécessaires pour qu'une borne basse à 95 % franchisse 50 % :

| effet vrai | Elo | `n` en une vue | `n` réparti sur deux vues |
|---:|---:|---:|---:|
| 0,5 % | ~3,5 | 38 416 | 19 208 |
| 1,0 % | ~7 | 9 604 | 4 802 |
| 1,5 % | ~10 | 4 269 | 2 135 |
| 2,0 % | ~14 | 2 401 | 1 201 |
| 2,5 % | ~17 | 1 537 | 769 |
| 3,0 % | ~21 | 1 068 | 534 |

Nos écrans tournent à `n=1000` par cellule et par vue. **Ils ne peuvent donc
établir qu'un effet d'environ 2,5 à 3 %, soit 17 à 21 Elo.** Tout gain réel
inférieur est invisible pour eux.

C'est la relecture la plus importante de la campagne : les verdicts
`M2_PLATEAU`, `D10_PLATEAU`, `TURNOVER_DIRECTIONAL`, `REPLAY25_DOSE_CLOSED` et
`L2_NOT_REPLICATED` signifient **« aucun lead détectable à notre puissance »**,
et non « aucun effet ». Une lignée qui progresse par paliers de 5 à 10 Elo
resterait entièrement sous notre seuil de détection.

## Conséquences opérationnelles

1. **Additionner les vues** plutôt qu'exiger la supériorité dans chacune : même
   compute, intervalle `√2` fois plus serré. Les deux vues restent jouées, car
   Q00 fixe la précision et native atteste la condition réelle.
2. **Dimensionner par la puissance**, pas par habitude : annoncer, avant chaque
   écran, le plus petit effet détectable à `n` donné.
3. **Ne plus écrire « plateau » quand on veut dire « rien de détectable à
   17 Elo près »** ; publier le seuil avec le verdict.
4. **Préférer Q00 pour arbitrer** et native pour garde-fou de non-régression,
   la native ne se reproduisant pas à entrées identiques.
5. Un gain de 1 % (~7 Elo) demande environ **4 800 parties par cellule** vues
   additionnées : c'est atteignable en une heure sur HOME, et c'est le budget
   qu'exige toute question désormais posée près du champion.

## Reproduction

L'analyse relit les artefacts `artefacts/force/*.json` des runs `home-0963` à
`home-0989` dans `r2:jass-data`. Elle est déterministe et ne dépend d'aucun
état local.
