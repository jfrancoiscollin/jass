# L3-PURE — écran L2 sur le corpus TURNOVER 50/50

Date de préenregistrement exécutable : 26 juillet 2026, après la cellule Q00
REPLAY25/TURNOVER de `home-0983`, mais avant ses cellules natives, sa conversion
et son verdict final. Les trois niveaux de L2 et l'ordre « premier tri L2, puis
croisement avec le replay » étaient déjà fixés dans
[`L3_PURE_PLAN.md`](../L3_PURE_PLAN.md), avant tout résultat M2 ou REPLAY25.

## Déclencheur

Le bras ne devient exécutable que si
`home-0983-l3-pure-replay25-independent-eval-v1` termine avec :

- `verdict=REPLAY25_DOSE_CLOSED_REVIEW` ;
- un résultat complet, des identités authentifiées et toutes les cellules
  attendues ; `all_guardrails_pass` peut être faux parce que ce champ inclut
  précisément la non-régression scientifique que REPLAY25 vient d'échouer ;
- `promotion_authorized=false` et `automatic_next_job=null`.

Un incident technique ou un verdict différent interdit ce lancement et impose
la branche prévue par `home-0983`. En particulier, un signal directionnel doit
être confirmé sur un nouveau pool ; il ne peut pas être remplacé par cet écran.

## Question causale

À parent, corpus, split, architecture, recherche, objectif et optimisation
constants, la régularisation explique-t-elle le plafond du meilleur corpus
temporel actuellement confirmé ?

Le contrôle est le modèle TURNOVER 50/50 de `home-0977`, déjà entraîné avec
`L2=3e-5`. Deux nouveaux modèles sont fittés sur **exactement le même corpus**
et depuis le même warm-start F2M :

| bras | L2 | corpus | parent |
|---|---:|---|---|
| `L2_1E5` | `1e-5` | TURNOVER 1M époque F2M + 1M époque M2 | F2M |
| `L2_3E5_CONTROL` | `3e-5` | identique, modèle certifié `home-0977` | F2M |
| `L2_1E4` | `1e-4` | identique | F2M |

Identités immuables du corpus :

- JNNW :
  `9b7db67a87025baf9115c72512312ac13ace076cef700c54ff1862f4ab240a2d` ;
- JSM :
  `acf3bbf4a28e7b44a1077df06bca9658cd4b189fc4cf11ee7f56720661626682` ;
- 2 000 000 records, mix seed `141421` ;
- split par ouverture seed `577215`, 1 800 796 train et 199 204 holdout ;
- parent F2M :
  `be675b6c1c6360a0a9aa5977ed492284bc8dcc1861ee47bc2e3139046ed769f2` ;
- contrôle TURNOVER :
  `b2c79b3617c41087191fee04d9aee0e1929ea63ad621c2efeaebc14ae53a7c16`.

Tout le reste reste figé : départs standards, d8, 8cf, Q00, WDL terminal,
color-fold/tempo-stage actuels, `max_iter=1000`, `maxcor=20`, `gtol=1e-3`,
chunk 20 000. Sont interdits : nouvelle génération, changement de replay,
oracle, teacher, TOP3, reweight V2, changement de géométrie, profondeur ou
recherche.

## Chaîne réservée

1. `home-0984-l3-pure-turnover-l2-preflight-v1` authentifie `home-0983`,
   `home-0980`, `home-0977` et F2M ; reconstruit deux fois le split ; installe
   NumPy 1.26.4/SciPy 1.14.1 dans un venv isolé ; valide build, tests, feature
   dump et mini-fits aux deux L2 ; publie RAM et ETA. Il construit aussi deux
   fois un pool indépendant de 500 ouvertures, seed `1836313`, disjoint de tous
   les pools M1/M2/d10/d12/TURNOVER/REPLAY25.
2. `home-0985-l3-pure-turnover-l2-train-v1` réutilise le corpus et le split
   certifiés, fait un seul feature dump et fitte `L2_1E5` et `L2_1E4` avec au
   plus deux optimiseurs concurrents. Les deux doivent converger réellement.
3. `home-0986-l3-pure-turnover-l2-independent-eval-v1` commence par comparer
   chaque candidat au contrôle TURNOVER sur le même nouveau pool, en Q00 d9 et
   cadence native. Seuls les candidats dont les deux estimations ponctuelles
   dépassent 50 % ouvrent les cellules de garde contre F2M et Gen2 ainsi que
   P3/P4 avec défenseur fixe. Si aucun ne franchit ce filtre préenregistré,
   l'écran se ferme sans dépenser ces cellules secondaires.

Les losses holdout, normes de gradient et amplitudes de poids sont des
diagnostics, jamais des critères de sélection.

## Règle de décision

Un L2 est un **lead confirmé de l'écran** seulement si, contre
`L2_3E5_CONTROL`, les deux bornes basses Wilson à 95 % dépassent 50 % en Q00
et en cadence native, sans régression établie contre F2M, Gen2 ou sur P3/P4.

Si les deux estimations ponctuelles dépassent 50 % mais qu'au moins une borne
basse ne le fait pas, le résultat est directionnel et autorise seulement une
confirmation indépendante du même modèle. Dans tous les autres cas,
`L2=3e-5` est retenu et le facteur L2 est clos.

Si les deux nouveaux L2 satisfont le même niveau, aucun n'est choisi sur la
loss : une confrontation appariée directe sur un nouveau pool les départage.

Même un lead confirmé ne promeut rien. Il autorise ensuite le croisement replay
`0/25 %` au L2 retenu, déjà prévu dans `L3_PURE_PLAN.md`.

Dans tous les cas :

```text
promotion_authorized=false
automatic_next_job=null
```

## Déclencheur observé

`home-0983` a terminé avec exit code 0 et
`REPLAY25_DOSE_CLOSED_REVIEW`. Les huit cellules de force contiennent chacune
1 000 parties complètes. La cellule primaire REPLAY25/TURNOVER Q00 établit la
régression attendue (`46,90 %`, IC95 `[43,83 ; 49,97]`) ; le résultat conserve
`promotion_authorized=false` et `automatic_next_job=null`.

Le préfixe immuable est :

```text
r2:jass-data/runs/home-0983-l3-pure-replay25-independent-eval-v1/20260726T112309Z-42b9af7e
```

Le déclencheur du préflight `home-0984` est donc satisfait. Cette observation
ne modifie ni les niveaux L2, ni le corpus, ni la règle de décision ci-dessus.

Le premier claim `home-0984` s'est arrêté pendant l'authentification, avant
tout split, build, mini-fit ou génération de pool. Le résumé agrégé de
`home-0983` conserve `n`, `wins_a`, `draws` et `wins_b`, mais omet
intentionnellement le booléen brut `complete`. La relance `home-0984bis`
contrôle donc la complétude par `n=1000` et `wins_a+draws+wins_b=1000` pour
chacune des huit cellules. Aucun critère scientifique ni budget n'est modifié.

`home-0984bis` termine ensuite avec `TURNOVER_L2_PREFLIGHT_READY`. Le split
reproduit contient 1 800 796 records train et 199 204 holdout ; son pic est
919 896 KiB de RSS. Les mini-fits `1e-5` et `1e-4` passent dans l'environnement
NumPy 1.26.4/SciPy 1.14.1. Le pool indépendant final est :

```text
seed=1836313
records=500
sha256=e7b89a5e3feade8919c8a498f424084deb0a2128c1712c9ca0a9547cf22b6df2
r2:jass-data/runs/home-0984bis-l3-pure-turnover-l2-preflight-v2/20260726T122615Z-5ef14ffe
```

Le certificat ouvre uniquement l'entraînement `home-0985`, sans promotion.

`home-0985` termine ensuite avec `TURNOVER_L2_TRAINING_SCREEN_READY` et exit
code 0. Les deux bras convergent réellement sous `gtol=1e-3` :

```text
L2_1E5  iterations=375  gradient_inf_norm=0.000923790306928623
        holdout_logloss=0.444361  max_rss_kib=1411344
        sha256=27cf9bedf20d00bbcc106a52ad183990f8df131362c4590fc319cc708464ff49
L2_1E4  iterations=170  gradient_inf_norm=0.0007450357165352047
        holdout_logloss=0.446187  max_rss_kib=1431056
        sha256=0b710b80ab11fbcdcf4904adaeeb48166f0449c8c0c0fbf063a12c182372884b
```

Le corpus, le split (`1 800 796 / 199 204`, seed `577215`) et le parent F2M sont
inchangés ; `new_generation_performed=false` et `external_teacher_inputs=0`.
Le contrôle `L2=3e-5` conserve sa loss holdout de `0,444060`. Ce classement des
losses n'ordonne rien : la règle de décision ci-dessus reste seule applicable.

Le préfixe immuable est :

```text
r2:jass-data/runs/home-0985-l3-pure-turnover-l2-train-v1/20260726T123823Z-ad067a4b
```

Le déclencheur du readout `home-0986` est donc satisfait, sans modification des
niveaux L2, du corpus, du pool ni de la règle de décision.

`home-0986` s'est arrêté techniquement à l'étape
`build-guard-and-fixed-defender-engines`, sur
`ABORT: guard engine king-capture witness failed`. Les deux moteurs 32cf
avaient pourtant été construits sans erreur. Le témoin
`--perft 1 'W:W40,43,K2:B8,18,29,30' == 9` est le test de non-régression
introduit par `5f5a7e7b`, qui déduplique les chaînes de capture dans
`emit_chain` ; le template l'appliquait aussi au défenseur figé
`J32FIXED`, construit depuis `FIXED_DEFENDER_CODE_SHA=038a2001`, soit 47
commits avant ce correctif. Ce binaire retourne donc un perft différent par
construction et le job ne pouvait pas aboutir. Le template éprouvé
`l3-pure-replay25-eval-v1.sh`, validé par `home-0983`, témoigne `J8` et `J32`
et exclut `J32FIXED`, qui n'y sert que de `--defender-jass` ; le correctif
rétablit exactement ce périmètre.

Conformément à la discipline du programme, **aucun verdict scientifique n'est
tiré de cet échec technique**. Ses quatre cellules primaires étaient complètes,
mais elles ne sont pas réutilisées : `home-0987` refait le readout entier. Les
niveaux L2, le corpus, le split, le pool indépendant, les identités de modèles
et la règle de décision sont inchangés ; seul le périmètre du témoin de garde
est corrigé.

## Résultat de l'écran

`home-0987` termine avec exit code 0 et
`TURNOVER_L2_SCREEN_DIRECTIONAL_CONFIRMATION_REVIEW`. Les douze étapes sont
complètes, `confirmed_leads` est vide et `directional_arms=["L2_1E5"]`.

```text
primaire vs L2_3E5_CONTROL, n=1000 par cellule
  L2_1E5  q00     50,15 %  490-23-487  +1,04 Elo   IC95 [47,09 ; 53,21]
  L2_1E5  native  51,45 %  507-15-478  +10,08 Elo  IC95 [48,38 ; 54,52]
  L2_1E4  q00     47,45 %  469-11-520  -17,73 Elo  IC95 [44,37 ; 50,53]
  L2_1E4  native  46,40 %  456-16-528  -25,06 Elo  IC95 [43,33 ; 49,47]

gardes, L2_1E5 seul
  vs F2M   q00 52,60 %  native 51,60 %
  vs GEN2  q00 60,80 %  native 58,05 %
  conversion P3 98,33 % (contrôle 98,00 %, delta +0,33 pp)
  conversion P4 98,33 % (contrôle 99,00 %, delta -0,67 pp)
```

`L2_1E4` est rejeté : sa régression native est établie. `L2_1E5` place ses
quatre estimations ponctuelles au-dessus du contrôle sans qu'aucune borne basse
Wilson ne franchisse 50 % ; il tombe donc exactement dans la clause
directionnelle de la règle de décision. Ses huit garde-fous passent.

Conformément à cette règle, **`L2=3e-5` reste retenu** et la seule suite
autorisée est une confirmation indépendante de `L2_1E5` sur un nouveau pool, à
modèle inchangé. Le croisement replay `0/25 %` reste fermé jusque-là.

Le préfixe immuable est :

```text
r2:jass-data/runs/home-0987-l3-pure-turnover-l2-independent-eval-v2/20260726T164809Z-fa8cd0b1
```

## Confirmation indépendante de `L2_1E5` — préinscription

Préenregistré le 26 juillet 2026, **après** le verdict `home-0987` mais **avant**
toute partie de confirmation. Le modèle candidat est figé depuis `home-0985` et
n'est pas ré-entraîné : le seul facteur qui change est l'échantillon
d'évaluation.

### Chaîne réservée

1. `home-0988-l3-pure-turnover-l2-confirm-preflight-v1` authentifie le
   certificat `home-0987`, vérifie les identités des trois modèles immuables
   (`L2_1E5` `27cf9bed…`, contrôle `L2_3E5` `b2c79b36…`, F2M `be675b6c…`),
   construit le moteur 8cf, puis génère **deux fois** un pool de 1 000
   ouvertures depuis 4 000 candidats, seed `2718281`, disjoint des treize pools
   déjà dépensés — y compris le pool `e7b89a5e…` de l'écran lui-même. Aucun fit,
   aucune partie.
2. `home-0989-l3-pure-turnover-l2-confirmation-v1` joue quatre cellules de
   2 000 parties : `L2_1E5` contre le contrôle `L2_3E5` et contre F2M, en Q00 d9
   et en cadence native `mt0,1`. Il cumule ensuite avec les cellules de 1 000
   parties de `home-0987` pour un readout à 3 000 parties par cellule.

Seuls des moteurs 8cf participent : le candidat, le contrôle et F2M vivent tous
en 8cf. Aucun moteur 32cf ni défenseur figé n'est construit, donc le témoin de
garde qui a arrêté `home-0986` est hors périmètre.

### Règle de décision

`L2_1E5` est **confirmé** seulement si, contre le contrôle `L2_3E5`, les bornes
basses à 95 % dépassent 50 % **à la fois sur les 2 000 parties fraîches et sur
le cumul de 3 000**, en Q00 **et** en natif, sans régression établie contre F2M
dans aucune des deux lectures.

- si ces conditions sont réunies et que la supériorité sur F2M est elle aussi
  établie dans les deux vues et les deux lectures :
  `L2_1E5_CHAMPION_CONFIRMATION_REVIEW_READY` ;
- sinon, si elles sont réunies : `L2_1E5_EFFECT_CONFIRMED_HUMAN_REVIEW` ;
- sinon, si les deux estimations ponctuelles fraîches restent au-dessus de 50 %
  sans borne basse qui franchisse le seuil :
  `L2_1E5_DIRECTION_REPLICATED_REVIEW` ;
- dans tous les autres cas : `L2_1E5_DIRECTION_NOT_REPLICATED_RETAIN_3E5`.

Dans **tous** les cas, `promotion_authorized=false` et
`automatic_next_job=null`. Un effet confirmé ne promeut rien : il autorise
seulement le croisement replay `0/25 %` au L2 retenu.

### Puissance annoncée avant le run

Cette confirmation est déclarée **peu susceptible d'aboutir**, et ce constat est
publié avant les parties pour qu'il ne puisse pas être réinterprété après coup.
Avec `n=2000`, établir la supériorité exige un taux frais d'environ **52,2 %**,
et environ **52,6 %** pour que le cumul Q00 franchisse le seuil. Or `home-0987`
mesure `L2_1E5` à **50,15 %** en Q00. Si le run frais reproduit simplement les
taux de l'écran, le résultat attendu est
`L2_1E5_DIRECTION_REPLICATED_REVIEW`, pas une confirmation.

L'exercice est néanmoins exécuté parce que la règle de décision n'autorise que
lui, et parce qu'un cumul à 3 000 parties tranche proprement si le `+10 Elo`
natif de l'écran est réel ou s'il relève du bruit de `movetime` — écart mesuré à
**1,55 pp** entre `home-0986` et `home-0987` sur cette même vue, pour le même
modèle. Quelle que soit l'issue, le réglage retenu reste `L2=3e-5` tant qu'aucun
lead n'est confirmé.

## Résultat de la confirmation

`home-0988` certifie le pool `71dc575e…` : 1 000 ouvertures uniques, seed
`2718281`, recouvrement nul avec les treize pools exclus, dont le pool
`e7b89a5e…` de l'écran lui-même. `home-0989` termine ensuite avec exit code 0 et
**`L2_1E5_DIRECTION_NOT_REPLICATED_RETAIN_3E5`**.

```text
frais n=2000 (pool 71dc575e)
  q00     vs contrôle  53,02 %  1042-37-921  +21,05 Elo  IC95 [50,86 ; 55,19]  supériorité ÉTABLIE
  native  vs contrôle  49,68 %   972-43-985   -2,26 Elo  IC95 [47,51 ; 51,84]
  q00     vs F2M       52,33 %  1034-25-941  +16,17 Elo  IC95 [50,15 ; 54,50]  supériorité ÉTABLIE
  native  vs F2M       53,15 %  1043-40-917  +21,92 Elo  IC95 [50,99 ; 55,31]  supériorité ÉTABLIE

cumulé n=3000 (avec home-0987)
  q00     vs contrôle  52,07 %  1532-60-1408  +14,37 Elo  IC95 [50,30 ; 53,84]  supériorité ÉTABLIE
  native  vs contrôle  50,27 %  1479-58-1463   +1,85 Elo  IC95 [48,49 ; 52,04]
  q00     vs F2M       52,42 %  1555-35-1410  +16,81 Elo  IC95 [50,64 ; 54,19]  supériorité ÉTABLIE
  native  vs F2M       52,63 %  1552-54-1394  +18,32 Elo  IC95 [50,86 ; 54,40]  supériorité ÉTABLIE
```

La règle préenregistrée exige la supériorité contre le contrôle **dans les deux
vues, à la fois sur le frais et sur le cumul**. La vue native ne la fournit pas,
et son estimation ponctuelle fraîche passe même sous 50 %. Le facteur L2 est
donc **clos sur `L2=3e-5`**, sans promotion.

### Les deux vues se sont inversées

C'est le fait marquant du run. Entre l'écran et la confirmation, sur des pools
disjoints et à modèle strictement identique :

| vue | `home-0987` (n=1000) | `home-0989` frais (n=2000) |
|---|---|---|
| Q00 | 50,15 % (+1,0 Elo, rien) | **53,02 %** (+21,1 Elo, établie) |
| native | 51,45 % (+10,1 Elo, « prometteur ») | **49,68 %** (−2,3 Elo, rien) |

La vue qui portait tout le signal directionnel de l'écran est exactement celle
qui s'effondre, et la vue plate devient la plus forte. La prédiction de
puissance publiée avant le run — « l'écran ne se confirmera pas » — est vérifiée,
mais par un chemin qu'elle n'avait pas prévu : le verdict attendu était
`DIRECTION_REPLICATED`, l'observé est `DIRECTION_NOT_REPLICATED`.

Cette inversion n'est pas un défaut du harnais. La vue Q00 est déterministe à
profondeur fixe — ses cellules `home-0986`/`home-0987` étaient identiques au bit
près sur un même pool — donc l'écart Q00 de 2,87 pp entre les deux runs mesure
la **variance d'échantillonnage entre pools d'ouvertures**, pas du bruit moteur.
Conclusion opérationnelle : à `n=1000`, une lecture mono-vue de l'ordre de
`±10 Elo` ne porte pas de décision.

### Observation hors question causale

Sur le cumul de 3 000 parties, `L2_1E5` établit sa supériorité **contre F2M dans
les deux vues** (52,42 % et 52,63 %, bornes basses 50,64 et 50,86), et il en va
de même sur les 2 000 parties fraîches. Cela ne fait pas de lui un candidat
champion : les cellules F2M sont des **garde-fous de non-régression**, pas le
test préenregistré d'une promotion, et la question causale de cet écran était
`L2_1E5` contre son contrôle `L2_3E5` — à laquelle la réponse est « pas de lead ».

Le fait notable est plutôt que le candidat **et** son contrôle descendent tous
deux de F2M sur le corpus TURNOVER et se tiennent à égalité entre eux tout en
dominant leur parent. Toute exploitation de ce constat exigerait une expérience
séparée et préenregistrée, avec son propre pool. Rien ici ne l'autorise :
`promotion_authorized=false`, `automatic_next_job=null`.

Le préfixe immuable est :

```text
r2:jass-data/runs/home-0989-l3-pure-turnover-l2-confirmation-v1/20260726T201002Z-42f2db33
```

## Budget HOME

HOME fournit 16 CPU logiques et environ 15,6 Go de RAM. Les builds restent à
`-j4`. Les deux fits culminent historiquement autour de 1,4 Go de RSS chacun ;
deux optimiseurs concurrents sont donc autorisés, jamais davantage. ETA :
15–25 minutes de préflight, 30–50 minutes de fit, puis 45–70 minutes de
readout.
