# MÉMO CODEX — Feuille de route qualité du signal pour Jass

> Date : 28 juillet 2026  
> Dépôt : `jfrancoiscollin/jass`  
> Branche cible : `develop`  
> Point de départ observé : `6dcc49d1ed3f9fb5d32d5de988eeb8059260d641`  
> Destinataire : Codex  
> Portée : documentation et planification uniquement. Aucun job, aucun bake et aucune promotion ne sont autorisés par ce document.

---

## 0. Instruction immédiate à Codex

Avant toute modification, lire dans cet ordre :

1. `CLAUDE.md` ;
2. `docs/L3_CURRENT.md` ;
3. `docs/L3_PURE_PLAN.md` ;
4. `docs/PROJECT_RESULTS.md` ;
5. `docs/experiments/L3_TOPK_CAUSAL_AB_SPEC_20260728.md` ;
6. `docs/L3_LINEAGE_ROLES_AND_MATURITY.md` ;
7. le présent mémo.

Puis vérifier le vrai HEAD de `develop`. Le SHA indiqué ci-dessus est seulement le point de départ observé lors de la rédaction.

Contraintes non négociables :

- ne rien queuer sur HOME, cpx62 ou ccx33 sans GO explicite de JFC ;
- ne pas baker ni promouvoir un modèle ;
- conserver `L3-PURE` autonome : aucun moteur externe, aucune partie humaine et aucun teacher externe dans son entraînement ;
- isoler un facteur scientifique à la fois ;
- terminer et lire le DOE causal `UNIFORM vs TOPK3` avant de supposer que Top-K est bénéfique ;
- traiter la loss holdout, la couverture et les normes de gradient comme des diagnostics, jamais comme des critères de sélection à la place de l’Elo indépendant.

Première action recommandée : préparer une PR data-only de hard-position mining v1, avec outil déterministe, fixtures, tests de non-fuite et manifeste, sans changement moteur et sans job long.

---

## 1. Contexte scientifique actuel

Le champion général courant est `TURNOVER`. Le résultat utile sur la mémoire n’est pas un ratio arbitraire : la dose intérieure établie dans la campagne actuelle est `50 pour cent frais / 50 pour cent mémoire`.

Le volume brut n’est pas un levier suffisant. Un candidat beaucoup plus volumineux a déjà perdu malgré une meilleure couverture et une meilleure loss holdout. Toute proposition doit donc tester la qualité du signal à volume et recette constants.

Jass entraîne une évaluation linéaire Scan-style avec objectif logistique WDL et banques milieu de partie / finale. Ce n’est pas un réseau policy-value. Conséquences :

- réordonner les lignes ne crée pas un curriculum sous L-BFGS full-batch convergé ;
- le Top-K de génération déplace la distribution des trajectoires, mais ne distille pas une policy ;
- une vraie distillation doit passer par des comparaisons de fratries, des cibles de valeur ou une sélection de corpus ;
- un warm-start seul ne constitue pas une mémoire ;
- une pondération par record change réellement l’objectif et doit être testée causalement.

---

## 2. Briques déjà présentes à réutiliser

### Données et replay

`tools/selfplay_frontier.py` fournit déjà :

- `merge` de shards JNNW/JSM1 avec namespaces ;
- `mix` pondéré exact et déterministe ;
- `split` groupé par `opening_id` ;
- `mine` de conversions réussies ou ratées, avec miroirs couleur et cibles remises à zéro ;
- `profile` de diversité, phases, matériel et conversion.

Le sidecar JSM1 aligne actuellement :

```text
game_id:u64, opening_id:u64, seeded:u8
```

Ne pas casser ce format. Toute métadonnée supplémentaire doit être optionnelle, versionnée et placée dans un sidecar distinct, sauf migration ascendante explicitement testée.

### Génération

`src/main.cpp --gen-data-wdl` prend déjà en charge notamment :

- `--seed-file` et `--seed-frac` ;
- `--explore-topk` et `--explore-margin` ;
- `--split-selfplay-rngs` ;
- `--pair-openings` ;
- `--drop-plycap` et `--drop-post-eps` ;
- profondeur de jeu par phase ;
- punisher asymétrique ;
- `--tb-relabel` ;
- `--sample-meta-out`.

Une grande partie de la plomberie du reverse self-play existe donc déjà.

### Entraînement

`pattern_jass/tools/train_stream.py` possède déjà :

- objectif WDL ;
- cible `value` via le champ `score` ;
- fit full-batch streamé ;
- warm-start ;
- prior séquentiel ;
- holdout exact ;
- hook interne `sw_all`, aujourd’hui non exposé proprement par la CLI.

`pattern_jass/tools/rank_finetune.py` possède déjà :

- loss de rang sur paires de fratries ;
- ancrage au champion ;
- fit chunké exact ;
- gardes POV, gradient et pairwise accuracy.

`jobs/templates/conversion-teacher-smoke-runner-v3.sh` et `docs/archives/MEMO_BOUCLE_AUTO_AMELIORATION.md` constituent déjà des bases pour les tracks teacher et self-plus-time.

---

## 3. Traduction correcte des idées pour Jass

| Idée | Traduction adaptée | Anti-pattern |
|---|---|---|
| Hard-position mining | sélectionner des positions difficiles, rares ou contradictoires comme replay ou seeds | score composite opaque dès la v1 |
| Replay buffer | catalogue de corpus immuables et mélange exact | gros fichier mutable sans provenance |
| Reverse self-play | repartir de positions difficiles avec cibles nulles et nouveau WDL terminal | ressusciter automatiquement l’ancienne frontière mobile |
| Curriculum | faire évoluer la composition des corpus ou des seeds entre étapes | seulement réordonner les lignes du fit |
| Distillation Top-K | fratries préférées ou cibles de valeur issues d’une recherche plus forte | appeler distillation le bruit Top-K de génération |
| Confidence weighting | poids selon stabilité ou accord mesuré, bornés et audités | utiliser `abs(score)` comme confiance |
| Multi-policy | mélange de générateurs concrets, versionnés et déjà validés | styles agressif ou défensif sans définition reproductible |
| Consensus | majorité de classements ou sélection par accord | moyenne brute de scores non calibrés |
| Méta-évaluation | blend PJTW statique avant tout routeur runtime | charger plusieurs modèles sans garde NPS |
| Population | petite population fit-only sur corpus commun | nombreuses lignées self-play sélectionnées sur le même pool |
| Teacher externe | track séparé avec licence et provenance | contaminer `L3-PURE` |

Aucun gain Elo ne doit être annoncé avant mesure.

---

## 4. Ordre de priorité recommandé

1. Finaliser le readout causal `UNIFORM vs TOPK3`.
2. Implémenter hard-position mining v1 en data-only.
3. Tester hard replay contre replay uniforme à dose `50/50` et volume constant.
4. Tester un reverse self-play one-shot avec contrôle apparié.
5. Exposer proprement les sample weights dans le trainer.
6. Construire un atlas objectif des angles morts.
7. Tester un blend PJTW statique.
8. Tester la distillation autonome par fratries et self-plus-time.
9. Assembler ensuite seulement multi-policy et curriculum.
10. Garder teacher externe et Turbo Dambase dans un track distinct.

---

## 5. WP0 — Terminer le DOE causal Top-K

Question primaire : à recette identique, `TOPK3` est-il plus fort que `UNIFORM` et redirige-t-il utilement la couverture ?

À publier :

- Elo et IC95 de `TOPK3 vs UNIFORM` ;
- W/D/L bruts par vue et additionnés ;
- couverture, Jaccard de buckets, masse déplacée et divergence de Jensen-Shannon ;
- coût de génération et débit ;
- invariants du split ;
- mise à jour de `docs/L3_CURRENT.md`, et de `docs/PROJECT_RESULTS.md` si une famille est close.

Aucun composant ultérieur ne doit considérer Top-K comme une source supérieure avant ce verdict.

---

## 6. WP1 — Hard-position mining v1

### Hypothèse

À volume constant, un replay de positions explicitement difficiles fournit davantage de signal utile qu’un échantillon uniforme du même historique.

### Signal v1 unique

```text
failed_conversion = avantage matériel observé, mais issue terminale non gagnante pour le camp avantagé
```

Ne pas ajouter en v1 : désaccord de profondeur, désaccord de modèles, rareté de buckets, surprise statique ou teacher externe.

### Implémentation

Préférence : étendre `tools/selfplay_frontier.py` avec une opération explicite `mine-hard`, à condition de garder un diff lisible. Sinon créer un outil dédié qui réutilise les lecteurs et écrivains existants sans dupliquer les formats.

Entrées minimales :

```text
--data SOURCE.jnnw
--meta SOURCE.jsm
--split-manifest SOURCE-split.json
--max-records N
--seed S
--signal failed_conversion
--one-per-game
--colour-mirror
```

Règles :

- miner exclusivement la partition train ;
- une position maximum par jeu et par classe ;
- quotas déterministes par phase, marge matérielle et nombre de pièces ;
- déduplication par position canonique ;
- conserver le WDL original dans la sortie replay ;
- produire aussi une sortie seeds avec `score=0` et `wdl=0` ;
- ne jamais utiliser le holdout pour définir seuils, quotas ou positions.

Sorties :

```text
hard-replay.jnnw
hard-replay.jsm
hard-seeds.jnnw
hard-mining-manifest.json
```

Le manifeste doit inclure : hashes des entrées et sorties, code SHA, signal, split, candidats et sélection par catégorie, jeux et ouvertures uniques, déduplications, WDL, phase, pièces, matériel, vérification des cibles nulles et `external_teacher_inputs=0`.

Tests obligatoires :

- alignement JNNW/JSM1 ;
- aucune fuite du holdout ;
- déterminisme bit-à-bit ;
- one-per-game ;
- miroirs corrects ;
- conservation des cibles replay ;
- nullification des cibles seeds ;
- échec fermé sur fichier tronqué, count divergent ou manifeste incompatible.

---

## 7. WP2 — Hard replay causal à dose validée

Le buffer doit rester un catalogue logique de corpus immuables dans l’object store. Chaque source doit conserver au minimum : job, tentative, code SHA, parent SHA, hashes data/meta, fingerprint de policy, profondeur, mode de label, canari WDL, records, jeux, ouvertures et date.

DOE recommandé depuis le même parent :

```text
CONTROL   = 1 M frais + 1 M replay historique uniforme
TREATMENT = 1 M frais + 1 M replay historique hard-selected
```

Tout le reste reste identique : source historique admissible, moitié fraîche, parent, Q00, d8, L2, warm-start, budget de fit et holdout commun construit avant le mining.

Readout primaire : `HARD_REPLAY vs UNIFORM_REPLAY`, vues Q00 et native, pool neuf et haut-N.

Secondaires : conversion P1-P4, couverture, densité, diversité, duplication, coût de sélection et loss holdout commune comme diagnostic seulement.

---

## 8. WP3 — Reverse self-play contrôlé

Comparer :

```text
CONTROL   = self-play avec seeds aléatoires appariées
TREATMENT = self-play avec hard seeds issues des mêmes sources
```

Les seeds contrôle doivent être appariées sur phase, bande de pièces, strate matérielle, source temporelle, cardinalité et fraction d’utilisation.

`SEED_FRAC` doit être explicite et préenregistré après micro-sonde de rendement.

Pour un véritable rewind, JSM1 ne suffit pas car il ne contient pas le ply. Ajouter plus tard un sidecar optionnel et versionné, par exemple `JSP1` avec `ply:u16`, sans modifier JSM1.

Un gain démontrerait l’utilité des états de départ ciblés, pas automatiquement la validité générale de la formule de hardness.

---

## 9. WP4 — Pondération par confiance ou difficulté

Distinguer :

- confidence : fiabilité du label ou de l’ordre teacher ;
- hardness : difficulté pour le student.

Extension minimale de `train_stream.py` :

```text
--sample-weights PATH.npy
--weight-normalization mean-train-1
--weight-min X
--weight-max Y
--weights-report PATH.json
```

Contraintes : float32, longueur exacte, valeurs finies et positives, normalisation sur train seulement, holdout évalué sans pondération, passage au hook `sw_all`, rapport min/max/quantiles et ESS.

Tests : poids tous à 1 identiques au chemin historique, gradient chunké contre full-batch, erreurs sur NaN/zéro/négatif/longueur, holdout non pondéré et déterminisme.

Premier DOE : mêmes records et même split, seule la formule de poids change. Ne pas combiner pondération et oversampling au premier test.

---

## 10. WP5 — Atlas des angles morts

Créer un rapport versionné avec catégories objectives : phase, strate P1-P4, dames par camp, capture obligatoire ou calme, mobilité, asymétrie, distance à promotion, seeded ou standard.

Les motifs tels que verrou, sacrifice, opposition ou encerclement ne doivent être ajoutés qu’avec définition déterministe, witnesses et tests.

Publier par tag : records, jeux, ouvertures, WDL diagnostic, conversion diagnostic, couverture, densité, désaccord modèles, instabilité de profondeur et surprise terminale.

Les probes doivent être fixes, hashés et versionnés. Un probe externe peut servir au diagnostic mais ne doit jamais revenir dans `L3-PURE`.

---

## 11. WP6 — Distillation de recherche et consensus

Le Top-K de génération n’est pas une distillation. La voie préférée est la comparaison de fratries avec `rank_finetune.py`.

MVP :

```text
meilleur enfant teacher > meilleur compétiteur admissible
```

Teacher autonome : le même moteur avec davantage de temps ou profondeur. Vérifier d’abord le headroom réel. Une paire maximum par parent en v1, marge minimale préenregistrée, split par parent ou ouverture, ancrage au champion et readout Elo indépendant.

Pour un consensus A/B/C : garder les paires où la majorité ou l’unanimité donne le même ordre. Publier taux d’accord et taux de rejet. Ne pas moyenner les scores bruts sans calibration.

Une variante disagreement mining peut sélectionner les désaccords comme hard positions, mais elle constitue une expérience distincte.

Relire les campagnes historiques de deep relabel avant toute nouvelle cible `value`, afin de ne pas répéter un axe déjà testé à l’identique.

---

## 12. WP7 — Curriculum adapté à Jass

Le curriculum doit agir sur la composition des corpus ou des seeds entre étapes, pas sur l’ordre des lignes du fit.

Exemples de leviers : fraction de hard replay, fraction de hard seeds, quotas par phase et matériel, budget teacher pour les fratries.

Règles :

- chaque composant doit d’abord gagner isolément ;
- chaque transition possède un parent figé et un gate ;
- aucune continuation automatique ;
- deux étapes sans pente de force positive ferment la recette testée.

---

## 13. WP8 — Multi-policy contrôlé

Les policies doivent être concrètes et reproductibles :

- `Q00_UNIFORM` ;
- `Q00_TOPK3` seulement après validation ;
- `ASYM_PUNISHER` avec paramètres épinglés ;
- `HARD_SEEDED` avec source et seed fraction épinglées ;
- profondeur par phase seulement si déjà validée.

Générer, authentifier et profiler chaque source séparément, puis mélanger avec `selfplay_frontier.py mix` à quotas exacts.

Premier DOE recommandé : contrôle 100 pour cent source de référence contre traitement 75 pour cent référence et 25 pour cent source candidate. Un mix gagnant prouve une complémentarité à cette dose, pas la force intrinsèque de la source candidate.

---

## 14. WP9 — Méta-évaluation hybride

### Priorité A : blend statique PJTW

Créer `tools/blend_pjtw.py` avec validation des headers, géométrie, flags, nombre de patterns, extras et conventions de phase. Déquantifier, moyenner, requantifier de façon déterministe et contrôler les saturations.

Tester sur probe :

```text
eval_static(BLEND, p) proche de alpha eval_static(A, p) + beta eval_static(B, p)
```

Avantages : un seul fichier de poids, aucun coût NPS supplémentaire et aucune logique runtime.

Une petite grille d’alphas peut servir à éliminer les grosses régressions, mais le gagnant doit être évalué sur un pool final jamais utilisé pour choisir l’alpha.

### Ensuite seulement

- blend distinct MG/EG ;
- éventuellement patterns/extras ;
- routeur dynamique uniquement si un spécialiste a une compétence établie et bornée, avec garde NPS, activation bornée et non-régression généraliste.

---

## 15. WP10 — Population training à coût maîtrisé

Commencer fit-only sur un corpus commun immuable. Faire varier un petit ensemble préenregistré : seuil de mining, borne de poids, dose hard replay, alpha de blend ou force d’ancrage rank.

Maximum 3 à 5 bras. Utiliser un écran bas-N seulement pour éliminer les fortes régressions, puis une finale haut-N sur un pool neuf.

Le rapport doit déclarer le nombre de candidats, les pools utilisés, la règle de sélection et l’incertitude après sélection.

Une population de self-play n’est justifiée qu’après démonstration d’un levier fit-only reproductible.

---

## 16. WP11 — Teacher externe et Turbo Dambase

Créer ou prolonger un track séparé tel que `L3-TEACHER-LAB`. Il ne doit jamais être présenté comme `L3-PURE`.

Pour un ensemble de moteurs, préférer : paires de fratries avec accord, classement majoritaire, cible de valeur calibrée et désaccords conservés pour diagnostic.

Chaque sortie teacher doit enregistrer : nom, version ou SHA, licence, budget de recherche, paramètres, calibration, source des positions, règle d’accord, taux de rejet et hashes.

Turbo Dambase doit d’abord servir au diagnostic : export documenté, replay légal avec Jass, déduplication, pools d’ouvertures externes, benchmark de positions réelles et divergences Jass/humain ou Jass/teacher.

Les coups humains ne sont pas automatiquement des meilleurs coups. Un entraînement teacher-annoté n’est autorisé qu’après vérification de licence et dans le track externe.

Ne jamais committer ni redistribuer la base brute. Conserver preuve d’achat, version et conditions d’utilisation.

---

## 17. Séquence de PR recommandée

### PR 1 — Hard mining v1, data-only

- spécification ;
- outil déterministe ;
- fixtures et tests ;
- manifeste ;
- aucune queue ;
- aucune modification moteur.

### PR 2 — Assemblage causal hard replay

- holdout commun ;
- template runner-v3 paramétré ;
- certificat causal ;
- micro-smoke seulement ;
- lancement interdit sans GO.

### PR 3 — Reverse seeds contrôlé

- contrôle matched-random ;
- source authentifiée ;
- `SEED_FRAC` explicite ;
- aucun loop automatique.

### PR 4 — Sample weights

- CLI ;
- hook `sw_all` ;
- tests all-ones, chunk, full et holdout ;
- rapport ESS ;
- aucune formule activée par défaut.

### PR 5 — Blind-spot report v1

- taxonomie objective ;
- probes hashés ;
- JSON/CSV ;
- distinction diagnostics et gates.

### PR 6 — Blend PJTW

- blend global ;
- validation headers ;
- tests de linéarité statique ;
- aucun routeur runtime.

### PR 7 — Rank-distillation autonome

- headroom d’abord ;
- petit corpus de fratries ;
- fit rank ancré ;
- gate séparé.

### PR 8 — Multi-policy et curriculum

Assembler uniquement des composants déjà validés.

Teacher externe et Turbo Dambase restent dans une série séparée.

---

## 18. Contrat commun des outils et jobs

Chaque outil doit être déterministe à seed fixée, vérifier magic, taille, count et alignement, échouer fermé, produire un JSON versionné et trié, inclure les SHA256, ne jamais modifier une entrée, écrire par fichier temporaire puis rename atomique, avoir fixtures et round-trip, et fonctionner localement sans R2.

Chaque template de job doit suivre `CLAUDE.md`, authentifier code, parent et corpus, calibrer nproc/rate/timeout/ETA, utiliser des timeouts par shard, éviter `wait` nu avec monitor, publier le progress en heure française, préserver les checkpoints, traiter `n=0` comme échec et finir avec :

```text
promotion_authorized=false
automatic_next_job=null
```

---

## 19. Prompt prêt pour Codex

```text
Travaille dans le repo jfrancoiscollin/jass depuis develop.

Lis CLAUDE.md, docs/L3_CURRENT.md, docs/L3_PURE_PLAN.md,
docs/PROJECT_RESULTS.md, docs/experiments/L3_TOPK_CAUSAL_AB_SPEC_20260728.md,
docs/L3_LINEAGE_ROLES_AND_MATURITY.md et le présent mémo. Vérifie le vrai HEAD.

Objectif de la première PR uniquement : implémenter hard-position mining v1 en
mode data-only, sans queuer de job, sans changer le moteur et sans modifier la
recette active.

Réutilise les formats et helpers de tools/selfplay_frontier.py. Le signal v1 est
failed_conversion uniquement. Mine exclusivement la partition train, sélectionne
de manière déterministe, limite la corrélation par game_id, stratifie phase et
matériel, déduplique, puis produis hard-replay.jnnw avec JSM1, hard-seeds.jnnw
avec score et wdl à zéro, et un manifeste complet avec provenance et hashes.

Ne casse pas JSM1. N’ajoute pas encore de score composite, sample weights,
teacher externe, curriculum ou job long.

Ajoute des fixtures et tests couvrant alignement, non-fuite du holdout,
déterminisme bit-à-bit, one-per-game, miroirs, conservation ou nullification
des cibles, déduplication et échec fermé.

Ajoute une spécification du futur DOE causal : 1 M frais + 1 M replay uniforme
contre 1 M frais + 1 M replay hard-selected, mêmes sources, parent, split et fit,
holdout commun, readout haut-N indépendant, promotion false et aucune suite
automatique.

Avant de proposer la PR, exécute les tests ciblés, py_compile et git diff
--check. Donne la liste exacte des fichiers modifiés et des validations. Ne
lance rien sur HOME, cpx62 ou ccx33.
```

---

## 20. Résumé exécutable

```text
Top-K causal terminé
→ hard mining v1
→ hard replay 50/50 contre replay uniforme
→ reverse seeds contrôlé
→ sample weights et atlas d’angles morts
→ blend PJTW statique
→ distillation par fratries
→ multi-policy et curriculum seulement ensuite
→ teacher externe et Turbo dans un track séparé
```

Le premier levier rationnel n’est pas davantage de données, mais une meilleure sélection des mêmes données, testée causalement avec toutes les autres dimensions maintenues fixes.
