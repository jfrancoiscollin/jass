# L3-IMBALANCE2 — référence de difficulté par quantité de matériel

Statut : **protocole préparé, aucun résultat scientifique encore produit**.

## 1. Pourquoi le taux de conversion brut est insuffisant

Un avantage de deux pions ne représente pas la même difficulté dans toutes les
strates. Une position `1v3` peut être théoriquement nulle parce que le pion
isolé atteint la dame, tandis qu’une position `18v20` décrit un milieu de partie
très différent. Agréger les dix-huit strates dans un seul taux W/D/L ou un seul
coût `2L+D` suppose implicitement qu’elles ont la même convertibilité, ce qui est
faux.

Les strates de la lignée sont :

`1v3`, `2v4`, `3v5`, ..., `18v20`.

Le nombre total de pièces est donc toujours pair : 4, 6, 8, ..., 38. Il n’existe
pas de strate à exactement sept pièces dans cette campagne.

## 2. Frontière exacte et référence empirique

### 2.1 Vérité exacte EGDB

La vérité WDL est calculée exactement pour les positions de départ contenant au
plus six pièces :

- `1v3` — quatre pièces ;
- `2v4` — six pièces.

Chaque position A64/B64 de ces deux strates est extraite, relabellisée par
l’EGDB, puis le runner exige `egdb-resolved == records`. Le WDL exact est replié
du point de vue du camp qui commence avec deux pions de plus.

Une nulle exacte n’est donc pas décrite comme une « conversion ratée » au sens
théorique : elle indique que la position initiale est nulle sous jeu parfait.
Le rapport conserve séparément la distribution exacte victoire/nulle/défaite.

### 2.2 Référence Scan au-delà de six pièces

À partir de `3v5`, soit huit pièces au total, la campagne ne dispose pas d’une
vérité tablebase complète. Les strates `3v5` à `18v20` sont donc jouées par Scan
contre lui-même sur les mêmes positions A64/B64, à profondeur 10 et cap 400
plies.

Cette distribution est nommée :

```text
scan_d10_selfplay_reference
```

Elle est une **référence empirique**, jamais une vérité exacte. Le manifeste
impose explicitement :

```text
scan_reference_is_exact = false
reference_used_for_training = false
reference_used_for_weighting = false
```

Scan ne fournit donc aucune cible d’entraînement et ne modifie pas la politique
de rééchantillonnage role-aware V2.

## 3. Sorties par strate

Pour chacune des dix-huit strates, le profil publie :

- nombre total de pièces ;
- source de référence : `exact_egdb_wdl` ou
  `scan_d10_selfplay_reference` ;
- nombre de positions ;
- taux W/D/L du point de vue du camp initialement à `+2` ;
- coût de référence `2 × loss + draw` ;
- résultats séparés pour les pools A64 et B64.

Ainsi, `6v8` — quatorze pièces — et `18v20` — trente-huit pièces — possèdent des
références W/D/L indépendantes et ne sont jamais supposées équivalentes.

## 4. Mesure principale V1 contre V2

Le verdict causal V1/V2 ne dépend pas de Scan. Les huit modèles sont comparés
sur les mêmes positions, et le rapport calcule pour chaque strate :

- W/D/L V1 et V2 ;
- coût `2L+D` V1 et V2 ;
- delta apparié V2−V1 ;
- IC bootstrap apparié.

Le score principal devient la **macro-moyenne par strate** : chaque strate pèse
`1/18`, quel que soit son taux naturel de nulle ou de victoire. L’IC principal
est obtenu par bootstrap stratifié, en rééchantillonnant les positions à
l’intérieur de chaque strate puis en moyennant les dix-huit effets.

Le global micro sur les 2 304 positions reste publié comme diagnostic
secondaire, mais il ne peut plus être la seule base du verdict.

## 5. Lecture ajustée par difficulté

Lorsque le profil de référence est fourni au comparateur, chaque strate contient
a lecture descriptive supplémentaire :

```text
coût candidat − coût de référence
W/D/L candidat − W/D/L de référence
```

Pour `1v3` et `2v4`, la référence est exacte. Pour les seize autres strates, la
référence est celle de Scan d10 et conserve donc son incertitude empirique.

Cette lecture sert à répondre à deux questions différentes :

1. **effet causal de la V2** : V2 est-elle meilleure que V1 sur les mêmes
   positions ?
2. **niveau absolu par difficulté** : à quelle distance chaque génération se
   situe-t-elle de l’EGDB ou de Scan dans sa strate ?

La référence de difficulté n’entre pas dans la règle de lead V1/V2. Elle ne peut
donc ni créer artificiellement un lead, ni autoriser P2 ou une promotion.

## 6. Jobs préparés

Après publication de la P1 V2 et de ses pools A64/B64 :

```text
cpx62-l3-imbalance2-a64-b64-difficulty-reference.sh
```

produit :

- WDL exact EGDB pour `1v3` et `2v4` ;
- WDL Scan d10 pour `3v5` à `18v20` ;
- `imbalance2-a64-b64-difficulty-reference.json` ;
- les rapports bruts et preuves de résolution exacte.

Le job comparatif reste :

```text
cpx62-l3-imbalance2-p1-v1-v2-a64-compare.sh
```

Il produit la comparaison candidate-only stratifiée. Le comparateur peut être
rejoué avec `--reference` pour joindre les écarts EGDB/Scan au rapport sans
modifier le verdict causal.

## 7. Limite méthodologique

Une victoire du camp à `+2` dans une position théoriquement nulle ne prouve pas
que le modèle joue mieux que la tablebase : en autojeu, le camp défenseur peut
commettre une erreur. Pour les petites strates, la classe WDL exacte de la
position initiale doit donc rester visible, plutôt que d’être résumée uniquement
par un scalaire « conversion ».

De même, Scan d10 peut sous-convertir ou sur-convertir certaines strates. Sa
courbe sert d’ancre empirique, pas de plafond absolu.

## 8. Invariants

- aucune donnée Scan dans le train ;
- aucune modification des poids role-aware à partir de Scan ;
- EGDB exacte exigée à 100 % pour les deux strates couvertes ;
- mêmes octets A64/B64 pour V1, V2, EGDB et Scan ;
- résultats par strate toujours publiés ;
- macro-moyenne stratifiée principale, global brut secondaire ;
- aucune promotion, continuation P2 ou gate externe automatique.
