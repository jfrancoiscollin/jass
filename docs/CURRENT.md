# CURRENT — source de vérité active (programme « battre Scan »)

> # ⛔⛔ RÈGLE GRAVÉE DANS LE MARBRE (2026-06-23, JFC) — AUCUN NNUE ⛔⛔
> **ZÉRO NNUE, ZÉRO réseau, ZÉRO changement de classe TANT QUE la classe LINÉAIRE n'est pas POUSSÉE À FOND.**
> Justification empirique : on a **8,5M poids vs 2,1M pour Scan** et on ne l'a **même pas égalé** → la classe linéaire
> est **LOIN d'être épuisée** ; notre FIT est juste moins bon que celui de Scan. Leviers linéaires à épuiser AVANT toute
> évocation de NNUE : **distillation depuis Scan au scale** (Scan = prof dispo), itération, géométrie, qualité de data,
> recherche. **NNUE = INTERDIT** jusqu'à preuve d'un vrai plafond linéaire (best-linear-fit atteint ET < Scan). Non négociable.

> **1 page, à jour à CHAQUE verdict.** Le détail vit ailleurs : [BOUCLE_VIRTUEUSE.md](BOUCLE_VIRTUEUSE.md) (système
> actif), [JOURNAL_DE_BORD.md](JOURNAL_DE_BORD.md) §0 (faits/chronologie), [SCAN_METHODOLOGY_GAP.md](SCAN_METHODOLOGY_GAP.md)
> (règles permanentes), [ARBRE_DECISION.md](archives/ARBRE_DECISION.md) (principe). MAJ : **2026-06-27** (verdicts en tête).

## 🏆 CHAMPION COURANT (promu 2026-06-24) — `champion-egdbmix` (bitbase-mix)
> **Nouveau meilleur 32cf** : `jobs/results/ccx33-0454-egdb-mix/artefacts/champion-egdbmix.pjtw.gz`.
> Fit sur (pool self-play **+ 4M positions egdb-finale exactes**, phase-weighté → ne touche que la banque EG).
> Gains mesurés (0454) vs le champion 3e-5 précédent : **+58 Elo self-play** (0,583), **conversion de finale vs Scan
> 0,867 → 0,900**, **précision décisive finale 88,2 % → 94,4 %** (plafond linéaire egdb-only = 97,3 %).
> ⇒ **Le mix egdb-finale est BAKÉ dans la recette** : toute future boucle/champion inclut cette étape (gen egdb-WLD
> + mix phase-weighté). Premier +Elo concret post-diagnostic → **le linéaire n'est PAS épuisé (jus dans la finale).**
> Le trou MILIEU (combinaisons) reste ouvert — voir VERDICTS 2026-06-25.

## 🔑 VERDICTS 2026-06-27 — le MUR des ~11 leviers, et le bootstrap from-scratch ×2 seeds
> MAJ **2026-06-27**. Suite directe du recadrage 2026-06-25 (« c'est le FIT / la distribution des labels, pas les features »).
> ⚠️ **SUPERSEDÉ le 2026-06-27 soir** : le briefing externe §3 a montré qu'un éval linéaire **statique** ne peut PAS encoder
> des combinaisons résolubles par la **recherche** ⇒ « 2 seeds plats » ne prouve PAS « linéaire épuisé ». Le bootstrap est
> **rétrogradé** au rang d'info (décideur faible) et **mis en pause** ; le vrai décideur = les **extensions** (`0483`, #1).
> Voir « 🔬 EN TEST MAINTENANT » + « PHASE IMPLÉMENTATION » ci-dessous.

- **HYPOTHÈSE ÉLAGAGE-GEN RÉFUTÉE (`0479`, A/B 5M/bras, dimensionné pour conclure)** : on pensait que l'élagage forward
  (multicut/razor/LMR/LMP) baké ON **aveuglait nos labels** au gen (cachait ~40 % des shots à profondeur fixe → distribution
  shot-blind). Verdict : élagage **ON = 0,280** [0,236 ; 0,325] vs **OFF = 0,261** [0,216 ; 0,310] ⇒ **OFF n'aide PAS** (même
  légèrement pire, IC chevauchants). **L'élagage au gen N'EST PAS le coupable.** ⇒ défaut **gen = élagage ON** (confirmé). Le
  bon paramétrage reste : **gen = élagage ON** (0479) **ET** jeu/movetime = élagage ON (0451 : OFF au jeu = −1,6 plies).
- **LE MUR : ~11 leviers données/entraînement TOUS plats à ~0,28 sur 0440.** Rien ne déplace la conversion de combinaisons :
  `0460`=0,259 · `0462`=0,285 · `0464`=0,304 · `0466`=0,308 · `0468`=0,251 · `0470`=0,313 · `0473`(sparring v1)=0,279 ·
  `0474`(bootstrap deep-relabel)=0,25–0,29 · `0476`(champ-3-tactique)=0,284 · `0477`(sparring localisé)=0,236 · `0479`=0,261.
  **Ni volume, ni μ, ni élagage (gen/jeu), ni encodage du sparring, ni seed tactiquement riche.** Scan (MÊME classe linéaire,
  **2,1M poids**) est à **0,95**. Le sparring-vs-Scan (B) a été essayé (`0473`/`0477`) et **n'allume pas** sous les formes testées.
- **LE SEUL INGRÉDIENT SCAN JAMAIS RÉPLIQUÉ = le bootstrap FROM-SCRATCH.** Recherche clean-room (méthode publiée, pas le code) :
  Scan a été monté **depuis zéro en self-play pur** — seed = éval matérielle primitive + règles, **PAS de prof, PAS de
  master-games** — logistic regression **itérée sur des centaines de générations**. Nous, à **chacun** des 11 essais ci-dessus,
  on a piloté le gen depuis **egdbmix** = un point fixe **déjà formé, possiblement COINCÉ** ⇒ on a fait varier μ/volume/élagage
  **autour du même point fixe**, sans jamais **migrer le point fixe lui-même**. C'est le **dernier trou** dans la preuve « le
  linéaire est épuisé », et le dernier levier 100 % fidèle à Scan avant la gate.
- **LANCÉ — bootstrap from-scratch, 2 bras (croisés sur le SEED)** : même protocole exact (10M/gen, **depth 10**, **élagage ON**,
  chaîne forcée 10 générations, juge **0440 vs Scan à chaque génération** + IC95), **seule** variable = le seed de la gen 1 :
  - **`cpx62-0481`** : seed = **éval embarquée par défaut** (matériel + king-PST + mob + balance ; primitif *appris*, loin d'egdbmix).
  - **`ccx33-0482`** : seed = **matériel PUR** (men=1, roi=3, **zéro prior positionnel** ; forgé par fit-sur-signe-matériel +
    vérif `--eval-position`), **totalement indépendant** d'egdbmix ⇒ équivalent littéral du seed « piece-count, roi=3h » de Scan.
- **LE DÉCIDEUR DE LA GATE** (lecture des 2 courbes) :
  - les **deux bras MONTENT** au-delà de 0,28 ⇒ egdbmix était un point fixe **coincé**, **le linéaire n'est PAS épuisé** ⇒ on continue (refit à plein volume).
  - les **deux COLLENT à ~0,28** malgré deux seeds indépendants ⇒ le plateau est une **propriété de la CLASSE** (pas de l'init) ⇒
    **le linéaire est PROUVÉ épuisé** ⇒ **la gate NNUE s'ouvre proprement, preuve à l'appui (11 leviers + bootstrap ×2 seeds).**
  - **un seul bras monte** ⇒ dépendance au seed/chemin ⇒ le point fixe est déplaçable ⇒ on creuse ce bras.
- **ÉTAT RÈGLE GRAVÉE** : ⛔ NNUE toujours INTERDIT. Ces deux bras sont le test final qui rend l'épuisement **prouvé** plutôt que
  **présumé** ; c'est leur verdict (et lui seul) qui peut ouvrir le débat C3/C4 — pas une « impression de plateau ».

## 🔑 VERDICTS 2026-06-25 — FIT confirmé, l'auto-supervision tactique est MORTE, pivot VÉRITÉ EXTERNE
> Trois résultats reconstruits depuis les game-dumps gold (les `RESULTS.txt` n'avaient pas flushé) → conclusion nette.

- **FIT, pas FEATURE (0461, ex-`0457`)** : men-only vs king-aware **jugés sur le set 0440** (le test décisif pré-engagé).
  Conversion 0440 : **men-only 0,300 · king-aware 0,284** → mettre les rois dans l'occupancy des patterns **n'aide PAS**
  à convertir les combinaisons. ⇒ **la géométrie n'est pas le mur** ; le levier est bien le **FIT/les données** (notre pari
  tient). La géométrie reste **verrouillée**. (Résout le lever C2-(1) et la branche « feature roi manquante ».)
- **Auto-supervision tactique = MORTE (0460 + 0462)** — les deux tentatives ont échoué, **pour la même raison de fond** :
  - `0460` (relabel-TOUT le milieu, recherche profonde jass) : self-direct **0,472**, 0440 **0,259** → **auto-distillation**
    (72 % des « corrections » = opinion d'éval, pas vérité-terrain). Recul.
  - `0462` (shot-filter : ne garder que les positions à shot forcé ≥2, labels = recherche d6 élagage-OFF de jass) :
    0440 **0,285 < 0,302** (egdbmix). Régresse aussi.
  - **LE point** : étiqueter avec **la recherche de jass lui-même** ne peut enseigner que les shots **qu'il voit déjà**.
    Or le trou 0440 EST les ~70 % de combinaisons qu'il **ne voit pas**. **On ne peut pas apprendre ses angles morts avec
    des labels produits par l'œil aveugle.** (Version-données de Tsitsiklis-Van Roy : le point fixe est borné par ce que le
    pilote **sait voir**.) ⇒ le lever C2-(2) « supervision tactique » **dans sa forme AUTO-supervisée est CLOS**.
- **⇒ PIVOT : la donnée doit venir d'une VUE EXTERNE.** FIT est le mur (0461) mais la donnée **auto-générée est insuffisante
  par construction** (0460/0462). Seule issue restante côté données : injecter des combinaisons **trouvées par un agent
  voyant** (parties de maîtres/lidraughts où le coup gagnant a été **joué ET gagné**), étiquetées par le **résultat réel**
  — **ni auto-supervision, ni distillation Scan** (aucun moteur dans le label).

## 🔬 EN TEST MAINTENANT (snapshot live — 2026-06-27 soir) — LE DÉCIDEUR MANQUANT : extensions forçantes
> **Recadrage briefing externe #1** (accepté) : « c'est l'ÉVAL pas la recherche » N'EST PAS prouvé. 0436/0451 ont isolé
> l'**élagage** et la **non-réduction** — JAMAIS une **extension**. Et (briefing §3) un éval linéaire statique **ne PEUT PAS**
> encoder des combinaisons résolubles par la recherche, quelle que soit la distribution d'entraînement ⇒ **2 seeds plats
> (0481/0482) ne prouvent PAS « linéaire épuisé »**. Le vrai décideur = est-ce que les **extensions** bougent 0440.

| box | job | ce qu'on teste | décision |
|---|---|---|---|
| **cpx62** | `0483-forcing-extension-ab` ⏳ tourne | flag `ext_forcing` (search.cpp, gated) : étend +1 ply tout coup quiet forçant une capture (sac) + exempte LMR/LMP. A/B sur jauge **0440** (champion egdbmix, **sans re-entraînement**), 3 bras : baseline / no_reduce-seul / ext_forcing | **C hors IC (>~0,35)** = l'écart était la RECHERCHE → baker + re-juger movetime ; gate NNUE non pertinente. **C~A** = c'est l'ÉVAL (prouvé sans le confond extensions) |
| **ccx33** | `0484-tools-verify` ⏳ tourne | vérif réelle des outils #2/#5/#6 (suites unit + run sur `expert_games.db`) + livre la **calibration #5** (Texel K + ECE/phase d'egdbmix) | JNNW valides + ECE/phase → feu vert pour la recette self-play propre |

- **Check local `ext_forcing` (avant déploiement)** : change **12/13** combinaisons dilf à d11 — les scores flippent vers le
  **sacrifice** (ex. −155 → +122). La recherche **trouve** enfin les shots. **Mais** : voir le sac en recherche ≠ le convertir
  vs Scan (qui défend) — c'est pourquoi 0483 joue des **parties complètes** (teste si les sacs sont SAINS, pas juste optimistes).
- ⚠️ **Caveat 0451** (le piège à éviter) : `no_reduce_forcing` à **movetime** = 0,506 ≈ 0,519 baseline (redondant car jass
  atteint déjà d14-16). Donc si 0483 (d11) monte, il **faut** un A/B **movetime NPS-compensé** pour écarter le « mirage d11 ».

### 🛠️ PHASE IMPLÉMENTATION (directive JFC : « tout implémenté/testé/vérifié AVANT de relancer le self-play »)
> Boucles from-scratch **0481+0482 MISES EN PAUSE** (tuées, reprise-safe). On code/teste les leviers du briefing externe,
> puis on lancera **une** recette self-play propre. Implémenté + **unit-testé** ce tour, déployé sur `main` :

| # | livrable | ce que ça fait | état |
|---|---|---|---|
| **#1** | `ext_forcing` (`search.cpp`/`search_params.hpp`, gated OFF) | extension forçante +1 ply (cf ci-dessus) | code + build OK ; A/B `0483` en cours |
| **#2** | `tools/build_ballots.py` | ouvertures réelles diverses/déséquilibrées (ply 6-12) + **miroir couleur** (rot180+swap = symétrie exacte) → `--seed-file` | unit-testé (miroir involutif, fenêtre plis, déséquilibre) |
| **#5** | `tools/eval_calibration.py` | **K de Texel** (calibration eval→winprob, *a posteriori*, ne ré-entraîne rien) + **ECE par phase** | unit-testé (récup K synthétique) ; chiffres réels via `0484` |
| **#6** | `tools/master_games_to_jnnw.py` | parties entières → positions **quiètes** (capture obligatoire ⟹ quiet ssi coup non-`x`) labellisées **résultat réel**, **fréquence naturelle** (PAS d'oversampling de racines comme 0464/0466/0468) | unit-testé (filtre quiet, labels STM-POV) |
| **#4** | audit `--quiet-only` | **CONFIRMÉ jamais utilisé** (11 leviers + 0481/0482 entraînés sur positions à capture en attente) ; fix = passer le flag (existe) | à intégrer à la recette |

- **#5 — honnêteté** : le #5 *littéral* (« fitter K=2.0 codé en dur ») **N/A** — `train.py` fait une **régression logistique
  complète** (`z=w·x` logit, gradient `σ(z)−y`) ⇒ la température est **déjà fittée** (dans `w`), l'échelle train↔inférence est
  cohérente, et re-pondérer = `--phase-weight` = **MORT** (−210 Elo). La version implémentée fitte le K de **calibration**
  (utile, distinct) et mesure l'ECE/phase — teste « le milieu est-il mal calibré ? ».
- **RECETTE SELF-PLAY PROPRE (à lancer quand 0483 + 0484 verts)** : gen avec **`--quiet-only`** (#4) + **`--seed-file=ballots`**
  (#2) + mélange **masters-naturels** (#6) à fréquence naturelle + **`ext_forcing` au jeu SI 0483 le valide** (#1). Rien lancé
  encore — c'est le « lancer proprement » d'après JFC.
- **Antérieurs clos** : `0470`/`0474` deep-relabel (0,25–0,31) · `0473`/`0477` sparring (0,236–0,279) · `0479` élagage-gen OFF (0,261≈ON) · Drawish (`0469`) ☠️ · 0464/0466/0468 supervision tactique ✅ clos.

## 🗺️ PROCHAINES ÉTAPES (roadmap linéaire « poussé à fond » — à exécuter dans l'ordre)
> Jauge unique = conversion combinaisons **0440** vs Scan (IC ±0,05). Seuil de victoire linéaire = **asymptote ≥0,70**.

0. **MAINTENANT** : `0470` probe (ccx33) + `0465` boucle 1 (cpx62). Lecture probe : 0440 **>0,35** + FLIP % élevé = matière.
1. **(5) Bootstrap deep-relabel** — `0471-bootstrap` (armé, tire si 0465 boucle 1 flat) : K=4 passes, lire la **courbe** `{0440_p1..p4}`.
   - **≥0,70** ⇒ 🎉 **linéaire gagne, NNUE jamais nécessaire. FIN.**
   - **cale ~0,52** ⇒ borné par la vue de jass → étape (6).
   - **plate ~0,30** ⇒ FLIP %/depth/volume à creuser avant (6).
2. **(6) Sparring vs Scan baseline** (B — à ÉCRIRE quand (5) cale) : jass vs Scan, labels résultat réel, rééquilibré W/D/L,
   mixé self-play profond → **champion-B** (~Scan, casse le plafond 52 %). **Dépendance-Scan = allumage transitoire.**
3. **(7) Self-play bootstrap DEPUIS champion-B** (à ÉCRIRE après (6)) : pilote shot-safe → self-play punit les shots → point fixe
   remonte **sans Scan** → indépendance ; la classe linéaire grimpe-t-elle vers 0,70 ?
4. **Gate NNUE (C3/C4)** : décisif **seulement si (7) reste <0,70** (avec C1 saturation + C4 vs-Scan ≤0,40, cf gate falsifiable).

## ⏳ EN COURS (historique daté — 2026-06-25) — deux box, deux leviers en parallèle
- **cpx62 → `0465-freshmix-12m`** : **reprise du plan de base** (self-play diversifié, 100 % épuré/boucle, 5 recettes de μ),
  **pilote = champion-egdbmix**, ancre/juge = egdbmix (⇒ `vs_base>0,55` = la recette a cassé le point fixe du **meilleur**
  champion actuel). Le plan de base n'avait **jamais** été joué (`0442` tué en vol pour le détour tactique). **Re-dimensionné
  25M→12M** : TVR ⇒ au-delà de la saturation (~10M) le volume ne **déplace pas** le point fixe, il ne réduit que la variance
  de `vs_base` (bruit dominant = le juge, 28 paires) ⇒ 12M screene en ~1,5 j au lieu de 3-4 ; on refit la gagnante à plein
  volume ensuite. (`0463` à 25M tué.)
- **ccx33 → `0464-master-combo-mining` ✅ FINI = PLAT (vérité externe NE bouge PAS 0440)** : 155k vraies combinaisons
  minées (`data/expert_games.db` ; sac→regain net dans la ligne RÉELLE, gagnant au trait, label = résultat réel),
  sur-pondérées ×8 (~5,4 % du corpus), même base que 0462. Conversion 0440 **apples-to-apples sur 232 ouvertures-attaquant
  communes** : **combo 0,304 vs egdbmix 0,302 = +0,002** (juge tronqué à 76 % par le wall-time, mais la compa sur le
  sous-ensemble jugé est propre). ⇒ **même la vérité-terrain tactique externe ne déplace pas 0440.** 3ᵉ échec données
  d'affilée (0460 0,259 · 0462 0,285 · 0464 0,304) → **signal de plafond FEATURE linéaire le plus fort à ce jour.**
  ⚠️ Caveat restant : combos à seulement ~5,4 % ⇒ **dilution** possible (vs vrai plafond) → levé par `0466`.
- **ccx33 → `0466-combo-weight-doseresponse` ✅ FINI = DOSE-RÉPONSE PLATE (caveat dilution LEVÉ)** : mêmes combos 0464 à
  **poids LOURD ~35 % du corpus** (1 fit, 1 juge vs Scan, DILF complet 305, **pas de troncature**). Conversion 0440 =
  **0,308** (94/305). Dose-réponse **0 %→5,4 %→35 % = 0,302 → 0,304 → 0,308** : **PLATE**. ⇒ **ce n'était PAS la dilution** ;
  même de vraies combinaisons à poids lourd ne déplacent pas 0440. **Le levier données-tactique C2-(2) est ENTIÈREMENT clos**
  (4 formes : relabel, self-shot, vue-externe, vue-externe-lourde). ⚠️ Une seule réserve de VALIDITÉ subsiste (cf note gate).
- **0456 (combine-egdbmix-μ) TUÉ** : zombie ~10,5 h (gen 10M trop lent sur ccx33 16gb) ; verdicts décisifs déjà tombés.

## 🎯 RECADRAGE (JFC, 2026-06-25 soir) — ce n'est PAS un plafond de features, c'est la DISTRIBUTION des labels
> **Objection décisive de JFC** : « ça doit décoller, sinon comment Scan aurait fait ? » — et il a raison. **Correction d'un
> excès de pessimisme des notes précédentes** (« plafond FEATURE solide » = FAUX).
- **Notre classe ⊇ celle de Scan** : 32cf (8,5M) **⊃** 8cf (2,1M) + features rois appariées (king_mob). Donc **les poids qui
  convertissent les combinaisons EXISTENT dans notre classe** — au moins ceux de Scan, représentables exactement. **Scan = preuve
  d'existence.** Si c'était un mur de représentation, **Scan ne convertirait pas non plus** (il convertit à 95 %). ⇒ **PAS un
  plafond de features.**
- **Donc c'est le FIT — précisément la DISTRIBUTION des labels** (Tsitsiklis-Van Roy : le point fixe linéaire-WDL = la distrib
  d'entraînement). **Notre défaut** : self-play par un pilote **shot-aveugle**, joué **superficiellement (d8-d12)** ⇒ dans nos
  parties **les shots ne sont jamais punis** ⇒ le WDL n'enseigne **pas** la sécurité tactique. L'entraînement de Scan avait des
  shots punis. Même classe, distrib différente ⇒ poids différents.
- **Pourquoi 0468/oversampling a échoué autrement que je le disais** : sur-pondérer des **racines** étiquetées par le résultat
  est du **point-par-point** (ça corrompt les poids matériels) ; il faut que la shot-vulnérabilité → défaite sur des **milliers
  de positions naturelles** (un déplacement de **distribution**, pas des points).
- **LEVIER-FIT (sans Scan) = la PROFONDEUR DE JEU.** Re-étiqueter par recherche **profonde d16-d20** (où jass punit déjà ~52 %
  des shots, cf 0451 movetime) ⇒ le WDL enseigne enfin la sécurité tactique ⇒ on monte vers **~0,52 (le plafond de NOTRE
  recherche)**. C'est `--deep-relabel` (réserve dormante, réhabilitée). **Probe `ccx33-0470`** lancé (correctif de 0462 qui
  filtrait à d6 = trop superficiel). **Cap honnête** : ne punit que les shots que jass VOIT (~52 %) ; au-delà → sparring fort
  (Scan, distinct de la distillation) ou **bootstrap** (jeu profond → pilote plus fort → punit plus → itérer = la voie pure).
- **0465 = version trop faible** (d10-d12, pas assez profond pour punir fiablement) : s'il sort plat, **ce n'est pas « le
  linéaire est mort », c'est « la profondeur était trop basse »** → 0470 est le vrai test.

> **DÉCISION GATE — où on en est (2026-06-25, après 0468 + recadrage)** : levier **données-tactique point-par-point** clos (5
> formes : 0460/0462/0464/0466/0468, full-line à volume plein **dégrade** à 0,251). MAIS ce n'est **PAS** un plafond de features
> (Scan le réfute) — **le levier-FIT par la PROFONDEUR DE JEU n'a jamais été poussé** (`0470` probe en cours, scale d18-20 +
> bootstrap à suivre). **Items C2 restants** : profondeur-de-jeu/deep-relabel (`0470`+) · données-μ (`0465`). [`JASS_DRAWISH_SCALING`
> = ☠️ **DEAD END** : 0353 neutre + finale-only ⊥ gap midgame.] **Tant que la profondeur de jeu n'est pas épuisée (probe → scale → bootstrap), AUCUNE ouverture du débat NNUE** —
> c'est le cœur du « linéaire poussé à fond ». C3/C4 ne deviennent décisifs qu'après ça.

## 🧮 DÉCIDEUR FINAL DU LINÉAIRE (ajouts JFC 2026-06-25 soir — A & B) — la COURBE, puis le SPARRING
> Le levier-fit ne se juge **pas** sur un probe unique : deep-relabel ne punit que les **~52 %** de shots que le pilote VOIT
> (cf 0451) ⇒ son plafond intrinsèque sur 0440 ≈ **0,52**. Donc `0470>0,35` une fois ne prouve **rien de structurel**.

- **A — Bootstrap jugé sur la COURBE d'asymptote** (`0471-bootstrap`, armé) : relabel **ITÉRÉ** (pilote plus fort → punit plus
  → relabel → refit), instrumenté **pass-après-pass** : on logue la suite `{0440_p1, 0440_p2, …}` (+ FLIP %) dans `curve.txt`.
  **Lecture** : asymptote **≥0,70** ⇒ le linéaire **gagne** (bootstrap converge au-dessus de C3) → NNUE jamais nécessaire ·
  asymptote **calée ~0,52** ⇒ borné par la **vue de jass**, PAS par la classe → **levier B avant tout NNUE** · plate ~0,30 ⇒
  le relabel ne prend pas (FLIP % faible / depth / volume) → creuser.
- **B — C2-(4) NOUVEAU : SPARRING vs Scan, labels = RÉSULTAT RÉEL** (à monter SI le bootstrap cale ~0,52) : jass joue **contre
  Scan**, parties étiquetées par le **résultat W/D/L** — **aucune éval moteur dans le label**. ⇒ **NI distillation** (≠ éval-Scan
  comme cible, ⛔) **NI auto-supervision** (≠ labels-jass, mort 0460-0468). Un adversaire qui voit **95 %** des shots fabrique la
  distribution-punie que le deep-relabel produit en interne, **sans le plafond des 52 %**. Jamais essayé sous cette forme.
  - ✅ **B = ALLUMAGE, dépendance-Scan TRANSITOIRE (cadrage JFC 2026-06-25)** : B ne sert qu'à **fabriquer une BASELINE** —
    casser le plafond des 52 % en important la distribution-punie d'un agent voyant. **Derrière, on REPART en self-play** avec
    le **champion-B comme pilote** : ce pilote étant shot-safe (~Scan), ses parties self-play **punissent enfin les shots** → le
    point fixe self-play se déplace au niveau shot-safe **sans Scan** → **indépendance retrouvée**, et le bootstrap self-play
    peut continuer à grimper (potentiellement au-delà de Scan, n'étant plus borné par son jeu exact). ⇒ la dépendance-Scan est
    **un démarreur ponctuel, pas un plafond** : c'est l'échappée façon AlphaZero (prof externe une fois → auto-amélioration).
  - Failles à gérer au build : (1) labels **biaisés perte** (jass perd la plupart des milieux vs Scan) → **rééquilibrer** W/D/L
    au fit ; (2) volume borné par la vitesse de Scan → movetime modéré + paralléliser ; (3) punition récoltée **seulement** où
    jass marche dans un shot vs Scan → **mélanger** avec self-play profond pour la couverture positionnelle. (Job écrit au
    moment où A cale, son dimensionnement utilisant FLIP %/asymptote observés.)
- **SÉQUENCE LINÉAIRE COMPLÈTE (le « poussé à fond »)** : (5) deep-relabel bootstrap (A, auto, cap ~0,52) → (6) sparring-Scan
  baseline (B, allumage externe, ~Scan) → **(7) self-play bootstrap DEPUIS le champion-B** (indépendance ; la classe linéaire
  sustain/grimpe-t-elle vers 0,70 une fois débloquée ?). **C3/C4 ne deviennent décisifs qu'APRÈS (7).** Un bootstrap <0,70 à
  l'étape (5) **n'ouvre PAS** le NNUE — il enchaîne sur (6) puis (7).
## 🔬 DOUTE-VOLUME (JFC, 2026-06-25) — pris en compte : 0466/0467 affamaient le pool, refait à volume plein
> Question : a-t-on conclu/fermé des leviers sur des volumes trop faibles (= la famine 0401 qu'on a passé le programme à fuir) ?
> **Cartographie** : architecture (29-36M, dé-confondue) · egdbmix/0461/0462/0464 = **base PLEINE 18M+4M** (saturation,
> appariée). **MAIS `0466`/`0467` ont rétréci le pool à 5M** pour monter les combos à 35 % ⇒ **base sous-saturation, sans
> contrôle apparié** ⇒ leur « plat à poids lourd » **n'est pas concluant**.
- **Ce qui TIENT** : `0464` est déjà un null PROPRE — egdbmix **EST** le champion « 18M+4M sans combos » (contrôle apparié),
  0464 = même base **+ combos 5,4 %** = 0,304 vs 0,302 ⇒ combos n'ajoutent rien **à saturation, contrôle apparié**.
- **Ce qui était FRAGILE** : « les combos LOURDES n'aident pas » (0466/0467) — testé en **affamant** le pool, pas en répliquant.
- **CORRECTION `0468` ✅ FINI (full-line à volume PLEIN, `0467` 5M tué)** : pool **18M** (saturation, apparié egdbmix) +
  671k positions full-line montées à ~35 % **par RÉPLICATION** (pool jamais réduit) + **bootstrap IC95**. Verdict :
  **conversion 0440 = 0,251 [0,205 ; 0,297]** — egdbmix 0,302 est **HORS l'IC95 (au-dessus)** ⇒ full-line à volume propre
  **ne monte pas, il DÉGRADE** (significativement). Sur-pondérer la ligne forçante (nœuds matériel-en-bas étiquetés
  « gagnant ») **corrompt** l'éval linéaire (elle ne peut représenter « en-moins-de-matériel MAIS gagnant » → le signal se
  smear dans les poids matériels). ⇒ **doute-volume LEVÉ : le test lourd, refait proprement, confirme le null — et pire.**
  **Le levier données-tactique est CLOS, sans reproche de volume** (5 formes : relabel, self-shot, racine-léger, racine-lourd,
  full-line-lourd — la seule à volume sous-saturé était 0466, redondante avec 0468/0464).
- **Résolution du juge (chiffrée)** : 0440 = **305 positions** ⇒ IC95 bootstrap **≈ ±0,05** (egdbmix 0,302 ∈ [0,25 ; 0,35]).
  Un vrai levier doit pousser 0440 **> ~0,35** (hors IC) pour compter ; aucune supervision tactique n'en approche.

## 🧭 RÉÉVALUATION MÉTHODO 2026-06-24 (failles critiques — prises en compte)
> Le juge primaire (self-direct) est **AVEUGLE au mode d'échec** : si champ_k et champ_{k-1} partagent la cécité
> combinatoire (même éval), le match ne la voit pas → la boucle peut grimper (positionnel), s'auto-stopper « plateau »,
> et livrer **avec le gap à Scan intact**. Mêmes mots que pour l'élagage : « invisible en self-play, les 2 côtés pareil ».
- **GATE PRIMAIRE AJOUTÉ — conversion combinaisons 0440** (`data/dilf_combinations.fen`, vs Scan, depth-fixe) : mesurée à
  **CHAQUE champion**, loguée ici **au même rang que le self-direct**. Progrès = `25 % → ?`. (Vérité = recherche/EGDB, pas
  « battre Scan » au plancher → non bruité.) Le self-direct seul ne suffit plus.
- **FIT vs FEATURE — ✅ TRANCHÉ (0461, 2026-06-25) = FIT** : men-only vs king-aware jugés **sur le set 0440** ⇒
  **men-only 0,300 · king-aware 0,284** (king-aware n'aide PAS). Le pari FIT/données tient, **géométrie verrouillée**.
  (cf VERDICTS 2026-06-25 en tête.)
- **LEVIER TACTIQUE DIRECT (anti-25 %)** — la doctrine « WDL seul non borné » est **mal appliquée à nos défaites** (lignes
  FORCÉES 2-6 plis, dans l'horizon, résolubles en vérité-terrain → PAS de la distillation). MAIS ⚠️ **la forme
  AUTO-supervisée a ÉCHOUÉ** (0460 relabel-tout 0,259 ; 0462 shot-filter labels-jass 0,285) : **les labels produits par la
  recherche de jass ne couvrent que les shots qu'il voit déjà** — pas ses angles morts (= le trou 0440). ⇒ **le flux tactique
  doit venir d'une VUE EXTERNE** : combinaisons de **vraies parties de maîtres** (sac→regain net dans la ligne réelle,
  label = résultat réel), `0464` en cours. (cf VERDICTS 2026-06-25.)
- **GATE NNUE FALSIFIABLE (FIXÉ 2026-06-24)** — s'ouvre **ssi les 4 conditions tiennent simultanément** :
  - **C1 saturation** : self-direct (gen_k vs gen_{k-1}) ≤ 0,52 × 3 itérations consécutives, corpus ≥ 60M.
  - **C2 leviers épuisés (LISTE CLOSE, aucun ajout)** : (1) ✅ men-only vs king-aware/0440 (`0461` = FIT, fait) ·
    (2) supervision tactique ✅ **CLOSE** — AUTO (0460/0462) ET VÉRITÉ-EXTERNE diluée+lourde (`0464` 0,304 / `0466` 0,308),
    **dose-réponse PLATE 0→35 %** ⇒ pas la dilution ; réserve validité « full-line » à arbitrer · (3) `JASS_DRAWISH_SCALING` ✅ **DEAD END** (0353 neutre + finale-only ⊥ gap midgame) ·
    (4) ✅ géométrie plus riche — **N/A** (0461=FIT) · **(5) PROFONDEUR DE JEU / deep-relabel bootstrap** (`0470`/`0471`,
    jugé sur la COURBE d'asymptote vs 0,70) · **(6) SPARRING vs Scan, labels résultat réel** (C2-(4) du mémo — CONDITIONNEL,
    si (5) cale ~0,52 ; réintroduit la dépendance-Scan, plafonne ~Scan) · (données-μ) `0465` = **mauvais cheval** (d10-d12 trop
    superficiel, ne pas conclure dessus).
    [déjà faits : king_mob, egdb-mix]. Liste finie → on ÉVALUE ; **pas de « encore une idée »**.
    **C2 n'est vidé que quand (5) la courbe-bootstrap ET (6) le sparring ont tourné** (un bootstrap calé <0,70 n'ouvre PAS le
    gate tant que (6) n'a pas été essayé). Alors seulement C3/C4 deviennent décisifs.
  - **C3 conversion 0440 plafonnée ET basse** : meilleure conversion 0440 (a) n'améliore plus de ≥0,05 sur les 2 derniers
    leviers, ET (b) reste **< 0,70**.
  - **C4 vs-Scan confirme** : champion saturé, **éval-pur depth-fixe**, **N≥550 (ou SPRT)**, score **≤ 0,40**.
  - **C1∧C2∧C3∧C4 ⇒ linéaire prouvé < Scan ⇒ GATE OUVERT.** Un seul levier qui pousse 0440 ≥ 0,70 OU vs-Scan ≥ 0,40 ⇒
    on n'est PAS plafonné ⇒ on reste linéaire. (AND des 4 = conservateur, respecte le biais pro-linéaire gravé.)
- **Bruit du juge** : ±0,05 run-to-run, ~550 parties pour Δ=0,05 → pour les petits gains, **monter N ou SPRT**, sinon
  un « plateau » = plateau de **résolution de mesure**, pas de force.

## 📌 VERDICTS 2026-06-24 (état consolidé)
- **FINALE WLD = SATURÉE (0455)** : pousser l'egdb 4M → 12M monte les stats (précision 94,4 → **95,9 %** ; conversion vs
  Scan 0,90 → **0,95**) mais reste **neutre en self-play (0,500)** vs le champion 4M → **le gain finale-WLD est PRIS à ~4M.**
  Aller plus loin en finale = **labels MTC (distance)**, mais **bitbases MTC NON installés** (sonde 0455 absente) → gros
  download pour gain marginal ⇒ **pas prioritaire vs le milieu.** Lead « pousser la finale » ≈ **clos** côté WLD.
- **SEARCH = CLOS** (confirmé) : 0451 a montré que le fix d'élagage `no_reduce_forcing` **n'apporte rien à temps réel**
  (à movetime jass atteint d14-16 et trouve déjà les combos que le dé-élagage récupérait à d11). Param gardé **OFF**.
  ⚠️ Méthodo : 0451 comparait vs Scan **à movetime ÉGAL** = fautif (confond éval/vitesse) ; verdict tient pour d'autres
  raisons, mais **vs-Scan = depth-fixe (éval pure) ou movetime NPS-compensé, JAMAIS temps fixe égal.**
- **king_mob = DÉJÀ TIRÉ, pas dormant** : `JASS_KING_MOBILITY=ON` dans tous nos builds, **LIVE dans le champion** (poids
  lus : `BK_DENIED` = 287 en finale ≈ 57 % d'un homme ; validé **+33 Elo** en 0311). Le confinement de Scan est **codé,
  fitté et actif** — ce n'est pas un lead à tester, c'est acquis. (Correction du briefing §4.)
- **FEATURES = MATCHÉES À SCAN** : géométrie patterns identique (men-only ternaire, dead lever 0203-0236) + features
  king/confinement présentes et fittées ⇒ **pas de feature riche manquante.** Le mur restant = **FIT des poids de
  patterns au MILIEU** (combinaisons), borné par la distribution self-play → c'est `0442`/`0456` (données/μ).
- **EN COURS (2026-06-25)** : `0465` (plan de base 12M, pilote egdbmix) + `0464` (vérité tactique externe). `0456`/`0442`
  **tués/superseded** (cf VERDICTS 2026-06-25). **Jauge forward = conversion combinaisons dilf vs Scan (0440 ; egdbmix = 0,302).**
- **LEADS DORMANTS** (post-milieu) : ~~`JASS_DRAWISH_SCALING`~~ **☠️ DEAD END** (0353 neutre + finale-only, orthogonal au gap
  midgame — cf branches mortes) ; value-target distillation indépendante (`0443` paused) = **réhabilitée** comme le levier-fit
  profondeur-de-jeu (`0470`/`0471` deep-relabel).

## 🔬 DIAGNOSTIC 2026-06-23 — on perd vs Scan par COMBINAISONS en milieu de partie (pas finale, pas profondeur)
> 📋 Détail → [DIAGNOSTIC_VS_SCAN.md](DIAGNOSTIC_VS_SCAN.md). Match eval-pur no-DB, champion 3e-5 vs Scan (0435).

**Échelle handicap** : jass d11/d13/d15 vs Scan d11 = 0,056 / 0,000 / 0,028 → **la profondeur ne rattrape PAS**.
**Analyse des défaites** : **17/17 par COMBINAISON** (shot : ≥2 matériel en ≤2 plies), en **plein milieu (26 pièces, move ~27, men-only)**, **0/17 dérive lente**. On se fait **cueillir par des coups**, pas user en finale.

**VERDICT A/B (0436)** : élagage OFF = 0,028 ≈ ON = 0,056 → **ce n'est PAS la recherche, c'est l'EVAL.** MAIS (logique clé) **Scan a 2,1M poids, nous 8,5M, et il nous bat** ⇒ **PAS un plafond de capacité** : notre best-linear-fit possible est ≥ le sien, **notre FIT est juste moins bon** (self-play borné par notre pilote faible → point fixe trop bas). **Prochain levier LINÉAIRE = distiller depuis Scan au scale** (le prof est dispo) pour atteindre son point fixe. ⛔ **NNUE INTERDIT** (cf règle gravée en tête).

## 🔴 RÉVISION 2026-06-23 — « scaler vers les milliards » est INFIRMÉ par la littérature (rapport documenté)
> 📚 Détail + sources → [PROGRESSION_LITTERATURE.md](PROGRESSION_LITTERATURE.md) (6 angles, vérifié).

**Le mythe tombe** : Scan **n'a PAS** utilisé des milliards de data. Son eval = **~2,1M poids** (code source lu, *plus
petit* que notre 32cf 8,5M ≈ notre 8cf) ; volume d'entraînement **non documenté** ; la famille Kingsrow = **~1M parties /
145-231M positions** = **NOTRE ordre de grandeur**. Donc on n'est **pas** « 3 ordres sous Scan ».

**Théorie (vérifiée, scikit-learn + TD linéaire)** : un modèle **linéaire à features fixes** converge vers un **point
fixe UNIQUE** en **peu d'itérations** ; le **plafond = les features**, et **le volume ne fait que de la PRÉCISION**
(variance des poids), pas le biais de classe. ⇒ **un plateau rapide / petits gains près du plafond = NORMAL**, et
**scaler au-delà de ~50-100M n'est PAS un levier de force** (couverture déjà saturée, cf BOUCLE §10).

**Les deux SEULS leviers pour dépasser** (révise le principe directeur ci-dessous) :
1. **géométrie linéaire PLUS RICHE que Scan** (32cf 8,5M ⊃ 8cf 2,1M), bien fittée → relève notre point fixe au-dessus du sien ;
2. **NNUE** (non-linéaire) = lève-plafond documenté → **⛔ INTERDIT tant que le linéaire n'est pas épuisé** (règle gravée en tête).

## ✅ VERDICT 2026-06-21 (quater) — rois TRANCHÉS : men-only gagne, king-aware perd (GATE 2b / 0409)
> Sur **36,2M**, 32cf color-fold, fit `train_stream --king-patterns` (extension livrée + validée), juge cross N=252.

**king-aware vs men-only = 0,306** (−6σ) → les rois dans l'occupancy des patterns **DILUENT**. Le verdict 0240/0360 **TIENT au scale** (PAS confondu par le fit-volume) — re-testé exprès à 36M, men-only confirmé meilleur. Les rois restent servis par les **extras** (king-PST/mobilité), pas par les patterns.

**→ Archi VALIDÉE au scale sur 3 axes** : 32cf>8cf (0401) · color-fold>no/full-fold (0408) · men-only>king-aware (0409) ⇒ **32cf color-fold men-only verrouillé, dé-confondu**. Plus de question d'archi ouverte → place à l'**ITÉRATION**.

## ✅ VERDICT 2026-06-21 (ter) — fold TRANCHÉ : color-fold gagne, no-fold/full-fold perdent (GATE 2a / 0408)
> Sur **33,4M**, 32 patterns, 3 fits `train_stream`, juge cross N=252.

| fold vs color-fold | score | lecture |
|---|---|---|
| **no-fold** (17M poids pleins) | **0,417** | perd (−2,6σ) — capacité en + **non justifiée**, encore affamé |
| **full-fold** (translation) | **0,306** | perd — contrôle OK (mauvaise invariance) |

**→ `color-fold` VERROUILLÉ** comme géométrie de prod. Cohérent avec la couverture (verdict bis) : no-fold double les poids → buckets rares à <2 % du jeu → **inutile de le rechercher à 100M**. Le levier n'est ni le fold ni le volume brut → **itération**.

## ✅ VERDICT 2026-06-21 (bis) — la couverture utile est DÉJÀ gagnée → le moteur, c'est l'ITÉRATION (pas + de volume)
> Mesuré sur **8,4M de nos parties** (color-fold, TB=8 503 072) : distribution réelle des visites de buckets.

| seuil visites | % des **buckets** | % du **JEU réel** (activations) |
|---|---|---|
| ≥5 | 62 % | **99,7 %** |
| ≥30 (bien déterminés) | 34 % | **98,1 %** |
| ≥100 | 20 % | **94,8 %** |

**« 47 % de buckets bien déterminés » TROMPE** : les 66 % mal déterminés pèsent **1,9 % du jeu réel** (configs rarissimes). **98 % de ce qui se joue tombe déjà sur des buckets bien déterminés dès ~8M.** Le volume fait 2 choses : **COUVERTURE** (≈ saturée à **10-30M**) + **PRÉCISION** des fréquents (rendements **décroissants**). Donc :
- **NE PAS courir après le volume** (80M/round inutile : on ne couvrirait que la queue à <2 % du jeu). **Socle ~30-60M suffit.**
- **Le moteur de progression = ITÉRER** (pilote améliorant → concentre les visites là où ça compte, y c. nos finales de rois faibles), **pas grossir la fenêtre**. → fenêtre boucle figée **35M** (98 %+ de couverture, +turnover) ; gen **mix d10/d12 5:1 par compte** (≈2:1 en temps car d12 ~2,5× plus lent : d12 = 17 % des positions / ~33 % du compute — minorité réelle, d10 décisivité+volume domine).
- ⚠️ **tempère** l'optimisme « viser 100M » du 0401 : le **60M vs 29M** (GATE progression) montrera un gain **MODESTE** (précision), pas un nouveau 0,69. Le gros gain (2M→30M) est **encaissé**.

**Pruning VÉRIFIÉ** : `--prune-min-visits=1` **lossless** ; ~1,16M buckets actifs à 8,4M (→ ~1,77M à 60M) ; **86 % des 8,5M jamais vus** (configs illégales → 0). **Fit 60M en streaming OK** (bloc prunée ~1,8M, ~2 Go RAM). **L2** (calé ≤2M, 0176) **re-swept au scale** (3e-5/1e-4/3e-4) dans le GATE progression. `train_stream --king-patterns` **livré + validé byte-compat**.

## ✅ VERDICT 2026-06-21 — fit-volume CONFIRMÉ, la géométrie riche s'INVERSE au scale (GATE 0401)
> Matrice 2×2 (volume × archi) sur le corpus **29M** (17 shards), fits `train_stream` (gradient exact), juge cross-arch N=252/case.

| | mesure | score A vs B | signif. |
|---|---|---|---|
| **V32** | 32cf@29M vs 32cf@2M | **0.694** | +6.2σ — le **volume paie** (archi riche) |
| **V8** | 8cf@29M vs 8cf@2M | 0.472 | ns — volume **inutile** (archi pauvre sature à 2M) |
| **A29** | 32cf@29M vs 8cf@29M | **0.583** | +2.6σ — au scale la **riche gagne** |
| **A2** | 32cf@2M vs 8cf@2M | **0.306** | +6.2σ (8cf) — à 2M la riche **perd** |

**L'INVERSION est réelle** : A2=0.31 (riche perd affamée) → A29=0.58 (riche gagne nourrie). **La même archi passe de perdante à gagnante juste en la nourrissant.** ⇒ « géométrie morte / 8=32 / full-fold » = **CONFONDUS confirmés**. **Archi gagnante = 32cf**, figée pour la boucle de prod (`train_stream` sur corpus accumulé, plus de fenêtre 2M). Note : 32cf encore sous-nourrie à 29M (3.4 visites/poids vs ~30-50 idéal) → son avantage **croîtra** avec 100M+.

## 🎯 Hypothèse active (2026-06-20) — on était limité par le FIT, pas par l'archi
> 📘 **Système actif → [BOUCLE_VIRTUEUSE.md](BOUCLE_VIRTUEUSE.md)** (boucle vertueuse profonde + scale du fit).

**LA découverte (JFC) : depuis le début on fittait sur ~2M positions max** (limite full-batch RAM). Donc on jugeait
l'archi linéaire **affamée**. → plusieurs verdicts (« géométrie morte » 0230/0234/0239, « plafond linéaire ») sont
**confondus** par cette famine et **à revisiter**. Scan : milliards de positions ; nous : millions = 3 ordres en dessous.
**Les deux vrais leviers** : (1) **jeu profond** (d≥10 → issues véridiques, pas blunder-driven, 0363/0365) ; (2) **scaler
le FIT** (volume d'entraînement). Plan = boucle vertueuse profonde, self-jugée, **fit qui grossit avec la data**.

### Scale du fit — 3 tiers (le mur historique levé)
| tier | méthode | volume | état |
|---|---|---|---|
| 0 | full-batch `--lowmem` | ~2,4M | le mur (OOM 3,4M) |
| 1 | **`--minibatch --loss logistic`** (RAM, design streamé) | ~10-15M | **dispo, 0 code** (le « L2-only » visait les ancres) — test 0383 |
| 2 | **`tools/train_stream.py`** (disque, gradient EXACT 3e-15) | **15-100M+** | **livré + unit-validé, byte-compatible C++** |

⚠️ **Un plateau de la fenêtre 2M ≠ le vrai plafond** (elle expulse les buckets rares avant leurs 30-50 visites). Avant
de « ressortir Scan » : **test scale-du-fit** (gros fit sur le cumul). Nouveau pacing = la **génération** (~1,4M/h →
30M ≈ ~21h). Acquis : boucles profondes GRIMPENT (0373/0374) ; champion poolé bat d10 ET d12 (0378) ; **d10 > d12** (0.75, volume gagne).

## ⛔ Principe directeur (MAJ 2026-06-20)
**Scaler le fit linéaire AVANT tout pivot.** Scan = même classe (linéaire-patterns) et plus fort ⇒ **pas de plafond de
classe** là où on est ; notre fit était juste **affamé**. Donc : boucle vertueuse profonde + fit qui grossit (minibatch →
`train_stream`, vers 30-100M), self-jugée. **NNUE = INTERDIT** (règle gravée en tête) tant que le LINÉAIRE n'est pas
épuisé — et on a **plus de poids que Scan sans l'égaler**, donc il ne l'est pas. (cf BOUCLE_VIRTUEUSE §1 : A invente des
features, B optimise des poids fixes = nous ; on reste en B jusqu'à preuve d'un vrai plafond linéaire.)

## Defaults actuels (build/recherche) — vérifier via le manifeste d'artefact
| flag | valeur | source |
|---|---|---|
| `JASS_ENDGAME_FEATURES` | **ON** (NUM_EXTRAS=110) | baké 0311 |
| `JASS_KING_MOBILITY` / `JASS_KING_PATTERNS` | OFF / OFF (rois ≠ levier ; **confirmé au scale 36M, 0409**) | 0311 / 0240 / 0360 / 0409 |
| `JASS_SCAN_PARITY` / `JASS_TEMPO_STAGE` | ON (builds boucle) | 0323 |
| search NMP (`eg_no_nmp`) | **OFF partout** (garder) | +97 Elo 0256/0259 (zugzwang) |
| search **multicut**(min6,moves8,cuts2) + **razor**(max4) | **BAKÉ ON** (~+50 Elo, seul gain recherche) | 0336/0338/0343 |
| search probcut / iid / conthist / history-malus / TT>16Mo | OFF (plats, cf SEARCH_TUNING) | 0334-0344 |

## Métrique (pivot 2026-06-19)
**Juge = SOI-MÊME, EN DIRECT** : `benchmark-nnue-vs-nnue` (même archi) ou `tools/jass_vs_jass_arch.py` (cross-archi, shardé
parallèle), bande ~0.5 = sensible. **Scan ne ressort qu'au PLATEAU *après* scale-du-fit** — jamais au plancher (bruité,
run-to-run ±0.05, insensible). SCREEN_ONLY : `endgame_mse`/`val_mse`/Elo_hc (⚠️ ⟂ force, 0311/0312). Auto-stop boucle :
champ_k vs champ_{k-1} ≤ 0,52 (≈1σ@1000) 3 tours + cumulé ≤0,53, par archi (cf BOUCLE_VIRTUEUSE).

## 🔒 Règles permanentes (détail → [SCAN_METHODOLOGY_GAP.md](SCAN_METHODOLOGY_GAP.md))
- **Jeu profond ≥10** : décisif ≠ véridique (d4 = blunder-driven → value-function d'un faible, 0363/0365).
- **Scaler le fit** : la fenêtre 2M plafonne *artificiellement* ; `--minibatch` **supporte la logistique**, puis `train_stream`.
- **Géométrie/fold** : `--full-fold` impose une invariance par TRANSLATION **fausse en dames** → écrase les familles de
  translates → **nos verdicts « géométrie » sont CONFONDUS**. Comparer au repli position-préservant **`--color-fold`**
  (32cf = 8,5M ⊃ Scan 2,1M = 8cf). **TRANCHÉ au scale** : 32cf > 8cf (0401) ET color-fold > no-fold > full-fold (0408) → **color-fold 32cf verrouillé**.
- **Infra (cf BOUCLE §6)** : `gen_patterns --emit` pas reset-proof → build de suite + `JASS_PATTERNS_DIR` hors-tree +
  garde-fou ×32 ; runner **nettoie l'untracked du tree mid-job** → **travailler HORS-tree** ; pjtw full-fold 136 Mo → **gzip** (cap git 95 Mo) ;
  cross-box fragile → boucle **self-contained une box**.

## Branches MORTES / à REVISITER
> 📋 **État des lieux complet des verdicts CONFONDUS par le fit-volume → [BIAIS_FIT_VOLUME.md](BIAIS_FIT_VOLUME.md)** (géométrie, fold, hash, rois, WDL, méta « plafond linéaire »).
| Levier | Statut | reviendrait si… |
|---|---|---|
| **Rallumer NMP** | MORT −97 Elo (zugzwang) | — |
| **TT >16 Mo / movegen captures / probcut-iid-conthist** | MORT (plats, cf SEARCH_TUNING) | — |
| `--phase-weight` | MORT −210 Elo (0261) | — |
| Gradient MTC comme CIBLE | MORT (99,9 % proxy, 0306) | densité MTC massive |
| Covariate-shift PUR (data forte seule) | MORT (0327/0329/0331) | pool mixte |
| Distillation via jass-self-play | MORT (0362/0364 : dégrade) | — |
| WDL/bootstrap depuis data DÉJÀ forte/drawish | MORT (0356/0357 : cible ≈0.5) | départ faible décisif |
| **« Géométrie morte » / « élaguer la capacité »** | ⚠️ **CONFONDU par le fit-volume** (testé à ≤2M) | **À REVISITER** (color-fold + 30M+) |
| **FM/MLP (NNUE)** | ⛔ **INTERDIT** (règle gravée 2026-06-23) | best-linear-fit ATTEINT **et** prouvé < Scan (linéaire épuisé : distill-Scan, itération, géométrie) |
| Drawish ÷8/÷2 (`JASS_DRAWISH_SCALING`) | ☠️ **DEAD END (2026-06-25)** : NEUTRE en jeu (0353) **+** feature de FINALE only (gagnant ≤3p vs roi / matériel quasi-égal) → **orthogonale au gap MIDGAME** (0440) → ne peut le bouger par construction ; la recherche résout déjà ces finales rares. C2-(3) clos. | — (rien ne le ressuscite : le gap n'est pas en finale) |


## Pipeline actif (2026-06-21) — socle 60M → gates → ITÉRATION
> 📘 Mécanique détaillée → [BOUCLE_VIRTUEUSE.md](BOUCLE_VIRTUEUSE.md) §7 (boucle d'itération 60M).

**En cours** : cpx62 termine **0405** (boucle prod 32cf, **retirée** ensuite — accumulation +0,8M/round sous le bruit) ;
ccx33 **gen pure** (0415+). **Queue cpx62 (auto-enchaînée)** : `0408` GATE 2a (fold : color vs **no-fold** vs full) →
`0409` GATE 2b (**rois** king-aware vs men, via `train_stream --king-patterns`) → `0411-0414` **gen pure** (+11,2M).
**ccx33** : `0415-0418` gen pure (+5,6M). Tous **pilote figé `w32_full`**, vers le **doublement ~60M**.

**Prêts, non déployés (lancés au bon moment)** :
- `0410` **GATE progression + sweep L2** (challenger@~60M vs baseline 29M) → au doublement. Mesure le gain de PRÉCISION
  du volume (attendu **modeste**) et **fige le L2 au scale**. Auto-gardé (no-op si <55M).
- `0420` **BOUCLE D'ITÉRATION 60M** (le MOTEUR) : régénère une large fenêtre fraîche **pilotée par le champion courant**
  (mix d10/d12 5:1 par compte) → fenêtre glissante FIFO 35M → refit → juge **champ_k vs champ_{k-1}** → auto-stop. Data box-local (régénérable) ;
  champions committés. Se lance une fois le socle 60M là.

**Object store** : dormant, **non bloquant jusqu'à ~70-80M** (git porte ; `.git`≈1,7 Go). Diagnostic + activation →
[OBJSTORE_SETUP.md](archives/OBJSTORE_SETUP.md). **Acquis** : `train_stream` (+king) livré · pruning lossless vérifié · gen pure
(pilote figé) remplace le théâtre de mesure de 0405.
