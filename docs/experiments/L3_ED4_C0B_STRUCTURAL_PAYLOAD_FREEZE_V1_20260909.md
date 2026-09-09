# ED4-C0B — gel conservateur des payloads structurels visibles V1

Date : 2026-09-09. Statut : **PRÉENREGISTREMENT PROSPECTIF, METADATA UNIQUEMENT**.

## Objet

C0A-v1 a rendu `INSUFFICIENT` avec 51 producteurs encore `unknown` et un
payload HomeScan classé `structural_payload_unavailable`. C0B ne cherche pas à
reclasser ces producteurs par leur nom et ne tente pas de prouver des relations
de sous-ensemble a posteriori. Il gèle au contraire, de façon volontairement
sur-inclusive, tous les chemins de payloads de positions dont le format est
identifiable à partir des inventaires déjà authentifiés.

Le but est de préparer une version ultérieure de l'audit qui pourra **ajouter**
ces payloads à l'univers d'exclusion. Une sur-exclusion est acceptable : elle
peut seulement retirer des positions du futur test frais. C0B ne peut jamais
faire considérer comme fraîche une position déjà vue.

## Source immuable

C0B utilise exactement le même snapshot contrôle que C0A-v1 :

```text
jfrancoiscollin/jass-control
3ae5a3980ee60816ef078124deafa72b2e2f4662
```

Il réutilise les enveloppes déjà authentifiées par le chemin C0A : `_SUCCESS` ou
`_FAILED`, `manifest.json`, `inventory.json`, `checksums.sha256`. Aucun payload
scientifique n'est téléchargé ni ouvert.

## Sélection purement nominale des candidats

Pour chaque ligne encore `unknown` ou `structural_payload_unavailable`, un
chemin est retenu uniquement si son nom correspond à un parser structurel
préenregistré :

```text
*.jnnw, *.jnnw.gz
*.fen,  *.fen.gz
*.jsm,  *.jsm.gz
parents.tsv, children.tsv, siblings.tsv, groups.tsv
*roots.tsv, *root-pool.tsv
ordered-identities.txt, *-ordered-identities.txt
*exclusion-union.txt, *canonical-union.txt
```

Le filtre ne regarde ni contenu, score, label, WDL, target, métrique, résultat
de partie, modèle ou nom sémantique du job. Les chemins provenant d'un worktree,
d'un ancien corpus ou d'une fixture restent donc candidats s'ils correspondent
au format. Cette sur-inclusion est intentionnelle.

Pour chaque candidat, le manifest publie seulement : job, tentative,
classification C0A au moment du gel, chemin exact, classe de parser, taille et
SHA256 provenant de l'inventaire authentifié.

## Sortie

```text
ed4-c0b-structural-candidate-manifest.json
schema = jass.ed4.c0b_structural_candidate_manifest.v1
classification = METADATA_ONLY_OVERINCLUSIVE_FREEZE
```

Le manifest publie également les comptes par format, le volume déclaré total et
la liste des producteurs qui n'ont aucun candidat de format parseable.

## Barrière scientifique

C0B doit terminer avec :

```text
payload_downloads=0
payload_bytes_read=0
model_reads=0
target_reads=0
outcome_reads=0
qvalue_reads=0
scientific_verdict=null
confirmation_authorized=false
automatic_continuation=false
```

Il ne dépense aucun alpha, ne sélectionne aucune position fraîche, n'exécute
aucun teacher/search/fit/partie et ne modifie ni ED4, ni BASE/HARD/SOFT, ni les
seuils de confirmation.

Le manifest C0B **n'est pas** une admission C0A positive. La suite scientifique
doit être préenregistrée séparément avant toute lecture de ces payloads : parsers
à champs structurels seulement, exclusion par union canonique, et fail-closed
pour tout format non authentifiable ou tout producteur pertinent encore sans
couverture.
