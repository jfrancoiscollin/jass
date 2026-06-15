# Movegen optimization — terrain préparé (audit + plan)

> Rédigé 2026-06-15. Le movegen est **~31 % du temps/nœud** (mesuré, job 0095 :
> eval 26 % · movegen 31 % · « other » 41 % · apply 3 %), le 2e plus gros poste
> et le plus structurellement améliorable. Ce doc consigne l'audit du code, le
> plan priorisé, et le **garde-fou perft** non-négociable. Sert de spec pour un
> executor (Codex) : je fournis ce plan, je vérifie chaque PR par perft + Elo.

## Cadrage honnête (lire avant de coder)

- **Upside borné** : l'ensemble des 7 leviers ≈ **−20 à −37 % du temps movegen** =
  **+6 à +11 % NPS** (movegen n'est que 31 % du nœud ; Amdahl). PAS un ×N.
- **Et le NPS plafonne en Elo** tant que l'éval plafonne (`rate(depth)` plat
  au-delà de ~d9-11, job 0188). → **Faire le movegen quand l'éval respire**, pas
  en priorité. Mais c'est du gain réel, sans risque sur la classe d'éval.
- **Correctness > tout** : un bug movegen corrompt SILENCIEUSEMENT toute la
  recherche. **Chaque changement DOIT passer perft** (comptage de coups par
  profondeur, comparé à la version actuelle) + une régression de partie (Elo vs
  baseline, pas de coup illégal). Voir §Garde-fou.

## Mesurer AVANT d'optimiser (job 0271)

On sait movegen = 31 % global mais PAS la répartition interne. L'instrumentation
existe déjà (`-DJASS_TIME_BREAKDOWN` → `movegen_capture_ms` / `movegen_quiet_ms`,
`BD_TIME` à `movegen.cpp:161/209`). **`ccx33-0271-movegen-profile`** build avec le
flag et profile des positions **stratifiées par phase** (ouverture/milieu/finale-
à-rois) → split **capture-DFS vs quiet** par phase. Ça dit quel levier attaquer en
premier (hypothèse : la **DFS de captures** domine ; en finale, le **movegen rois**
monte). **Ne rien coder avant ce profil.**

## L'audit — 7 leviers (priorisés)

Le cœur du coût = la **DFS de captures** (rafle maximale obligatoire, l'intrinsèque-
ment cher en dames), qui fait des **lookups de table par direction**
(`neighbour()` / `king_ray()`) **répétés à chaque niveau de récursion**.

| # | Levier | Fichier | Gain movegen | Risque |
|---|---|---|---|---|
| **1** | **Captures-hommes** (`extend_man_captures`) : remplacer les `neighbour()` ×2/dir/récursion par des **masques bitboard** (`captures_in_dir = (shift(cur)&enemy&~captured) & (shift²(cur)&~occ)`), itérer `pop_lsb`. | `movegen.cpp:86-114` | ~8-12 % | **MEDIUM** (math de masques brick-layout ; bug = mauvaise case d'arrivée = coup illégal) |
| **2** | **Captures-rois** (`extend_king_captures`) : calculer les cases d'arrivée en **un masque** (`land_ray & ~occ`) au lieu de `landing_blocked` ×N en boucle. | `movegen.cpp:116-158` | ~5-8 % | MEDIUM (gestion `from_sq` + blocage par pièce capturée) |
| **3** | **Skip-check par pièce** : avant `extend_*_captures`, court-circuit « cette pièce peut-elle vraiment sauter ? » (`reach_all_dirs(from)&enemy` + case d'arrivée libre). Évite init+DFS pour les pièces « menaçantes mais bloquées » (30-50 % en milieu encombré). | `movegen.cpp:188-205` | ~3-6 % | **LOW** (pur court-circuit, ne change pas le résultat) |
| **4** | **Quiet hommes** : **promotion-rows précalculées en bitboard** (`d0 & PROMO_ROW_W`) au lieu de `is_promotion_square()` par coup ; source par shift inverse au lieu de `neighbour()`. | `movegen.cpp:208-241` | ~1-3 % | LOW |
| **5** | **Quiet rois** : itérer un **masque ray&empty** (stop au 1er bloqueur) au lieu de `test(occ,to)` par case. Surtout utile en finale (rois). | `movegen.cpp:243-260` | ~0.5-2 % | LOW-MEDIUM |
| **6** | **MoveList** : `reserve()` la capacité en amont (`gen_moves`, `search.cpp:71`) ; `emplace`/push direct au lieu de construire un `Move` temporaire. | `movegen.cpp:77-83` + `search.cpp` | ~0.5-1 % | LOW (aucun risque correctness) |
| **7** | **Règle de majorité** : éviter le `clear()` de la liste pendant la DFS quand une rafle plus longue apparaît (2 listes / 2 passes). | `movegen.cpp:71-83` | ~2-5 % | MEDIUM (seul levier qui touche la SÉLECTION des coups) |

**Ordre recommandé** : commencer par **#3 + #6** (LOW risque, court-circuits/alloc,
gain immédiat sans toucher la logique de capture), valider perft, PUIS attaquer
**#1** (le gros, MEDIUM risque) une fois le profil 0271 confirmant que la DFS
captures domine. #7 en dernier (touche la sélection).

## Ce que fait un movegen dames RAPIDE (Scan/Kingsrow) — la cible

Précalcul bitboard lourd (séquences de rayons, masques de voisinage), génération
**captures-first étagée** (les captures étant obligatoires, si une capture existe
les coups calmes ne sont jamais générés — déjà le cas ici via le `return` quand la
liste de captures est non vide), **zéro allocation par nœud**. Notre écart = les
lookups de table répétés dans la DFS (vs masques bitboard) + l'alloc MoveList.

## Garde-fou — protocole de validation OBLIGATOIRE par changement

1. **Perft** : comptage de coups par profondeur sur un jeu de positions de
   référence, **identique bit-à-bit** à la version actuelle (avant/après). Tout
   écart = bug. (Ajouter un mode `--perft <fen> <depth>` si absent.)
2. **`jass_tests`** : les 6408 assertions passent.
3. **Régression Elo** : A/B vs baseline (mêmes éval/search) — **0 régression** ET
   0 coup illégal en N parties. Le gain de vitesse doit se voir en profondeur
   atteinte (`--depth-at-movetime`) sans changer le résultat à profondeur fixe.

## État

- **Mesure** : `ccx33-0271-movegen-profile` (en file) → split capture/quiet par phase.
- **Optims** : non commencées (en attente que l'éval respire + du profil 0271).
- **Candidat Codex** : chantier isolé, spec ci-dessus, vérif par perft + Elo.
