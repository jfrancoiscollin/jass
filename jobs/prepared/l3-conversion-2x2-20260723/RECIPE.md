# 0922 — ablation conversion G1 `2 × 2`

Écran mécanistique d’une génération, non promotable :

| cellule | départ | reweighting role-aware V2 |
|---|---|---|
| `standard_off` | standard | non |
| `standard_on` | standard | oui |
| `top3_off` | 16v18 / 17v19 / 18v20 | non |
| `top3_on` | 16v18 / 17v19 / 18v20 | oui |

Les cellules off/on d’une même distribution réutilisent exactement le même
self-play G1 et le même split. Les deux distributions contiennent chacune
500 000 records source. Tous les autres facteurs sont figés : G0 matériel,
8cf, d8, Q00/63 paramètres, exploration 8/8 %/60, WDL terminal, fit logistic,
L2 `3e-5`, chunk 500 k, 25 itérations.

Le gate utilise le pool TOP3 stable immuable de 0921 :

- 384 positions, 12 cellules × 32 ;
- pour chaque candidat : attaque contre G0, défense contre G0 et candidat/candidat ;
- contrôle G0/G0 commun ;
- 10 000 bootstraps appariés ;
- garde équilibrée : 128 parties par candidat contre G0.

Sizing CPX62 :

- `nproc=16`, 31 GiB, 441 237 MiB libres mesurés le 23 juillet ;
- génération : 8 producteurs standard + 6 TOP3 concurrents ;
- ancre 0842 : 4×500 k, build et quatre fits en 985 s ;
- ancre 0890bis sur CCX33 : 4×2 M TOP3 en 22 821 s ;
- ETA 30–45 min ; hard cap 60 min ;
- timeout génération 2 700 s/shard, matrices et garde 900 s/shard.

Le verdict technique est `CONVERSION_2X2_G1_SCREEN_READY`. Il n’autorise ni
promotion, ni continuation, ni job automatique.
