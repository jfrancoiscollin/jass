# L3-PURE — TURNOVER G2 : palier ou pente ?

Préenregistré le 27 juillet 2026, avant toute génération.

## La question, et pourquoi elle prime

`home-0993` a établi TURNOVER au-dessus de F2M, `+13,77 Elo` sur `n=5000`
préenregistré. Mais **TURNOVER est une seule génération**. Deux mondes restent
compatibles avec ce résultat :

- **palier** — la mémoire temporelle corrige un défaut ponctuel de `M2`, le gain
  est un décalage unique et itérer ne donnera rien ;
- **pente** — le renouvellement 50/50 est un régime d'entraînement durable, et
  chaque génération rapporte ~10 Elo. Cinq tours vaudraient alors +50 Elo.

Aucune autre expérience ouverte ne discrimine autant pour aussi peu : la recette
existe, le corpus source existe, et un seul run répond. C'est pourquoi elle
passe avant le croisement volume × mémoire et avant la génération dirigée par
la couverture.

## Recette — strictement celle de G1, décalée d'un cran

| facteur | G1 (`home-0977`) | **G2** |
|---|---|---|
| parent | F2M | **TURNOVER** |
| moitié mémoire | 1 M époque F2M | **1 M échantillonné du corpus de TURNOVER** |
| moitié fraîche | 1 M époque M2 | **1 M généré depuis TURNOVER** |
| volume | 2 000 000 | 2 000 000 |
| profondeur de jeu | d8 | d8 |
| géométrie / recherche | 8cf / Q00 | 8cf / Q00 |
| labels | WDL terminal, ply-caps exclus | identique |
| fit | L-BFGS, `L2=3e-5`, warm-start parent | identique |
| split | par ouverture, seed `577215` | identique |

Tout le reste est figé. Le seul facteur qui bouge est **le rang de génération**.

### Choix de protocole à expliciter

« La moitié mémoire » admet deux lectures : rejouer l'époque la plus récente
seulement, ou rejouer le corpus du parent. **G2 retient la seconde** : 1 M
échantillonné du corpus 2 M de TURNOVER lui-même.

C'est le seul choix qui rende la recette **auto-similaire** : à chaque
génération, le corpus garde la moitié de celui de son parent et ajoute la moitié
de frais. La mémoire décroît alors géométriquement — c'est exactement un tampon
de replay, et c'est ce qui donne un sens à la question « pente ». L'autre
lecture ne se répète pas à l'identique et ne permettrait pas de lire une pente.

## Chaîne réservée

1. **`home-0999`** — préflight : authentifie la porte de succession et
   l'identité de TURNOVER, reconstruit le corpus source, certifie un pool
   indépendant neuf, disjoint des seize pools déjà dépensés.
2. **`home-1000`** — génération + fit : 12 shards produisent 1 M positions
   fraîches depuis TURNOVER à d8 (`--gen-data-wdl`, `LABEL_DEPTH=4`,
   `--random-open-plies 8 --explore-eps 8 --explore-decay-plies 60`,
   `--pair-openings --drop-plycap`), mix 1:1 avec 1 M du corpus parent, split,
   puis fit `L2=3e-5`. L'optimiseur **doit converger réellement**.
3. **`home-1001`** — readout à vues additionnées contre **TURNOVER** (le parent,
   question causale) et contre **F2M** (contrôle de continuité de la pente).

## Sizing, ancré sur des durées mesurées

`home-0966bis` a généré 2 M positions en 12 shards et fitté 2 M records :
génération ≈ **17 min**, fit ≈ **33 min**, sur la même box HOME 16 CPU.

| étape | volume | ETA |
|---|---|---|
| préflight `0999` | pool 1500 + authentification | 6-10 min |
| génération `1000` | 1 M positions, 12 shards | ~9 min |
| mix + split `1000` | 2 M records | ~6 min |
| fit `1000` | 2 M records, ~200 itérations | ~33 min |
| readout `1001` | 4 cellules × 3000 parties/vue | ~80-110 min |

Total ≈ **2 h 20 à 2 h 50**, dont une seule heure avant de savoir si le modèle
converge.

## Règle de décision, préenregistrée

Le readout compare G2 à **TURNOVER**, vues additionnées, `n=6000` par matchup,
seuil de détection ~`1,27 pp` soit ~8,8 Elo.

- **pente confirmée** — borne basse à 95 % au-dessus de 50 % contre TURNOVER,
  sans régression établie contre F2M. Autorise G3, et seulement G3.
- **palier** — pas de supériorité établie contre TURNOVER, sans régression non
  plus. **La recette est close en itération** : le gain de G1 était ponctuel, et
  le compute doit aller au croisement volume × mémoire ou à la génération
  dirigée par la couverture.
- **régression** — borne haute sous 50 % contre TURNOVER. Ferme l'itération et
  ouvre une question neuve : pourquoi la recette se dégrade-t-elle en se
  répétant ?

Dans tous les cas : `promotion_authorized=false`, `automatic_next_job=null`.
Une pente confirmée ne promeut pas G2 ; elle justifie seulement de continuer.

## Puissance annoncée avant le run

À `n=6000` vues additionnées, un gain de génération de **+10 Elo** est
détectable confortablement, **+8,8 Elo** l'est tout juste, **+5 Elo** ne l'est
pas. Si la pente réelle est de l'ordre de +5 Elo par génération, ce run
conclura « palier » à tort.

C'est une limite assumée : porter le seuil à +5 Elo coûterait ~19 200 parties
par cellule, soit près de 4 h de jeu supplémentaires. **Le verdict « palier »
devra donc se lire « pas de pente d'au moins ~9 Elo par génération »**, et non
« aucune pente ». Cette formulation est imposée d'avance pour qu'elle ne puisse
pas être arrondie après coup.
