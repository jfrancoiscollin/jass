# L3-IMBALANCE2 — lignée spécialisée dans les positions à deux pions d’écart

> **Version 1.1 — 19 juillet 2026**  
> **Statut : PR préparée, aucun job mis en queue**

## 1. But

L3-IMBALANCE2 est une lignée indépendante de L3-PURE. Elle travaille sur les
parties et positions dont le point de départ présente exactement deux pions
d’écart :

`1 v 3`, `2 v 4`, `3 v 5`, `4 v 6`, `5 v 7`, `6 v 8`, `7 v 9`, `8 v 10`,
`9 v 11`, `10 v 12`, `11 v 13`, `12 v 14`, `13 v 15`, `14 v 16`,
`15 v 17`, `16 v 18`, `17 v 19`, `18 v 20`.

Les positions initiales ne contiennent que des pions simples. Le rôle avantagé
est partagé entre Blancs et Noirs, et le trait est équilibré. Chaque génération
contient exactement 500 000 records source, répartis également entre les dix-huit
strates puis entre les deux couleurs avantagées.

Pour les strates d’au moins sept pièces, la spécialisation porte sur la
**distribution de départ**. Les captures, promotions et transitions réellement
jouées sont conservées afin de préserver le retour Monte-Carlo de la partie.

## 2. Professeur exact sous sept pièces

Les seules configurations demandées contenant moins de sept pièces sont :

- `1 v 3`, soit quatre pièces ;
- `2 v 4`, soit six pièces.

Ces positions sont déjà dans le domaine de l’EGDB exacte. Un rollout ordinaire
n’est pas adapté : le générateur détecte immédiatement la tablebase et termine
avant d’émettre un échantillon. Ces deux strates sont donc traitées comme un
**corpus statique exact** :

1. des positions fraîches et équilibrées sont générées à chaque génération ;
2. `jass --egdb-relabel` écrit le WDL exact de la tablebase ;
3. chaque position constitue une unité d’ouverture indépendante pour le split ;
4. aucune recherche, évaluation Scan ou évaluation Gen2 ne fournit la cible.

Les strates `3 v 5` à `18 v 20` restent en autojeu terminal WDL selon la recette
P1. L’EGDB continue d’y intervenir uniquement lorsqu’une trajectoire l’atteint
naturellement.

## 3. Objectif asymétrique du camp avantagé

Dans cette distribution, le camp avec deux pions d’avance doit gagner nettement
plus souvent qu’il ne perd. Une régression logistique WDL symétrique accorde
sinon trop peu de poids aux échecs rares mais critiques.

Le code calcule donc le résultat de la **partie du point de vue du camp
initialement avantagé**, puis inscrit un code auxiliaire auditable dans le champ
`score`, sans lancer de recherche de score. Après le split par partie :

- victoire du camp avantagé : poids `1` ;
- nulle : poids `2` ;
- défaite : poids `4`.

Le ratio pré-enregistré est donc **1 / 2 / 4**. La défaite coûte deux fois la
nulle et quatre fois la victoire. Le train set est rééchantillonné de manière
déterministe avec ces poids, à nombre de records constant ; le holdout reste
strictement intact et non pondéré. Ainsi, le L2 conserve la même échelle et le
log-loss de validation reste comparable entre générations.

Ce mécanisme pénalise une mauvaise issue de la partie, et non un simple label
`loss` du joueur au trait : tous les records d’une même partie reçoivent la
classe correspondant au résultat du camp initialement avantagé.

## 4. Contrat commun

Hors les deux adaptations précédentes, P1 reprend la recette de la PR #358 :

- G0 matériel homme=1, dame=3, autres termes à zéro ;
- 500 000 records frais par génération ;
- d8 pour G1–G4 ;
- fingerprint Q00 complet de 63 paramètres ;
- rollouts : 8 plies aléatoires, epsilon 8 %, décroissance au ply 60 ;
- WDL terminal, EGDB exacte après atteinte naturelle et ply-cap censuré ;
- fit logistique WDL, color-fold, tempo-stage, L2 `3e-5` ;
- G1 depuis zéro, puis warm-start du student précédent ;
- géométrie 8cf ;
- aucun replay, MMTO, frontière, adjudication matérielle ou professeur moteur ;
- seed primaire `271828` ;
- aucune promotion ni continuation automatique.

Scan ne fournit aucune donnée d’entraînement. Gen2-MMTO ne fournit aucune donnée
d’entraînement. L’EGDB est la seule vérité externe admise, exclusivement comme
vérité exacte des positions de moins de sept pièces et après atteinte naturelle
pour les autres trajectoires.

## 5. Paliers

| Palier | Générations | Recherche de jeu | Parent |
|---|---:|---:|---|
| P1 | G1–G4 | d8 | G0 matériel |
| P2 | G5–G8 | d10 | G4 immuable |
| P3 | G9–G12 | d12 | G8 immuable |
| P4 | G13–G16 | d14 | G12 immuable |

Chaque palier est un job séparé. P2–P4 exigent l’URI et le SHA-256 gzip du
dernier modèle du palier précédent. Aucun wrapper ne chaîne le palier suivant.

## 6. Plateau avant toute référence externe

Le benchmark Gen2-MMTO/Scan n’est plus exécuté systématiquement après P1, P2,
P3 et P4. Il est réservé à la fin d’un cycle lorsque la lignée a atteint un
plateau documenté.

Deux pools internes `plateau-a` et `plateau-b`, distincts des pools finaux, sont
publiés sans jamais faire jouer Gen2 ou Scan. Un rapport de plateau doit couvrir
au moins quatre générations consécutives au même budget et mesurer, sur les deux
pools, le coût :

`coût d’échec = 2 × taux de défaite + taux de nulle`.

Le plateau est confirmé seulement si :

- l’amélioration première→dernière génération est inférieure à 0,02 ;
- l’IC bootstrap apparié à 95 % du changement contient zéro ;
- l’étendue du coût sur les trois dernières générations est au plus 0,04 ;
- les générations utilisent exactement le même budget et la même recette ;
- aucune référence Gen2 ou Scan n’a été consultée pour cette décision.

Le benchmark final refuse de démarrer sans un rapport immuable validant ces
conditions et un `PLATEAU_APPROVED=1` explicite.

## 7. Benchmark final : référence basse et référence haute

Une fois le plateau confirmé, les mêmes positions des pools finaux A et B sont
jouées séparément par :

1. le candidat contre lui-même ;
2. **Gen2-MMTO contre lui-même**, référence basse ;
3. **Scan contre lui-même**, référence haute.

Le protocole reste compatible avec le benchmark matériel `0841` : d10, cap 400
plies, résultat replié du point de vue du camp avec deux pions d’avance, Scan
sans bitbases. Gen2 utilise sa géométrie et sa recherche natives ; le candidat
utilise son fingerprint Q00 complet.

Un pool passe si :

- chaque taux global W/D/L du candidat est à ±3 points de Scan ;
- les IC bootstrap appariés à 95 % restent dans ±5 points ;
- chaque strate a au moins 20 résultats et reste à ±10 points de Scan ;
- le coût `2L+D` du candidat n’est pas supérieur à la référence Gen2 de plus que
  la marge de non-régression pré-enregistrée ;
- aucune erreur moteur n’est tolérée.

Les deux pools doivent passer pour produire
`STOP_LINEAGE_SCAN_EQUIVALENT`. Si la lignée est au plateau mais reste sous la
cible, le verdict est `PLATEAU_BELOW_SCAN_REDESIGN` : on ne prolonge pas
mécaniquement la même recette.

## 8. Fichiers

- `jobs/tools/make_imbalance2_pools.py` : seeds par couleur avantagée, pools de
  plateau et pools finaux indépendants ;
- `jobs/tools/prepare_imbalance2_training.py` : corpus TB statique, code du
  résultat du camp avantagé et rééchantillonnage 1/2/4 ;
- `jobs/templates/l3-imbalance2-runner-v1.sh` : P1–P4 ;
- `jobs/tools/imbalance2_plateau.py` : verdict interne sans référence externe ;
- `jobs/tools/imbalance2_scan_gate.py` : benchmark candidat/Gen2/Scan ;
- `jobs/templates/l3-imbalance2-scan-gate-v1.sh` : garde plateau et verdict final ;
- `jobs/prepared/l3-imbalance2-20260719/` : wrappers hors queue.
