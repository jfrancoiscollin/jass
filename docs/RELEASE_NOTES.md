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
