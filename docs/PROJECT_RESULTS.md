# Jass — synthèse consolidée des résultats du projet

> **Mis à jour :** 2026-08-30  
> **Rôle :** registre scientifique courant des directions établies/fermées ; empêcher de rouvrir une piste close sans fait nouveau.  
> **État vivant L3 :** [L3_CURRENT.md](L3_CURRENT.md)  
> **Historique consolidé antérieur complet :** [PROJECT_RESULTS_PRE_T3_20260830.md](archives/PROJECT_RESULTS_PRE_T3_20260830.md)

Le registre exhaustif maintenu jusqu'au 19 août 2026 est archivé **byte-identique** au lien ci-dessus. Le présent fichier conserve les résultats qui pilotent directement l'état courant et ajoute les terminaux T3/F6 du 30 août. En cas de contradiction, le verdict terminal le plus récent fondé sur un run complet et son manifest prévaut.

## 1. Règle de lecture

| Statut | Sens |
|---|---|
| **établi** | résultat direct suffisamment dimensionné ou répliqué |
| **supporté** | direction cohérente mais précision/réplication limitée |
| **clos** | mécanisme testé sans gain utile ou avec régression ; ne pas relancer à l'identique |
| **supersédé** | résultat réel dont l'interprétation a été corrigée ultérieurement |
| **non testé** | idée ou exécution incomplète ; ne pas la présenter comme réfutée |
| **décision de programme** | choix de périmètre distinct d'une preuve scientifique |

Une porte close ne se rouvre que si un élément causal change réellement. Augmenter seulement le volume, changer une seed ou relire une cohorte consommée ne suffit pas.

## 2. État courant

### 2.1 Champion de production

`CURRICULUM` reste le champion de production. Aucun artefact T3 n'est promu ou baké.

### 2.2 Verdict offline T3

Le terminal preregistré est :

```text
F6_TRANSFER_ESTABLISHED_D1_NOT_ADDITIVE
```

Sur un fresh commun, T3-A `F6_ONLY` a établi un transfert massif des 66 observables F6 : pairwise `0.7831693588` contre T0/CURRICULUM `0.6082147602`, delta A−T0 `+0.1749545986`, CI95 `[+0.1694074710 ; +0.1804750871]`. Le gain est positif dans P0/P1/P2/P3 et dans les deux couleurs.

L'ajout du scalaire D1 scellé n'est pas additif : B−A pairwise `-0.0049429348`, CI95 `[-0.0083936669 ; -0.0014982551]`, négatif dans les quatre phases et les deux couleurs. Aucun troisième bras, retune ou réemploi du fresh consommé n'est autorisé.

### 2.3 Runtime R0-v4

R0-v4 a établi le contrat production-leaf exact :

```text
R0_V4_PRODUCTION_LEAF_CONTRACT_ESTABLISHED
```

Job `cpx62-1685-l3-t3-f6-runtime-r0-v4`, attempt `20260830T083226Z-0ead13cb`, completed exit `0`. Ce gate a autorisé **Pool1 uniquement** et n'était pas un résultat de force.

### 2.4 Pool1 T3-A/F6 — direction de force v4 fermée

Le PRIMARY CPX62 a été exécuté :

- job `cpx62-1686-l3-t3-f6-runtime-strength-pool1-v4` ;
- attempt `20260830T104034Z-0ead13cb` ;
- `6000` parties, exit `0` ;
- reçu terminal read-only `cpx62-1689-l3-t3-f6-runtime-pool1-terminal-receipt-v1`, attempt `20260830T114717Z-ea643d77`.

Résultat exact :

```text
VERDICT = T3_F6_RUNTIME_STRENGTH_NOT_SUPPORTED
W/D/L T3-A = 1167 / 180 / 4653
score T3-A = 0.2095
Elo T3-A - CURRICULUM = -230.6871387863655
game CI95 = [0.19943856856108436 ; 0.21956143143891563]
paired CI95 = [0.20033333333333334 ; 0.21866666666666668]
P(score>0.5) = 0.0
POOL2_AUTHORIZED = FALSE
```

**Statut : clos.** Le gain offline F6 ne se convertit pas en gain de force native dans l'implémentation v4. Le résultat est loin de la zone d'incertitude. Aucun Pool2 v4, Pool3, bake ou promotion n'est autorisé.

Cette fermeture ne rétracte pas le verdict offline : elle établit précisément que **transfert statique et force au temps sont deux portes différentes**.

### 2.5 Coût runtime — hypothèse technique forte, pas nouveau verdict scientifique

Le diagnostic HOME post-terminal `home-1688-l3-t3-f6-v4-q00-native-repair-v1` a confirmé que le binaire CPX gelé n'était pas portable vers HOME (`SIGILL/132`), puis qu'un rebuild HOME natif des mêmes sources pouvait exécuter le sizer. Sur ce build technique :

```text
wall_ratio_t3_over_curriculum = 37.154452
nps_ratio_t3_over_curriculum = 0.053152
strength_games = 0
scientific_decision = FALSE
```

Ces mesures ne sauvent ni ne réinterprètent Pool1. Elles motivent uniquement l'ingénierie exacte O1.

## 3. Prochaine étape autorisée : O1 exact-cache, technique uniquement

Preregistration : [L3_T3_F6_RUNTIME_EXACT_CACHE_O1_20260830.md](experiments/L3_T3_F6_RUNTIME_EXACT_CACHE_O1_20260830.md).

O1 teste **une seule transformation** : mémoriser le résiduel raw F6 d'une position déjà évaluée, avec cache direct-mapped `65536` entrées, clé complète board+STM vérifiée à chaque hit et index FNV-1a exactement gelé. Le cache est désactivé par défaut et son activation O1 est fail-closed à `threads == 1`.

O1 doit passer, dans cet ordre : contrats unitaires ; équivalence leaf bit-à-bit ; équivalence search exacte à budgets fixes ; seulement ensuite profil de coût CPX62. Les racines et le cycle de vie du cache sont preregistrés ; aucun sweep de taille/hash/lifecycle n'est permis.

**O1 joue zéro partie de force.** Il n'autorise jamais Pool2, bake ou promotion. Si l'optimisation est établie et suffisamment prometteuse, tout nouveau test causal de force exige une preregistration séparée et un fresh distinct après le terminal O1. Une éventuelle O2 exige également sa propre preregistration.

## 4. Résultats historiques encore structurants

Les détails exhaustifs, valeurs, portes closes et incidents historiques jusqu'au 19 août sont conservés dans l'[archive byte-identique](archives/PROJECT_RESULTS_PRE_T3_20260830.md). Les points structurants restent :

- corrections de méthode/search/fit (`--score-drop`, NMP/threat/history, MMTO) ont fourni des gains réels ;
- `gen2-mmto`, F2M, TURNOVER puis EXACT ont constitué les principales successions historiques ;
- le fold sur la symétrie exacte du damier a apporté un gain établi, alors que des contraintes approximatives injectaient un biais ;
- la loss holdout, la pairwise offline, la couverture de buckets ou la divergence de politique ne sont jamais des substituts à la force jouée ;
- plusieurs mécanismes ont amélioré un diagnostic de profondeur fixe tout en perdant au movetime parce que le coût de nœuds dominait ;
- CTX3 a confirmé qu'une information prédictive réelle peut régresser une fois injectée dans le canal de décision testé ;
- les cohorts consommés ne doivent pas être réutilisés pour sélection/tuning post-hoc.

## 5. Garde anti-réouverture

1. `CURRICULUM` reste champion jusqu'à une succession explicitement autorisée.
2. `F6_TRANSFER_ESTABLISHED_D1_NOT_ADDITIVE` reste le verdict offline T3.
3. `T3_F6_RUNTIME_STRENGTH_NOT_SUPPORTED` reste le verdict causal runtime v4.
4. `POOL2_AUTHORIZED__FALSE` est permanent pour cette campagne v4.
5. Aucun nouveau modèle, retune/refit/calibration, D1 ou retrait de F6 n'est autorisé dans O1.
6. Pool1 v4 ne peut jamais devenir un corpus de sélection pour choisir une variante d'optimisation.
7. Toute nouvelle force sur une implémentation optimisée exige une nouvelle preregistration et un fresh distinct.

Le registre courant suit maintenant la frontière O1 ; l'historique antérieur reste intégralement auditable dans l'archive liée en tête.