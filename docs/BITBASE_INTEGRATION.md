# Bitbase integration — terrain préparé (Kingsrow egdb_intl)

> Rédigé 2026-06-16. **But** : doter jass d'une base de finale WLD complète
> (hommes + dames, jusqu'à 7-8 pièces) en **adaptant une source externe**
> existante — le driver open-source d'Ed Gilbert `egdb_intl`
> (https://github.com/eygilbert/egdb_intl), qui lit les bases Kingsrow — plutôt
> que de refaire une analyse rétrograde multi-Go. Faisabilité jugée **HAUTE**.
> Ce doc consigne le **seam** déjà en place, l'adaptation, le build, la config,
> et les **points de vérification** non-négociables avant de faire confiance à
> une seule sonde.

## Pourquoi (rappel)

L'éval plafonne en finale (autopsie ~3.2-3.6 de perte côté rois ; la finale est
SEARCH-BOUND, cf 0252). Une base WLD exacte court-circuite la recherche sur les
positions ≤ N pièces : `probe_endgame` rend directement WIN/LOSS/DRAW absolu, ce
qui (a) supprime le bruit d'éval en finale et (b) donne au self-play des labels
de finale parfaits (le verrou « couverture/représentation » des Directions
A/B). C'est exactement ce que fait Scan/Kingsrow.

## Le seam (DÉJÀ EN PLACE, ce commit)

Tout l'`egdb_intl` est isolé dans **une** unité de traduction
`src/egdb_bridge.{hpp,cpp}` ; le reste du moteur ne voit jamais ses types.

- `jass::egdb::init(db_dir, cache_mb)` / `shutdown()` — cycle de vie du handle.
- `jass::egdb::available()` — `std::atomic<bool>`, **gate hot-path** (1 load).
- `jass::egdb::max_pieces()` — plafond de pièces couvert (0 si indispo).
- `jass::egdb::probe(pos)` — `Position` → board driver → lookup WLD → `EndgameResult`.
- `jass::egdb::ensure_initialised()` — bootstrap unique depuis `JASS_EGDB_PATH`
  (`std::call_once`), appelé **une fois par recherche top-level**
  (`search.cpp`), pas par nœud.

**Branchement** (`endgame.cpp::probe_endgame`) : avant la logique rois-only, si
`egdb::available()` et `popcount(occupied) ≤ max_pieces()`, on rend le WLD exact
de la base (men+kings = sur-ensemble strict des tables internes). En build
défaut, `available()` est `false` → un seul branchement par nœud, fall-through
inchangé.

**Deux saveurs de compilation** :
- `JASS_EGDB` **OFF (défaut)** : `egdb_bridge.cpp` = stubs no-op. **Zéro
  dépendance externe**, comportement finale identique à avant (6428 tests OK,
  perft inchangé).
- `JASS_EGDB` **ON** : compile `egdb_intl` depuis les sources, ouvre la base,
  convertit et sonde. **Compile + linke + tourne validé** (this commit) contre
  un checkout d'egdb_intl ; binaire OK, 6428 tests OK (bridge inerte sans data).

## Build (saveur réelle) — VALIDÉE

Compile `egdb_intl` depuis un checkout (aucune lib pré-buildée requise ; le job
clone le repo comme les jobs Scan) :

```
git clone --depth 1 https://github.com/eygilbert/egdb_intl /root/egdb_intl
cmake -S . -B build-egdb -DCMAKE_BUILD_TYPE=Release \
      -DJASS_EGDB=ON -DJASS_EGDB_SRC_DIR=/root/egdb_intl
cmake --build build-egdb -j --target jass
```

`CMakeLists.txt` compile `egdb/ engine/ builddb/ Huffman/ Re-pair/*.cpp` en une
static lib `egdb_intl` (avec `USE_MULTI_THREADING` + `Threads::Threads`), include
= racine du checkout, et linke sur `jass_lib`. (Une lib pré-buildée reste
acceptée via `-DJASS_EGDB_LIB` + `-DJASS_EGDB_INCLUDE_DIR`.) Les **fichiers de
données** se téléchargent à part (edgilbert.org).

## Config runtime

- `JASS_EGDB_PATH` — répertoire des fichiers de base. **Requis** pour activer.
- `JASS_EGDB_CACHE_MB` — cache RAM (défaut 1024). Dimensionner selon le host
  (CPX62 32 Go ≫ CCX33 16 Go).

Aucun plumbing Engine/HUB/main nécessaire : `ensure_initialised()` lit l'env au
1er search. (Un `egdb::init()` explicite reste exposé si on veut ouvrir au
démarrage HUB plus tard.)

## Adaptation — points de vérification : RÉSOLUS contre `egdb/egdb_intl.h`

Les 6 hypothèses `VERIFY` ont été confirmées contre le header public + le
`example/main.cpp` d'egdb_intl. L'implémentation `#ifdef JASS_EGDB` est désormais
**correcte, pas un skeleton** :

1. **Layout de bits `EGDB_POSITION` — DIFFÉRENT (le risque était réel).**
   egdb_intl insère un **bit de gap après chaque groupe de 10 cases** (bits
   sautés 10/21/32/43) : case `s` → bit `(s−1)+(s−1)/10`, sur bits 0..53. jass
   est CONTIGU (case `s` → bit `s−1`, bits 0..49). → `spread50_to_egdb()`
   (header) décale chaque groupe de 10 par son index. **Validé OFFLINE** par
   `test_egdb_bitboard_spread` (12 assertions ; case 2→`0x2`, case 26→`0x08000000`,
   etc., décodés de la table d'exemple egdb) — le verrou du mapping est posé
   SANS base de données.
2. **Couleur** : `EGDB_BLACK=0`, `EGDB_WHITE=1`. jass Noir (cases basses / haut
   du damier, hommes vers le bas) = egdb black. Confirmé via les lignes
   WIN/LOSS de l'exemple (même position, BLACK→WIN ⇔ WHITE→LOSS).
3. **`egdb_open(options, cache_mb, dir, msg_fn)`** — options = `"maxpieces=N"`.
   `egdb_close(handle)` (fonction LIBRE, pas un membre). `egdb_identify(dir,
   &type, &max)` interroge la base avant ouverture.
4. **`egdb_lookup` (fonction libre)** rend `EGDB_WIN=1/LOSS=2/DRAW=3` **du point
   de vue de `color` (le trait)** ; partiels `*_OR_*`=4/5, `UNKNOWN`=0,
   `NOT_IN_CACHE`=−1, `SUBDB_UNAVAILABLE`=−2 → tous `Unknown`. `from_egdb_value`
   ré-exprime WIN/LOSS en absolu White/Black via le trait.
5. **`cl`** : `0` = lookup inconditionnel (charge du disque si pas en cache).
   `egdb_lookup` est **thread-safe** (README + macro `USE_MULTI_THREADING` au
   build) → pas de lock côté jass pour les sondes lazy-SMP.
6. **Plafond de pièces** : `egdb_get_pieces(handle, &max, &max_1side)` +
   `egdb_identify` → `max_pieces()` réel (plus de hard-code).

Tout `egdb_intl` est dans `namespace egdb_interface` au scope GLOBAL → le
`#include <egdb/egdb_intl.h>` est hors de `namespace jass::egdb` (sinon
nesting → link fail ; corrigé).

## Caveat règle FMJD

Les bases sont du WLD pur (comme les tables internes, cf `bitbase.hpp`) : la
règle de nulle des 16/25 coups dames-contre-dames n'est PAS modélisée. Quelques
positions « gagnantes » seraient nulles en partie réelle. Limitation connue,
acceptable (Scan/Kingsrow l'utilisent ainsi en pratique).

## Plan de validation (sur boxe, avec les fichiers de base)

1. **Cross-check tables internes — OUTILLÉ** : `jass --egdb-selfcheck <db_dir>
   [samples] [cache_mb]` (mode CLI, `main.cpp`). Tire un échantillon de
   positions rois-only K-vs-K / 2v1 / 3v1 et compare `egdb::probe` à la
   référence interne : **KvK doit être Draw** (sinon bug mapping), et partout où
   notre bitbase affirme un gain DÉFINI egdb doit rendre le **même** absolu (les
   bugs layout/couleur/résultat se voient ici). egdb décisif là où on dit
   Draw/Unknown = egdb plus fort (reporté, pas un échec). **Garde-fou : 0
   violation requis avant de faire confiance à la base.** (Le mapping de bits
   est DÉJÀ validé offline par `test_egdb_bitboard_spread`.)
2. **Perft inchangé** + 6428 tests (la sonde ne change pas la génération).
3. **Elo / autopsie** : A/B avec vs sans base sur des finales — la perte côté
   rois (~3.6) doit chuter ; vérifier 0 régression milieu de jeu.
4. **Self-play seedé finale** (cf Directions A/B) **relabelisé par la base** :
   labels de finale parfaits → re-densification → mesurer si le verrou cède.

## Scope du suivi (sur boxe — il reste UNIQUEMENT les données + le run)

Le code est complet et build-validé. Reste, sur un host :
- **Télécharger un sous-ensemble de base** (≤6 pièces d'abord) depuis
  edgilbert.org/InternationalDraughts (dépend de la policy réseau de la boxe).
- `git clone egdb_intl` + build `-DJASS_EGDB=ON -DJASS_EGDB_SRC_DIR=...`.
- `jass --egdb-selfcheck <db_dir>` → **doit être CLEAN** (étape 1).
- Puis étapes 3-4 (Elo/autopsie, relabel self-play).
- **Garde-fou : rien ne se branche en défaut tant que le self-check n'est pas
  vert.**

## État

- **Seam + hook + CMake from-source + CLI self-check + doc** : FAIT.
- **Saveur réelle = CORRECTE et BUILD-VALIDÉE** (compile+linke+tourne contre un
  checkout egdb_intl ; 6428 tests OK ; mapping de bits validé offline). Les 6
  points VERIFY sont RÉSOLUS contre le header.
- **Reste** : les fichiers de données + le run `--egdb-selfcheck` sur une boxe
  (pas de Codex requis — c'est du run, plus du code).
