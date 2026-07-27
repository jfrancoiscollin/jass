# Où se situe TURNOVER face à Scan — matrice de calibration

Préenregistré le 27 juillet 2026, avant `home-1002`. Débloqué par `home-1001`
(`SCAN_HARNESS_SOUND_ANCHOR_AT_OR_ABOVE_FLOOR`), qui a établi que le harnais
mesure enfin du jeu et non l'abandon du moteur.

## Les trois questions, telles que posées

> « Est-ce que notre depth 10 équivaut à un depth 8 de Scan ? Est-ce qu'un
> mt 0.2 équivaut à un 0.1 s de Scan ? Et à armes égales, quel est le % de
> W/D/L entre les deux ? »

Une rangée par question, et chaque rangée contient sa cellule **à armes
égales**, qui donne le W-N-D brut.

| rangée | notre côté | Scan balayé | n/cellule |
|---|---|---|---:|
| **A** | `d9`, Q00 | `d3, d5, d6, d7, d9` | 1000 |
| **B** | `d11`, Q00 | `d5, d7, d9, d11` | 1000 |
| **C** | `mt0.2`, Q00 | `mt0.02, 0.05, 0.1, 0.2` | 200 |

**B existe pour une raison précise** : l'équivalence de A pourrait n'être
qu'un point, pas une propriété. Si notre `d9` vaut un `Scan d_x` et notre
`d11` un `Scan d_{x+2}`, l'échange est de un pour un et l'écart est un pur
décalage de profondeur. S'il vaut `d_{x+1}`, chaque ply que nous ajoutons vaut
moins qu'un ply de Scan, et le déficit se creuse avec le temps de réflexion —
ce qui est la vraie question derrière « on est à combien ».

Le pool est un tirage neuf (`--gen-opening-pool`, graine `2718282`), pas les
combinaisons DILF de l'ancre : celles-ci sont des positions tactiques choisies,
utiles pour reproduire un protocole historique, mauvaises pour estimer une force
générale.

## Lecture — interpolation, jamais extrapolation

Pour chaque rangée, le job trie les cellules par force croissante de Scan et
**interpole linéairement le croisement à `0,5`**. C'est la réponse à « notre
`d9` vaut le `d_x` de Scan ».

Si aucune cellule ne passe au-dessus de `0,5`, le job publie
`below_weakest_scan_tested` et **ne donne pas de chiffre**. L'équivalence est
alors seulement bornée, pas mesurée, et le dire est le seul résultat honnête :
`home-1001` donne `d9` contre `Scan d9` à `0,150`, donc le croisement est
attendu bien plus bas, mais rien ne garantit qu'il soit au-dessus de `d3`.

Verdicts possibles :

- `SCAN_CALIBRATION_MATRIX_EQUIVALENCE_MEASURED` — les trois rangées croisent.
- `SCAN_CALIBRATION_MATRIX_EQUIVALENCE_BOUNDED_ONLY` — au moins une rangée
  reste sous la plage testée ; l'équivalence est encadrée, pas chiffrée.
- `SCAN_CALIBRATION_MATRIX_PARTIAL_CELLS_FAILED` — une cellule n'atteint pas
  90 % de son `n` visé. `n` insuffisant est un échec, pas un résultat faible.

`promotion_authorized=false`, `automatic_next_job=null` dans tous les cas.

## Puissance

À `n=1000`, l'erreur-type sur un score de `0,3` est `1,45 pp` ; à `n=200` et
`0,25`, elle est `3,1 pp`. Les cellules de profondeur situent donc le
croisement à environ un tiers de ply près, les cellules de cadence beaucoup
plus grossièrement. C'est le compromis retenu : la profondeur fixe est presque
gratuite, la cadence est le seul régime qui coûte du temps machine.

## Garde-fou spécifique

Le job **refuse de démarrer** si `src/search.cpp` ne contient pas
`root_is_drawn`, c'est-à-dire si le moteur est antérieur au correctif de la
racine nulle. Sans lui, chaque cellule mesurerait l'abandon de Jass et non sa
force — c'est précisément ce qu'ont fait `home-0997` à `home-1000`, et cette
assertion rend l'erreur non répétable.

## Sizing, ancré sur `home-1001`

Débits mesurés sur cette box : `d9` = **89 parties/min/cellule**,
`mt0.3` = **4,0 parties/min/cellule**.

| vague | cellules | procédés | durée attendue |
|---|---|---:|---|
| 1 | rangée A (5) + rangée C (4) | 18 sur 16 CPU | ~30-35 min, dominée par la cadence |
| 2 | rangée B (4) | 8 | ~40-45 min, `d11` ≈ 4× `d9` |

Plus ~12 min de build. **ETA ≈ 1 h 25 à 1 h 35.** Plafonds par cellule :
40 min (A), 60 min (C), 90 min (B) — larges, pour qu'un plafond signale une
anomalie et non un sous-dimensionnement.
