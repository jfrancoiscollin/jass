# Jass — synthèse consolidée des résultats du projet

> **Mis à jour :** 2026-09-23
> **Rôle :** registre scientifique courant des directions établies/fermées ; empêcher de rouvrir une piste close sans fait nouveau.  
> **État vivant L3 :** [L3_CURRENT.md](L3_CURRENT.md)  
> **Historique consolidé antérieur complet :** [PROJECT_RESULTS_PRE_T3_20260830.md](PROJECT_RESULTS_PRE_T3_20260830.md)

Le registre exhaustif antérieur reste archivé byte-identique au lien ci-dessus. Le présent fichier conserve seulement les résultats qui pilotent directement la frontière scientifique actuelle. En cas de contradiction, le verdict terminal le plus récent fondé sur un run complet et son manifest prévaut.

## Chinook — diagnostics terminés, force causale non encore testée

La chaîne Chinook a atteint un candidat runtime causal, mais **aucun résultat de force
CHINOOK_HYBRID vs CURRICULUM n'est encore établi**.
[Handoff exact de reprise](experiments/L3_CHINOOK_PAUSE_HANDOFF_V1_20260923.md).

2079 (`CHINOOK_ERROR_MINING_COMPLETE_V1`) a terminé l'exploration descriptive des
512 racines gelées. 2080 (`CHINOOK_INTERACTION_AUDIT_COMPLETE_V1`) a terminé les
interactions fixes ; `P2_CORE` est la plus forte observée (support 29, 13 gross
errors, taux 0,4482758621, lift 3,531034483). Ces deux étapes sont
`EXPLORATORY_CONSUMED_DATA` et n'autorisent aucune causalité ou promotion.

Le runtime figé au commit `7a3a13679274079055262241c3829f4d1077d1d7` utilise
CURRICULUM hors gate et HIER dans le gate 9-19 pièces / 5-8 coups légaux /
side-to-move derrière. Le rehearsal 2081
(`20260921T200839Z-7a3a1367`) a échoué techniquement à `build-runtime` avec
`STAGE_FAILED:EXECUTE / ValueError`; il n'a donc produit **aucun verdict
scientifique** et n'a pas admis le main de 288 paires / 576 parties.

Statut de programme : **`CHINOOK_HYBRID_REHEARSAL_TECHNICAL_RECOVERY_PENDING`**.
À la reprise, réparer uniquement le blocage technique 2081, rejouer le rehearsal
inchangé, puis n'admettre le main gelé qu'après terminal READY publié. CURRICULUM
reste champion ; aucun retuning, bake ou promotion automatique.

## CLS — discordance des rejets G0 avec une perte de 100 Elo, panel clos

Le panel préenregistré LOCAL 2075/WDL 2076 est complet et authentifié : 288 paires/576 parties
par contraste, mêmes ouvertures, alpha familial 0,05. Les deux verdicts sont
`SUBSTANTIAL_LOSS_EXCLUDED`, avec intervalles [0,4145140661 ; 0,6011109339] et
[0,4040973995 ; 0,5941664894]. Terminal : `G0_PANEL_LARGE_LOSS_DISCORDANCE_REPLICATED_V1`.
[Résultat et preuves](experiments/CLS_G0_REJECTION_PANEL_V1_RESULTS_20260921.md).

Cette discordance concerne deux cas déjà rejetés et la marge de 100 Elo à la cadence
fixée ; elle n'établit ni supériorité, ni sensibilité/spécificité générale de G0.
Les intervalles contiennent 0,5. Les FAIL historiques ne changent pas, CURRICULUM
reste champion. Décision : `STOP_INTERPRET_NO_AUTO_G0_V2_NO_PROMOTION`, sans extension
du panel ni activation automatique d'une nouvelle porte. La seule suite recommandée est
une [proposition G0 V2 séparée](experiments/CLS_G0_V2_THREE_STATE_VALIDATION_PROPOSAL_V1_20260921.md).
L'audit fini de faisabilité est depuis clos avec
`G0_V2_PROPOSAL_BLOCKED_INDEPENDENT_CASES_UNAVAILABLE` : aucun ensemble indépendant
répondant aux quatre prérequis n'est établi dans les sources locales examinées.
[Preuve et portée bornée](experiments/CLS_G0_V2_CASE_FEASIBILITY_RESULTS_20260921.md).

## D4 / D4b / D4c — ordonnancement par coupure déjà exécuté

Ces pistes ne sont pas des propositions restées sans exécution. Le
[relevé des statuts terminaux canoniques](operations/D4_D4B_D4C_TERMINAL_HISTORY_20260921.json)
conserve leurs identités, sans prétendre à une nouvelle authentification R2 :

- D4 : 4 000 recherches teacher en 1862, puis publication de clôture 1866 ;
  `D4_SEARCH_UTILITY_OFFLINE_INVALID_V1` pour support exact/de phase insuffisant,
  zéro fit réalisé. C'est une invalidité de support, pas un résultat scientifique négatif.
- D4b 1868 : `D4B_MICRO_GATE0_NOT_SUPPORTED_V1`. Le signal offline favorable
  n'a pas transféré au gate runtime : gain de regret nul et ratio de temps médian
  1,0728213964, au-delà de son plafond 1,05.
- D4c 1871 : `D4C_RANK_BREAKER_OFFLINE_NOT_SUPPORTED_V1`. Le taux de changement
  TEST est 0,001 et la correction des étiquettes non premières 0,00363636,
  sous les seuils préenregistrés 0,01 et 0,05.

Leurs décisions d'arrêt restent inchangées. Aucun match de force n'est autorisé,
et changer le nom, le parent ou le bootstrap ne suffit pas à présenter cette
famille consommée comme une nouvelle confirmation indépendante.

## PL8 — reprise technique non admise, aucun verdict scientifique

La réconciliation bornée 1719/1720 du 21 septembre termine avec
`PL8_BOUNDARY_B_TECHNICAL_RECOVERY_NOT_ADMISSIBLE_V1`. Le diagnostic publié est
authentifié et le script exact prouve un arrêt avant fit, ancrage et confirmation
fraîche ; la cause de l'échec Python n'est toutefois pas identifiée. Aucun correctif
ou nouveau lancement n'est justifié par cette preuve. PL8 n'est pas déclaré
scientifiquement négatif. [Décision et limites](operations/PL8_BOUNDARY_B_1719_1720_RECOVERY_DECISION_20260921.md).

## ED4 et ED5 — confirmations fraîches négatives, familles closes

La validité technique du candidat ED4 `2e856652…` avait été acquise en 1888.
Sa confirmation D 1970 est depuis terminée avec `CAMPAIGN_ATTEMPT_SCIENTIFIC_NOT_SUPPORTED_V1`
(trois gates échoués sur quatre). ED5 D 1997 porte le même terminal avec quatre gates
échoués sur quatre. [ED4 D](experiments/L3_ED4_FRESH_D_CONFIRMATION_RESULTS_20260914.md) ·
[ED5 D](experiments/L3_ED5_FRESH_D_CONFIRMATION_RESULTS_20260915.md).

Les cohortes D sont consommées, aucune cible W/S abandonnée ne prolonge ces tentatives.
Alpha D cumulé dépensé : 0,0125, sans recyclage. Aucun gain décisionnel avec calibration
et recherche préservées n'est établi. Le mandat de recherche prospective demeure,
avec préenregistrement et données nouvelles ; il ne transforme pas ces terminaux.

## ED3-T1 — diagnostic descriptif terminé (9 septembre 2026)

1885 (répétition) et 1886 (production) sont publiés et authentifiés, avec les
mêmes sorties scientifiques et 29 régressions passées dans chaque invocation.
Le [diagnostic sur données consommées](experiments/L3_ED3_TRANSFER_DIAGNOSTIC_RESULTS_20260909.md)
décrit 44 changements de choix HARD→SOFT sur les 512 parents de confirmation,
dont neuf entrées et sept sorties du meilleur ensemble ; 18 regrets diminuent,
20 augmentent. Les distributions WDL reproduisent la perte moyenne SOFT−BASE
positive. Ce résultat exploratoire ne constitue pas une nouvelle confirmation
et ne modifie ni `ED3_SOFT_CONFIRMATION_NOT_SUPPORTED_V1` ni `STOP_ED3`.

## ED3-P2 — confirmation non supportée, STOP_ED3 (9 septembre 2026)

La confirmation préenregistrée `1884 / 20260909T051901Z-0946f57d` compare les
modèles gelés BASE / HARD / SOFT sur 512 parents frais, avec une garde WDL
historique distincte de 8 192 lignes. Verdict :
`ED3_SOFT_CONFIRMATION_NOT_SUPPORTED_V1` ; décision de programme : `STOP_ED3`.
[Preuves et résultat détaillé](experiments/L3_ED3_CONFIRMATION_RESULTS_20260909.md).

SOFT diminue ponctuellement le regret moyen, mais les deux IC95 contre BASE
et HARD incluent zéro. Sa logloss WDL est plus élevée et la borne supérieure
de différence (0,002236) dépasse la marge de non-infériorité 0,002. Le contrôle
de meilleurs coups face à BASE et celui des parents améliorés/dégradés échouent
aussi. Le Brier seul passe. Aucun gain décisionnel avec calibration préservée
n'est établi ; ce n'est pas une preuve d'effet nul. La garde historique ne
constitue pas une nouvelle mesure d'issues de parties.

Aucun fit, force jouée, promotion, bake ou suite automatique. `CURRICULUM`
reste champion ; pas de Gate0, extension de l'échantillon ou retuning ED3
sur ce résultat. Les faits historiques ED2 restent inchangés.

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

---

## 2. État courant

### 2.1 Champion de production

`CURRICULUM` reste le champion. Aucun artefact T3 n'est promu ou baké.

```text
CURRICULUM SHA256 = 319d174f4b548b1655aad4bb30d4c6dc86c08dd715c9c23f8b19ba1937dc0be1
T3-A F6_ONLY      = 16e5db8fd78849bba12b158eee5c1da4ab170129d8aeac1b91ab7a40ad9d0bb2
D1 sealed         = e91a55500713154f50be74db5d699b64d7684e1c078725d09e1d15e713549b49
RF1/F6            = 0d26ba50b668160b3da3e247cd4e1bd709c2cb7989b3b5877b9ea7deb34db58b
```

### 2.2 Verdict offline T3 — établi

```text
F6_TRANSFER_ESTABLISHED_D1_NOT_ADDITIVE
```

Sur un fresh commun :

```text
T0 pairwise   = 0.6082147602129492
T3-A pairwise = 0.7831693588009130
A - T0        = +0.17495459858796386
CI95 A - T0   = [+0.16940747096694114 ; +0.18047508706277157]
T3-B - T3-A   = -0.004942934833288572
```

Les 66 observables F6 transfèrent fortement offline. L'ajout exact du scalaire D1 scellé n'est pas additif au-dessus de F6 dans le bras joint preregistré. La cohorte `1638/1639/1640` est consommée et interdite à tout fit/tuning/calibration/feature/model selection post-hoc.

### 2.3 Runtime R0-v4 — établi

```text
R0_V4_PRODUCTION_LEAF_CONTRACT_ESTABLISHED
```

Job `cpx62-1685-l3-t3-f6-runtime-r0-v4`, attempt `20260830T083226Z-0ead13cb`, exit `0`.

### 2.4 Pool1 T3-A/F6 au temps — clos négativement

Job `cpx62-1686-l3-t3-f6-runtime-strength-pool1-v4`, attempt `20260830T104034Z-0ead13cb`, `6000` parties ; reçu terminal `cpx62-1689-l3-t3-f6-runtime-pool1-terminal-receipt-v1`.

```text
VERDICT = T3_F6_RUNTIME_STRENGTH_NOT_SUPPORTED
W / D / L T3-A = 1167 / 180 / 4653
score           = 0.2095
Elo             = -230.6871387863655
game CI95       = [0.19943856856108436 ; 0.21956143143891563]
paired CI95     = [0.20033333333333334 ; 0.21866666666666668]
P(score>0.5)    = 0.0
POOL2_AUTHORIZED = FALSE
```

**Statut : clos.** Aucun Pool2 v4, Pool3, bake ou promotion. Le verdict offline n'est pas rétracté : information statique et force au temps sont deux portes distinctes.

### 2.5 Diagnostic HOME post-Pool1 — motivation seulement

`home-1688-l3-t3-f6-v4-q00-native-repair-v1` a observé sur un rebuild HOME natif :

```text
wall_ratio_t3_over_curriculum = 37.154452
nps_ratio_t3_over_curriculum  = 0.053152
strength_games                 = 0
scientific_decision            = FALSE
```

Ces ratios appartiennent à HOME et ne peuvent pas être transportés comme rates CPX62. Ils ont motivé O1 mais ne sauvent ni ne réinterprètent Pool1.

### 2.6 O1 exact cache — terminal établi

Preregistration : [L3_T3_F6_RUNTIME_EXACT_CACHE_O1_20260830.md](experiments/L3_T3_F6_RUNTIME_EXACT_CACHE_O1_20260830.md).  
Terminal : [L3_T3_F6_RUNTIME_EXACT_CACHE_O1_RESULTS_20260830.md](experiments/L3_T3_F6_RUNTIME_EXACT_CACHE_O1_RESULTS_20260830.md).

```text
VERDICT = O1_EXACT_CACHE_ESTABLISHED
```

Reçu terminal :

```text
job     = cpx62-1705-l3-t3-f6-o1-terminal-receipt-v1
attempt = 20260830T195143Z-53bddb24
code    = 53bddb24a2d144af39df486d8c3e53b7d196cf65
exit    = 0
```

O1 conserve exactement le T3-A gelé : mêmes 66 F6, modèle/poids/normalisation, calcul/rounding/clamp, POV, movegen et search. Gate B passe sur `4096` feuilles ; Gate C passe sur `64` racines × quatre budgets avec mismatch `0` ; Gate D passe sur CPX62 avec `128` racines / `256` recherches depth-9 et arbre strictement identique OFF/ON.

Mesures Gate D :

```text
cache_hit_rate          = 0.322842
wall_ratio ON / OFF     = 0.691964
nps_ratio  ON / OFF     = 1.445162
search mismatches       = 0
nodes OFF == nodes ON   = true
eval calls OFF == ON    = true
strength_games          = 0
```

O1 économise environ `30.8 %` de wall search-only et augmente le NPS d'environ `44.5 %` sans changer l'arbre. Ce résultat ne mesure pas `nodes(T3-A)/nodes(CURRICULUM)` et ne crée aucun droit de force.

---

## 3. Programme suivant preregistré : E1 / E2 / E3

Preregistration : [L3_F6_TRANSFER_PROGRAM_E1_E3_20260830.md](experiments/L3_F6_TRANSFER_PROGRAM_E1_E3_20260830.md).  
Amendment terminal O1 : [L3_F6_TRANSFER_PROGRAM_E1_E3_O1_TERMINAL_AMENDMENT_20260830.md](experiments/L3_F6_TRANSFER_PROGRAM_E1_E3_O1_TERMINAL_AMENDMENT_20260830.md).

Le programme a été mergé byte-identique via PR `#735`, merge `f6c3c4928625d0628945eb66d7289dce24c6f551`. Le draft `#733` a été supersédé uniquement pour contourner un bug du connecteur Ready-for-review ; aucun contenu scientifique n'a changé dans cette transition.

### 3.1 E1 — attribution technique, prochain bloc

`0` partie, `0` fit. E1 mesure sur CPX62 le coût F1..F5/MLP/base et le ratio direct :

```text
nodes_ratio_E1 = sum(nodes_T3_A) / sum(nodes_CURRICULUM)
```

Support : `4096` feuilles pour l'exactitude instrumentation et `128` racines depth-9 pour le search. L'attribution primaire utilise T3-A cache O1 **OFF**. Si une famille concentre `>=60 %` du coût, seule une future ablation preregistrée séparément devient envisageable ; E1 lui-même n'ablate ni ne fit.

### 3.2 E2 — verrouillé derrière E1

E2 est un A/B frais à nœuds égaux : C1 T3-A/CURRICULUM 20k/20k, C2 CURRICULUM 20k/10k pour la pente, C3 byte-identical 20k/20k comme garde harnais ; `2700` parties au total.

Le contraste expérimental direct est C1. Le programme utilise aussi la décomposition preregistrée :

```text
delta_info = Elo(C1) + log2(nodes_ratio_E1) * slope(C2)
```

`delta_info` est explicitement une décomposition mécanistique locale, pas une identification non-paramétrique parfaite. Sa borne basse CI95 >0 peut ouvrir E3 mais ne peut autoriser bake/promotion/Pool2.

### 3.3 E3 — verrouillé derrière le gate E2

E3 est un unique fit PatternEval conditionnel où F6 sert seulement de teacher offline. Parent POV : `S_T3(parent,child) = -T3_A.evaluate(child)`.

Le corpus est résolu fail-closed comme l'input byte-exact unique du dernier stage de fit ayant produit les bytes CURRICULUM ; aucune sélection de dataset au moment du job. Un holdout fidélité neuf et target-blind doit passer avant le profil runtime. Même si projection et runtime passent, le document s'arrête **avant toute partie de force**.

### 3.4 Autorité

Le merge de la preregistration n'est pas un GO. **E1, E2 et E3 exigent chacun un GO JFC distinct** après les faits machine, rate comparable, sizing/ETA, disque et checks pré-lancement.

Au moment de cette mise à jour :

```text
E1 = NOT_STARTED
E2 = LOCKED_BEHIND_E1
E3 = LOCKED_BEHIND_E2
strength games under current active authorization = 0
```

---

## 4. Résultats historiques encore structurants

Les détails exhaustifs et les portes historiques restent dans le [snapshot antérieur](PROJECT_RESULTS_PRE_T3_20260830.md). Les points qui continuent de gouverner les décisions sont :

- corrections de méthode/search/fit (`--score-drop`, NMP/threat/history, MMTO) ont fourni des gains réels ;
- `gen2-mmto`, F2M, TURNOVER puis EXACT ont constitué les principales successions historiques ;
- le fold sur la symétrie exacte du damier a apporté un gain établi, alors que des contraintes approximatives injectaient un biais ;
- loss holdout, pairwise offline, couverture de buckets ou divergence de politique ne remplacent jamais une force correctement preregistrée ;
- plusieurs mécanismes ont amélioré un diagnostic de profondeur fixe tout en perdant au movetime parce que le coût de nœuds dominait ;
- CTX3 a confirmé qu'une information prédictive réelle peut régresser une fois injectée dans le canal de décision testé ;
- les cohorts consommés ne doivent pas être réutilisés pour sélection/tuning post-hoc.

---

## 5. Garde anti-réouverture

1. `CURRICULUM` reste champion jusqu'à succession explicitement autorisée.
2. `F6_TRANSFER_ESTABLISHED_D1_NOT_ADDITIVE` reste le verdict offline T3.
3. `T3_F6_RUNTIME_STRENGTH_NOT_SUPPORTED` reste le verdict causal runtime v4 à temps égal.
4. `POOL2_AUTHORIZED__FALSE` est permanent pour la campagne v4.
5. `O1_EXACT_CACHE_ESTABLISHED` est un terminal technique ; il ne réinterprète pas Pool1.
6. Pool1 v4 ne peut jamais servir à sélectionner une variante d'optimisation.
7. `1638/1639/1640` reste consommé pour fit/tuning/calibration/feature/model selection.
8. E1 ne peut ni ablater ni fit ; une ablation éventuelle exige sa propre preregistration.
9. E2/E3 restent fail-closed derrière leurs gates et GO distincts.
10. Toute nouvelle force sur un evaluator optimisé/distillé exige une preregistration de force séparée, un fresh disjoint et un GO séparé.

Dans le programme F6, `E1_COST_ATTRIBUTION_PENDING_EXPLICIT_GO` reste non exécuté et inchangé. La frontière opérationnelle de reprise au 23 septembre est toutefois `CHINOOK_HYBRID_REHEARSAL_TECHNICAL_RECOVERY_PENDING`, conformément au handoff Chinook ; cela ne clôt ni ne réinterprète E1.
