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

## Budget HOME

HOME fournit 16 CPU logiques et environ 15,6 Go de RAM. Les builds restent à
`-j4`. Les deux fits culminent historiquement autour de 1,4 Go de RSS chacun ;
deux optimiseurs concurrents sont donc autorisés, jamais davantage. ETA :
15–25 minutes de préflight, 30–50 minutes de fit, puis 45–70 minutes de
readout.
