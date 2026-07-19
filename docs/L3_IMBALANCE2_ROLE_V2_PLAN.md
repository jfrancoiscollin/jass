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
2. exécute le runner V1 gelé pour conserver toute la recette scientifique ;
3. exige un rapport V2 valide pour chaque génération ;
4. remplace dans le manifeste final la sémantique V1 par la matrice rôle/domaine V2 ;
5. publie un résumé agrégé des buckets conversion, résilience et ancres.

## 7. Contrat d’exécution ccx33

La cible de cette lignée spécialiste est la box **ccx33** : 8 vCPU et 16 GiB RAM.

Paramètres et gardes préenregistrés :

- `PAR_GEN=8` ;
- `JASS_BUILD_JOBS=8` ;
- au moins 14 GiB RAM détectés par le runner ;
- au moins 20 GiB libres dans `JASS_RESULT_DIR` ;
- suivi de `min_mem_available_mb` toutes les 20 secondes.

Le runner spécialiste V1 ne place pas actuellement chaque processus sous une commande `timeout`. Les wrappers V2 n’annoncent donc pas une protection qui n’est pas réellement appliquée. Une absence de progression doit être détectée via les logs et le suivi de progression.

Avant P1 complet, un wrapper de sonde obligatoire est fourni :

```text
ccx33-l3-imbalance2-role-v2-probe.sh
```

La sonde exécute seulement la première génération P1 avec `PROBE=1` et `FRESH=54000`, soit exactement 3 000 records par strate logique. Elle conserve les gardes EGDB, Q00, pondération et architecture, mais elle est explicitement **non scientifique et non promotable**.

Le passage à P1 complet exige une vérification manuelle de :

- l’absence d’OOM ou de processus bloqué ;
- la mémoire minimale disponible ;
- la vitesse de production ;
- la résolution EGDB à 100 % pour `1 v 3` et `2 v 4` ;
- la présence des rapports `deterministic_role_domain_resample` ;
- l’intégrité du holdout et du manifeste V2.

Aucune durée de P1–P4 n’est annoncée avant cette micro-calibration ccx33.

## 8. Expérience recommandée

La comparaison la plus propre est un A/B apparié :

- même code de génération ;
- même G0 ou même parent immuable ;
- mêmes seeds, positions, profondeur et nombre de records ;
- seule la politique de rééchantillonnage diffère : V1 contre V2.

Mesures prioritaires :

- coût du camp avantagé `2 × loss + draw` ;
- taux de nulle et de victoire du camp désavantagé ;
- log-loss WDL non pondérée du holdout ;
- résultats par tranche : domaine exact conservé, sortie du domaine, renversement matériel ;
- non-régression sur les pools équilibrés et sur les benchmarks finaux de la lignée.

Le benchmark Gen2-MMTO / Scan reste interdit avant plateau, comme dans V1.

## 9. Généralisation L3-PURE

La même règle de calcul est aussi utilisée par un runner séparé pour la L3 initiale équilibrée. Cette intégration et ses A/B ccx33/cpx62 sont décrits dans `docs/L3_ROLE_V2_DUAL_LINEAGE_PLAN.md`. Les deux lignées partagent l’outil de calcul, mais gardent des runners, manifests et décisions de promotion indépendants.

## 10. Décision

La V2 ne remplace V1 que si elle démontre au minimum :

- meilleure résilience du camp à `-2` sans hausse des défaites évitables ;
- conversion à `+2` non régressée ;
- holdout non pondéré non régressé ;
- résultat global au moins neutre face au champion ;
- absence d’effet parasite aux transitions hors domaine.

Aucun palier, merge scientifique ou benchmark externe ne doit être déclenché automatiquement par cette PR.
