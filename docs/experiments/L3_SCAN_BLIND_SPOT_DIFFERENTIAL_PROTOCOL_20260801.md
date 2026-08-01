# Atlas avec témoin Gen2 — protocole différentiel (2026-08-01)

## Question

L'atlas TURNOVER de `cpx62-1114` a montré une perte diffuse, calme et surtout
pré-finale, mais sans témoin. Cette forme appartient-elle au modèle 8cf courant,
ou est-elle déjà présente chez la référence historique Gen2 en 32cf ?

Le protocole refait l'instrument à neuf sur le champion courant **EXACT**, puis
sur **Gen2**, avant de calculer `EXACT − Gen2`.

## Deux passes, un seul instrument

| | passe 1 | passe 2 |
|---|---:|---:|
| modèle | EXACT `d84a7fc7…` | Gen2 figé `01cc3ea5…` (gzip) |
| géométrie | 8cf | 32cf (`gen_patterns --variant v4`) |
| `n_pat` | `8 × 531441` | `32 × 531441` |
| `n_ext` | **120** | **120** |
| classe | linéaire `.pjtw` | linéaire `.pjtw` |
| features extras | ENDGAME + KING_MOBILITY + SCAN_PARITY, TEMPO_STAGE | identiques |

Le template unique `l3-scan-blind-spot-atlas-v1.sh` exige désormais
`--variant exact` ou `--variant gen2`. Le chemin 32cf réutilise celui des gardes
de succession : génération `v4`, build avec les mêmes flags, puis contrôle du
header avant toute partie. Une dérive de `n_pat` ou de `n_ext=120` arrête le job.

Les deux wrappers épinglent strictement :

- même SHA moteur `develop` ;
- même binaire Scan et même `data/eval`, `bb-size=0`, sans livre ;
- `EGDB=OFF` des deux côtés ;
- jeu `d8`, jugement Scan des deux enfants `d10` ;
- `MAX_PLIES=160`, 16 shards, seeds `1..16` ;
- budget de 1 500 s par shard, cap 100 000 parties, plancher 200 positions.

Chaque atlas publie `protocol.json` et embarque ce même contrat dans
`atlas.json`. Le readout refuse de comparer les bras si les deux copies ne sont
pas identiques ou si un paramètre commun diffère.

## Différentiel

Le readout publie :

- accord/désaccord global et coût Scan ordinaire par position ;
- taux de coûts écrêtés, taux de conversion ratée global et différentiel de
  conversion par bucket lorsque le plancher est franchi dans les deux bras ;
- `Δ = EXACT − Gen2` par axe (`phase`, présence des dames, matériel,
  calme/capture forcée) ;
- `Δ` par bucket, seulement lorsque le bucket franchit le plancher dans les
  deux bras ;
- parts de masse de coût, pour distinguer amplitude et simple fréquence.

Les volumes ne sont pas forcés égaux : le budget mural l'est. Toutes les
grandeurs différentielles sont donc normalisées par position ou exprimées en
parts. Les trajectoires étant propres à chaque modèle et corrélées à l'intérieur
des parties, le readout reste descriptif : aucune p-value iid n'est fabriquée.

## Ce que le résultat pourra dire

- **Géométrie/profil : oui.** Les deux profils 8cf et 32cf deviennent
  directement comparables sous le même instrument ; `n_ext` est tenu à 120 et
  la dimension structurelle qui change est `n_pat`.
- **Features : non.** Elles sont tenues constantes ; aucune attribution à une
  feature n'est possible.
- **Classe linéaire contre non-linéaire : non.** Les deux bras sont linéaires ;
  aucun bras non-linéaire n'existe dans ce protocole.
- **Ablation pure des poids : non.** EXACT et Gen2 portent aussi leurs poids et
  leurs trajectoires propres. Le résultat localise un différentiel de profils,
  il ne prétend pas remplacer une ablation d'entraînement à géométrie croisée.

Lectures préenregistrées :

- même forme et même amplitude : l'atlas décrit principalement un fond commun
  aux deux évaluations linéaires ;
- même forme, EXACT uniformément plus bas : amélioration diffuse sans nouvelle
  localisation ;
- redistribution nette de la masse entre axes/buckets : point aveugle propre à
  l'un des profils géométriques, localisé descriptivement.

## Sizing et autorisation

`cpx62-1114` a produit 4,99 M positions en 27 minutes avec 16 shards et le même
budget de 25 minutes. Les deux passes sont attendues à environ 27–35 minutes
chacune, puis moins de 5 minutes pour le readout, soit **60–75 minutes
séquentielles**. Le budget par passe reste borné même si le build 32cf donne un
débit différent.

Jobs préparés sous
`jobs/prepared/l3-scan-blind-spot-differential-20260801/`. Ils ne sont pas
soumis par ce commit. Soumission seulement après validation du sizing et go
explicite JFC ; aucune continuation automatique.
