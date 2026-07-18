> ⚠️ **ARCHIVE — NE PAS PRENDRE COMME CONSIGNE ACTIVE.** Doc historique (ère pré-fit-volume / NNUE).
> Source de vérité unique = [CURRENT.md](../L3_CURRENT.md) (+ docs système : BOUCLE_VIRTUEUSE, SCAN_METHODOLOGY_GAP,
> DIAGNOSTIC_VS_SCAN, BIAIS_FIT_VOLUME, PROGRESSION_LITTERATURE). Conservé pour l'historique seulement. _(Classé archive 2026-06-24.)_

# Session log — 2026-05-20 → 2026-05-24

> Notes de session pour mémoire et passation. Couvre la période depuis
> la reprise du travail (commit `2313bfa runner: heartbeat 0019-…`) jusqu'à
> la décision de geler l'axe corpus + activer l'axe pattern.

---

## TL;DR — état du projet à la fin de session

- **NNUE de référence** : v5 inchangé. `0018-train-with-master-bce/.../nnue-256-128-q.bin` (Cycle 8 BCE hybride). `-812 ELO` vs Scan (bench `0019`), `+304 ELO` vs handcrafted (interne).
- **Search 1.57× plus rapide** grâce à SIMD + accumulator incrémental, parité bit-identique préservée.
- **Pattern infrastructure** posée (C++ `PatternNetwork`, format JPAT, trainer Python) mais non-compétitive avec le training setup actuel.
- **Axe corpus jugé exhausté** : Cycle 9 1M v5-labelled = tie vs v5 au depth 10. Le 10M (€700+) gelé définitivement.
- **Axe architecture (pattern Scan-style)** : démontré viable mais nécessite un training pipeline plus sophistiqué. Direction prioritaire pour la suite — voir `docs/PATTERN_ROADMAP.md`.

---

## Travaux mergés sur main

### Infrastructure runner

| PR | Contenu | Impact |
|---|---|---|
| #62 | `JASS_HOST_FILTER` env var pour multi-host coordination | Permet 2× CCX23 sans race |
| #63 | GitOps `kill-in-flight` flag dans `runner.py` | Stop un job sans SSH (sauve une session bloquée 6h sur Scan) |
| #66 / #67 | Templates 0023 (book diag) + 0024 (FMJD probe) | Outils diag |
| #68 | Pipeline Cycle 9 pilote (0025a/27/28) | Premier vrai cycle relabelling |
| #70 / #71 / #74 | Workflow: kill+re-scope+unblock du pilote stuck à filtre | Workaround sans SSH |
| #76 | Activation pattern v1 + bigger-arch | Lancement axe architecture |
| #77 | Recovery bigger-arch après OOM 2048-1024 | Récup les 512-256 et 1024-512 |
| #79 | Pattern v2 pure-WDL last shot | Validation négative training setup |

### NNUE core

| PR | Contenu | Impact mesuré |
|---|---|---|
| #73 | **SIMD column-major W1 + AVX2 Layer 1** | 2.11× raw eval (469K vs 214K evals/s) |
| #73 | **Incremental accumulator end-to-end** (Engine wiring inclus) | **1.57× search** à depth 12, bit-identique |
| #75 | **PatternNetwork infrastructure** (JPAT format, default_v1) | Foundation pour axe pattern |
| #78 | **PatternNetwork v2** (16×8, full coverage) | Scan-class scale, training pas convergent |

### Cleanup / méthodo

| PR | Contenu |
|---|---|
| #72 | (fermée sans merge — contenu déjà dans #73 via cherry-pick) |
| `docs/ANALYSE_VEILLE_NNUE.md` | Critique méthodo posée par le mainteneur — direction patterns |

---

## Jobs queue exécutés cette session — verdicts

### Cycle 9 pilote (axe corpus)

| Job | Wall | Verdict |
|---|---|---|
| **0019-calibrate-vs-scan-fair** | ~75 min | v5 vs Scan : 0.009 (`-812 ELO`). Pattern : 100% défaites par "no legal move". |
| **0022-build-master-book-and-calibrate** | ~90 min | Master-frequency book = même résultat 0/53/1. |
| **0023-master-book-vs-scan-no-book** | ~80 min | Master-book vs Scan-sans-book = même 0/53/1. **Réfute "Scan's book domine"**. |
| **0029-diag-book-jass-vs-jass** | ~30 min | Book neutre en jass-vs-jass (W=8 L=7 D=3, rate 0.528). Le book n'est PAS le bug. |
| **0025a-cycle9-pilot-host-a** (100K @ depth 16, v5-labelled) | ~26 h | Génération propre. |
| **0025a-1-train-cycle9-pilot** | ~68 min | Best arch émergente : **512-256** (différente de v5's 256-128). |
| **0025a-2-bench-cycle9-vs-v5** | ~30 min | **d6=0.639, d10=0.500 (tie 18-18-18)**. Cycle 9 marginal au depth qui compte. |

### Architecture (axe pattern et MLP plus gros)

| Job | Wall | Verdict |
|---|---|---|
| **0025a-3-train-pattern-v1** (8×4, 5K weights) | ~30 min | 0/54 partout (sous-paramétré, training pas converge). |
| **0025a-4-train-bigger-arch** | ~90 min | OOM sur 2048-1024 ; 512-256 et 1024-512 trained OK. |
| **0025a-5-bench-bigger-arch-recovery** | ~30 min | 512-256 vs v5 d10 = 0.417 (regression). 1024-512 vs v5 d10 = 0.444 (régression aussi). |
| **0025a-6-train-pattern-v2** (16×8, 6.25M weights) | ~6 min train + bench | 0/54. val_mse plat à 91M = "always predict 0". |
| **0025a-7-train-pattern-v2-wdl-only** | ~3 min train + bench | **3/54 vs v5 d6 (rate 0.056)**. val_mse 91M→81M. **Archi viable, training sous-tuné**. |

### Diagnostic / probes

| Job | Notes |
|---|---|
| **0024-probe-fmjd-spa** | Trouvé endpoint `fmjd.space/game_open.php` (autre domaine). Scraping FMJD reste à coder. |

---

## Décisions importantes prises

1. **10M Cycle 9 gelé** — €700-1000 pour gain attendu +30-80 ELO contre un déficit de 800 vs Scan. Mauvais ROI confirmé par le tie à depth 10 sur le pilote 100K.
2. **Multi-host CPU non-priorisé** — sans 2e CCX23 sur le compte, pas activé. Templates dormants disponibles si retour.
3. **Approche eval-server GPU abandonnée** — IPC overhead Unix socket = 46.6 μs/call vs 2.6 μs in-process. Pas viable pour alpha-beta sériel. Code conservé en docs.
4. **MCTS-only repo (jams) abandonné** — budget compute trop élevé pour les retours attendus à court terme. README rédigé et conservé en cas de retour.
5. **Pattern axis priorité après session** — la seule direction non-exhaustée qui peut casser le plafond -812 vs Scan.

---

## Coût total session

- Hetzner CCX23 (1 host) : ~5 jours d'usage en continu = ~€8
- Aucun autre coût compute (pas de GPU, pas de CPX62 ajouté)
- **Total : ~€10**

Pour comparaison, le 10M aurait coûté €700-1000.

---

## Branches obsolètes au moment de cette session

Ces branches contiennent du travail soit déjà mergé soit superseded :

- `claude/nnue-simd-int8` → mergé via #73 (cherry-pick)
- `claude/nnue-incremental-scaffold` → mergé via #73
- `claude/nnue-eval-server` → contenu intégré dans la consolidation finale
- `claude/cycle9-10M-templates` → templates dormants intégrés dans la consolidation
- `claude/cycle9-depth10-experiment` → templates dormants intégrés dans la consolidation
- Les `claude/resume-*` et `claude/setup-github-project-*` → fragments historiques

À nettoyer dans une session de housekeeping ultérieure (pas critique).

---

# Annexe — 2026-05-24 → 2026-05-26 : post-biblio + diagnostic pattern

> Suite de la session précédente après réception de la bibliographie
> annotée (`docs/REFERENCES_BIBLIOGRAPHIE.md`). Recadrage de l'ordering
> via `docs/ROADMAP.md` : phases data-side AVANT bascule archi pattern.

## Axe data — succès franc

| Run | Recipe | vs handcrafted | vs v5 d6 | vs v5 d10 | ELO Δ vs v5 |
|---|---|---|---|---|---|
| **0043** | quiet filter 200K (Phase 0) | **1.000** | 0.472 | **0.639** | **+99** |
| **0045** | quiet + pv-extract 500K (v6) | 0.861 | **0.722** | 0.556 | +39 d10, +165 d6 |

**Verdict consolidé** : la biblio avait raison sur le précédent TalkChess. Le quiet filter est LA réponse à la suspicion d'archi plafond. v6 est shippé (PR #89, `docs/RELEASE_NOTES.md`) comme référence pour tous les futurs gen-data et benchs.

PRs cette phase : #81 (`--quiet-only`), #82 (activate 0043), #84 (`--pv-extract`),
#85 (0045 standby), #87 (activate 0045), #89 (ship v6 + D1).

## Axe pattern — diagnostic blitz exhaustif, conclusion honnête

Plan diagnostic D1/D2/D3 issu de la lecture de `rhalbersma/scan/src/eval.cpp`
(`docs/SCAN_ARCHITECTURE_NOTES.md`). 4 expériences supervised sur
l'archi pattern v2 (16 × 8 squares) :

| Run | Recipe | vs hc | vs v5 d6 | vs v5 d10 |
|---|---|---|---|---|
| 0046 | Phase 1 pure pattern | 0/18 | 0/54 | 0/54 |
| 0047 | Phase 1 + quiet data (D3) | 0/18 | 0/54 | 0/54 |
| 0048 | D1 hybrid (skeleton material+king) | 0/18 | **6/54** | 0/54 |
| 0049 | D2 hybrid + base-3 (Scan-aligned) | 0/18 | 1.5/54 | 0/54 |

**Conclusion factuelle** : aucune des 4 expériences supervised n'atteint
le decision gate Phase 2 (rate vs v5 d10 ≥ 0.30). Le meilleur, D1 hybrid
base-5, plafonne à 6/54 à d6 et 0/54 à d10. Les paramètres structurels
trainables (man_value, king_value) convergent vers EXACTEMENT les mêmes
valeurs entre D1 et D2 (30.7 / 228.2), preuve que le trainer trouve le
même minimum local : *minimiser MSE en réduisant le skeleton vers des
valeurs qui collent au bruit des labels*.

**Pattern axis frozen** pour cette session. Le gap méthodologique vs
Scan (TD-leaf + RL + décennies de feature engineering) est trop large
pour être franchi par du supervised cheap. Voir
`docs/SCAN_METHODOLOGY_GAP.md` pour le plan itératif de fermeture du
gap si on décide d'investir Phase 2+ ultérieurement.

PRs cette phase : #83 (doc accumulator), #86 (Phase 1), #88 (SCAN notes
+ D3), #89 (D1 hybrid), #90 (D2 base-3).

## Suite décidée

1. **0050 v7** = 1M complet quiet+pv-extract (extrapolation v5/v6, gain
   attendu +20-50 ELO vs v6).
2. **Phase 0b master volume** (Lidraughts refresh, FMJD scrape) en
   parallèle quand budget dev.
3. **Pattern axis re-tenté** seulement avec un leverage nouveau (TD-leaf,
   knowledge distillation depuis v7, ou pattern geometry alignée Scan).
   Détail dans `docs/SCAN_METHODOLOGY_GAP.md`.

## Coût compute cumulé annexe

- 0043 gen 200K : ~24h × 4 vCPU CCX23
- 0045 gen 500K : ~18h × 4 vCPU
- 0046/0047/0048/0049 train+bench : ~1.5h chacun = 6h × 4 vCPU
- **Total annexe : ~€5-6**

Cumulé session 2026-05 entière : **~€15-16**. Référence : 10M @ depth-20
seul aurait coûté €700-1000.
