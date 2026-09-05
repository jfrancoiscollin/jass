# Projection d'allocation adaptive-shadow B2 — contrat technique v1

Date : 2026-09-05

Statut : contrat d'implémentation historique et synthétique. Ce document décrit
le projecteur déjà implémenté et revu. Il ne constitue pas la preregistration
confirmatoire B2, ne gèle aucun seuil scientifique et n'autorise aucune lecture
de cohorte fraîche.

Implémentation :
`jobs/tools/adaptive_sibling_b2_projection.py`.

Tests :
`jobs/tests/test_adaptive_sibling_b2_projection.py`.

Empreintes du snapshot revu :

```text
projection.py  CBCB7C6F4D1A497E4A66A0615E158744F43DBC7C0B1B116C7F30599C86B6176F
tests          744E3F0719874FA6AAAE29D7488572A5D0CBA87E36D62E810581759E13C8E5B0
clarification  C9C66E7CD93398E0DBD77A54448412C976F31CDC71C47204F0A969FA53579A0A
```

La troisième empreinte désigne
`.codex-tmp/pr771-b2-projection-hash-clarification.md`. Les règles de deux vues,
de scellement, de perturbation et de validation précoce de `nodes200k` de ce
mémo sont intégrées ci-dessous afin que le contrat ne dépende pas durablement
d'un fichier temporaire.

## 1. Périmètre

Le projecteur porte la policy d'allocation B1 dans une interface où les valeurs,
familles et labels q200 sont absents. Il reçoit les exactitudes immédiates, les
utilities exactes, les scores q5k/q50 et trois composantes de coût. Il fixe les
survivants et le choix pré-q200, scelle cette décision, puis somme le coût
`nodes200k` uniquement sur l'ensemble déjà scellé.

Ce module ne lance aucune recherche, ne joint aucun score q200, ne calcule aucun
endpoint confirmatoire et ne produit aucun verdict scientifique. Le manifest
atteste `searches=0`, `fits=0` et `strength_games=0`.

## 2. CLI et artefacts

Le CLI est exactement :

```text
python jobs/tools/adaptive_sibling_b2_projection.py \
  --input <allocation-parents.jsonl> \
  --out-receipts <allocation-receipts.jsonl> \
  --out-manifest <projection-manifest.json>
```

Il n'expose aucune marge, aucun minimum de survivants, aucun budget et aucune
option de policy. Les trois chemins sont obligatoires. Le programme retourne 0
après succès et 2 après toute erreur de contrat.

Les chemins d'entrée, des deux sorties et des deux temporaires `*.tmp` doivent
être distincts après résolution. Une sortie ou un temporaire préexistant est
refusé avant écriture. Les sorties sont construites par temporaires puis
renommées ; une erreur supprime les sorties partielles.

Les reçus sont ordonnés par `parent_id` croissant et écrits en JSONL canonique :
UTF-8, ASCII échappé, clés triées, séparateurs compacts, un LF final par ligne,
aucun NaN ou Infinity. Le manifest est un objet JSON soumis à la même
sérialisation canonique.

## 3. Schémas fermés et types

Les identifiants de schéma sont :

```text
entrée parent  jass.adaptive_sibling_b2_projection_input_parent.v1
reçu parent    jass.adaptive_sibling_b2_allocation_receipt_parent.v1
manifest       jass.adaptive_sibling_b2_projection_manifest.v1
```

Chaque parent d'entrée possède exactement :

```text
schema:string, parent_id:int64, phase:{P0,P1,P2,P3}, stm:{0,1}, rows:list
```

Il contient au moins deux siblings. Chaque ligne possède exactement :

```text
row_index:int64
child_rule_terminal:bool
child_tb_exact:bool
exact_parent_utility:int8
q5k_parent:int32
q50_parent:int32
nodes5k:uint64
nodes50k:uint64
nodes200k:uint64
```

Les booléens ne sont jamais acceptés comme entiers. Les `row_index` sont uniques
dans un parent et les `parent_id` sont uniques dans le fichier. Le parseur trie
les lignes par `row_index` et les parents par `parent_id` avant toute décision.

Une ligne est exacte lorsque `child_rule_terminal` ou `child_tb_exact` est vrai.
Son utility doit alors appartenir à `{-1,0,1}`. Une ligne non exacte utilise
exactement la sentinelle `2`. Les clés supplémentaires ou manquantes, les clés
JSON dupliquées, les constantes non finies, CR, lignes vides, fichiers vides et
valeurs hors bornes sont rejetés.

Toute clé contenant `q200`, à toute profondeur, est interdite sauf le nom exact
`nodes200k`. Cette exception transporte un coût opaque ; elle n'autorise aucun
score, famille, band, label, profondeur, état ou PV q200.

Le SHA du fichier d'entrée dans le manifest couvre ses bytes reçus. Les hashes
sémantiques par parent sont calculés après resérialisation canonique des objets
validés et ordonnés.

## 4. Policy legacy portée sans paramètre libre

Les constantes d'implémentation sont :

```text
M5                 = 100
M50                = 60
minimum_survivors  = 2 lorsque possible
tie-break           = row_index croissant
```

Elles reproduisent la policy B1 ; ce document ne les propose pas comme seuils
confirmatoires.

La précédence exacte est :

1. S'il existe au moins un exact de utility `WIN=1`, choisir son plus petit
   `row_index`, ne charger aucun étage et publier `EXACT_WIN`.
2. Si tous les siblings sont exacts, choisir le plus petit exact draw lorsqu'il
   existe et publier `ALL_EXACT_DRAW` ; sinon choisir le plus petit exact loss et
   publier `ALL_EXACT_LOSS`. Aucun étage n'est chargé.
3. Sinon, seuls les siblings non exacts entrent dans l'allocation par étages.

Pour un ensemble non exact et un score donné, `_top_with_margin` classe par score
décroissant puis `row_index` croissant. Il conserve chaque ligne située à au
plus la marge du meilleur score et ajoute les deux premières lignes du classement
lorsqu'elles existent. Le résultat publié est remis en `row_index` croissant.

`S5_rows` est obtenu avec `q5k_parent` et `M5=100`. `S50_rows` est obtenu à
partir de `S5_rows` avec `q50_parent` et `M50=60`. Si `S50_rows` ne contient
qu'une ligne, elle devient le choix pré-q200, `S200_charge_rows` est vide,
`SOLE_UNRESOLVED_BEFORE_Q200` est publié et `uncertified_shadow=true`. Sinon,
il n'existe pas encore de choix pré-q200 et `S200_charge_rows=S50_rows`.

Les enums fermés de raison sont donc :

```text
exact_shortcut_reason = null | EXACT_WIN | ALL_EXACT_DRAW | ALL_EXACT_LOSS
sole_survivor_reason  = null | SOLE_UNRESOLVED_BEFORE_Q200
```

## 5. Deux vues d'entrée et trois niveaux d'empreinte

Le parseur construit une entrée complète authentifiée, puis sépare immédiatement
les données remises à la policy des coûts q200.

`ProjectionInputFullV1` est l'objet parent complet, avec `nodes200k`. Sa
sérialisation canonique produit `projection_input_sha256`. Ce hash authentifie
les scores q5k/q50 et tous les coûts reçus.

`ProjectionDecisionInputV1` conserve exactement le même schéma et les mêmes
champs, sauf l'omission de `nodes200k` dans chaque ligne. Sa sérialisation
canonique produit `decision_input_sha256`. Seul cet objet, représenté par les
types `ProjectionDecisionInputV1` et `DecisionRowV1`, est remis à
`seal_decision`. `DecisionRowV1` ne possède aucun membre `nodes200k`.

La décision scellée contient exactement :

```text
parent_id
ordered_rows
S5_rows
S50_rows
S200_charge_rows
pre_q200_choice_row_or_null
exact_shortcut_reason
sole_survivor_reason
uncertified_shadow
```

Sa sérialisation canonique produit `decision_output_sha256`. Ce hash exclut les
coûts, les deux hashes d'entrée et le reçu complet.

Le reçu parent ajoute les coûts, compteurs et trois hashes. Son hash canonique
complet, `allocation_receipt_sha256`, est publié dans `parent_receipts` du
manifest. Le manifest publie aussi le SHA des bytes du JSONL d'entrée et celui
du JSONL de reçus. Ces niveaux ne sont pas interchangeables : le hash complet
authentifie la provenance et les coûts, tandis que `decision_output_sha256`
authentifie l'invariance de la policy.

## 6. Validation de `nodes200k` et barrière q200

La validation de schéma, type et plage de `nodes200k` est autorisée avant le
scellement. Elle appartient à l'ingress fail-closed. `_strict_int` refuse bool,
float, chaîne, valeur négative et valeur supérieure à `UINT64_MAX` avant tout
appel de policy.

Après cette validation, deux objets sans référence partagée donnant accès au
coût sont construits :

- `ProjectionDecisionInputV1`, seul objet de policy, ne contient pas le coût ;
- `CostRows200V1` est une `MappingProxyType(row_index -> nodes200k)` immutable,
  inaccessible à la policy et consultée seulement après scellement.

Cette séparation est la barrière. Conserver un coût brut opaque jusqu'après le
scellement n'est pas requis et affaiblirait la validation d'ingress.

Les compteurs par parent et agrégés dans le manifest ont le sens exact suivant :

```text
nodes200k_validated_rows           = nombre de lignes validées
nodes200k_policy_reads             = 0
nodes200k_policy_branches          = 0
nodes200k_preseal_aggregation_reads= 0
nodes200k_aggregation_reads        = |S200_charge_rows|
q200_value_reads                   = 0
q200_label_reads                   = 0
q200_branches                      = 0
```

Une comparaison de type ou plage incrémente seulement la validation ; elle ne
peut modifier aucun ensemble, ordre, choix, tie-break, shortcut, raison ou flag.
La passe post-scellement sélectionne des coûts par l'appartenance déjà fixée à
`S200_charge_rows` et ne peut réévaluer cette appartenance.

Les deux propriétés de perturbation sont distinctes :

1. Les valeurs, familles et labels q200 sont hors schéma. Les perturber dans un
   full ladder externe laisse le reçu de projection byte-identique.
2. Modifier seulement un `nodes200k` valide modifie
   `projection_input_sha256` et le hash complet du reçu. Si la ligne est
   chargée, cela modifie aussi `shadow_nodes200` et `shadow_nodes_total`.

Sous la seconde perturbation, doivent rester identiques :

```text
decision_input_sha256, decision_output_sha256
ordered_rows, S5_rows, S50_rows, S200_charge_rows
pre_q200_choice_row_or_null
shadow_nodes5, shadow_nodes50
exact_shortcut_reason, sole_survivor_reason, uncertified_shadow
nodes200k_policy_reads, nodes200k_policy_branches
nodes200k_preseal_aggregation_reads
q200_value_reads, q200_label_reads, q200_branches
```

Pour une ligne hors `S200_charge_rows`, seuls `projection_input_sha256` et le
hash complet du reçu changent. Pour une ligne chargée, le test impose aussi un
delta exact représentable de `shadow_nodes200` et `shadow_nodes_total`. Toute
autre différence est `B2_PROJECTION_BARRIER_FAILURE`, terminale avant fraîcheur.

## 7. Comptabilité des coûts

Après scellement :

```text
shadow_nodes5   = somme nodes5k de tous les siblings non exacts,
                  ou 0 si exact_shortcut_reason n'est pas null
shadow_nodes50  = somme nodes50k sur S5_rows
shadow_nodes200 = somme nodes200k sur S200_charge_rows
shadow_nodes_total = somme vérifiée des trois composantes
```

Chaque composante et le total sont additionnés en `uint64` avec contrôle avant
addition. Tout overflow échoue fermé. Les exact shortcuts ont un coût staged
nul. Le cas d'un seul survivant non exact paie q5/q50 conformément aux ensembles
mais aucun q200 simulé.

## 8. Preuves déjà obtenues et preuve exhaustive encore requise

La suite propre au projecteur contient 12 tests et passe. Elle couvre précédence
exacte, marges et ties, minimum deux, poison q200, perturbations séparées,
validation pré-policy, types/bornes, overflow, hashes scellés, canonicalisation
des sorties, manifest, entrées malformées et collisions de chemins.

La suite combinée suivante contient 22 tests et passe également :

```text
python -m unittest \
  jobs.tests.test_adaptive_sibling_b2_projection \
  jobs.tests.test_adaptive_sibling_teacher_shadow \
  jobs.tests.test_adaptive_sibling_teacher_shadow_guards
```

La revue indépendante de ces invariants n'a trouvé aucun P1/P2 restant sur les
empreintes publiées en tête de document.

Ces preuves unitaires ne remplacent pas l'équivalence exhaustive sur le
développement B1. Avant toute fraîcheur B2, un job futur doit comparer le
projecteur au chemin legacy sur les 8 000 parents B1, parent par parent : ordre,
exact shortcuts, `S5_rows`, `S50_rows`, `S200_charge_rows`, choix pré-q200,
raisons, flags et coûts simulables. Après la jointure q200 distincte, il doit
aussi comparer choix final, same-row, full/shadow nodes et rapport B1 complet,
avec hashes d'inputs/outputs, diff vide et rapport reproduit byte-identique.

Cette preuve 8k n'a pas encore été exécutée. Une divergence donne
`B2_IMPLEMENTATION_NOT_EQUIVALENT` et arrête le chemin avant toute donnée B2.

## 9. Garde-fous du futur wrapper de preflight statistique

Le preflight statistique est un job distinct. Son wrapper doit appeler uniquement
le CLI déjà revu :

```text
python jobs/tools/adaptive_sibling_b2_statistics.py \
  --preflight-synthetic \
  --kernel-receipt <synthetic-statistical-runtime-probe.json> \
  --out-dir <nouveau-répertoire>
```

Le wrapper doit appliquer les garde-fous suivants sans ajouter de paramètre ou
de seuil scientifique :

1. Épingler le commit et vérifier byte-identiques le blob de l'outil, ses tests
   et le contrat publié ; exiger un checkout propre au début et à la fin.
2. Résoudre l'interpréteur explicitement. Son implémentation, sa version, son
   chemin, sa plateforme, sa machine, sa libc et son nombre de CPU visibles
   doivent correspondre exactement au reçu kernel authentifié. Une version
   supposée ou seulement locale est refusée.
3. Authentifier le reçu kernel par SHA256 avant l'appel. Le loader doit valider
   son JSON canonique, les 2 000 000 tirages, dix accumulations, le vecteur
   SplitMix64, les dix checksums fixés, les champs temporels finis et positifs,
   et le caractère `SYNTHETIC_ARITHMETIC_ONLY`.
4. Fournir un `out-dir` absent, dédié et sans alias avec le code, le reçu kernel,
   les logs ou tout autre input. Refuser une sortie ou un temporaire préexistant.
5. Ne monter ni sélectionner aucune cohorte B2 et ne fournir aucun teacher,
   parent scientifique ou résultat frais. Le wrapper ne doit avoir aucun chemin
   de CLI pour modifier `R`, la seed, l'ordre des cellules, les quantiles, CP ou
   les gates.
6. Conserver stdout, stderr, temps monotone, temps CPU, RSS, tailles disque,
   code SHA et environnement. Un timeout éventuel est une borne opérationnelle
   déclarée par le job ; il ne permet pas de réduire `R`, changer le PRNG ou
   paralléliser différemment après observation.
7. Après succès, recalculer les SHA des artefacts et exiger dans le reçu final :

```text
synthetic_only=true
scientific_parents=0
fresh_data_reads=0
games=0
fits=0
promotion=false
bake=false
bootstrap_replications=200000
accepted_draws=800000000
runtime_matches_kernel_environment=true
status=VALID
gate_exercise_only=true
scientific_verdict=null
measured_scope=wire_parse_bootstrap_cp_quantiles_report_serialization_and_write
```

8. Vérifier que les hashes et tailles du JSONL synthétique, de la truth et du
   rapport correspondent aux fichiers produits. Un statut invalide, une
   divergence de runtime, de compteur, de checksum ou de hash est un échec
   technique fail-closed ; il ne produit aucun verdict B2.

Le wrapper ne transforme ni les résultats de la fixture synthétique ni sa durée
en seuil confirmatoire. Son reçu sert uniquement à authentifier l'exécution
prospective exacte et à dimensionner le futur job avant tout gel ou toute
fraîcheur.

## 10. Limites

Le projecteur ne prouve pas que le full ladder teacher est valide, que les 8 000
parents legacy sont équivalents, que le readout joint correctement q200, ni que
les critères B2 passent. Ces preuves appartiennent à des étapes distinctes. La
publication de ce contrat et de l'implémentation reste une préparation technique
réversible et ne vaut ni preregistration confirmatoire, ni gel, ni lancement B2.
