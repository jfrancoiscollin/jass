# Jobs préparés — L3-PURE C0

Ces scripts matérialisent les deux bras appariés décrits dans
`docs/L3_PURE_PLAN.md` :

- `ccx33-l3-pure-c0-a-v1.sh` : contrôle, autojeu terminal-WDL pur ;
- `cpx62-l3-pure-c0-b-v1.sh` : même recette, avec 25 % de départs depuis la
  frontière auto-générée en G2 et G3.

Ils restent volontairement hors de `jobs/queue/`. Les merger ne lance aucun
calcul.

Le sizing complet est volontairement symétrique à 8 shards. À l'ancre mesurée
`0665` d10 (~230 positions gardées/min/shard), 500 k positions demandent environ
4 h 32 par génération, soit ~13 h 35 pour trois générations, auxquelles
s'ajoutent build, splits et fits : **ETA préliminaire 14–18 h par bras**. Cette
estimation doit être remplacée par une micro-calibration sur chaque box avant
soumission. Le timeout préparé est 21 600 s/shard (~1,3× l'ancre).

## Publication GitOps

Après merge de la PR moteur :

1. relever le SHA exact de `jass/develop` ;
2. faire une micro-sonde sur chaque box, publier `nproc`, rate et ETA recalculée ;
3. obtenir le go explicite JFC, puis injecter `FULL_RUN_APPROVED=1` dans les
   wrappers GitOps ;
4. copier les deux wrappers dans `jass-control/queue/pending/` ;
5. laisser le runner v3 figer son worktree sur le SHA ;
6. lancer les deux bras avec le même `BASE_SEED` ;
7. ne comparer conversion et force qu'après succès complet des deux manifests.

Le C0 produit des students G1–G3 et les corpus nécessaires à l'audit. Il ne
promet ni ne promeut automatiquement un champion. Une évaluation haut-N
appariée A-vs-B constitue l'étape suivante après revue de Claude Code.
