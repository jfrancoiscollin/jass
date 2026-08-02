# Réouverture de la quiescence — règle de décision PRÉENREGISTRÉE

Écrit le 2 août 2026 **avant toute nouvelle mesure** et avant le dépôt de
`home-1200`. Aucun chiffre produit par ce replay n'a été consulté au moment de
fixer cette règle.

## La question, et seulement la question

Le verdict contractuel `cpx62-0812-c1q1-verdict-v2` avait fermé la quiescence :
aucun des effets menace, sacrifices ou interaction n'était établi en conversion.
La cellule `Q01_SACS` était toutefois la seule cellule décisive à bouger dans une
vue de force : à temps égal, `0,540833`, IC95 `[0,501059 ; 0,580608]`, soit
`+28,44 Elo`. Son effet de conversion restait plat.

`0812` et les quatre modèles qu'il relisait sont antérieurs à `9c1d1e8e`. Ce
moteur pouvait rendre un coup nul lorsqu'une racine était déjà nulle par
répétition. Comme la quiescence explore précisément des suites tactiques pouvant
déboucher sur une répétition, **il est plausible** que l'ancien instrument ait
déformé cette mesure. Le 1er août a montré que le même défaut avait fabriqué un
repère de conversion faux de 22 points
(`L3_EXACT_PROMOTION_20260801.md`). Cela motive le contrôle ; **cela n'établit
aucun lien causal avec le verdict de `0812`**. Quel que soit le résultat du
présent replay, cette explication restera une hypothèse non mesurée.

Le replay ne refait pas les quatre cellules de `0812`. Il compare le champion EXACT à lui-même,
avec le même binaire courant et les 63 clés historiques résolues. Le parseur
courant en expose désormais deux de plus, `scan_verify_pruning` et
`scan_threat_reentry` : elles sont elles aussi explicites et fixées à zéro. Les
fingerprints courants ont donc 65 clés et le seul bouton entre bras est
`qs_sacs=0 → 1`. `qs_sacs_depth0_only=1`, `qs_threat_ext=0`,
`qs_forcing_depth=0` et `qs_promo_depth=0` restent constants. Le défenseur figé
prédate ces deux diagnostics : son fingerprint contient explicitement ses 63
clés historiques, sans prétendre que son parseur reconnaît les deux nouvelles.

## Entrées et producteurs immuables

| entrée | producteur | identité vérifiée |
|---|---|---|
| champion EXACT 8cf | `cpx62-1117-l3-exact-fold-refit-v1` | `exact.pjtw.gz`, SHA décompressé `d84a7fc7…` |
| ouvertures de force | `home-1004-l3-pure-volume8m-preflight-v2` | 1 500 FEN, SHA `94cb6a15…` |
| défenseur Gen2 32cf | bundle figé T1-bis | SHA gzip `01cc3ea5…` |
| jauge P3 | `home-0954-l3-pure-m1-abextras-validation-v5` | 300 positions, SHA décompressé `cd92710f…` |
| jauge P4 | `home-0954-l3-pure-m1-abextras-validation-v5` | 300 positions, SHA décompressé `0d925c4f…` |

Les jauges P3/P4 sont téléchargées explicitement depuis leur producteur. Elles
ne sont pas dans le bundle figé T1-bis. Le défenseur de conversion est reconstruit
au SHA réparé `9c1d1e8eaaa5b9bbd86105f7f9807a3033784186`; les deux attaquants sont le
**même** EXACT exécuté par le moteur au SHA du job.

## Sizing fixé

- force à profondeur 9 : 1 500 ouvertures × deux couleurs = **3 000 parties** ;
- force à temps égal 0,1 s : **3 000 parties** ;
- conversion profondeur 10 : P3 et P4, 300 positions chacune, pour Q00 et Q01 =
  **1 200 parties** ;
- total : **7 200 parties**, aucun doublon artificiel par `--pairs > 1` ;
- conversion appariée : au moins **270 positions communes par strate**. En
  dessous, le résultat est inconclusif et ne ferme ni ne rouvre la piste.

La durée de référence HOME est `home-0996` : sa vue native de 3 000 parties a
pris environ 79 minutes à parallélisme 4. Le présent job utilise 12 workers et
n'a ni seconde référence de force ni second modèle attaquant à construire.
**ETA pré-job : 40 minutes, enveloppe 35–55 minutes.** Cette estimation est
communiquée avant queue et ne constitue pas une autorisation de lancement.

## La règle, fixée d'avance

Il y a deux critères co-primaires, choisis avant les chiffres :

1. l'écart de force `Q01 − Q00` à temps égal, la vue qui rendait `Q01` décisive
   dans `0812` ;
2. le delta de conversion apparié `Q01 − Q00`, P3 et P4 concaténés avec leur
   poids naturel identique (300 positions chacun).

Pour conserver un risque global d'environ 5 % malgré deux critères, chacun est
lu avec un **intervalle central à 97,5 %** (correction de Bonferroni). Le seuil
nul est respectivement `0,5` et `0` ; il n'existe pas de seuil d'effet ajouté a
posteriori.

- **`QUIESCENCE_REOPEN_0812`** si au moins un des deux intervalles à 97,5 %
  exclut strictement son nul, dans un sens ou dans l'autre. « Réouvrir » signifie
  seulement que le factoriel complet de `0812` redevient scientifiquement
  justifié. Cela ne promeut aucun réglage et n'établit pas la cause moteur.
- **`QUIESCENCE_CLOSE_CONFIRMED`** si les deux intervalles contiennent leur nul
  et si tous les minima techniques sont atteints. La piste est alors refermée.
- **`QUIESCENCE_REOPEN_INCONCLUSIVE`** si une entrée manque, si une vue n'a pas
  exactement 3 000 parties, ou si une strate a moins de 270 positions communes.

La vue fixe profondeur 9 et les deltas P3/P4 séparés sont des diagnostics
préenregistrés. Ils ne peuvent pas, seuls, renverser la décision. Aucun job
suivant, aucun bake et aucune promotion ne sont automatiques.

## Contrats qui doivent échouer tôt

1. Le readout lit les clés réellement écrites par `aggregate_conv_shards.py` :
   `conversion` et `n_pos`, jamais `conversion_rate` ni `records`.
2. Chaque entrée consommée est téléchargée par le job et rattachée à son
   producteur ; P3/P4 ne sont jamais attribuées au bundle figé.
3. Les deux fingerprints doivent contenir exactement les 65 clés du parseur
   courant (les 63 historiques plus les deux diagnostics Scan fixés à zéro) et différer
   uniquement sur `qs_sacs`. Les assertions portent sur le bouton paramétré,
   pas sur une propriété accidentelle d'un bras historique.
