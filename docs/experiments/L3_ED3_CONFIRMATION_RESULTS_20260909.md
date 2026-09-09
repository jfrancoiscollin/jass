# ED3-P2 — résultat terminal BASE / HARD / SOFT

9 septembre 2026. Le [préenregistrement ED3-P2](L3_ED3_CONFIRMATION_V1_20260909.md)
a été intégré par la [PR #880](https://github.com/jfrancoiscollin/jass/pull/880)
avant la répétition et la confirmation. Aucun paramètre scientifique n'a changé.

## Décision

`ED3_SOFT_CONFIRMATION_NOT_SUPPORTED_V1` ; suite prescrite : `STOP_ED3`.

Sur les 512 parents frais, SOFT réduit le regret moyen observé, mais aucune des
deux améliorations appariées n'a une borne basse d'IC95 strictement positive.
Le critère de non-infériorité de logloss WDL échoue également. Cette expérience
n'établit donc pas une meilleure décision avec calibration préservée. Elle ne
prouve pas que l'effet sur les décisions est exactement nul.

## Exécution et identités

- Code préenregistré et exécuté : `0946f57d5443c0507fd9210371396bdf1c49abd2`.
- Répétition : `cpx62-1883-l3-ed3-confirmation-rehearsal-v1`, tentative
  `20260909T050858Z-0946f57d`, exit 0. Les 25 tests de régression sont passés,
  sans test ignoré ; les sept phases sont complètes. Relecture R2 authentifiée :
  `FULL_PIPELINE_REHEARSAL_PASS`.
- Reçu de répétition :
  `0a4b4774214fa5a598a5e7cd8219dfc736c7713202942b4e5ef8fbe6c3a902d5`.
- Confirmation : `cpx62-1884-l3-ed3-confirmation-production-v1`, tentative
  `20260909T051901Z-0946f57d`, exit 0. Lancement par la
  [PR control #582](https://github.com/jfrancoiscollin/jass-control/pull/582),
  avec cinq tests du contrôleur passés sous Linux et CI verte.
- Admission de production : `ADMITTED_STAGE_COMPLETE_V2`, reçu
  `904b9aa82dfe9a81e273f694b34d13fa36b0d6cc7752b3b5fde27c4ce6bdc6cb`.
- Empreinte commune de la spécification :
  `97f0a739bbf580be1b502da935d20321b8835fd4002967d8f3ed01596fcd665c`.
  Seul `LAUNCH_MODE` diffère entre répétition et production.

| Bras | SHA256 du modèle gelé |
|---|---|
| BASE | `e4d510fbb9b81cbe74574d92da48e8de6f61d8f98de6472eeb409713785f0de0` |
| HARD | `3db65fe6dcc3dc828a7467ac27a43c4904c33d5791b484a2b2f19efcef70570e` |
| SOFT | `d8a193de2017a6c156a46d89692245bdc1af00d29d056af3a41e7d6d4f5a486a` |

Scellement de la cohorte :
`f1ce4d2d8cdb947c1dbfc1bdccdfc588927a4299f661d58097b0507e28a5bb8b`.
512 parents, 64 dans chacune des huit cellules phase/couleur ; 4 702 enfants
évalués, dont 27 terminaux sans recherche. La garde contient 8 192 lignes et
2 394 groupes d'ouvertures. Les sélections sont scellées avant lecture des cibles.

## Décisions statiques

Le regret est mesuré dans l'échelle du score de référence Scan à 200 000 nœuds,
avec le traitement des terminaux préenregistré. Il ne s'agit ni d'une vérité
exacte de jeu ni d'une mesure Elo.

| Bras | Regret moyen | Choix parmi les meilleurs coups Scan, ex æquo inclus |
|---|---:|---:|
| BASE | 417,9355 | 29,6875 % |
| HARD | 430,5215 | 27,7344 % |
| SOFT | 398,1172 | 28,1250 % |

| Réduction du regret par SOFT | Moyenne | IC95 apparié | Choix changés | Améliorés / dégradés / regret égal |
|---|---:|---|---:|---:|
| Contre BASE | +19,8184 | [−36,0489 ; +88,3870] | 105 | 43 / 48 / 421 |
| Contre HARD | +32,4043 | [−1,2618 ; +81,0313] | 44 | 18 / 20 / 474 |

Les nombres à regret égal portent sur tous les 512 parents ; un choix différent
peut avoir le même regret. Les IC utilisent les 20 000 tirages préenregistrés,
stratifiés par cellule. Le contrôle BASE contre BASE est non vide et exactement
nul : moyenne, bornes d'IC et nombre de changements valent zéro.

## Garde WDL

| Bras | Logloss | Brier |
|---|---:|---:|
| BASE | 0,444534212 | 0,045102540 |
| HARD | 0,446670801 | 0,045769753 |
| SOFT | 0,445931344 | 0,045515042 |

Différence de logloss SOFT − BASE : **+0,001397132**, IC95 par groupes
d'ouvertures **[+0,000569994 ; +0,002236488]**. Une valeur positive est une
dégradation de cette perte. La borne supérieure dépasse la marge gelée de
0,002 : la non-infériorité n'est pas établie. Cela ne démontre pas que la
dégradation vraie dépasse 0,002. Le Brier augmente de 0,000412502 et respecte
sa tolérance ponctuelle de 0,002.

Cette garde est un sous-ensemble historique Context30, distinct des anciennes
sélections ED2 et des groupes d'ouvertures de la répétition. Elle ne contient
aucune nouvelle issue de partie et n'est pas un corpus globalement inexposé.
Les parents de décision sont frais et exclus des empreintes énumérées au
préenregistrement ; les trajectoires peuvent partager des préfixes d'ouverture.
Les intervalles s'interprètent conditionnellement à cette population générée.

## Portes gelées et portée

| Porte | Résultat |
|---|---|
| Regret SOFT meilleur que BASE, borne basse > 0 | Échec |
| Regret SOFT meilleur que HARD, borne basse > 0 | Échec |
| Taux de meilleurs coups au moins égal à BASE et HARD | Échec face à BASE |
| Parents dégradés au plus aussi nombreux qu'améliorés face à BASE | Échec : 48 > 43 |
| Non-infériorité logloss WDL, borne haute ≤ 0,002 | Échec |
| Brier SOFT ≤ Brier BASE + 0,002 | Réussite |

La production a effectué 4 675 recherches de référence et 17 de calibration,
soit 938 400 000 nœuds demandés, avec huit workers. La référence a pris
29,154 secondes ; le plafond calculé sur la calibration était de 99,836 secondes.
Le stage complet a pris 59,772 secondes, hors admission et publication externe.
Les instantanés de nœuds ne sont pas présentés comme une consommation finale exacte.

Aucun fit, recherche Jass, self-play, match de force, promotion ou bake.
`automatic_continuation=false`, `runtime_authorized=false`.
`CURRICULUM` reste champion. Aucun agrandissement, nouveau seed, réentraînement
ou Gate0 ne découle de ce résultat.

## Vérification de publication

Le résultat R2 `runs/cpx62-1884-l3-ed3-confirmation-production-v1/20260909T051901Z-0946f57d/`
a été relu après finalisation avec le vérificateur original : marqueur `_SUCCESS`,
manifeste externe, inventaire et sommes de contrôle. Toutes les sorties
enregistrées concordent avec le reçu, ainsi que code, spécification, profil et
environnement d'exécution. Les 25 régressions de production sont passées, sans
test ignoré.

Le [reçu de relecture](receipts/ed3-confirmation-1884-readback.json) conserve
les valeurs exactes et les identités authentifiées. Le recalcul à partir des
512 lignes par bras reproduit les deux contrastes, les IC95 et le contrôle
BASE/BASE. Les tables natives WDL publiées et les cibles Context30 aux indices
déjà scellés reproduisent exactement logloss, Brier et l'IC par ouvertures.
La relecture des sources et de la garde de 1883 confirme l'absence de
chevauchement parent/enfant, d'identités WDL et de groupes d'ouvertures entre
répétition et confirmation ; les empreintes de décision sont également absentes
de la garde WDL.

SHA256 de la synthèse scientifique publiée :
`d068fea4d548eb4cdbef5efb46b54985644c4aff370a612359b347290a4bb944`.
Cette vérification ne crée aucune nouvelle recherche ou cible. La revue
scientifique Sol confirme la correspondance entre les métriques, les portes
gelées et le verdict terminal.
