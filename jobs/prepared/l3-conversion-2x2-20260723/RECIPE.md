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

Le verdict technique est `CONVERSION_2X2_G1_SCREEN_READY`. Il n'autorise ni
promotion, ni continuation, ni job automatique.

## Reprise HOME

Après retrait de CPX62/CCX33, l'évaluation seule est portée sur le runner
`home-` sans réentraînement. Le profil HOME conserve les 16 shards, `-j4`, les
modèles immuables de `0922bis`, le pool de 0921 et les 10 000 bootstraps. Seuls
les gardes machine changent : minimum 14 000 MiB de RAM, timeouts shards
1 800/1 200 s et hard cap global 120 min.

Les deux reprises CPX ont authentifié exactement deux caps déterministes à 400
plis : `standard_off/g0_g4`, shard 10, position `9bc75f...`, puis
`top3_off/g4_g0`, shard 12, position `62faf1...`. `home-0928` exige ces deux
caps, les dérive comme nulles sans rejouer, et échoue fermé si l'un disparaît
ou si une troisième anomalie apparaît.

Si une anomalie supplémentaire apparaît tardivement, `home-0928quater`
importe le tar brut vérifié de `home-0928`, réutilise chaque bras complet et ne
joue que les bras manquants. Ce mode découverte accepte uniquement des ply-caps
propres à 400 plis (nul, aucune erreur moteur), publie leur inventaire complet
sur les 4 992 lignes, et n’effectue ni adjudication ni calcul causal.
