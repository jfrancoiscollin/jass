# L3-PURE M2 — protocole frais depuis F2M

Date : 25 juillet 2026.

## Parent

F2M est le parent immuable de M2. Sa promotion générale a été revue
manuellement après `home-0965` :

- Q00 réparé : `562-21-417`, score `57,25 %`,
  IC95 `[54,22 ; 60,28]` ;
- cadence native réparée : `580-12-408`, score `58,60 %`,
  IC95 `[55,57 ; 61,63]`.

Les deux moteurs du benchmark provenaient du même SHA réparé. F2M remplace
donc `gen2-mmto` comme champion général courant ; Gen2 demeure une référence
historique figée.

## Entraînement 0966

M2 est un test de continuation de la recette qui a produit F2M :

- architecture 8cf, paramètres de recherche Q00 ;
- exactement 2 000 000 de positions fraîches ;
- self-play WDL sans oracle, teacher, TOP3 ou reweight ;
- départs standards, ouvertures aléatoires appariées ;
- parent et warm-start F2M ;
- split par ouverture grâce au JSM ;
- NumPy `1.26.4` et SciPy `1.14.1` dans un venv isolé ;
- optimisation L-BFGS jusqu'à convergence, maximum 1 000 itérations.

Le corpus JNNW/JSM est archivé avant le fit. Un échec du fit conserve ainsi
les données coûteuses et, s'il existe, le checkpoint.

## Suite autorisée

Un entraînement valide autorise seulement un écran M2 séparé :

1. M2 contre F2M en Q00 et cadence native sur un pool indépendant ;
2. garde-fou M2 contre Gen2 réparé ;
3. conversion réparée sur les cellules P3/P4 ;
4. comparaison de couverture utile entre les corpus M1-F2M et M2.

M2 ne sera promu que sur une pente de force positive, sans régression établie
sur la conversion ni contre Gen2. Ni la promotion ni la continuation M3 ne
sont automatiques.
