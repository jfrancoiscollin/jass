# Jass MegaCorpus v1 — sélection P2 et smoke fit reproductible

Date : 2026-08-14
Statut : préenregistré avant tout fit MegaCorpus et avant toute lecture de force.

## Décision d'inclusion P2

Le premier corpus entraînable n'est pas un mélange opportuniste de tous les
objets trouvés par P0. Il utilise une seule strate historique dont la provenance
et le contrat de génération sont déjà authentifiables :

- `home-1044-l3-pure-hard-replay-large-source-v1`, tentative
  `20260729T070032Z-477da64d` ;
- artefacts bruts `uniform.jnnw.gz` et `uniform.jsm.gz`, 40 000 000 lignes ;
- self-play général UNIFORM post-correctif, parent TURNOVER, jeu d8, label d4,
  `random-open-plies=8`, `explore-eps=8`, `explore-decay-plies=60`, ouvertures
  appariées et RNG séparés ;
- aucun TOPK, teacher externe, Scan, oracle, EGDB ou frozen set.

Le mot `hard-replay` dans le job décrit la destination historique de cette
source, pas sa distribution. L'artefact retenu est le flux UNIFORM brut publié
avant tout mining spécialiste. Son certificat de génération doit confirmer
`policy.name=uniform`, `topk_ranked_plies=0`,
`external_teacher_inputs=0` et le verdict source attendu.

TURNOVER 2M reste le corpus Current de l'expérience causale ultérieure, mais il
n'entre pas dans ce Mega smoke : il est composé de positions pré-correctif et
porte le biais de sélection connu des parties nulles manquantes. Les corpus
TOPK/hard, teachers, dérivés, snapshots non restaurés et runs non authentifiés
restent en quarantaine.

## Matérialisation

Pour borner le premier coût sans échantillonner des positions isolées, on garde
les parties dont le hash déterministe satisfait `hash % 10 == 0`, seed
`20260814`. Le volume attendu est voisin de 4 M lignes, mais aucun compte exact
n'est imposé a posteriori : toutes les parties sélectionnées restent entières.

Le split est ensuite déterministe par ouverture (`holdout_mod=10`, seed
`577215`) et l'ordre de sortie est train puis holdout. Chaque ligne possède :

- `origin_source_id.npy` en `uint32` ;
- `origin_record_index.npy` en `uint64` ;
- une entrée de source immuable avec URI, job, tentative, code SHA, date,
  modèle générateur, paramètres de self-play et hashes bruts.

Les données et sidecars téléchargés sont vérifiés contre `_SUCCESS`,
`manifest.json`, `inventory.json` et `checksums.sha256`, puis contre les hashes
bruts du certificat scientifique. Le sidecar fusionné est JSM1 ; le JSM
original reste authentifié et immuable à son URI. Aucun champ JSM2 n'est
inventé.

## Reconstruction et smoke fit

Le binaire est compilé avec l'architecture L2LOW complète de 120 extras. Il
reconstruit le FEAT sur les lignes matérialisées, puis le builder conditionnel
produit `CONTEXT_30` avec folds disjoints par partie et holdout aveugle.

Le smoke fit utilise :

```text
--target external --loss logistic --exact-fold --tempo-stage
--prior-mean L2LOW --prior-decay 0
--l2 1e-5 --lbfgs-gtol 1e-4 --max-iter 25
```

Vingt-cinq itérations valident le chemin de données, la cible, l'architecture,
le prior et l'export PJTW ; la convergence n'est pas requise pour ce smoke. Le
job publie le corpus, la provenance, `context30`, le modèle, les hashes et les
rapports d'optimisation nécessaires pour rejouer le fit.

CPX ne sert plus de wheel NumPy 1.26.4 pour sa version de Python. Le job utilise
donc la pile NumPy/SciPy courante compatible, résolue une seule fois dans un
cache `/var/tmp` versionné et marqué READY. Les versions exactes sont publiées
avec le résultat ; PyTorch n'est ni installé ni requis par ce pipeline.

Le verdict `JASS_MEGACORPUS_SMOKE_FIT_READY` signifie uniquement qu'un fit
MegaCorpus reproductible est techniquement valide. Il ne constitue ni un gain
de force, ni une promotion. Aucun frozen set n'est lu et aucune continuation ou
promotion automatique n'est autorisée.
