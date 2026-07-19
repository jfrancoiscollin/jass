# L3-IMBALANCE2 — pondération rôle/domaine V2

Statut : **protocole préparé pour ccx33, aucun job scientifique lancé**.

## 1. Objet

Cette variante conserve intégralement la lignée L3-IMBALANCE2 V1 (18 strates `n v n+2`, teacher EGDB exact pour `1 v 3` et `2 v 4`, rollouts autonomes au-delà, géométrie 8cf, Q00, WDL terminal, holdout non pondéré), mais remplace la pondération globale du résultat du camp initialement avantagé par une pondération **par position, par rôle et par domaine courant**.

L’objectif est double :

- **conversion** : pénaliser les nulles et surtout les défaites lorsque le camp au trait possède actuellement deux pions de plus ;
- **résilience** : récompenser les nulles et surtout les victoires lorsque le camp au trait possède actuellement deux pions de moins.

## 2. Domaine exact

Le multiplicateur spécialisé n’est appliqué qu’aux records vérifiant simultanément :

- écart absolu de **deux pions simples** ;
- même nombre de dames pour les deux camps.

Le domaine est recalculé indépendamment pour chaque position à partir des bitboards du record. Les positions sorties de ce domaine — échange réduisant l’écart, promotion, déséquilibre de dames, renversement matériel différent — restent des **ancres de poids 1**.

Cette règle empêche le résultat final d’une partie rare de surpondérer toute la trajectoire, y compris les positions qui ne sont plus des positions « deux pions d’écart ».

## 3. Matrice préenregistrée

Le WDL du fichier JNNW est exprimé du point de vue du camp au trait.

| Rôle courant du camp au trait | Victoire | Nulle | Défaite |
|---|---:|---:|---:|
| deux pions de plus — conversion | `1` | `2` | `4` |
| deux pions de moins — résilience | `4` | `2` | `1` |
| hors domaine exact | `1` | `1` | `1` |

Interprétation :

- résultat matériellement attendu : poids `1` ;
- nulle : poids `2` ;
- renversement du résultat attendu : poids `4`.

Le rééchantillonnage reste déterministe, conserve exactement le nombre de records d’entraînement et ne touche pas au holdout final.

## 4. Différence réelle avec V1

Sur une partie qui reste constamment dans le domaine exact et conserve le même camp avantagé, la matrice V2 produit mathématiquement le même multiplicateur global `1 / 2 / 4` que V1 : les positions du défenseur et de l’attaquant reçoivent le même poids de partie vu depuis leurs rôles opposés.

Le gain méthodologique de V2 vient donc précisément de quatre changements :

1. la pondération est limitée aux positions réellement dans le domaine exact ;
2. le rôle est recalculé sur la position courante, y compris après un renversement matériel ;
3. conversion et résilience sont auditées séparément dans les rapports ;
4. le format prépare une future V3 de **criticité par coup** sans modifier une nouvelle fois la sémantique des rôles.

Cette PR ne prétend donc pas qu’un simple miroir de la matrice crée à lui seul un nouveau signal sur les trajectoires parfaitement propres. Elle supprime surtout la contamination hors domaine et rend le crédit défensif explicite et mesurable.

## 5. Ce qui n’est pas inclus

Cette V2 n’effectue pas encore :

- de recherche profonde du meilleur coup pour mesurer la criticité ;
- de récompense supplémentaire pour le seul coup conservant la nulle ;
- de relabellisation teacher des coups joués ;
- de changement de la cible WDL, de la loss logistique ou de l’architecture PJTW ;
- de mélange avec Gen2-MMTO ou Scan pendant l’entraînement.

Une éventuelle V3 « critical defence » devra être une expérience séparée, fondée sur un teacher figé et un budget de recherche préenregistré.

## 6. Implémentation

`prepare_imbalance2_training.py reweight` conserve par défaut le comportement V1. Le comportement V2 n’est activé que par :

```bash
IMBALANCE2_REWEIGHT_POLICY=role-aware-v2
```

Le wrapper `jobs/templates/l3-imbalance2-runner-v2.sh` :

1. active explicitement cette politique ;
2. exécute le runner V1 pour conserver toute la recette scientifique ;
3. exige un rapport V2 valide pour chaque génération ;
4. remplace dans le manifeste final la sémantique V1 par la matrice rôle/domaine V2 ;
5. publie un résumé agrégé des buckets conversion, résilience et ancres ;
6. impose et publie les pools indépendants communs A64/B64.

Le générateur de pools sépare désormais :

- la seed d’entraînement, toujours `271828` ;
- la seed des pools plateau, fixée à `161803` ;
- les benchmarks finaux, qui restent construits depuis la seed d’entraînement historique.

Changer la seed plateau ne modifie donc ni les seeds de self-play, ni les pools d’entraînement, ni les benchmarks finaux.

## 7. Contrat d’exécution ccx33

La cible de cette lignée spécialiste est la box **ccx33** : 8 vCPU et 16 GiB RAM.

Paramètres et gardes préenregistrés :

- `PAR_GEN=8` ;
- `JASS_BUILD_JOBS=8` ;
- au moins 14 GiB RAM détectés par le runner ;
- au moins 20 GiB libres dans `JASS_RESULT_DIR` ;
- suivi de `min_mem_available_mb` toutes les 20 secondes ;
- `PLATEAU_PER_STRATUM=64` ;
- `IMBALANCE2_PLATEAU_SEED=161803`.

Le runner spécialiste V1 ne place pas actuellement chaque processus sous une commande `timeout`. Les wrappers V2 n’annoncent donc pas une protection qui n’est pas réellement appliquée. Une absence de progression doit être détectée via les logs et le suivi de progression.

Avant P1 complet, un wrapper de sonde obligatoire est fourni :

```text
ccx33-l3-imbalance2-role-v2-probe.sh
```

La sonde exécute seulement la première génération P1 avec `PROBE=1` et `FRESH=54000`, soit exactement 3 000 records par strate logique. Elle conserve les gardes EGDB, Q00, pondération, architecture et publication A64/B64, mais elle est explicitement **non scientifique et non promotable**.

Le passage à P1 complet exige une vérification manuelle de :

- l’absence d’OOM ou de processus bloqué ;
- la mémoire minimale disponible ;
- la vitesse de production ;
- la résolution EGDB à 100 % pour `1 v 3` et `2 v 4` ;
- la présence des rapports `deterministic_role_domain_resample` ;
- l’intégrité du holdout et du manifeste V2 ;
- les SHA-256 et le compte de 1 152 positions pour chacun des pools A64/B64.

Aucune durée de P1–P4 n’est annoncée avant cette micro-calibration ccx33.

## 8. Campagne P1 combinée : re-assess V1 + nouvelle V2

Le premier assess plateau de la P1 historique `ccx33-0847` était sous-puissant : 8 positions par strate, soit 144 positions par pool. Le nouveau protocole utilise **64 positions par strate**, donc **1 152 positions par pool**.

Deux pools indépendants sont produits une seule fois par la P1 V2 :

- `plateau-a`, seed plateau `161803 + 15485863` ;
- `plateau-b`, seed plateau `161803 + 179424673`.

Leurs fichiers JNNW, métadonnées, tailles et SHA-256 sont publiés avant la comparaison. Les mêmes octets sont ensuite utilisés pour les huit modèles :

- V1 historique `0847` : G1, G2, G3 et G4 ;
- nouvelle lignée role-aware V2 : G1, G2, G3 et G4.

L’évaluation candidate-only est effectuée à d10, Q00 complet et cap 400 plies. Elle représente :

```text
8 modèles × 2 pools × 1 152 positions = 18 432 parties
```

Le wrapper préparé est :

```text
cpx62-l3-imbalance2-p1-v1-v2-a64-compare.sh
```

Il exige les préfixes immuables et les identifiants exacts des deux jobs sources. Il vérifie les manifests et les SHA des huit modèles, puis publie :

- le re-assess plateau V1 G1→G4 ;
- le plateau V2 G1→G4 ;
- les deltas appariés V2−V1 pour G1, G2, G3 et G4 ;
- les résultats séparés sur A64 et B64 ;
- les rapports bruts candidate-only ;
- une recommandation de revue non exécutable automatiquement.

Le lead V2 au terme de P1 n’est déclaré que si, sur G4 :

- l’amélioration du coût `2L+D` est au moins `0,02` ;
- la borne haute de l’IC bootstrap apparié est au plus zéro ;
- le delta ponctuel est non positif sur chacun des deux pools.

Même dans ce cas, `promotion_authorized=false`, `p2_authorized=false` et `automatic_next_job=null`. Le résultat doit être revu avant P2 ou avant un gate externe.

## 9. Lecture scientifique

La campagne répond à trois questions distinctes :

1. la V1 historique était-elle réellement au plateau sur des pools suffisamment puissants ?
2. la V2 continue-t-elle d’apprendre de G1 à G4 ?
3. la V2-G4 est-elle meilleure que la V1-G4 sur exactement les mêmes positions ?

Cette séparation évite de confondre l’effet de la taille des pools, une nouvelle réalisation de self-play et l’effet de la pondération role-aware.

Mesures prioritaires :

- coût du camp avantagé `2 × loss + draw` ;
- taux de nulle et de victoire du camp désavantagé ;
- log-loss WDL non pondérée du holdout ;
- résultats par tranche : domaine exact conservé, sortie du domaine, renversement matériel ;
- résultats globaux, par pool et par strate ;
- non-régression sur les pools équilibrés et sur les benchmarks finaux de la lignée.

Le benchmark Gen2-MMTO / Scan reste interdit avant plateau, comme dans V1.

## 10. Généralisation L3-PURE

La même règle de calcul est aussi utilisée par un runner séparé pour la L3 initiale équilibrée. Cette intégration et ses A/B ccx33/cpx62 sont décrits dans `docs/L3_ROLE_V2_DUAL_LINEAGE_PLAN.md`. Les deux lignées partagent l’outil de calcul, mais gardent des runners, manifests et décisions de promotion indépendants.

## 11. Décision

La V2 ne remplace V1 que si elle démontre au minimum :

- meilleure résilience du camp à `-2` sans hausse des défaites évitables ;
- conversion à `+2` non régressée ;
- holdout non pondéré non régressé ;
- résultat apparié G4 au moins neutre, et idéalement meilleur, sur A64 et B64 ;
- résultat global au moins neutre face au champion lors d’un gate ultérieur autorisé ;
- absence d’effet parasite aux transitions hors domaine.

Aucun palier, merge scientifique ou benchmark externe ne doit être déclenché automatiquement par cette PR.
