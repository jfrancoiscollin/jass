# Prior centré sur le parent — règle de décision PRÉENREGISTRÉE

Écrit le 2 août 2026 **avant** que `cpx62-1149` ne rende, et validé par JFC dans
ces termes. Le but est qu'aucun seuil ne soit rediscuté une fois les chiffres
connus — ce projet s'est déjà fait piéger par des lectures a posteriori.

## La question

`--warm-start` ne choisit que le point de départ de l'optimiseur ; l'objectif
garde un **L2 centré sur zéro**, ce qui affirme qu'un bucket sans données vaut 0.
En continuation de lignée c'est faux — la meilleure estimation est celle du
parent — et cela décide du sort de la majorité des 130 086 buckets retenus, vus
une poignée de fois. `--prior-mean` déplace le centre du ridge sur le parent ;
avec `--prior-decay 0` la précision reste uniformément `l2`, donc **seul le
centre bouge**. Un facteur.

## Ce qui est mesuré

| job | pool | rôle |
|---|---|---|
| `cpx62-1148` | `home-1004` | **découverte** : `+9,15 Elo`, IC95 `[+0,6 ; +17,7]`, `n=6000` |
| `cpx62-1149` | `home-0995` (disjoint) | **réplication indépendante** |
| `home-1150` | `home-1004` (le MÊME) | **reproductibilité machine/build — PAS un troisième point** |

⛔ `home-1150` **n'entre pas dans la consolidation** : mêmes ouvertures, moteur
déterministe à profondeur fixe, donc très probablement les mêmes parties.
L'agréger reviendrait à compter deux fois les mêmes données et à rétrécir
artificiellement l'intervalle.

## La règle, fixée d'avance

1. **Consolidation sur les compteurs BRUTS** des deux pools disjoints,
   `n = 12 000` — l'estimateur à vues additionnées étendu aux pools, comme la
   promotion de TURNOVER (quatre pools, `n=17 000`) et la solidification d'EXACT
   (deux pools, `n=12 000`).
2. **Bake si** l'IC95 consolidé **exclut zéro** *et* les deux points estimés sont
   **de même signe**. Le second critère écarte le cas où un pool porterait tout
   l'effet pendant que l'autre le contredit — ce que la consolidation seule
   masquerait.
3. **Gardes additionnelles obligatoires**, comme pour EXACT : non-régression
   contre `gen2-mmto`, plancher de conversion **recalibré à ~`0,76`** (le `0,95`
   est mort le 1er août, cf. `L3_EXACT_PROMOTION_20260801.md`), et le second pool
   — qui est `cpx62-1149` lui-même. Template : `l3-succession-guards-v1.sh`.
4. ⚠️ **Le point consolidé sera BIAISÉ VERS LE HAUT.** `cpx62-1148` est la mesure
   de découverte, et un effet retenu parce qu'il a franchi zéro de justesse
   surestime sa taille (malédiction du vainqueur). Cela ne bloque pas le bake ;
   cela doit figurer dans l'enregistrement de promotion, pour que le chiffre ne
   soit pas sur-cité dans six mois comme l'a été le `0,98` de conversion.

## Pourquoi `n=6000` et pas plus

`n` est **plafonné par la taille du pool** : 1500 ouvertures, chacune déjà jouée
dans les deux couleurs, et un moteur **déterministe** à profondeur fixe — rejouer
une ouverture rend la même partie. Augmenter `--pairs` ne fabriquerait que des
doublons. `cpx62-1151` engendre un pool de **3000** pour lever ce plafond :
`n = 12 000` par porte, et la puissance sur un effet de `+9 Elo` passe de **56 %**
à **84 %**.
