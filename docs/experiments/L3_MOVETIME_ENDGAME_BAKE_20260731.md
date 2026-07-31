# Bake search — correctif de l'overshoot `go movetime` en finale de dames

> Date : 31 juillet 2026
> Commit du correctif : `16f8c151`
> Nature : **bake search**, promotion délibérée, sur go explicite de JFC
> Réversible : `git revert 16f8c151`

## Ce que ce bake promeut

Un correctif de **recherche**, pas un modèle. Aucun champion ne change :
TURNOVER reste le champion général courant. Ce que le bake enregistre, c'est
que le comportement de recherche corrigé devient la référence, et que les
mesures antérieures de vue native ne lui sont pas comparables.

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
atteint `depth=20 score=0`.

**Toute finale de dames jouée sous pendule était décidée sur une évaluation à
profondeur 3.** Le défaut ne dégradait donc pas seulement la mesure, il
dégradait le jeu.

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

## ⚠️ Ce que ce bake casse dans l'historique

Toutes les mesures de **vue native** antérieures au 31 juillet 2026 ont été
prises avec le défaut présent. Deux effets distincts, tous deux dans le même
sens :

1. dans les finales de dames sous pendule, le moteur jouait sur une recherche
   tronquée à la profondeur 3 ;
2. `jass_vs_jass_arch` attrape explicitement le dépassement et **compte la
   partie comme nulle** (chemin `game skipped`, commentaire
   « ROBUSTESSE : un coup qui timeout (overshoot movetime-endgame) »).

Les portes concernées incluent `home-1040` (porte de promotion TOPK3, 10 000
parties) et toute cellule native des campagnes de juillet. **Elles ne sont pas
byte-comparables aux mesures postérieures à ce bake.** L'ampleur réelle de la
contamination est quantifiée séparément — voir le décompte des parties sautées
dans les logs des portes déjà tournées.

Ce bake **n'invalide aucun verdict** de lui-même : il enregistre une rupture de
comparabilité et ouvre la question de savoir lesquels méritent d'être rejoués.

## Rollback

```bash
git revert 16f8c151
git push origin HEAD:refs/heads/develop
```

Aucun artefact R2 n'est touché. Le revert restaure le comportement précédent en
entier.
