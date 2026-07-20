# L3-IMBALANCE2 — suite D1-X : S1 search-only et W3 poids oracle-adaptatifs

> **Statut : plan préenregistré — 21 juillet 2026**

## 1. Deux hypothèses indépendantes

D1-X a fermé RC4 et recommande un unique pilote search-only. La remarque sur les
pénalités ouvre une seconde hypothèse distincte. Elles ne doivent jamais être
modifiées dans le même bras :

- **S1 — recherche :** même modèle et mêmes poids V2, seule la recherche change ;
- **W3 — crédit :** même recherche Q00, seule la pondération change.

Toute combinaison S1+W3 est interdite avant un résultat causal positif de chacun.

## 2. Limite des pénalités fixes

La matrice V2 applique actuellement `1/2/4` à toutes les positions du domaine
exact, de `1v3` à `18v20`. Elle traite donc une nulle théorique de finale sparse
comme une nulle évitable de milieu de partie.

La référence `0862` prouve que la difficulté varie par strate, mais elle ne montre
pas une coupure monotone simple : Scan d10 donne par exemple un taux de gain du
camp à `+2` d'environ `0,594` à `15v17`, contre `0,430` à `14v16`. Une règle
manuelle du type « poids fixes au-dessus de 14 pièces, poids faibles en dessous »
serait donc trop dépendante du bruit des pools.

## 3. W0 — calibration read-only

W0 réutilise la référence immuable :

```text
r2:jass-data/runs/cpx62-0862-l3-imbalance2-a64-b64-difficulty-reference/20260720T130310Z-59940065
```

Pour chaque strate, du point de vue du camp initialement à `+2` :

```text
alpha_s = clip(P_oracle(gain) - P_oracle(défaite), 0, 1)
poids_résultat_attendu = 1
poids_nulle            = 1 + alpha_s
poids_renversement     = 1 + 3 * alpha_s
```

Cette règle retrouve `1/2/4` lorsque l'oracle décrit une position quasiment
gagnée (`alpha=1`) et revient vers `1/1/1` lorsque l'oracle décrit une position
naturellement nulle (`alpha≈0`).

W0 publie quatre lectures : valeur brute, shrinkage par source, ajustement
monotone selon le matériel et normalisation sur les strates `14v16..18v20`.
Il mesure aussi l'écart entre les pools A et B.

W0 n'autorise aucun entraînement. Trois verdicts sont possibles :

1. courbe trop instable — construire un pool indépendant C512 plus grand ;
2. adaptation par strate soutenue, mais pas une simple loi de densité ;
3. tendance de densité suffisamment stable pour préparer W1.

## 4. Source oracle et séparation des lignées

- `1v3` et `2v4` : WDL EGDB exacte sur les positions de calibration ;
- `3v5..18v20` : Scan reste une référence empirique avec incertitude ;
- l'oracle ne remplace pas les cibles WDL terminales, mais influence les poids ;
- la variante devient donc **teacher-calibrée**.

Cette propriété est acceptable uniquement dans le laboratoire spécialiste
`L3-IMBALANCE2`. Les courbes, poids, corpus et modèles W3 sont interdits dans
`L3-PURE`.

## 5. Étape W1 éventuelle

Si W0 est suffisamment stable, W1 devra utiliser :

- un nouveau pool de calibration C, indépendant des anciens A/B ;
- idéalement 512 positions par strate ;
- EGDB exacte pour les strates couvertes ;
- Scan à budget supérieur ou répété pour les autres ;
- estimation cross-fit des poids, avec clipping ;
- mêmes octets de train pour contrôle V2 et candidat W3 ;
- mêmes recherche, split, loss, L2 et initialisation ;
- évaluation sur de nouveaux pools E64/F64.

A/B ne pourront pas servir simultanément à calibrer les poids et à déclarer un
lead.

## 6. S1 — pilote search-only séparé

Le mécanisme retenu pour conception est une extension bornée de stabilité de
rôle : dans le domaine exact `|Δ hommes|=2`, dames égales, la première
continuation ordonnée qui conserve le même camp avantagé peut recevoir `+1 ply`,
hors quiescence, à profondeur minimale et avec cap d'extensions sur le chemin.

S1 doit conserver un modèle immuable sans refit et être mesuré sur :

- nouveaux pools E64/F64 ;
- budget qualité fixe et budget temps fixe ;
- sentinelles D0 comme diagnostic de mécanisme seulement ;
- garde généraliste ;
- NPS, nœuds et débit ;
- aucune promotion automatique.

Le mécanisme exact devra rester opt-in et neutre par défaut. W0 et S1 peuvent
être préparés en parallèle, mais leurs résultats et décisions restent séparés.

## 7. Gardes

```text
training_authorized=false
weight_policy_authorized=false
search_pilot_promotion_authorized=false
promotion_authorized=false
automatic_next_job=null
```
