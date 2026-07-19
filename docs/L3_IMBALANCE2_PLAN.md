# L3-IMBALANCE2 — lignée spécialisée dans les positions à deux pions d’écart

> **Version 1.0 — 19 juillet 2026**  
> **Statut : implémentation préparée, aucun job mis en queue**

## 1. But

L3-IMBALANCE2 est une lignée indépendante de L3-PURE. Elle apprend uniquement à
partir de parties dont la position de départ comporte des pions simples et un
écart matériel exact de deux pions. Les dix-huit strates sont :

`1 v 3`, `2 v 4`, `3 v 5`, `4 v 6`, `5 v 7`, `6 v 8`, `7 v 9`, `8 v 10`,
`9 v 11`, `10 v 12`, `11 v 13`, `12 v 14`, `13 v 15`, `14 v 16`,
`15 v 17`, `16 v 18`, `17 v 19`, `18 v 20`.

Les deux couleurs occupent alternativement le rôle avantagé, et le trait est
également équilibré. Une génération contient exactement 500 000 records, avec
un shard dédié à chacune des 18 strates ; les 14 premiers shards produisent
27 778 records et les quatre derniers 27 777.

La spécialisation porte sur la **distribution de départ**. Après le premier
coup, les captures, promotions et transitions de phase réellement jouées sont
conservées. Filtrer les positions intermédiaires pour ne garder que les états où
l’écart vaut encore deux casserait le retour Monte-Carlo terminal et créerait
une population artificielle.

## 2. Contrat scientifique

Le contrat P1 est celui de la PR #358, sauf la distribution de départ :

- G0 matériel homme=1, dame=3, autres termes à zéro ;
- 500 000 records frais par génération ;
- d8 pour G1–G4 ;
- fingerprint Q00 complet de 63 paramètres ;
- 8 plies aléatoires, epsilon 8 %, décroissance au ply 60 ;
- WDL terminal uniquement et champ score constamment nul ;
- EGDB exacte seulement après atteinte naturelle ;
- parties au ply-cap entièrement censurées ;
- fit logistique WDL, color-fold, tempo-stage, L2 `3e-5` ;
- G1 optimisé depuis zéro, générations suivantes warm-startées ;
- géométrie 8cf ;
- aucun teacher, replay, relabel, MMTO, frontière ou adjudication ;
- seed primaire `271828` ;
- aucune promotion ni continuation automatique.

Scan ne fournit aucune donnée d’entraînement : aucune position Scan, aucun coup,
aucun score et aucun résultat Scan n’entrent dans le corpus ou dans le fit.

## 3. Paliers

| Palier | Générations | Recherche de jeu | Parent |
|---|---:|---:|---|
| P1 | G1–G4 | d8 | G0 matériel |
| P2 | G5–G8 | d10 | G4 immuable |
| P3 | G9–G12 | d12 | G8 immuable |
| P4 | G13–G16 | d14 | G12 immuable |

Chaque palier est un job séparé. P2, P3 et P4 exigent l’URI immuable et le
SHA-256 gzip du dernier modèle du palier précédent. Aucun wrapper ne chaîne le
palier suivant.

## 4. Règle d’arrêt : équivalence W/D/L avec Scan

Après chaque palier, le candidat et Scan jouent séparément le côté avantagé
contre le **même défenseur fixe**, sur les mêmes positions et au même budget de
recherche. Le benchmark utilise deux pools indépendants A et B, chacun équilibré
sur les dix-huit strates et sur les couleurs.

Un pool passe lorsque :

- l’écart ponctuel candidat−Scan sur chacun des taux W, D et L est au plus 3
  points globalement ;
- les IC bootstrap appariés à 95 % restent dans ±5 points ;
- chaque strate contient au moins 20 paires valides et aucun taux ne diffère de
  plus de 10 points ;
- aucune erreur moteur n’est tolérée.

La lignée est arrêtée uniquement si les **deux pools indépendants** passent :
`STOP_LINEAGE_SCAN_EQUIVALENT`. Sinon le verdict est `CONTINUE_NEXT_PHASE` et le
palier suivant peut être préparé après lecture humaine. Si P4 échoue encore, le
runner s’arrête tout de même : prolonger au-delà de G16 requiert une nouvelle
décision scientifique, pas une continuation implicite.

## 5. Fichiers préparés

- `jobs/tools/make_imbalance2_pools.py` : pools déterministes par strate et deux
  pools de benchmark indépendants ;
- `jobs/templates/l3-imbalance2-runner-v1.sh` : runner P1–P4 ;
- `jobs/tools/imbalance2_scan_gate.py` : matchs et agrégation d’équivalence ;
- `jobs/templates/l3-imbalance2-scan-gate-v1.sh` : verdict deux pools ;
- `jobs/prepared/l3-imbalance2-20260719/` : wrappers hors queue ;
- tests de contrat, syntaxe et génération des pools.
