# L3-PURE hard replay causal — jobs préparés

Cette série implémente la PR 2 du mémo signal :

1. `l3-pure-hard-replay-preflight-v1.sh` construit et authentifie le catalogue
   hard de 1M records ;
2. `l3-pure-hard-replay-train-v1.sh` génère un million frais commun, assemble
   `UNIFORM_REPLAY` et `HARD_REPLAY`, puis fitte les deux bras.

Le gate terminal `home-1040` rejette TOPK3 (`0,47205`, `-19,44 Elo` contre
TURNOVER sur 10 000 parties). TURNOVER reste donc parent et le bras historique
admissible est `UNIFORM`. Le premier wrapper concret est :

```text
home-1042-l3-pure-hard-replay-preflight-uniform-v1
```

Il épingle :

- code `9ba51abe2c03cc9b157229f05c05c50bb289468f` ;
- source `home-1017`, tentative `20260728T123640Z-9e404854`, état `failed`
  mais corpus UNIFORM complet ;
- certificat `home-1021`, verdict
  `L3_PURE_TOPK_1017_FIT_INPUTS_AUTHENTICATED` ;
- dose hard exacte de 1 000 000, sans réduction post-hoc.

Résultat terminal : `home-1042` publie
`L3_PURE_HARD_REPLAY_CATALOGUE_INSUFFICIENT`. La capacité authentifiée est
58 908 records (29 454 positions canoniques miroirées) pour 1 000 000 requis.
Le mining est déterministe, mais `training_authorized=false` : le template de
fit reste préparé et **ne doit pas être instancié** avec ce certificat.

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
`automatic_next_job=null`. `home-1042` est data-only : aucun fit ne sera lancé
si son certificat ne publie pas
`L3_PURE_HARD_REPLAY_CATALOGUE_READY` avec `training_authorized=true`.

La réouverture choisie produit une source `UNIFORM` post-correctif de 40M
records sous :

```text
home-1044-l3-pure-hard-replay-large-source-v1
```

Le template `l3-pure-hard-replay-large-source-v1.sh` conserve strictement le
parent TURNOVER et la policy UNIFORM d8/d4 de `home-1017`, mais utilise des
graines fraîches disjointes. Les six producteurs HOME sont le plafond de
concurrence. La source publie ses hashes, son split et son canari, puis s'arrête
avec `automatic_next_job=null` ; le mining 1M restera un job séparé.
