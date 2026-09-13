# Sonde ADJ+G1 multi-tours — rapport final T1-bis à T3

Date : 17 juillet 2026. Statut : sonde close.

Ce rapport consolide les éléments préparatoires des PR #338 et #339 avec le verdict publié dans `docs/CURRENT.md`. La recette scientifique, les références, les quotas et les gates sont restés inchangés entre les tours ; seul le candidat promu du tour précédent est devenu le parent du tour suivant.

## Traçabilité des runs

| Tour | Run | Conversion globale | Statut scientifique |
|---|---|---:|---|
| T1-bis | `ccx33-0756-t1bis-adj-g1-native-full-v2` | 0,667 | `continue_probe` |
| T2 | `ccx33-0762-probe-t2-adj-g1-v2` | 0,657375 | `continue_probe` |
| T3 | `ccx33-0769-probe-t3-adj-g1-v1` | 0,669 | `complete_probe` |

Préfixes R2 exacts conservés par la chaîne :

```text
r2:jass-data/runs/ccx33-0756-t1bis-adj-g1-native-full-v2/20260717T074749Z-6d90e72d
r2:jass-data/runs/ccx33-0762-probe-t2-adj-g1-v2/20260717T115602Z-f5410cbf
r2:jass-data/runs/ccx33-0769-probe-t3-adj-g1-v1/20260717T145848Z-1b907771
```

Pour T2, les empreintes publiées dans les PR #338/#339 sont :

```text
candidate logical SHA-256:
f8f12c057640eaaec9e8dc4245fafea7efc38617416ef0e1ca327430f633bbf3

candidate archive SHA-256:
8267cfe4578a0274bc7224af2839ee55a54246976e599d713749ab967dddae48
```

Aucune autre empreinte de candidat n'est reproduite ici : les sources documentaires du dépôt ne donnent pas d'autre SHA-256 complet à archiver, et ce rapport n'en déduit aucun.

## Résultats

La trajectoire de conversion est :

```text
0,667 → 0,657 → 0,669
```

Les gates de T3 sont plats :

- contre le parent T2 : `0,4967`, IC 95 % `[0,457 ; 0,537]` ;
- contre la référence fixe T0 : `0,5033`, IC 95 % `[0,463 ; 0,543]`.

Les paliers de conversion T3 sont :

| Palier | T3 |
|---|---:|
| p1 | 0,841 |
| p2 | 0,609 |
| p3 | 0,489 |
| p4 | 0,513 |

À titre de filiation, T2 avait publié une conversion globale de `0,657375`, avec p1 `0,824176`, p2 `0,554455`, p3 `0,494444` et p4 `0,565217`. Ses gates étaient `0,4725` contre T1-bis et `0,4900` contre T0, tous deux admis par le protocole jeune.

## Verdict

Le fork (a) ne compose pas. T1-bis, T2 et T3 sont plats en conversion comme sur les gates généralistes : trois tours de labels adjudicated n'accumulent aucun gain mesurable. T3 clôt proprement la sonde avec `scientific_status=complete_probe`; la chaîne de filiation a été vérifiée, donc ce résultat est scientifique et non un incident de runner.

Référence actuelle : `docs/CURRENT.md`. Les PR #338 et #339 ne sont que les documents préparatoires remplacés par ce rapport final.
