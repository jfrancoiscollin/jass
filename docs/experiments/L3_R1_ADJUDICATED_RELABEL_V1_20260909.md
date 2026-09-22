# L3 — R1 : relabel adjugé de la cible d'entraînement — preregistration v1

> **Date : 9 septembre 2026**
> **Statut : preregistration. Le merge autorise l'outillage et les tests ; il n'autorise aucun job distant, aucun fit réel, aucune partie.** Chaque étape distante exige un GO JFC distinct après faits machine, micro-sonde, ETA chiffrée, disque et check-list en 12 points.
> **Décision de programme qui rend ce document possible :** le 9 septembre 2026, JFC lève l'interdiction du relabel adjugé posée par `L3_PURE_PLAN` §2. L'amendement est porté dans `L3_PURE_PLAN.md` §0 et §2 par la même PR. Rien d'autre n'est levé : MMTO, cibles de ranking/préférence, positions externes, parties humaines, poids Scan/Gen2 restent interdits.

---

## 1. Diagnostic qui motive R1

Les faits ci-dessous sont établis et référencés ; R1 n'en réinterprète aucun.

1. **La classe n'est pas le plafond.** Les poids exacts de Scan 3.1 portés dans le format PJTW donnent une égalité statique sur `600/600` positions, écart max `0` (`home-0957`). Avec le moteur réparé, ces poids convertissent `99,00 % / 98,00 %` (`home-0961ter`). La classe 8 bandes ternaires + fold exact + 120 extras + mg/eg contient donc une solution bien plus forte que la nôtre.
2. **Le fit n'identifie qu'une fraction infime de la classe.** JFI (`L3_JFI_CAMPAIGN_TERMINAL_READOUT_V1_20260904.md`, finding C) mesure sur le corpus de production : `8 503 296` coordonnées, `effective_df = 23 687` à `l2 = 1e-5`, `97,0 %` de coordonnées jamais activées, `0,012 %` dominées par la donnée, ratio gradient données/ridge `92`. L'optimiseur n'est pas en cause (`JFI_OPTIMIZER_PATH_INDEPENDENCE_ESTABLISHED`).
3. **Le label porte très peu d'information par ligne.** La cible est l'issue WDL de la partie jouée, partagée par toutes les positions échantillonnées de cette partie, produite par un pilote à profondeur `8` avec `8 %` d'exploration. `context30` (`0,70 × WDL terminal + 0,30 × WDL conditionnel`) a rendu `+5,91 Elo` `[−0,15 ; +11,97]`, `P(>0) = 97,2 %` : un débruitage partiel du label paie déjà.
4. **Des labels vrais et denses ont déjà payé deux fois dans ce projet.** MMTO à travers la recherche : `+52 Elo` (gen2). Arbitre `d14 + EGDB` sur les issues on-policy, à positions identiques : `+49 Elo` (`cpx62-0722`), `61,5 %` d'issues renversées, confirmé par le plan factoriel `0726` (`+16` à `+19` pour les cellules adjugées contre `−8` à `−29` pour les cellules on-policy).
5. **Le volume de la même distribution ne bouge pas l'identification.** VOL8M `−14,95`, couverture par ouvertures aléatoires `−9,27`, on-policy à recette constante `−4,05`, mégacorpus `+2,32` non établi.

Conclusion opérationnelle : augmenter l'information **par position** plutôt que le nombre de positions, sans changer la classe, la recette de fit ni la distribution des positions.

---

## 2. Question R1

> Remplacer la cible `context30` par une cible **adjugée** — issue W/D/L de chaque position décidée par l'arbitre interne gelé (recherche Jass à profondeur fixe `14` + EGDB), blendée à parts égales avec le WDL terminal — améliore-t-il, à corpus, positions, recette et classe strictement identiques, d'abord la décision statique sur cohorte fraîche, puis la force ?

Un seul facteur change : **la cible**. Les positions sont les mêmes lignes, dans le même ordre.

---

## 3. Intervention gelée

### 3.1 Corpus

- entrée : le corpus byte-exact du dernier stage de fit ayant produit les bytes de `CURRICULUM` (`CURRENT_2M`), résolu fail-closed par manifeste et SHA, comme E3 ; aucune sélection de dataset au moment du job ;
- aucune ligne ajoutée, retirée, réordonnée ou dédupliquée ; les parties au ply-cap restent censurées comme dans le corpus source ;
- la cohorte `1638/1639/1640` et toute cohorte consommée restent interdites.

### 3.2 Arbitre interne gelé

Mode binaire existant `jass --deep-relabel` (`src/main.cpp`), étendu par cette PR de deux options **inactives par défaut** ; sans elles la sortie reste byte-identique à l'ancien comportement. Code SHA pinné dans le job, une passe par ligne :

1. position = les quatre bitboards + trait de la ligne JNNW ;
2. **EGDB d'abord** : si la base renvoie un WDL exact, `adj = WDL(EGDB)`, `score = adj × 10000`, `source = TB` ; aucune recherche ;
3. sinon, si le trait n'a aucun coup légal : `adj = −1` (perte du trait, règle du jeu), `score = −10000`, `source = TERMINAL` ; aucune recherche ;
4. sinon recherche à **profondeur fixe `14`**, paramètres de recherche `Q00` passés par `--search-params` (captures obligatoires seules en quiescence, baseline L3), EGDB **ON**, book **OFF**, `threads = 1`, **TT vidée avant chaque position** (`--clear-tt`), aucun `movetime` ; score `s` en centipions, POV du trait ; `source = SEARCH` ;
5. **bande de nulle gelée `50 cp`** (`--draw-band 50`, valeur par défaut du mode et des jobs `0722/0726`) : `adj = +1` si `s > +50`, `adj = −1` si `s < −50`, `adj = 0` sinon. La constante `50` n'est pas un paramètre de R1 ;
6. sorties : (a) un JNNW **relabellisé** de même longueur et même ordre, où seuls l'octet `wdl` (`adj`, POV trait) et le champ `score` (`s` brut, POV trait) diffèrent de l'original ; (b) un fichier de **tags de source** d'un octet par ligne (`--source-tags-out`) : `0 = SEARCH`, `1 = TB`, `2 = TERMINAL`.

Déterministe. Shardage par plages de lignes contiguës ; la fusion vérifie le nombre de lignes, l'identité byte-à-byte des 33 premiers octets de chaque ligne avec l'original, et publie le SHA256 des fichiers fusionnés. Aucune position n'est jouée, aucune partie n'est générée.

### 3.3 Cible R1

Outil `jobs/tools/l3_r1_adjudicated_target.py` (livré par cette PR, testé, fail-closed). Conversion en POV noir puis en probabilité : `p_term = (wdl_black + 1) / 2` depuis l'original, `p_adj = (adj_black + 1) / 2` depuis le relabellisé.

```text
y_R1 = 0.5 × p_term + 0.5 × p_adj
```

Le coefficient `0,5` est symétrique et non ajusté ; il n'est pas balayé. La cible est écrite dans le **même format de sidecar externe** que `context30` et consommée par `train_stream --target external`.

Un second sidecar diagnostique `y_ADJ = p_adj` est produit par le même outil, pour l'arm C décrit au §4.

### 3.4 Fit

Recette **byte-identique** à celle du dernier stage de `CURRICULUM`, un seul fit par bras, aucun sweep :

```text
--exact-fold --tempo-stage
--prior-mean <CURRICULUM> --prior-decay 0
--l2 1e-5 --lbfgs-gtol 1e-4 --lbfgs-maxcor 20
```

| Bras | Cible | Rôle |
|---|---|---|
| **A** | `context30` reconstruite à l'identique | contrôle : même code, même pipeline, refit du champion |
| **B** | `y_R1` | **primaire** |
| C | `y_ADJ` | diagnostique ; jouable seulement par la règle pré-déclarée du §4.3 |

`l2`, `gtol`, fold, tempo, prior, extras, quantification : inchangés. Le gain d'identification attendu d'un label moins bruité **ne** se matérialise **pas** dans R1 par un changement de `l2` ; un tel changement exigerait sa propre preregistration après le terminal R1.

### 3.5 Commandes gelées

```text
# arbitre, par shard k de lignes contiguës [a_k ; b_k)
jass --deep-relabel <shard_k.jnnw> <shard_k.adj.jnnw> 14 \
     --egdb <EGDIR> --cache-mb 512 --search-params "<Q00 résolu>" \
     --draw-band 50 --clear-tt --source-tags-out <shard_k.tags>

# fusion (ordre des shards = ordre des lignes), puis cible
python3 jobs/tools/l3_r1_adjudicated_target.py \
     --original <CURRENT_2M.jnnw> --relabelled <merged.adj.jnnw> --source-tags <merged.tags> \
     --out-r1 <y_r1.npy> --out-adj <y_adj.npy> --report <r1_target_report.json> \
     --context30 <context30.npy>

# fit, un par bras, recette byte-identique au dernier stage CURRICULUM
train_stream ... --target external --target-values <y_*.npy> --targets-report <...> \
     --exact-fold --tempo-stage --prior-mean <CURRICULUM> --prior-decay 0 \
     --l2 1e-5 --lbfgs-gtol 1e-4 --lbfgs-maxcor 20 --optimizer-report <...>
```

`--prior-precision-file` **n'apparaît dans aucune commande R1**.

---

## 4. Gates, dans l'ordre, fail-closed

### 4.1 G0 — micro-sonde et sizing (avant tout job complet)

- `nproc` imprimé par le job ;
- micro-sonde `--adjudicate-relabel` sur `2 000` lignes, un shard, avec TT vidée par position : rate mesuré en s/position ; l'ancre `0,033 s/position` (`0721`) est un ordre de grandeur **sans** vidage de TT et ne vaut pas comme rate ;
- ETA = `2 000 000 × rate / nproc` + build + fusion + deux fits ; garde `df` ; `RES`/`PROG` hors arbre git ; smoke-test write→read sur `2 000` lignes complet jusqu'au sidecar externe.
- EGDB shardée : `cache_mb × nshards < ~24 Go` (gotcha gravé après l'OOM `0723` : `512 × 16` OK) ; les moteurs EGDB peuvent mourir au démarrage en masse-parallèle, donc redémarrage sur mort et vérification du compte de lignes par shard ;
- micro-sonde obligatoire aussi pour le **taux de renversement** sur les `2 000` lignes : s'il sort de `[0,20 ; 0,80]`, arrêt et diagnostic avant tout job complet (les valeurs historiques sont `61,5 %` sur corpus bootstrap `d9` ; un pilote `d8` à `8 %` d'exploration devrait être dans la même région, mais ce n'est pas acquis).

### 4.2 G1 — hygiène du label (offline, zéro partie)

Publiés par l'outil de construction de cible, tous obligatoires :

- nombre de lignes du sidecar `=` nombre de lignes JNNW, SHA256 des deux ;
- répartition des tags `source` TB / TERMINAL / SEARCH (la profondeur est fixe à `14`, il n'y a pas de profondeur atteinte variable à publier) ;
- matrice de confusion `wdl_terminal × adj` (9 cellules) et **taux de renversement** global et par phase P0–P3 ;
- distribution W/D/L de `adj` dans les bandes de `assert_corpus_wdl.py` (nulles dans `[0,10 ; 0,60]`, |W−L| ≤ 10 points), sinon `R1_LABEL_GUARD_FAILED` et STOP ;
- distribution de `y_R1` (moyenne, quantiles) contre `context30` sur les mêmes lignes.

Aucune de ces statistiques n'est un critère de force ; elles rendent le label auditable.

### 4.3 G2 — décision statique fraîche (offline, zéro partie)

Cohorte **fraîche et target-blind** : sélection puis teacher par les outils gelés existants (`deep_sibling_*`), disjointe de toute cohorte consommée, seeds publiées dans le job, `≥ 4 000` parents avec minimum par cellule phase × trait. La cohorte est consommée après lecture.

Métrique : `pairwise` et `top-hit` contre le teacher `q200`, bootstrap parent-cluster `200 000`, seed publiée, comme les readouts T3.

```text
R1_OFFLINE_DECISION_SUPPORTED      ⇔  borne basse IC95 de pairwise(B) − pairwise(A) > 0
                                       ET top-hit(B) − top-hit(A) ≥ 0
R1_OFFLINE_DECISION_NOT_SUPPORTED  sinon
```

Règle pré-déclarée pour C : C n'est joué en force que si B rend `NOT_SUPPORTED` **et** C rend `SUPPORTED` par le même contraste contre A. Aucune autre substitution.

Diagnostic publié mais **non décisionnel** : `effective_df` et classes de coordonnées (outillage JFI) pour A et B. L'`effective_df` dépend du design et du ridge, très peu du label ; il est attendu quasi identique entre A et B. Il est publié pour empêcher toute sur-lecture, pas pour trancher.

`NOT_SUPPORTED` sur B et C ferme R1 sans partie : le label adjugé, à `α = 0,5` et `l2 = 1e-5`, n'est pas le levier. Aucun retuning, aucune bande de nulle alternative, aucun second fit.

### 4.4 G3 — force (après GO JFC distinct)

Porte standard `l3-model-gate-v1.sh`, bras retenu contre `CURRICULUM` :

- **deux pools d'ouvertures frais et disjoints**, `n = 6 000` parties chacun, vues Q00 et native `0,1 s`, EGDB identique des deux côtés, couleurs appariées ;
- `P(Elo > 0)` imprimé à côté de l'IC95, garde d'hétérogénéité `between_pool_z`, chaînage sur compteurs bruts ;
- `game skipped` publié et asserté `= 0` ;
- `wall_ratio` et `nps_ratio` du bras retenu contre `CURRICULUM` publiés : par construction attendus `≈ 1` (même classe, mêmes extras), mais la règle « aucun verdict sans coût mesuré » s'applique.

```text
R1_STRENGTH_ESTABLISHED       ⇔  P(Elo > 0) > 95 % sur pools chaînés ET |between_pool_z| < 1,96
R1_STRENGTH_NOT_ESTABLISHED   sinon
R1_INCONCLUSIVE_HARNESS       si une cellule est sous plancher ou game skipped ≠ 0
```

`ESTABLISHED` est une pré-condition d'entrée en procédure de bake, jamais une autorisation. `PROMOTION_AUTHORIZED = false` dans tous les jobs.

---

## 5. Ce que R1 ne fait pas

- aucun changement de `l2`, de fold, de tempo, d'extras, de géométrie, de quantification ;
- aucune précision de prior par coordonnée : le mécanisme `--prior-precision-file` est livré par la même PR **désactivé**, byte-identique quand absent, et sa politique d'accumulation inter-générations (R2) exige une preregistration séparée ;
- aucune boucle générationnelle (R3) ; aucun redémarrage from-scratch ;
- aucune cible score continue (sigmoïde du score brut) : `score_raw` est publié pour diagnostic uniquement ; une cible continue exigerait une preregistration séparée ;
- aucun MMTO, aucune cible de ranking ou de préférence ;
- aucune position, partie, coup ou poids externe ; l'arbitre est le moteur Jass lui-même et l'EGDB déjà utilisée en jeu ;
- aucune promotion, bake ou Pool2.

---

## 6. Lecture pré-déclarée

| Résultat | Lecture | Suite autorisée |
|---|---|---|
| G2 `NOT_SUPPORTED` pour B et C | l'information du label n'était pas la contrainte liante à recette constante | R2 (prior séquentiel) reste préregistrable indépendamment ; aucune variante R1 |
| G2 `SUPPORTED`, G3 `NOT_ESTABLISHED` | gain statique sans transfert en force, cas déjà vu (CTX3, T3/F6) | autopsie read-only ; aucun retune |
| G2 `SUPPORTED`, G3 `ESTABLISHED` | le label adjugé est un levier réel dans la classe | procédure de bake sur décision JFC ; R2 puis R3 préregistrables sur cette base |

---

## 7. Interdictions et données consommées

- la cohorte G2 est consommée après lecture ; aucun refit, sélection ou tuning ne peut la relire ;
- `1638/1639/1640` et toute cohorte antérieurement consommée restent interdites ;
- les terminaux `1685`, `1686`, `1689`, `1700`, `1705`, `1708`, `1714`–`1716`, `1884` restent immuables ;
- le merge de ce document ne lance rien.

---

## 8. Traçabilité requise

Chaque terminal R1 publie : code SHA du binaire arbitre et du fit, SHA256 du corpus source, du sidecar `adj`, des cibles `y_R1`/`y_ADJ`/`context30`, paramètres `Q00` résolus, profondeur `14`, bande `50`, chemin/version EGDB, `threads = 1`, statistiques G1 complètes, seeds de cohorte et de bootstrap, itérations L-BFGS de chaque bras (le signal de convergence fiable est l'asymétrie du compte d'itérations entre bras appariés), `effective_df` A/B, contrastes G2 avec IC95, et pour G3 les compteurs bruts, `P(Elo > 0)`, `between_pool_z`, `game skipped`, `wall_ratio`, `nps_ratio`, et le verdict exact pris dans les listes ci-dessus.
