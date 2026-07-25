# L3 — causalité de l’ordre racine Scan (0961, préenregistré)

## Preuve de départ

0960bis a montré que les deux moteurs génèrent exactement le même ensemble de
coups sur 48/48 sentinelles, mais que leur ordre racine diverge sur 40/48 à
d12. Le meilleur coup ne coïncide alors que sur 32/48. La première divergence
est l’ordre racine pour 35 sentinelles, le score récursif pour 12 et la fenêtre
pour une.

Cette observation localise un candidat ; elle ne prouve pas encore qu’il cause
le déficit de conversion.

## Intervention causale

Une compilation diagnostique de Scan gelé recherche la même position et
n’émet que l’ordre complet des coups racine de la dernière tentative à chaque
profondeur. Cet ordre est injecté dans Jass avant chaque tentative racine.

Jass conserve intégralement :

- les poids Scan exacts ;
- ses fenêtres, sa TT, ses retours de score et sa recherche interne ;
- le bras `SCAN_VERIFY_THREAT` de 0959.

Le planning doit contenir chaque classe de coup légal
`(départ, arrivée, prises)` exactement une fois. Si Jass contient plusieurs
chemins de prise encodant la même classe, ils sont conservés mais regroupés
dans l’ordre stable à l’emplacement fourni par Scan. Toute profondeur absente,
toute classe dupliquée/inconnue ou tout ensemble de classes différent
incrémente `rootorderfail` et invalide le run. L’intervention est désactivée
par défaut.

## Deux readouts

1. **48 sentinelles, d1–d12.** Comparaison appariée du meilleur coup Jass avec
   Scan avant/après replay. L’ordre final doit être identique sur 48/48 à
   chaque profondeur.
2. **Conversion complète d10, 300 + 300 positions.** Même défenseur Gen2 Q00,
   mêmes poids et mêmes positions que 0959. Le run corrigé ajoute un bras
   `NATIVE_REPAIRED` sans oracle, puis un bras `ROOT_ORDER` où, avant chaque
   coup de l’attaquant, Scan fournit uniquement le planning racine ; son
   meilleur coup et ses scores sont ignorés.

Les résultats témoins `SCAN_VERIFY_THREAT` d10 de 0959 sont réutilisés, donc
aucune partie témoin n’est recalculée.

Le premier run 0961 a révélé deux défauts de légalité qui invalidaient son
readout : les chemins de prise sémantiquement identiques n’étaient pas
dédupliqués et une racine de tablebase nulle non terminale renvoyait `0-0`.
Les deux réparations s’appliquent aux bras natif et root-order. La comparaison
ancien témoin → natif réparé mesure leur effet système ; natif réparé →
root-order isole ensuite l’ordre.

## Règle de décision

1. Borne basse Wilson 95 % du natif réparé ≥ 80 % sur les deux strates :
   `LEGALITY_REPAIR_RECOVERS_CONVERSION`.
2. Sinon, borne basse Wilson 95 % du replay ≥ 80 % sur les deux strates :
   `ROOT_ORDER_REPLAY_RECOVERS_CONVERSION`.
3. Sinon, gain de conversion apparié ≥ 10 points avec IC95 strictement positif
   sur les deux strates :
   `ROOT_ORDER_CAUSAL_PARTIAL_RECOVERY`.
4. La même règle appliquée ancien témoin → natif réparé produit
   `LEGALITY_REPAIR_CAUSAL_PARTIAL_RECOVERY`.
5. Sinon, si le taux de meilleur coup d12 gagne ≥ 10 points avec IC95
   strictement positif :
   `ROOT_ORDER_EXPLAINS_ROOT_CHOICE_NOT_CONVERSION`.
6. Sinon :
   `ROOT_ORDER_NOT_DOMINANT_RECURSIVE_TRACE_REQUIRED`.

Un contrat d’ordre incomplet produit `ROOT_ORDER_REPLAY_CONTRACT_FAILED`.

## Garde-fous

- HOME uniquement ; source, runtime, paramètres, poids et corpus gelés.
- Scan ne fournit ni score, ni poids, ni coup sélectionné à Jass.
- Aucun entraînement, aucune promotion, aucune continuation automatique.
- `artefacts/` et `metadata.json` locaux préservés.

## Verdict certifié

`home-0961ter-l3-pure-m1-legality-root-order-causal-v1`, code
`f4ff6548fe9aa46ee4d5161473d8d1ddb8471e7c`, est terminé avec le verdict
`LEGALITY_REPAIR_RECOVERS_CONVERSION`.

Face au défenseur Gen2 historique inchangé, l’attaquant Scan-exact réparé
obtient :

- `p3_mince` : 297 victoires, 0 nulle, 3 défaites, soit 99,00 % ;
- `p4_egal` : 294 victoires, 0 nulle, 6 défaites, soit 98,00 %.

Les témoins antérieurs étaient respectivement à 38,00 % et 35,33 %. Les gains
appariés de la réparation sont donc de +61,00 et +62,67 points, sans aucune
régression de position gagnante vers une non-victoire.

L’ordre racine Scan porte les deux strates à 299/299 victoires valides. Son
effet résiduel est seulement de +1,00 point sur `p3_mince` et +2,01 points sur
`p4_egal`, avec zéro échec de planning. La cause dominante du faux plafond
était donc la légalité/terminaison du moteur Jass, pas l’ordre racine.

Archive immuable :
`r2:jass-data/runs/home-0961ter-l3-pure-m1-legality-root-order-causal-v1/20260725T132947Z-f4ff6548`.

## Reprise M1

La prochaine mesure rejoue la matrice C0/P1/F500/F2M/R2M et les trois
ablations sur la jauge 0954. Seul l’attaquant reçoit la réparation certifiée ;
le défenseur Gen2 reste compilé depuis le code historique 0955. Les résultats
sont appariés position par position au registre 0955. Ce protocole distingue
ainsi la capacité réelle des poids M1 à convertir de l’effet moteur maintenant
mesuré. Il reste non promotable et sans continuation automatique.
