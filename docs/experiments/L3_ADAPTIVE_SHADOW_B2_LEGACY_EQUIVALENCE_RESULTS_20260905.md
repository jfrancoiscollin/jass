# L3 adaptive shadow — équivalence historique 1775

Date : 2026-09-05. Résultat technique historique, sans confirmation B2.

## Verdict et identité

```text
job       cpx62-1775-l3-decision-math-b2-legacy-equivalence-v1
attempt   20260905T031428Z-fd2f1280
code      fd2f1280804c27829fb6b946ae2fd52cdbe2937c
host      cpx62
started   2026-09-05T03:14:33Z
ended     2026-09-05T03:19:57Z
exit      0
verdict   B1_HISTORICAL_PROJECTION_EQUIVALENCE_COMPLETE
next      B2_COMPLETE_IMPLEMENTATION_AND_PREREGISTRATION_BEFORE_FRESH_DATA
```

L'implémentation provient de la [PR #781](https://github.com/jfrancoiscollin/jass/pull/781).
Le contrôle terminal est le commit `479f9ef4e553e600aa0592da6e76b3ef99b436c0`
de `jass-control`. Le préfixe authentifié est :

```text
r2:jass-data/runs/cpx62-1775-l3-decision-math-b2-legacy-equivalence-v1/20260905T031428Z-fd2f1280
```

## Résultat exhaustif

Les **8 000 parents et 74 449 lignes historiques** du teacher 1574 sont comparés.
Les décisions d'allocation et les résultats finaux B1 concordent chacun pour
**8 000 parents sur 8 000**. Le fichier de différences est vide. Les trois
ledgers publiés contiennent exactement les identifiants ordonnés `0..7999`.
Les quatre phases comportent 2 000 parents chacune ; STM0/STM1 vaut 3 970/4 030.

Le rapport B1 reproduit est identique octet par octet au rapport 1769 authentifié.
Il conserve 18 542 435 675 nœuds du full ladder, 10 789 907 706 nœuds simulés,
41,809652760194893 % d'économie et 96,425 % de choix de ligne identiques à q200.
La moyenne brute historique 95,749 mélange des encodages de score ; elle ne
devient pas une perte moyenne en centipions ordinaires ni une mesure de force.

La projection valide les coûts `nodes200k` de 74 449 lignes à l'entrée, puis
les sépare de l'objet remis à la policy. Les compteurs de lecture de valeurs
ou labels q200, de branches q200 et de lecture/branchement/agrégation précoce
des coûts q200 sont nuls dans chacun des 8 000 reçus. Après scellement, les
40 747 agrégations de coûts chargés et les lectures de référence/sélection q200
(74 402/40 747) sont explicitement distinctes. Le
[contrat de projection](L3_ADAPTIVE_SHADOW_B2_PROJECTION_V1_20260905.md) décrit
cette séparation et les empreintes de décision.

## Authentification des artefacts

L'audit terminal relit l'inventaire et les sommes de contrôle du résultat,
authentifie job/tentative/code/état, recalcule SHA256 et taille des sept fichiers
ci-dessous, rapproche le rapport intégré à la synthèse, puis contrôle
cardinalités, ordre des parents, compteurs et différence vide. Il ne relance
aucune recherche et n'exporte aucune ligne parent dans son reçu local.

Les chemins, sauf `scientific-summary.json`, sont sous
`artefacts/historical-equivalence/` ; la synthèse est sous `artefacts/`.

| Fichier | Octets | SHA256 |
|---|---:|---|
| scientific-summary.json | 6474 | `10d9ae121a7fae16988b85295ca1370f4057f650b9f84f73ec60218290f881a0` |
| legacy-equivalence-report.json | 2968 | `b6616b4a4d4a13f9e3f44eff1218c28c33b8ae20d02e593b23ed6dcd19944423` |
| legacy-report.json | 2562 | `f786210b41490feb32e582bd6075e38b765ef53d5330525b66792cf10e7dd9c0` |
| equivalence-diff.json | 106 | `0162f2b2878a1e82ba0cbd1862688e039af8a37cf9b7355fe4c46d00b820f9cc` |
| projection-receipts.jsonl | 8083811 | `80910ae44c34e6bf45e5d0ae1189e46914393716d00f6b89763f700bd38822d1` |
| postseal-q200-join.jsonl | 1705912 | `93e7c4a2ec726a605285da74554101a919a1654c0e69c68563fe686fe49aad2d` |
| legacy-decisions.tsv | 867068 | `7520d08d2952e96a7d5369caedff47168ffd13a96b7a2bdf4158f66f5a8cbdfd` |

Le teacher source est le gzip SHA
`bed80165f2e1249dbc8d0416237250a9ae0c62bcf0900816f60a8fc72c78ac76`,
tentative `20260826T185527Z-a6da4a0b` du job 1574. Le rapport B1 de référence
est celui de la tentative `20260904T221533Z-db6e6a5c` du job 1769.

## Coût et limites

La comparaison prend 3,122598262 s ; le travail complet du wrapper prend
6,489344976 s sous CPython 3.14.4, `/usr/bin/python3`, sur 16 CPU visibles.
Le temps entre début et fin du statut inclut le cycle de publication du runner
et ne mesure pas uniquement le calcul. Les bornes déclarées sont 90 s pour
la comparaison et 360 s pour le wrapper.

Cette preuve porte sur les ensembles d'allocation, choix, coûts et agrégats B1.
Elle ne compare ni le bitboard complet des cases capturées, ni l'identité
sémantique complète des coups, ni la provenance ou la famille des scores.
Ces limites historiques restent explicitement fausses dans le rapport.

Génération de parents, lecture de données fraîches, recherches, fits et parties :
**zéro**. Aucun seuil B2 n'est gelé, aucune confirmation B2 exécutée, aucun
enseignant adaptatif réel autorisé par ce résultat. Les outils de cohorte,
teacher, fusion et readout restent à compléter et valider avant le
préenregistrement final. `CURRICULUM` reste champion ; aucun bake ni promotion.

## Adaptateur teacher prospectif préparé après ce résultat

`jobs/tools/adaptive_sibling_b2_teacher_source.py` rend la source historique
épinglée en construisant un `Engine` neuf par sibling et par budget. Les trois
budgets, les 43 colonnes, les règles TB/terminales, book OFF et un thread restent
inchangés. Ses commandes `render`, `verify-selection` et `merge-reports`
produisent des reçus ; la fusion des rapports exige exactement 16 shards et
4 000 parents. Elle ne fusionne pas encore les fichiers enfants/TSV. L'outil
SHA `2c69e1c78c965f365a05809147fcc07e25895a32adff68197d72f8a7ee17e2c1`
rend la source SHA
`3f9a1e65a769db9478b0a376996670dd8b6662f34f1007ebfff5c1c38e42ffd3`,
23 035 octets. La revue indépendante ne laisse aucun P1/P2.

La suite teacher compte 20 tests : 19 réussis et un test de compilation ignoré
sous Windows. La compilation syntaxique avec GCC 13.3 sous WSL et
`JASS_EGDB=1` réussit. Le lien et le smoke avec le vrai CURRICULUM et une EGDB
authentifiée restent une précondition séparée, ainsi que la protection des
sorties directes du binaire et la vérification sémantique des payloads fusionnés.
Ce composant ne constitue pas le préenregistrement ni une exécution B2.
