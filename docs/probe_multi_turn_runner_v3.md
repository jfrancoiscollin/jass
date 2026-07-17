# Sonde ADJ+G1 multi-tours sur runner v3

## Objet

Cette chaîne implémente le fork (a) figé dans la revue v3.2 :

```text
T1-bis promu
→ T2 avec le candidat T1-bis comme parent
→ T3 avec le candidat T2 comme parent
→ verdict de sonde
```

La recette scientifique ne change pas entre les tours. Seul le parent générateur
est remplacé par le candidat promu du tour précédent.

## Invariants

À T2 et T3, le chargeur :

- recharge le bundle immutable `inputs/t1bis-adj-g1/v1` ;
- conserve `fixed.pjtw.gz` comme référence T0/bootstrap ;
- conserve `gen2`, les seeds, G1 et la jauge p1–p4 ;
- exige un résultat runner-v3 terminé avec `_SUCCESS`, `state=completed` et
  `exit_code=0` ;
- vérifie `inventory.json`, `checksums.sha256`, le candidat et le manifeste de
  promotion ;
- exige `promotion_decision=promote` et `scientific_status=continue_probe` ;
- exige la filiation exacte `T1-bis→T2` ou `T2→T3` ;
- remplace uniquement `parent.pjtw.gz`.

Le manifeste de promotion publié par les nouveaux tours contient les SHA-256
réels du candidat, du parent et de la référence fixe.

## Lancer T2 après le résultat 0756

Le résultat promu de T1-bis est :

```text
r2:jass-data/runs/ccx33-0756-t1bis-adj-g1-native-full-v2/20260717T074749Z-6d90e72d
```

Le job GitOps `jass-control` doit seulement fournir :

```bash
export TOUR=T2
export PROBE_PARENT_RUN_PREFIX='r2:jass-data/runs/ccx33-0756-t1bis-adj-g1-native-full-v2/20260717T074749Z-6d90e72d'
exec bash jobs/templates/probe-adj-g1-next-tour-runner-v3.sh
```

Le wrapper reprend les totaux de shards, la quota G1 et les plafonds de
concurrence ccx33 utilisés par `0756`. Les paramètres scientifiques restent
ceux du lanceur natif : 300 parties par shard, profondeur de jeu 10, arbitre
14, ancre 0,05, conversion 10, 300 ouvertures et gate profondeur 9.

## Lancer T3

Après un T2 vert, utiliser son `result_uri` comme nouvelle valeur :

```bash
export TOUR=T3
export PROBE_PARENT_RUN_PREFIX='<result_uri du T2 promu>'
exec bash jobs/templates/probe-adj-g1-next-tour-runner-v3.sh
```

T3 accepte uniquement un parent dont le manifeste de promotion porte
`tour=T2`, `promotion_decision=promote` et `scientific_status=continue_probe`.
Le gate jeune de T3 produit ensuite `scientific_status=complete_probe`.
