# L3-PURE — Hard-position mining v1

Date : 2026-07-28
Statut : spécification et outillage data-only ; aucune expérience lancée
Portée : PR 1 du mémo `MEMO_CODEX_JASS_QUALITE_SIGNAL_20260728.md`

## 1. Résultat de l’audit

Le format JNNW contient, pour chaque position, les quatre bitboards, le trait,
un score et un WDL exprimés du point de vue du joueur au trait. JSM1 fournit
l’alignement `game_id`, `opening_id`, `seeded`. L’opération `split` de
`tools/selfplay_frontier.py` place le train avant une queue holdout et garantit
un split par `opening_id`.

L’opération historique `mine` ne convient pas au DOE demandé :

- elle accepte le corpus complet sans preuve de partition ;
- elle ne protège donc pas contre une sélection sur le holdout ;
- elle ne produit que des seeds à cibles nulles, sans replay étiqueté ni JSM1 ;
- son manifeste ne contient pas la provenance et les contrôles nécessaires ;
- sa déduplication n’est pas canonique par symétrie de couleur.

La v1 ajoute une opération séparée `mine-hard`. Elle ne modifie ni le moteur,
ni le format des données, ni le comportement de `mine`.

## 2. Signal unique

Le seul signal autorisé en v1 est :

> `failed_conversion = material advantage observed, terminal outcome
> non-winning for advantaged side`

La sélection utilise uniquement les WDL de la partition train. Le WDL n’est ni
recalculé, ni remplacé par un teacher, un oracle ou une recherche moteur.
`external_teacher_inputs` vaut obligatoirement zéro.

## 3. Contrat d’entrée

Commande :

```text
python tools/selfplay_frontier.py mine-hard \
  --data INPUT.jnnw \
  --meta INPUT.jsm \
  --split-manifest SPLIT.json \
  --max-records N \
  --seed SEED \
  --signal failed_conversion \
  --one-per-game \
  --colour-mirror \
  --code-sha FULL_40_HEX_SHA \
  --out-replay hard-replay.jnnw \
  --out-meta hard-replay.jsm \
  --out-seeds hard-seeds.jnnw \
  --manifest hard-mining-manifest.json
```

`--max-records` inclut les miroirs de couleur et doit être pair. Le mineur
refuse de travailler sans `--one-per-game`, `--colour-mirror`, SHA complet ou
manifeste de split compatible.

Le manifeste de split doit certifier :

- schéma 1, opération `split`, unité `opening_id` ;
- queue holdout (`tail_is_holdout=true`) ;
- comptes data/meta/train/holdout exacts ;
- nombres d’ouvertures exacts ;
- aucune ouverture commune au train et au holdout ;
- partitions train et holdout non vides.

Le holdout est lu uniquement pour vérifier ce contrat structurel. Aucun de ses
enregistrements n’entre dans le signal, les quotas ou la sélection.

## 4. Sélection déterministe

La sélection suit cet ordre :

1. détecter les `failed_conversion` dans le train ;
2. conserver au plus une position par `game_id`, avec tie-break déterministe ;
3. dédupliquer les positions canoniques sous rotation 180° et échange des
   couleurs ;
4. équilibrer par round-robin déterministe sur
   `(phase, marge matérielle exacte, nombre de pièces exact)` ;
5. émettre chaque position avec son miroir de couleur.

La graine participe uniquement aux tie-breaks déterministes. À entrée, manifeste
de split, graine et SHA identiques, les trois fichiers data sont bit-identiques.

## 5. Sorties et cibles

La publication produit :

- `hard-replay.jnnw` : positions sélectionnées et miroirs, score/WDL originaux
  conservés ;
- `hard-replay.jsm` : JSM1 aligné, avec le même identifiant de partie et
  d’ouverture pour les deux couleurs ;
- `hard-seeds.jnnw` : mêmes positions, score et WDL explicitement mis à zéro ;
- `hard-mining-manifest.json` : marqueur de complétude écrit après relecture et
  vérification de toutes les sorties.

Les écritures sont atomiques fichier par fichier. Le manifeste final contient :

- chemins, SHA256 et comptes des entrées et sorties ;
- SHA du code, signal, graine et preuve du split train/holdout ;
- candidats et sélections par catégorie ;
- jeux, ouvertures et positions canoniques uniques ;
- suppressions one-per-game et déduplication canonique ;
- distributions WDL, phase, pièces et marge matérielle ;
- vérification des cibles replay préservées et des cibles seeds nulles ;
- `external_teacher_inputs=0`.

Toute troncature, désalignement JNNW/JSM1, incohérence de compte, fuite
d’ouverture, manifeste incompatible ou sortie non vérifiable ferme l’opération
en erreur. Les chemins de sortie existants ne sont jamais écrasés. Le manifeste
de complétude n’est publié qu’après relecture des trois sorties data.

## 6. Couverture de tests

La fixture `jobs/tests/fixtures/hard_mining_v1.json` couvre :

- plusieurs positions d’une même partie ;
- doublon canonique entre deux parties ;
- conversion réussie exclue ;
- échec de conversion noir et blanc ;
- plusieurs phases, marges et nombres de pièces ;
- candidat holdout qui ne doit jamais être sélectionné.

Les tests vérifient l’alignement, le déterminisme bit à bit, l’absence de fuite
holdout, one-per-game, les miroirs, la préservation des cibles replay, la mise à
zéro des seeds et les échecs fermés sur données tronquées, comptes divergents ou
manifeste incompatible.

## 7. DOE futur préenregistré — non lancé par cette PR

Hypothèse : à budget de fit constant, concentrer le replay historique sur les
échecs de conversion améliore davantage la force que tirer ce replay
uniformément.

| Élément | CONTROL | TREATMENT |
|---|---|---|
| Données fraîches | 1 M, même source | 1 M, même source |
| Replay historique | 1 M uniforme | 1 M `hard-replay` |
| Parent | identique | identique |
| Source historique | identique | identique |
| Split, graines et fit | identiques | identiques |

Le holdout commun doit être construit par ouverture avant tout mining. Le
mineur ne voit que le train. Le seul facteur mobile est la politique de
sélection du million d’observations de replay historique.

Le readout futur doit être indépendant, apparié, à haute puissance, sur des
ouvertures fraîches disjointes du train et du mining, dans les deux vues Q00 et
native 0,1 s/coup, avec IC95 et diagnostics de couverture. La taille, les
graines et les seuils de décision doivent être figés avant le calcul.

Ce DOE reste strictement préparatoire :

```json
{
  "promotion": false,
  "automatic_next_job": null
}
```

Aucun template, job, bake, promotion ou changement de champion ne fait partie de
cette PR.
