# Journal de bord — programme « battre Scan »

> **À LIRE AVANT DE (RE)CHERCHER.** Registre court et tenu à jour à chaque
> verdict. Ancres mesurées + faits établis (à ne pas re-litiger) + index des
> jobs. Pour l'analyse détaillée → [PATTERN_PROGRAM_NOTES.md](PATTERN_PROGRAM_NOTES.md).
> Pour ce qui est **codé** → [ARCHITECTURE.md](ARCHITECTURE.md).
>
> Mise à jour : **2026-06-12** (après 0201).

---

## 1. Ancres mesurées (durables)

### vs Scan — la VRAIE référence (profondeur égale, no bitbases, harness corrigé)
| | d7 | d9 | d11 | mt 0.5s | source |
|---|---|---|---|---|---|
| **champion** (pattern, distill Scan-d10) | 0.028 | 0.000 | 0.000 | 0.000 | 0199 |
| **v15** (NNUE 128-64) | 0.028 | 0.056 | 0.056 | 0.019 | 0197/0137 |

Handicap de profondeur (champion vs **Scan-d9**) : +0 → **0.000**, +2 → **0.194**,
+4 → **0.083** (0201). v15 vs Scan-d9 : +0 = +4 = 0.056 (plat). → **l'eval est le
gap dominant ; +4 plies ne ramènent pas à parité** (la part « efficacité de
recherche » ≈ 2 plies est mineure).

### vs v15 — sparring-partner INTERNE (commode mais FLATTEUR : v15 ≈ 0 vs Scan)
| eval / cible | d9 vs v15 | source |
|---|---|---|
| master + WDL 1.4M | 0.22 | 0194 |
| self-play + WDL 1M | 0.22 | 0196 |
| self-play + score @30ms (superficiel) | 0.08–0.17 | 0198 |
| **self-play + score deep d12** | **0.306** (l2=3e-4 ; 1e-4 s'effondre) | 0200 |
| champion (master + score Scan-d10) | 0.39 | 0141 |

### Vitesse / divers
- NPS : v15-128-64 = **0.92 Mnps** ; Scan ≈ **×8** v15 (0189).
- champion en relabel **d12 = 0.026 s/pos** → 1M/8 cœurs ≈ 0.9 h (relabel cheap).
- Self-play (champion @mt30) : **59.2 % de nulles** vs **18.6 %** master.
- v15 a été entraîné sur labels **Scan-distillés** (0078, `v10-distilled-1M`).

---

## 2. Faits établis — NE PAS re-litiger

1. **La recherche de jass est complète** (TT, ID, aspiration, PVS, LMR, LMP,
   null-move, IID, extensions singulières/promo, multi-cut, killers, history,
   countermoves, quiescence). Cf. checklist [ARCHITECTURE.md](ARCHITECTURE.md).
   **Ne JAMAIS déduire « ça manque » d'un grep par mots-clés** (noms variables).
2. **Bencher contre Scan** (profondeur égale), pas contre v15 — v15 ≈ 0 vs Scan
   donc « X vs v15 » flatte (champion 0.39 vs v15 = ~0 vs Scan).
3. **Le levier est l'EVAL** : la recherche est complète, et la profondeur/vitesse
   ne compensent pas (0201) → la vitesse (×8 NPS) est **secondaire**.
4. **Cible eval = labels de recherche PROFONDE** (pas WDL, pas score superficiel).
   Confirmé : deep-d12 (0.306) ≫ score@30ms (0.08) ≫… et > WDL (0.22).
5. **WDL plafonne ~0.22** quelle que soit la source (master = self-play) — c'est
   le label, pas la classe linéaire (qui atteint 0.39 via score) ni les données.
6. **Un cycle de bootstrap ≈ le prof, pas au-delà** (deep-d12 0.306 < champion
   0.39) ; dépasser = **multi-cycles**. La distance à Scan reste **grande**.

---

## 3. Index des jobs (récents)

| job | objet | finding 1-ligne |
|---|---|---|
| 0196 | self-play 1M WDL @mt30 + logistic | WDL plafonne 0.22 (= master) ; volume aidait |
| 0197 | v15 vs Scan profondeur égale | 0.028/0.056/0.056 ; harness corrigé (fin des coups illégaux) |
| 0198 | même data, cible score @30ms | 0.08–0.17 < WDL → score superficiel = mauvais prof |
| 0199 | **ré-ancrage** champion vs Scan | champion ≈ v15 ≈ 0 → 0.39 vs v15 était flatté |
| 0200 | relabel 1M **d12** teacher-free + train | **levier deep confirmé** : 0.306 vs v15 (< champion 0.39, 0 vs Scan) |
| 0201 | handicap de profondeur vs Scan-d9 | **l'eval est le gap** (+4 plies ne ramènent pas à parité) |
| 0202 | **sweep12** (l2 sur deep-d12) | *en cours* — plafond réel cycle-1 = générateur cycle-2 |
| 0203 | **cycle 2** (bootstrap itéré) | *à construire après 0202* |

---

## 4. Outils ajoutés
- `jass --rewrite-scores-with-search <in> <out> --nnue <eval> [--depth D]
  [--start S] [--count C]` — relabel par recherche profonde, teacher-free
  (`eval ← recherche(eval)`), shardable. Cf. ARCHITECTURE.md.
- `tools/calibrate_vs_scan.py --jass-depth N --scan-depth M` — profondeur
  asymétrique (diagnostic eval-vs-recherche).

---

## 5. Prochaines étapes
1. **0202 (sweep12)** → meilleur l2 sur deep-d12 = générateur de cycle-2.
2. **0203 (cycle 2)** : regénérer self-play avec le gagnant → re-relabel d12 →
   retrain ; tester le **compounding** (> 0.306 vs v15 ?).
3. Tenir ce journal à jour **après chaque verdict**.
