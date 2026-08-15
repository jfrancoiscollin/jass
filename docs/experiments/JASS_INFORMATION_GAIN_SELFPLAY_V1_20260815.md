# Jass Information-Gain Self-Play v1 — protocole préenregistré

> **Statut :** expérience exploratoire préenregistrée. Aucun résultat de force ne doit être consulté avant le gel des corpus, des métriques de diversité et des bras de fit. Aucune promotion automatique.

## 1. Question scientifique

Le self-play itératif Jass semble produire l'essentiel de son signal dès la première génération puis saturer. L'hypothèse testée ici est que le facteur limitant n'est pas le volume brut mais l'information marginale : des générations verticales issues de leurs propres descendants deviennent fortement corrélées, alors que des bras indépendants repartant du même G0 avec des seeds différentes peuvent couvrir des régions différentes de l'espace des positions.

On teste donc :

- **H0** : à volume égal, plusieurs seeds indépendantes n'apportent pas plus d'information utile ni de force qu'un corpus plus gros issu d'un seul générateur / d'une lignée verticale ;
- **H1** : à volume égal, le pooling de bras indépendants augmente la couverture effective et conduit à un meilleur fit que les contrôles de volume et de compounding.

Le test primaire porte sur **indépendance + pooling**, pas sur un nouveau moteur, une nouvelle architecture ou une nouvelle cible.

## 2. Principe mathématique

Pour une politique/modèle `f`, le pipeline historique peut être vu comme un opérateur :

```text
f[t+1] = L(S(f[t]))
```

Aucune propriété du fit WDL ne garantit que cet opérateur soit strictement améliorant en force. Il peut approcher un point fixe lorsque le self-play et le fit reproduisent surtout la distribution déjà induite par `f[t]`.

L'expérience cherche donc à maximiser un proxy d'information conditionnelle :

```text
ΔI_i ≈ nouveauté(D_i | pool précédent) + divergence_distributionnelle(D_i, pool)
```

Ce proxy ne remplace jamais l'Elo. Il sert uniquement à décider si un pool multi-seed mérite d'être entraîné à grande échelle.

## 3. Invariants

Tous les bras primaires utilisent :

- le même code SHA ;
- le même moteur et les mêmes paramètres de recherche ;
- le même modèle de départ G0 ;
- les mêmes règles de génération, profondeur/budget, exploration, adjudication et ply cap ;
- la même distribution de positions de départ ;
- le même nombre de records par unité de calcul ;
- la même architecture de fit ;
- la même cible `context30` conditionnelle pour les candidats entraînés ;
- le même holdout et les mêmes gates de force.

**Le seul facteur du screen horizontal est la seed.** Aucun ancien corpus, teacher externe, Scan, EGDB ou replay n'entre dans l'expérience causale primaire.

## 4. Phase A — screen d'information, faible coût

Générer 10 corpus indépendants depuis exactement le même G0 :

```text
H01 = S(G0, seed_01)
H02 = S(G0, seed_02)
...
H10 = S(G0, seed_10)
```

Budget recommandé pour le premier screen : `100k–200k records` par bras. Les seeds sont fixées avant exécution et ne sont jamais remplacées sur la base d'un résultat.

Le script `jobs/tools/selfplay_information_gain.py` publie avant tout fit :

- fraction de positions exactes uniques ;
- overlap/Jaccard exact paire par paire ;
- couverture directionnelle d'un corpus par l'autre ;
- entropie d'états sur des bins matériels/STM ;
- divergence Jensen-Shannon des distributions d'états ;
- divergence WDL séparée, uniquement diagnostique ;
- ordre glouton de pooling maximisant un proxy `0.7 × nouveauté + 0.3 × JS` ;
- nouveauté marginale du dernier corpus ajouté.

Le fingerprint de position exclut score et WDL : `blake2b64(wm,wk,bm,bk,stm)`. Le screen échantillonne au plus 200k records par corpus de manière déterministe et bornée en mémoire.

### Gate A

Le seuil primaire préenregistré est :

```text
final_marginal_exact_novelty >= 0.05
```

Ce seuil est volontairement modeste : il demande seulement que le dixième bras retenu ajoute encore au moins 5 % de positions exactes non vues dans le pool échantillonné. Il ne prouve pas que cette diversité est utile en force.

Si le gate échoue, **pas de gros fit multi-seed**. On conclut que changer uniquement la seed n'est pas un levier suffisant et on teste ensuite une diversité contrôlée de paramètres (top-K, budget de nœuds, cadence, ouverture), dans une expérience distincte.

## 5. Phase B — test causal à volume strictement comparable

Si Gate A passe, construire quatre candidats depuis le même G0.

| bras | données | but |
|---|---|---|
| `H_POOL_10` | pool égalisé H01..H10 | test principal diversité + volume |
| `SINGLE_10N` | un corpus frais de `10N` depuis G0, une seed préfixée | contrôle volume brut |
| `VERTICAL_10xN` | 10 générations de `N`, chaque génération pilotée par le modèle précédent | contrôle compounding historique |
| `H_POOL_EQUAL_N` | sous-échantillon du pool H à `N` | diagnostic diversité à volume d'une seule branche |

`H_POOL_10` et `SINGLE_10N` doivent contenir exactement le même nombre de records d'entraînement après les mêmes règles de split. `VERTICAL_10xN` dépense le même ordre de grandeur de génération mais conserve sa causalité verticale ; son modèle final est évalué tel quel.

Pour `H_POOL_10`, aucun bras individuel n'est entraîné puis utilisé comme teacher. Les dix corpus sont indépendants jusqu'au pooling. Le fit est unique, depuis le même G0/prior que le contrôle `SINGLE_10N`.

## 6. Cible et fit

Le test primaire utilise la cible conditionnelle `context30`, reconstruite avec le même mapper et les mêmes folds disjoints par partie pour tous les bras compatibles.

Le WDL terminal reste conservé pour les diagnostics et contrôles, mais il n'est pas utilisé pour changer le protocole après lecture des résultats.

Même architecture PatternEval, même L2, même budget d'optimisation, même convergence, même split, même géométrie et mêmes features. Aucun tuning par bras.

## 7. Lecture des résultats

Ordre de lecture obligatoire :

1. intégrité/provenance ;
2. métriques Phase A ;
3. loss/calibration sur holdout commun ;
4. seulement ensuite force indépendante.

La comparaison primaire de force est :

```text
H_POOL_10 vs SINGLE_10N
```

Elle répond directement à la question « à volume égal, l'indépendance apporte-t-elle quelque chose ? ».

La comparaison secondaire :

```text
H_POOL_10 vs VERTICAL_10xN
```

répond à « pooling horizontal ou compounding vertical ? ».

`H_POOL_EQUAL_N` indique si un bénéfice existe déjà sans avantage de volume.

Les résultats sont reportés avec score W/D/L, Elo, intervalle de confiance, conversion, gardes P3/P4/Q00/native et log-loss context30. Une meilleure loss seule n'est jamais une preuve de progrès.

## 8. Verdicts préenregistrés

- `INDEPENDENT_POOLING_SUPPORTED` : `H_POOL_10` bat `SINGLE_10N` avec effet positif robuste et aucune garde en régression ;
- `VOLUME_ONLY` : H_POOL et SINGLE sont indiscernables mais tous deux battent les petits volumes ;
- `VERTICAL_COMPOUNDING_SUPPORTED` : la lignée verticale domine le pool horizontal ;
- `DIVERSITY_NOT_EFFECTIVE` : Gate A passe mais la diversité ne se transforme pas en force ;
- `SEED_DIVERSITY_TOO_LOW` : Gate A échoue ;
- `INCONCLUSIVE` : puissance statistique insuffisante.

Aucun de ces verdicts n'autorise automatiquement une promotion de champion.

## 9. Étape suivante si H1 est confirmée

Seulement après confirmation, passer d'un nombre fixe de générations à une politique d'acquisition active : générer plusieurs petits batchs candidats et sélectionner le prochain batch maximisant l'information marginale par CPU-h, avec arrêt lorsque `ΔI / coût` sature.

Une deuxième vague pourra alors utiliser l'incertitude du modèle (`H(W,D,L | s)`) pour cibler les régions où le réseau est peu certain. Cela constitue une expérience v2 séparée : la v1 doit d'abord établir causalement que l'indépendance des corpus apporte plus que le volume brut.

## 10. Commande du screen

Exemple :

```bash
python3 jobs/tools/selfplay_information_gain.py \
  --corpus H01=/path/h01.jnnw \
  --corpus H02=/path/h02.jnnw \
  --corpus H03=/path/h03.jnnw \
  --corpus H04=/path/h04.jnnw \
  --corpus H05=/path/h05.jnnw \
  --corpus H06=/path/h06.jnnw \
  --corpus H07=/path/h07.jnnw \
  --corpus H08=/path/h08.jnnw \
  --corpus H09=/path/h09.jnnw \
  --corpus H10=/path/h10.jnnw \
  --sample-per-corpus 200000 \
  --novelty-weight 0.7 \
  --min-marginal-novelty 0.05 \
  --out information-gain.json
```

Le JSON produit est un artefact scientifique à conserver avec les manifests et seeds de génération.
