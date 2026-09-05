# L3 adaptive shadow B2 — contrat de préparation historique v1

> **STATUS: CONTRAT TECHNIQUE HISTORICAL-ONLY — PAS UNE PRÉENREGISTRATION B2, AUCUN PARAMÈTRE CONFIRMATOIRE GELÉ, AUCUNE DONNÉE FRAÎCHE**

Date : 2026-09-05, Europe/Paris.

## 1. Objet

Ce contrat autorise un outillage borné avant la future préenregistration scientifique B2 :

1. authentifier exactement les 40 artefacts historiques d'identité déjà nommés ;
2. compiler leur union canonique déterministe pour l'exclusion de parents ;
3. exécuter sur CPX62 un probe kernel-only borné de 2 000 000 tirages SplitMix64 et dix accumulations entières par tirage ;
4. publier des reçus matériels qui préparent, sans le remplacer, un futur preflight synthétique complet puis la préenregistration B2.

Cette préparation ne teste aucune hypothèse B2 et ne produit aucun verdict de policy. Elle ne confirme ni l'efficacité, ni la fidélité, ni la force de jeu. Son verdict terminal est seulement la disponibilité, l'authenticité et la reproductibilité de l'infrastructure préalable.

Le draft scientifique courant reste un document de travail non gelé. Les règles B1 existantes, notamment M5=100, M50=60, minimum deux survivors et l'interdiction d'utiliser q200 pour l'allocation avant S200, restent immuables ; ce contrat ne les redéfinit pas.

## 2. Autorisation et frontières

L'utilisateur a déjà autorisé l'enchaînement conditionnel code, PR, publications et jobs CPX62 conforme au plan PR771, sans promotion ni bake. Cette autorisation couvre la future publication historique et le probe synthétique décrits ici après merge et checks applicables. Elle ne transforme pas ce document en demande de lancement immédiat.

Limites exécutoires de cette étape :

```text
nouveaux parents B2       = 0
sélection fraîche B2      = 0
labels/scores frais B2    = 0
teacher q5/q50/q200 B2    = 0
parties                   = 0
fits/rankings/sweeps      = 0
promotion                 = false
bake                      = false
freeze confirmatoire B2   = false
queue downstream auto     = false
```

Le publisher peut lire uniquement :

- les 40 artefacts d'identité du catalogue fermé ;
- leurs métadonnées d'authentification strictement nécessaires ;
- le catalogue et l'outillage mergés ;
- un tableau synthétique en mémoire de 500 lignes × 10 entiers, sans FEN réelle, score réel, sibling réel ou résultat expérimental.

Il ne lit aucune cohorte B2, aucun teacher B2, aucun score ou label attaché aux sources historiques et aucune donnée réseau étrangère aux 40 chemins catalogués. Pour HomeScan 1651, le seul payload admis est `artefacts/parents.tsv` ; aucun score, sibling ou métrique Scan n'est admis.

## 3. Univers historique fermé

Le registre normatif de préparation est :

```text
jobs/manifests/adaptive_sibling_b2_exclusion_sources_v1.json
schema          jass.adaptive_sibling_b2_exclusion_sources.v1
universe        PR771_B2_V1_HISTORICAL_40
canonicalization min(exact,rotate180_plus_colour_swap_and_invert_stm)
```

Il doit contenir exactement 40 entrées ordinales contiguës 0..39 :

```text
10 parent_tsv
 1 home_scan_parent_tsv
29 fen
--
40 sources
```

Les 29 FEN comprennent les 24 pools historiques et les 5 pools post-registre déjà consommés par le développement. M1 n'est pas une 41e source : c'est l'alias documentaire de Rich-D C. Le manifest ou son reçu terminal doit publier explicitement `M1_alias_of_RichD_C=true`.

Le catalogue est stable pour B2 v1. Aucune source ne peut être ajoutée, retirée, substituée ou réordonnée par le publisher ou par la future implémentation. Une volonté d'étendre le scope impose une nouvelle version du protocole, revue avant toute fraîcheur ; elle ne peut pas modifier cet univers v1.

Les anciennes sources volontairement absentes, dont R0-v4, O1, JFI, les traces passives SearchDecisionTrace/A3, PL8 et les FEN non cataloguées, restent hors scope. Cette borne ne prétend pas qu'elles sont disjointes de l'union. Elle limite honnêtement la revendication à l'identité plateau+STM que les 40 artefacts permettent d'établir.

## 4. Authentification 40/40

Pour chaque entrée, le wrapper appelle le chemin standard `fetch_result_files.py` avec le préfixe, le job, l'attempt et l'unique `artifact_path` du catalogue. Chaque reçu doit attester exactement :

```text
schema       = 1
state        = verified
prefix       = valeur cataloguée
job_id       = valeur cataloguée
attempt_id   = valeur cataloguée
code_sha     = valeur cataloguée
result_state = completed
exit_code    = 0
files        = exactement un élément
```

L'élément `files[0]` doit faire correspondre le chemin distant et le nom local catalogués, puis publier un `size_bytes>0` entier et un SHA256 minuscule de 64 hexadécimaux. Le compilateur recalcule taille et SHA sur les bytes locaux. Une absence, un état non completed, un code non nul, une discordance job/attempt/code/prefix/path/name/taille/SHA ou plus d'un fichier rend la préparation invalide.

Le wrapper publie le SHA256 des bytes du catalogue mergé. Aucun SHA de catalogue, d'outil, de commit ou d'artefact n'est inventé dans ce contrat ; le publisher les matérialise depuis le checkout et les reçus effectivement exécutés.

## 5. Extraction d'identité fail-closed

L'outil de compilation est :

```text
jobs/tools/adaptive_sibling_b2_exclusions.py
```

Il accepte trois allowlists TSV exactes, sans colonne ajoutée, retirée ou réordonnée.

Pour les sources `00-dssd-a`, `04-micro-m3` et `06-q1` :

```text
parent_id,canonical_fingerprint,raw_fingerprint,parent_stm,
pieces,legal_moves,phase,partition,source_identity,source_bucket,
candidate_id,source_path,source_row_index,sample_hash
```

Pour les sept autres `parent_tsv` :

```text
parent_id,canonical_fingerprint,raw_fingerprint,parent_stm,
pieces,legal_moves,phase,source_row_index,sample_hash
```

Pour `10-home-scan-ceiling` :

```text
parent_id,canonical_fingerprint,raw_fingerprint,parent_stm,
pieces,legal_moves,phase,source_shard,source_row_index,
selection_hash,subset_hash,in_deep512,in_ultra256
```

Cette égalité de schéma exclut implicitement toute colonne score/WDL/utility/label/target. Les parent_id TSV sont contigus depuis zéro ; STM vaut 0 ou 1 ; les bitboards occupent au plus 50 cases, ne se chevauchent pas et leur forme textuelle est normalisée.

Chaque FEN non vide et non commentée doit être une FEN Jass valide avec un côté au trait et exactement un champ W et un champ B. Cases, intervalles, couleurs, rois, doublons et occupations croisées sont contrôlés. Toute ligne non parsable ferme le contrat ; elle n'est ni ignorée ni réparée.

L'identité est :

```text
min(
  fingerprint exact WM:WK:BM:BK:STM,
  rotation 180° + échange des couleurs + inversion STM
)
```

Le port local doit être byte-equivalent à `jobs.tools.tb_frontier_symmetry_dedup.canonical_fingerprint` sur les 256 fixtures valides déterministes prévues par l'outil, et invariant sous la symétrie. Les fingerprints normalisés sont ASCII minuscules. Une identité TSV déclarée doit être égale à l'identité recalculée. Les doublons internes interdits par le schéma TSV échouent ; les doublons FEN et overlaps intersources sont conservés dans la comptabilité avant déduplication de l'union.

## 6. Union et manifest déterministes

Le wrapper de contrôle est `.codex-tmp/cpx62-1773-l3-decision-math-b2-historical-identities-v1.sh`, job sémantique `cpx62-1773-l3-decision-math-b2-historical-identities-v1`. Il épingle le commit mergé avant publication ; ce contrat n'invente pas ce SHA.

La compilation primaire écrit exactement :

```text
historical-parent-canonical-union.txt
historical-parent-exclusion-manifest.json
```

Le fichier union contient une identité canonique par ligne, triée bytewise, encodée ASCII et terminée LF. Le manifest utilise JSON canonique UTF-8/LF, clés triées, séparateurs compacts et newline final. Il publie au minimum :

- le schéma `jass.adaptive_sibling_b2_historical_exclusion_manifest.v1` ;
- `historical_authentication_only=true` ;
- `confirmation_freeze=false` ;
- `scores_or_labels_read=0` ;
- le SHA du catalogue ;
- 40 sources et le compte exact 10+1+29 ;
- pour chaque source, reçus/SHA/taille, lignes, uniques, doublons internes, overlap avec l'union antérieure et cumul unique ;
- le nombre total de lignes, la cardinalité finale unique, la sérialisation et le SHA256 de l'union ;
- `M1_alias_of_RichD_C=true`, son job/attempt d'alias et `new_source_added=false` ;
- la preuve de 256 fixtures de canonicalisation contre le helper de référence.

Le wrapper recalcule après écriture les SHA et cardinalités annoncés. Il effectue une seconde compilation dans des chemins scratch absents et distincts avec les mêmes entrées, compare union et manifest byte à byte, puis peut supprimer les sorties de répétition. Cette deuxième passe est un round-trip mécanique peu coûteux ; elle ne lit aucune autre source et ne crée aucun artefact scientifique supplémentaire. Toute sortie préexistante, alias entre entrée/source/reçu/sortie/temporaire, exception ou différence entre les deux passes échoue avant publication.

Les cardinalités et overlaps réels sont des propriétés historiques d'identité. Ils peuvent être lus avant le gel B2 parce qu'ils ne contiennent aucune observation fraîche ni aucun outcome de la policy. Ils ne permettent pas de changer les 40 sources.

## 7. Probe synthétique borné du kernel

### 7.1 Portée exacte

Le job 1773 ne mesure pas l'implémentation statistique confirmatoire complète. Il exécute seulement le noyau suivant avec le `python3` qui réalise aussi le publisher :

```text
seed SplitMix64                  = 2026110717
n                               = 500
vecteur de contrôle             = 20 indices attendus
synthetic_rows                  = 500 tuples de 10 entiers
synthetic_rows[i][j]             = (i+1)*(j+1)
tirages chronométrés            = 2000000
accumulations entières/tirage   = 10
timeout interne du probe        = 60 s
ordre                           = séquentiel, un processus
```

Le vecteur attendu est exactement :

```text
159,188,35,319,13,47,123,305,286,282,
426,24,322,233,439,277,331,319,261,284
```

Après ce contrôle, l'état PRNG repart du seed. À chaque tirage accepté dans `[0,500)`, les dix entiers de la ligne choisie sont additionnés à dix accumulateurs Python. Le probe ne crée pas de `SyntheticParentStatsV1`, n'exécute pas 800M tirages, ne calcule aucun ratio, intervalle Clopper-Pearson ou quantile, ne trie aucune distribution et ne mesure pas le RSS.

### 7.2 Environnement et artefact réels

`statistical-runtime-environment.json` publie exactement les champs observés par le wrapper :

- `python_version`, `python_implementation`, `python_executable` ;
- `platform`, `machine`, `libc`, `nproc`, `code_sha` ;
- les SHA256 des quatre fichiers de code/catalogue vérifiés contre les blobs du commit.

Ce job observe la version Python de CPX62 ; il ne prétend pas qu'elle vaut CPython 3.12.14 et ne l'authentifie pas comme runtime confirmatoire final.

`synthetic-statistical-runtime-probe.json` publie exactement :

```text
kind = SYNTHETIC_ARITHMETIC_ONLY
scientific_parents = 0
draws = 2000000
integer_accumulations_per_draw = 10
splitmix_test_vector_pass = true
elapsed_seconds
draws_per_second
extrapolated_800m_draw_kernel_seconds = elapsed_seconds * 400
kernel_only_excludes_parsing_ratios_quantiles_and_final_validation = true
synthetic_accumulator_checksums
environment
```

L'extrapolation ×400 borne uniquement le kernel de tirage et d'accumulation sous cet environnement. Elle ne constitue ni une ETA du bootstrap exact ni un sizer du futur readout. Le readout 1581 à 325 secondes reste non comparable.

## 8. Sorties réelles du publisher 1773

Le run publie :

```text
exclusion-sources-catalog.json
statistical-runtime-environment.json
verified-sources/<40 reçus>
fetch-logs/<40 logs>
historical-parent-canonical-union.txt
historical-parent-exclusion-manifest.json
synthetic-statistical-runtime-probe.json
scientific-summary.json
VERDICT__B2_HISTORICAL_IDENTITY_PREPARATION_COMPLETE
```

`progress.json` est un état de progression, pas un résultat scientifique. `scientific-summary.json` réconcilie les 40 sources, SHA catalogue/union/manifest, cardinalité de l'union, temps de fetch, environnement, probe et compteurs de frontière. Il reste inférieur à 65 536 bytes dans le wrapper.

Les compteurs et flags terminaux sont exactement :

```text
new_searches             = 0
new_fits                 = 0
strength_games           = 0
fresh_parent_generation  = 0
b2_confirmation_frozen   = false
b2_confirmation_executed = false
promotion_authorized     = false
bake_authorized          = false
```

## 9. Gate technique et verdict exact

`B2_HISTORICAL_IDENTITY_PREPARATION_COMPLETE` requiert conjointement :

1. hostname `cpx62`, `nproc=16`, checkout propre et commit épinglé ;
2. fichiers code/catalogue byte-identiques aux blobs du commit ;
3. exactement 40/40 sources vérifiées et 10+1+29 types ;
4. payload unique, taille et SHA conformes pour chaque source ;
5. trois allowlists TSV exactes et parsers FEN/fingerprint fail-closed ;
6. canonicalisation équivalente au helper sur 256 fixtures ;
7. union non vide et manifest/union byte-identiques entre deux compilations ;
8. comptabilité par source, overlaps, cumul et SHA réconciliés ;
9. alias M1/Rich-D C attesté sans 41e source ;
10. vecteur de 20 indices SplitMix exact ;
11. probe 2M × 10 achevé sous 60 s et checksums publiés ;
12. budget de travail 1 500 s respecté et compteurs de frontière à zéro/false.

Toute autre issue échoue le job et s'arrête sans fraîcheur. Un retry technique conserve exactement catalogue et sources ; il explique la panne et publie un nouvel attempt. Il ne change aucune règle scientifique.

Le verdict exact signifie seulement que les identités historiques et le probe kernel-only ont été publiés. Il ne vaut jamais `B2_ADAPTIVE_SHADOW_POLICY_CONFIRMED_V1`, ne gèle aucun seuil, ne dimensionne pas le readout, ne permet pas la génération B2 à lui seul et ne lance aucun downstream.

## 10. Étapes obligatoires après 1773

Après 1773, une revue scientifique indépendante vérifie les preuves réelles 40/40, l'union, les allowlists, l'environnement observé et la portée bornée du probe.

Le draft scientifique v3 conserve ensuite, hors du périmètre de ce contrat, l'obligation d'implémenter, revoir et exécuter un preflight statistique complet sans donnée B2 avant toute proposition de gel ou fraîcheur. Le probe kernel-only 1773 ne satisfait pas cette obligation.

Seulement après ce futur reçu complet et sa revue, une préenregistration B2 peut épingler SHA, runtime et sizer, recevoir sa revue finale et merger avant sélection. Aucun paramètre n'est choisi par l'implémenteur et aucune donnée confirmatoire fraîche n'est lue entre ces étapes.

La préparation 1773 s'arrête à ses reçus. Elle ne queue ni le preflight complet, ni B2 frais, ni B3.

## 11. Première tentative — échec technique Q1 et correction

Le job `cpx62-1773-l3-decision-math-b2-historical-identities-v1`, tentative
`20260905T005721Z-227c7917`, a exécuté le commit
`227c79177699bdb6e8dac1db77a119f5db7afdbf`. Le runner rapporte un début
`2026-09-05T00:57:25+00:00`, une finalisation `2026-09-05T01:02:27+00:00`
et un échec technique avec exit `1`. Les 40 téléchargements ont terminé en
90,802 s. Le compilateur s'est arrêté sur le schéma Q1 avant de publier
l'union ou son manifeste et avant la sonde synthétique. Aucun verdict de
préparation ou de confirmation n'est acquis par cette tentative.

La correspondance de schéma attribuait à tort 14 colonnes à `06-q1`.
Son payload authentifié `artefacts/q1-selected-parents.tsv.gz`, issu de
`cpx62-1617-l3-joint-td-q1-select-v7` / `20260828T114236Z-2034c5c9`,
contient exactement les neuf colonnes suivantes :

```text
parent_id canonical_fingerprint raw_fingerprint parent_stm pieces legal_moves phase source_row_index sample_hash
```

Les séparateurs réels sont des tabulations. Le SHA256 du fichier compressé est
`d04988a233db3cc1f1f1136918421192c239f7b42edfdf1f79abcbd94013d4f5`
pour 278 386 octets. L'audit des onze en-têtes authentifiés confirme que seules
les sources A et M3 utilisent le schéma à 14 colonnes, HomeScan celui à 13
colonnes, et les huit autres sources TSV celui à neuf colonnes.

La correction retire uniquement Q1 de la liste des sources à 14 colonnes.
Les allowlists restent exactes : aucune colonne supplémentaire, aucun score
ou label n'est accepté. Le catalogue et ses 40 sources ne changent pas.
Un test de régression reconstruit explicitement l'en-tête Q1 observé et
vérifie la compilation des 40 fixtures. Les 14 tests du compilateur passent.

Le reçu de runtime de cette tentative authentifie **CPython 3.14.4**,
`/usr/bin/python3`, Linux `7.0.0-30-generic`, `x86_64`, glibc `2.43` et
`nproc=16`. Il n'apporte aucune durée de sonde, aucun résultat statistique et
ne remplace pas le futur preflight complet.

Le journal et le reçu runtime sont publiés sous le préfixe immuable
`r2:jass-data/runs/cpx62-1773-l3-decision-math-b2-historical-identities-v1/20260905T005721Z-227c7917`.
Leurs SHA256 vérifiés contre inventaire et checksums sont respectivement :

```text
output.log.gz
1639dfa6ee49405f866fc6716ed58e1db2cdcec75c54ea3babf9239b24c1657b
artefacts/statistical-runtime-environment.json
c139b282352ec34b3f40b6779ad1e63609cfb22b687b5a8893f61f0cf442ce30
```

La reprise technique conserve le même catalogue, les mêmes règles d'identité,
les deux compilations, la sonde 2M et les limites de travail. Elle doit épingler
le commit du correctif et publier une nouvelle tentative, sans nouvelle donnée
de confirmation.
