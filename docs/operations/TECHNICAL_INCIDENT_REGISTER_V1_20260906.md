# Jass — registre central des incidents techniques v1

Date de création : 2026-09-06

Statut : **registre opérationnel actif**.

Objectif : transformer chaque défaillance technique comprise en invariant durable, test de régression et, quand le risque dépend de données/runtime réels, en preflight obligatoire. Ce registre n'autorise aucun changement scientifique ; les seuils, cohortes, seeds, modèles et gates restent gouvernés par leurs preregistrations.

## Règle de capitalisation

Pour tout incident terminal ou quasi-terminal :

1. classer `TECHNICAL` vs `SCIENTIFIC` avant toute correction ;
2. publier la cause racine exacte, pas seulement le symptôme ;
3. exprimer la correction comme invariant de contrat ;
4. ajouter au minimum un test positif et un test fail-closed ;
5. ajouter un preflight target-data/runtime lorsque le synthétique ne peut pas couvrir le risque ;
6. conserver les side-effects scientifiques à zéro pendant la réparation ;
7. ne jamais modifier silencieusement une science gelée ;
8. après correction, relancer l'étape minimale qui prouve l'invariant avant le compute coûteux.

## Registre

> Cette table est générée depuis `TECHNICAL_INCIDENTS_V1.json`. Ne pas l'éditer à la main.

<!-- GENERATED_TECHNICAL_INCIDENT_TABLE_START -->
| ID | Job / contexte | Symptôme | Cause racine | Invariant / garde-fou durable | Preuve / couverture | Statut |
|---|---|---|---|---|---|---|
| TI-001 | 1806, dispatcher Level-3 | `exit 126` avant stage | le dispatcher exécutait directement un shell non exécutable | les stages shell sont invoqués explicitement par `/usr/bin/bash`, jamais par permission implicite | correction control #515 + rehearsal ultérieure verte | CLOSED |
| TI-002 | 1808, observabilité Level-3 | stage réel terminé mais état/résultats insuffisamment visibles dans control | divergence entre ownership `result` et `artifact` | chaque stage publie un status bridge déterministe et authentifie ses sorties requises | Jass #797 + rehearsals suivantes | CLOSED |
| TI-003 | 1823, isolation stage | environnement isolé cassait outils standards | `environment.inherit=[]` supprimait aussi `PATH`/`TMPDIR` nécessaires au runtime | `PATH` déterministe runner-owned ; `TMPDIR` runner-owned préservé, sans héritage ambiant arbitraire | Jass #798 + 1824 PASS | CLOSED |
| TI-004 | 1825, B2 recovery | `rclone.conf not found` / remote `r2` absent | capability object-store supprimée par isolation stage | R2 est une capability explicite ; seules les 5 variables `RCLONE_CONFIG_R2_*` documentées sont héritables ; secrets non déclarés interdits | `STAGE_OBJECT_STORE_CAPABILITY_INCIDENT_1825_20260906.md`, `test_run_experiment_stage_object_store.py`, Jass #800 | CLOSED |
| TI-005 | 1827, B2 target-data | `PROJECTION_BINDING_INVALID: full total must be positive` parent 1216 | producer et consumer X divergeaient sur un parent entièrement exact dont les recherches légitimes consomment 0 nœud | preflight target-data obligatoire avant bootstrap ; `full_nodes=0` autorisé uniquement avec `shadow_nodes=0`; support reste non nul au niveau cellule/global | `B2_EXACT_ZERO_COST_COMPAT_1827_20260906.md`, workflow `b2-exact-zero-cost-compat`, Jass #802/#803, 1830 PASS 4000/4000 | CLOSED |
| TI-006 | 1828, wrapper preflight v2 | stage `exit 1` avant diagnostic métier | script direct `python jobs/tools/...` sans bootstrap de racine repo dans `sys.path` | tout entrypoint Python exécutable directement doit se tester comme subprocess depuis le repo et initialiser son import path explicitement si nécessaire | Jass #804 ; 1830 PASS | CLOSED |
| TI-007 | 1829, terminal bundle B2 | `verified-historical.json` rejeté comme non-canonical | support JSON historique immuable utilisait une sérialisation legacy valide sémantiquement mais non canonique selon le consumer récent | compat de format limitée aux basenames legacy authentifiés ; bytes sources conservés ; aucune normalisation silencieuse de contenu | Jass #805 ; 1831 terminal PASS | CLOSED |
| TI-008 | 1797/1799, merge teacher B2 | king move rejeté avec `moving_king=1,promotes=1` | `Move.promotes` est un flag destination-rank, y compris pour un roi, tandis qu'un guard Python supposait l'inverse | nouveaux stages ne doivent pas reconstruire la sémantique de `promotes`; catalogue natif fait autorité ; compat legacy isolée et testée | `adaptive_sibling_b2_legacy_contract_compat.py` + tests | CLOSED |
| TI-009 | 1800/1801, publisher B2 | publisher exigeait artifact-dir vide mais wrapper y écrivait son reçu mécanique avant publication | collision ownership wrapper/publisher | `artifact_directory_contract=empty_or_runner_launch`; diagnostics mécaniques pré-publication vont dans result-dir, artefacts scientifiques restent owner du stage | 1801 PASS + contrat stage v1 | CLOSED |
| TI-010 | PR #807, B3 renderer pre-CPX | le renderer échoue avant génération sur l'anchor de schema C++ | l'adapter cherchait une chaîne JSON non échappée alors que le source C++ contient `\"...\"` dans un string literal | tout renderer source-to-source doit exercer le vrai CLI en CI et matcher les bytes/échappements exacts des anchors ; aucun fallback fuzzy/sed opportuniste | workflow `b3-real-adaptive-teacher`, tests renderer + direct CLI ; détecté avant CPX | CLOSED |
| TI-011 | 1832, B3 real adaptive parity | shard 11 abort `rc=-6`: `B2 teacher counter contract mismatch` avant tout verdict de parity | le renderer B3 remplaçait la boucle full-ladder B2 par la politique adaptative 100/60/2 mais conservait l'assertion B2 `q5=q50=q200=emitted` | B3 impose `q200<=q50<=q5<=emitted_siblings` et `engine_constructions=q5+q50+q200`; le renderer fail-closed si le contrat full-ladder B2 survit | `B3_ADAPTIVE_COUNTER_CONTRACT_INCIDENT_1832_20260906.md`, Jass #808, workflow B3 vert, control #529, rerun 1833 PASS exit 0, 4000 parents, mismatch_count=0, verdict `B3_REAL_ADAPTIVE_TEACHER_PARITY_ESTABLISHED_V1`; PR #812 | CLOSED |
| TI-012 | 1834, B3 fresh exclusion preparation | stage exit 2 after authenticated upstream fetches, before exclusion artefacts | the B3 exclusion consumer parsed the generic `fetch_result_files.py --report` output with `read_canonical_json()`, but the fetcher intentionally serializes its semantic report as indented JSON | generic authenticated fetch reports are validated semantically by identity/state fields; compact canonical-byte equality is required only for artefacts whose contract explicitly declares canonical serialization | `B3_EXCLUSION_FETCH_RECEIPT_JSON_INCIDENT_1834_20260906.md`, Jass #815, failed attempt `20260906T132605Z-e2762791`; corrected rerun 1835; PR #816 | MITIGATED — 1835 PENDING |
<!-- GENERATED_TECHNICAL_INCIDENT_TABLE_END -->

## Invariants transverses actifs

### A. Environnement

- aucun stage scientifique ne dépend d'un shell utilisateur implicite ;
- `PATH`, `TMPDIR` et capabilities externes sont runner-owned ou explicitement déclarées ;
- les secrets ne sont jamais hérités en bloc ;
- R2 utilise une allow-list fermée.

### B. Entrypoints

- tout outil CLI critique doit être exercé en CI via son mode d'invocation réel ;
- un test d'import module seul ne remplace pas un test `python path/to/tool.py ...` ;
- shell/Python/C++ sont lancés par un interpréteur/binaire explicite.

### C. Données et contrats

- tests synthétiques -> preflight target-data/runtime -> compute scientifique ;
- producer et consumer doivent être testés ensemble sur les vraies formes de données avant une étape coûteuse ;
- une incompatibilité de sérialisation ne peut pas être reclassée en résultat scientifique ;
- les compatibilités legacy sont isolées, byte-authenticated et interdites aux nouveaux contrats natifs.

### D. Publication / observabilité

- status, result et artifact ont des ownerships explicites ;
- un stage ne peut pas réussir si ses sorties required/nonempty ne sont pas authentifiées ;
- les failure classes doivent nommer le stage technique précis ;
- aucun retry ne doit masquer le job/attempt source.

## Politique pour B3 et la suite

À partir de B3, toute nouvelle stage doit satisfaire avant compute :

```text
CI contract
  -> CLI/subprocess rehearsal
  -> capability/environment preflight
  -> target-data admissibility quand applicable
  -> stage scientifique
```

Les incidents futurs sont enregistrés via `jobs/tools/technical_incident_register.py` ou via le bloc PR `JASS_TECHNICAL_INCIDENT`. La source canonique est `TECHNICAL_INCIDENTS_V1.json`; la table ci-dessus est régénérée automatiquement et la CI bloque toute dérive.
