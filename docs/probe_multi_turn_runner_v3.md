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

Le wrapper reprend les totaux de shards, le quota G1 et les plafonds de
concurrence ccx33 utilisés par `0756`. Les paramètres scientifiques restent
ceux du lanceur natif : 300 parties par shard, profondeur de jeu 10, arbitre
14, ancre 0,05, conversion 10, 300 ouvertures et gate profondeur 9.

## Résultat effectif T2 — `ccx33-0762`

Le run T2 natif terminé le 17 juillet 2026 a publié :

```text
r2:jass-data/runs/ccx33-0762-probe-t2-adj-g1-v2/20260717T115602Z-f5410cbf
```

Verdict du manifeste de promotion :

- `tour=T2` ;
- `promotion_decision=promote` ;
- `scientific_status=continue_probe` ;
- aucune raison de veto ;
- candidat sémantique SHA-256
  `f8f12c057640eaaec9e8dc4245fafea7efc38617416ef0e1ca327430f633bbf3`.

Télémétrie de conversion :

| Mesure | T2 |
|---|---:|
| globale | 0,657375 |
| p1 net | 0,824176 |
| p2 moyen | 0,554455 |
| p3 mince | 0,494444 |
| p4 égal | 0,565217 |

Gates généralistes :

| Adversaire | Score | IC 95 % | n | Elo central | Décision |
|---|---:|---:|---:|---:|---|
| parent T1-bis | 0,4725 | [0,432586 ; 0,512414] | 600 | -19,13 | pass |
| référence fixe | 0,4900 | [0,450 ; 0,530] | 600 | -6,95 | pass |

Le point central n'établit pas un gain de force, mais les deux intervalles de
confiance recouvrent l'équilibre et aucun veto du régime jeune n'est déclenché.
La décision protocolaire est donc de terminer la sonde avec T3.

## Lancer T3 depuis le T2 promu

Le job GitOps de campagne est `ccx33-0769-probe-t3-adj-g1-v1` et fournit :

```bash
export TOUR=T3
export PROBE_PARENT_RUN_PREFIX='r2:jass-data/runs/ccx33-0762-probe-t2-adj-g1-v2/20260717T115602Z-f5410cbf'
exec bash jobs/templates/probe-adj-g1-next-tour-runner-v3.sh
```

T3 accepte uniquement ce parent dont le manifeste porte `tour=T2`,
`promotion_decision=promote` et `scientific_status=continue_probe`. La recette,
les références, les quotas, les profondeurs et les gates restent inchangés.
Le gate jeune de T3 doit publier `scientific_status=complete_probe`, ce qui clôt
la sonde multi-tours et permet le verdict final sur la trajectoire T1-bis→T2→T3.
