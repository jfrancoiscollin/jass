# L3-PURE — axe de dose replay : clôture et succession de champion

Chaîne `home-0990` → `home-0993`, 27 juillet 2026. Premier écran de la campagne
dimensionné par une analyse de puissance explicite.

## Question

Le plan normatif prévoyait un croisement `replay {0 ; 25 %} × L2` après le
premier tri L2. Ce croisement était **déjà mesuré** : `M2` (dose 0), `REPLAY25`
(dose 25) et `TURNOVER` (dose 50) ont tous été entraînés à `L2=3e-5`, même
parent F2M, 2M records, d8, 8cf/Q00, WDL. L'axe n'était vierge qu'**au-delà de
50 %**, d'où le bras `REPLAY75` : 1,5M records époque F2M + 0,5M époque M2.

## Estimateur : vues additionnées

Rupture assumée avec les écrans précédents, justifiée par
[`L3_VIEW_AGREEMENT_AND_POWER_20260727.md`](L3_VIEW_AGREEMENT_AND_POWER_20260726.md) :
les vues Q00 et native estiment la même force, et exiger la supériorité dans
chacune séparément double le plancher de bruit sans ajouter d'information. Ici
les deux vues sont **additionnées** : 2 500 parties par cellule et par vue, soit
`n=5000` par matchup et un seuil de détection de **1,386 pp ≈ 9,6 Elo**, contre
17 à 21 Elo pour tous les écrans antérieurs.

Trois paires sont mesurées plutôt que deux. Le train `home-0992` ayant convergé
en **6 itérations seulement** — mécanique, puisque 75 % du corpus est l'époque du
parent lui-même — `REPLAY75` était attendu très proche de F2M, et la comparaison
`TURNOVER`/`F2M` ne pouvait donc pas être déduite par transitivité. Elle est
mesurée en direct.

## Résultats — `home-0993`, pool `17544078…`, 1 250 ouvertures

```text
vues additionnées, n=5000 par matchup
  REPLAY75 vs F2M        50,11 %  2464-83-2453   +0,76 Elo  IC95 [48,74 ; 51,48]  non établi
  REPLAY75 vs TURNOVER   47,77 %  2355-67-2578  -15,51 Elo  IC95 [46,39 ; 49,15]  RÉGRESSION ÉTABLIE
  TURNOVER vs F2M        51,98 %  2558-82-2360  +13,77 Elo  IC95 [50,61 ; 53,35]  SUPÉRIORITÉ ÉTABLIE
```

Les trois paires restent compatibles entre vues (`z = −1,84`, `+0,44`, `−1,06`),
ce qui valide l'estimateur additionné sur données fraîches.

## Conséquence 1 — l'axe de dose est clos, l'optimum est intérieur

| dose replay | modèle | contre TURNOVER |
|---|---|---|
| 0 % (`M2`) | `75ace3c0…` | inférieur |
| 25 % (`REPLAY25`) | `289047ff…` | inférieur (régression Q00 établie) |
| **50 % (`TURNOVER`)** | `b2c79b36…` | **optimum** |
| 75 % (`REPLAY75`) | `9b9b26d5…` | **inférieur, régression établie** |

La courbe monte de 0 à 50 % puis redescend : l'optimum est **intérieur**, pas au
bord. Le mécanisme du bras 75 % est transparent — sa loss holdout est la
meilleure des quatre (`0,443431`) parce qu'il ré-apprend les données de son
parent, et il n'est effectivement pas distinguable de F2M en force
(`50,11 %`). **La loss ne prédit toujours pas la force.**

`REPLAY75 ≈ F2M` était prédit avant le readout à partir des 6 itérations de
convergence ; la cellule `50,11 %` le confirme et sert de contrôle de sanité du
harnais.

## Conséquence 2 — `TURNOVER` dépasse le champion F2M

C'est le premier bras `L3-PURE` à établir sa supériorité sur le champion en
titre, dans une cellule **préenregistrée et dimensionnée pour cela** :

```text
home-0993, préenregistré, n=5000   51,98 %   +13,77 Elo   IC95 [50,61 ; 53,35]
```

Toutes les mesures antérieures de ce même couple, sur pools indépendants,
pointent dans le même sens et se consolident ainsi (**diagnostic de soutien**,
non préenregistré) :

```text
home-0978 q00    n=1000  52,10 %   +14,60 Elo
home-0978 native n=1000  51,15 %    +7,99 Elo
home-0980 q00    n=2000  50,35 %    +2,43 Elo
home-0980 native n=2000  50,90 %    +6,25 Elo
home-0993 q00    n=2500  52,72 %   +18,92 Elo
home-0993 native n=2500  51,24 %    +8,62 Elo
------------------------------------------------
CUMUL     n=11000  51,42 %  5565-183-5252  +9,89 Elo  IC95 [50,50 ; 52,35]
```

Six mesures sur six sont positives ; le cumul exclut 50 % avec une demi-largeur
d'intervalle de `0,926 pp`.

Pourquoi `home-0980` n'avait rien conclu : il mesurait `50,35/50,90 %` par vue
sur 3 000 parties, très en deçà de son propre seuil de détection d'alors. **Le
signal était là ; la puissance manquait.** C'est l'illustration directe de
l'analyse d'accord des vues.

## Ce que ce résultat n'autorise pas

Rien n'est promu : `promotion_authorized=false`, `automatic_next_job=null`.
Une succession de champion est une **promotion délibérée**, réservée à une revue
humaine explicite, comme l'a été `home-0965` pour F2M contre Gen2. Un tel bake
demanderait au minimum :

- une garde de non-régression contre Gen2, référence historique figée ;
- la conversion P3/P4 avec défenseur figé ;
- la couverture par bucket du corpus TURNOVER ;
- un pool indépendant supplémentaire, non dépensé.

Ces cellules n'ont **pas** été jouées ici : le compute a été délibérément
réalloué des cellules secondaires vers la puissance de la question causale.
C'est un arbitrage assumé, et il borne exactement ce que le résultat autorise à
dire.

## Préfixe immuable

```text
r2:jass-data/runs/home-0993-l3-pure-replay75-readout-v1/20260726T232409Z-64829307
```
