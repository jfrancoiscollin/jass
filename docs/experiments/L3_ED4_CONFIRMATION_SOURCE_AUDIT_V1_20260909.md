# ED4-C0A — préenregistrement de l'audit des sources de confirmation V1

Date : 2026-09-09. Statut : **PRÉENREGISTREMENT PROSPECTIF, METADATA ET
STRUCTURE UNIQUEMENT**.

Ce stage construit le registre d'exclusion nécessaire à une future confirmation
ED4. Il ne sélectionne aucune nouvelle position, ne fixe aucun volume, seed,
budget, politique de partie ou méthode d'intervalle et n'exécute aucun teacher,
search, fit ou partie. La seule dérivation de position autorisée est
l'énumération des enfants légaux de parents historiques score-free connus.

ED4-P1, ses contrôles et la campagne restent inchangés. Aucun fichier BASE,
HARD, SOFT ou ED4 n'est accessible à C0A. Aucune dépense de `alpha_1` n'a lieu et
aucun gate candidat ne peut passer ici.

## 1. Question bornée et livrable

C0A demande : peut-on authentifier, sans lire de cible, un univers canonique
reproductible qui couvre les parents, enfants, racines et positions CURRENT_2M
structurelles déjà consommés par les branches pertinentes de décision,
calibration et recherche ?

Le livrable positif est une union ASCII triée d'identités board+STM et un
catalogue qui distingue :

```text
static_decision_history
wdl_history
search_history
```

Il réserve seulement les noms des futurs rôles :

```text
static_decision  wdl_game_opening  search_root
static_timing    wdl_timing        search_timing
```

C0A ne matérialise aucun de ces six rôles. Leur ordre, leurs seeds, leurs
volumes et leurs règles restent hors de ce protocole.

## 2. Identité canonique unique

Pour les 33 octets structurels d'un record JNNW
`white_men,white_kings,black_men,black_kings,stm`, l'identité est exactement :

```text
min(
  fingerprint exact WM:WK:BM:BK:STM,
  rotation180 + échange couleurs + inversion STM
)
```

Le format ASCII, la validation des 50 cases, l'absence de recouvrement des
bitboards et la symétrie sont byte-equivalents à
`jobs.tools.tb_frontier_symmetry_dedup.canonical_fingerprint` et au compilateur
1773. Les fichiers JNNW exigent magic, cardinalité et taille
`8 + 38*N` exactes. Les identités déclarées dans un TSV/manifest sont
recalculées ; elles ne remplacent jamais les bytes structurels.

Pour chaque parent historique sans `children.jnnw` score-free publié, le movegen
de production énumère une fois toutes les actions légales, déduplique selon
l'identité sémantique `Move` et canonise chaque enfant. Le nombre émis doit être
égal au nombre légal recalculé et au compteur structurel scellé lorsqu'il existe.
Si un `children.jnnw` score-free existe, son ordre, son rattachement parent et
ses bytes structurels doivent aussi concorder avec la reconstruction. Aucun
score teacher ne sert à reconstruire un enfant.

## 3. Sources littérales et allowlists

Toute source est authentifiée par `fetch_result_files.py` contre son résultat,
son inventaire et ses checksums. Aucun fallback, préfixe élargi, découverte de
payload ou substitution de tentative n'est permis.

### 3.1 Socle historique parent-only

```text
job      cpx62-1835-l3-decision-math-b3-fresh-exclusion-prep-rerun-v1
attempt  20260906T134208Z-c553a572
code     c553a572ed8ada9c49f8ebbefa3db22a9b6ca739
allow    artefacts/b3-fresh-exclusion-union.txt
         artefacts/b3-fresh-exclusion-manifest.json
```

Hashes attendus :

```text
union     b553939e8ded3ab31d121e40b2be9cfa1012168bf01835f692b59a60815d9ecb
manifest  f734de99761b7a3ee7ddb107de3d678fa29eb7e39a11708b6a8c8bbbe700cc0c
count     227317
```

Ce socle contient l'union parent-only 1773 de 223 317 identités et les 4 000
parents B2. Il ne prouve pas que tout état jamais produit par le projet est
présent et ne contient pas à lui seul les footprints enfants.

### 3.2 Benchmark HomeScan et footprints B2/B3

```text
HOME_SCAN
job      home-1651-l3-scan-ceiling-selection-v1
attempt  20260829T133348Z-28e12fba
code     28e12fba0ead14def244ffc442b15937f65edc0e
allow    artefacts/manifest.json
         artefacts/parents.jnnw.gz
         artefacts/children.jnnw.gz
         artefacts/siblings.tsv

B2
job      cpx62-1778-l3-decision-math-b2-source-selection-v1
attempt  20260905T102917Z-d3657332
code     d3657332c3a5609a5501a9ff130f5d5c19488c7f
allow    artefacts/source-selection-publication.json
         artefacts/parents.jnnw
         artefacts/parents.tsv
         artefacts/ordered-identities.txt

B3
job      cpx62-1837-l3-decision-math-b3-fresh-source-selection-v1
attempt  20260906T141235Z-29084b25
code     29084b25789b1a88c19a86f73c476eedc52acbc6
allow    artefacts/source-selection-publication.json
         artefacts/parents.jnnw
         artefacts/parents.tsv
         artefacts/ordered-identities.txt
```

HomeScan ajoute les siblings du benchmark dont 1773 ne portait que les parents.
Les enfants B2 et B3 sont reconstruits depuis leurs parents score-free. Les
bundles teacher 1801/1841 et le full ladder 1843 sont interdits. Le B3 complet
couvre ses sous-cohortes d'audit 1842/1843.

### 3.3 Racines recherche D4

```text
job      cpx62-1862-l3-decision-math-d4-search-utility-offline-cardinality-recovery-requeue-v1
attempt  20260907T182914Z-1c779cc8
code     1c779cc87608a12b26432cad6a23872aeb5eabe8
allow    artefacts/d4-search-utility-roots.tsv
         artefacts/d4-root-pool-provenance.json
```

Le TSV doit garder exactement son schéma
`root_index,split,canonical_identity,fen,selection_digest`. Chaque FEN est
reparsée et son footprint légal reconstruit. Ce superset couvre les
sous-sélections 1864/1868. Les deux cohortes ED1 issues de HomeScan sont déjà
couvertes par le bundle HomeScan complet.

### 3.4 ED2-P0 et confirmations ED3

```text
ED2_P0
job      cpx62-1875-l3-ed2-data-teacher-preflight-v1
attempt  20260908T171140Z-bc30d685
code     bc30d6858c4d590625f8831c4995f055816b95c2

ED3_REHEARSAL
job      cpx62-1883-l3-ed3-confirmation-rehearsal-v1
attempt  20260909T050858Z-0946f57d
code     0946f57d5443c0507fd9210371396bdf1c49abd2

ED3_PRODUCTION
job      cpx62-1884-l3-ed3-confirmation-production-v1
attempt  20260909T051901Z-0946f57d
code     0946f57d5443c0507fd9210371396bdf1c49abd2
```

Pour chacun, l'allowlist structurelle est littéralement :

```text
artefacts/source/parents.jnnw
artefacts/source/children.jnnw
artefacts/source/parents.tsv
artefacts/source/groups.tsv
artefacts/source/source.json
```

Ajouter `artefacts/ed2-source-seal.json` pour 1875, et
`artefacts/cohort-seal.json`, `artefacts/guard-plan.json` pour 1883/1884. Les
schémas ED2 autorisés sont exactement :

```text
parents.tsv = parent_id,parent_fingerprint,canonical_fingerprint,parent_phase,
              parent_stm,split,trajectory_index,seed
groups.tsv  = row_index,sibling_identity,child_fingerprint,
              child_rule_terminal,child_legal_moves,parent_id,parent_phase,
              parent_stm,split
```

Tout autre champ ou ordre échoue. Seuls ces champs structurels sont parsés.

### 3.5 Exclusion structurelle de tout CURRENT_2M

```text
job      cpx62-1878-l3-ed2-numerical-recovery-n1
attempt  20260908T191343Z-d71679e9
code     d71679e96d78609b6d32052be80ca78c0deaece0
allow    artefacts/wdl-selection.json
         artefacts/wdl-selection.seal.json
         work/current.jnnw
         work/current.jsm
```

Le JNNW et le sidecar sont ceux reproduits et authentifiés par N1 contre le
manifest CURRENT_2M. Le nombre attendu est celui du header/manifest scellé,
exactement 2 000 000. **Toutes** les positions structurelles sont canonisées et
exclues, indépendamment du split ou des indices effectivement lus par ED2/ED3.
Ce choix évite de qualifier de fraîche une tranche inconnue d'un corpus
globalement exposé. Les `guard-plan.json` 1883/1884 et la sélection N1 servent
seulement à réconcilier les rôles consommés ; ils ne réduisent jamais cette
exclusion complète.

`current-context30.npy`, les tables natives, les fichiers de modèle et tout
autre fichier N1 sont interdits.

## 4. Ledger de lecture au niveau champ

Avant tout payload, le stage écrit `field-read-policy.json`; après exécution il
écrit `field-read-ledger.json`. Les deux utilisent le schéma
`jass.ed4.c0a_field_read_ledger.v1` et comptent, par source/fichier/type de
champ, `transported`, `authenticated`, `parsed_records` et `semantic_reads`.

Lectures permises :

- résultats/inventaires/checksums : uniquement job, attempt, code SHA, state,
  exit, chemins, tailles, SHA256 et descripteurs de schéma/cardinalité ;
- union 1835 et `ordered-identities.txt` : identité ASCII seulement ;
- JNNW score-free : header, bytes 0..32, et bytes 33..37 uniquement pour exiger
  qu'ils soient tous nuls ;
- `work/current.jnnw` : header et bytes 0..32 ; le lecteur saute 33..37 sans les
  décoder ni les copier dans un objet ;
- JSM1/JSM2 : `game_id`, `opening_id`, `seeded` seulement. En JSM2, ply,
  game_plies, last_eps_ply, `game_result` et flags sont sautés. Ces champs ne
  participent pas à l'identité canonique ;
- TSV : uniquement les colonnes structurelles explicitement gelées ci-dessus,
  celles du D4 root TSV, et les identifiants/rattachements structurels du
  `siblings.tsv` HomeScan ;
- JSON source/seal/publication : uniquement identité, rôle/split, descripteurs,
  compteurs de structure, seeds de provenance, target-blind/score-free et hashes.

Sont interdits avec compte attendu zéro : score, q5/q50/q200, utility, label,
WDL, outcome, `game_result`, logit, regret, candidate choice, métrique,
Context30, feature tensor et bytes de modèle. Le hash intégral nécessaire à
l'authentification de transport n'est pas une lecture sémantique ; il est
compté séparément. Un parser générique qui matérialise un JSON/TSV entier puis
ignore des clés est interdit : les allowlists de champs sont appliquées à la
lecture.

Le résumé doit constater :

```text
model_reads=0  fit_calls=0  search_calls=0  teacher_calls=0
games=0        outcomes_read=0  qvalues_read=0  alpha_spent=0
new_source_positions=0
```

`derived_legal_children` est reporté séparément et ne peut provenir que des
parents historiques allowlistés.

## 5. Inventaire des producteurs et limite de la revendication

Une phase préalable peut interroger uniquement les status, manifests,
inventaires et checksums authentifiés pour résoudre l'existence, le nom, la
taille et le hash d'un artefact structurel. Elle ne télécharge aucun payload et
ne lit aucune valeur scientifique.

Le cutoff du catalogue est littéral : tous les jobs dont l'ordinal sémantique
est compris entre **1773 et 1888 inclus**, tels qu'ils existent dans les
metadata authentifiées de `jass-control` au commit de préenregistrement C0A,
doivent avoir exactement une ligne. Les sources antérieures nommées
explicitement dans les allowlists, dont HomeScan 1651, restent incluses par leur
identité littérale ; elles ne rouvrent pas un inventaire antérieur général. Un
job créé après 1888 n'entre pas rétroactivement dans C0A-v1. Un identifiant sans
ordinal interprétable dans cette fenêtre est `unknown`, jamais classé par une
heuristique de nom.

Le stage classe chaque producteur de cohorte visible entre le gel 1773 et le
gel de C0A dans exactement une catégorie :

```text
included_exact
covered_by_authenticated_superset
non_position_producer
structural_payload_unavailable
```

Chaque ligne donne job/attempt/code, rôle historique, source couvrante et preuve.
La catégorie est justifiée par le manifest, l'inventaire ou un reçu source
authentifié ; le nom du job ne suffit pas à la déduire.
Un producteur absent du catalogue, une catégorie inconnue, ou un producteur de
TRAIN/benchmark/confirmation placé dans `structural_payload_unavailable` rend
le verdict positif impossible. Le stage publie alors la liste exacte des
manques, sans inventer de chemin et sans télécharger une cible. Une version
ultérieure pourrait ajouter les payloads identifiés avant toute sélection
fraîche ; C0A-v1 ne s'étend pas dynamiquement.

La revendication positive reste bornée aux 40 sources parent-only de 1773, à
leurs extensions authentifiées 1835, et aux deltas littéraux ci-dessus. Les
anciennes sources que le manifest 1773 déclare hors scope ne deviennent pas
soudain prouvées disjointes. Si l'inventaire les identifie comme corpus de
parents TRAIN/benchmark/confirmation non couvert, le résultat est insuffisant.
Il n'existe aucune revendication « toute position jamais étudiée par le projet ».

## 6. Algorithme et invariants de publication

L'ordre est immuable :

1. authentifier code, protocole, status et inventaires ;
2. écrire le catalogue et la policy de champs ;
3. terminer la classification des producteurs ;
4. si elle est complète, fetcher seulement les allowlists ;
5. vérifier formats, seals, champs et zéro-target ;
6. canoniser CURRENT_2M entier et toutes les positions publiées ;
7. reconstruire les seuls footprints enfants manquants ;
8. concaténer, dédupliquer, trier bytewise et écrire l'union ;
9. relire indépendamment tous les outputs, puis publier le ledger final.

Les comptes par source sont ceux observés dans les headers/descripteurs
authentifiés ; aucun compte enfant ou overlap n'est préinventé. Les invariants
obligatoires sont : entrée non vide pour chaque source requise, cardinalité
reconciliée fichier par fichier, zéro contradiction identité/parent/enfant,
CURRENT_2M exactement complet, union triée/unique/LF, et
`final_unique = prior_unique + additions_unique - overlaps`. Tous les overlaps
par paire de sources sont publiés descriptivement ; ils ne servent à exclure
une source du catalogue.

Sorties immuables :

```text
source-catalog.json
producer-classification.json
field-read-policy.json
field-read-ledger.json
source-authentication.json
legal-child-reconstruction.json
canonical-exclusion-union.txt
canonical-exclusion-manifest.json
audit-pure-payload.json
scientific-summary.json
publication-manifest.json
```

`audit-pure-payload.json` contient uniquement les identités d'entrée, compteurs,
hashes et invariants déterministes, sans mode, chemin local, temps ou tentative
d'exécution. Le manifest interne hash uniquement les payloads immuables de la
liste jusqu'à `audit-pure-payload.json`, hors lui-même. Il exclut
`scientific-summary.json`, que le launcher peut compléter avec sa provenance,
ainsi que les timestamps et preuves finalisés après publication. Ces éléments
sont authentifiés par l'inventaire et le runner externe, sans circularité.

## 7. Répétition complète et limites de ressources

CI teste fixtures synthétiques, parsers à champs interdits, canonicalisation,
reconstruction légale, déterminisme, corruption et producteurs non classifiés.
Elle ne remplace pas le chemin complet.

Avant l'implémentation du parser complet, une admission séparée publie exactement
`ed4-c0a-source-descriptor-inventory.json`, schéma
`jass.ed4.c0a_source_descriptor_inventory.v1`. Elle contient seulement :

```text
state, verdict
audit_code_sha256, protocol_path, protocol_sha256
catalogue_cutoff = {first_ordinal:1773,last_ordinal:1888,inclusive:true}
sources[] = {
  job_id, attempt_id, code_sha, prefix, result_state, exit_code,
  required_paths[] = {
    path, present, size_bytes, sha256,
    declared_cardinality, cardinality_source
  },
  classification, classification_evidence
}
missing_paths[], unknown_or_unclassified_producers[]
declared_input_bytes_total, declared_records_total
payload_downloads=0, payload_bytes_read=0
model_reads=0, target_reads=0, outcome_reads=0, qvalue_reads=0
```

`declared_cardinality` vaut `null` si aucun descriptor metadata ne la publie ;
elle n'est jamais obtenue en ouvrant le payload. `cardinality_source` nomme le
manifest/inventaire et son hash, ou vaut `null`. Le reçu authentifie aussi que
la liste `required_paths` est exactement celle de la section 3. Il permet donc
de constater explicitement si `work/current.jnnw`, `work/current.jsm` et chaque
autre chemin littéral ont survécu à la publication.

Tous les paths requis existent, les identités concordent, chaque job 1773..1888
est classifié par preuve et aucun corpus pertinent n'est
`structural_payload_unavailable` : `ED4_C0A_INVENTORY_ADMISSION_READY_V1`. Un
path manque, un producteur reste inconnu/non classifié, ou un corpus pertinent
n'a pas de payload structurel disponible :
`ED4_C0A_INVENTORY_ADMISSION_INSUFFICIENT_V1`. Status, inventaire ou checksum
non authentifiable : `ED4_C0A_INVENTORY_ADMISSION_TECHNICAL_FAILURE_V1`.
Ce terminal ne fetch aucun payload, n'est ni la répétition ni l'audit C0A, ne
prouve aucune canonicalisation, cardinalité réelle, durée ou compatibilité avec
le cap, et n'autorise ni confirmation ni production. Il autorise seulement
l'implémentation/revue du chemin complet contre les descripteurs disponibles.

La répétition puis la production exécutent toutes deux **l'audit complet** avec
les mêmes inputs, code et protocole. Aucun sous-échantillon. La répétition publie
`ED4_C0A_SOURCE_AUDIT_REHEARSAL_COMPLETE_V1` sans autoriser de suite. La
production n'est admise qu'après authentification de ce terminal. Les payloads
purs `canonical-exclusion-union.txt` et `audit-pure-payload.json` doivent être
byte-identiques. Tous les descripteurs qu'ils contiennent doivent donc retrouver
les mêmes hashes des catalogues, ledgers et manifests immuables. Les champs de
mode, temps, chemins, tentative, lancement et publication ne sont pas comparés.
Aucune sortie n'est choisie entre les deux.

Chaque stage a un cap de 900 s, 16 CPU maximum, aucun thread numérique implicite
et au moins 3 Gio libres ; le runner externe garde un cap de 1500 s incluant
fetch et publication. Après l'admission inventory-only, le preflight technique
peut utiliser les tailles/cardinalités déclarées et une fixture synthétique pour
établir un sizing prospectif ; il ne profile aucun vrai payload et ne change
aucune recette. L'admission seule ne fait aucune inférence de runtime.
Dépassement prospectif du preflight ou support disque insuffisant ferme
l'admission à la répétition complète.

## 8. Issues terminales

- Tout est authentifié, classifié et reproduit deux fois à l'identique :
  `ED4_C0A_CONFIRMATION_SOURCE_AUDIT_COMPLETE_V1`. Suite permise : écrire un
  protocole séparé de timing/source qui fixe encore toutes ses décisions.
- Producteur pertinent non couvert, payload structurel absent, ou opération
  complète impossible sous le cap :
  `ED4_C0A_CONFIRMATION_SOURCE_AUDIT_INSUFFICIENT_V1`. Aucun sélecteur ne peut
  alors se déclarer « fresh » contre cet univers.
- Hash, format, field barrier, canonicalisation, movegen, réconciliation,
  répétition, timeout ou publication échoue :
  `ED4_C0A_CONFIRMATION_SOURCE_AUDIT_TECHNICAL_FAILURE_V1`. Une correction
  mécanique peut répéter le contrat identique ; aucune source ou règle ne peut
  être changée silencieusement.

Aucune issue C0A n'est un résultat scientifique favorable ou défavorable pour
ED4. Le timing, les unités de cluster, les intervalles, les volumes, seeds,
budgets, politiques WDL/search et les quatre gates de campagne restent
entièrement différés et gelés ailleurs avant leur première cible.
