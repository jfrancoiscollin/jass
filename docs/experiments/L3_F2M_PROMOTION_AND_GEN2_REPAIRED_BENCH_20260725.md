# Promotion L3-PURE F2M et benchmark Gen2 réparé

Date : 25 juillet 2026.

## Décision L3-PURE

Après autorisation humaine explicite, F2M devient le champion de la lignée
`L3-PURE`. Cette promotion interne ne remplace pas encore le champion général
historique `gen2-mmto`.

Les preuves sont :

- conversion réparée : `97,33 %` sur `p3_mince` et `98,33 %` sur `p4_egal` ;
- écran 0963 contre C0 : `60,00 %` en Q00 et `60,25 %` en cadence native ;
- confirmation indépendante 0964 contre C0 :
  - Q00 : `595-17-388`, score `60,35 %`,
    IC95 `[57,35 ; 63,35]` ;
  - native : `591-17-392`, score `59,95 %`,
    IC95 `[56,94 ; 62,96]` ;
- aucune régression établie contre R2M :
  `50,70 %` en Q00 et `49,85 %` en cadence native ;
- couverture supérieure au parent C0.

F2M est donc le parent prévu de M2, indépendamment du résultat du benchmark
général, sauf incident scientifique nouveau.

## Pourquoi le benchmark Gen2 historique ne suffit pas

Les précédents matchs contre Gen2 utilisaient volontairement le binaire
historique 32cf afin de conserver un défenseur fixe. Ce binaire précédait les
correctifs de légalité et de terminaison racine. Le score F2M de `91,00 %`
contre ce Gen2 ne peut donc pas attribuer équitablement le titre général.

## Protocole 0965 préenregistré

Le benchmark construit depuis le même SHA réparé :

- un moteur F2M 8cf ;
- un moteur Gen2-mmto 32cf ;
- les mêmes paramètres Q00, le même EGDB et les mêmes règles de partie.

Les 500 ouvertures sont nouvelles, uniques, appariées par couleur et sans
recouvrement avec DILF ni les quatre pools synthétiques antérieurs. Chaque vue
contient 1 000 parties :

1. profondeur 9 avec Q00 ;
2. cadence native `0,1 s/coup` avec Q00.

F2M n’est recommandé comme nouveau champion général que si la borne basse à
95 % dépasse `50 %` dans les deux vues. Sinon Gen2 conserve son titre par
incumbence. Le résultat n’autorise automatiquement ni promotion générale ni
lancement de M2.

## Verdict 0965 et décision humaine

`home-0965` a terminé sur 500 nouvelles ouvertures, soit 1 000 parties par
vue, avec le moteur réparé construit depuis le même SHA des deux côtés :

- Q00 : `562-21-417`, score F2M `57,25 %`,
  IC95 `[54,22 ; 60,28]`, environ `+50,7 Elo` ;
- cadence native : `580-12-408`, score F2M `58,60 %`,
  IC95 `[55,57 ; 61,63]`, environ `+60,4 Elo`.

Les deux bornes basses dépassent 50 %. Après revue humaine et autorisation
explicite, **F2M devient le champion général courant**. `gen2-mmto` reste le
champion historique figé et un garde-fou externe.

F2M devient aussi le parent immuable de M2. Le protocole M2 est décrit dans
[`L3_PURE_M2_PROTOCOL_20260725.md`](L3_PURE_M2_PROTOCOL_20260725.md).
