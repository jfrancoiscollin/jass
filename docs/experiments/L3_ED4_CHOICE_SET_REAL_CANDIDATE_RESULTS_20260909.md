# ED4-P1 — candidat réel scellé, répétition et production authentifiées

Date : 2026-09-09. Terminal : **`ED4_CHOICE_SET_REAL_CANDIDATE_SEALED_V1`**.
Le premier gate technique de la [campagne](L3_EVAL_SEARCH_CANDIDATE_CAMPAIGN_V1_20260909.md)
passe. Aucune donnée de confirmation ED4 n'a été évaluée ; aucun gain de
décision, de calibration ou de recherche n'est encore établi.

## Identités et exécution

Le [préenregistrement ED4-P1](L3_ED4_CHOICE_SET_REAL_CANDIDATE_FIT_V1_20260909.md)
est exécuté sans changement de recette par les deux jobs CPX62 :

| Mode | Job | Tentative | Stage | Publication terminée, heure FR |
|---|---|---|---:|---|
| Répétition | `cpx62-1887-l3-ed4-choice-value-fit-rehearsal-v1` | `20260909T141444Z-93e2fd1f` | 19,567523 s | 9 septembre, 16:20:08 |
| Production | `cpx62-1888-l3-ed4-choice-value-fit-production-v1` | `20260909T143020Z-93e2fd1f` | 19,527100 s | 9 septembre, 16:35:49 |

Code commun : `93e2fd1f19417bb5076e2013830ec77e999d95bf`, intégré par la
[PR #885](https://github.com/jfrancoiscollin/jass/pull/885). Les PR de contrôle
#585 et #586 ont passé leurs validations avant fusion. Chaque job est terminé
avec exit 0, une invocation réelle du solveur, 512 parents TRAIN, 4 976 lignes
enfants, 17 622 arêtes et 8 192 lignes de replay. Total : deux invocations
réelles, un candidat scientifique. Les optimisations sur fixtures sont des
contrôles techniques supplémentaires, pas des candidats sélectionnés.

CPX62 : 16 CPU disponibles, Python 3.14.4, NumPy 2.5.2, SciPy 1.18.0 ; les
bibliothèques numériques sont limitées à un thread. Les caps solveur/stage/runner
300/900/1500 s et la garde disque de 3 Gio ont été respectés. La production
complète prend 324 s de démarrage à publication ; l'attente du timer de
publication est incluse dans cette durée.

## Candidat et contrôles numériques

`ED4_CHOICE.pjtw` : 34 013 204 octets, SHA256
`2e856652efdd1d2758a949a5d4a29557fa31f4a64d55505ae6dc41482b641f5b`.
La production porte le rôle `candidate`, la répétition `development_only`.

L'objectif TRAIN passe de 1,685665562279 à 1,664130074530, et vaut
1,664136498538 après quantification. Le solveur termine en quatre itérations,
avec norme du gradient `4.295342921103809e-08`, valeur propre minimale de la
Hessienne `0.0005614269006722884` et asymétrie `1.7763568394002505e-15`.
La conclusion reste `APPROXIMATE_SECOND_ORDER_STATIONARY_POINT_ONLY` ; ces
mesures d'entraînement n'établissent aucune généralisation.

238 des 240 coefficients supplémentaires changent. Le préfixe de modèle
gelé est byte-identique à BASE. Le résidu nul reproduit BASE exactement ; les
rechargements natifs n'ont aucun désaccord. Sur les 13 168 lignes TRAIN/replay,
l'erreur maximale de logit est `5.329070518200751e-15`. Aucune recherche n'est
effectuée par ces sondes natives.

## Publication authentifiée et relue

Les deux préfixes `r2:jass-data/runs/<job>/<tentative>` sont authentifiés par
le lecteur original `fetch_result_files` : marqueur terminal, identité,
manifest, inventaire, checksums et bytes sélectionnés. La production vérifie
la répétition publiée avant admission. Après publication de 1888, une relecture
indépendante vérifie les mêmes liens, le profil, la spec, le runtime, les
33 régressions sans échec/erreur/skip, le reçu de stage, les compteurs d'effets,
le seal candidat et tous ses hashes de preuves.

| Preuve | SHA256 |
|---|---|
| Reçu de lancement 1887 | `b6983be3e06adb8024cf6647a898c132b13c8792047a1beb5373794cbca31f09` |
| Reçu de stage 1887 | `fbe90c46aa6d67b6f7cad73a9d469d3bc019372070dca033bfa182f54b40428f` |
| Seal développement 1887 | `6130fa4ce18568f03b5ce792e5e956bc6324d755f5fb1d471b73119208359349` |
| Reçu de lancement 1888 | `c193364031d7dc5f9b05d90d9f9d8d6c1ef8f6189aeda759183b4b86e9754064` |
| Reçu de stage 1888 | `970cb30df5880e0baff40f5f56456e89609c181d225cbc495f53444a825ade57` |
| Seal candidat 1888 | `5c9af7ee26fd9a5a3d5f4174d332bb57c9f8ada40f6737a5fabe11c8b4229b6a` |
| Spec normalisée commune | `a3e0a0e11cfb3c7c0794c29e35a2d0d1e186e96e45ac5606b7e3d38157909233` |

Les six payloads purs sont identiques entre répétition et production :

| Payload | SHA256 commun |
|---|---|
| `ED4_CHOICE.pjtw` | `2e856652efdd1d2758a949a5d4a29557fa31f4a64d55505ae6dc41482b641f5b` |
| `beta.npy` | `842ec44b89e88d86a2c3798c03289ae2df89186857736f04245b088162d4b43a` |
| `solver-diagnostic.json` | `77096037c2fb0b736200dc1e524229d3b31cad0025158665292757fa727531aa` |
| `fit-report.json` | `7a7e807f8c8a8429f5720be879782dfe48de82f790cb1642c155f17acbc965e4` |
| `train-contract.json` | `e2f593f5a8878226340bb0c4603686c8c95bac39ab22ba4d3a88e97b12ee1c2c` |
| `native-roundtrip.json` | `693eaab522253c13fefaa4e2dc8479dfba1badaa1dacc2c94868f4334523fc34` |

## Limites et suite

Zéro cible TEST, teacher, recherche Jass, partie, bake ou promotion. Le résumé
publié donne `scientific_verdict=null`, `scientific_success_established=false`,
`heldout_evaluation_performed=false` et `runtime_authorized=false`.

Suite de campagne : audit prospectif des exclusions et sources, puis protocoles
de confirmation frais pour décision statique, garde WDL indépendante et
recherche à nombre de nœuds égal. Les seuils et la dépense alpha restent ceux
de la campagne. `STOP_ED3` reste acquis ; `CURRICULUM` reste champion.
