# Le format de score de Scan 3.1 — mesuré, pas supposé (2026-07-31)

**Question** : l'atlas de points aveugles a besoin du *score* de Scan sur une
position. Quel est le gabarit réel de ses lignes ? Le motif d'extraction écrit
dans `jobs/tools/scan_blind_spot_atlas.py` fonctionne-t-il dessus ?

**Réponse : oui, le motif marche.** Verdict `SCAN_SCORE_PATTERN_WORKS`, 4/4
positions. Mais la mesure a sorti une propriété d'échelle qui change la
conception du collecteur — c'est le vrai résultat de cette sonde.

## Comment c'est mesuré

Runtime Scan **gelé et épinglé**, restauré depuis
`r2:jass-data/runtime/scan/7aae17e7b7bfc47744601afb1ee7655e18983ce5` :
`scan_linux` = `a634cbb4…5941864`, `data/eval` = `0e7161c3…e58abba`, empreinte
runtime `91698ab5…c53d4bf` — les quatre hashes recomptés et conformes. C'est
**bit pour bit** le binaire que `calibrate_vs_scan` utilise depuis `home-0925`.

Paramètres HUB forcés (les mêmes que `calibrate_vs_scan`) : `variant=normal`,
`book=false`, `ponder=false`, `threads=1`, `tt-size=24`, `bb-size=0`.
`level depth=10`, quatre positions couvrant trois régimes.

Sonde : `jobs/tools/scan_protocol_probe.py`. Transcription verbatim des deux
sens. Exécutée dans le conteneur de session, pas sur une box — le binaire épinglé
tourne ici, et lancer un job pour ça aurait coûté du temps de box sans rien
ajouter à la preuve : mêmes hashes, mêmes paramètres, profondeur fixe.

## Le gabarit

```
info depth=10 mean-depth=11.1 score=0.00 nodes=77378 time=0.010 nps=7.6 pv="34-30 17-21 …"
done move=34-30 ponder=17-21
```

- Le score est **uniquement sur les lignes `info`**. `done` ne porte que `move=`
  et `ponder=`. La prémisse de la sonde est confirmée : lire `done` ne suffit
  pas, et `calibrate_vs_scan` — qui ne lit que le coup — jetait bien le score.
- `time=` et `nps=` n'apparaissent qu'aux profondeurs où Scan a mesuré quelque
  chose ; un motif qui les exigerait raterait les lignes peu profondes.
- `pv=` est nu à un seul coup, **entre guillemets** dès qu'il y en a plusieurs.
- `extract_scan_score` prend le **dernier** score avant `done`, donc celui de la
  profondeur la plus grande. Correct.

## ⚠️ L'échelle : décimale, en unités-pion, et **saturée à ~100**

| position | dernier score |
|---|---|
| initiale | `0.00` |
| milieu calme | `0.04` |
| finale de dames | `0.01` |
| **gain forcé** | **`99.97`** |

Ce ne sont pas des centipions entiers : ce sont des **décimaux en unités-pion**.
Et un gain forcé ne sort **pas** un jeton « mat en N » — il sort une valeur
sentinelle proche de 100, atteinte dès la profondeur 2 et constante ensuite :

```
info depth=1  mean-depth=1.0 score=0.13  nodes=1   pv=31-27
info depth=2  mean-depth=3.0 score=99.97 nodes=35  pv="31-26 5-10 46x5x10"
info depth=10 mean-depth=3.0 score=99.97 nodes=199 pv="31-26 5-10 46x5x10"
```

### Ce que ça impose au collecteur (pas encore écrit)

`Atlas.add()` **somme les coûts bruts** et classe les buckets par
`cost_per_position = cost_sum / positions`. Avec cette échelle, les évaluations
ordinaires vivent dans `0.00–0.10` et un gain forcé vaut `~100` : **un seul
désaccord sur une position gagnée pèse plus de mille désaccords ordinaires.**

Non corrigé, l'atlas ne classerait pas les points aveugles — il classerait
« quel bucket contient une finale gagnée », ce qu'on sait déjà et qui n'apprend
rien. Le classement serait dominé par une poignée de positions, exactement le
genre de faux signal que la règle 10 interdit.

Ce n'est **pas** un bug à corriger dans l'agrégateur aujourd'hui : le calcul du
coût appartient au collecteur, qui reste à écrire. C'est une **contrainte de
conception mesurée**, à trancher avant de l'écrire. Les options, à arbitrer par
JFC :

1. **Écrêter** le coût à un plafond (p. ex. 1.0 unité-pion) — un désaccord reste
   un désaccord, son poids cesse d'être illimité.
2. **Séparer** les positions saturées (`|score| > 50`) dans leur propre famille
   « conversion/finale gagnée », comptées en *taux* et non en coût sommé.
3. Coût **borné par construction** (p. ex. `min(|Δ|, seuil)` ou une transformée
   type WDL), qui rend la métrique insensible à la sentinelle.

Ma préférence : **(2) puis (1)**. Une position gagnée ratée et une évaluation
tiède mal ordonnée ne sont pas la même erreur ; les mélanger dans une somme les
rend incomparables, et les séparer répond en plus à une question qu'on se pose
déjà (sait-on convertir ?). L'écrêtage seul écraserait cette distinction.

## Statut

- Motif d'extraction : **validé sur du réel**, aucune réécriture nécessaire.
- `cpx62-1111` (la sonde en job) : **échec, `binaire Scan absent`** — Scan n'a
  jamais été installé sur cpx62, seulement sur HOME, et HOME est out. Sa question
  est néanmoins tranchée par la mesure locale ci-dessus.
- Reste bloquant pour l'atlas lui-même (qui, lui, a besoin de la box) :
  installer le runtime gelé sur cpx62 — `jobs/templates/install-frozen-scan-runtime-v1.sh`.
