# CLAUDE.md — instructions permanentes (lues à CHAQUE session, en premier)

> **État vivant L3 = [`docs/L3_CURRENT.md`](docs/L3_CURRENT.md)** (lire en premier à chaque session).
> Spécification normative = [`docs/L3_PURE_PLAN.md`](docs/L3_PURE_PLAN.md).
> Résultats acquis et portes closes = [`docs/PROJECT_RESULTS.md`](docs/PROJECT_RESULTS.md).
> Les autres Markdown de `docs/archives/` sont historiques et ne doivent plus être mis à jour.

## ⛔ RÈGLES OPÉRATIONNELLES JFC — non négociables

## ✅✅ CHECK-LIST PRÉ-LANCEMENT COMPLÈTE — À VÉRIFIER À CHAQUE JOB (JFC 2026-07-10, « trop de gâchis »)
> **Rien ne part sans avoir coché CES 12 points, dans cet ordre. Trop de compute gâché (0664 sur-sizé, 0665 mis-sizé nproc PUIS hung 2h11, 0659 timeout culé n=0, 0657 hung). Chaque point vient d'une bourde réelle payée en heures.** Coller le résultat des checks dans le rapport à JFC.
>
> **A. SIZING (ne pas gâcher par le volume)**
> 1. **`nproc` RÉEL de la box cible** connu (volume = `PERG × nproc`). Ancres MESURÉES : cpx62 = **16** (0666 imprime `×16`), ccx33 = **8**. *(NB : j'ai flotté 16↔32 sur cpx62 par sur-inférence d'un ratio shard bruité ; la VALEUR IMPRIMÉE par le job `NCPU=$(nproc)` fait foi, pas une déduction.)*
> 2. **RATE mesuré sur la box réelle** (micro-sonde `PERG=200`/1 shard, OU lu d'un PROGRESS/RESULTS comparable récent). Mesuré, pas déduit. Ancre self-play gen-data-wdl d10+qs ≈ **~300 kept/min/shard** (cpx62).
> 3. **ETA CHIFFRÉE** = `volume ÷ rate` + build + fit + gate, **sortie à JFC avec le nproc + rate qui la fondent**.
> 4. **SIZER LÉGER** (retour < ~30-45 min par défaut ; escalade sur demande explicite seulement).
>
> **B. ROBUSTESSE RUNTIME (ne pas gâcher par un hang / une traîne)**
> 5. **`timeout` PAR SHARD sur TOUTE génération/A-B parallèle** — un shard bloqué ne DOIT jamais geler le job entier (0665/0657 hung). Le job doit atteindre fit/gate avec ce qui a fini.
> 6. **`timeout` CALIBRÉ sur la box LENTE** = `temps_shard_sain × ~1.3` (marge). **Trop court = cellules culées à n=0** (0659 sur ccx33 : baseline n=0). Trop long = on subit la traîne. Calculer depuis le rate (point 2), pas copier d'une box rapide.
> 7. **MONITOR de progress committé /~10 min** (compteurs + ETA restante). Jamais dark (0665 tour-0 dark 89 min avant kill). **⚠️ PIÈGE MONITOR+`wait` (bug 0665/0666/0668, prouvé rc=124) : un `wait` NU attend TOUS les enfants, MONITOR COMPRIS → le monitor boucle jusqu'à `.stopmon` posé APRÈS le `wait` = DEADLOCK circulaire (la génération FINIT mais le job ne dépasse jamais le `wait`). FIX OBLIGATOIRE : collecter les PID des shards (`pids+=($!)`) et `wait "${pids[@]}"` — jamais `wait` nu quand un monitor tourne en fond.**
> 8. **Savoir si l'outil écrit INCRÉMENTAL ou EN FIN DE SHARD** : `gen-data-wdl`/`scan_selfplay_gen` écrivent **en fin de shard** → aucun harvest partiel, aucun kill propre mid-run → **sizer JUSTE + timeout** (points 4-6).
> 8bis. **🧹 HYGIÈNE DISQUE OBLIGATOIRE (ccx33 rempli à 100% le 2026-07-11 → runner MORT + 0670 bouclait + reset password KO → 2h de récup en rescue).** ccx33 = **152 Go seulement** (cpx62 = 640 Go). **En tête de CHAQUE job** : (a) **garde `df`** (abort si `/root` libre < ~3-5 Go) ; (b) **auto-clean des scratch stale** — coller après le `W=…` :
> ```bash
> find /root -maxdepth 1 -name 'cw-*' -type d -mmin +180 ! -path "$W" -exec rm -rf {} + 2>/dev/null || true  # vire les cw-* >3h (jamais le sien, protégé par mtime)
> DFA=$(df -Pm /root|awk 'NR==2{print $4}'); [ "${DFA:-0}" -gt 3000 ] || { say "ABORT disque <3Go"; exit 3; }
> ```
> Les jobs qui MEURENT laissent leur `cw-*` (le `rm -rf "$W"` de fin ne tourne pas) → ça s'accumule → disque plein. L'auto-clean au start de chaque job vide les stale au fil de l'eau. Jobs de maintenance `NNNN-diskclean` à re-queuer si pression disque.
> 8ter. **📄 RES/PROG DANS `$W` (HORS ARBRE GIT), JAMAIS DANS `$ART` (bug reporting résolu 2026-07-11 : 0670 RESULTS vide, 0674 lag, 0675 verdict PERDU).** Le runner tourne les jobs en DÉTACHÉ ; un job long traverse ~N ticks du runner (/5min) et **chaque tick fait une sync git (`reset --hard origin/main`) qui RÉINITIALISE l'arbre de travail** → un `RESULTS.txt` écrit dans `$ART` (=`jobs/results/.../`, DANS le repo) est **remis à la dernière version committée** → les `say()` post-census sont EFFACÉS avant le commit final. **FIX** : `RES="$W/RESULTS.txt"; PROG="$W/PROGRESS.txt"` (dans le scratch `$W`, HORS repo) ; `commit_to_main` fait `git hash-object "$RES"` qui marche sur n'importe quel chemin → committe au bon `$rel` sans que le fichier-source soit clobbé. **+ ceinture-bretelles** : mettre le verdict-clé dans le **message de commit** (`commit_to_main ... "0675 FIN gate=$(cat $W/.verdict) rate=..."`) — les messages ne sont JAMAIS clobbés.
>
> **C. REPORTING (ne pas gâcher le run par un bug de report)**
> 9. **SMOKE-TEST write→read round-trip** sur mini-échantillon : le parser lit ce que le job écrit (mêmes clés/format/N). `bash -n` + `py_compile` des heredocs.
> 10. **n=0 (ou n < plancher) = ÉCHEC, PAS « neutre »** : tout parseur A/B/gate doit **crier ABORT/INCONCLUANT** si une cellule n'a pas produit ≥ N_min parties (0659 a rapporté « neutre » sur n=0 = faux signal). **Baseline symétrique doit sortir ~0.5 avec n>0** (sanity harnais) sinon le job est cassé.
>
> **D. ARCHI + GO**
> 11. **GARDE-FOU ARCHI** : pull explicite `scan_eval/search/movegen` d'une ref connue + `arch_assert` (g_emasks + has_any_capture) AVANT `cmake` (cf §4).
> 12. **GO EXPLICITE JFC** sur (ETA chiffrée + sizing) — seulement ensuite queuer.

### 1. ⏱️ TIMING AVANT LANCEMENT (répété plusieurs fois par JFC — 2026-07-07)
> **🖥️ BOX PAR DÉFAUT = `cpx62` (JFC 2026-07-31) — HOME est OUT.** Tout nouveau job se queue en `cpx62-NNNN-*.sh`. Le runner sélectionne par **prefix de nom de fichier**, donc un job nommé `home-*` ne sera jamais réclamé et restera en file indéfiniment (`home-1111` y est resté avant d'être renommé).
> ⚠️ **Les ancres de rate ne se transportent pas d'une box à l'autre.** Les repères ci-dessous mesurés sur HOME (`home-1003/1004` : 9 804 pos/min/shard à d8, 2 519 à d9, sur 16 shards) valent pour HOME, pas pour cpx62. Sur cpx62, **re-mesurer** (micro-sonde ou PROGRESS d'un job cpx62 comparable) avant toute ETA — c'est le point 2 de la check-list, et le transport aveugle d'une ancre est exactement la bourde 0665.

**AVANT de queuer TOUT job (ou batch de jobs) sur les box (cpx62 / ccx33), TOUJOURS, dans cet ordre :**
1. **Pré-estimer le runtime**, ANCRÉ sur la durée réelle `start→finalize` d'un job COMPARABLE déjà tourné — jamais « au doigt mouillé ».
2. **Faire VALIDER l'estimation + le sizing par JFC AVANT de queuer.** Ne rien lancer sans (pré-estimation chiffrée + go explicite).
3. **Sizer LÉGER par défaut** (retour rapide < ~30-45 min) ; n'escalader le N / volume / movetime que sur demande explicite.

**✅ CHECK-LIST PRÉ-LANCEMENT MÉCANIQUE (obligatoire, dans l'ordre — 2026-07-10, après ma bourde 0665) :**
> Bourde 0665 : sizé `PERG=45000` en supposant « ×16 cœurs ≈ 720k », or **cpx62 = ~32 cœurs → 1,4M réel** → ETA annoncée 45-70 min vs ~3,5h réel. La cause = **volume/durée jamais calibrés sur la box réelle**. Cette check-list rend l'étape non-sautable :
> 1. **CONNAÎTRE `nproc` de la box cible** (le volume total = `PERG × nproc`, jamais un nproc supposé). Ancres : **cpx62 ≈ 32 cœurs**, **ccx33 ≈ 8-16 cœurs** (vérifier).
> 2. **MICRO-CALIBRER le rate sur la box réelle** avant le vrai run : soit un job-sonde minuscule (`PERG=200`, 1 shard, mesurer sec→pos), soit lire le rate d'un PROGRESS/RESULTS d'un job COMPARABLE récent. **Rate mesuré, pas déduit.**
> 3. **CALCULER l'ETA chiffrée** = `volume_total ÷ rate_mesuré` (+ build + fit + gate), et la sortir à JFC **avec le nproc et le rate qui la fondent**.
> 4. **VALIDER avec JFC** (go explicite) — seulement ensuite queuer.

**Repères de durée mesurés (à ré-ancrer au fil du temps) :**
- **Self-play `--gen-data-wdl` d10 + qs pleine (0665, cpx62 ~32 cœurs)** : ≈ **~7,3k pos KEPT/min au total** (≈ ~230 pos/min/shard) → 720k ≈ ~98 min, 1,4M ≈ ~3,2h. **DIMENSIONNER `PERG` par ce rate × nproc réel.** Le monitor PROGRESS committe l'octet-count des shards /10 min (rate live).
- `calibrate_vs_scan` (d9 + mt0.3 + survie, N~1300 games) ≈ **2h** ; la cellule **mt1.0 = goulot ~4h** ; **movetime + gros-N = très lent** (0636 : 5h+).
- A/B `jass_vs_jass_arch` 4 cellules, N~1500/cellule, mt0.2-0.3 : ≈ **1h45 sur cpx62**, ≈ **2×** sur ccx33 (8 cœurs).
- MMTO gen-siblings `--leaf-mode` + fit (~50-100k parents) ≈ **5-15 min**.
- **⚠️ Self-play Scan — YIELD ré-ancré (0638, ma sur-estimation ×3)** : asym-conversion mt0.3/0.03 ≈ **~20 parents/partie** (PAS 5,7), ~45 s/partie effectif (8 shards) → **10400 parties ≈ ~8h, ~200k+ parents** ; équilibré fort-vs-fort ≈ **~116 parents/partie** (0630). **DIMENSIONNER PERG PAR LE YIELD** : parties = parents_cible ÷ (parents/partie) (ex. 60k parents asym ≈ **~3000 parties ≈ ~2h**, pas 10400). `scan_selfplay_gen` écrit les pref **SEULEMENT en fin de shard** (aucun checkpoint, aucun kill propre mid-run) → **bien sizer PERG AVANT de lancer**.
- ✅ `rank_finetune --chunk N` = **fit STREAMÉ (gradient EXACT chunké, byte-identique au full-batch, vérifié)** → **plus d'OOM** quel que soit le volume (jusqu'aux millions de paires). L'ancien OOM (~1.5M paires ccx33) est levé. (Full-batch `--chunk 0` reste le défaut pour les petits corpus.)
- ✅ **BUG ENGINE `go movetime` — RÉSOLU ET BAKÉ le 2026-07-31 (`16f8c151`).** Cause : la bitbase **3-dames-contre-1** (50⁴×2 entrées) était construite par rétro-analyse **à la première sonde, DANS `negamax`**, sous un `std::call_once` que la sonde de deadline ne peut pas interrompre. Coût mesuré : **5,15 s** (2v1 : 280 ms). Mesure sur `W:WK46,K47,K48:BK3,K4,K5` : `go movetime 100` rendait après **5558 ms = 55×** (pas 2-3,5×), à depth 3, 2048 nœuds — d'où ~370 nœuds/s, ce qui explique pourquoi tester 0x3FF→0xFF n'avait rien donné (on est **garé dans un `call_once`**, pas en train de compter des nœuds). **Ce n'était pas qu'un bug de temps** : le moteur rendait `depth=3 score=164` (il se croyait gagnant) là où la version préchauffée atteint `depth=20 score=0`. **Le PREMIER coup, PAR PROCESSUS moteur, qui descendait dans une telle finale était décidé sur une recherche tronquée à la profondeur 3** — une seule fois, `call_once` réchauffant tout le reste du processus (mesuré : `go` #1 = 3861 ms depth 3, #2 = 85 ms depth 17, #3 = 40 ms depth 18). Fix : `warm_kings_endgame_bitbases()` appelé au handshake HUB, après le flush de `ready`. Résultat 55,58× → **1,01×**. Déterminisme intact (`go depth 4` : `nodes=4314`, `bestmove 46-41`, identiques avant/après).
  - ✅ **CONSÉQUENCE SUR L'HISTORIQUE — MESURÉE, ET FAIBLE.** Exposition : 2 moteurs par shard × 12-16 shards, soit **≤ ~32 coups touchés par cellule** sur 3000-5000 parties (~0,3-0,6 % des parties, un coup chacune). Et le canal « nulles fabriquées » **n'a jamais tiré** : `game skipped` compté à **0** sur `home-1040`, `1008`, `1091`, `1108` et `1102` — le `--game-timeout` est à 180 s, un blocage de 5,4 s ne l'approche pas. **Aucun verdict n'est remis en cause.** Les mesures antérieures ne sont pas byte-comparables, mais l'écart est négligeable. Voir [`docs/experiments/L3_MOVETIME_ENDGAME_BAKE_20260731.md`](docs/experiments/L3_MOVETIME_ENDGAME_BAKE_20260731.md).
- Les jobs `calibrate_vs_scan` / A/B ne committent le RESULTS **qu'à la fin** (pas de partiel fiable) ; cellules multi-parts souvent tronquées dans RESULTS → **lire `output.log`** au finalize.

### 2. 📊 PROGRESS AU FIL DE L'EAU (JFC — 2026-07-07)
Quand un job tourne, fournir des **premières estimations EN CONTINU** dès que possible — surtout pour les jobs d'estimation sur des **PARTIES** ou des **DONNÉES**. À défaut de streaming, donner des **estimations de durée RESTANTE**. Concrètement, CONCEVOIR les jobs pour :
- Émettre un progress **incrémental committé à intervalles** (compteurs : parties jouées / positions / paires générées, rate A/B provisoire, ETA) — **pas uniquement au finalize**. (progress.json / RESULTS partiel / `--progress-file` de `jass_vs_jass_arch`.)
- A/B : committer **chaque cellule dès qu'elle finit** + un tally courant.
- Génération : logger/committer « N/total parties, X paires, ETA » tous les K.
- Côté reporting à JFC : dès qu'un partiel existe, sortir une **première estimation** plutôt que « ça tourne encore ».
- **📌 `docs/L3_CURRENT.md` TENU À JOUR AU FUR ET À MESURE** : dès qu'un job L3 finalise, renseigner ses compteurs, résultats et décision — **pas seulement en fin de campagne**. Un résultat qui clôt ou rouvre une famille doit aussi mettre à jour `docs/PROJECT_RESULTS.md`.

### 3. 🧪 SMOKE TEST DES FORMATS DE REPORTING AVANT LANCEMENT (JFC — 2026-07-07)
Pour éviter les **erreurs de reporting** (troncature RESULTS, variable non-liée, cellules perdues, format écriture ≠ lecture — ça nous a coûté plusieurs runs), TOUJOURS **smoke-tester AVANT de queuer** :
- Faire tourner une **version minuscule** (peu de games/positions) OU vérifier explicitement que l'**écriture ET la lecture/parsing** des fichiers de reporting **round-trip** (le parser lit bien ce que le job écrit : mêmes clés, même format, mêmes N attendus).
- `bash -n` (syntaxe) + `py_compile` des heredocs + test du couple **write → read** sur un mini-échantillon.
- **Ne queuer qu'après** le round-trip write→read validé.

### 4. Autres règles gravées
- **⛔ AUCUN NNUE / réseau / changement de classe** tant que le linéaire n'est pas poussé à fond (cf SCAN_METHODOLOGY_GAP §0).
- **Code sur `develop`** (jamais main pour le code) ; **queue de jobs sur `main`**. Le runner exécute les jobs `jobs/queue/<box>-NNNN-*.sh` par prefix de box.
- **Bake (éval ou search) = promotion délibérée sur `main`, uniquement sur go explicite de JFC.** Réversible (archiver l'ancien champion).
- Commits vers main/develop via plumbing `read-tree origin/<ref>` + `commit-tree` + `push` (cf `commit_to_main` dans les jobs).
- Champion historique de référence : **gen2-mmto**. Student/champion L3 courant : voir `docs/L3_CURRENT.md`.
- **🛡️ GARDE-FOU ARCHI (obligatoire dans TOUT job qui build — JFC 2026-07-10)** : ne JAMAIS s'appuyer sur l'arbre de base du runner pour les fichiers perf-critiques (silencieusement stale possible). **Pull explicitement `scan_eval.cpp/.hpp`, `search.cpp`, `movegen.cpp/.hpp` d'une ref connue** (`git show origin/develop:<f> > <f>`) **PUIS assert les opts AVANT `cmake`.** 0659 s'appuyait sur l'arbre de base (OK car main==develop ce jour-là, mais fragile) ; 0665 pull explicite (bon patron). Snippet à coller juste avant le build :
  ```bash
  arch_assert(){  # à appeler après les pull develop, avant cmake
    grep -q "g_emasks"        src/scan_eval.cpp || { say "ABORT archi: scan_eval SANS opts NPS (g_emasks)"; restore_src; exit 5; }
    grep -q "has_any_capture" src/search.cpp    || { say "ABORT archi: search SANS has_any_capture"; restore_src; exit 5; }
    grep -q "has_any_capture" src/movegen.cpp   || { say "ABORT archi: movegen SANS has_any_capture"; restore_src; exit 5; }
    say "  garde-fou archi ✓ : scan_eval=g_emasks (dot creux+popcount) + has_any_capture (search+movegen) = NPS-opt"; }
  ```

### 3. Style de collaboration
- JFC pilote au tour par tour, en français, statuts courts. Répondre concis, chiffres d'abord.
- Ne pas re-pinger « ça tourne encore » sans info neuve. Sortir le verdict au finalize.
- **🕑 REPORTING EN HEURE FRANÇAISE (Europe/Paris) — JFC 2026-07-10** : toutes les heures/ETA sorties à JFC en **heure française** (CET/CEST, gérer l'été = UTC+2). Les fichiers/commits/in-flight sont en UTC → **convertir en heure FR avant d'afficher** (préciser « FR » si ambigu). Ne pas rapporter d'heures brutes UTC.
