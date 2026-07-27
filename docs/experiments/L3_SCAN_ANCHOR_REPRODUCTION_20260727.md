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
| pool | 40 premières combinaisons DILF | `0571` en prenait 60 de la même façon |
| appariement | `--pairs 1`, couleurs échangées | `0571` |
| parties | 80 par cellule | `0571` en jouait 120 |
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

## Règle de décision, fixée avant le run

Ancres publiées : `mt0.3` → `−155 Elo` (score ~`0,290`), `d9` → `−276 Elo`
(score ~`0,170`). À `n=80`, l'erreur-type est de `5,6 pp` ; la bande retenue
est l'ancre ±3 erreurs-types, élargie pour absorber le changement de box, de
code et de pool.

| cellule | bande de score |
|---|---|
| `gen2-mt030` | `[0,12 ; 0,46]` |
| `gen2-d9` | `[0,02 ; 0,34]` |

- **`SCAN_HARNESS_REPRODUCES_HISTORICAL_ANCHOR`** — les deux cellules GEN2
  tombent dans leur bande. Le harnais est sain, et le `0,050` de TURNOVER est
  un vrai résultat qu'il faudra expliquer et non un artefact.
- **`SCAN_HARNESS_CONTRADICTS_HISTORICAL_ANCHOR`** — aucune n'y tombe. Toute
  mesure contre Scan postérieure à `0637` est nulle, `home-0997/0998`
  comprises, et la calibration attend une réparation du harnais.
- **`SCAN_ANCHOR_PARTIAL_HUMAN_REVIEW`** — une seule reproduit.
- **`SCAN_ANCHOR_INCONCLUSIVE_CELL_FAILED`** — une cellule sous le plancher de
  60 parties, ou en échec. `n` insuffisant est un **échec**, jamais un
  résultat faible.

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

Quatre cellules en parallèle, deux processus moteur chacune, sur 16 CPU. Débit
mesuré en `0997ter` sur cette box : `mt0.5/mt0.5` = `1,93` parties/min, d'où
`mt0.3` ≈ `3,1` parties/min et 80 parties ≈ `26 min`. Chaque cellule est
plafonnée à `40 min`, deux builds (8cf puis v4) précèdent le jeu.

**ETA ≈ 45 à 60 min**, mur d'horloge dominé par la cellule la plus lente.
