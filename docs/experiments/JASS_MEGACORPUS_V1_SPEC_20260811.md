# Jass MegaCorpus v1 — provenance, mémoire historique et curriculum

> **Statut :** protocole préenregistré avant census R2 et avant tout résultat de
> force MegaCorpus. Le census ne télécharge aucun corpus, modèle ou frozen set.

## 1. Question

Peut-on transformer le calcul de self-play historique du projet en actif
d'entraînement sans réintroduire les corruptions, les doublons, les corpus
dérivés ni les distributions expérimentales qui ont déjà produit de fausses
améliorations de loss ?

L'expérience conserve exactement l'architecture PatternEval L2LOW à 120 extras,
la recette de fit, le parent, le budget d'optimisation, les pools d'évaluation et
la cible `context30`. La provenance n'est jamais une feature d'inférence : elle
sert uniquement à sélectionner, pondérer, auditer et reproduire les données.

## 2. Pipeline irréversible par étapes

### P0 — census R2, sans payload

Le job `jass-megacorpus-r2-census-v1.sh` liste tous les objets de
`r2:jass-data`, puis ne copie localement que les manifests, inventaires,
checksums et marqueurs runner. Il publie :

- `r2-objects.jsonl.gz` : inventaire exhaustif chemin/taille/date R2 ;
- `runner-attempts.jsonl.gz` : identité, état terminal et intégrité des runs ;
- `corpus-candidates.jsonl.gz` : chaque objet JNNW, son sidecar possible, son
  origine observée, les faits manquants et un statut `review`, `quarantine` ou
  `reject` ;
- `catalog-summary.json` : compteurs et SHA des catalogues.

`review` ne signifie pas « accepté ». Aucune donnée n'entre automatiquement
dans MegaCorpus. Les `paths.jsonl.gz` des snapshots Git historiques sont eux
aussi développés en entrées candidates sans restaurer leurs blobs ; ces entrées
restent en quarantaine jusqu'à restauration et vérification du Git blob OID.

### P1 — enrichissement et graphe de lignage

Pour les seuls candidats revus, récupérer les petits manifests scientifiques,
scripts/configurations et certificats qui permettent de renseigner, sans
inférence silencieuse : génération, modèle générateur, date, code SHA, recherche,
exploration, ply-cap, adjudication, tablebase, seeds, source parent, split,
filtrage et mélange.

Chaque exemple reçoit deux tableaux NumPy strictement alignés :
`origin_source_id.npy` (`uint32`) et `origin_record_index.npy` (`uint64`). Le
premier référence une table de sources immuable ; le second désigne la ligne
dans le corpus source authentifié. Les champs communs ne sont donc pas répétés
sur des millions de lignes, mais chaque exemple reste retraçable sans dépendre
de l'ordre d'un merge. Le JSM1/JSM2 d'origine est conservé séparément et n'est
jamais promu artificiellement vers JSM2. Un champ historiquement absent vaut
explicitement `null` avec une raison.

### P2 — matérialisation authentifiée et déduplication

Télécharger seulement les sources acceptées, vérifier taille et SHA contre
`inventory.json`/`checksums.sha256`, décompresser en streaming, puis publier les
SHA bruts JNNW/JSM.

La déduplication v1 retire :

1. les copies exactes d'un même blob brut ;
2. les descendants `merge/split/mix/filter` lorsqu'un parent déjà sélectionné
   couvre les mêmes exemples ;
3. les inclusions prouvées par manifests et SHA.

Des parties identiques issues de générations indépendantes ne sont pas retirées
automatiquement : leur fréquence peut appartenir à la distribution réelle. Un
audit de fingerprints par partie mesure cette redondance avant toute règle
supplémentaire.

### P3 — reconstruction `context30`

Pour chaque corpus accepté, reconstruire les FEAT avec le binaire et
l'architecture épinglés, puis générer les cibles avec le mapper conditionnel
groupé par partie. Les folds sont disjoints par partie et le holdout n'entraîne
jamais le mapper. Date, modèle, job et paramètres de self-play ne sont pas des
entrées du mapper.

Un seul sidecar Mega `context30` est construit avant les bras B et C : ces deux
bras diffèrent donc uniquement par les poids d'échantillons. Le corpus Current
possède son sidecar Current construit par le même code et les mêmes hyperparamètres.

## 3. Politique qualité pré-force

### Rejet dur

- run failed, état/marker contradictoire, `n=0`, payload vide ou checksum faux ;
- JNNW/JSM désalignés, WDL/STM/bitboards invalides ou POV incohérent ;
- contamination d'un pool d'évaluation/frozen, teacher externe, Scan, PDN,
  oracle ou EGDB hors contrat autonome ;
- copie exacte ou descendant dérivé déjà représenté ;
- défaut de moteur/label connu et non réparable.

### Quarantaine réversible

- provenance modèle/recherche inconnue ;
- ancien JSM1 : admissible après audit, mais les champs JSM2 absents restent
  inconnus ;
- exploration, profondeur, adjudication ou calibration expérimentales ;
- corpus spécialiste, hard replay, relabel, mix ou filtre dont le parent n'est
  pas encore attribué.

La décision est prise avant les résultats de force MegaCorpus. La loss ou l'Elo
d'un descendant ne servent jamais à décider s'il entre dans le catalogue.

## 4. Expérience causale

Les bras principaux sont :

| bras | données | poids | initialisation / prior |
|---|---|---|---|
| A `CURRENT_C30` | corpus Current haute qualité | uniforme | parent commun |
| B `MEGA_UNIFORM_C30` | mêmes lignes Mega que C | uniforme | parent commun |
| C `MEGA_WEIGHTED_C30` | mêmes lignes Mega que B | récence × qualité | parent commun |
| D `MEGA_PRETRAIN_THEN_CURRENT_C30` | Mega puis Current | uniforme à chaque étape | sortie Mega comme prior du fine-tune Current |

B contre C isole la pondération. A contre B mesure la recette Mega complète,
pas le seul volume. D teste le curriculum proposé sans le confondre avec C.
Un diagnostic `MEGA_UNIFORM_EQUAL_N` sous-échantillonne Mega au nombre de lignes
de Current, avant toute lecture de force : il sépare composition/diversité et
volume, mais ne participe pas à la décision primaire à quatre bras.

Les poids C sont strictement positifs, bornés, enregistrés source par source,
puis normalisés à moyenne 1 sur le train. La formule primaire sera figée après
lecture du census des dates — autorisée — mais avant tout fit/strength Mega :

```text
raw_weight(source) = quality_multiplier
                   × (recency_floor + (1-recency_floor) × 2^(-age/half_life))
```

Le rapport publie min/max/quantiles, masse par source et effective sample size.
Le plan primaire utilise une seule demi-vie ; aucune recherche post-hoc sur le
gate de force n'est permise.

D est un fit séquentiel, pas un changement d'architecture. PatternEval étant un
modèle linéaire optimisé jusqu'à convergence, un simple warm-start serait
normalement effacé par le fit Current. Le modèle préentraîné devient donc le
prior explicite du fit Current ; la force du rappel au prior et le budget du
fine-tune sont préenregistrés. Une
amélioration de log-loss seule n'autorise rien, les fine-tunes WDL historiques
ayant déjà amélioré la loss tout en perdant de la force.

## 5. Contrôles et décision

- mêmes architecture, cible, parent initial, L2, tolérance et convergence ;
- même holdout Current non pondéré, jamais utilisé pour choisir les poids ;
- budget de lignes et budget d'optimisation publiés ; B/C ont exactement les
  mêmes lignes et seul le vecteur de poids change ;
- couverture 8cf, `ge_10`, `ge_100`, Gini, diversité parties/ouvertures,
  redondance et ESS ;
- gate indépendant contre le champion courant et garde Gen2, conversion P3/P4,
  Q00/native et débit identique ;
- aucune promotion automatique.

Lecture primaire : C gagne si sa force appariée dépasse B sans régression
établie sur les gardes. D répond séparément à la question « prétrain puis
recentre » et peut être retenu même si le fit uniforme B échoue. Tout point
estimate positif est conservé comme information ; « promotion » exige en plus
la puissance et les gardes préenregistrées.

## 6. Ordre rationnel d'exécution

1. census P0 sur CPX, en parallèle des expériences Mini-Jass sur HOME ;
2. revue humaine du catalogue et publication de la politique d'inclusion ;
3. matérialisation d'un échantillon par strate, validation des formats et mesure
   du débit de reconstruction FEAT/context30 ;
4. matérialisation complète et gel de MegaCorpus v1 ;
5. smoke A/B/C/D à volume réduit ;
6. fits complets puis gate indépendant.

Le probe full-Jass `context30` à 2 M reste une précondition de sûreté avant de
payer la reconstruction massive, mais il ne bloque pas le census métadonnées.

## 7. Correction opérationnelle P0 — census v4

Le job `cpx62-1255-jass-megacorpus-r2-census-v3` a expiré après deux heures
pendant l'unique `rclone lsjson --recursive`. Il n'a téléchargé aucun payload,
n'a lu aucun frozen set et n'a produit aucun résultat scientifique. Cet échec
invalide la forme monolithique du census, pas l'hypothèse MegaCorpus.

La v4 remplace cette opération par un index adaptativement shardé :

- séparation initiale à profondeur 2, puis lecture récursive indépendante de
  chaque préfixe ;
- subdivision d'un préfixe qui dépasse son timeout, jusqu'à profondeur 6 ;
- checkpoint atomique après chaque shard, avec contenu compressé et SHA-256 ;
- reprise possible depuis un précédent checkpoint de métadonnées uniquement ;
- fusion exhaustive, triée et sans doublon avant construction du catalogue ;
- téléchargement exact, par listes de 500 chemins et `--no-traverse`, des
  seuls manifests, inventaires, checksums et marqueurs autorisés.

Les checkpoints sont des artefacts du runner même si la tentative s'interrompt.
Une relance reprend les préfixes terminés au lieu de relire tout R2. La v4 garde
les mêmes barrières P0 : aucun corpus/modèle, aucune lecture frozen, aucun fit,
aucune promotion et aucune continuation automatique.
