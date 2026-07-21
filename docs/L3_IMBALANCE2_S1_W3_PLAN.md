# L3-IMBALANCE2 — suite D1-X : S1 search-only et W3 poids oracle-adaptatifs

> **Statut : W0 terminé, W1 screen préparé — 21 juillet 2026**

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

La référence `0862` montre une difficulté variable et non monotone. Une règle
manuelle selon le seul nombre de pièces confondrait densité et convertibilité.

## 3. W0 — calibration read-only terminée

Source immuable :

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

W0 a été exécuté par :

```text
cpx62-0877-l3-imbalance2-w0-oracle-calibration
r2:jass-data/runs/cpx62-0877-l3-imbalance2-w0-oracle-calibration/20260720T235638Z-d0329285
```

Verdict :

```text
W0_ORACLE_WEIGHT_CALIBRATION_READY
STRATUM_ORACLE_WEIGHTING_SUPPORTED_DENSITY_ONLY_NOT_SUPPORTED
POOL_STABILITY_PASS=true
DENSITY_ONLY_PASS=false
```

Diagnostics principaux :

- alpha moyen `1v3..7v9` : `0,464997` ;
- alpha moyen `14v16..18v20` : `0,372246` ;
- corrélation de Spearman matériel/alpha : `−0,612204` ;
- écart médian A/B : `0,09375` ;
- écart maximal A/B : `0,203125`.

Conclusion : une pondération **par strate** mérite un screen, mais une loi
monotone ou un seuil manuel selon le nombre de pièces est rejeté.

## 4. Source oracle et séparation des lignées

- `1v3` et `2v4` : WDL EGDB exacte sur les positions de calibration ;
- `3v5..18v20` : Scan reste une référence empirique avec incertitude ;
- l’oracle ne remplace pas les cibles WDL terminales, mais influence les poids ;
- la variante devient donc **teacher-calibrée**.

Cette propriété est acceptable uniquement dans le laboratoire spécialiste
`L3-IMBALANCE2`. Les courbes, poids, corpus et modèles W3 sont interdits dans
`L3-PURE`.

## 5. W1-SCREEN — pondération adaptative par strate

Le premier test causal réutilise le corpus G4 immuable de `ccx33-0852` :

- contrôle : matrice role-aware V2 fixe `1/2/4` ;
- candidat : poids absolus shrinkés de W0, distincts pour les 18 strates ;
- même corpus, même split, même warm-start G3, même géométrie 8cf ;
- même recherche Q00, mêmes features, loss, L2 et optimiseur ;
- mêmes 500 000 lignes après rééchantillonnage ;
- holdout byte-identique ;
- aucune nouvelle partie d’autojeu pour l’entraînement ;
- les labels WDL terminaux restent inchangés.

Évaluation :

- nouveaux pools E64/F64, seed `141421` ;
- 2 304 positions appariées par bras ;
- d10, max 400 plies, macro-moyenne égale sur les 18 strates ;
- bootstrap apparié/stratifié 10 000 ;
- garde généraliste 64 paires à d8.

Gate : delta adaptatif−contrôle du coût `2L+D` ≤ `−0,020`, borne haute IC95 ≤ 0,
aucun pool dégradé, au moins 12/18 strates non dégradées, pire régression locale
≤ `0,10`, garde généraliste passée.

Le job est préparé pour ccx33 :

```text
jobs/prepared/l3-imbalance2-w1-20260721/ccx33-l3-imbalance2-w1-screen.sh
```

Même en cas de passage, le résultat ne peut qu’autoriser une revue humaine pour
une confirmation avec calibration oracle fraîche C512, cross-fit et nouveaux
pools. Il ne peut ni continuer l’entraînement, ni promouvoir le modèle.

## 6. S1 — pilote search-only séparé

Le mécanisme retenu pour conception est une extension bornée de stabilité de
rôle : dans le domaine exact `|Δ hommes|=2`, dames égales, la première
continuation ordonnée qui conserve le même camp avantagé peut recevoir `+1 ply`,
hors quiescence, à profondeur minimale et avec cap d’extensions sur le chemin.

S1 doit conserver un modèle immuable sans refit et être mesuré sur des pools
indépendants, à budget qualité et temps fixes, avec garde généraliste et débit.
S1 ne doit pas réutiliser les pools E64/F64 du W1 comme preuve confirmatoire.

## 7. Gardes

```text
training_continuation_authorized=false
weight_policy_confirmation_authorized=false
search_pilot_promotion_authorized=false
promotion_authorized=false
automatic_next_job=null
```
