# JSM2 — sidecar de contexte pour JNNW

JSM2 est un fichier binaire compté, aligné record par record avec un corpus
JNNW. Il enrichit la provenance JSM1 sans modifier le moindre octet du JNNW.

Tous les entiers multi-octets sont little-endian. Le fichier contient :

```
offset  taille  contenu
0       4       magic ASCII "JSM2"
4       4       nombre de records, u32
8       25*N    records
```

Chaque record de 25 octets est encodé par `struct "<QQBHHHbB"` :

| offset | taille | champ | contrat |
|---:|---:|---|---|
| 0 | 8 | `game_id` | `u64`, identifiant de partie |
| 8 | 8 | `opening_id` | `u64`, identifiant d'ouverture |
| 16 | 1 | `seeded` | `u8`, exclusivement `0` ou `1` |
| 17 | 2 | `ply` | `u16`, ply de la position dans la partie |
| 19 | 2 | `game_plies` | `u16`, longueur finale de la partie |
| 21 | 2 | `last_eps_ply` | `u16`, dernier ply d'exploration ; `0xFFFF` s'il n'y en a pas |
| 23 | 1 | `game_result` | `i8`, résultat **POV blanc**, exclusivement `-1`, `0`, `+1` |
| 24 | 1 | `flags` | `u8`, bits décrits ci-dessous |

Bits de `flags` :

- `b0` (`0x01`) : partie terminée au ply-cap ;
- `b1` (`0x02`) : partie terminée par adjudication ;
- `b2` (`0x04`) : label JNNW de ce record remplacé par la tablebase ;
- `b3..b7` : réservés, doivent être nuls dans cette version.

## Convention de signe

Le piège volontairement explicite du format est la coexistence de deux POV :

- `JSM2.game_result` est le résultat de la partie du point de vue **blanc** ;
- le byte WDL du record JNNW aligné est du point de vue du **joueur au trait**.

Hors record `tb_relabelled`, la relation est donc :

```
jnnw_wdl = game_result * (+1 si trait blanc, -1 si trait noir)
```

Un lecteur doit refuser un résultat hors `{-1,0,+1}` et ne doit jamais convertir
silencieusement un POV dans l'autre.

## Invariants

- la taille exacte est `8 + count * 25` ; aucun octet final n'est admis ;
- `ply < game_plies` pour chaque record ;
- si `flags.plycap` est posé, `game_plies` est égal au `max_plies` de la
  génération ;
- `last_eps_ply == 0xFFFF` signifie « aucune exploration » ; sinon un record est
  contaminé si et seulement si `ply <= last_eps_ply` ;
- les champs de partie (`game_plies`, `last_eps_ply`, `game_result`, ply-cap et
  adjudication) sont constants pour un même `game_id` ; `tb_relabelled` est un
  drapeau par record.

## Écriture et compatibilité

Le générateur conserve JSM1 par défaut :

```bash
jass --gen-data-wdl ... --sample-meta-out corpus.jsm
```

JSM2 est opt-in :

```bash
jass --gen-data-wdl ... --sample-meta-out corpus.jsm --sample-meta-format jsm2
```

`--pv-extract` est refusé avec JSM2 : ces positions appartiennent à une PV
hypothétique et n'ont pas de ply réel dans la trajectoire jouée.

Les lecteurs dispatchent sur le magic. JSM1 reste `"JSM1" + u32 count +
count * 17` et conserve exactement son comportement historique. `merge`, `mix`
et `split` préservent le schéma d'entrée ; mélanger JSM1 et JSM2 dans une même
opération échoue au lieu d'inventer les champs absents.
