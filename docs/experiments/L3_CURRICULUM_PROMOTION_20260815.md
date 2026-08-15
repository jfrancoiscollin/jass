# CURRICULUM — promotion au rang de champion général

Enregistrement immuable. Promotion décidée par revue humaine de JFC le
15 août 2026, après le gate `cpx62-1349`, son audit `cpx62-1350`, puis la
réplication indépendante `cpx62-1352` sur un second pool disjoint.

## Identités

```text
nouveau champion   CURRICULUM  319d174f4b548b1655aad4bb30d4c6dc86c08dd715c9c23f8b19ba1937dc0be1
                   r2:jass-data/runs/cpx62-1341-jass-megacorpus-arm-d-fit-v1/
                      20260814T191555Z-18c38a33/artefacts/D-c-prior-then-current.pjtw.gz

champion précédent L2LOW       ec47e4b37fc7e95dcb390c0a5eddf207e98c0818c1708636d2df9e85b1d149b4
                   r2:jass-data/runs/cpx62-1164-l3-prior-dose-l2-refit-v1/
                      20260803T060626Z-209eb56b/artefacts/control.pjtw.gz
```

Empreintes SHA-256 du `.pjtw` **décompressé**. L'audit final `cpx62-1353`
authentifie ces deux modèles, les deux pools, les budgets et les résultats bruts.

## Comment CURRICULUM a été construit

`CURRICULUM` est le bras D de MegaCorpus, nommé
`C_PRIOR_THEN_CURRENT_2M` dans son certificat :

1. pré-entraînement C sur `MEGA_FULL_4M` ;
2. recentrage sur les 2 000 000 positions `CURRENT_2M` ;
3. cible externe alignée `CONTEXT_30` ;
4. modèle C utilisé comme moyenne du prior pendant le recentrage.

La seconde étape optimise exactement :

```text
CE_Current(CONTEXT_30) + 0.5e-5 * ||w - C||²

--exact-fold --tempo-stage
--prior-mean C --prior-decay 0
--l2 1e-5 --lbfgs-gtol 1e-4 --lbfgs-maxcor 20
```

Ce bake ne refait pas le fit : il réutilise byte pour byte le modèle certifié
de `cpx62-1341`.

## Preuve de force contre L2LOW

Chaque pool contient 3 000 ouvertures, jouées couleurs inversées : 6 000
parties par vue de recherche. Les deux pools sont certifiés disjoints entre eux
et des pools historiques imposés. Toutes les parties utilisent le même binaire
8cf exact-fold tempo-stage et les mêmes modèles.

| pool | vue | W/D/L de CURRICULUM | score | IC95 apparié | Elo indicatif |
|---|---|---:|---:|---|---:|
| `1348`, premier pool frais | Q00 d9 | 2926/317/2757 | 51,4083 % | [50,4500 ; 52,3667] % | +9,79 |
| `1348`, premier pool frais | native 0,1 s | 2894/327/2779 | 50,9583 % | [50,0750 ; 51,8500] % | +6,66 |
| `1351`, réplication indépendante | Q00 d9 | 2895/306/2799 | 50,8000 % | [49,8417 ; 51,7583] % | +5,56 |
| `1351`, réplication indépendante | native 0,1 s | 2919/350/2731 | 51,5667 % | [50,6667 ; 52,4667] % | +10,89 |

Zéro erreur sur **24 000 parties**. Les effets des deux pools sont compatibles :
`z = −0,880` en Q00 et `z = +0,943` en native.

| vue | estimateur combiné des deux pools | IC95 | Elo indicatif |
|---|---:|---|---:|
| Q00 d9 | **51,1042 %** | **[50,4265 ; 51,7818] %** | **+7,67** |
| native 0,1 s | **51,2582 %** | **[50,6263 ; 51,8902] %** | **+8,74** |

Les deux vues combinées sont établies positives. Elles satisfont a fortiori le
critère de bake `P(Elo > 0) > 95 %` sur pools chaînés, avec la garde
d'hétérogénéité verte. La réplication rend le verdict
`D_VS_L2LOW_INDEPENDENT_REPLICATION_CONFIRMED`.

## Ce que cette promotion établit — et n'établit pas

✅ **CURRICULUM est plus fort que L2LOW dans les deux vues**, sur deux pools
frais disjoints et compatibles. C'est la seule revendication nécessaire à la
succession de champion.

⚠️ **Elle n'attribue pas le gain à un facteur causal unique.** CURRICULUM et
L2LOW diffèrent par le corpus historique, le pré-entraînement, la cible
`CONTEXT_30` et le recentrage. Le contraste D−L2LOW mesure la recette complète.

⚠️ La confirmation MegaCorpus `cpx62-1347` n'a établi ni D>A ni D>C : les
estimations étaient compatibles avec zéro. Elle ne permet donc pas d'affirmer
que « tout l'historique » ou le curriculum seul explique le gain.

⚠️ Aucune nouvelle garde Gen2 ni conversion P3/P4 n'a été jouée spécifiquement
pour CURRICULUM. Ces propriétés restent celles du champion précédent jusqu'à
mesure contraire. Aucun résultat frozen n'a été lu pour cette promotion.

## Réversibilité

Promotion **purement documentaire**. Aucun artefact de l'object store n'est
modifié ; L2LOW reste immuable sous son préfixe daté et restaurable. `git revert`
du commit de bake suffit.

## Trace

- fit CURRICULUM : `r2:jass-data/runs/cpx62-1341-jass-megacorpus-arm-d-fit-v1/20260814T191555Z-18c38a33`
- confirmation D−A / D−C : `r2:jass-data/runs/cpx62-1347-jass-megacorpus-d-highn-confirmation-v1/20260815T054155Z-18c38a33`
- premier pool frais : `r2:jass-data/runs/cpx62-1348-jass-d-champion-fresh3000-pool-v1/20260815T065455Z-18c38a33`
- premier gate D−L2LOW : `r2:jass-data/runs/cpx62-1349-jass-d-vs-l2low-champion-v1/20260815T071104Z-18c38a33`
- audit du premier gate : `r2:jass-data/runs/cpx62-1350-jass-d-vs-l2low-final-audit-v1/20260815T082956Z-18c38a33`
- second pool disjoint : `r2:jass-data/runs/cpx62-1351-jass-d-champion-replication3000-pool-v1/20260815T083517Z-18c38a33`
- réplication : `r2:jass-data/runs/cpx62-1352-jass-d-vs-l2low-replication-v1/20260815T085052Z-18c38a33`
- audit final : `r2:jass-data/runs/cpx62-1353-jass-d-vs-l2low-replication-final-audit-v1/20260815T111655Z-18c38a33`
- promotion précédente : [`L3_L2LOW_PROMOTION_20260804.md`](L3_L2LOW_PROMOTION_20260804.md)
