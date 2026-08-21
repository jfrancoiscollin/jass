# L3 — apprendre directement la décision : écran mécanistique DCR1

Date : 2026-08-22  
Tracking : issue #555

## 1. Pourquoi ce test est différent

Les campagnes récentes ont surtout appris une **valeur scalaire de position** :
WDL natif, `context30`, CTX3, CTX4 ou replay changent la cible, les données ou
l'ancrage, mais PatternEval doit toujours compresser le signal dans un seul
score universel.

DCR1 change l'objet appris. Pour une position où CURRICULUM hésite entre deux
coups légaux plausibles, le modèle reçoit une supervision directement liée à la
décision :

```text
D(s) = Q_juge_profond(s, top2) - Q_juge_profond(s, top1)
```

Le ranker doit prédire le signe et l'amplitude de `D(s)`. Il ne prédit pas le
résultat terminal de la partie et ne modifie pas CURRICULUM.

Cette voie est distincte de :

- CTX4, qui appliquait un mapper contextuel appris sur WDL aux enfants légaux ;
- MMTO/P3, qui ciblait un sous-domaine de conversion et réécrivait une eval ;
- `rank_finetune.py`, qui ajuste les poids PatternEval eux-mêmes.

DCR1 est généraliste, top-two, OOF et conserve la valeur scalaire byte pour
byte.

## 2. Séquence et dépendance

La PR prépare uniquement la phase mécanistique. Son job ne doit être mis en
queue qu'après le verdict terminal de `cpx62-1455-l3-replay-context30-target-gate-v1`.
L'attempt immuable de 1455 sera alors fourni au launcher.

Le protocole DCR1 est figé avant lecture du résultat de 1455. Le verdict de 1455
ne change donc aucun paramètre, seuil ou règle de sélection DCR1.

## 3. Sources et pools

Le modèle scalaire et le juge sont tous deux l'artefact immuable CURRICULUM :

- job `cpx62-1341-jass-megacorpus-arm-d-fit-v1` ;
- attempt `20260814T191555Z-18c38a33` ;
- SHA-256 brut `319d174f4b548b1655aad4bb30d4c6dc86c08dd715c9c23f8b19ba1937dc0be1`.

DCR1 réutilise comme **source mécanistique**, après leur gate terminé, les deux
pools 1455 qui ont été générés avant tout résultat DCR1 :

- 3 000 ouvertures par pool ;
- seeds de génération 1455 `2026082211` et `2026082212` ;
- disjonction mutuelle certifiée ;
- exclusion de 23 pools historiques, dont 1451 et 1454 ;
- aucun résultat de partie 1455 n'est une feature ou une étiquette DCR1.

Cette réutilisation économise une nouvelle génération de pools et reste
préenregistrée avant le verdict 1455. Les pools 1455 deviennent ensuite des
données DCR1 et sont donc définitivement interdits à tout futur gate de force
du ranker.

Dans chaque pool, 512 racines sont sélectionnées déterministiquement avec la
seed `2026082303`. La sélection ignore tous les résultats de recherche et de
partie.

## 4. Construction des paires

Pour chaque racine :

1. énumérer tous les enfants légaux ;
2. rechercher séparément chaque enfant avec CURRICULUM/Q00 à profondeur 9 ;
3. ordonner les enfants en POV du joueur parent ;
4. conserver la paire `(top1, top2)` seulement si la marge est `<= 40 cp` ;
5. réévaluer top1 et top2 à profondeur 12 puis profondeur 14.

Les recherches indépendantes appellent `new_game` avant chaque enfant. Les
pannes et timeouts sont fatals ; ils ne deviennent jamais des nulles.

Le label final est :

```text
judge_delta_cp = score_d14(top2) - score_d14(top1)
```

La profondeur 12 sert de garde de stabilité. Avec une zone morte de `8 cp` :

- `+1` si delta > +8 cp ;
- `-1` si delta < -8 cp ;
- `0` sinon.

Une paire entre dans le fit uniquement si les classes d12 et d14 sont égales et
non nulles. Aucun seuil n'est adapté après lecture des données.

## 5. Features du ranker

Le moteur produit pour chaque enfant le dump dédié
`--dump-conditional-context-v2`, soit 30 signaux phase/tactiques. Le vecteur de
paire contient :

- les 30 différences `top2 - top1` converties en POV du joueur parent ;
- la marge de recherche d9 `top2 - top1`, divisée par 100 ;
- le nombre de pièces, divisé par 40 ;
- le nombre de coups légaux, borné à 20 puis divisé par 20 ;
- la différence des indicateurs de capture ;
- l'indicateur « les deux coups capturent ».

Le total est de 35 features. Ni l'identité du pool, ni l'ouverture, ni le score
d14, ni Scan, ni un résultat futur ne sont des features.

## 6. Fit OOF

Le ranker primaire est une régression ridge linéaire vers le delta d14 :

```text
y = clip(judge_delta_cp, -200, +200) / 100
```

Contrat fixe :

- 5 folds déterministes par hash de `(seed, pool, ordinal, FEN)` ;
- seed de fold `2026082311` ;
- standardisation ajustée sur le train de chaque fold uniquement ;
- poids donnant 50 % de masse à chaque pool dans chaque fit ;
- ridge `0.1` ;
- intercept non pénalisé ;
- aucune recherche d'hyperparamètre ;
- score de chaque position produit strictement hors fold.

Un modèle final sur toutes les paires stables est publié uniquement comme
artefact d'audit. Un PASS n'autorise pas son déploiement direct.

## 7. Intervention et contrôle causal

CURRICULUM reste la décision de base. Dans la bande d'incertitude, le ranker
recommande top2 uniquement si son score OOF prédit :

```text
predicted_judge_delta_cp > 0
```

Le gain jugé vaut alors le delta d14 réel ; sans intervention, le gain vaut zéro.

Le contrôle SHUFFLED conserve exactement les mêmes scores OOF et le même nombre
d'interventions. Les scores sont tournés cycliquement, sans point fixe, dans
chaque cellule `(pool, fold)`. La seule information détruite est l'association
entre le score et sa position.

Effet primaire :

```text
mean[ I(score_aligned > 0) * judge_delta
    - I(score_shuffled > 0) * judge_delta ]
```

Le bootstrap rééchantillonne séparément les deux pools et leur donne chacun 50 %
de masse. Seeds : shuffle `2026082312`, bootstrap `2026082313`, 100 000 tirages.

## 8. Gates préenregistrées

Toutes les conditions doivent passer :

1. au moins 240 paires stables non nulles ;
2. au moins 80 par pool ;
3. au moins 30 labels positifs et 120 négatifs ;
4. fraction stable parmi les positions incertaines `>= 0,65` ;
5. zéro point fixe SHUFFLED ;
6. au moins 20 interventions ALIGNED ;
7. taux d'intervention `> 0` et `<= 35 %` ;
8. borne basse IC95 de l'effet ALIGNED−SHUFFLED `> 0 cp` ;
9. `P(effet > 0) >= 97,5 %` ;
10. effet ponctuel positif dans chacun des deux pools ;
11. borne basse IC95 du gain d14 sur les interventions ALIGNED `> 0 cp` ;
12. balanced accuracy OOF strictement supérieure à 50 %.

Verdicts :

- `JASS_DECISION_RANKER_MECHANISM_SCREEN_PASSED` ;
- `JASS_DECISION_RANKER_MECHANISM_SCREEN_FAILED`.

## 9. Conséquence d'un PASS

Un PASS autorise une nouvelle PR séparée :

- sidecar de ranker distinct de CURRICULUM ;
- contrôle `lambda=0`/canal désactivé byte-compatible ;
- intervention uniquement dans la bande de 40 cp ;
- ALIGNED et SHUFFLED exécutés par le même chemin runtime ;
- deux nouveaux pools de force excluant toutes les données DCR1, en particulier
  les deux pools 1455 ;
- native 0,1 s primaire et Q00 diagnostic ;
- confrontation supplémentaire contre CURRICULUM si le contraste causal passe.

Aucun de ces éléments n'est implémenté ou autorisé par la phase 1.

## 10. Conséquence d'un FAIL

Le triplet exact suivant est fermé sans tuning post-hoc :

```text
features = CTX2 phase/tactique 30 + cinq descripteurs
teacher  = CURRICULUM d12/d14
band     = 40 cp
```

Un autre essai devra modifier une hypothèse structurelle, par exemple la
représentation de coup, le teacher ou l'architecture, et publier une nouvelle
préinscription avant calcul.

## 11. Sécurité et scope

- PatternEval fits : 0 ;
- ranker fits : OOF + un modèle final d'audit ;
- nouveau self-play : 0 ;
- parties de force : 0 ;
- lecture frozen : 0 ;
- Scan/teacher externe : 0 ;
- modification ou promotion de CURRICULUM : 0 ;
- continuation automatique : interdite.
