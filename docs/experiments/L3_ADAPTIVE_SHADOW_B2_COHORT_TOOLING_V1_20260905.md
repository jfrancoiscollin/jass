# L3 adaptive shadow B2 — outillage prospectif de cohorte v1

Date : 2026-09-05, Europe/Paris.

**Statut : implémentation prospective ; aucun préenregistrement B2, aucune cohorte fraîche, aucune confirmation.**

Ce document décrit les outils préparatoires du [plan decision-information](L3_DECISION_INFORMATION_IMPLEMENTATION_PLAN_V1_20260903.md). Leur présence dans le dépôt ne déclenche ni n'autorise une génération. Le préenregistrement final et ses reçus doivent être publiés avant toute donnée B2 fraîche. Les contrats ci-dessous proviennent du travail de développement après B1 ; ils ne sont pas des critères rétrospectifs appliqués à B1.

## 1. Sources et séparation des étapes

Le fichier `jobs/manifests/adaptive_sibling_b2_selection_contract_v1.json` contient la recette prospective, les graines, les quotas et les identités historiques. Son SHA256 est `5e94e0b8a71089d01959212debcfe0b90700714d96693097b519090462fe0e66`. Le sélecteur exige ces octets canoniques et n'offre aucune surcharge CLI de population, graine, quota ou recette.

La chaîne prévue est :

```text
préenregistrement publié et authentifié
  -> 16 producteurs CURRICULUM
  -> filtre board/STM seul, séparé par shard
  -> manifeste de préparation scellé
  -> sélecteur sans accès aux JNNW bruts
  -> cohorte et identité ordonnée scellées
  -> vérification indépendante avant lecture teacher
  -> full teacher, fusion et readout contrôlés
```

Les [40 sources historiques de 1773](L3_ADAPTIVE_SHADOW_B2_HISTORICAL_PREPARATION_V1_20260905.md) constituent l'univers d'exclusion fermé : 223 317 classes canoniques, union SHA `3a751ba967276f6e2562bfa7257dfa36fbe562e33cd710dd49abcfe51afdfc8f`, manifeste SHA `2f1a551bf6fe020e6436689dc8ef8c95940f473d79a2ebc8613e6c15447cff16`. Cela ne prétend pas recenser toute position jamais étudiée. Le sélecteur authentifie l'union et son manifeste contre le reçu réussi `20260905T012244Z-1490b353` ; il ne relit pas les 40 payloads.

## 2. Producteurs et filtre

Chaque shard `i=0..15` doit produire exactement 10 000 records, avec la graine `2026110700+i`. Le CURRICULUM décompressé doit avoir le SHA256 `319d174f4b548b1655aad4bb30d4c6dc86c08dd715c9c23f8b19ba1937dc0be1`.

```text
jass --gen-data-wdl 10000 shard-XX.jnnw 4 8 260 SEED
  --nnue CURRICULUM
  --wdl-zero-score --random-open-plies 8
  --explore-eps 8 --explore-decay-plies 60
  --pair-openings --drop-plycap
```

La recette impose profondeur d'évaluation 4, profondeur de jeu 8 et plafond de 260 plies. Chaque fichier brut doit faire `8+38*10000=380008` octets, sans octet surnuméraire. Aucun shard court n'est compensé par un autre. Les cibles WDL brutes peuvent être non nulles ; le sélecteur n'a jamais accès à ces fichiers.

Le launcher séparé `adaptive_sibling_b2_source_launcher.py` doit prouver une barrière de seize enfants directs vivants, avec PID, PPID et starttime `/proc`, avant libération. Chaque enfant fait ensuite `exec` du producteur. Le reçu vérifie l'exécutable résolu, son SHA et l'argv après `exec`, attend chaque PID exact et exige les seize sorties réussies. Les délais opérationnels sont explicites ; ils ne changent aucun paramètre scientifique. Chaque producteur et filtre possède un groupe de processus distinct. Une interruption SIGTERM/SIGINT ou un timeout déclenche un arrêt borné du groupe et de ses descendants, puis la récolte du processus direct. Un descendant restant invalide le lancement.

L'environnement enfant prévu est exactement vide (`{}`, `transmitted_names=[]`) ; les exécutables sont invoqués par chemin absolu. Il ne contient aucun nom `JASS_*`, y compris une variable vide. Les dix noms audités sont listés dans le contrat. Le producteur n'active aucune EGDB implicite. Le launcher calcule les hashes des binaires, du CURRICULUM, du build, des logs et des fichiers bruts et les publie dans le manifeste. Le sélecteur valide le schéma et les liaisons internes déclarées, authentifie les bytes des triples filtrés et des exclusions, puis publie le SHA du manifeste reçu. Il n'a accès ni aux binaires, ni au CURRICULUM, ni aux fichiers bruts ou logs : leur authentification matérielle, ainsi que celle du manifeste scellé, reste une obligation du wrapper avant le teacher.

Le filtre existant `jass_scan_ceiling_parent_filter` s'exécute pour chaque shard avec les bornes `9 40 2 16`. Il consulte seulement board/STM, émet des cibles nulles et conserve le `source_row_index` brut. Le manifeste associe exactement les seize triples JNNW filtré/TSV/report à leur shard, graine et SHA source.

## 3. Sélection déterministe

Le module offline `adaptive_sibling_b2_select.py` ne lance ni producteur, ni teacher, ni recherche. Il ne reçoit que les fichiers filtrés à cible nulle et les reçus autorisés.

| Cellules | Pièces | Effectif retenu par STM |
|---|---:|---:|
| P0_stm0, P0_stm1 | 30–40 | 500 |
| P1_stm0, P1_stm1 | 20–29 | 500 |
| P2_stm0, P2_stm1 | 12–19 | 500 |
| P3_stm0, P3_stm1 | 9–11 | 500 |

La classe canonique est le minimum entre l'identité exacte et sa rotation à 180 degrés avec échange des couleurs et inversion du STM. Les exclusions précèdent la déduplication et le prélèvement. Dans chaque classe restante, le représentant est l'occurrence observée minimale selon `(raw_fingerprint, source_shard, source_row_index)`. La cellule utilise le STM de ce représentant, sans fabriquer une orientation.

La clé est `SHA256(UTF8("2026110716:" + canonical_fingerprint))`, sans autre préfixe ou terminateur, puis le fingerprint canonique ASCII pour départager une collision. Chaque cellule fournit ses 500 premières clés ; une cellule insuffisante échoue, sans top-up. Les 4 000 retenus sont ensuite retriés globalement par cette même clé et reçoivent les identifiants `0..3999`.

Les permutations autorisées déplacent des tuples JNNW filtré/TSV alignés en conservant shard et index brut. Elles ne renumérotent pas la provenance brute. Un désalignement JNNW/TSV, un champ supplémentaire, un score/cible non nul, une incohérence d'identité, de taille, de hash ou de compteur échoue avant publication.

La CLI produit `parents.jnnw`, `parents.tsv` et un rapport canonique. Les sorties et temporaires doivent être distincts de toutes les entrées et absents. Les fichiers temporaires sont relus avant publication. Le rapport scelle aussi les bytes logiques de l'identité ordonnée : un fingerprint canonique ASCII par ligne, avec LF final, dans l'ordre des parents. Le wrapper final devra matérialiser ce fichier et vérifier son SHA, sa taille et ses 4 000 lignes avant le teacher.

## 4. Adaptateur full teacher

`adaptive_sibling_b2_teacher_source.py` génère une traduction temporaire depuis la source historique épinglée. Il conserve les 43 colonnes, les trois budgets `5000/50000/200000`, book OFF, un thread et les limites de nœuds exactes. Chaque appel construit un nouvel `Engine`, y compris pour les siblings immédiatement exacts. Aucun objet Engine ou TT ne traverse budget ou sibling.

Les compteurs observés doivent donner, par shard puis au total :

```text
fresh_engine_each_search = true
engine_constructions = 3 * emitted_siblings
cheap_searches = screen_searches = teacher_searches = emitted_siblings
```

Le teacher refuse tout environnement `JASS_*`. Sa TB obligatoire est configurée explicitement par build `JASS_EGDB` et arguments `egdb_dir, cache=256`, puis vérifiée disponible. L'absence des variables d'environnement ne constitue donc pas une désactivation de la TB. Avant son lancement, `verify-selection` vérifie le rapport de sélection authentifié et les bytes des parents sélectionnés.

La fusion des rapports ne remplace pas la fusion des payloads. Le futur merger doit vérifier les seize couples `children.jnnw/groups.tsv`, les parents exacts `0..3999`, les associations de shards, les cardinalités et le rebasing des indices de lignes locaux. Ce travail reste une dépendance explicite.

## 5. Identité sémantique et limites des 43 colonnes

Le movegen et le teacher dédupliquent déjà les actions sur l'ensemble des cases capturées ; aucun chemin géométrique équivalent ne reçoit de poids supplémentaire. Le TSV omet toutefois cet ensemble. Deux coups peuvent partager from/to/nombre de captures tout en retirant des ensembles différents : les colonnes seules ne suffisent pas à les identifier complètement.

Avant la confirmation, le merger doit rapprocher parent JNNW, ligne TSV et enfant JNNW, reconstruire l'ensemble capturé, contrôler la transition parent/enfant et l'unicité de l'identité complète, puis publier les compteurs et hashes correspondants. Les contrôles de légalité doivent préciser leur preuve ; une simple différence de bitboards ne prouve pas à elle seule qu'un mouvement est légal. La limite historique B1 `captured_square_bitboard_compared=false` reste inchangée.

## 6. Validation et dépendances avant toute fraîcheur

La suite finale sélecteur/launcher compte 31 tests : 31 réussis sous WSL en revue indépendante avec `ResourceWarning` fatal ; sous Windows, 22 réussis et neuf tests Linux ignorés. Elle couvre hash golden, quotas, exclusions, représentants, permutations, schémas, cibles nulles, overflow, reçus et alias. Les stubs Linux exercent une vraie barrière de seize processus, les deadlines, SIGTERM pendant producteur et filtre, l'arrêt des groupes et descendants, ainsi que le refus d'une mutation des bytes bruts pendant le filtrage. Aucun vrai `jass` n'a été exécuté. La revue finale ne laisse aucun P1/P2.

L'adaptateur teacher final a été vérifié par une suite de 20 tests en revue indépendante : 19 réussis et un test de compilation ignoré faute de compilateur Windows (6,467 s). La compilation syntaxique indépendante sous WSL, GCC 13.3, `-std=c++20 -DJASS_EGDB=1 -fsyntax-only`, réussit avec la source rendue SHA `3f9a1e65a769db9478b0a376996670dd8b6662f34f1007ebfff5c1c38e42ffd3` (23 035 octets). Aucun lien natif ni smoke avec le vrai CURRICULUM et une EGDB authentifiée n'est encore réalisé. Les sorties directes du binaire teacher doivent être protégées par son wrapper ; le launcher réel, la fusion des payloads, le readout riche et son ledger doivent également être validés. Le [preflight statistique 1774](L3_ADAPTIVE_SHADOW_B2_STATISTICAL_PREFLIGHT_V1_20260905.md) ne ferme pas ces dépendances.

Une erreur de contrat, de support, de hash, de processus ou de fichier arrête la cohorte ; elle ne déclenche ni complément, ni changement de graine/quota/budget, ni interprétation scientifique positive. L'ensemble de l'implémentation et le préenregistrement final doivent être revus et intégrés avant toute nouvelle cohorte. `CURRICULUM` reste champion ; aucune promotion ni bake automatique.
