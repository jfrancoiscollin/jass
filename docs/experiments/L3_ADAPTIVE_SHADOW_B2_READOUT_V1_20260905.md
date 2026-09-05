# PR #771 — préparation de l'allocation et du readout B2

Date : 2026-09-05, Europe/Paris.

Statut : préparation technique prospective. Ce document n'est pas le
préenregistrement confirmatoire et n'autorise aucune génération fraîche.

Le [plan de la PR #771](L3_DECISION_INFORMATION_IMPLEMENTATION_PLAN_V1_20260903.md)
demande une confirmation B2 séparée après le shadow historique B1. L'équivalence
B1 de la projection a été [authentifiée sur 8 000 parents et 74 449 lignes](L3_ADAPTIVE_SHADOW_B2_LEGACY_EQUIVALENCE_RESULTS_20260905.md).
Le [smoke 1776](L3_ADAPTIVE_SHADOW_B2_TEACHER_NATIVE_SMOKE_RESULTS_20260905.md)
valide le teacher natif sur un seul parent historique. Ces résultats ne sont
pas des observations de confirmation B2.

## 1. Chaîne et séparation des lectures

La préparation ajoute deux outils à la
[fusion teacher et sa vérification native](L3_ADAPTIVE_SHADOW_B2_TEACHER_MERGE_V1_20260905.md) :

- `jobs/tools/adaptive_sibling_b2_allocation_input.py` authentifie les parents,
  le teacher, les actions sémantiques et les reçus, puis publie les seules
  colonnes acceptées par la projection sans q200 ;
- `jobs/tools/adaptive_sibling_b2_readout.py` joint les observations après
  scellement de la projection, produit les lignes riches et suffisantes, puis
  délègue l'analyse au module statistique publié.

L'ordre est obligatoire : allocation input → processus projection distinct →
reçus de décisions scellés → readout riche → statistiques. Le readout ne
réexécute jamais la policy d'allocation et ne lance aucune recherche.

L'allocation peut authentifier les octets du TSV complet. Les tokens q200 de
score, profondeur, arrêt, temps et PV restent opaques. Seul `nodes200k` est
validé comme coût ; ce coût n'appartient pas au type reçu par la policy.
Il est agrégé uniquement pour les lignes déjà chargées après scellement.

## 2. Identités et formats

Les outils exigent 4 000 parents ordonnés, 500 dans chacune des huit cellules,
et 2 à 16 actions légales par parent. Les fichiers, outils réellement importés
et reçus sont liés par SHA256 et taille. Une copie aux mêmes octets est admise ;
deux entrées ne peuvent pas être des alias d'un même fichier.

Le shard de génération conservé dans la sélection est une provenance. Le shard
teacher vaut `parent_id % 16` après sélection et tri ; ces deux valeurs ne sont
pas supposées égales.

En amont, le sélecteur distingue désormais un pool valide qui n'atteint pas le
quota d'une erreur technique. Seule `InsufficientSupportError` produit le code
retour 4 et un JSON canonique `jass.adaptive_sibling_b2_target_blind_support.v1`,
avec les huit comptes avant tirage, les cellules insuffisantes et les
compteurs d'exclusion/déduplication. Les 53 entrées sont réauthentifiées avant
ce retour ; aucune sortie parent n'est créée, aucun complément ni nouveau
tirage n'est permis. Les autres erreurs restent techniques.

Chaque parent riche possède une projection unique vers le type public
`ParentStatsSufficientV1`, à treize clés. Le rapport conserve les hashes de
chaque paire de lignes, l'ordre des parents, les comptes par cellule, les
coûts et le ledger exhaustif. Une valeur numérique inéligible reste `null`
dans la ligne riche ; sa contribution nulle au numérateur statistique ne la
transforme pas en observation numérique.

## 3. Observations et catégories

Le readout contrôle le transport aux trois horizons : domaines des scores et
des nœuds, profondeurs, arrêt et interruption, temps et indicateur PV. Pour
chaque ligne non exacte, il contrôle aussi le support des bandes de score.
Les observations immédiatement exactes sont contrôlées sans utiliser leur
score dans les familles ou endpoints.

L'action contient l'origine, la destination, le nombre de prises, la promotion
et le bitboard complet des cases capturées. La preuve de légalité et de
transition appartient au vérificateur natif ; le readout authentifie cette
preuve et ses jointures.

Le ledger distingue même ligne, autre ligne de même valeur, puis les
inéquivalences : exact/mixte, transitions de famille, différences numériques
finies, ordre encodé TB/mate et autres mécanismes. Une bande TB ou mate décrit
un score de recherche et ne constitue pas une preuve de l'issue d'une partie.

## 4. Échec de build authentifié

Un build valide publie exactement :

```text
parent-stats-rich-v1.jsonl
parent-stats-sufficient-v1.jsonl
rich-to-sufficient-report-v1.json
```

Une validation classée invalide peut publier un reçu séparé
`jass.adaptive_sibling_b2_readout_build_failure.v1`, avec code retour 4,
sans répertoire de succès ni payload riche ou suffisant. Le reçu donne une
classe et une étape fermées, uniquement un contexte authentifié, et des
compteurs nuls de statistiques, recherches, fits, parties et promotions.

Si l'authentification commune initiale échoue, code, parent, ligne et horizon
sont tous `null`. Les erreurs techniques `ReadoutError` et `OSError`, dont
les erreurs de lecture, de permission, de chemin et les alias, rendent le
code retour 2 sans reçu scientifique d'échec. Les timeouts, signaux et autres
erreurs internes restent techniques ; leur retour externe n'est pas
nécessairement 2 et ne doit jamais être converti en résultat scientifique.

Le wrapper doit authentifier les octets du reçu, le code retour, le module
exécuté et l'absence de sorties normales avant de rendre
`B2_ADAPTIVE_SHADOW_SUPPORT_NOT_ESTABLISHED_V1`. Il n'appelle alors ni
`finalize` ni les statistiques. Aucun fichier vide ou fabriqué ne remplace
un payload manquant.

## 5. Analyse et terminal

Le terminal authentifie les entrées et leur provenance, recharge le fichier
suffisant par `load_parent_stats_sufficient_jsonl`, puis appelle une seule
fois `analyze_parent_stats` lorsque le support est valide. La CLI ne permet
de changer ni les 200 000 réplications, ni la seed, ni les méthodes ou gates.
Le runtime réel doit correspondre au
[preflight 1774](L3_ADAPTIVE_SHADOW_B2_STATISTICAL_PREFLIGHT_V1_20260905.md),
notamment CPython 3.14.4.

Le mapping est fermé :

| État | Verdict |
| --- | --- |
| Support ou analyse invalide | `B2_ADAPTIVE_SHADOW_SUPPORT_NOT_ESTABLISHED_V1` |
| Support valide, au moins une gate fausse | `B2_ADAPTIVE_SHADOW_POLICY_NOT_CONFIRMED_V1` |
| Support valide, toutes les gates vraies | `B2_ADAPTIVE_SHADOW_POLICY_CONFIRMED_V1` |

Ces routes ne jouent aucune partie, ne modifient aucun modèle et n'enchaînent
aucun job elles-mêmes. `CURRICULUM` reste champion. Une éventuelle confirmation
permet seulement la préparation distincte de B3 selon le plan ; elle ne vaut
ni promotion ni bake.

## 6. Conditions restantes

La validation finale des implémentations et des publishers, leurs pins réels,
les enveloppes de runtime et le préenregistrement normatif restent nécessaires
avant toute génération B2. Le document normatif doit être publié et authentifié
avant la sélection ; la sélection doit ensuite être vérifiée et committée
avant toute première lecture teacher.

## 7. Validation technique

La reproduction sous WSL Ubuntu 24.04, avec les `ResourceWarning` traités en
erreurs, passe les **75 tests** allocation, readout, pipeline et sélecteur en
**52,673 s**.
La chaîne synthétique utilise le vrai helper natif sur 4 000 parents, huit
cellules de 500 et seize shards, puis le vrai merger/vérificateur, l'allocation,
la projection et le build riche. La fixture terminale contient 15 937
observations et passe par les vrais manifests, le loader suffisant public et
`finalize_command`. Seuls l'analyseur statistique et le runtime observé sont
remplacés dans ce test borné. Les observations teacher sont fabriquées :
aucune recherche n'est lancée. La projection est appelée dans le processus
du test ; la séparation des processus de production reste à valider dans
le publisher.

Les tests ciblés couvrent les tokens q200 opaques avant scellement, les
jointures et coûts, les catégories exactes/numériques, les trois routes
terminales, les échecs typés et la préservation des fichiers préexistants.
Ils ne réexécutent pas les 800 millions de tirages du preflight 1774. La preuve
de durée statistique reste celle de ce preflight ; l'exécution confirmatoire
complète attend le préenregistrement et les publishers.

Les 23 tests du sélecteur inclus dans cette reproduction couvrent notamment
la cellule insuffisante, la mutation d'une entrée avant retour, les alias et
la préservation des sorties préexistantes.
