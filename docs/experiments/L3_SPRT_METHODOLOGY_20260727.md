# L3 — test séquentiel (SPRT) pour les gates de force

Outillage préparé le 27 juillet 2026, en réponse au mur de coût identifié par
[`L3_VIEW_AGREEMENT_AND_POWER_20260726.md`](L3_VIEW_AGREEMENT_AND_POWER_20260726.md).

## Le problème

Le coût d'un readout à `n` fixe croît en `1/effet²`. Sur nos budgets :

| effet à établir | parties/cellule | temps de jeu HOME |
|---|---:|---|
| +10 Elo | ~4 800 | ~25 min |
| +5 Elo | ~19 200 | ~1 h 40 |
| +3 Elo | ~53 000 | ~4 h 30 |
| +2 Elo | ~120 000 | ~10 h |

Les incréments mesurés se resserrent — F2M contre Gen2 valait ~+50 Elo,
TURNOVER contre F2M ~+10 — donc la validation deviendra plus chère que
l'entraînement avant que la classe linéaire ne sature.

## Ce que le SPRT apporte réellement

Le SPRT accumule un log-rapport de vraisemblance et s'arrête dès qu'il franchit
`log(β/(1−α))` ou `log((1−β)/α)`. Il ne paie donc pas le pire cas
systématiquement.

**Mesuré, à hypothèses et taux d'erreur identiques** (`α = β = 0,05`) :

| H0 vs H1 | effet vrai | `n` fixe | `n` SPRT | gain |
|---|---:|---:|---:|---:|
| 0 vs +5 | 0 | 51 216 | 27 869 | ×1,8 |
| 0 vs +5 | +5 | 51 216 | 27 869 | ×1,8 |
| 0 vs +5 | +10 | 51 216 | 9 292 | ×5,5 |
| 0 vs +5 | +15 | 51 216 | 5 577 | ×9,2 |
| 0 vs +5 | −15 | 51 216 | 3 983 | ×12,9 |

**Le gain typique est ×1,8, pas ×2-3.** Il n'explose que lorsque la vérité est
loin des deux hypothèses — c'est-à-dire précisément quand la question était
facile. Quand la vérité tombe entre H0 et H1, le SPRT peut au contraire être
**plus lent** que le `n` fixe : à H0=0/H1=+10 avec un effet vrai de +5, l'espérance
diverge. C'est la pathologie classique, et elle impose un **plafond `n_max`
obligatoire** au-delà duquel on retombe sur la lecture par intervalle.

## Deux modèles de variance

- **trinomial** — comptes W/D/L. Utilisable immédiatement : c'est tout ce que
  nos cellules publient aujourd'hui.
- **pentanomial** — résultats par *paire d'ouvertures jouée aux deux couleurs*,
  `{0; 0,5; 1; 1,5; 2}` points sur 2. Notre harnais joue **déjà** en paires
  appariées (`--pairs 1`), donc ce modèle est le bon dès que les cellules
  publieront le détail par paire. Il retire du bruit la part due au tirage de la
  couleur, gain qui s'ajoute à celui du séquentiel.

Passer au pentanomial demande une seule chose côté harnais : que
`run_jass_gate_bounded.py` émette le vecteur des cinq effectifs en plus de
W/D/L. C'est le prochain pas concret.

## Ce que le SPRT aurait donné sur nos cellules

Rejeu à taux observé constant, `H0=0`, `H1=+5`, `α=β=0,05` :

```text
cellule                                   n réel      Elo     LLR    verdict     n SPRT
TURNOVER vs F2M   (0993)                    5 000   +13,77    2,37   CONTINUE      > n
TURNOVER vs F2M   (cumul 3 pools)          11 000    +9,89    3,42   ACCEPT_H1   9 460
REPLAY75 vs TURNOVER (0993)                 5 000   −15,51   −3,78   ACCEPT_H0   3 890
REPLAY75 vs F2M   (0993)                    5 000    +0,76   −0,37   CONTINUE      > n
L2_1E5 vs contrôle (0987+0989)              6 000    +0,93   −0,40   CONTINUE      > n
```

Lecture importante : le SPRT `0 vs +5` est **plus exigeant** que notre critère
actuel « borne basse à 95 % au-dessus de 50 % ». Il ne conclut pas à `n=5000`
là où le test par intervalle conclut. Les deux ne répondent pas à la même
question — l'intervalle demande « l'effet est-il positif ? », le SPRT demande
« l'effet ressemble-t-il plus à +5 qu'à 0 ? ». Le second est un contrat plus
fort, et c'est celui qu'il faut pour une promotion.

**Conséquence : adopter le SPRT resserrera nos verdicts, pas seulement nos
coûts.** Il ne faut pas le présenter comme une pure économie.

## Réglages recommandés

| usage | H0 | H1 | α, β | `n_max` |
|---|---:|---:|---|---:|
| écran exploratoire | 0 | +8 | 0,05 | 12 000 |
| confirmation de bras | 0 | +5 | 0,05 | 30 000 |
| porte de champion | 0 | +5 | 0,025 | 40 000 |

`n_max` atteint sans franchissement = **inconcluant**, jamais « neutre ». Le
job doit le dire explicitement, conformément à la règle n=0 du projet.

## Statut

`jobs/tools/l3_sprt.py` + 19 tests. L'outil calcule le LLR, les bornes, le
verdict et une espérance de taille d'échantillon. Il n'est **branché sur aucun
gate** pour l'instant : le brancher est une décision de protocole, puisqu'il
change le critère de décision et pas seulement le budget.
