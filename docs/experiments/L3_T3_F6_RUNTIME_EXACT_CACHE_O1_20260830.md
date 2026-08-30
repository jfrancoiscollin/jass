# L3 — T3-A/F6 Runtime Exact Cache O1 — preregistration

> **Date : 30 août 2026**
> **Statut : preregistration uniquement.** Aucun code d'optimisation ni nouveau job de recherche/force n'est autorisé par ce document tant que cette preregistration n'est pas mergée.

## 1. Contexte terminal immuable

La science du candidat reste gelée :

- `CURRICULUM` reste champion de production ;
- T3-A/F6 SHA256 : `16e5db8fd78849bba12b158eee5c1da4ab170129d8aeac1b91ab7a40ad9d0bb2` ;
- CURRICULUM SHA256 : `319d174f4b548b1655aad4bb30d4c6dc86c08dd715c9c23f8b19ba1937dc0be1` ;
- verdict offline : `F6_TRANSFER_ESTABLISHED_D1_NOT_ADDITIVE` ;
- R0-v4 : `R0_V4_PRODUCTION_LEAF_CONTRACT_ESTABLISHED` ;
- Pool1 PRIMARY CPX62 : job `cpx62-1686-l3-t3-f6-runtime-strength-pool1-v4`, attempt `20260830T104034Z-0ead13cb`, `6000` games, exit `0`, verdict `T3_F6_RUNTIME_STRENGTH_NOT_SUPPORTED` ;
- reçu terminal : `cpx62-1689-l3-t3-f6-runtime-pool1-terminal-receipt-v1`, attempt `20260830T114717Z-ea643d77`.

Le résultat PRIMARY exact est :

```text
wins T3-A       = 1167
draws           = 180
wins CURRICULUM = 4653
score T3-A      = 0.2095
Elo T3-CURR     = -230.6871387863655
game CI95       = [0.19943856856108436 ; 0.21956143143891563]
paired CI95     = [0.20033333333333334 ; 0.21866666666666668]
P(score>0.5)    = 0.0
POOL2_AUTHORIZED = FALSE
```

Ce terminal est immuable. O1 ne peut ni le réinterpréter, ni autoriser Pool2, ni le transformer en résultat positif.

Le diagnostic HOME post-terminal `home-1688-l3-t3-f6-v4-q00-native-repair-v1` est technique uniquement. Il a confirmé que le binaire CPX gelé provoque `SIGILL/132` sur HOME, puis qu'un rebuild HOME natif des mêmes sources peut exécuter le sizer. Sur ce build HOME, le depth-9 technique a publié :

```text
wall_ratio_t3_over_curriculum = 37.154452
nps_ratio_t3_over_curriculum  = 0.053152
strength_games                 = 0
scientific_decision            = FALSE
```

Ces nombres motivent une optimisation exacte mais ne constituent pas un nouveau verdict de force.

## 2. Observation de code qui motive O1

Le wrapper T3-A courant calcule le résiduel par :

```text
Network::residual_parent(pos)
  -> residual_features::extract_f6(pos)
  -> Model::residual_parent(features)
```

`extract_f6` est recalculé à chaque évaluation statique T3. F1 génère les coups légaux des deux couleurs. F2 `RESPONSE_FRONTIER` réutilise la première liste de réponses puis, pour chaque réponse légale, construit la position suivante et relance `generate_legal_moves` afin de produire ses statistiques. Le coût est donc structurellement bien supérieur au petit MLP final.

O1 teste une seule transformation d'ingénierie : **mémoriser exactement le résiduel F6 d'une position déjà évaluée**, sans modifier F6, le réseau, le score de base ou la recherche.

## 3. Question O1

> Peut-on éviter les recomputations F6 répétées dans un même processus de recherche tout en conservant une équivalence fonctionnelle exacte du T3-A gelé ?

O1 n'est **pas** un nouveau model search et ne teste pas la force Elo.

## 4. Intervention gelée

Implémenter un cache privé au wrapper `t3_f6::Network` avec le contrat suivant :

1. cache du **résiduel raw `double`** retourné par `Model::residual_parent`, pas du score CURRICULUM ;
2. clé complète = white men, white kings, black men, black kings, side-to-move ;
3. une collision d'index ne peut jamais produire un hit : la clé complète stockée doit être comparée avant réutilisation ;
4. capacité fixe `65536` entrées ; aucun sweep de taille ;
5. indexation déterministe par un mélange 64-bit de la clé complète ; remplacement direct-mapped déterministe ;
6. hit : retourner exactement le `double` stocké ; miss : exécuter exactement l'ancien chemin `extract_f6(pos).all_new()` puis MLP, stocker et retourner ;
7. `base_->evaluate(pos)` reste appelé selon le chemin actuel ; aucun cache du score CURRICULUM ;
8. aucun changement de F1/F2/F3/F4/F5, normalisation, poids, arrondi, clamp, POV, movegen, qsearch, pruning, ordering, TT ou terminal/TB ;
9. cache désactivé par défaut dans le binaire tant que le nouveau contrat n'est pas explicitement activé pour O1 ;
10. compteur diagnostique exact : lookups, hits, misses, replacements et `extract_f6` réellement exécutés.

Aucune autre optimisation n'est autorisée dans O1. En particulier : pas de refactor F2, pas de vectorisation approximative, pas de compression, pas de quantification, pas de changement de précision.

## 5. Données et support

O1 peut utiliser les cohorts déjà consommés **uniquement comme tests techniques d'équivalence et de coût** ; ils restent interdits à tout fit, tuning, calibration ou model selection.

Support gelé :

- corpus R0-v4 exact `4096` positions de `cpx62-1685` ;
- sous-ensemble search R0-v4 exact ;
- aucun score teacher/deep nécessaire ;
- aucun nouveau fresh n'est généré en O1.

## 6. Gates exacts

### Gate A — build et unit contracts

- build Release avec les flags production R0-v4 ;
- tests existants T3/F6 inchangés ;
- nouveaux tests cache : miss, hit, collision d'index avec clé différente, remplacement, STM distinct ;
- aucun hit ne doit être accepté sur simple hash/index sans égalité de clé complète.

### Gate B — équivalence leaf exacte

Sur les `4096` positions R0-v4, dans plusieurs ordres déterministes incluant des répétitions :

- résiduel raw OFF-cache vs ON-cache : égalité bit-à-bit `double` ;
- score T3 entier : égalité exacte ;
- saturation/non-finite : `0` différence ;
- mêmes résultats après flush explicite du cache ;
- au moins un hit réel doit être observé dans le replay avec répétitions, sinon le test de hit est invalide.

Tout mismatch donne `O1_EXACT_CACHE_EQUIVALENCE_FAILED` et STOP.

### Gate C — équivalence search exacte

Sur exactement `64` racines R0-v4, `16` par phase, sélectionnées par l'ordre benchmark déjà gelé `2026092505`, comparer cache OFF puis ON avec moteur/state/TT frais par bras :

- depth exact `1` ;
- depth exact `9` ;
- nodes exact `1000` ;
- nodes exact `10000`.

Pour chaque root/budget, exiger égalité exacte de tous les champs déterministes déjà suivis en R0-v4 : score, best move, completed/effective depth, PV, nodes, eval calls, qnodes, terminal/TB hits, TT probes/hits, cutoffs, reductions, extensions, qsearch calls et stop reason.

Les compteurs du cache et le wall-clock ne font évidemment pas partie de l'égalité.

Tout mismatch donne `O1_EXACT_CACHE_SEARCH_EQUIVALENCE_FAILED` et STOP.

### Gate D — profil coût technique

Seulement après A/B/C PASS, mesurer sur CPX62 avec le **même exécutable O1** et mêmes bytes/search :

- exactement `128` racines R0-v4, `32` par phase, ordre déterministe `2026092505` ;
- cache OFF et ON, ordre alterné ;
- depth exact `9` ;
- publier wall time, NPS, nodes, eval calls, effective depth, cache hit-rate, `extract_f6` executions, movegen calls et famille F1..F5 si disponibles.

Aucun seuil de performance ne transforme O1 en résultat scientifique. Le profil est descriptif : la seule condition de PASS O1 est l'équivalence exacte A/B/C plus une exécution technique saine.

## 7. Verdicts O1 autorisés

```text
O1_EXACT_CACHE_EQUIVALENCE_FAILED
O1_EXACT_CACHE_SEARCH_EQUIVALENCE_FAILED
O1_EXACT_CACHE_ESTABLISHED
O1_RUNTIME_TECHNICAL_FAILED
```

`O1_EXACT_CACHE_ESTABLISHED` signifie uniquement : optimisation exacte démontrée et coût mesuré.

Il **n'autorise aucune partie de force**. Si O1 est établi et son profil est jugé suffisamment prometteur pour justifier un nouveau test causal, une **nouvelle preregistration séparée** devra définir un nouveau fresh de force et ses seeds avant toute partie. Si O1 est trop peu efficace, toute optimisation O2 (par exemple refactor exact de F2) exige elle aussi une preregistration séparée ; aucun sweep opportuniste n'est permis dans O1.

## 8. Interdictions

- aucun nouveau modèle ;
- aucun retune/refit/calibration ;
- aucun D1 ;
- aucun retrait ou approximation de feature F6 ;
- aucun changement de search ;
- aucune réutilisation de Pool1 pour sélectionner une variante de cache ;
- aucune promotion/bake ;
- aucun Pool2 v4 ;
- aucune interprétation de HOME 1688 comme force.

## 9. Traçabilité requise

Le terminal O1 devra publier : code SHA, bytes T3/CURRICULUM, capacité/cache key contract, compteurs hit/miss/replacement, résultats d'équivalence leaf/search, profil coût, host/nproc, build flags, et verdict exact.

Les terminaux `1685`, `1686`, `1688`, `1689` restent immuables et doivent être référencés, jamais réécrits.
