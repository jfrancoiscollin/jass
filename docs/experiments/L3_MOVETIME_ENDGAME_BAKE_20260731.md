# Bake search — correctif de l'overshoot `go movetime` en finale de dames

> Date : 31 juillet 2026
> Commit du correctif : `16f8c151`
> Nature : **bake search**, promotion délibérée, sur go explicite de JFC
> Réversible : `git revert 16f8c151`

## Ce que ce bake promeut

Un correctif de **recherche**, pas un modèle. Aucun champion ne change :
TURNOVER reste le champion général courant. Ce que le bake enregistre, c'est
que le comportement de recherche corrigé devient la référence. Les mesures
antérieures de vue native ne lui sont pas byte-comparables, mais l'écart est
mesuré et négligeable — voir la section historique en fin de document.

## Le défaut

Ouvert depuis le 7 juillet 2026, décrit dans `CLAUDE.md` comme
« `go movetime` OVERSHOOT 2-3.5× en endgame-dames, cause exacte à creuser,
PAS la granularité du node-check ».

La cause réelle, localisée par six échantillons `gdb` qui donnent tous la même
pile :

```
negamax → probe_endgame → probe_kings_endgame
        → __pthread_once_slow → ThreeVsOneBitbase::ensure_built
```

La bitbase 3-dames-contre-1 (`50⁴ × 2` entrées) est construite par
rétro-analyse **à la première sonde**, et cette sonde a lieu **à l'intérieur de
`negamax`**, sous un `std::call_once` que la sonde de deadline ne peut pas
interrompre.

Coûts de construction mesurés, une fois par processus :

| Table | Coût |
|---|---:|
| 3-contre-1 | **5,15 s** |
| 2-contre-1 | 280 ms |
| témoin sans finale | 21 ms |

### Pourquoi chaque symptôme du dossier s'explique

| Observation au dossier | Explication |
|---|---|
| seulement en finale de dames | `probe_kings_endgame` est la seule sonde qui atteint ces tables |
| trivial à profondeur fixe ≤ 3, explose à 4 | c'est à la profondeur 4 que la recherche descend dans une position 3v1 |
| `0x3FF → 0xFF` sans effet | le thread est **garé dans un `call_once`**, pas en train de compter des nœuds : 2048 nœuds en 5,5 s, soit ~370/s |
| « 2-3,5× » vu en A/B | là, le coût est payé par le premier coup de la partie qui atteint une telle finale, puis amorti sur le reste |

## Mesures avant / après

Position `W:WK46,K47,K48:BK3,K4,K5`, moteur avec TURNOVER.

| Cellule | Avant | Après |
|---|---:|---:|
| `movetime 100`, dames 3v3 | 5558 ms — **55,58×** | 101 ms — **1,01×** |
| `movetime 300`, dames 3v3 | 5351 ms — 17,84× | 259 ms — 0,86× |
| `movetime 100`, dames 4v3 | 5509 ms — 55,09× | 80 ms — 0,80× |
| `movetime 100`, milieu de partie | 80 ms — 0,80× | 85 ms — 0,85× |
| `movetime 100`, position initiale | 0 ms | 0 ms |

## Ce n'était pas seulement un bug de temps

À `movetime 100` sur la position 3v3, le moteur rendait
`depth=3 score=164` : il se croyait gagnant. Préchauffé, la même recherche
atteint `depth=20 score=0`. Le défaut ne dégradait donc pas seulement la mesure,
il dégradait le jeu.

**Mais une seule fois par processus.** `std::call_once` construit la table au
premier passage et tout le reste du processus est chaud. Mesuré sur le binaire
pré-correctif, trois `go movetime 100` consécutifs dans le même processus :

| | durée | profondeur | score |
|---|---:|---:|---:|
| `go` #1 | 3861 ms | 3 | 46 |
| `go` #2 | 85 ms | 17 | 0 |
| `go` #3 | 40 ms | 18 | 0 |

Seul le **premier** coup, par processus moteur, qui descend dans une telle
finale est décidé sur une recherche tronquée.

## Le correctif

`warm_kings_endgame_bitbases()` (`src/bitbase.hpp` / `.cpp`) construit les deux
tables, appelée depuis `HubFrontEnd::cmd_hello` **après le flush de la réponse
`ready`** — un client qui attend le handshake avec un timeout court ne doit pas
subir la construction. La boucle de commandes étant sérielle, ce qui arrive
ensuite est simplement mis en file.

### Coût, vérifié et non supposé

`jass_vs_jass_arch` et `calibrate_vs_scan` construisent tous deux leurs moteurs
**une fois par shard, hors de la boucle de parties**. Deux moteurs par shard, une
construction de 5,4 s chacun, amortie sur ~250 parties : **~43 ms par partie**,
contre 5,4 s volées à l'horloge d'une seule partie aujourd'hui.

### Déterminisme

Inchangé. `go depth 4` sur la même position rend `nodes=4314` et
`bestmove 46-41`, identiques avant et après : seul le **moment** de la
construction a bougé, jamais le contenu des tables.

### Tests

Deux tests dans `tests/test_endgame.cpp` :

- `test_deadline_holds_in_a_kings_endgame` — vérifié comme ayant des dents :
  en retirant l'appel de préchauffage, la suite échoue ; en le remettant, elle
  passe ;
- `test_warming_does_not_change_probe_results` — idempotence et invariance des
  sondes.

## Ce que ce bake casse dans l'historique — mesuré

Faible. Deux canaux étaient envisageables ; un seul a existé.

**Canal 1 — jeu dégradé : réel, mais borné.** Le coup touché est le premier, par
processus moteur, qui descend dans une finale de dames sondable. Les harnais
construisent **deux moteurs par shard**, hors de la boucle de parties, et une
cellule de porte tourne 12 à 16 shards : l'exposition maximale est donc de
**~24 à 32 coups par cellule**, sur 3000 à 5000 parties — de l'ordre de
**0,3 à 0,6 % des parties, un coup chacune**.

**Canal 2 — nulles fabriquées : n'a jamais existé.** `jass_vs_jass_arch` attrape
le dépassement et compte la partie comme nulle (chemin `game skipped`), mais ce
chemin se déclenche sur le `--game-timeout`, réglé à **180 s**. Un blocage de
5,4 s ne l'approche pas. Compté dans les archives de logs :

| Porte | `game skipped` |
|---|---:|
| `home-1040` (promotion TOPK3, 10 000 parties) | **0** |
| `home-1008` (readout volume 8M) | **0** |
| `home-1091` (reverse-seed 2M) | **0** |
| `home-1108` (reverse-seed 4M) | **0** |
| `home-1102` (poids d'échec ×2) | **0** |

**Conclusion : aucun verdict n'est remis en cause, et aucun ne demande d'être
rejoué.** Les mesures antérieures ne sont pas byte-comparables à celles d'après
le bake, mais l'écart attendu est négligeable devant leurs intervalles de
confiance. Le correctif reste justifié pour lui-même : il supprime une violation
de budget de 55× et une décision de jeu prise sur une recherche tronquée.

## Et les données de self-play depuis le début ? (question JFC, 2026-07-31)

La section ci-dessus ne parle que des **portes A/B**. Le self-play a un profil
d'exposition différent, et il fallait le mesurer séparément.

### L'immunité est structurelle, pas chanceuse

`has_deadline` n'est armé **que** si `movetime_ms > 0` (`search.cpp:1491`). Sans
deadline, le blocage `call_once` coûte du temps **mural**, mais la recherche
atteint quand même la profondeur demandée : le résultat est **bit-à-bit
identique**. Toute génération à profondeur fixe est donc hors d'atteinte du bug,
par construction.

Sur **176** scripts ayant jamais appelé `--gen-data-wdl` dans l'historique des
deux dépôts, **166 génèrent à profondeur fixe**.

### Les 10 exceptions, toutes dans l'ère bootstrap

`0195`, `0196`, `0203`, `0204`, `0205`, `ccx33-0205b`, `cpx62-0214`,
`ccx33-0215`, `cpx62-0228`, et le template `wdl-loop-portable` — génération sous
`--movetime 30–60 ms`.

⚠️ Le tri doit porter sur la **commande**, pas sur le fichier : `0254` et `0297`
contiennent bien `--movetime`, mais dans leur **porte Scan** (`calibrate_vs_scan
--movetime 0.5`), pas dans la ligne de génération. Les compter comme touchés
aurait été faux.

**Borne : ≤ 2 coups par processus générateur.** Il y a deux `once_flag`
distincts (`bitbase.cpp:80` pour 2v1 à 280 ms, `bitbase.cpp:233` pour 3v1 à
5,15 s) et `call_once` ne tire qu'une fois par processus. Pire cas, `0228` :
8 générations × 16 shards = 128 processus → **≤ 256 coups sur ~2,4 M positions**.

### Et ces coups-là ne sont pas de mauvaises étiquettes

C'est le point décisif. La cible WDL est **le résultat de la partie telle qu'elle
a été jouée** (retour Monte-Carlo, pas une valeur bootstrapée). Un coup plus
faible ne rend pas l'étiquette fausse : la partie s'est réellement terminée
ainsi. L'effet est un déplacement infime de la distribution hors-politique —
exactement la perturbation qu'on **injecte délibérément** ailleurs (epsilon-
exploration, bruit top-k).

C'est une nature de défaut **différente** de celle du root nul (`9c1d1e8e`), qui
lui **supprimait des parties** et biaisait donc la distribution des issues.

### Les autres voies de génération

- **Corpus L3 courants** (VOL8M, TURNOVER, TOPK, reverse-seed) : **0 sur 16**
  jobs récents ne passe `--movetime`. Propres.
- **Parents MMTO / `scan_selfplay_gen`** : `--strong-movetime` a **zéro appelant,
  jamais** — le mode movetime asymétrique n'a servi dans aucun job. Les 7
  templates en `--player-jass-bin` font jouer Jass à profondeur fixe
  (`default_movetime = None`). Propres.

### Ce qui n'est PAS établi

Le « ≤ 2 coups par processus » est une **borne**, pas une mesure : il n'a pas été
vérifié que ces processus atteignaient effectivement une finale à dames sondable.
Le compte réel peut être zéro. Et la lignée `gen2-mmto` remonte à cette ère : si
un artefact en porte une trace, c'est cet adversaire de référence — sans
conséquence, puisqu'il sert de thermomètre **figé, identique pour tous les bras**.

**Verdict : aucun corpus d'entraînement n'est à rejeter, aucun fit à refaire.**

## Rollback

```bash
git revert 16f8c151
git push origin HEAD:refs/heads/develop
```

Aucun artefact R2 n'est touché. Le revert restaure le comportement précédent en
entier.
