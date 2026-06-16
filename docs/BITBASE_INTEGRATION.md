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
  dépendance externe**, comportement finale identique à avant (6408 tests OK,
  perft inchangé).
- `JASS_EGDB` **ON** : lie `egdb_intl`, ouvre la base, convertit et sonde.

## Build (saveur réelle)

Sur un host qui a la lib + les fichiers de base :

```
cmake -S . -B build-egdb -DCMAKE_BUILD_TYPE=Release \
      -DJASS_EGDB=ON \
      -DJASS_EGDB_INCLUDE_DIR=/opt/egdb_intl/include \   # contient egdb/egdb_intl.h
      -DJASS_EGDB_LIB=/opt/egdb_intl/build/libegdb_intl.a
cmake --build build-egdb -j --target jass
```

`CMakeLists.txt` câble include + link sur `jass_lib` quand `JASS_EGDB=ON`.

## Config runtime

- `JASS_EGDB_PATH` — répertoire des fichiers de base. **Requis** pour activer.
- `JASS_EGDB_CACHE_MB` — cache RAM (défaut 1024). Dimensionner selon le host
  (CPX62 32 Go ≫ CCX33 16 Go).

Aucun plumbing Engine/HUB/main nécessaire : `ensure_initialised()` lit l'env au
1er search. (Un `egdb::init()` explicite reste exposé si on veut ouvrir au
démarrage HUB plus tard.)

## Adaptation — points de VÉRIFICATION (à confirmer contre les headers egdb_intl)

Le skeleton `#ifdef JASS_EGDB` code l'adaptation mais chaque hypothèse marquée
`VERIFY` doit être confirmée AVANT de faire confiance à une sonde. **Un bug ici
rend des WLD faussement confiants qui corrompent silencieusement la recherche.**

1. **Layout de bits `EGDB_POSITION` (#1 RISQUE)** : jass utilise bit `i` =
   case FMJD `i+1` (`bitboard.hpp`). Confirmer qu'egdb_intl utilise le **même**
   mapping (numérotation FMJD standard, bit = case−1). Sinon → permuter les bits
   dans `to_egdb_position()`.
2. **Convention couleur** : `EGDB_BLACK`/`EGDB_WHITE` (valeurs + sens de jeu).
   jass Noir en haut (FMJD 1..20), Blanc en bas (31..50) ; vérifier que les
   home-rows egdb correspondent.
3. **Signature `egdb_open`** + chaîne `options` (type de base / sélection du
   plafond de pièces) + nom du membre `close`.
4. **Codes retour `lookup`** : `EGDB_WIN/LOSS/DRAW` exacts vs partiels
   (`*_OR_*`, `NOT_IN_CACHE`) → seuls les exacts propagés, le reste = Unknown.
   Vérifier que WIN/LOSS sont bien **du point de vue du trait** (`color`).
5. **Argument `cl`** du lookup (load-from-disk vs cache-only) + thread-safety
   du driver pour le lazy-SMP (plusieurs threads sondent le même handle).
6. **Plafond de pièces** : comment l'interroger (`get_pieces` ?) ; codé en dur
   à 8 dans le skeleton.

## Caveat règle FMJD

Les bases sont du WLD pur (comme les tables internes, cf `bitbase.hpp`) : la
règle de nulle des 16/25 coups dames-contre-dames n'est PAS modélisée. Quelques
positions « gagnantes » seraient nulles en partie réelle. Limitation connue,
acceptable (Scan/Kingsrow l'utilisent ainsi en pratique).

## Plan de validation (saveur réelle, sur boxe)

1. **Cross-check tables internes** : sur toutes les positions K-vs-K / 2v1 / 3v1
   que `bitbase.cpp` résout déjà, la sonde egdb DOIT donner le **même** WLD.
   Tout désaccord = bug de mapping (point #1/#2). C'est le garde-fou le plus
   fort avant d'élargir aux positions avec hommes.
2. **Sondes de référence** : un petit jeu de positions de finale connues
   (compositions, finales théoriques men+king) avec WLD attendu.
3. **Perft inchangé** + 6408 tests (la sonde ne change pas la génération).
4. **Elo / autopsie** : A/B avec vs sans base sur des finales — la perte côté
   rois (~3.6) doit chuter ; vérifier 0 régression milieu de jeu.
5. **Self-play seedé finale** (cf Directions A/B) **relabelisé par la base** :
   labels de finale parfaits → re-densification → mesurer si le verrou cède.

## Scope du suivi (boxe / Codex — chantier isolé)

- Vendoriser/builder `egdb_intl` sur la boxe ; récupérer un sous-ensemble de
  base (≤6 pièces d'abord, ~quelques Go) sur le host.
- Confirmer les 6 points VERIFY contre les vrais headers ; ajuster
  `egdb_bridge.cpp`.
- Lancer la validation 1→5 ci-dessus, perft + tests à chaque étape.
- Garde-fou : **rien ne fusionne tant que le cross-check (1) n'est pas vert.**

## État

- **Seam + stubs + hook + CMake + doc** : FAIT (ce commit), build défaut OK
  (6408 tests, perft inchangé, zéro dépendance).
- **Saveur réelle** : skeleton écrit, `VERIFY` en attente d'un host avec la lib
  + les bases. Candidat Codex.
