# PRIOR — promotion au rang de champion général

Enregistrement immuable. Promotion décidée par revue humaine de JFC le
2 août 2026, selon la règle **préenregistrée avant les chiffres**
([`L3_PRIOR_MEAN_PREREGISTRATION_20260802.md`](L3_PRIOR_MEAN_PREREGISTRATION_20260802.md)).

## Identités

```text
nouveau champion  PRIOR     22e9c903fb504c0f5739a3a13cce9fb3840a6b4b62075ba9c502b785c8d35dc3
                  r2:jass-data/runs/cpx62-1147-l3-prior-mean-refit-v3/
                     20260802T082359Z-2dfdc5a7/artefacts/exact.pjtw.gz

champion précédent EXACT    d84a7fc7c3127d135d3cc150406055b9506daaa881af2959cd3721f6be66eb0a
référence figée   GEN2 (gen2-mmto), inchangée
```

Empreintes du `.pjtw` **décompressé**, comme F2M, TURNOVER et EXACT.

## Comment PRIOR a été construit

**Aucune donnée neuve, aucune capacité neuve, aucune géométrie neuve** — le
troisième gain d'affilée obtenu en retirant une contrainte fausse.

`--warm-start` ne choisit que le point de départ de l'optimiseur ; l'objectif
gardait un **L2 centré sur zéro**, ce qui affirme qu'un bucket sans données
vaut `0`. En continuation de lignée c'est faux — la meilleure estimation est
celle du parent — et cela décidait du sort de la majorité des `130 086` buckets
retenus, vus une poignée de fois : pour eux, **le régulariseur décide, pas les
données**. `--prior-mean <parent> --prior-decay 0` déplace le centre du ridge sur
le parent en laissant la précision **uniformément `l2`** (`3,000e-05`, vérifié
dans le log du fit). **Seul le centre bouge.**

Les deux bras viennent du **même job** (`cpx62-1147`) : même corpus, même parent,
`--exact-fold` des deux côtés, même environnement numérique. Le bras CONTROL
reproduit le holdout du champion au chiffre près (`0,442898`), ce qui vaut
contrôle de validité.

## Preuve de force

Règle appliquée telle qu'écrite, sans rediscussion du seuil.

| cellule | pool | n | Elo | IC95 |
|---|---|---:|---:|---|
| `cpx62-1148` découverte | `home-1004` | 6000 | `+9,15` | `[+0,4 ; +18,0]` |
| `cpx62-1149` réplication | `home-0995` (disjoint) | 6000 | `+4,17` | `[−4,6 ; +13,0]` |
| **consolidé** | deux pools | **12 000** | **`+6,66`** | **`[+0,44 ; +12,88]`** |

`5808W 614D 5578L`. IC95 consolidé excluant zéro **et** deux points de même
signe : les deux critères préenregistrés sont remplis.

### Gardes (`cpx62-1153`)

| garde | PRIOR | repères |
|---|---|---|
| non-régression Gen2 | `59,94 %`, **`+70,01 Elo`**, IC95 `[0,5870 ; 0,6118]`, deux vues positives | EXACT `+68,21` · TURNOVER `+64,19` |
| conversion `p3_mince` | `0,7600` (W228 D15 L57) | plancher `0,70` |
| conversion `p4_egal` | `0,7433` (W223 D19 L58) | plancher `0,70` |

`SUCCESSION_GUARDS_GREEN`. Le plancher `0,70` est **sous la plus basse valeur
honnête jamais mesurée** (`0,7133`, EXACT p4) ; le `0,95` historique était
calibré sur le repère de juillet, démonté le 1er août.

## ⚠️ Ce que cette promotion n'établit pas

- **Le chiffre consolidé est BIAISÉ VERS LE HAUT**, et c'était écrit avant de le
  connaître. `cpx62-1148` est la mesure de **découverte** ; un effet retenu parce
  qu'il franchit zéro de justesse surestime sa taille. Le point est d'ailleurs
  tombé de `+9,15` à `+4,17` à la réplication — le rétrécissement attendu.
  **L'effet vrai est vraisemblablement plus proche de `+4` que de `+6,66`.**
  Borne basse consolidée : `+0,44 Elo`. À ne pas sur-citer.
- **Un seul point de l'axe.** `--prior-decay 0` est *un* réglage. Le prior
  bayésien fut le mécanisme de production de l'ère gen1/gen2 (`0545`…`0555`, dont
  un balayage de λ), calibré alors sur du **100 % frais** ; le corpus est
  aujourd'hui un **mélange 1:1**, dont la moitié mémoire **EST le parent
  réinjecté comme donnée**. Un prior centré sur le parent risque donc de le
  **compter deux fois**, et le λ d'alors ne se transporte pas. La dose-réponse
  reste à faire ([`../L3_BACKLOG.md`](../L3_BACKLOG.md) §3.2).
- **`--hier-l2` n'est pas testé** : même famille, mécanisme différent (reculer
  vers la moyenne du pattern). Backlog §3.1.
- **Rien sur Scan, rien au-delà de d8, rien hors 8cf.**

## Réversibilité

Promotion **purement documentaire**, comme F2M (`3db4506f`), TURNOVER
(`54c9dc39`) et EXACT (`52e8a448`). Aucun artefact de l'object store n'est
modifié ; EXACT reste immuable et restaurable. `git revert` suffit.

## Trace

- refit deux bras : `r2:jass-data/runs/cpx62-1147-l3-prior-mean-refit-v3/20260802T082359Z-2dfdc5a7`
- découverte : `r2:jass-data/runs/cpx62-1148-l3-prior-vs-control-gate-v2`
- réplication : `r2:jass-data/runs/cpx62-1149-l3-prior-gate-pool2-v1`
- gardes : `r2:jass-data/runs/cpx62-1153-l3-prior-succession-guards-v1`
