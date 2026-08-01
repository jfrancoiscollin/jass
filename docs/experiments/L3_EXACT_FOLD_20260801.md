# Le fold exact — +17,1 Elo en changeant quelle symétrie on impose (2026-08-01)

**Résultat** : à corpus, parent, hyperparamètres, pile numérique et machine
identiques, plier le fit sur la symétrie **exacte** du damier plutôt que sur une
symétrie **approximative** vaut **+17,10 Elo**, IC95 `[+9,2 ; +25,0]` sur
**6000 parties**. Premier gain établi de la campagne après quatre axes
successivement négatifs ou plats.

Aucun changement de moteur, aucune feature nouvelle, aucun volume supplémentaire.
Le fichier produit reste un `.pjtw` 8cf standard.

## Comment on en est arrivé là

L'atlas `cpx62-1114` avait montré une perte **diffuse**, dans le jeu **calme**,
concentrée en ouverture et milieu, sans point chaud (cf.
[`L3_SCAN_BLIND_SPOT_ATLAS_20260801.md`](L3_SCAN_BLIND_SPOT_ATLAS_20260801.md)).
Signature d'une erreur systématique de faible amplitude, pas d'un trou localisé.

JFC a écarté la piste capacité : « Scan est 8cf donc on peut pousser notre éval
telle qu'elle ». Vérification dans le source de Scan (`eval.cpp`) :

```
const int P {2125820};                 // paramètres d'éval
var += pow(3, Pattern_Size) * 4;       // 531441 × 4 = 2 125 764
```

**Scan est 4 patterns, pas 8** — 2 125 764 poids de patterns + 56 extras, soit
`2 125 820 × 2 phases × 2 octets = 8 503 280 o`, exactement la taille de son
`data/eval` épinglé. Nous avons **8 patterns et 120 extras**, donc **2× sa
capacité de patterns**, pour un moteur qui joue à ~2500 FMJD. La conclusion de
JFC était juste, et renforcée : la capacité n'est pas la contrainte.

Le facteur 2 s'explique : nos 8 patterns sont **les 4 colonnes de Scan
dupliquées haut/bas**, appariées exactement sous le miroir FMJD (p0↔p7, p1↔p6,
p2↔p5, p3↔p4). Scan impose la relation par construction — index signé,
contributions ±1. Nous la laissions s'apprendre.

## Le défaut, et il était à l'envers

`pattern_jass/tools/symmetry.py` le dit dans son propre docstring :

> *the exact symmetry is rot180 ∘ colour-swap … **cs/rot alone are approximate**
> (men have a direction) but pool data*

Mesuré sur TURNOVER, entraîné avec `--color-fold` :

| symétrie | statut réel | dans TURNOVER |
|---|---|---:|
| `cs` seule (couleurs sur place) | **approximative** | imposée **exactement** — 0,0000 % |
| `rot180∘cs` | **exacte** | violée à **25,80 %** |

**On imposait structurellement la contrainte fausse et on laissait la vraie
s'apprendre.** Un quart de l'énergie des poids affirmait qu'une même
configuration vaut différemment selon le bout du plateau d'où on la regarde —
ce que les règles interdisent. Et c'est exactement la signature que l'atlas
avait relevée : faible amplitude, systématique, partout dans le jeu calme.

## Ce que le correctif n'est PAS

⚠️ **Ce n'est pas un gain de capacité.** Le log de `home-0977` montre que
`--color-fold` atteint déjà `TB = 2 125 768` : les deux folds mutualisent le
**même nombre** de configurations par poids. Ce qui change est **ce qu'ils
mutualisent** — des positions réellement équivalentes au lieu de positions qui
ne le sont pas. L'effet attendu était la disparition d'un biais systématique, pas
une réduction de variance, et c'est ce qui a été mesuré.

`--exact-fold` plie sur le groupe à deux éléments `{id, rot180∘cs}` : 2 125 764
poids canoniques pour la géométrie 8cf, soit exactement le compte de Scan.

## Le protocole, et pourquoi il a un bras de contrôle

`cpx62-1117` a refitté **le corpus de TURNOVER lui-même** (2 000 000 positions,
holdout 199 204, parent `be675b6c…`), en **deux bras dans le même
environnement** :

- **CONTROL** — `--color-fold`, la recette de TURNOVER ;
- **EXACT** — `--exact-fold`.

Tout le reste identique. Comparer EXACT à l'artefact TURNOVER d'origine aurait
mélangé l'effet du fold avec la dérive d'environnement : l'épinglage numérique
historique (numpy 1.26.4) n'est plus servi pour le Python de cpx62, et le job a
résolu numpy 2.5.1 / scipy 1.18.0. Le bras de contrôle absorbe exactement ce
confounder.

| | rot180∘cs (exacte) | cs seule (approx) | holdout | itérations | taille .gz |
|---|---:|---:|---:|---:|---:|
| CONTROL | **25,15 %** | 0,0000 % | 0,443306 | 95 | 1 436 Ko |
| EXACT | **0,0000 %** | 44,67 % | 0,442898 | 141 | **937 Ko** |

Le control reproduit l'inversion de TURNOVER (25,8 %), confirmant que le bras de
référence est bien la recette d'origine. Le modèle exact **compresse 35 % mieux**
— cohérent avec deux moitiés qui sont l'image l'une de l'autre.

## La porte

`cpx62-1118`, appariée, deux vues (profondeur 9 fixe et movetime 0,1), 1500
ouvertures indépendantes, compteurs bruts sommés :

| | |
|---|---:|
| n | 6 000 |
| EXACT | 2546 W / 1203 D / 2251 L |
| taux | 0,5246 — IC95 `[0,5133 ; 0,5359]` |
| **Elo** | **+17,10** — IC95 `[+9,2 ; +25,0]` |

Verdict `EXACT_FOLD_BEATS_CONTROL_HUMAN_REVIEW`.

⚠️ **EGDB était absent de la box** : la comparaison interne entre les deux bras
reste valide (ils partagent le binaire), mais cet Elo **n'est pas comparable en
absolu** aux portes antérieures qui tournaient avec la base de finales.

⚠️ Le holdout n'a **pas** servi d'arbitre. L'écart y est de 0,0004, et ce projet
a mesuré quatre fois que la perte en holdout ne prédit pas la force.

## La passe on-policy — négative (`cpx62-1119` / `cpx62-1120`)

Le corpus refitté avait été engendré par l'ancienne politique. `cpx62-1119` a
fermé la boucle : le modèle exact a joué ses propres 2 000 000 de positions
(12 producteurs, d8, mêmes paramètres de génération que `l3-pure-m2-train-v1`),
puis a été refitté dessus sous `--exact-fold` — sortie exactement antisymétrique,
481 itérations, holdout 0,450177.

Porte `cpx62-1120`, ONPOLICY contre son propre parent EXACT, même forme deux
vues :

| | |
|---|---:|
| n | 6 000 |
| ONPOLICY | 2261 W / 1320 D / 2419 L |
| taux | 0,4868 — IC95 `[0,4757 ; 0,4980]` |
| **Elo** | **−9,15** — IC95 `[−16,9 ; −1,4]` |

Verdict `A_BELOW_B`. **Perte établie, pas un plat** : la borne haute est sous
zéro.

Le holdout de la passe on-policy (0,450177) n'est **pas** comparable à celui du
refit (0,442898) — corpus différents, distributions différentes.

Un seul tour on-policy depuis le modèle exact **dégrade**. Ce résultat s'aligne
sur l'histoire de la campagne : les axes de *mise en forme des données* échouent
les uns après les autres, et le seul gain acquis vient d'une **correction de
justesse**, pas d'un tour de données de plus. Ce qui ne dit pas qu'aucune boucle
on-policy ne peut marcher — seulement que celle-ci, à ce volume et à ce
paramétrage, coûte.

## Ce qui reste ouvert

- **Promotion non demandée.** Le modèle exact bat son contrôle, pas le champion
  courant : TURNOVER a été ajusté sous une autre pile numérique et joue avec
  EGDB dans les portes de succession. Une porte EXACT contre TURNOVER, avec
  EGDB, reste à faire avant toute question de champion.
- **4cf en dur dans le moteur** : purement une optimisation mémoire/cache
  maintenant que le point statistique est acquis. Rien ne l'exige.
- **Les autres folds** : `--full-fold` existe et ajoute translation et
  réflexion. La réflexion gauche-droite est **exacte** (signe +1 d'après le
  docstring) ; la translation ne l'est pas. Un fold `{id, rot180∘cs, LR,
  LR∘rot180∘cs}` serait le prochain palier entièrement vrai.

## Artefacts

- refit deux bras : `r2:jass-data/runs/cpx62-1117-l3-exact-fold-refit-v1/20260731T235446Z-970f14de`
- porte : `r2:jass-data/runs/cpx62-1118-l3-exact-fold-gate-v1/`
