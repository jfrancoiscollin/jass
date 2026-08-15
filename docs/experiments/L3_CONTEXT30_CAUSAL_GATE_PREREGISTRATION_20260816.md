# Jass 10×10 — attribution causale de `CONTEXT_30`

Date de préenregistrement : 16 août 2026. Statut : **préparé, non lancé**.
Ce protocole ne lit aucun frozen set, ne génère aucun self-play et n'autorise
ni promotion ni continuation automatique.

## 1. Pourquoi ce test est nécessaire

`cpx62-1354` a mesuré `CURRENT_C30` à `+5,91 Elo` contre L2LOW, IC95
`[-0,15 ; +11,97]`, `P(Elo>0)=97,2 %`, sur 12 000 parties. C'est un signal
prometteur, mais **pas encore une attribution causale à la cible** : le modèle
`CURRENT_C30` est un refit supplémentaire de L2LOW. Le contraste avec L2LOW
change donc à la fois l'objectif d'apprentissage et le fait de refitter.

La question suivante est plus stricte : à corpus, split, parent, architecture,
solveur et budget identiques, l'association correcte entre une position et son
contexte produit-elle un modèle plus fort qu'une association détruite qui
conserve exactement les mêmes marginales du target final ? Et le target ainsi aligné bat-il un
refit témoin sur le W/D/L terminal ?

## 2. Bras scellés

Les trois bras utilisent les 2 000 000 positions immuables de TURNOVER,
l'ouverture-level split `seed=577215`, le parent L2LOW, l'architecture 8cf
exact-fold avec 120 extras et tempo-stage, puis la même recette :

```text
loss=logistic
prior_mean=L2LOW ; prior_decay=0
l2=1e-5 ; gtol=1e-4 ; maxcor=20 ; max_iter=2000
chunk=20000 ; prune=true
```

| bras | cible | construction |
|---|---|---|
| `ALIGNED` | `CONTEXT_30` aligné | modèle `CURRENT_2M` certifié de `cpx62-1340`, réutilisé sans refit |
| `SHUFFLED` | contrôle marginal | permutation sans point fixe dans chaque cohorte/fold/WDL : même WDL, même multiset conditionnel et même multiset du target final |
| `OUTCOME` | contrôle de refit | W/D/L terminal pur |

Le job de fit reproduit le sidecar `ALIGNED` byte pour byte avec le certificat
de `cpx62-1340`, puis construit un contrôle `SHUFFLED` plus strict que le
shuffle historique : la stratification par WDL conserve aussi la marginale du
target final. Il refitte
**seulement** `SHUFFLED` et `OUTCOME`, séquentiellement. Il réauthentifie aussi
le modèle `ALIGNED` et les trois gradients `||grad||∞ <= 1e-4`. Les trois
modèles doivent être structurellement valides et avoir trois hashes distincts.

Sources immuables :

```text
TURNOVER  r2:jass-data/runs/home-0977-l3-pure-turnover1to1-train-v1/
          20260726T071254Z-336bb984
L2LOW     r2:jass-data/runs/cpx62-1164-l3-prior-dose-l2-refit-v1/
          20260803T060626Z-209eb56b
ALIGNED   r2:jass-data/runs/cpx62-1340-jass-megacorpus-comparative-fit-v1/
          20260814T123246Z-2ce07222/artefacts/current_2m.pjtw.gz
AUDIT A   r2:jass-data/runs/cpx62-1341-jass-megacorpus-arm-d-fit-v1/
          20260814T191555Z-18c38a33/artefacts/source-A-convergence.json
```

Template : `jobs/templates/l3-context30-causal-fit-v1.sh`.

## 3. Pools indépendants

Deux nouveaux pools de 3 000 ouvertures sont générés déterministement :

```text
C30_POOL_1 seed=2026081601
C30_POOL_2 seed=2026081602
```

Chaque pool doit être disjoint de `1348`, `1351`, `highn1500`, `ABCD
source500`, `big3000`, `big3000b`, `vol8m` et `succession`. Le second doit en
plus être disjoint du premier. Le certificat doit publier la liste des sources
exclues, le hash du fichier et zéro recouvrement. Aucun pool n'est remplacé
après lecture d'une force.

## 4. Gates et ordre hiérarchique

Chaque gate emploie exactement les mêmes ouvertures, couleurs inversées, le
même binaire 8cf exact-fold tempo-stage et les mêmes deux vues : Q00 profondeur
9 puis native 0,1 s. Un pool donne 6 000 parties par vue, 12 000 au total. Deux
pools donnent 24 000 parties par contraste. Chaque vue publie un bootstrap
apparié par ouverture de 200 000 tirages (`seed=20260816`) et accepte au plus
2 % d'erreurs (`MAX_ERROR_RATE=0.02`).

### Primaire — causalité de l'alignement

```text
ALIGNED − SHUFFLED
```

Jouer pool 1, puis pool 2 chaîné au premier. PASS si et seulement si :

- les effets inter-pools sont compatibles (`|z| < 1,96`) ;
- sur les deux pools chaînés, `P(Elo > 0) > 95 %` ;
- les budgets, identités, deux vues et taux d'erreur passent.

Il n'existe **aucun seuil Elo minimal**. Un petit effet positif est un résultat
positif ; le seuil porte sur l'incertitude, pas sur une magnitude arbitraire.

### Secondaire — utilité face au WDL terminal

```text
ALIGNED − OUTCOME
```

Ce contraste n'est joué que si le primaire passe. Même deux pools, même règle.
Il distingue l'apport pratique de la cible de l'effet banal « refaire un fit de
plus depuis L2LOW ».

### Tertiaire — valeur nette et réplication de `1354`

```text
ALIGNED − L2LOW
```

Ce contraste n'est joué que si primaire et secondaire passent. Une porte sur
`C30_POOL_1` est chaînée à la porte antérieure `cpx62-1354`, puisque le modèle
`ALIGNED` est byte-identique à son `A_CURRENT_C30` et que les pools sont
disjoints. Le critère reste `P(Elo>0)>95 %` sur les deux pools compatibles.

## 5. Verdicts préenregistrés

| observation | verdict scientifique |
|---|---|
| primaire échoue ou pools hétérogènes | aucune preuve causale que l'alignement contextuel améliore la force ; ne pas promouvoir la cible |
| primaire passe, secondaire échoue | l'alignement porte un signal relatif au shuffle, mais `CONTEXT_30` ne bat pas un refit WDL propre |
| primaire + secondaire passent, tertiaire échoue | mécanisme causal confirmé mais valeur nette contre L2LOW non répliquée ; conserver comme résultat de labo, pas comme recette |
| les trois passent | `CONTEXT_30` est un mécanisme causal de force confirmé et répliqué ; seulement alors discuter transfert au champion CURRICULUM ou self-play |

Une amélioration de loss ou de diagnostic statique ne peut sauver aucun échec
de force. Un résultat neutre n'est pas renommé « fail » si son estimation reste
positive : il est rapporté positif mais non établi, avec son intervalle.

## 6. Budget et séquence opératoire

1. Fit CPX : deux contrôles seulement ; `ALIGNED` est réutilisé.
2. Génération/certification des deux pools, sans force.
3. Primaire : 24 000 parties nouvelles.
4. Si PASS, secondaire : 24 000 parties nouvelles.
5. Si PASS, réplication L2LOW : 12 000 parties nouvelles, puis chaînage avec
   les 12 000 déjà jouées dans `1354`.

Le maximum est donc 60 000 nouvelles parties, mais la hiérarchie arrête la
dépense dès que la revendication causale nécessaire échoue. Aucun job enfant
n'est lancé automatiquement : chaque étape consomme le certificat immuable de
la précédente après audit.
