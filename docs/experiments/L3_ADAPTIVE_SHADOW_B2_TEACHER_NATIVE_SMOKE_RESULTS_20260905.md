# B2 — smoke natif historique du teacher, 1776

Date : 5 septembre 2026. Préparation technique du
[programme decision-information de la PR 771](L3_DECISION_INFORMATION_IMPLEMENTATION_PLAN_V1_20260903.md).

## État et identité

Le job `cpx62-1776-l3-decision-math-b2-teacher-native-smoke-v1`, tentative
`20260905T073548Z-c93717f4`, est terminé et authentifié dans R2 avec exit `0`
et `B2_TEACHER_NATIVE_SMOKE_COMPLETE`. Le runner le prend en charge le
5 septembre à 07:35:52 UTC et publie son terminal à 07:41:00 UTC.

Code : `c93717f4cbc7017233e850e3ccf0684d78680859`, intégré par la
[PR 783](https://github.com/jfrancoiscollin/jass/pull/783).
La suite déclarée reste
`B2_COMPLETE_IMPLEMENTATION_AND_PREREGISTRATION_BEFORE_FRESH_DATA`.

Les neuf artefacts JSON sont relus depuis
`r2:jass-data/runs/cpx62-1776-l3-decision-math-b2-teacher-native-smoke-v1/20260905T073548Z-c93717f4`
et vérifiés contre l'inventaire terminal authentifié : identité du job,
tentative, code, host, état, exit, SHA256 et tailles. Le reçu de smoke et
`scientific-summary.json` sont identiques, SHA256
`2fa26aa70f6c5c70115d2c114fc95ceb18364a6646ca826912d169e0276ad190`,
37 296 octets. Le reçu de build possède le SHA256
`94395320d08762505955881177e2f08271121c4f39c1b448fa37889f922a5dcb`.
Les bindings du rendu, du modèle, des bases, des objets de lien et du
processus sont recoupés ; aucune ligne teacher n'est exportée par cet audit.

## Périmètre exécuté

Le smoke reprend uniquement le premier parent de la sélection historique
1570, tentative `20260826T104456Z-1493d426`. Le JNNW historique authentifié
contient 8 000 parents ; le fichier de travail d'un parent possède le SHA256
`38bc7a10bc18fcbedb236303f11d833fca8555a38515752fdba3acf79e7edf94`.
Il n'y a aucune génération ni sélection de parents B2 frais.

Le teacher rendu possède le SHA256
`3f9a1e65a769db9478b0a376996670dd8b6662f34f1007ebfff5c1c38e42ffd3`.
Il charge `CURRICULUM`, SHA256
`319d174f4b548b1655aad4bb30d4c6dc86c08dd715c9c23f8b19ba1937dc0be1`.
Chaque recherche crée son propre moteur, avec un thread, book OFF, TT 16 MB,
limites exactes de 5 000, 50 000 et 200 000 nœuds, et environnement vide.
Le PID, groupe de processus, argv, environnement et SHA de l'exécutable sont
contrôlés après `exec`.

Le build Release utilise EGDB, les mêmes options de features que la recette
historique, les objets runtime de l'exécutable de production et les archives
Jass/EGDB. L'environnement vide laisse l'arm F6 désactivé. L'exécutable
authentifié possède le SHA256
`f4a6a3133194dcb3da017f4f18950407a05054b8e39f680c51611d44a11f56e2`.

L'identité EGDB porte sur les bytes installés : 158 fichiers de données,
5 051 377 274 octets, manifeste SHA256
`1f494fd242282ee01043e77cfee18608650d867594ea40db274072444ba2992e` ;
50 fichiers source suivis au commit
`eacf10797e8f6c81d618caa7af1eba05df139ac7`, manifeste SHA256
`82dcf4d96e99c75c4224b7d5bea1f6073b4f24949c7fc4b7cd1dfe4ecfca9d4e`.
Le scope reste `EXACT_INSTALLED_BYTES_NOT_UPSTREAM_RELEASE_AUTHENTICATION`.
Le cache est de 256 MB et les bases déclarées disponibles vont jusqu'à sept
pièces. Aucun des douze enfants n'est exact TB ou terminal par règle : ce
smoke ne prouve donc pas un hit TB positif sur un enfant.

## Résultat technique

Les douze siblings produisent **36 moteurs et 36 recherches**, réparties en
douze recherches par budget. Les compteurs totalisent 60 000, 600 000 et
2 400 000 nœuds. Aucun doublon de coup n'est déclaré.

Le JNNW enfant contient douze records avec targets nuls ; le TSV contient
douze lignes et les 43 colonnes attendues. Le publisher contrôle ces formes
et les compteurs sans décoder les champs de score. Les payloads parent,
modèle et teacher de travail sont retirés après le smoke ; les métadonnées,
empreintes, journaux de build et reçus sont publiés.

Temps mesurés sur CPX62 : **23,081 s** pour la chaîne du publisher, dont
11,916 s de build/lien, 5,718 s d'authentification EGDB, 4,289 s de
récupération/validation historique et **1,068 s de teacher**. Ces durées
excluent l'attente de prise en charge et de publication du runner. Un parent
historique ne suffit pas à garantir le temps de toute la future cohorte.

## Tentatives techniques conservées

- `20260905T071004Z-c93717f4` : exit `1` avant récupération, build ou
  recherche. La garde de répertoire vide rencontrait le marqueur
  `runner-launch.json` créé par le runner. La correction préserve ce seul
  fichier normal sans lire ses bytes transitoires de démarrage.
- `20260905T072528Z-c93717f4` : exit `1` au lien C++, avant recherche.
  La recette manuelle omettait les deux objets `jass_t3_f6_runtime` conservés
  hors de `jass_lib` par CMake. La correction lie les objets de production
  et enregistre leurs empreintes. Un build/lien séparé sur CPX62 réussit en
  11,799 s avant relance, sans invoquer le teacher.

Les deux échecs sont authentifiés dans R2. Les correctifs conservent le même
code, parent historique, modèle, bases, budgets et environnement. La version
relancée passe quinze tests Linux et une revue indépendante sans P1/P2.

## Portée et suite

Ce résultat établit l'exécution technique du nouveau teacher sur ce parent.
Il ne confirme ni l'économie B2, ni ses portes statistiques, ni une mesure
de force, et ne complète pas les identités historiques B1. La
[fusion native des actions](L3_ADAPTIVE_SHADOW_B2_TEACHER_MERGE_V1_20260905.md)
possède ses propres contrôles.

L'allocation sans q200, son scellement, le readout riche et leur intégration
restent à valider. Le préenregistrement B2 doit être publié avant toute
nouvelle donnée de confirmation. `CURRICULUM` reste champion ; aucun bake ou
promotion automatique n'est autorisé par ce reçu.
