> ⚠️ **ARCHIVE — NE PAS PRENDRE COMME CONSIGNE ACTIVE.** Doc historique (ère pré-fit-volume / NNUE).
> Source de vérité unique = [CURRENT.md](../L3_CURRENT.md) (+ docs système : BOUCLE_VIRTUEUSE, SCAN_METHODOLOGY_GAP,
> DIAGNOSTIC_VS_SCAN, BIAIS_FIT_VOLUME, PROGRESSION_LITTERATURE). Conservé pour l'historique seulement. _(Classé archive 2026-06-24.)_

# jass — release notes

Historique des NNUE de référence successives. Chaque entrée pointe vers
l'artefact JNNQ canonique du release, le job qui l'a produite, et les
mesures vs la baseline précédente.

> NB : l'eval « embedded default » dans le binaire `jass` (utilisé sans
> `--nnue`) n'est PAS automatiquement mis à jour à chaque release. Pour
> tester la dernière version, charger explicitement le `.bin` via
> `--nnue /path/to/nnue-…-q.bin`. La mise à jour de l'embedded default
> est une étape de release séparée (recompile + tests parity) qui n'est
> faite que quand un release accumule suffisamment de gain pour mériter
> le risque de bump.

-----

## v8 — 2026-05-29 (job 0056-v8-quiet-pv-1M-v7-labeller)

**Artefact** : `jobs/results/0056-v8-quiet-pv-1M-v7-labeller/artefacts.src/nnue-512-256-q.bin`

**Architecture** : MLPNetworkQ **512-256** (saut de capacité vs 256-128 pour v5/v6/v7) HalfMen 450 features, int8 quantifié.

**Dataset** : 1M self-play records @ depth 16, recipe v7 + knowledge bootstrap :
- `--quiet-only` + `--pv-extract 3` (identique v6/v7)
- **Labeller : v7** (au lieu de v5 pour v6/v7) — knowledge bootstrap

**Performance (54 games par bench)** :

| Métrique | v8 (512-256) | v7 (256-128) | v6 |
|---|---|---|---|
| vs handcrafted | 0.833 (15/18) | **0.944** | 0.861 |
| **vs v5 d10** | **0.722** (39/54) | 0.583 | 0.556 |
| **vs v7 d10** | **0.639** (34.5/54) | – | – |
| vs v7 d6 | 0.417 | – | – |
| **vs v6 d10** | **0.472** (25.5/54) | 0.667 | – |

**ELO gain estimé** :
- vs v7 d10 : `400 × log10(0.639/0.361)` ≈ **+99 ELO**
- vs v5 d10 cumulé : **+166 ELO**
- Total v5 → v8 cumulé : **~+258 ELO**

**⚠️ Quirks observés** (non-transitivités) :
- vs v6 d10 = 0.472 — **v8 perd légèrement vs v6** alors que v8 > v7 > v6 transitivement. Suggère que la bigger arch + clean labels v7 ont **specialisé** vs v7 au coût d'une légère perte de généralisation vs v6.
- vs handcrafted = 0.833 (drop vs v7 = 0.944) — robustesse vs adversaire faible légèrement érodée.
- vs v7 d6 = 0.417 (perd à shallow depth) — même asymétrie depth d6 vs d10 que v7 vs v6.

**Lecture** : v8 EST plus fort que v7 (gain vs v5 énorme, gain vs v7 d10 net), mais les quirks d6/handcrafted/v6 indiquent qu'on approche d'un **plateau du knowledge bootstrap** 1M quiet+pv-extract. Chaque cycle gagne mais hérite progressivement des biais du précédent.

**Coût** : 21.5h gen + 1.4h train + 0.5h bench = ~23h × 8 vCPU CCX33 ≈ ~€5.

**Ship policy** : v8 devient l'artefact de référence ; v7 reste accessible mais déclassé. **NON-recommandation** : v9 = 1M avec v8 labeller (diminishing returns probables, mieux investir sur axe pattern via H1/H2/H3 templates standby PRs #102 et le G5 H1 dans queue 0057). L'embedded default reste sur v5 (pas de bump tant que +50 ELO cumulés vs embedded ne sont pas franchis avec tests parity).

-----

## v7 — 2026-05-28 (job 0050-v7-quiet-pv-extract-1M)

**Artefact** : `jobs/results/0050-v7-quiet-pv-extract-1M/artefacts.src/nnue-256-128-q.bin`

**Architecture** : MLPNetworkQ 256-128 HalfMen 450 features, int8 quantifié.
Identique à v5/v6 — c'est encore le DATA qui change.

**Dataset** : **1M** self-play records @ depth 16, recipe identique v6 (×2 volume) :
- `--quiet-only` (PR #81)
- `--pv-extract 3` (PR #84)
- Mixé avec master games (BCE blend, recipe v5)

**Performance vs v6 et v5 (54 games par bench)** :

| Métrique | v7 (1M) | v6 (500K) | v5 (1M depth-20) |
|---|---|---|---|
| vs handcrafted | **0.944** (17/18) | 0.861 | 0.852 |
| vs v5 d10 | **0.583** | 0.556 | – |
| vs v5 d6 | 0.556 | 0.722 | – |
| **vs v6 d10** | **0.667** (36/54) | – | – |
| vs v6 d6 | 0.417 | – | – |

**ELO gain estimé** :
- vs v6 d10 : `400 × log10(0.667/0.333)` ≈ **+120 ELO**
- vs v5 d10 cumulé : ≈ **+58 ELO**

**Quirk** : v7 < v6 à d6 (0.417). Probable interprétation : v7 a appris des
features plus subtiles qui ne payent qu'à profondeur ≥ 10. La métrique de
référence est d10 (cf. ROADMAP.md "depth 10 = signal principal") donc le
ship est validé. À monitorer si on observe la même asymétrie sur v8.

**Coût** : 35.9h gen + 1.2h train + ~0.5h bench = ~37.6h × 4 vCPU CCX23 ≈ ~€5.

**Ship policy** : v7 devient l'artefact de référence pour les benchs et le
labelleur des futurs gen-data. v6 (0045) reste accessible mais déclassé.
L'embedded default reste sur v5/Cycle 8 (pas de bump tant que +50 ELO
cumulés vs embedded ne sont pas franchis avec tests parity).

-----

## v6 — 2026-05-26 (job 0045-quiet-pv-extract-scaleup)

**Artefact** : `jobs/results/0045-quiet-pv-extract-scaleup/artefacts.src/nnue-256-128-q.bin`

**Architecture** : MLPNetworkQ 256-128 HalfMen 450 features, int8 quantifié.
Identique à v5 — c'est le DATA qui change.

**Dataset** : 500K self-play records @ depth 16 avec :
- `--quiet-only` (PR #81) : skip positions tactiques (capture obligatoire au trait)
- `--pv-extract 3` (PR #84) : multi-extraction par arbre (~3× labels/search)
- Mixé avec master games (BCE blend, recipe v5)

**Performance vs v5 (0018) sur 54 games, 9 openings × 3 pairs × 2 colours** :

| Métrique | v6 (0045) | v5 (0018) | Δ |
|---|---|---|---|
| vs handcrafted | **0.861** | 0.852 | +0.009 |
| vs v5 (autre direction) d6 | **0.722** | (0.5 = ref) | +0.222 |
| vs v5 d10 | **0.556** | (0.5 = ref) | +0.056 |

**ELO gain estimé vs v5** : `+39 ELO` à d10, `+165 ELO` à d6.

**Notes** :
- Le verdict 0043 (pilote 200K quiet-only seul) faisait +99 ELO à d10
  mais n'avait pas de `--pv-extract`. Le 500K avec pv-extract trade-off
  un peu de qualité label (positions PV hypothétiques) contre ×2.5
  volume et ×3 vitesse gen-data.
- Le combo `quiet + pv-extract` est désormais le default pour tous les
  futurs gen-data jobs.

**Ship policy** : v6 est l'artefact de référence pour les benchs et le
labelleur de tous les futurs gen-data. L'embedded default reste sur
v5/Cycle 8 jusqu'à ce qu'un release franchisse +50 ELO cumulés (seuil
arbitraire pour mériter le coût de re-build + parity tests).

-----

## v5 — 2026-XX-XX (job 0018-train-with-master-bce)

**Artefact** : `jobs/results/0018-train-with-master-bce/artefacts.src/nnue-*-q.bin`

**Architecture** : MLPNetworkQ 256-128 HalfMen 450 features, int8 quantifié.

**Dataset** : 1M self-play depth-20 (job 0010) + master games BCE blend.

**Performance** : 0.852 vs handcrafted (référence ELO depuis fin 2026-04).

**Statut** : était la référence avant v6.

-----

## Conventions

- **NNUE format** : JNNQ (int8 quantifié, magic "JNNM" + headers, lu par
  `MLPNetworkQ::load`).
- **Embedded default** : compilé dans le binaire via blob `nnue_default_*`.
  Pas changé à chaque release.
- **Ship checklist** quand on bump embedded default :
  1. Tests parity vs version précédente sur 100 positions
  2. Bench vs Scan pour confirmer non-régression absolue
  3. Update `src/nnue_default_*.cpp` + recompile
  4. Update tests/test_nnue.cpp si la baseline embedded change
