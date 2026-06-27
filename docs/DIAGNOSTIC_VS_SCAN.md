# Diagnostic vs Scan — POURQUOI on perd (2026-06-23)

> Analyse des parties champion 32cf (fit L2=3e-5@35M) vs **Scan**, **eval pur (no-DB des 2 côtés)**, depth fixe.
> Source : job `ccx33-0435-scan-handicap-ladder` (18 parties/rung, déterministe → ordre de grandeur). À lire avec
> [PROGRESSION_LITTERATURE.md](PROGRESSION_LITTERATURE.md).

## Résultats bruts
**Échelle de handicap** (jass-depth vs Scan d11, no-DB, 18 parties) :
| jass-depth | score vs Scan d11 |
|---|---|
| 11 | 0,056 (1 gagnée / 17 perdues) |
| 13 | 0,000 |
| 15 | 0,028 |

→ **La profondeur ne rattrape PAS** (plat à ~0 même +4 plies). Ce n'est **pas** un manque de recherche.

**Analyse des 17 défaites (d11)** :
- **17/17 par COMBINAISON** : ≥2 pions-équ perdus en ≤2 plies (un *shot*). **0/17 dérive lente.**
- Phase : **plein milieu de partie**, **26 pièces** sur le damier (médiane), move ~27 (ply 54), **pions seulement** (rois présents seulement 4/17).
- Ampleur médiane : 2 pions-équ (un coup net qui gagne une pièce).

## Conclusion
**On se fait cueillir par des COMBINAISONS en plein milieu de partie men-only — pas en finale, pas par dérive
positionnelle, pas par manque de profondeur.** (Ma 1ʳᵉ lecture « blocage finale » était FAUSSE : *no legal move*
est juste la fin normale d'une partie de dames.)

## Hypothèse forte (à tester) : notre ÉLAGAGE nous rend tactiquement aveugles
Normalement, chercher plus profond évite les combinaisons. Or la profondeur ne rattrape pas → le coupable probable
est notre **élagage forward** (`multicut` min6/moves8/cuts2 + `razor` max4, bakés ON, **+50 Elo EN SELF-PLAY** 0336/0343).
Il **coupe les lignes tactiques défensives** : à toute profondeur nominale la ligne est élaguée → la défense n'est jamais vue.
**Invisible en self-play** (les 2 côtés élaguent pareil), **mais une vraie faiblesse contre un adversaire tactiquement
aiguisé comme Scan.**

- **Test décisif** : rejouer avec **élagage OFF** (`--jass-search-params "multicut_min_depth=0,razor_max_depth=0"`).
  - Si le score **monte** → c'est l'élagage (faiblesse de **RECHERCHE**, réparable, **pas NNUE**).
  - Si le score **reste ~0** → c'est l'**EVAL** (elle guide dans des positions shot-vulnérables) → richesse linéaire / NNUE.
- Job A/B : `ccx33-0436-scan-pruning-ab` (élagage ON vs OFF, d11, no-DB, même champion).

## Ce que ça change au cadre stratégique
- Avant ce diagnostic : « eval-limité → NNUE » semblait la seule issue.
- Maintenant : **une part de l'écart à Scan pourrait être de la RECHERCHE** (élagage trop agressif vs adversaire fort),
  **récupérable sans changer de classe**. À trancher par l'A/B avant toute décision NNUE.
- ⚠️ Réserves : 18 parties déterministes, champion mi-itération, no-egdb (mais le décrochage est en **milieu** de partie
  à 26 pièces → l'egdb n'y change rien).

## VERDICT A/B (0436, 2026-06-23) — c'est l'EVAL, et le linéaire n'est PAS épuisé
- élagage **ON** = 0,056 · élagage **OFF** = 0,028 → **B ≈ A : ce n'est PAS la recherche.** Hypothèse élagage RÉFUTÉE.
- Donc l'écart est dans l'**EVAL**. MAIS **Scan = 2,1M poids, nous = 8,5M, et il nous bat** ⇒ **PAS un plafond de
  capacité** : notre best-linear-fit possible est **≥** le sien ; **notre FIT est moins bon** (self-play borné par notre
  pilote plus faible → point fixe trop bas).
- **⇒ Prochain levier LINÉAIRE : distiller depuis Scan au scale** (Scan dispo en binaire ; `relabel_with_scan.py`,
  `scan_selfplay_gen.py` → fit train_stream → juger vs Scan) pour atteindre SON point fixe **dans la classe linéaire**.
  C'était classé MORT (0073-0084) mais **à ≤2M = confondu par le fit-volume** → à revisiter au scale.
- ⛔ **NNUE INTERDIT** tant que ce levier (et les autres linéaires) ne sont pas épuisés (RÈGLE GRAVÉE, cf CURRENT.md).

## MESURE TACTIQUE CHIFFRÉE (0440, 2026-06-23) — combinaisons de livre, jass vs Scan
Job `ccx33-0440-dilf-tactical` : champion 3e-5 **vs Scan**, **depth 11, eval pur (no-DB)**, joué **depuis 305
combinaisons de livre** (dilf `ALL_DIAGRAMS` → `data/dilf_combinations.fen`, médiane 26 pièces = plein milieu).
Chaque position jouée 2× (jass au trait / Scan au trait via swap). Métrique = **taux de conversion du camp AU TRAIT**
(celui qui a le coup gagnant). Verdict reconstruit depuis les 610 parties dumpées (`artefacts/games/`) :

| Camp **au trait** (a la combinaison gagnante) | Conversion |
|---|---|
| **JASS** | **0,246** (75 / 305) |
| **SCAN** | **0,954** (291 / 305) |
| **Écart** | **−0,708** |

- **Scan trouve+convertit 95 % des combinaisons ; jass seulement 25 % de LES MÊMES.** Pire : **499/610** parties
  finissent par « jass sans coup légal » (maté/bloqué) vs 67 pour Scan ⇒ **jass change régulièrement une position
  GAGNÉE en DÉFAITE.**
- À depth 11 ces combinaisons (2-6 plis) sont **dans l'horizon** : jass devrait les voir. S'il ne convertit pas,
  **c'est son éval qui le détourne du bon coup** (shot-vulnerable) — cohérent avec le verdict A/B (l'éval, pas la recherche).
- Caveat : la métrique mêle attaque (jass vs défense forte de Scan) et défense (Scan vs défense faible de jass) ;
  les deux pointent dans le même sens, donc −0,708 majore le pur trou d'attaque, mais la direction est certaine.
- **C'est notre meilleure cible MESURABLE** : refaire ce match (25 % → ?) après chaque champion = la jauge de progrès.

## CADRE STRATÉGIQUE COURANT (2026-06-23, après décisions JFC)
- ❌ **Distillation Scan ABANDONNÉE** (la ligne « distiller depuis Scan » ci-dessus est CADUQUE) : Scan est monté
  **sans** distillation, on doit pouvoir grimper sans (plafond = Scan ; dépendance Scan). Règle gravée.
- ✅ **Plan de base : self-play 100 % ÉPURÉ 25M, diversifié** (`cpx62-0442-freshmix-loop`) — chaque boucle régénère
  un corpus neuf avec une **composition de μ distincte** (profondeur de jeu d8/d10/d12 + seeds combinaisons dilf /
  milieux lidraughts + `--random-open-plies` + `--explore-eps`). Pilote = meilleur champion connu. Jugé vs base 3e-5 ;
  une recette qui passe `vs_base > 0,55` = composition de μ qui **casse le point fixe** (self-play à son point fixe = 0,50,
  cf `cpx62-0428` iter1/2 = 0,50). La cible directe : le trou tactique 25 %→ ci-dessus.
- 🅱️ **Réserve si stagnation : value-target distillation INDÉPENDANTE** (label = recherche profonde jass d18-20 + EGDB,
  PAS Scan). Outillage prêt et dormant : `--deep-relabel` (src/main.cpp) + `train_stream --target value` ;
  sonde `ccx33-0443-deeplabel-probe` en `jobs/paused/`. Failles connues (à corriger avant un vrai run) : filtre quiet
  / valeur-feuille, clip des scores de mat, contrôle WDL-vs-valeur, et **itérer** le relabel (sinon plafond sous notre
  propre force). Ne casse PAS un éventuel plafond de features (seul risque que rien de linéaire ne corrige).
- ⛔ **NNUE toujours INTERDIT** tant que le linéaire n'est pas poussé à fond (RÈGLE GRAVÉE).

## BRANCHE SEARCH/PROMOTION FERMÉE (2026-06-24, verdicts 0444-0452)
Investigation « et si l'écart combinaisons était de la RECHERCHE (élagage) ou un mur de promotion ? » → **non, cul-de-sac.**
- **0446 (ablation)** : LMR(27 %)+LMP(26 %) cachent ~40 % des combinaisons ratées **à profondeur fixe d11** → fix
  `no_reduce_forcing` construit (gaté, exempte les coups forçants de LMR/LMP).
- **0451 (décideur, A/B vs Scan à MOVETIME 300 ms)** : le fix **n'apporte rien à temps réel** — conversion combinaisons
  baseline **0,519** vs fix **0,506** (≈), jeu général légèrement pire. À movetime jass atteint **d14-16** → il trouve
  DÉJÀ les combos que le dé-élagage récupérait à d11 → bénéfice redondant + coût −1,6 plies. **Param gardé OFF par défaut.**
  ⇒ Le « gain search » était un **mirage du test à profondeur fixe d11** ; le d11 de 0440 **sous-estimait jass** (0,246
  vs 0,519 réel à movetime). Le résidu (0,52 vs Scan 0,95) est l'**ÉVAL**, pas la recherche.
- **0450/0453 (valeur du roi)** : l'éval valorise déjà le roi à **~3,5 hommes** → le mur promotion n'est PAS la valeur du roi.
- **0452 (promo egdb, 37 686 finales gagnantes)** : **0 sacrifice-de-promotion** trouvé → ce motif est du **MILIEU de partie**,
  pas de la finale (≤7 pièces) ; egdb ne peut pas le tester. (Branche promotion abandonnée — JFC, option B.)
- **CONCLUSION** : la recherche/l'élagage n'est PAS le levier. Le mur est l'**ÉVAL au milieu de partie** (combinaisons
  positionnelles shot-blind). Seuls leviers restants : **données/μ** (`0442`) et, à terme, **features linéaires plus riches**.

## SAGA SUPERVISION TACTIQUE (2026-06-25) — FIT confirmé, l'AUTO-supervision est morte, pivot VÉRITÉ EXTERNE
> Verdicts reconstruits depuis les game-dumps gold (les `RESULTS.txt` n'avaient pas flushé ; conversion 0440 recalculée sur
> les 610 parties/corpus). Le détour tactique remplaçait `0442` (tué en vol) ; bilan ci-dessous.

### 1. FIT, pas FEATURE — `0461` (le test décisif pré-engagé)
men-only vs king-aware (rois dans l'occupancy des patterns, build `-DJASS_KING_PATTERNS`), **même corpus**, jugés
**spécifiquement sur la conversion 0440** (pas en agrégat — le verrou 0401/0408/0409 portait sur la force GLOBALE) :

| build | conversion 0440 |
|---|---|
| **men-only** (défaut) | **0,300** (92/305) |
| **king-aware** | **0,284** (86/305) |

→ mettre les rois dans les patterns **n'améliore PAS** la conversion des combinaisons. **La géométrie n'est pas le mur.**
Le levier est le **FIT/les données** — géométrie **verrouillée**, l'hypothèse « feature roi manquante » (SCAN_EVAL_DIFF
LEAD 1/2) est **réfutée sur la cible qui compte**.

### 2. AUTO-supervision tactique = MORTE — `0460` + `0462` (deux échecs, une seule cause)
On a voulu fabriquer un flux de supervision tactique en **étiquetant avec la recherche de jass lui-même** :
- `0460` (relabel-TOUT le milieu à profondeur jass) : self-direct **0,472**, 0440 **0,259**. **Auto-distillation** — 72 %
  des « corrections » étaient de l'**opinion d'éval**, pas de la vérité-terrain. Recul net.
- `0462` (shot-filter : ne garder que les positions où une recherche **élagage-OFF d6** trouve un gain forcé ≥2, label =
  signe du score) : 0440 **0,285 < 0,302** (egdbmix). Régresse aussi.

> **La cause commune** : la recherche de jass ne peut **étiqueter que les shots qu'il VOIT déjà**. Le trou 0440 **EST** les
> ~70 % de combinaisons qu'il **ne voit pas**. **On ne peut pas enseigner ses angles morts avec des labels produits par
> l'œil aveugle.** C'est la version-DONNÉES de Tsitsiklis-Van Roy : le point fixe est borné par ce que le **pilote sait
> voir**. Le volume ou le filtrage n'y changent rien tant que la SOURCE des labels reste jass.

### 3. PIVOT — la donnée doit venir d'une VUE EXTERNE — `0464` puis `0466` (RÉSULTAT : PLAT)
FIT est le mur (0461) **mais la donnée auto-générée est insuffisante par construction** (0460/0462). Seule issue données :
injecter des combinaisons **trouvées par un agent voyant**. → `ccx33-0464-master-combo-mining` :
- source = **vraies parties** (`data/expert_games.db`, box-local, fetch lidraughts `0438`) ;
- détection = **profil matériel de la ligne RÉELLE** : sacrifice (le matériel du gagnant baisse) → **regain net ≥2** dans la
  fenêtre, **gagnant au trait** ; aucune recherche moteur dans la détection ;
- label = **résultat réel de la partie** (wdl=+1 côté gagnant). ⇒ **ni auto-supervision, ni distillation Scan** : pure
  vérité-terrain, la combinaison a été **vue par un humain** (au-delà des angles morts de jass) ET **a gagné**.
- **A/B propre** : **même base que 0462** (pool+egdb), on ne change QUE la source du flux tactique ⇒ « **vue propre (0,285)
  vs vue externe** ». Décision :
  - `mastercombo > 0,302` ET `> 0,285` ⇒ la vue externe **déplace** 0440 → lever confirmé, scaler le mining ;
  - `mastercombo ≈ 0,30` ⇒ même la vérité-terrain tactique externe ne bouge pas 0440 à features verrouillées ⇒ **indice
    fort de plafond FEATURE linéaire** ⇒ **rouvre proprement le débat du gate NNUE (C3/C4)**.

**RÉSULTAT `0464`** : 155k combinaisons minées (la DB lidraughts a survécu), oversample ×8 (~5,4 % du corpus). Conversion 0440
**apples-to-apples sur 232 ouvertures-attaquant communes** : **combo 0,304 vs egdbmix 0,302** (+0,002 ; juge tronqué à 76 % par
le wall-time mais la compa sur le sous-ensemble jugé est propre). → **PLAT.**

**CONTRÔLE DILUTION `0466`** (réserve : combos à seulement ~5,4 % ⇒ peut-être noyés) : mêmes combos à **poids LOURD ~35 % du
corpus**, 1 fit, 1 juge vs Scan sur DILF complet (305, pas de troncature) → conversion 0440 = **0,308** (94/305). **Dose-réponse
0 %→5,4 %→35 % = 0,302 → 0,304 → 0,308 : PLATE.** ⇒ **ce n'était PAS la dilution.**

> **CONCLUSION (4 formes testées, toutes plates ou pire)** : relabel-tout (0460, 0,259) · self-shot-filter (0462, 0,285) ·
> vue-externe diluée (0464, 0,304) · vue-externe lourde (0466, 0,308). **Aucune supervision tactique — quelle que soit la
> source du label OU le poids — ne déplace 0440.** Combiné à 0461 (FIT, pas feature), c'est le **plus fort signal de plafond
> FEATURE linéaire sur l'axe combinaisons** qu'on ait. **Le levier données-tactique C2-(2) est CLOS.**
>
> ⚠️ **Une seule réserve de VALIDITÉ subsiste** (avant de décréter le plafond) : on a sur-pondéré la **position-RACINE**
> pré-combinaison (étiquetée gagnante), PAS les nœuds **intermédiaires matériel-en-bas** de la ligne forçante — or convertir
> exige que l'éval voie *au-delà du sacrifice* (les nœuds où le matériel est temporairement négatif). Un dernier variant
> **« full-line »** (sur-pondérer toute la ligne forçante, pas seulement la racine) testerait un MÉCANISME différent. À
> **arbitrer** contre la règle anti-« encore une idée » (C2 = LISTE CLOSE) : est-ce une faille de validité du test, ou le
> tapis-roulant qu'on s'interdit ? — décision JFC.

### 4. Reprise du plan de base — `0465` (en parallèle) + principe TVR-données
`0442` (self-play diversifié) n'avait **jamais** été joué (tué pour le détour tactique). Repris en `cpx62-0465-freshmix-12m`,
**pilote = champion-egdbmix**, ancre/juge = egdbmix (⇒ `vs_base>0,55` = la recette casse le point fixe du **meilleur**
champion actuel). **Re-dimensionné 25M→12M** : TVR ⇒ au-delà de la saturation (~10M) le volume **ne déplace pas** le point
fixe, il ne réduit que la **variance** de `vs_base` (bruit dominant = le juge, 28 paires de parties) — 12M screene les 5
recettes en ~2× moins de mur, on **refit la gagnante à plein volume** ensuite. (`0456` zombie 10M/ccx33 tué au passage.)

## LE MUR DES ~11 LEVIERS + LE DÉCIDEUR FINAL (2026-06-27) — bootstrap from-scratch ×2 seeds
Après 0465 et la saga ci-dessus, on a continué d'épuiser l'axe données/entraînement. **Bilan : ~11 leviers, TOUS plats à
~0,28 sur 0440** (la conversion de combinaisons vs Scan, IC ±0,05) :

| Levier (job) | 0440 | Levier (job) | 0440 |
|---|---|---|---|
| relabel-tout (`0460`) | 0,259 | bootstrap deep-relabel (`0474`) | 0,25–0,29 |
| shot-filter (`0462`) | 0,285 | champ-3-tactique (`0476`) | 0,284 |
| combo-mining externe (`0464`) | 0,304 | sparring localisé (`0477`) | 0,236 |
| combo-poids-lourd (`0466`) | 0,308 | **élagage-gen OFF** (`0479`) | **0,261** |
| full-line volume plein (`0468`) | 0,251 | *(egdbmix baseline)* | *0,302* |
| freshmix μ (`0470`) | 0,313 | *(Scan, même classe 2,1M poids)* | **0,95** |
| sparring v1 (`0473`) | 0,279 | | |

- **`0479` a réfuté la dernière conviction forte** : on était sûrs que l'élagage au gen aveuglait les labels (cachait les shots
  à profondeur fixe). À 5M/bras : **OFF 0,261 ≈ ON 0,280** (OFF même un peu pire, IC chevauchants). Ce n'était pas ça.
- **Le sparring-vs-Scan (levier B) a été essayé** (`0473` global, `0477` localisé sur la falaise matérielle) et **n'allume pas**
  sous ces formes — la distribution étroite (cliff-only) **éloigne** même l'éval de la justesse positionnelle (0477 = 0,236, HURT).

### Le seul ingrédient Scan jamais répliqué : le bootstrap FROM-SCRATCH
Recherche clean-room (méthode publiée, pas le code GPL) : **Scan a été monté depuis ZÉRO en self-play pur** — seed = éval
matérielle primitive + règles, **aucun prof, aucun master-game** — logistic regression **itérée sur des centaines de
générations**. Le « prof » de Scan = **sa propre recherche profonde + l'itération**, pas un agent voyant externe.

**Notre angle mort méthodologique** : à chacun des 11 essais, on a piloté le gen depuis **egdbmix** = un point fixe **déjà
formé, possiblement coincé**. On a fait varier μ/volume/élagage **autour** de ce point fixe — **jamais on n'a migré le point
fixe lui-même** en repartant d'un seed primitif et en itérant. C'est le dernier trou dans la preuve « le linéaire est épuisé ».

### Le test (lancé) : 2 bras croisés sur le SEED — `cpx62-0481` + `ccx33-0482`
Même protocole exact (10M/gen, depth 10, **élagage ON** — 0479 confirme —, chaîne forcée 10 générations, juge 0440 vs Scan à
chaque génération + IC95), **seule variable = le seed de la génération 1** :
- **`0481`** : seed = éval embarquée par défaut (matériel + king-PST + mob + balance ; primitif *appris*, loin d'egdbmix).
- **`0482`** : seed = **matériel PUR** (men=1, roi=3, zéro prior positionnel ; forgé par fit-sur-signe-matériel via le pipeline
  canonique + vérif `--eval-position` — pas de binaire forgé à la main, le matériel des hommes est encodé *dans* les patterns),
  **totalement indépendant** d'egdbmix = équivalent littéral du seed « piece-count, roi=3h » de Scan.

**Pourquoi 2 seeds** : 0481 part d'un primitif qui est un *ancêtre de la lignée egdbmix* (objection : « pas vraiment parti de
zéro »). 0482 part d'un seed qui ne partage **que les règles** avec egdbmix. Si **les deux** convergent vers ~0,28, la preuve
« plateau = propriété de la classe, pas de l'init » est **blindée** (deux bassins de départ indépendants → même point fixe).

**Lecture (le décideur de la gate)** :
- deux courbes **montent >0,28** ⇒ egdbmix était coincé, **linéaire PAS épuisé** ⇒ continuer (refit à plein volume) ;
- deux courbes **collent ~0,28** ⇒ plateau = **classe** ⇒ **linéaire PROUVÉ épuisé** ⇒ gate NNUE s'ouvre **avec preuve** ;
- un seul bras monte ⇒ dépendance au seed/chemin ⇒ point fixe déplaçable ⇒ creuser ce bras.

**Honnêteté** : le scénario le plus probable reste la reconvergence à ~0,28 (egdbmix descend lui-même d'un bootstrap de ce
seed). Mais une reconvergence **propre et mesurée** EST le livrable — c'est la pièce manquante qui rend l'épuisement linéaire
**prouvé** au lieu de **présumé**, et c'est elle (et elle seule) qui ouvre proprement le débat C3/C4.

