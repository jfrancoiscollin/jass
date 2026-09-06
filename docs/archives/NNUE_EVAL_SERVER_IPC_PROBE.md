# Sonde historique — serveur d'évaluation NNUE par IPC

Ce document conserve le verdict expérimental de la branche `claude/nnue-eval-server`. Le prototype n'est pas réintroduit dans le code actif.

## Montage

La phase 0 isolait le coût d'un aller-retour IPC, sans inférence distante : un client C++ envoyait sur un Unix socket quatre bitboards de 64 bits et l'indication du camp au trait, soit 33 octets ; le serveur Python renvoyait un score `int32` de 4 octets. La réponse était un stub déterministe afin que la mesure ne contienne ni PyTorch, ni GPU, ni véritable forward pass.

## Mesure

Sur un CPU de classe CCX23 avec le NNUE v5 256-128 HalfMen :

| Chemin d'évaluation | Latence | Débit approximatif |
|---|---:|---:|
| AVX2 local, avec accumulateur | environ 2,6 µs/appel | 389 k évaluations/s |
| stub IPC par Unix socket | environ 46,6 µs/appel | 21 k évaluations/s |

Le chemin IPC minimal est donc environ 18 fois plus lent avant même d'ajouter une inférence GPU. Le coût du seul couple `send()`/`recv()` dépasse déjà celui du forward pass AVX2 local.

## Verdict

L'architecture eval-server appel-par-appel n'est pas viable pour la recherche alpha-bêta actuelle. Elle ne pourrait devenir compétitive qu'avec un changement structurel permettant des évaluations batchées, par exemple une recherche MCTS ou apparentée ; un simple serveur GPU derrière le socket ne suffit pas.

La règle actuelle du projet reste : **aucun NNUE**, aucun réseau et aucun changement de classe tant que la classe linéaire n'a pas été poussée à fond. Cette archive ne rouvre pas cette piste.
