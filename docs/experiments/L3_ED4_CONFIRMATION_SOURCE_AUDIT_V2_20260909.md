# ED4-C0A — addendum prospectif de classification metadata V2

Date : 2026-09-09. Statut : **PRÉENREGISTREMENT PROSPECTIF, METADATA UNIQUEMENT**.

Ce document complète, sans réécrire, `L3_ED4_CONFIRMATION_SOURCE_AUDIT_V1_20260909.md` après les admissions descriptor-only 1891–1894. Aucun payload scientifique, score, cible, outcome, q-value, modèle, teacher, search, fit ou partie n'a été lu ou exécuté pour produire cet addendum. `alpha_1=0`; ED4, CURRICULUM et tous les gates scientifiques restent inchangés.

Le snapshot de producteurs reste exactement `jfrancoiscollin/jass-control@3ae5a3980ee60816ef078124deafa72b2e2f4662`, borné aux ordinals 1773..1888 plus les sources antérieures littéralement nommées par V1.

## 1. Erratum technique HomeScan

V1 nommait `artefacts/manifest.json` pour `home-1651-l3-scan-ceiling-selection-v1`. L'enveloppe authentifiée montre que le manifest résultat est le reçu top-level `manifest.json`, déjà lu par le transport metadata, tandis que les trois payloads structurels restent exactement :

```text
artefacts/parents.jnnw.gz
artefacts/children.jnnw.gz
artefacts/siblings.tsv
```

V2 remplace donc uniquement le descripteur inexistant `artefacts/manifest.json` par `manifest.json`. Cela n'ajoute ni position ni champ sémantique et ne modifie pas l'allowlist des payloads structurels.

## 2. Preuve de non-exécution 1820

Le status gelé
`status/cpx62-1820-l3-decision-math-b2-terminal-classified-failure-zero-placeholder-repair-v1.json`
au snapshot contrôle a exactement les identifiants de lancement suivants :

```text
attempt_id = null
code_sha   = null
started_at = null
state      = failed
phase      = launch
exit_code  = -1
```

Le job n'a donc jamais acquis d'attempt ni exécuté de code. Il est classé `non_position_producer` sur cette preuve de status authentifiée, jamais sur son nom.

## 3. Fermeture par SHA256 byte-identique

V1 autorise les SHA256 des inventaires authentifiés comme metadata. V2 fige la règle suivante avant toute lecture de payload : un producteur non littéral peut être classé `covered_by_authenticated_superset` **uniquement** si :

1. ses descripteurs capables de porter une identité de position sont déterminés par la règle fermée du §4 ;
2. chacun possède un SHA256 hexadécimal de 64 caractères dans l'inventaire authentifié ;
3. l'ensemble de ces SHA256 est un sous-ensemble de l'ensemble des SHA256 des `required_paths` présents d'**une seule** source `included_exact` V1 ;
4. aucune valeur du fichier n'est ouverte, parsée ou décodée pour établir cette relation.

Cette règle prouve seulement une couverture byte-identique par une source déjà exclue. Elle ne déduit aucune équivalence depuis un nom, une taille, un chemin ou une similarité sémantique. Si un seul descripteur de position porte un hash absent de la source exacte couvrante, le producteur reste `unknown`.

## 4. Règle fermée des descripteurs capables de porter une position

La classification metadata distingue les noms contenant accidentellement `root`, `parent` ou `sibling` des fichiers capables de porter des positions/identités. Sont candidats structurels :

```text
*.jnnw, *.jnnw.gz, *.jsm, *.jsm.gz, *.fen, *.fen.gz
*.tsv, *.tsv.gz, *.txt, *.txt.gz
    seulement si le basename contient parent|child|sibling|root|position|opening|identit|exclusion
*.jsonl, *.jsonl.gz
    seulement si le chemin contient dataset|position|.fen
```

Sont exclus de cette détection descriptor-only : objets/builds CMake, sources et docs (`*.o`, `*.o.d`, `*.cpp`, `*.hpp`, `*.cc`, `*.c`, `*.cmake`, `*.md`, `*.py`, `*.sh`, `*.log`, `*.err`) ainsi que les chemins sous `CMakeFiles`, `native-build`, `documentary-worktree/docs` ou `docs/archives`.

Cette règle ne déclare pas un contenu frais ou disjoint ; elle sert uniquement à ne pas confondre un artefact de build nommé `root/...` avec un payload de position. Tout fichier candidat non couvert par la fermeture SHA reste bloquant.

## 5. Verdict et frontière

Les quatre catégories V1 restent les seules catégories terminales :

```text
included_exact
covered_by_authenticated_superset
non_position_producer
structural_payload_unavailable
```

Un `unknown`, un payload structurel requis manquant ou une contradiction d'identité conserve `ED4_C0A_INVENTORY_ADMISSION_INSUFFICIENT_V1`. V2 ne transforme donc pas les 51 blockers observés par 1894 en succès par déclaration : il permet seulement de retirer ceux dont la non-exécution ou la couverture byte-identique est effectivement démontrée par les metadata gelées.

Même un inventaire descriptor `READY` n'est pas l'audit structurel complet C0A, ne lit aucune nouvelle position et n'autorise aucune confirmation ED4. Le full audit V1 ne peut commencer qu'après admission descriptor complète et répétée sous ce protocole V2.
