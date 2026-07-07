# CLAUDE.md — instructions permanentes (lues à CHAQUE session, en premier)

> **Source de vérité technique = [`docs/CURRENT.md`](docs/CURRENT.md)** (lire en premier à chaque session).
> Règles de méthode permanentes = [`docs/SCAN_METHODOLOGY_GAP.md`](docs/SCAN_METHODOLOGY_GAP.md).

## ⛔ RÈGLES OPÉRATIONNELLES JFC — non négociables

### 1. ⏱️ TIMING AVANT LANCEMENT (répété plusieurs fois par JFC — 2026-07-07)
**AVANT de queuer TOUT job (ou batch de jobs) sur les box (cpx62 / ccx33), TOUJOURS, dans cet ordre :**
1. **Pré-estimer le runtime**, ANCRÉ sur la durée réelle `start→finalize` d'un job COMPARABLE déjà tourné — jamais « au doigt mouillé ».
2. **Faire VALIDER l'estimation + le sizing par JFC AVANT de queuer.** Ne rien lancer sans (pré-estimation chiffrée + go explicite).
3. **Sizer LÉGER par défaut** (retour rapide < ~30-45 min) ; n'escalader le N / volume / movetime que sur demande explicite.

**Repères de durée mesurés (à ré-ancrer au fil du temps) :**
- `calibrate_vs_scan` (d9 + mt0.3 + survie, N~1300 games) ≈ **2h** ; la cellule **mt1.0 = goulot ~4h** ; **movetime + gros-N = très lent** (0636 : 5h+).
- A/B `jass_vs_jass_arch` 4 cellules, N~1500/cellule, mt0.2-0.3 : ≈ **1h45 sur cpx62**, ≈ **2×** sur ccx33 (8 cœurs).
- MMTO gen-siblings `--leaf-mode` + fit (~50-100k parents) ≈ **5-15 min** ; gros self-play Scan (~10k parties) ≈ **2-5h**.
- ⚠️ `rank_finetune` **OOM au-delà de ~1.5M paires sur ccx33** → cap paires / subsample, gros corpus sur cpx62.
- Les jobs `calibrate_vs_scan` / A/B ne committent le RESULTS **qu'à la fin** (pas de partiel fiable) ; cellules multi-parts souvent tronquées dans RESULTS → **lire `output.log`** au finalize.

### 2. Autres règles gravées
- **⛔ AUCUN NNUE / réseau / changement de classe** tant que le linéaire n'est pas poussé à fond (cf SCAN_METHODOLOGY_GAP §0).
- **Code sur `develop`** (jamais main pour le code) ; **queue de jobs sur `main`**. Le runner exécute les jobs `jobs/queue/<box>-NNNN-*.sh` par prefix de box.
- **Bake (éval ou search) = promotion délibérée sur `main`, uniquement sur go explicite de JFC.** Réversible (archiver l'ancien champion).
- Commits vers main/develop via plumbing `read-tree origin/<ref>` + `commit-tree` + `push` (cf `commit_to_main` dans les jobs).
- Champion éval courant : voir le bloc en tête de `docs/CURRENT.md` (au 2026-07-07 : **gen2-mmto**).

### 3. Style de collaboration
- JFC pilote au tour par tour, en français, statuts courts. Répondre concis, chiffres d'abord.
- Ne pas re-pinger « ça tourne encore » sans info neuve. Sortir le verdict au finalize.
