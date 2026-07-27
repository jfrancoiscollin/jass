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

## Résultat — `home-1002`, 17h51-18h57 FR

`SCAN_CALIBRATION_MATRIX_EQUIVALENCE_BOUNDED_ONLY`. Treize cellules sur treize
utilisables, aucune au plafond.

### Rangée A — notre `d9` contre la profondeur de Scan

| Scan | n | W-N-D | score | Elo |
|---|---:|---|---:|---:|
| `d3` | 1000 | 427-127-446 | **`0,490`** | `−7` |
| `d5` | 1000 | 255-103-642 | `0,306` | `−142` |
| `d6` | 1000 | 207-93-700 | `0,254` | `−187` |
| `d7` | 1000 | 185-75-740 | `0,223` | `−217` |
| `d9` | 1000 | 160-77-763 | `0,199` | `−242` |

**Notre profondeur 9 vaut la profondeur 3 de Scan.** À `n=1000`,
`0,490` d'intervalle `[0,459 ; 0,521]` : la parité avec `Scan d3` n'est pas
rejetée. Le verdict formel dit « sous la plus faible profondeur testée » parce
que `0,490 < 0,5`, mais le croisement est à un cheveu de `d3` — il faudrait
`d2` pour l'encadrer proprement.

**Six plies de handicap.** C'est le chiffre demandé, et il est brutal.

### Rangée B — l'échange se fait-il un ply pour un ply ?

| Scan | score `d9` (A) | score `d11` (B) | écart |
|---|---:|---:|---:|
| `d5` | `0,306` | `0,380` | `+7,4 pp` (`z=+3,5`) |
| `d7` | `0,223` | `0,289` | `+6,6 pp` (`z=+3,4`) |
| `d9` | `0,199` | `0,242` | `+4,3 pp` (`z=+2,3`) |

Deux plies de plus chez nous valent `+4` à `+7 pp`, soit **`2,2` à
`3,7 pp` par ply**. Deux plies de plus chez Scan coûtent `−2,6 pp/ply`
(pente identique sur les deux rangées, `−2,67` et `−2,63`).

**Nos plies valent au moins autant que les siens.** L'écart est donc un
**décalage fixe de profondeur**, pas un écart qui se creuse : allonger la
réflexion des deux côtés ne devrait pas nous enfoncer davantage. C'est la
bonne nouvelle du run.

**Défaut de conception à porter à mon compte** : la rangée B commence à
`Scan d5` alors que la rangée A descendait à `d3`. Elle ne peut donc pas
croiser, et son équivalence propre reste non mesurée. Il aurait fallu
descendre les deux rangées au même plancher.

### Rangée C — la cadence

| Scan | n | W-N-D | score | Elo |
|---|---:|---|---:|---:|
| `mt0.02` | 200 | 49-20-131 | `0,295` | `−151` |
| `mt0.05` | 200 | 47-15-138 | `0,273` | `−170` |
| `mt0.1` | 200 | 44-15-141 | `0,258` | `−184` |
| `mt0.2` | 200 | 50-9-141 | `0,273` | `−170` |

**La courbe est plate.** Donner à Scan **dix fois moins de temps** qu'à nous ne
nous rapporte que `+2,2 pp` (erreur-type `4,5 pp`, `z=+0,5`) : rien. À
`0,02 s` par coup, Scan nous bat encore à `70 %`.

L'équivalence en cadence n'est donc pas seulement non mesurée, elle est
**hors d'atteinte de la plage testée**, et de très loin.

### À armes égales — la réponse directe

| régime | W-N-D | score | Elo | IC95 |
|---|---|---:|---:|---|
| `d9` contre `d9` | 160-77-763 | `0,199` | `−242` | `[−270 ; −216]` |
| `d11` contre `d11` | 186-71-743 | `0,222` | `−218` | `[−245 ; −193]` |
| `mt0.2` contre `mt0.2` | 50-9-141 | `0,273` | `−170` | `[−229 ; −119]` |

### Le déficit est de l'évaluation, pas de la vitesse

On fait **mieux à temps égal** (`−170`) qu'**à profondeur égale** (`−242`).
Autrement dit, pour un budget de temps donné nous obtenons plus de profondeur
effective que Scan : notre vitesse par nœud n'est pas le goulot, elle nous
rapporte même du terrain.

C'est l'inverse de la légende qu'affichait `cpx62-0571` (« rate(prof. fixe)
>> rate(movetime) ⟹ vitesse-limité ») et cela confirme la lecture déjà retenue
dans `PROJECT_RESULTS` : **le résidu contre Scan est de la marge
d'évaluation**. Un moteur qui perd `70 %` face à un adversaire réfléchissant
`0,02 s` par coup ne perd pas par manque de nœuds.

### Ce que ce run ne dit pas

- Il ne mesure **que TURNOVER**. Le contrôle `gen2-mmto` est dans `home-1001`,
  à `n=40`, trop faible pour départager les deux contre Scan.
- Les gains de la lignée (`+52 Elo` pour `gen2-mmto`, `+13,7` pour TURNOVER)
  ont tous été mesurés **Jass contre Jass**. Ils sont réels et ils restent
  petits devant un écart de `−170` à `−240`.
- La platitude de la rangée C admet une explication mécanique non testée : un
  plancher de profondeur ou de temps côté Scan qui rendrait `mt0.02`
  inopérant. Les durées de cellule varient bien avec la cadence de Scan
  (`8,1 s/partie` à `mt0.02` contre `13,9 s` à `mt0.2`), donc le paramètre est
  honoré — mais cela ne prouve pas qu'il n'y a pas de plancher.
