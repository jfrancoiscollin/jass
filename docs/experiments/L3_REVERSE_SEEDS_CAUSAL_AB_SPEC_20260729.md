# L3-PURE — reverse seeds contrôlés v1

Date : 2026-07-29
Statut : outillage data-only et micro-probe opérationnel ; aucun entraînement,
match, bake, promotion ou job lancé par cette PR
Portée : PR 3 du mémo `MEMO_CODEX_JASS_QUALITE_SIGNAL_20260728.md`

## 1. Question causale

À parent, policy, profondeur, volume, fit et fraction de seeds constants,
démarrer le self-play depuis des échecs de conversion historiques améliore-t-il
plus la force que démarrer depuis des positions aléatoires comparables ?

Le contraste primaire futur est :

```text
HARD_SEED_SELFPLAY minus MATCHED_RANDOM_SEED_SELFPLAY
```

Le facteur est la **politique de sélection de la racine seedée**. Ce DOE ne
reteste ni la sélection de replay historique, ni une nouvelle profondeur, ni
une formule générale de hardness.

## 2. Source et séquencement

Les deux catalogues proviennent du même train historique authentifié. Le holdout
historique est structurellement vérifié, mais n'est jamais éligible.

Le traitement est le `hard-seeds.jnnw` zero-target certifié par
`mine-hard`. Le contrôle est sélectionné sans consulter le WDL parmi les autres
parties et positions de la même source. Les parties et positions canoniques du
traitement sont exclues du contrôle.

Le micro-probe distant et tout DOE complet restent bloqués jusqu'à publication
d'un verdict hard-replay explicite et revue humaine. Un catalogue `READY` ne
vaut pas verdict scientifique. Aucun job suivant n'est déclenché
automatiquement.

## 3. Appariement v1 figé

Chaque position de base est suivie immédiatement de son miroir couleur. Les
deux catalogues ont la même cardinalité et le contrôle d'indice `2*i` a la même
strate que le traitement d'indice `2*i`.

La clé d'appariement est :

```text
(source_temporal_id, phase_band, piece_band, material_stratum)
```

Définitions figées, identiques aux helpers existants de
`tools/selfplay_frontier.py` :

| Dimension | Bandes |
|---|---|
| phase | `opening >=30`, `midgame 22..29`, `late_midgame 15..21`, `endgame 8..14`, `deep_endgame <=7` pièces |
| pièces | `late_midgame >=17`, `endgame 11..16`, `deep_endgame <=10` |
| matériel | `P4=0`, `P3=1`, `P2=2..3`, `P1>=4` en valeur homme=1, dame=3 |
| temps | identifiant immuable job/tentative/bras de la source authentifiée |

Le contrôle utilise une priorité BLAKE2b déterministe au niveau partie puis
position, à partir de `game_id`, position, `opening_id`, graine d'appariement et
source temporelle. Le buffer borné conserve au plus une candidate par partie
et strate, puis la sortie au plus une partie et une position canonique par
racine sélectionnée.

Le buffer initial est `quota + max(16, 25 % du quota)`. Si la déduplication
globale des parties ou positions déjà attribuées à une strate précédente
consomme cette marge, le matcher rescane uniquement la strate déficitaire avec
un buffer doublé géométriquement. Les priorités BLAKE2b, exclusions, quotas et
ordre des strates restent inchangés ; le manifeste consigne capacités initiale
et finale ainsi que le nombre de rescans. Une strate réellement insuffisante
ferme toujours le préflight : aucune fusion de bande ou réduction post-hoc
n'est permise.

Cette règle ferme l'incident opérationnel `cpx62-1079` : le buffer initial de
la strate `deep_endgame / p3_thin` ne conservait plus que 36 002 contrôles
utilisables après déduplication globale pour un quota de 37 339, soit un
déficit de 1 337. Le diagnostic `cpx62-1080` a exclu un manque de source,
de mémoire ou de disque ; aucune sortie partielle de 1079 n'est réutilisable.

## 4. Contrat self-play futur

Les bras doivent partager exactement :

- parent et warm-start ;
- volume de records ;
- Q00, jeu d8 et label d4 WDL-only ;
- policy d'exploration et graines de shards ;
- `--pair-openings`, `--drop-plycap`, `--sample-initial` ;
- `--split-selfplay-rngs` ;
- `--random-open-plies 0` ;
- `--seed-frac P`, identique dans les deux bras.

`random-open-plies` doit être nul : les deux positions appariées peuvent avoir
des longueurs de séquence légale différentes. Avec une ouverture aléatoire,
elles consommeraient un nombre différent de tirages du flux `opening`, ce qui
désapparierait tous les futurs indices de catalogue.

`P` est un entier dans `[0,100]`. Sa valeur scientifique n'est pas choisie par
cette PR. Elle sera préenregistrée après un micro-probe qui ne lit que le
rendement, le débit, les compteurs de racines et les ply-caps. Les W/D/L et la
force ne peuvent pas servir à choisir `P`.

## 5. Préflight catalogue data-only

`jobs/templates/l3-pure-reverse-seed-catalogue-v1.sh` est le seul producteur
des entrées du probe. Il :

- authentifie le job source, son certificat, le job catalogue HARD et tous les
  SHA/counts associés ;
- reproduit bit à bit le split historique avant toute sélection ;
- lie le catalogue HARD à cette source et à ce split ;
- exécute le matcher deux fois dans deux répertoires neufs et exige l'identité
  binaire des deux JNNW et du manifeste ;
- publie `control-seeds.jnnw`, `treatment-seeds.jnnw`,
  `reverse-seed-matching.json` et un certificat job.

Ce préflight ne contient ni self-play, ni fit, ni match de force, ni wrapper de
queue. Son certificat fixe `training=false`, `promotion=false` et
`automatic_next_job=null`.

## 6. Micro-probe CPX62

`jobs/templates/l3-pure-reverse-seed-probe-v1.sh` est un probe opérationnel
non-queue :

- `nproc=16`, build `-j4`, un seul producteur à la fois ;
- 200 records par bras, `PROBE_SEED_FRAC=100` ;
- même graine, catalogues alignés, génération séquentielle ;
- timeout par producteur et traps TERM/INT ;
- RES/PROG sous le scratch, garde disque et monitor à PID explicite ;
- certificat sans W/D/L, fit, Elo ni verdict scientifique.

Le probe consomme exclusivement le préflight catalogue authentifié via
`MATCHED_PREFIX`. Il publie records/minute, records et ouvertures seedés
observables, compteurs moteur et durée. Sa fraction 100 % sert à mesurer le
rendement des deux types de racines ; ce n'est pas le futur `SEED_FRAC`.

## 7. Interprétation et rewind différé

Un gain futur démontrerait l'utilité des états de départ ciblés sous ce parent,
cette policy et cette dose. Il ne validerait pas automatiquement la formule de
hardness sur d'autres sources ou usages.

JSM1 ne contient que `game_id`, `opening_id` et `seeded`. Un véritable rewind
historique exige plus tard un sidecar optionnel et versionné, par exemple JSP1
avec un `ply:u16` aligné par record. JSM1 ne doit pas être modifié.

```json
{
  "probe_authorized": true,
  "training_authorized": false,
  "promotion_authorized": false,
  "automatic_next_job": null,
  "external_teacher_inputs": 0
}
```
