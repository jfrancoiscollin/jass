# L3-PURE — dose mémoire 25 % à volume constant

Date de préenregistrement : 26 juillet 2026, après 1 500 des 2 000 parties
natives de confirmation `home-0980`, mais avant sa dernière vague, son verdict
agrégé et tout corpus ou modèle REPLAY25.

## Déclencheur et question causale

La continuation M2 entièrement fraîche est plate contre F2M. Augmenter la
profondeur de génération à d10 reste plat et d12 régresse. Le bras temporel
50/50, entraîné sur 1M positions de l'époque F2M et 1M positions de l'époque
M2, fournit au moment de ce préenregistrement :

- confirmation Q00 complète : 53,775 % contre M2 et 50,350 % contre F2M ;
- confirmation native partielle, 1 500/2 000 parties : 53,133 % contre M2 et
  50,667 % contre F2M ;
- aucune donnée externe, aucun teacher et aucune nouvelle génération.

Le dernier quart de `home-0980` reste autoritaire. REPLAY25 ne peut être lancé
que si `home-0980` termine avec tous ses garde-fous valides et l'un des verdicts
`TURNOVER_EFFECT_CONFIRMED_HUMAN_REVIEW` ou
`TURNOVER_DIRECTION_REPLICATED_REVIEW`. Tout autre état ferme ce lancement
automatique et impose une nouvelle revue.

Résultat final observé après le préenregistrement : `home-0980` termine avec
`TURNOVER_EFFECT_CONFIRMED_HUMAN_REVIEW` et tous ses garde-fous valides. Sur le
pool frais, TURNOVER marque 53,775 % contre M2 en Q00 et 53,20 % en natif,
avec les deux bornes basses à 95 % au-dessus de 50 %. Contre F2M, il marque
50,35/50,90 % : aucune régression n'est établie, mais aucune supériorité non
plus. Le déclencheur REPLAY25 est donc satisfait sans promotion de TURNOVER.

La question suivante est : **à parent, volume, profondeur, architecture,
objectif, split, L2 et optimisation constants, une mémoire de 25 % conserve-t-elle
le gain contre M2 tout en dépassant le bras 50/50 et le champion F2M ?**

| Facteur | M2 frais | TURNOVER 50/50 | REPLAY25 |
|---|---:|---:|---:|
| parent et warm-start | F2M | F2M | F2M |
| volume de fit | 2 000 000 | 2 000 000 | 2 000 000 |
| positions époque F2M | 0 | 1 000 000 | 500 000 |
| positions époque M2 | 2 000 000 | 1 000 000 | 1 500 000 |
| profondeur des sources | d8 | d8 | d8 |
| architecture / recherche | 8cf / Q00 | identique | identique |
| objectif / L2 | WDL terminal / 3e-5 | identique | identique |
| split | JSM par ouverture | identique | identique |

Ce test réalise le niveau de replay `25 %` prévu dans
[`L3_PURE_PLAN.md`](../L3_PURE_PLAN.md), sans le confondre avec un changement
de L2. Le croisement L2 éventuel reste une étape ultérieure et séparée.

## Construction et préflight

Le corpus utilise exactement les deux sources certifiées du bras 50/50 :

- époque F2M, reconstruite depuis `common-fresh-500k` et
  `extra-fresh-1500k` ;
- époque M2, corpus frais d8 de `home-0966bis`.

`tools/selfplay_frontier.py mix` sélectionne exactement 500 000 et
1 500 000 records, avec IDs de parties et d'ouvertures namespacés par source.
Le seed de mix est `618034`. Il n'y a ni génération, ni oracle, ni teacher,
ni TOP3, ni reweight V2, ni changement de géométrie, profondeur ou volume.

`home-0981-l3-pure-replay25-preflight-v1` doit :

1. authentifier `home-0980`, F2M, M2 et les corpus sources ;
2. reconstruire deux fois le mix et le split par ouverture, puis prouver leur
   identité byte à byte ;
3. publier les SHA JNNW/JSM, les comptes exacts, le profil de couverture et la
   RAM ;
4. installer NumPy 1.26.4 et SciPy 1.14.1 dans un venv isolé ;
5. valider build, tests, feature dump et mini-fit ;
6. construire deux fois le futur pool d'évaluation indépendant, seed
   `1836311`, en excluant DILF et tous les pools M1/M2/d10/d12/TURNOVER déjà
   utilisés ;
7. publier l'ETA HOME avant tout entraînement.

Un préflight incomplet, non reproductible ou dont le mini-fit échoue interdit
le train.

## Entraînement et évaluation réservés

Après préflight vert seulement :

1. `home-0982-l3-pure-replay25-train-v1` refait le split certifié, fitte depuis
   F2M jusqu'à convergence réelle L-BFGS et publie le modèle sans promotion ;
2. `home-0983-l3-pure-replay25-independent-eval-v1` compare REPLAY25 à M2,
   TURNOVER 50/50 et F2M en Q00 d9 et cadence native, garde Gen2 comme
   thermomètre, puis mesure conversion P3/P4 et couverture.

Chaque cellule de force utilise 500 ouvertures avec couleurs appariées, soit
1 000 parties. Les contrôles partagent exactement le même nouveau pool.

## Règles de décision préenregistrées

- **Revue champion** : bornes basses à 95 % au-dessus de 50 % contre M2,
  TURNOVER 50/50 et F2M dans les deux vues, avec tous les garde-fous verts.
- **Dose 25 % causalement meilleure** : mêmes preuves contre M2 et TURNOVER
  50/50, sans régression établie contre F2M, Gen2 ou la conversion.
- **Signal directionnel** : estimations ponctuelles positives contre M2 et
  TURNOVER dans les deux vues, sans régression établie ; seule une confirmation
  indépendante devient alors admissible.
- **Sinon** : la dose 25 % est close. Aucun ajustement de L2, volume, profondeur
  ou seuil n'est ajouté après lecture.

Dans tous les cas :

```text
promotion_authorized=false
automatic_next_job=null
```

## Sizing HOME

HOME fournit 16 CPU logiques et 15,6 Go de RAM. Le build reste limité à `-j4`.
Le préflight vise 15–25 minutes. Le fit 2M est ancré sur les 36 minutes
mesurées de `home-0977`, soit une ETA prudente de 35–50 minutes. L'évaluation
complète est estimée à 45–70 minutes. Aucun de ces budgets n'autorise un scale
supplémentaire.
