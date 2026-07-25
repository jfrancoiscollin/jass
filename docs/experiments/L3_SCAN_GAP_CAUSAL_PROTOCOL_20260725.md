# L3 — localisation causale du gap Scan (préenregistré, 2026-07-25)

## Point de départ

La jauge corrigée et stable contient 300 positions `p3_mince` et 300
`p4_egal`. Sur cette même jauge, contre le même défenseur Gen2 Q00 d10 :

- le meilleur modèle appris (`AB_EXTRAS`) convertit 39,33 % / 42,00 % ;
- Scan 3.1 d10 convertit 100 % / 100 % ;
- Scan d12 donne exactement le même 100 % / 100 %.

Le seuil de 70–80 % est donc atteignable. Le volume M1 seul n’a pas débloqué
la conversion. La question causale restante est : le signal manque-t-il dans
les poids appris, ou la recherche Jass ne sait-elle pas exploiter même
l’évaluation de Scan ?

## Intervention exacte

Le fichier gelé Scan `data/eval`
(`sha256=0e7161c38af605f5e367f3f8fe17525d1c40db722714c68921971b386e58abba`)
est porté algébriquement vers PJTW v3 :

- quatre tables Scan sont développées sur les huit bandes 8cf ;
- permutations ternaires, phases MG/EG, PST, matériel, mobilité des dames,
  skew et convention de signe sont transformés sans fit ;
- aucun label, aucune régression et aucune distillation ne sont utilisés ;
- la phase tempo, le draw scaling, la mobilité par dame et l’arrondi suivent
  le runtime Scan 3.1.

Avant les matchs, le job compile un probe directement contre le bundle source
Scan gelé (`7aae17e7...`) et exige une égalité statique bit-à-bit sur les 600
positions. Toute différence annule le job.

## Plan 2×2

Le défenseur reste Gen2 Q00 d10. Les départs, couleurs, limites et positions
sont identiques et appariés par index.

| Évaluation côté attaquant | recherche Jass d10 | recherche Jass d12 |
|---|---:|---:|
| `AB_EXTRAS` apprise | réutilise 0955 | nouveau |
| poids Scan 3.1 exacts | nouveau | nouveau |

Les deux lignes Scan natif d10/d12 de 0956 restent des bornes externes.
Une nulle est une non-conversion valide.

## Règle de décision préenregistrée

Le plan produit une localisation, jamais une promotion automatique.

1. **`EVAL_WEIGHTS_DOMINANT`** : la borne basse Wilson 95 % de
   `SCAN_EXACT_D10` atteint 80 % dans les deux strates.
   Suite : reproduire le fit Scan (fold exact, conservation des poids rares,
   replay cumulatif, génération d12), toujours en self-play WDL.
2. **`SEARCH_DEPTH_DOMINANT`** : d10 échoue, mais d12 atteint ce plancher dans
   les deux strates et l’effet apparié de profondeur est positif.
   Suite : localiser horizon/extensions et calibrer le coût HOME avant tout
   nouvel entraînement.
3. **`SEARCH_IMPLEMENTATION_DOMINANT`** : même la borne haute Wilson 95 % de
   `SCAN_EXACT_D12` reste sous 80 % dans les deux strates.
   Suite : comparer les arbres Scan/Jass sur les mêmes positions ; ne pas
   générer une nouvelle lignée tant que l’arbre n’est pas corrigé.
4. Sinon : **`MIXED_OR_UNRESOLVED`**. Une réplication ciblée ou d14 sera
   soumise à revue humaine.

## Garde-fous

- HOME uniquement ; aucune box supprimée.
- SHAs des jauges, du runtime, du bundle source et des poids vérifiés.
- Aucune modification de `artefacts/` ou `metadata.json`.
- Pas de promotion, pas de continuation automatique.
- Le choix de la branche suivante exige une revue humaine du readout.
