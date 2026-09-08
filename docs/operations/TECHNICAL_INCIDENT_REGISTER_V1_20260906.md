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
| TI-012 | 1834, B3 fresh exclusion preparation | stage exit 2 after authenticated upstream fetches, before exclusion artefacts | the B3 exclusion consumer parsed the generic `fetch_result_files.py --report` output with `read_canonical_json()`, but the fetcher intentionally serializes its semantic report as indented JSON | generic authenticated fetch reports are validated semantically by identity/state fields; compact canonical-byte equality is required only for artefacts whose contract explicitly declares canonical serialization | `B3_EXCLUSION_FETCH_RECEIPT_JSON_INCIDENT_1834_20260906.md`, Jass #815; rerun 1835 attempt `20260906T134208Z-c553a572` PASS exit 0, combined_count=227317, component_overlap=0, union `b553939e8ded3ab31d121e40b2be9cfa1012168bf01835f692b59a60815d9ecb`, manifest `f734de99761b7a3ee7ddb107de3d678fa29eb7e39a11708b6a8c8bbbe700cc0c`; PR #820 | CLOSED |
| TI-013 | 1838, B3 fresh adaptive teacher | fresh teacher stage exit 2 after authenticated 1837 source retrieval, before required teacher outputs and without a scientific verdict | the fresh-teacher consumer required undeclared `selection.selected` and `selection.cell_quota` fields, while the sealed B2-derived source publication contract exposes total population as `selection.parents` and the frozen quota through the exact eight `selection.cells` counts | fresh-teacher source authentication must consume the actual sealed publication schema: `selection.parents==4000`, exactly eight cell counts all equal to 500, `forbidden_overlap==0`, and `target_blind==true`; no undeclared alias field may be invented by a consumer or its test fixture | `B3_FRESH_TEACHER_PUBLICATION_CONTRACT_INCIDENT_1838_20260906.md`; Jass #825; rerun 1841 attempt `20260906T154029Z-299779c0` PASS exit 0, 4000 parents, 38053 rows, verdict `B3_FRESH_ADAPTIVE_TEACHER_COMPLETE_V1`, renderer `a5f77f92abc7e77a8488c2c4751d71608d90cba04829a44f7c434138cb766d8f`, reference_audit_reads=0, full_ladder_backfill=false; PR #826 | CLOSED |
| TI-014 | 1846/1847, D1 WDL+listwise runtime | both stages exited 1 after about five minutes with inputs_authenticated=true, outputs_authenticated=false, no template RESULTS/logs and no scientific verdict | run_experiment_stage.py intentionally sanitizes the stage environment and does not propagate outer EXPECTED_CODE_SHA; D1 v1/v2 required ${EXPECTED_CODE_SHA:?} before installing traps, so the shell exited immediately on entry to EXECUTE | stage templates must consume only runner-owned stage variables or reconstruct defense-in-depth provenance from JASS_STAGE_SPEC; D1 must also retain the exact historical CURRENT_2M split 1800796/199204 and must never confuse bootstrap replication count 200000 with holdout rows | failed 1846 attempt 20260906T204702Z-2da8293b and 1847 attempt 20260906T211833Z-91414e25; run_experiment_stage.py build_command sanitized env; D1 v3 entrypoint + test_d1_stage_env_recovery.py; D1_STAGE_ENV_RECOVERY_1846_1847_20260906.md; PR #833; rerun 1849 attempt `20260906T222203Z-08fd187a` PASS exit 0 with authenticated outputs and terminal scientific readout | CLOSED |
| TI-015 | 1856, D3 runtime equal-node gate | stage exited 1 before the D3 equal-node start marker, with inputs authenticated, outputs unauthenticated and no scientific verdict | the stage preregistration guard searched for the non-existent literal `20,000`, while the frozen merged preregistration states the equal-node budget as `20000 nodes per move each arm` | runtime preregistration guards must match the exact merged preregistration bytes; recovery may correct only the guard/assertion plumbing, must fail closed on anchor drift, and may never edit frozen scientific constants or the preregistration | failed 1856 attempt `20260907T153211Z-9562f7e0`; PR #848; repaired rerun 1857 attempt `20260907T155344Z-fcdcd217` PASS exit 0 with authenticated outputs and full frozen equal-node execution; terminal scientific verdict `D3_RUNTIME_EQUAL_NODE_NOT_ESTABLISHED_V1`; PR #849 | CLOSED |
| TI-016 | 1858, D3 runtime terminal autopsy | read-only autopsy exited technically during authenticated source retrieval, before any scientific readout, with 0 games / 0 searches / 0 fits | the consumer generated shard ids with `seq -w 0 7`, which emits `0..7` for this range, while the sealed producer contract publishes exact directories `s00..s07` | consumers of sealed sharded publications must use the producer's exact shard identifiers; the D3 autopsy stage must use literal `00 01 02 03 04 05 06 07` for both fetch and analysis loops and must fail regression coverage if width-sensitive generation returns | failed attempt `20260907T162007Z-e42764d6`; PR #851; immutable recovery `cpx62-1860-l3-decision-math-d3-runtime-terminal-autopsy-recovery-requeue-v1` attempt `20260907T164613Z-0beb8796` PASS exit 0 with authenticated terminal autopsy publication; `D3_RUNTIME_TERMINAL_AUTOPSY_COMPLETE_V1`; classification `BROAD_EQUAL_NODE_SEARCH_EFFICIENCY_DEGRADATION`; PR #853 | CLOSED |
| TI-017 | D4 search-utility offline attempt 1861 | stage aborted during fresh-root-generation after authenticated inputs, before D4 root selection/teacher/fit, with no scientific verdict | `--gen-opening-pool` writes a `# count=...` metadata header plus exactly 30000 FEN payload rows, while the stage cardinality guard used `grep -cve '^[[:space:]]*$'` and therefore counted 30001 non-empty lines | cardinality checks on generated FEN pools must count payload rows only and ignore blank/comment metadata lines; recovery patching must apply exactly once and fail closed on source drift | failed attempt `20260907T175103Z-55416934`; generator source emits `# count=` header; recovery wrapper uses comment-aware `grep -cvE '^[[:space:]]*(#\|$)'`; regression test `jobs/tests/test_d4_root_cardinality_recovery.py`; PR #857 | MITIGATED — terminal recovery proof pending |
| TI-018 | D4 offline example-support terminal publication after 1862 | all 16 teacher shards and the example-prepare report were produced, but runner exited 4 with no scientific verdict | the frozen prepare CLI intentionally returns rc=4 for support INVALID; the stage attempted to capture it with `set +e`, but the installed Bash ERR trap still fires for a failing simple command and exits before the intended `prep_rc==4` publication branch | expected nonzero scientific/status return codes must be captured in an `if command; then ...; else rc=$?; fi` conditional or with ERR trap explicitly disabled; `set +e` alone is not a safe ERR-trap suppression mechanism | attempt `20260907T182914Z-1c779cc8` exit 4; artifacts include all 16 teacher reports, `d4-teacher-aggregate.json`, and `d4-example-prepare.json`; source prepare CLI returns 4 iff support is insufficient; recovery stage authenticates failed source and performs no new science; PR #859 | MITIGATED — terminal recovery readout pending |
| TI-019 | Scan-oracle Gate0 exploratory J1-J6 screen | stage exited 1 after J1/J2 completed and J3 emitted its 512-row TSV but before J3 report/readout | the scorer treated zero observed arm activation as a process-fatal condition; J3 had no single-reply extension event on the frozen 512-parent cohort | absence of treatment activation on a screening cohort is a scientific/support result and must not abort unrelated arms; it should be reported as not exercised/non-survivor | 1865 sealed artefacts contain J1/J2 TSV+report+readout and J3 TSV only; scorer calls assert_activation after all 512 searches and before report write; PR #863 | MITIGATED — partial recovery reuses J1/J2 and reruns J3-J6 with nonfatal activation accounting |
| TI-020 | ED1 1873 / 20260908T140143Z-a3ac3cdc; deterministic recovery 1874 / 20260908T161858Z-941faa2d | TECHNICAL: original ED1 wrapper exited before cohort authentication due to an OpenMP-contaminated CPU probe; no scientific verdict was produced by 1873. | OMP_NUM_THREADS=1 was exported before asserting nproc==16. GNU nproc observes OpenMP overrides. The repaired probe removes only OMP_NUM_THREADS and OMP_THREAD_LIMIT in its subprocess while retaining numeric caps. | Require cpx62 with 16 available CPUs without using nproc --all; preserve one-thread numeric caps, pinned clean code, ED1 data identities, labels, budgets, thresholds and information barriers. | Jass #870 merged as 941faa2df22c08b24cec45694d3277bd4407c0fc. jass-control/status/cpx62-1874-l3-ed1-partial-order-audit-openmp-recovery-v1.json: attempt 20260908T161858Z-941faa2d, completed exit 0 at 2026-09-08T16:24:13Z; label seal, ed1-readout.json and ED1_PARTIAL_ORDER_LABEL_SIGNAL_V1 published. Terminal rerun proves the unchanged resource guard and durable recovery.; PR #871 | CLOSED — terminal deterministic recovery 1874 authenticated |
| TI-021 | ED2-P0 1875 / 20260908T171140Z-bc30d685 and preparation of ED2 paired learner | TECHNICAL observability blocker: published 1875 record remains its initial running snapshot without recent phase/heartbeat/terminal evidence. Source inspection also identifies entire repository/build scratch included in result publication. | Confirmed code-level exposure: ED2 finalizers retain work/src and work/build, while runner_v3_store inventories and Rclone-copies/checks the entire run directory before the terminal marker; runner_v3 reaps/publishes terminal status only afterward. This can produce disproportionate publication work. Attribution of 1875's current delay to this mechanism remains unconfirmed; no current host phase/PID evidence was obtained. | Retain scientific data, models, seals, inputs, logs and native binary hashes; remove only this attempt's reproducible source/build scratch using strict path guards before publication. Never alter the running pinned attempt or history. No training before authenticated P0 READY, exact source and measured cost gates; stale running is not live progress. | P0 status blob 961a29fe227a80213ab2cbbbe53d0167c89f1c4b, attempt 20260908T171140Z-bc30d685. Source at bc30d685: jobs/templates/l3-ed2-data-teacher-preflight-v1.sh finalize, infra/runner_v3_store.py inventory_files/RcloneResultStore.publish, infra/runner_v3.py reap_finished_job. Three local cleanup preservation/path tests pass. P0 current phase and remote cleanup/terminal proof pending.; PR #873 | MITIGATED FOR FUTURE ED2 RUNS — P0 phase/terminal and remote cleanup proof pending |
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
