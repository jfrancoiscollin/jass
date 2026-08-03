# Dose du prior — règle de décision PRÉENREGISTRÉE

Écrite le 3 août 2026 **avant** que `cpx62-1164` ne soit lancé, sur go de JFC.
Aucun seuil ne sera rediscuté une fois les chiffres connus.

## La question, corrigée par la lecture du code

JFC demandait une dose-réponse sur « la force du prior », en soupçonnant que le
`λ` calibré à l'ère **100 % frais** ne se transporte pas au **mélange 1:1**
actuel, où la moitié mémoire **est** le parent réinjecté comme donnée — donc où
un prior centré sur le parent risque de le **compter deux fois**.

La lecture de `train_stream.py:637-641` déplace la question. La précision du
prior vaut :

```
prec_j = l2 + decay · λ · (visites_j / N)
```

⛔ **À `--prior-decay 0` — la recette championne — `λ` est strictement inerte**
(`dec · λ = 0`). Balayer `λ` sur le champion ne mesurerait rien.

✅ **La force du prior du champion, c'est `l2`.** Et sous `--prior-mean`, `l2`
n'est plus un rétrécissement vers zéro : c'est la **force du rappel vers le
parent**. Le même nombre, un autre sens. Sa valeur `3e-5` a été close en juillet
(`l2_factor_closed_on_3e5`) sur un ridge centré sur **zéro** ; cette fermeture ne
se transporte pas à la recette courante. **C'est cet axe-là qui teste le
double-comptage**, et c'est lui qui est mesuré ici.

## Ce qui est mesuré

Trois points, le champion au centre. Un seul facteur : `l2`. Tout le reste est
identique — même corpus TURNOVER, même parent (`be675b6c…`), `--exact-fold`,
`--prior-mean --prior-decay 0`, `--lbfgs-gtol 1e-4`.

| cellule | `l2` | rôle |
|---|---|---|
| `L2LOW` | `1e-5` | rappel **plus faible** vers le parent — ce que prédit le double-comptage |
| PRIORTIGHT | `3e-5` | **le champion**, déjà mesuré, sert de défenseur aux deux portes |
| `L2HIGH` | `1e-4` | rappel **plus fort** vers le parent |

Les deux challengeurs sortent du **même job** (`cpx62-1164`), donc de la même
pile numérique et de la même box — condition nécessaire depuis `home-1210`, qui
a montré qu'un fit ne se compare pas d'une box à l'autre. Chaque challengeur est
ensuite opposé à PRIORTIGHT sur le pool `big3000`, `n = 12 000`, deux vues
sommées.

## La règle, fixée d'avance

1. **Une cellule ne « gagne » que si son IC95 contre PRIORTIGHT exclut zéro.**
   Pas de lecture de point estimé isolé, pas de seuil rediscuté.
2. **Les deux cellules perdantes ou non concluantes ⇒ `l2 = 3e-5` est CONFIRMÉ
   comme point de fonctionnement et l'axe se ferme.** C'est un résultat, pas un
   échec : il dirait que la fermeture de juillet se transporte malgré le
   changement de sens.
3. **Une seule cellule gagnante ⇒ candidat, PAS champion.** Elle exige le même
   traitement que toute succession : réplication sur un second pool disjoint
   **et** les trois gardes (`l3-succession-guards-v1.sh`). Aucun bake sur une
   porte unique.
4. ⛔ **Les DEUX cellules gagnantes ⇒ résultat INCOHÉRENT, à ne pas promouvoir.**
   Le champion ne peut pas être simultanément battu par un rappel plus faible
   *et* par un rappel plus fort ; ce serait la signature d'un problème de
   harnais, pas d'une dose. À investiguer, jamais à baker.
5. **La direction est informative et elle est prédite.** L'hypothèse de
   double-comptage de JFC prédit que `L2LOW` gagne. Si c'est `L2HIGH`,
   l'hypothèse est fausse et le parent est au contraire **sous-pondéré**.
6. **Tout point gagnant sera BIAISÉ VERS LE HAUT** — c'est une mesure de
   découverte sur deux cellules. À écrire dans l'enregistrement, comme pour
   PRIOR et PRIORTIGHT.

## Ce que ce job n'établira pas

- **Rien sur `decay = 1`** (le régime pondéré par les visites, celui de l'ère
  gen1/gen2). Prédiction de mécanisme consignée d'avance : à `decay = 1` le
  rappel est le plus fort là où les données sont les plus abondantes — l'inverse
  du motif qui justifiait le prior — et les 120 extras (`visites/N = 1`)
  reçoivent une précision de `0,25` contre `l2 = 3e-5`, soit **~8 300×**, ce qui
  les **gèle** sur le parent au lieu de les doser. Mesurable par la continuation
  `priorvisit`, non mesuré ici.
- **Rien sur `λ`**, inerte à `decay = 0`.
- **Rien sur le ratio du mélange lui-même** (1:1). Le double-comptage est testé
  par son effet attendu sur la dose, pas en variant la composition.
- **Rien au-delà de trois points.** Un optimum interne entre `1e-5` et `1e-4` ne
  serait pas localisé par ce dessin.

## Sizing annoncé à JFC avant le go

Ancres mesurées sur cpx62 dans la nuit du 2 au 3 août : refit deux bras à
`gtol 1e-4` = **115,6 min** (`cpx62-1159`) ; porte `n = 12 000` sur `big3000` =
**59,7** et **61,5 min** (`cpx62-1163`, `cpx62-1161`). Total annoncé **~4h30**.

⚠️ Réserve annoncée avant le lancement : le bras `l2 = 1e-5` est **moins
régularisé**, donc peut demander nettement plus que les `904` itérations du
champion. `MAXIT = 5000` et `FIT_TIMEOUT = 14400` couvrent le cas, mais la borne
haute du refit est incertaine et peut atteindre ~3h.
