# Atlas EXACT / témoin Gen2 — ordre d'exécution

Préparé, **non soumis**. Les trois jobs doivent partager le même
`EXPECTED_CODE_SHA` revu.

1. `cpx62-1142-l3-scan-blind-spot-atlas-exact-v1.sh` — EXACT, build 8cf ;
2. `cpx62-1143-l3-scan-blind-spot-atlas-gen2-v1.sh` — Gen2, build 32cf ;
3. renseigner dans `cpx62-1144-l3-scan-blind-spot-differential-v1.sh` les deux
   préfixes R2 immuables produits, puis lancer le readout.

Les passes 1 et 2 sont dimensionnées par temps : 16 shards × 1 500 secondes,
en parallèle sur cpx62. `cpx62-1114` a terminé le même protocole en 27 minutes.
Le build/fetch Gen2 peut réduire son volume observé, mais pas augmenter son
budget scientifique ; compter environ 27–35 minutes par passe, puis moins de
5 minutes pour le readout. Total séquentiel attendu : environ 60–75 minutes.

Avant soumission : `bash -n` des trois wrappers et des deux templates, tests
Python ciblés, vérification de `nproc=16`, disque >3 Go, runtime Scan épinglé et
go explicite JFC sur ce sizing. Aucun job suivant n'est automatique.
