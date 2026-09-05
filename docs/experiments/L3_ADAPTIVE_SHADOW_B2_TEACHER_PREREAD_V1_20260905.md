# B2 — barrière teacher pre-read X/Y/S/F

Date : 5 septembre 2026, Europe/Paris.

Statut : **contrat technique prospectif**. Aucun teacher B2 frais n'est exécuté
par ce document ou par l'outil décrit ici.

## Objet

La publication source B2 distingue :

```text
X  commit exact d'implémentation exécuté
Y  descendant de X qui ajoute uniquement le prereg Markdown
F  reçu final source/sélection après replay et nettoyage
S  descendant documentaire de Y qui ajoute uniquement les bytes audités de F
```

La première lecture teacher ne peut commencer qu'après authentification de ces
quatre identités et des fichiers de sélection réellement fetchés.

`jobs/tools/adaptive_sibling_b2_teacher_preread.py` matérialise cette barrière.

## Invariants Git

Le processus teacher reste checkouté exactement sur X.

Avant toute lecture teacher il exige :

```text
HEAD == X
X ancestor-of Y
Y ancestor-of S
git diff --name-only X Y == [preregistration_path]
git diff --name-only Y S == [source_publication_path]
```

Il lit ensuite les bytes du prereg via `git show Y:path` et ceux de F via
`git show S:path`, et compare leurs SHA-256 aux valeurs externes déjà auditées.

Ainsi S ne peut pas introduire silencieusement une modification de code ou de
science entre la génération target-blind et le teacher.

## Invariants F

F doit être :

```text
schema  jass.adaptive_sibling_b2_source_selection_publication.v1
status  VALID
verdict B2_SOURCE_SELECTION_LOCAL_SEAL_COMPLETE
```

Il doit lier :

- `implementation.commit == X` ;
- `preregistration.commit == Y` et les bytes du prereg ;
- `top_up=false`, `regeneration=false`, `new_seed=false` ;
- zéro teacher row/search, fit, partie de force, promotion et bake ;
- 4 000 parents target-blind ;
- huit cellules de 500 ;
- aucun overlap historique.

## Invariants de sélection locale

Les quatre payloads fetchés depuis le résultat source sont re-hashés contre F :

```text
parents.jnnw
parents.tsv
selection-report.json
ordered-identities.txt
```

L'outil réutilise ensuite `adaptive_sibling_b2_teacher_source.verify_selection_input`
sur `parents.jnnw` et le rapport scellé. Cette vérification impose notamment :

```text
records = 4000
record_size = 38
target bytes checked = 5 * 4000
target bytes nonzero = 0
teacher scores read = 0
authenticated_before_teacher = true
```

Le reçu final de barrière est :

```text
schema  jass.adaptive_sibling_b2_teacher_preread_auth.v1
status  VALID
verdict B2_TEACHER_PREREAD_AUTH_COMPLETE
teacher_searches = 0
teacher_scores_read = 0
```

Le wrapper de production doit obtenir ce reçu avant de lancer le premier shard
teacher. Une authentification postérieure ne peut pas réparer une lecture teacher
prématurée.

## Portée

Cette barrière ne choisit aucune position, ne calcule aucun score teacher, ne
modifie aucune policy et n'évalue aucune gate scientifique. Elle ne fait que
rendre vérifiable la séparation temporelle requise par #787.
