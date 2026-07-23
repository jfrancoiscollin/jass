# Autopsie 0842 / 0890bis — pourquoi le spécialiste TOP3 ne convertit pas

> Date : 23 juillet 2026
> Verdict : **`TOP3_SPECIALIST_RECIPE_FAILURE_LOCALIZED_FACTORS_CONFOUNDED`**
> Nature : autopsie post-hoc, sans nouveau self-play, entraînement ou gate
> Outil reproductible : `jobs/tools/l3_conversion_autopsy.py`

## 1. Conclusion

L’échec de 0890bis n’est ni une limite de l’architecture linéaire 8cf, ni une
impossibilité du self-play WDL sans oracle. Le miroir 0921 montre que le G4
L3-PURE 0842, avec la même architecture et la même recherche, améliore
causalement l’attaque **et** la défense sur les positions TOP3.

La défaillance est localisée au bundle de recette propre à 0890bis :

1. toutes les parties commencent sur `16v18`, `17v19` ou `18v20` ;
2. le corpus est quadruplé à 2 M de records par génération ;
3. la pondération role-aware `1/2/4` est appliquée dans le domaine exact.

Ces trois facteurs ont été changés ensemble. L’historique ne permet donc pas de
déclarer l’un d’eux cause unique. L’ablation minimale restante est un `2 × 2`
distribution de départ × pondération, à volume strictement identique.

## 2. Contrats identiques

Les manifests immuables de 0842 et 0890bis confirment :

- même géométrie linéaire `8cf` ;
- mêmes 63 paramètres de recherche, SHA-256
  `61cdaf50cc1948537990331d78f5b296dc6aee71cc7c2b98bcbd0969977619e1` ;
- même bootstrap matériel G0 ;
- même profondeur de jeu 8 ;
- même exploration `8 plies / 8 % / decay 60` ;
- même fit logistic, `L2=3e-5`, chunk 500 k, 25 itérations ;
- corpus frais, warm-start G2+, cible WDL terminale ;
- aucun teacher, Scan, Gen2 ou label EGDB dans l’entraînement.

Le contraste ne peut donc pas être expliqué par une classe de modèle différente.

## 3. Le corpus TOP3 quitte presque immédiatement son domaine annoncé

Les profils sont calculés sur les records réellement présentés au pipeline, pas
sur les seules positions de départ.

| Diagnostic | L3-PURE G1 | L3-PURE G4 | TOP3 G1 | TOP3 G4 |
|---|---:|---:|---:|---:|
| records | 500 000 | 500 000 | 2 000 000 | 2 000 000 |
| records par partie | 26,08 | 25,84 | 11,96 | 12,34 |
| positions uniques | 98,05 % | 98,90 % | 93,66 % | 94,75 % |
| phase ≥30 pièces | 26,43 % | 31,44 % | **0,081 %** | **0,081 %** |
| phase ≤14 pièces | 25,01 % | 22,26 % | **72,05 %** | **72,59 %** |
| nulles WDL STM | 22,61 % | 20,61 % | 7,81 % | 8,10 % |
| conversion record P1 | 97,34 % | **97,86 %** | 94,78 % | **95,11 %** |
| conversion record P2 | 78,52 % | **83,33 %** | 81,20 % | **83,01 %** |
| conversion record P3 | 53,76 % | **56,88 %** | 54,07 % | **51,33 %** |

Ainsi, 0890bis génère quatre fois plus de records, mais une distribution beaucoup
plus concentrée sur les finales et moins diverse par record. La strate mince P3
se dégrade de 2,75 points entre G1 et G4, tandis qu’elle gagne 3,12 points dans
L3-PURE. Ces taux sont des records corrélés, pas un gate de parties indépendantes,
mais leur pente est cohérente avec le verdict causal.

## 4. La pondération spécialiste ne touche qu’une petite fraction du fit

En G4, avant resampling :

```text
training records                         1 800 184
exact ±2 hommes, dames égales              103 782   = 5,765 %
hors domaine, conservés comme anchors     1 696 402  = 94,235 %
```

Après resampling, le domaine exact représente 144 700 records, soit seulement
**8,038 %** du fit. À l’intérieur de cette fraction, les résultats inattendus
sont fortement amplifiés :

```text
camp +2 : win 43 066 -> 41 773 ; draw 5 786 -> 11 390 ; loss 3 843 -> 14 884
camp -2 : loss 37 566 -> 36 586 ; draw 6 389 -> 12 501 ; win 7 132 -> 27 566
```

La recette appelée « spécialiste TOP3 » entraîne donc principalement sur des
positions qui ont déjà quitté le domaine exact, en majorité à faible matériel.
La petite tranche encore exacte surpondère ensuite les renversements. C’est un
mécanisme plausible de perte de calibration du rôle attaquant, mais ce n’est pas
une preuve causale isolée : distribution et reweighting ont varié ensemble.

## 5. Preuve appariée position par position

Les tars bruts 0908 et 0921 contiennent exactement les mêmes 2 688 clés, les
mêmes FEN et le même pool :

```text
dfdbc788b715c7faab1c2e1dc1a1a7a7f7016eb1c4920b3544deacf973b569d0
```

Les deux contrôles reproduisent à l’identique les outcomes et les nombres de
plies sur 384/384 positions :

- `G0/G0` ;
- `Scan/Scan`.

Quand le seul G4 spécialiste est remplacé par le G4 pur :

| Bras | améliorées pour le rôle G4 | dégradées | inchangées | effet moyen W-L |
|---|---:|---:|---:|---:|
| attaque `G4/G0` | **171** | 7 | 206 | **+0,8542** |
| défense `G0/G4` | **171** | 17 | 196 | **+0,8021** |
| attaque `G4/Scan` | **74** | 3 | 307 | **+0,3698** |
| défense `Scan/G4` | 0 | 0 | 384 | 0 |

Les bascules principales sont franches :

```text
G4/G0 : 171 L->W contre 7 W->L
G0/G4 : 171 W->L contre 17 L->W   (le signe est inversé pour le défenseur G4)
G4/Scan : 74 L->W contre 3 W->L
```

Ce résultat est plus fort qu’une comparaison de taux agrégés : mêmes positions,
même recherche, mêmes adversaires, mêmes contrôles ; seul le modèle G4 change.

## 6. Les poids confirment une fonction apprise très différente

Les deux PJTW ont exactement le même format : version 515, scale 1000,
4 251 528 poids de patterns par phase et 120 extras par phase.

| Banque | corrélation pure/spécialiste | RMS pure | RMS spécialiste | signes opposés |
|---|---:|---:|---:|---:|
| patterns MG | 0,063 | 0,0649 | 0,0338 | 30 |
| patterns EG | 0,406 | 0,0472 | 0,2003 | 332 |
| extras MG | 0,418 | 123,26 | **44,50** | 7 |
| extras EG | 0,813 | 133,84 | 148,48 | 25 |

Les patterns sont très creux : seulement environ 0,14 % des buckets diffèrent,
donc leur corrélation globale doit être interprétée avec prudence. Le signal le
plus lisible est dans les 120 extras denses : 107/120 changent en MG, 120/120 en
EG, et la norme MG du spécialiste tombe à 36 % de celle du pur.

Cela confirme que 0890bis a convergé vers une autre fonction statique. Cette
inspection ne dit pas lequel des trois facteurs de recette a causé le drift.

## 7. Décision et prochaine expérience minimale

Décisions immédiates :

```text
0890bis_continuation_authorized=false
0890bis_promotion_authorized=false
l3_pure_conversion_capability_confirmed=true
automatic_next_job=null
```

La prochaine expérience scientifiquement propre est un écran `2 × 2` :

| Cellule | départ | pondération |
|---|---|---|
| A | standard | aucune |
| B | standard | role-aware V2 |
| C | TOP3 | aucune |
| D | TOP3 | role-aware V2 |

Les quatre cellules doivent partager G0, volume, profondeur, seeds, exploration,
split, fit et gate TOP3 stable. Une garde sur positions équilibrées reste
obligatoire. Une génération à volume égal suffit pour un écran mécanistique ;
une campagne G1–G4 n’est justifiée qu’après signal.

Cette autopsie prépare le diagnostic, mais **n’autorise pas** le lancement du
DOE.

## 8. Traçabilité

Sources :

```text
L3-PURE 0842
r2:jass-data/runs/cpx62-0842-l3-p1-frozen-v1/20260719T175711Z-337ccbdc

TOP3 0890bis
r2:jass-data/runs/ccx33-0890bis-l3-imbalance2-top3-selfplay-2m-p1/20260722T105552Z-952bea08

0908 salvagé
r2:jass-data/runs/cpx62-0920-salvage-0908-stable-top3-matrix-v1/20260723T133448Z-2ed34499

0921
r2:jass-data/runs/cpx62-0921-l3-pure-top3-stable-conversion-matrix-v1/20260723T134611Z-fbf0c93e
```

SHA-256 des entrées locales de l’autopsie :

```text
manifest 0842  672d28f14eb41cbf3a074adf407c6cd000726aadf0b9c6b756cf050c7719d9c5
manifest 0890  08eb6be803519a35d7ef1135be03c58c2deebddb8440d560bf7c5cc181b51641
tar brut 0908  9fa4bedd93df491bd0a46828dd5da30abf74fd53b116354869d453d70f2a5277
tar brut 0921  138304e583163dd3c2e7fa94b648df654c722e9f030449060b529a2944dbf50a
PJTW brut 0842  93c76031be3a039aa08eec4a1d3166321d93d602ca78a139509f8c6e90de5e86
PJTW brut 0890  4b54dfc093c6057b64f619b7e0bf4de5f6b2cc6edd1449e255fed8f7a5141eb1
```
