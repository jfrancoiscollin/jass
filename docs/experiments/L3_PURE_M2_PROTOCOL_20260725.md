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

Le premier essai `home-0966` s'est arrêté avant la génération : la suite de
tests du contrat stub sans EGDB avait été exécutée par erreur dans le build
scientifique avec EGDB activé. `home-0966bis` sépare désormais le build de
tests sans EGDB du binaire de production avec EGDB. Aucun corpus ni résultat
scientifique de 0966 n'est réutilisé.

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

## Écran 0967 préenregistré

`home-0967` utilise 500 nouvelles ouvertures uniques, appariées par couleur,
sans recouvrement avec les pools précédents. Il produit 1 000 parties par vue
pour M2 contre F2M et M2 contre Gen2 réparé :

- profondeur 9 avec Q00 ;
- cadence native à 0,1 seconde par coup.

La conversion est rejouée sur les 300 positions corrigées de `p3_mince` et
les 300 de `p4_egal`, contre le même défenseur Gen2. La couverture compare les
corpus exacts F2M et M2, tous deux de 2 millions de positions.

La promotion n'est recommandée à la revue humaine que si la borne basse à
95 % de M2 contre F2M dépasse 50 % dans les deux vues et si tous les
garde-fous passent. Deux scores ponctuels positifs sans preuve dans les deux
vues ouvrent seulement une confirmation indépendante. Sinon la recette d8
est considérée comme plate et la prochaine expérience recommandée devient un
bras causal d10 à volume constant. Aucune décision n'est automatique.

## Incident 0967 et relance 0970

`home-0967` a passe les sources immuables et les builds, puis s'est arrete
avant tout match dans `validate_opening_pool.py` : le generateur avait produit
un pool candidat ne satisfaisant pas directement la contrainte stricte
d'unicite/disjonction. Aucun resultat M2 n'a donc ete mesure par 0967.

`home-0970` conserve le protocole scientifique et la seed. La seule correction
est technique : generer 2 000 candidats, les filtrer dans l'ordre de facon
deterministe contre les doublons et tous les pools exclus, puis retenir les
500 premiers. Le manifeste publie le hash du sur-echantillon, le hash des
500 positions retenues et les compteurs de rejet.

Le premier claim de `home-0970` a utilise un snapshot de controle anterieur
au dernier pin SHA et s'est arrete immediatement au garde-fou
`code SHA mismatch`, avant tout calcul. `home-0970bis` est la relance
autoritative sur le SHA qui contient a la fois la selection robuste et la
generation v4 du defenseur historique dans son propre arbre source.
