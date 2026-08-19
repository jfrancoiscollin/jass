# CTX3 — autopsie directionnelle des décisions

## Question

Le gate causal cpx62-1419 établit que le modèle CTX3 aligné est moins fort
que son contrôle shuffled, malgré un signal statique indépendant confirmé par
1416b et un mapper causal valide confirmé par 1417.

L'autopsie tranche entre deux mécanismes :

1. une erreur de signe, de perspective ou de negamax ;
2. une information observationnelle réelle qui change les actions dans une
   direction nuisible lorsqu'elle est compressée dans la cible scalaire.

## Sources immuables

- modèles ALIGNED/SHUFFLED : cpx62-1418, attempt
  20260819T074026Z-1e718553 ;
- deux pools frais et preuves de force : cpx62-1419, attempt
  20260819T112556Z-8adc506a ;
- audit terminal : cpx62-1420, attempt
  20260819T134046Z-69170897 ;
- juge indépendant : champion CURRICULUM de cpx62-1341, SHA brut
  319d174f4b548b1655aad4bb30d4c6dc86c08dd715c9c23f8b19ba1937dc0be1.

Aucune cohorte frozen n'est lue.

## Protocole préenregistré

- 192 ouvertures par pool, soit 384, sélectionnées par hash déterministe avec
  seed 2026081913 ;
- même binaire 8cf exact-fold/tempo et même Q00 que 1419 ;
- décision ALIGNED et SHUFFLED à profondeur 9 ;
- uniquement lorsqu'elles diffèrent, évaluation des deux enfants à profondeur
  12 par CURRICULUM, ALIGNED et SHUFFLED ;
- toute valeur enfant est convertie en POV racine par
  V_root(action) = -V_child_stm ;
- 8 ouvertures par pool et trois modèles sont aussi rejoués sous la symétrie
  exacte rot180 + colour-swap. Les scores STM doivent être byte-exacts ;
- bootstrap 100 000 des deltas de valeur des actions retournées.

Le seuil minimal est 24 décisions retournées. Le diagnostic
DECISION_CHANNEL_CONFIRMED_HARMFUL demande conjointement que la borne haute
IC95 de V(aligned_action)-V(shuffled_action) soit sous zéro pour CURRICULUM
et pour la moyenne des trois juges.

Une violation de symétrie classe le défaut comme technique et impose une
correction de perspective avant toute suite. Sinon, l'algèbre de cible scalaire
reste fermée et la suite rationnelle est CTX4 : avantage d'action
contre-factuel, conservé dans un canal de décision séparé et utilisé seulement
comme tie-break dans une bande d'incertitude de la value principale.

## Sizing

CPX est contractuellement à 16 CPU. Huit shards sont lancés, avec timeout par
shard et attente explicite de leurs PID. Par comparaison avec les recherches
depth-9 du gate 1419, l'ETA préenregistrée est 15–35 minutes, build inclus.

## Interdictions

Zéro fit, zéro self-play, zéro partie de force, zéro lecture frozen et aucune
promotion. Le job ne produit qu'un diagnostic causal auditable.
