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

### ⚠️ CE RÉSULTAT NE DIT PAS « l'on-policy dégrade » — j'ai changé DEUX facteurs

Question de JFC : *un meilleur générateur devrait au pire produire des données
aussi bonnes, pas pires.* En vérifiant, le protocole ne tient pas.

Le corpus de TURNOVER n'est **pas** du self-play frais. C'est un **mélange 1:1**
(`selfplay_frontier mix --source PARENT f2m 1 --source FRESH m2-d8 1`), soit
**50 % mémoire / 50 % frais** — c'est l'identité même du champion, « turnover »
désignant ce roulement temporel, et il a été promu *parce que* ce mélange battait
les alternatives.

Ma passe on-policy est passée à **100 % frais, 0 % mémoire**. Deux facteurs ont
donc changé : le modèle générateur (ce que je voulais mesurer) **et** la
composition du corpus (ce que je n'ai pas vu changer).

Ce second facteur est connu et documenté : la fiche VOL8M de
`PROJECT_RESULTS` §5.2 liste explicitement « frais/mémoire 67/33 vs 50/50 » parmi
les quatre écarts qui rendent SON résultat non concluant. Même faute, en plus
extrême.

**Énoncé correct** : remplacer le mélange 50/50 par du frais pur issu d'un seul
modèle coûte **−9,15 Elo**. L'hypothèse « un générateur plus fort aide » reste
**non testée**.

### Ce que la mesure écarte quand même

Le mécanisme le plus intuitif — jeu plus fort → plus de nulles → moins de signal
— est **réfuté par les données** :

| corpus | loss | nulles | win |
|---|---:|---:|---:|
| TURNOVER (mélange 50/50) | 39,33 % | **21,41 %** | 39,26 % |
| on-policy (100 % frais, EXACT) | 40,75 % | **18,06 %** | 41,20 % |

Le corpus on-policy est **plus décisif**, pas plus nul. L'explication restante la
plus plausible est la **diversité** : un mélange de deux générations couvre des
régions qu'un modèle seul, plus déterministe, ne visite plus — et l'éval sert aux
**feuilles de la recherche**, donc sur une distribution bien plus large que la
trajectoire jouée.

### L'expérience qui testerait vraiment la question

Garder la recette turnover **et** ne changer que le générateur : 1 M frais issu
d'EXACT mélangé 1:1 avec la moitié mémoire existante, fit sous `--exact-fold`,
porte contre EXACT. Un seul facteur bouge.

## Contre le champion réel — `cpx62-1121`

La porte `1118` isole le fold proprement mais ne dit rien de ce qu'on expédie.
EXACT contre **TURNOVER**, le champion courant, même binaire, même forme :

| | |
|---|---:|
| n | 6 000 |
| EXACT | 2487 W / 1256 D / 2257 L |
| taux | 0,5192 — IC95 `[0,5079 ; 0,5304]` |
| **Elo** | **+13,32** — IC95 `[+5,5 ; +21,2]` |

Verdict `A_BEATS_B_HUMAN_REVIEW`. Borne basse au-dessus de zéro : **gain établi
contre le champion**, pas seulement contre un bras de contrôle.

Les trois mesures sont cohérentes entre elles : +17,1 contre CONTROL, +13,3
contre TURNOVER. L'écart de ~4 Elo entre les deux références est ce qu'on attend
si CONTROL est marginalement plus faible que TURNOVER — pile numérique
différente, et 95 itérations contre 204 à l'origine.

⚠️ Ce n'est **pas** une porte de succession : EGDB était absent, donc l'Elo n'est
pas comparable en absolu aux portes de promotion antérieures, qui tournaient avec
la base de finales. **Candidat à promotion, promotion non demandée** — c'est un
go explicite de JFC, et il se prendrait sur une porte avec EGDB.

## Ce qui reste ouvert

- **Promotion : candidat, non demandée.** EXACT bat TURNOVER de +13,3, mais sans
  EGDB. Rejouer la porte **avec EGDB** est le préalable à toute question de
  succession — et la décision reste un go explicite de JFC.
- **4cf en dur dans le moteur** : purement une optimisation mémoire/cache
  maintenant que le point statistique est acquis. Rien ne l'exige.
- **Pas de palier suivant par symétrie.** J'avais annoncé un fold
  `{id, rot180∘cs, LR, LR∘rot180∘cs}` sur la foi du docstring de `symmetry.py`,
  qui qualifiait la réflexion gauche-droite d'« exacte, signe +1 ». **C'est faux.**
  Un miroir gauche-droite d'un damier 10×10 envoie les cases sombres sur les
  claires : la surface de jeu n'est pas conservée. **Mesuré : LR casse 36 des 81
  adjacences diagonales**, là où `rot180` les préserve toutes. `rot180∘cs` est donc
  la **seule** symétrie exacte disponible, et le fold exact l'épuise déjà.
  `test_symmetry_geometry.py` verrouille le critère : toute transformation ajoutée
  doit d'abord préserver l'adjacence.

  C'est une question de JFC qui l'a attrapé — *si LR donnait la moitié des poids
  gratuitement, pourquoi Scan ne le ferait-il pas ?* Réponse : parce que ce n'est
  pas disponible. `cpx62-1122` a été tué en vol sur cette base.

## Artefacts

- refit deux bras : `r2:jass-data/runs/cpx62-1117-l3-exact-fold-refit-v1/20260731T235446Z-970f14de`
- porte fold : `r2:jass-data/runs/cpx62-1118-l3-exact-fold-gate-v1/`
- passe on-policy : `r2:jass-data/runs/cpx62-1119-l3-exact-fold-onpolicy-v1/20260801T010633Z-c0069d00`
- porte on-policy : `r2:jass-data/runs/cpx62-1120-l3-onpolicy-gate-v1/`
- porte contre champion : `r2:jass-data/runs/cpx62-1121-l3-exact-vs-turnover-gate-v1/`
