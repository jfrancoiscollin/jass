# L3-PURE M0 repair — 2026-07-21

## Incidents

- `cpx62-0875-l3-pure-m0-coverage` a produit les neuf rapports de couverture puis a échoué dans l'agrégateur : celui-ci comparait l'espace d'entraînement color-foldé (`8 × 265721 = 2125768`) au nombre brut runtime (`4251528`).
- `cpx62-0876-l3-pure-m0-triangle` a échoué avant tout benchmark : le manifeste historique schema 1 de `ccx33-0790` ne contient pas `search_params`, bien que son fingerprint cinq clés soit revu et immuable.

## Réparation

- couverture validée dans l'espace canonique color-foldé, avec cohérence `visited / trained_buckets_total` ;
- compatibilité C0 limitée exactement au job `ccx33-0790-l3-pure-c0-a-v1` et au SHA `8fc4eacbb7d99edb5aadc9db7caeb93abc8c85a2` ;
- fingerprint C0 restauré uniquement depuis le contrat revu, avec SHA-256 `525bbdc8a5e6b4413b6dc2635206b16f3d6d64d6993407b83d4121c817145609` ;
- toute autre source sans fingerprint reste refusée ;
- erreurs des agrégateurs copiées dans `RESULTS.txt` et `logs.tar.gz` avant arrêt.

## Invariants

```text
training_records=0
m1_authorized=false
promotion_authorized=false
automatic_next_job=null
```

Les relances doivent réutiliser les préfixes immuables C0/P1 et être épinglées sur le SHA mergé exact.
