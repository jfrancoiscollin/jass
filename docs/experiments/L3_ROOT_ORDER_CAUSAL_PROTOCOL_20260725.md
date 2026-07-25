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

Le planning doit contenir chaque coup légal exactement une fois. Toute
profondeur absente, tout doublon ou coup inconnu incrémente
`rootorderfail` et invalide le run. L’intervention est désactivée par défaut.

## Deux readouts

1. **48 sentinelles, d1–d12.** Comparaison appariée du meilleur coup Jass avec
   Scan avant/après replay. L’ordre final doit être identique sur 48/48 à
   chaque profondeur.
2. **Conversion complète d10, 300 + 300 positions.** Même défenseur Gen2 Q00,
   mêmes poids et mêmes positions que 0959. Avant chaque coup de l’attaquant,
   Scan fournit uniquement le planning racine ; son meilleur coup et ses
   scores sont ignorés.

Les résultats témoins `SCAN_VERIFY_THREAT` d10 de 0959 sont réutilisés, donc
aucune partie témoin n’est recalculée.

## Règle de décision

1. Borne basse Wilson 95 % ≥ 80 % sur les deux strates :
   `ROOT_ORDER_REPLAY_RECOVERS_CONVERSION`.
2. Sinon, gain de conversion apparié ≥ 10 points avec IC95 strictement positif
   sur les deux strates :
   `ROOT_ORDER_CAUSAL_PARTIAL_RECOVERY`.
3. Sinon, si le taux de meilleur coup d12 gagne ≥ 10 points avec IC95
   strictement positif :
   `ROOT_ORDER_EXPLAINS_ROOT_CHOICE_NOT_CONVERSION`.
4. Sinon :
   `ROOT_ORDER_NOT_DOMINANT_RECURSIVE_TRACE_REQUIRED`.

Un contrat d’ordre incomplet produit `ROOT_ORDER_REPLAY_CONTRACT_FAILED`.

## Garde-fous

- HOME uniquement ; source, runtime, paramètres, poids et corpus gelés.
- Scan ne fournit ni score, ni poids, ni coup sélectionné à Jass.
- Aucun entraînement, aucune promotion, aucune continuation automatique.
- `artefacts/` et `metadata.json` locaux préservés.
