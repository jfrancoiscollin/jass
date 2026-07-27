# Reproduire l'ancre historique contre Scan avant de croire `0,050`

Préenregistré le 27 juillet 2026, avant le run `home-0999`.

## Le désaccord

`home-0997ter` puis `home-0998` ont mesuré TURNOVER à **`0,050`** contre Scan,
soit environ **`−512 Elo`**, identique en `d12/d12` et en `d10/d6`, et `0,0`
sur les trois variantes d'argv testées. Les parties dumpées sont réelles :
98 demi-coups, prises légales, FEN finale montrant Jass à zéro pièce.

L'historique du projet dit autre chose. `PROJECT_RESULTS` §3.4 :

> Le gain d9 ne s'est transféré que de +5–6 Elo au movetime contre Scan :
> nouvelle référence environ mt0.3 −155, mt1.0 −128, NPS-comp −129.

Et la lignée L3-PURE a gagné de l'ordre de 60-70 Elo depuis `gen2-mmto`. Les
deux chiffres ne peuvent pas être vrais ensemble : il y a un facteur ~350 Elo
d'écart. **Aucune matrice de calibration ne vaut tant qu'on ne sait pas lequel
des deux est faux.**

## Ce que ce job fait, et pourquoi dans cet ordre

`home-0999` ne mesure pas TURNOVER en premier. Il rejoue d'abord **l'ancre**.

`gen2-mmto` est le modèle exact dont le `−155` a été publié. Il est disponible,
immuable et haché (`01cc3ea5…`), et la porte de succession `home-0996` l'a déjà
fait jouer comme garde. C'est donc un **étalon** : on connaît sa valeur, on la
remesure sur le harnais d'aujourd'hui, et l'écart mesure le harnais et non le
modèle.

Les deux bras partagent le pool, le binaire Scan figé, la cadence, le nombre de
parties. Ce qui les distingue est ce qui doit les distinguer : la géométrie de
chaque modèle (32cf pour GEN2, 8cf pour TURNOVER) et la configuration de
recherche canonique de chacun (constantes compilées pour GEN2 comme en `0571`
et `0637`, `Q00` pour TURNOVER). La comparaison qui porte est bras-à-bras
**dans le temps** — GEN2 aujourd'hui contre GEN2 en `0637` — pas bras contre
bras dans ce job.

## Protocole, repris de `cpx62-0571`

| élément | valeur | d'où |
|---|---|---|
| pool | 20 premières combinaisons DILF | `0571` en prenait 60 de la même façon |
| appariement | `--pairs 1`, couleurs échangées | `0571` |
| parties | 40 par cellule | `0571` en jouait 120 |
| plafond de coups | 200 (défaut) | `0571` |
| Scan | livre `off`, `bb-size 0`, binaire figé `a634cbb4…` | contrat de runtime `home-0925` |
| EGDB | **désactivée** | l'historique n'en avait pas, et Scan tourne sans bitbase |
| cellules | `mt0.3` et `d9`, sur chacun des deux bras | les deux ancres chiffrées disponibles |

Pool figé par empreinte (`eefdc366…`) pour que la relance soit exacte.

### Vérification de géométrie, tracée plutôt que supposée

L'explication la plus naturelle d'un effondrement à `0,050` serait un modèle
chargé dans la mauvaise géométrie. Elle est **fausse**, et le job le prouve
plutôt que de l'affirmer : `pattern_jass::load_weights` refuse un fichier dont
le nombre de buckets ne correspond pas à la géométrie compilée, et `--pattern`
sort en code 2 dans ce cas. Le job exige donc les quatre chargements — chaque
moteur accepte son modèle et **refuse** celui de l'autre — avant de jouer.

## Ce que le premier tir a trouvé — `home-0999`, 27 juillet, 15h08-15h18 FR

Verdict `SCAN_ANCHOR_INCONCLUSIVE_CELL_FAILED`, quatre cellules sur quatre
avortées. Le résultat n'est pas dans le verdict, il est dans les parties jouées
avant l'avortement :

| cellule | parties | motif de fin |
|---|---:|---|
| `gen2-mt030` | 26 | **26 × « no legal move from Jass-player »** |
| `gen2-d9` | 28 | 26 idem, 1 ply cap, 1 côté Scan |
| `turnover-d9` | 26 | 25 idem, 1 ply cap |
| `turnover-mt030` | 2 | 2 idem |

**`gen2-mmto` meurt exactement comme TURNOVER.** Le `0,050` n'était donc pas un
résultat sur le champion : les deux modèles s'effondrent à l'identique, ce qui
disqualifie le modèle comme explication et désigne le moteur.

### La cause, reproduite en une commande

`search()` portait trois court-circuits de nulle à la racine qui retournaient
**sans jamais choisir de coup**. `5f5a7e7b` en a réparé un — le tablebase. Il
en restait deux :

```cpp
for (auto h : game_history) if (h == root_hash) { res.score = 0; return res; }
if (pos.halfmove_clock() >= FIFTY_MOVE_PLIES)   { res.score = 0; return res; }
```

`res.best_move` reste construit par défaut, le HUB émet `bestmove 0-0`, et tout
client HUB lit ça comme « plus de coup légal », c'est-à-dire un abandon :

```text
position fen W:WK50:BK1 ; go depth 6   -> bestmove 50-44 ...
apply 50-45 / 1-6 / 45-50 / 6-1
go depth 6                             -> bestmove 0-0 score=0 depth=0 nodes=0
```

Une **seule** répétition suffit — la règle en demande trois, le moteur abandonne
à la première. En manœuvre de dames c'est quasi systématique.

Pourquoi ça n'avait jamais crevé les yeux : en Jass-contre-Jass les deux camps
abandonnent symétriquement, donc les portes L3-PURE mesurent quand même une
force *relative* juste et `home-0996` reste valide. Contre Scan, seul Jass
abandonne, et l'asymétrie est totale.

### Correctif

Le score d'une racine nulle reste `0` — c'est la règle — mais il est désormais
forcé **après** la recherche au lieu de la remplacer, donc le coup vient
toujours du jeu. Deux témoins C++ : racine répétée et horloge à 50 plies
rendent chacune un coup légal.

Conséquence à porter au dossier : **le `−128 à −155` historique est un
plancher, pas une valeur.** Il a été mesuré sur ce moteur, qui perdait toute
partie atteignant une racine nulle.

## Règle de décision, révisée après `home-0999`

Les ancres ne peuvent plus servir de cible bilatérale : elles sont contaminées
dans une direction connue. Un moteur réparé doit faire **mieux** qu'elles, et
un dépassement ne contredit rien. La règle devient donc unilatérale.

| cellule | plancher de score | ancre |
|---|---|---|
| `gen2-mt030` | `≥ 0,17` | `−155 Elo` (score ~`0,290`) |
| `gen2-d9` | `≥ 0,05` | `−276 Elo` (score ~`0,170`) |

À `n=40`, l'erreur-type est de `7,9 pp` ; le plancher est l'ancre moins une
erreur-type et demie.

- **`SCAN_HARNESS_SOUND_ANCHOR_AT_OR_ABOVE_FLOOR`** — les deux cellules GEN2
  tiennent leur plancher. Le correctif du coup nul tient, et on lit alors le
  contraste intra-job.
- **`SCAN_HARNESS_STILL_BROKEN_ANCHOR_BELOW_FLOOR`** — un second défaut reste,
  aucun chiffre contre Scan n'est utilisable.
- **`SCAN_ANCHOR_PARTIAL_HUMAN_REVIEW`** — une seule tient.
- **`SCAN_ANCHOR_INCONCLUSIVE_CELL_FAILED`** — cellule sous le plancher de 30
  parties, ou en échec. `n` insuffisant est un échec, jamais un résultat faible.

Le job publie aussi, et c'est ce qui porte vraiment : le **contraste
intra-job** `turnover − gen2` par régime. Il ne dépend d'aucune ancre — même
binaire, même pool, même Scan, même cadence — et c'est lui qui dira si un écart
subsiste entre les deux modèles une fois le moteur réparé.

Chaque cellule publie en plus sa **part de forfaits** (`no legal move from
Jass`). C'est le motif qui a trahi le bug ; il devient une métrique de sortie
pour qu'il ne puisse plus passer inaperçu.

Dans tous les cas `promotion_authorized=false`, `automatic_next_job=null`.

## Deux défauts du harnais corrigés au passage

Trouvés en diagnostiquant `0998`, indépendants du verdict ci-dessus.

**Un moteur qui ne rend pas de coup était compté perdant.** `go()` renvoyait
`None` sur `error`, et `go_from()` renvoyait `None` sur `error`, sur timeout et
sur réponse illisible ; la boucle de partie traduisait ce `None` en « plus de
coup légal », c'est-à-dire en défaite. Un binaire cassé se lisait donc comme un
moteur faible — exactement la lecture qu'on risquait de faire ici. Les trois
chemins lèvent désormais `EngineFailure`, et la boucle ne traite un « pas de
coup » comme terminal **que si l'arbitre confirme** qu'il n'y a pas de coup
légal. C'est la règle « `n=0` est un échec, pas un neutre » appliquée au niveau
du coup. Couvert par `jobs/tests/test_calibrate_vs_scan_failure_modes.py`.

**Le livre de Jass n'a jamais été désactivable.** Tous les appelants passent
`no_book=True`, la branche correspondante était un `pass` commenté, et le
moteur n'avait pas d'option pour ça — pendant que Scan tourne `book=off`. Le
moteur reçoit donc `--no-book` (`Engine::use_book(false)`, déjà existant, exposé
par le HUB) et `calibrate_vs_scan` un `--jass-no-book`.

Ce drapeau est **éteint par défaut, délibérément**. Toutes les portes publiées
à ce jour portent l'asymétrie ; l'activer changerait le moteur et rendrait les
nouveaux chiffres non comparables aux anciens. C'est une décision de protocole,
pas un défaut par défaut. `home-0999` tourne donc livre allumé, comme `0571` et
`0637`.

## Sizing

Quatre cellules en parallèle, deux processus moteur chacune, sur 16 CPU. Les
débits mesurés jusqu'ici sont **inutilisables** : ils ont été relevés sur des
parties qui se terminaient par forfait au bout de quelques dizaines de coups.
Une partie réparée va au bout — `~120` demi-coups à `mt0.3` des deux côtés, soit
`~70 s`, donc `40` parties ≈ `~50 min` sur la cellule la plus lente. Les
cellules `d9` sont nettement plus rapides.

Cellules plafonnées à `50 min`, deux builds (8cf puis v4) avant le jeu.

**ETA ≈ 55 à 70 min.** `n=40` donne une erreur-type de `7,9 pp` : c'est un
diagnostic de harnais, pas une mesure de force, et il est dimensionné comme tel.
