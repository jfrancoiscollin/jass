# L3-IMBALANCE2 — D1-A RC4 representation screen

Ce pilote répond au profil D0 `cpx62-0871` : sept sentinelles relèvent directement
de la représentation/objectif et vingt-trois portent des signaux mixtes. Aucun cas
n'a satisfait le critère strict d'un problème pur d'horizon de recherche.

## Question

Une évaluation linéaire qui conditionne quatre gradients de conversion au rôle
matériel courant améliore-t-elle la transformation d'un avantage de deux hommes,
sans toucher à la recherche ni à la distribution d'entraînement ?

## Source de train immuable

Les deux bras réutilisent les mêmes octets publiés par `ccx33-0852` :

- `g4-source.jnnw.gz`, 500 000 records ;
- `g4-source.jsm.gz`, métadonnées alignées ;
- split ouverture `holdout_mod=10`, seed `271828` ;
- pondération role-aware V2, matrice `1/2/4` ;
- logistic WDL, color-fold, tempo-stage, `L2=3e-5`, 25 itérations.

Aucun nouveau self-play n'est produit pour l'entraînement. Scan ne fournit aucun
label ni poids. Contrôle et RC4 sont refittés depuis zéro sur le même JNNW pondéré.

## Différence expérimentale unique

Le bras contrôle utilise la source revue sans modification. Le bras RC4 est bâti
depuis une seconde copie exportée du même SHA, transformée de façon déterministe
par `apply_imbalance2_rc4_patch.py`. La source de production n'est pas modifiée.

Les quatre extras sont nuls hors du domaine courant :

```text
|écart hommes| = 2
nombres de dames égaux
```

Extras black-POV :

1. `safe_mobility_delta` — destinations sûres pions+dames, noir moins blanc ;
2. `defender_confinement` — cases de dame déniées + pions bloqués du défenseur ;
3. `promotion_race_margin` — meilleure progression sûre vers promotion ;
4. `trade_pressure` — pièces adverses immédiatement capturables par les pions.

La classe reste additive, linéaire et interprétable.

## Pools d'évaluation

Nouveaux pools indépendants **C64/D64** :

- seed `314159` figée avant résultat ;
- 18 strates `1v3…18v20` ;
- 64 positions par strate et par pool ;
- mêmes positions et budget pour les deux bras ;
- d10, `maxplies=400`, 8 shards.

A64/B64 ne servent ni à la sélection ni au verdict D1-A.

## Mesure principale

Coût `2L+D` du camp initialement avantagé, macro-moyenne égale par strate.
RC4 passe le volet principal uniquement si :

- delta RC4−contrôle ≤ `−0,020` ;
- borne haute IC95 bootstrap stratifié ≤ `0` ;
- aucun pool C ou D dégradé ;
- au moins 12/18 strates non dégradées ;
- pire régression locale ≤ `0,10`.

Maximum deux timeouts explicitement identifiés, retirés symétriquement des deux
bras, et fraction exclue ≤ `0,001`. Toute autre erreur fait échouer le job.

## Gates secondaires de veto

### Sentinelles D0

Les 30 sentinelles sont rejouées à d14 par le contrôle refitté et RC4. Le gate
exige :

- au moins 4/7 cas représentation/objectif corrigés vers le coup Scan d14 ;
- au plus deux nouvelles divergences parmi les 23 autres cas ;
- débit agrégé RC4/contrôle ≥ `0,95`.

### Généraliste

64 positions fixes tirées de `data/dilf_combinations.fen`, deux couleurs par
position, d8. RC4 doit obtenir au moins 45 % et ne pas avoir un IC95 entièrement
sous 50 %.

## Décision

Un échec sur n'importe quel gate produit :

```text
D1_RC4_NO_GO
REJECT_RC4_AND_DESIGN_SEPARATE_SEARCH_PILOT
```

Un succès produit seulement :

```text
D1_RC4_SCREEN_PASS_REVIEW_D1B
REVIEW_SHORT_D1B_ONLY
```

Dans les deux cas :

```text
d1b_authorized=false
training_continuation_authorized=false
promotion_authorized=false
automatic_next_job=null
```

Une revue humaine est obligatoire avant tout D1-B. P3 reste interdit.

## Exécution

Utiliser un seul wrapper selon la première box disponible :

```text
jobs/prepared/l3-imbalance2-d1-rc4-20260720/ccx33-l3-imbalance2-d1-rc4.sh
jobs/prepared/l3-imbalance2-d1-rc4-20260720/cpx62-l3-imbalance2-d1-rc4.sh
```
