# ED5 Q200k — résultat terminal du bloc D

Résultat du 15 septembre 2026, relu indépendamment le 21 septembre 2026.
Le [préenregistrement k=2](L3_ED5_Q200K_TEACHER_CHOICE_SET_PREREG_V1_20260914.md)
modifiait un seul axe : les ensembles de meilleurs coups TRAIN provenaient
du teacher Q200k. Aucun paramètre n'a été ajusté à partir de cette confirmation.

## Identité et publication

- Job : `cpx62-1997-l3-ed5-fresh-d-confirmation-production-v1`.
- Tentative : `20260915T194938Z-89d64dbc`.
- Code : `89d64dbc85300399d5e7b830389cc0030a023967`.
- Candidat : `ED5_Q200K_CHOICE.pjtw`, SHA256 `f4e35ad02704f822614eb5a0be6ce33fa21f7187c452cbef7819f91242812ea5`.
- Source D : `cpx62-1990-l3-ed5-fresh-d-source-production-v2` / `20260915T155218Z-f746408f`.
- Disjointness : `cpx62-1995-l3-ed5-fresh-dws-historical-disjointness-rehearsal-v3` / `20260915T185720Z-b64ae6e8`.
- Spécification commune : `23a232ee9cd5999526001e221f1fef8aef45aa6746d84ff2408f98838c4014fb`.
- Reçu de lancement : `97b9c3bf5a605375754549d6cee1606f2b8e36445db9c345a987fb5af2e7d5e7`.

La publication est `completed`, exit 0. La relecture vérifie le marqueur
`_SUCCESS`, l'identité job/tentative/code, le manifeste, l'inventaire, les sommes
de contrôle et sept fichiers sélectionnés. Leurs tailles et empreintes sont
revérifiées après transfert local. Le résumé reproduit exactement le readout,
le reçu de lancement et les empreintes des sorties sélectionnées concordent.
Les 24 régressions publiées passent sans erreur, échec ni test ignoré.

[Reçus ED4 et ED5](../operations/EVAL_SEARCH_ED4_ED5_TERMINAL_READBACK_20260921.json),
SHA256 `6c5c3ea3cc373e1c8be315a3b955b9290dacffa4df442613ecefe19ce5baf5cd`.
Cette relecture n'ouvre aucune cible W/S ni donnée brute de confirmation.

## Résultat confirmatoire gelé

512 parents, 64 par cellule phase × STM ; Scan Q200k ; bootstrap stratifié
par parent, 20 000 réplications. Alpha k=2 : 0,0125 ; alpha D dépensé :
`0.004166666666666667` ; niveau unilatéral : `0.9958333333333333`.
Seeds BASE/HARD/SOFT : `202609141101` / `202609141102` / `202609141103`.

| Bras | Regret moyen | Top-hit |
| --- | ---: | ---: |
| BASE | 433.90234375 | 0.2578125 |
| CANDIDATE | 449.7265625 | 0.251953125 |
| HARD | 431.951171875 | 0.283203125 |
| SOFT, descriptif | 412.421875 | 0.27734375 |

L'amélioration est définie comme le regret du contrôle moins celui du candidat.

| Contraste | Moyenne | Borne inférieure obligatoire | Borne supérieure descriptive | Améliorés / dégradés | Delta top-hit |
| --- | ---: | ---: | ---: | ---: | ---: |
| Candidat vs BASE | -15.82421875 | -129.7109619140625 | 100.67226562500002 | 72 / 85 | -0.005859375 |
| Candidat vs HARD | -17.775390625 | -130.435986328125 | 98.76346842447919 | 81 / 106 | -0.03125 |

Les quatre gates obligatoires échouent : les deux bornes inférieures de gain
de regret ne sont pas positives, le top-hit est inférieur au meilleur contrôle
obligatoire, et les dégradations face à BASE dépassent les améliorations.
Cela n'établit pas un effet exactement nul ; le support confirmatoire requis
pour ED5 n'est pas obtenu. Scan reste une référence, pas une vérité exacte.

```text
block_verdict = ED5_FRESH_D_CONFIRMATION_NOT_SUPPORTED_V1
scientific_verdict = CAMPAIGN_ATTEMPT_SCIENTIFIC_NOT_SUPPORTED_V1
next_stage = STOP_ED5_K2_SCIENTIFIC_NOT_SUPPORTED
confirmation_target_consumed = true
alpha_spent = 0.004166666666666667
```

## Coût et disposition

4 749 lectures de cible, 4 744 recherches Scan, 948 800 000 nœuds demandés ;
mur teacher 24,632 s avec huit workers. Aucun fit, recherche Jass, match,
self-play, promotion ou bake dans cette confirmation.

D est définitivement consommé. Les cibles confirmatoires W/S ED5 restent
interdites pour sauver cette tentative. Aucun second bootstrap, réglage,
extension ou scale-up ED5 n'est autorisé par ce résultat.

ED4 k=1 et ED5 k=2 sont clos scientifiquement ; leur dépense alpha D cumulée
est `0.0125`, sans remise à zéro ni recyclage. La campagne
[CLS](L3_CLOSED_LOOP_STRENGTH_CAMPAIGN_V1_20260910.md) constitue la suite
opérationnelle active, scientifiquement distincte. Aucun k=3 eval/search
parallèle n'est lancé. `CURRICULUM` reste champion.
