# Atlas EXACT / témoin Gen2 — ordre d'exécution

Préparé, **non soumis**. Les trois jobs doivent partager le même
`EXPECTED_CODE_SHA` revu.

1. `home-1143-l3-scan-blind-spot-atlas-exact-v1.sh` — EXACT, build 8cf ;
2. `home-1144-l3-scan-blind-spot-atlas-gen2-v1.sh` — Gen2, build 32cf ;
3. renseigner dans `home-1145-l3-scan-blind-spot-differential-v1.sh` les deux
   préfixes R2 immuables produits, puis lancer le readout.

Les passes 1 et 2 sont dimensionnées par temps : 16 shards × 1 500 secondes,
en parallèle sur HOME (`nproc=16`, vérifié avant soumission). Le débit exact du
collecteur n'est pas transporté depuis cpx62 : il changera le volume observé,
pas le budget scientifique. Compter environ 30–40 minutes par passe avec
build/fetch, puis moins de 5 minutes pour le readout. Total séquentiel borné
attendu : environ 65–85 minutes.

Avant soumission : `bash -n` des trois wrappers et des deux templates, tests
Python ciblés, vérification de `nproc=16`, disque >3 Go, runtime Scan épinglé et
go explicite JFC sur ce sizing. Aucun job suivant n'est automatique.
