# Fork (c) — verdict du gate C0 (2026-07-17)

> Source de vérité : `c0-decision.json` du run `cpx62-0774-forkc-c0-v1`
> (`r2:jass-data/runs/cpx62-0774-forkc-c0-v1/20260717T200342Z-709fa072`), gate
> `jobs/tools/forkc_c0_gate.py`. Bundle d'inputs consommé :
> `inputs/t1bis-adj-g1/forkc-weak-v1` (départ affaibli **0.3× le bootstrap fort** :
> men 0.3 / king 0.9 / king-center 0.06 / mobility 0.015 ; parent=fixed=faible ;
> gen2/seeds/G1/jauge réutilisés de v1 à l'identique — publié par `cpx62-0773`).

## Verdict

**`decision = reject` · `scientific_status = stop_regression`** — un tour C complet
(`cpx62-0775-forkc-t1-v1`) NE DOIT PAS être soumis. Le départ affaibli au tiers ne
produit ni un signal de conversion différent ni un généraliste non-régressif.

## Chiffres (run réel, ~1h48 sur cpx62, N=600/gate)

| Mesure | Valeur | Seuil pré-engagé | Lecture |
|---|---:|---:|---|
| **refit faible vs fort** (elo) | **−32.5** | ci_high ≥ 0.50 | **ci_high 0.4932 < 0.50 → régression établie** = motif du reject |
| refit faible vs fort (rate, n=600) | 0.4533 [0.4135–0.4932] | — | perd hors-IC |
| **hard-conversion delta** (refit − baseline) | **−0.0111** | ≥ +0.02 | conversion NE monte PAS (0.5124 vs 0.5236) — **même plafond** |
| policy divergence brute (faible vs fort) | 0.055 | ≥ 0.05 | divergence de coups réelle mais marginale |
| policy divergence après refit | 0.1367 | ≥ 0.05 | le refit s'éloigne du fort… |
| raw faible vs fort (elo) | −14.5 [0.439–0.519] | — | …mais en JEU pur le faible ≈ fort dans le bruit |

## Interprétation

1. **Régression, pas dé-saturation.** L'hypothèse fork (c) était : partir plus faible
   dé-sature la logistique (0719) → le fit apprend enfin la conversion. Résultat inverse :
   le refit depuis le faible **régresse vs le fort** (−32.5 elo, ci_high < 0.5) et la
   **conversion baisse** (−0.011). Scaler le matériel du départ ne débloque rien.
2. **Cohérent avec le plafond 1-tour.** Le C0 confirme le verdict 0726/fork(a) : la
   conversion est un plafond structurel (~0.52 hard / ~0.66 WDL-grounded) que ni les
   labels adjud, ni le multi-tours, ni l'affaiblissement du départ ne font bouger.
3. **La divergence de politique existe** (5.5→13.7 %) mais est **découplée de la
   conversion et de la force** : le faible joue *différemment* sans jouer *mieux*.

## Décision

- **Fork (c) au départ 0.3× : CLOS (stop_regression).** `cpx62-0775-forkc-t1-v1` reste
  préparé mais non soumis (son propre pré-check C0 le clean-stoppe de toute façon).
- Leviers « départ » restants théoriques : un départ **zéro** pur (encore plus loin du
  fort — a priori pire) ou un scaling **intermédiaire** (0.6×) ; mais le mécanisme
  (régression + conversion plate) rend un gain improbable. **Le vrai pivot reste
  l'étape (6) sparring-vs-Scan** (labels = résultat réel vs Scan), hors de la famille
  « re-fit depuis un départ matériel ».
