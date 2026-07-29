# L3-PURE hard replay causal — jobs préparés

Cette série implémente la PR 2 du mémo signal :

1. `l3-pure-hard-replay-preflight-v1.sh` construit et authentifie le catalogue
   hard de 1M records ;
2. `l3-pure-hard-replay-train-v1.sh` génère un million frais commun, assemble
   `UNIFORM_REPLAY` et `HARD_REPLAY`, puis fitte les deux bras.

Les wrappers numérotés ne sont volontairement pas figés ici. Ils seront créés
après le verdict terminal du gate TOPK3 afin d'authentifier :

- le parent effectivement baké ;
- le SHA de code fusionné ;
- le préfixe, la tentative et les hashes exacts du corpus historique retenu ;
- un identifiant HOME encore libre et non dupliqué.

Ordre obligatoire :

```text
TOPK3 succession terminale
→ éventuel bake humainement autorisé
→ preflight hard catalogue
→ revue du certificat et de la capacité
→ fit causal A/B
→ readout indépendant préenregistré
```

Les deux templates exigent `FULL_RUN_APPROVED=1`, `SCIENTIFIC_GO=1` et
`NO_AUTOMATIC_CONTINUATION=1`. Ils publient `promotion=false` et
`automatic_next_job=null`. Aucun job n'est queué par ce répertoire.
