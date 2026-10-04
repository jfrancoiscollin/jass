# L3-PURE — spécification de la lignée autonome et plan DoE

> **Version : 5.0 — 18 juillet 2026**
> **Statut : C1-Q1 clos sans lead ; C2-X1 pré-enregistré et préparé, non lancé**
> **Ancienne version :** [L3_PURE_PLAN_V4_1_20260718.md](archives/l3/L3_PURE_PLAN_V4_1_20260718.md)
> **État et résultats :** [L3_CURRENT.md](L3_CURRENT.md)
> **Mémoire des résultats et portes closes :** [PROJECT_RESULTS.md](PROJECT_RESULTS.md)

## 0. Décision

> **Amendement du 9 septembre 2026 (JFC).** L'interdiction du relabel adjugé est
> levée pour la cible d'entraînement, dans le périmètre strict de la
> preregistration [R1](experiments/L3_R1_ADJUDICATED_RELABEL_V1_20260909.md) :
> arbitre interne (recherche Jass profondeur fixe `14` + EGDB), bande de nulle
> `50 cp`, blend `0,5/0,5` avec le WDL terminal, un seul facteur. La lignée reste
> autonome : aucun agent externe ne fournit position, coup, score ou résultat.
> Motif : la classe contient le point de Scan (port exact `600/600`) alors que le
> fit n'identifie que `≈ 24 k` ddl effectifs sur `2,1 M` (JFI finding C) ; le label
> WDL terminal d'un pilote `d8` à `8 %` d'exploration est la source d'information la
> plus pauvre du pipeline. Tout le reste du contrat §2 reste en vigueur.

La cible reste une lignée linéaire autonome, sans professeur externe :
graine matérielle, autojeu, résultat terminal WDL, fit, puis nouvelle
génération. Scan, Gen2, les maîtres, d14 et MMTO peuvent mesurer la lignée mais
ne fournissent ni position, ni coup, ni score, ni résultat d'entraînement.

En revanche, la recette C0 n'est plus considérée comme optimale par défaut.
Elle est un point reproductible. Les gains et pertes observés sur Gen2 ou sur
les anciennes lignées sont des **priors** : ils réduisent l'espace à explorer,
mais ne ferment pas un paramètre dont l'effet peut dépendre d'une évaluation
jeune, de sa distribution et de son budget de recherche.

La stratégie n'est donc ni « tout activer », ni balayer 63 nombres. Elle est :

1. supprimer les couplages accidentels ;
2. figer la totalité de la configuration ;
3. tester des mécanismes par blocs causaux sur une lignée L3 native ;
4. confirmer le gagnant depuis G0 avec une seconde graine ;
5. seulement ensuite engager la campagne longue.

Le verdict contractuel `0812` ferme C1-Q1 : menace, sacrifices sélectifs et
leur interaction n'améliorent ni la conversion ni la force. `Q00` (captures
obligatoires seulement) devient donc la baseline de recherche provisoire et
Q2 n'est pas déclenché.

Le prochain bloc est **C2-X1, exploration**. Il passe devant le DoE budget :
Q01 a montré qu'un gain de recherche natif (+28 Elo) peut rester sans effet sur
la conversion. Le levier le plus causal à tester maintenant est la distribution
des trajectoires auto-générées. Une micro-calibration de coût reste obligatoire
avant exécution, mais elle n'est pas un sweep de recherche.

## 1. Ce qui est appris des campagnes précédentes

Les faits suivants restent acquis :

- une boucle from-scratch peut apprendre : `0674` a composé à T2 ;
- T1-bis→T3 a été stable, mais la conversion est restée autour de 66–67 % ;
- fork C a produit de la divergence sans force ni conversion et a été rejeté ;
- C1-Q1 a été plat au verdict contract-grade : aucun effet de conversion
  menace/sacrifices, malgré un petit gain de recherche natif pour Q01 ;
- les gymnases statiques, teachers causaux et re-fits de Gen2 n'ont pas déplacé
  le plafond de conversion dans leurs protocoles ;
- la quiescence forcing profonde et les extensions larges ont coûté de la force
  au movetime sur l'ancien champion ;
- la géométrie riche peut payer au scale, mais elle est affamée à petit volume ;
- une baisse de loss ou une hausse de divergence ne suffit jamais à promouvoir.

Ce que ces faits **ne démontrent pas** : que le fingerprint de recherche de
Gen2 est optimal pour les trajectoires d'une lignée partie de matériel seul,
que 8 % d'exploration est le bon niveau, que L2=3e-5 est optimal, ou que le
rapport homme/dame initial 1:3 donne le meilleur curriculum.

## 2. Contrat scientifique invariant

Ces choix définissent l'expérience et ne sont pas des facteurs de tuning :

- cible d'entraînement : résultat terminal WDL de la partie réellement jouée ;
- perte : logistique WDL ; aucune cible score, ranking ou préférence ;
- terminaison EGDB exacte seulement après atteinte naturelle de la tablebase ;
- partie au ply-cap entièrement censurée ;
- **amendé le 9 septembre 2026 (décision JFC)** : l'adjudication de la cible par
  l'**arbitre interne gelé** (recherche Jass à profondeur fixe + EGDB, sans agent
  externe) est **autorisée comme cible d'entraînement**, uniquement sous
  preregistration ([R1](experiments/L3_R1_ADJUDICATED_RELABEL_V1_20260909.md)) ;
  restent interdits : adjudication matérielle, MMTO, cibles de ranking ou de
  préférence, et toute cible produite par Scan, Gen2, d14 externe ou des maîtres ;
- aucune position externe, partie humaine, politique ou poids Scan/Gen2 ;
- paires d'ouvertures, provenance par partie et holdout par ouverture complète ;
- aucun PV extrait : seules les positions réellement jouées sont entraînées ;
- aucun `drop-post-eps` : une continuation après exploration est un retour MC
  réel et fait partie de la trajectoire à apprendre ;
- symétrie couleur ; aucun full-fold par translation ;
- aucun anchor vers le parent ; le warm-start est une initialisation numérique ;
- chaque cellule publie code, données, seeds, paramètres, compteurs et SHA.

Une violation donne le statut `invalid_science`, indépendamment du code retour.

## 3. Revue de la surface de paramètres

| Surface | Décision L3 | Motif et condition de réouverture |
|---|---|---|
| 63 paramètres de recherche | **tous épinglés** dans chaque run | le C0 n'explicitait que 5 clés ; les runners v4/v5 publient la map résolue complète |
| score JNNW / profondeur de label | **zéro, sans recherche de score** | le fit WDL ignore le score ; l'ancienne recherche de label réutilisait la même TT et influençait donc le coup joué de façon cachée |
| captures obligatoires en quiescence | **invariant ON** | règle de jeu, pas un facteur |
| menace et sacrifices sélectifs | **clos dans le régime jeune** | C1-Q1 contract-grade `0812` : aucun effet de conversion ou de force |
| récursion des sacrifices, forcing, promotion | **Q2 non déclenché** | aucun lead Q1 ; réouverture seulement sur signal nouveau d'une lignée plus mûre |
| PVS, RFP, NMP, singular, LMR, LMP, history, razor, ProbCut, MultiCut, improving, conthist, IID | **profil puis ablations par mécanisme** | pas de sweep de marges avant preuve que le mécanisme s'active et aide L3 |
| profondeur fixe, cap de nœuds, profondeur par phase | **DoE budget B après X1** | Q01 a gagné en recherche sans convertir ; profiler avant toute ablation |
| plies aléatoires, epsilon, décroissance | **DoE immédiat C2-X1** | ces facteurs changent directement la distribution des trajectoires autonomes |
| échantillonnage ≈1 ply sur 4 | **à instrumenter puis tester** | pondération temporelle implicite ; ne change qu'après ajout d'un flag et d'un RNG dédié |
| graine homme=1, dame=3 | **baseline, pas optimum déclaré** | écran ultérieur du ratio dame {2,5; 3; 4} depuis G0 |
| centre/mobilité à zéro | **figé au premier écran** | évite de confondre le rapport matériel avec des heuristiques hand-set |
| max_plies=260 | **fixe tant que censure <0,5 %** | augmenter seulement si le taux de parties censurées devient matériel |
| L2=3e-5 | **DoE fit F** | dépend du volume, de la géométrie et du régime de visite |
| corpus 100 % frais | **baseline ; replay à tester** | croiser L2 avec replay 0/25 % après stabilisation de la génération |
| max_iter, chunk, pruning des buckets, quantification | **paramètres techniques** | augmenter max_iter si non-convergence ; exiger équivalence avant toute optimisation de coût |
| color-fold, tempo-stage, MG/EG | **figés pendant les écrans initiaux** | phase/tempo ne se rouvrent que sur résidu holdout localisé et couverture suffisante |
| géométrie 8cf | **figée pour les écrans, non close à long terme** | comparer 8cf/32cf dans un fork depuis G0 quand le volume cumulé nourrit réellement 32cf |
| king-patterns | **différé** | uniquement si un résidu roi mesuré persiste au scale |
| frontière mobile | **close, v1 retirée** | C0 `0795` : Δglobal −0,023 et P3 −0,070, sans signal positif |
| quiet-only, PV extraction, teacher externe | **OFF par contrat** | changeraient la population ou la vérité des trajectoires |
| adjudication interne de la cible (arbitre Jass + EGDB) | **autorisée depuis le 9 sept. 2026, sous prereg R1** | ne change ni la population ni les trajectoires : seule la cible change ; décision JFC après le diagnostic d'identification (JFI finding C, port exact Scan 600/600) |

## 4. D0 — hygiène causale avant tout DoE

Deux corrections précèdent les comparaisons :

1. **Fingerprint complet.** Les 63 clés reconnues par
   `apply_search_param` sont présentes dans la chaîne de chaque run. Une clé
   ajoutée au moteur fait échouer le test tant qu'elle n'est pas épinglée.
2. **WDL sans recherche de score.** `--wdl-zero-score` écrit `score=0` et ne
   lance pas la recherche de label. Le compteur `label_score_searches=0` est
   exigé dans chaque shard.

La seconde correction est volontairement commune à toutes les cellules C1.
Elle ne prétend pas améliorer Elo : elle supprime un budget de recherche
irrégulier et une précharge TT invisible alors que sa sortie n'entre pas dans
la loss. C1 est donc un fork de C0, pas une continuation comparable bit à bit.

## 5. C1-Q — terminé

Les quatre cellules `Q00/Q10/Q01/Q11` ont été entraînées jusqu'à G2 depuis la
même graine matérielle. Le verdict schema 2 `0812` a réévalué leurs artefacts
immuables avec fingerprint complet, conversion appariée et vues
common/native.

Résultat : `q1_no_lead`. Les effets globaux menace (+0,0006), sacrifices
(−0,0041) et interaction (+0,011) ont tous un IC recouvrant zéro ; aucune
cellule n'atteint +0,02 de conversion. Q01 gagne légèrement en recherche native
mais perd 0,015 de conversion globale. La baseline devient donc
`Q00_CAPTURE` et **Q2 n'est pas lancé**.

Forcing, promotion ou récursion de sacrifices ne redeviennent éligibles que si
une lignée plus mûre produit un nouveau signal causal. Il n'existe aucun bras
Q2 préparé ou autorisé dans le programme courant.

## 6. DoE suivants, dans cet ordre

### 6.1 C2-X1 — exploration immédiate

Le screen est un demi-factoriel de résolution III, générateur `C=AB`, plus un
point central. Les facteurs sont A = plies d'ouverture, B = epsilon initial et
C = fin de décroissance.

| Cellule | A : ouverture | B : epsilon | C : décroissance | Codes A/B/C | Rôle |
|---|---:|---:|---:|---|---|
| `X_LLH` | 4 | 4 % | 60 | −/−/+ | coin |
| `X_HLL` | 8 | 4 % | 30 | +/−/− | coin |
| `X_LHL` | 4 | 8 % | 30 | −/+/− | coin |
| `X_HHH_CONTROL` | 8 | 8 % | 60 | +/+/+ | recette courante, contrôle |
| `X_CENTER` | 6 | 6 % | 45 | 0/0/0 | diagnostic de courbure |

Les alias sont A=BC, B=AC et C=AB. X1 sert à sélectionner une **cellule**, pas
à déclarer isolément un effet principal si une interaction de second ordre est
plausible. Le centre est comparé à la moyenne des quatre coins pour détecter
une courbure ; il n'est pas confondu avec le contrôle.

Contrat commun : départ G0 matériel, deux générations de 150 k records, d8,
graine `271828`, géométrie 8cf, fit WDL/L2 `3e-5`, fingerprint Q00 de 63
clés, aucun teacher, aucune frontière et aucun enchaînement automatique.

Chaque shard publie le nombre réel de coups d'ouverture, plies jouées, tirages
epsilon, tirages qui changent le meilleur coup et parties touchées. Chaque
génération publie aussi : positions uniques, jeux/ouvertures distincts,
distribution WDL, phases, strates matérielles P1–P4 et conversion
**diagnostique par record**. Cette dernière n'est pas un gate car plusieurs
records proviennent d'une même partie.

Le verdict scientifique est construit après publication des cinq G2, sur leurs
URIs immuables. Un lead de screen exige contre `X_HHH_CONTROL` :

- Δconversion globale ponctuelle ≥ +0,02 ;
- aucune régression établie en common-search ni sur P1–P4 ;
- P3 mince explicitement rapporté ;
- chaîne, compteurs d'activation et manifests complets.

Le lead est ensuite rejoué seul face au contrôle depuis G0 avec la graine
`161803`. Aucun résultat X1 primaire ne promeut directement une recette.

### 6.2 B — budget et sélectivité de la recherche, après X1

Sur la baseline exploration confirmée :

1. profiler activations, nœuds, profondeur atteinte et débit sur positions L3 ;
2. comparer profondeur fixe, cap déterministe de nœuds et rampe par phase à
   compute apparié ;
3. ablater les mécanismes spéculatifs par paquets cohérents
   (razor/ProbCut/MultiCut), puis NMP et réduction tardive ;
4. ne tuner les marges que si l'ablation montre un effet causal.

Les anciens OAT LMR/NMP/ProbCut restent des priors négatifs. Ils empêchent un
nouveau balayage aveugle, pas cette unique revue native et instrumentée.

### 6.3 M/F — graine, régularisation et mémoire

- ratio dame de G0 : {2,5; 3; 4}, autres termes à zéro ;
- L2 : {1e-5; 3e-5; 1e-4} en échelle logarithmique ;
- replay : {0; 25 %} croisé avec L2 après un premier tri ;
- convergence de l'optimiseur obligatoire ; `max_iter` n'est pas un levier
  scientifique si la solution n'a pas convergé.

Le gagnant final est reconfirmé depuis G0 avec la graine indépendante
`161803`, afin d'éviter de sélectionner une fluctuation de trajectoire.

### 6.4 Représentation et frontière

8cf reste la géométrie des écrans. 32cf ne devient éligible qu'après publication
des visites par bucket et d'un volume cumulé suffisant ; le comparatif repart
de G0 et utilise le même budget d'optimisation. Aucun changement de géométrie
n'est fait au milieu d'une lignée.

La frontière mobile v1 est retirée : C0 `0795` est plat/négatif en conversion.
Aucun dose-réponse n'est prévu ; une réouverture exigerait un mécanisme de
curriculum causalement différent du re-seed matériel testé.

## 7. Mesure et règle de décision

Chaque candidat X1 est évalué selon trois vues :

1. **conversion fixe** : même pool WDL-grounded, même défenseur, global et P1–P4 ;
2. **force common-search** : tous les poids jouent sous le fingerprint Q00
   complet, qui est aussi leur recherche native dans X1 ;
3. **distribution générée** : dose d'exploration réellement activée, diversité,
   phases, strates matérielles et censure.

Chaque sortie de conversion conserve `{index, résultat}` pour un bootstrap
apparié contre `X_HHH_CONTROL`. Les contrastes du demi-factoriel publient
leurs alias ; le point central est testé contre la moyenne des coins. Un timeout
peut être exclu d'une paire, mais tous les index source doivent être
complètement comptabilisés.

Une chaîne partielle, une clé héritée, un compteur d'activation absent ou une
des cinq cellules manquante donne `invalid_science`. La loss, la divergence,
le nombre de positions uniques et la conversion par record du corpus sont des
diagnostics, jamais des gates.

Pour avancer d'un screen vers une confirmation :

- chaîne et manifests complets, aucun shard manquant ;
- pas de régression établie en common-search (`ci_high < 0,5` rejette) ;
- gain de conversion ponctuel d'au moins +0,02 ;
- aucune régression établie sur une strate (`IC_high(delta) < 0` rejette), P3
  mince explicitement inclus ;
- compteurs d'exploration cohérents avec la cellule pré-enregistrée.

Pour promouvoir après confirmation :

- gain de conversion ≥ +0,02 avec IC bootstrap apparié au-dessus de zéro ;
- non-régression généraliste à haut N et au movetime ;
- effet retrouvé avec la seconde graine ;
- aucune sélection a posteriori de seuil ou de cellule.

Dans X1, toutes les cellules ont la même recherche de jeu : un gain de force ou
de conversion est donc attribuable à l'apprentissage sur une distribution
différente, pas à un fingerprint natif plus coûteux.

Le verdict ne lance aucun job. Un lead X1 passe d'abord en confirmation ; le
wrapper de réplication n'est préparé qu'après lecture humaine, calibration, SHA
mergé et go explicite.

## 8. Campagne longue

Après les DoE, une seule recette confirmée entre dans la lignée longue :

| Palier | Générations | Budget indicatif |
|---|---:|---:|
| P1 | G1–G4 | exploration et budget confirmés |
| P2 | G5–G8 | +1 palier de nœuds ou d8→d10 |
| P3 | G9–G12 | d10→d12 ou équivalent |
| P4 | G13–G16 | d14 ou plafond apparié |
| confirmation | reprise depuis G0 | seconde graine |

Une génération plate ne suffit pas à arrêter. L'arrêt de plafond exige le
budget maximal, quatre générations sans pente et deux graines indépendantes.

## 9. PR C2-X1

La PR du prochain bloc fournit :

- compteurs moteur stables de dose d'exploration réellement activée ;
- profil de corpus autonome par jeu, ouverture, position, phase et strate ;
- runner v5 avec fingerprint Q00 de 63 clés et manifest schema 3 ;
- cinq wrappers du demi-factoriel + centre, préparés hors queue ;
- gardes `FULL_RUN_APPROVED`, volume/générations/seed pré-enregistrés, absence
  de frontière et de teacher, `automatic_next_job=null` ;
- tests de syntaxe, matrice `C=AB`, instrumentation et couverture des 63 clés ;
- archivage de la spec v4.1 et mise à jour des trois documents actifs.

Merger cette PR ne lance aucun job. Avant copie GitOps : build réel sur chaque
box, micro-calibration de chaque profil, ETA, disque, timeout, SHA exact et go
explicite. Le job d'évaluation n'est préparé qu'après disponibilité des cinq
URIs G2 afin de les épingler sans placeholder.
