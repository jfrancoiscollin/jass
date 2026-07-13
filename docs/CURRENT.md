# CURRENT — source de vérité active (programme « battre Scan »)

> # ⛔⛔ RÈGLE GRAVÉE DANS LE MARBRE (2026-06-23, JFC) — AUCUN NNUE ⛔⛔
> **ZÉRO NNUE, ZÉRO réseau, ZÉRO changement de classe TANT QUE la classe LINÉAIRE n'est pas POUSSÉE À FOND.**
> Justification empirique : on a **8,5M poids vs 2,1M pour Scan** et on ne l'a **même pas égalé** → la classe linéaire
> est **LOIN d'être épuisée** ; notre FIT est juste moins bon que celui de Scan. Leviers linéaires à épuiser AVANT toute
> évocation de NNUE : **distillation depuis Scan au scale** (Scan = prof dispo), itération, géométrie, qualité de data,
> recherche. **NNUE = INTERDIT** jusqu'à preuve d'un vrai plafond linéaire (best-linear-fit atteint ET < Scan). Non négociable.

> **1 page, à jour à CHAQUE verdict.** Le détail vit ailleurs : [BOUCLE_VIRTUEUSE.md](BOUCLE_VIRTUEUSE.md) (système
> actif), [JOURNAL_DE_BORD.md](JOURNAL_DE_BORD.md) §0 (faits/chronologie), [SCAN_METHODOLOGY_GAP.md](SCAN_METHODOLOGY_GAP.md)
> (règles permanentes), [ARBRE_DECISION.md](archives/ARBRE_DECISION.md) (principe). MAJ : **2026-07-11** (verdicts en tête).

## 📦 RELAIS DILF — CORPUS PC BLUES : v4, LE CORPUS ENTIER EST RAFFINÉ (2026-07-12 soir)
> **v5 FINALE (2026-07-12 nuit) — campagne dilf CLOSE, les 5 artefacts livrés** : **A2 = 21 718 combos vérifiées sur 58 volumes** (2 004 dup_of inter-volumes marqués, +787 réparées §4.13 toutes documentées) ; **A3 = 10 219 prefs graduées** (5 712 !/!! + 4 450 ?/?? négatives certifiées) ; **A5 = 960 tests** ; **A4 = 73 QA finales** (`pcblues_endgame_qa.jsonl`, positions à DAMES détectées par hypothèse-re-jeu MINIMISÉE — bois/gris/bleu, correction verrouillée par tests ; expected = claims déclaratifs du livre, `book_claim=true` → **revalidation moteur À FAIRE côté jass avant gate dur**) ; **A1 = 26 parties PDN**. Quarantaines résiduelles ~17 700 séquences diagnostiquées (dont ~rejets corrects : lignes d'analyse sans diagramme d'ancrage ; 2e passes ciblées possibles). **INGESTION FAITE (locale, 2026-07-12 nuit)** : `tools/pcblues_ingest.py` → `data/pcblues_combos.fen` (**16 160 positions**, ×53 vs les 305 de dilf_combinations.fen ; dédup croisée bitboards vs master-2000+0464 : **54 recouvrements seulement**, les livres et lidraughts sont disjoints), `data/pcblues_thermometre.fen` (**pcblues-thermo-v1, 224 positions FIGÉES**, instrument from-scratch), `data/pcblues_prefs_graded.tsv` (10 219 ; 5 665 !/!! + 4 450 ?/?? à inverser in-job). **Job B VALIDÉ (« Go B » JFC) et QUEUÉ : `cpx62-0687-pcblues-prefs-finetune`** (main `925a2642`) — 5 147 parents !/!! (518 captures écartées, 4 554 négatives ?/?? = phase 2 à venir), gen-siblings --leaf-mode d5 sur gen2-mmto, fit ancré {0.05, 0.1}, candidats committés pour A/B ; smoke-test write→read du bloc parents passé en local ; est. ~10-20 min (ancre 0624). LECTURE attendue : hors-IC positif = le prof humain élite ajoute au-delà de gen2-mmto (là où Scan-d14 0672 = PERD) ; plat = signal déjà capté → passer aux négatives. **⭐ THERMOMÈTRE 0688 FINALISÉ (T0, résultat FORT)** : gen2-mmto vs Scan d11 sur les 224 combos PC Blues figées → **conversion du camp-au-trait : jass 0.136 vs Scan 0.904, écart −0.768** (jass score-rate global 0.116, elo −353±38). ⟹ **énorme trou tactique de jass sur des combinaisons humaines RÉELLES que Scan voit** — motivation directe et chiffrée pour l'entraînement sur ce corpus (positions que jass rate mais qui sont des coups gagnants certifiés-joués). Set figé, re-passable sur chaque champion from-scratch (courbe sans contamination).
**BUILD FIX** : `cpx62-0687-pcblues-prefs-finetune` a échoué (rc=6, BUILD FAIL — ne tirait que src/main.cpp de develop, or il dépend des versions develop de scan_eval/search/movegen) → `cpx62-0689` a ABORT (candidats absents). Corrigé et re-queué en **`0690` (finetune) + `0691` (gate)** (patron 0679 : pull des 7 fichiers src develop + garde-fou archi). **✅ `0690` A RÉUSSI (rc=0)** : 5 147 parents !/!!, 45 454 paires, **fit POSITIF — pairwise-acc gen2-mmto 0.6162 → 0.6286 (anchor 0.05, +0.0124)** / 0.6210 (anchor 0.1) ; candidats `pcbprefs_{0.05,0.1}.pjtw.gz` committés. **`0691` FINALISÉ — VERDICT NÉGATIF NET** : pcbprefs_{0.05,0.1} vs gen2-mmto, d9+qs6, openings dilf_combinations → **rate 0.3145±0.055, elo ~−135, PERD hors-IC**. ⟹ **le fit sur les préférences POSITIVES !/!! DÉGRADE le champion** (malgré pairwise-acc en hausse 0.616→0.629 : overfit — ranker les coups humains élite au-dessus des sœurs n'améliore pas le JEU). **Interprétation (recoupée au thermomètre 0688)** : le trou tactique de jass (0.136 vs Scan 0.904) est un problème de **RECHERCHE/tactique, pas de ranking d'éval sur coups quiets** ; fitter l'éval aux préférences humaines positives ne le comble pas et peut nuire. ⟹ **NE PAS enchaîner la phase 2 (négatives ?/??) telle quelle** ; la vraie valeur du corpus PC Blues (21 718 combos) est probablement en **graines tactiques / cibles de recherche** (façon 0464 combo-mining) plutôt qu'en paires de préférence d'éval. À rediscuter avant tout nouveau job. *(Détail cosmétique : commits 0690 libellés « 0687 », tally 0691 affiche les 2 cellules identiques — sed de renumérotation incomplet ; substance du verdict nette.)*
**EXTENSIONS dilf C1-C3 (2026-07-12, main dilf `365dda6`)** : **C2** corpus Dubois FMJD raffiné → `dubois-a2bis-v1` = **789 combinaisons vérifiées** (25 seulement recouvrent pcblues = matière neuve ; `dilf/data/exports/dubois/`, §EXPORTS-bis INTEROP) — s'ajoute au gisement combos/graines. **C1** prédicat de **BLOCAGE STRUCTUREL** livré côté dilf (`pedagogy/features/blocage.py`, `mutual_blocked`/`blocage_structurel` par mobilité, zéro éval, 6 tests, verrou réel validé) : reconnaît les milieux ply-cappés (trou d'oracle n°1 ~19%) → **le harnais de notation reste À FAIRE côté jass** (TB + arbitre-fort d14 + gate DRAW≥99,9% → admis / sinon veto ply-cap ; via `EngineProtocol(movegen jass)` + corpus parties ply-cap). **C3** A4-bis finales Dubois = pilote 4 QA. Vu le verdict 0691, C2 conforte la piste « graines tactiques » (combo-mining) plutôt que prefs-fit.
**C4 — MINAGE EXCEPTIONS TB (chantier enrichissement, ≠ gate-C4 vs-Scan de la méthodo) (2026-07-12 nuit)** : primitive `--gen-egdb-wld` (positions quietes légales egdb-résolvables + label WLD EXACT STM-POV). **`ccx33-0692` calibration FINALISÉE** : rate **27 000 pos/s** (egdb caché → minage jamais goulot), **densité exceptions 23,4 %** (matériel STM-POV en désaccord avec le WDL) — quasi TOUT = *nulle malgré avantage ≥2* (23,36 %) ; *perd malgré avantage* ≈ **0** ; *gagne malgré déficit* 0,05 %. **`ccx33-0693` minage 3M FINALISÉ (go JFC « prepare job 3M »)** : **700 185 exceptions minées** sur 3 000 000 vues (6 shards, ~1,6 min, corpus+RESULTS committés par shard) → `jobs/results/ccx33-0693-tb-exceptions-mine/artefacts/exceptions.jnnw`. Répartition : ~698 367 nulle / 29 perd / 1 789 gagne. ⟹ corpus = à 99,6 % de la **connaissance matériel-défiante des finales** (matériel insuffisant, mauvais coin, opposition, blocage). ⚠️ volume gros et sans doute redondant/dégénéré → **dédup + équilibrage requis AVANT tout fit**, et le **fit éval reste une étape gatée à part** (prudence verdict 0691, pas d'enchaînement auto). C5 (TB étendue) EN PAUSE (décision JFC).
**PLAN BOOST gen2-mmto (mémo JFC 2026-07-13, « A et A ») — jauge commune = thermomètre-224 (baseline gen2-mmto au trait 0.136)** : **B3a CLOS** (0657 asp30/knobs neutre haut-N, cf bloc DOE ci-dessus). **B1 étape-0 FINALISÉ (cpx62-0696, rc=0 — VERDICT NÉGATIF)** : screen d'ensemencement (bras A base standard vs bras B base+25% combos pcblues, même gen `scan_selfplay_gen` + même `wdl_finetune` ancré 0.05). candA/candB gen ~1.6M pos. **Compose candB vs candA : neutre mt0.2 (+4), PERD hors-IC mt0.3 (−20)** ; candB vs gen2 −66 ; thermo-224 candB 0.094 vs baseline 0.136 (−0.042). ⟹ **l'ensemencement (combos vécues en self-play) N'AJOUTE PAS** — candB ≤ candA. **Recoupe 0691** : le corpus PC Blues n'améliore pas l'éval, ni en prefs-fit (0691 −135) ni en graines-vécues (B1) ⟹ sa valeur est ailleurs (oracles/QA, cf E1-E2 dilf), pas dans l'éval. Pas de scale B1 step-2. *(0694 avait BUILD FAIL — sous-pull src develop ; corrigé en 0696 = pull dynamique des src divergents + garde-fou archi + RES hors-arbre.)* **⭐ Étalonnage sain** : baseline défaut-vs-défaut ~0.5 (harnais symétrique OK). **B2 remap-dense → CHANTIER MOTEUR (go JFC 2026-07-13, « Go v1 »)** — CORRECTION de cible : le champion gen2-mmto est `ScanEvalNetwork` (**PJTW v3/v4, `src/scan_eval.cpp`**), PAS `pattern_network.cpp`/JPAT. Table = `w.pat` = `vector<PatPair{mg,eg}>` ≈ **17M entrées × 8 o = 136 Mo** ; gather = `w_.pat[offsets[i]+bucket]` sur 32 patterns, **DÉJÀ software-prefetché** (le code cache la latence DRAM du gather 17M = coût dominant de l'éval). ⟹ le gather naïf que le mémo visait n'existe pas ; un dense-**hash** insèrerait un probe dans le gather → **risque de négater le prefetch et de RÉGRESSER le NPS** (piège identifié). Décision **V1** (diagnostic sûr) : **compaction PUREMENT EN MÉMOIRE au load** (env `JASS_DENSE_REMAP=1`), **zéro changement de format fichier** — `remap[17M]` (uint32, 68 Mo) + `pat` dense dédup-par-valeur (~qq Mo) ; gather = 2 passes prefetchées (remap puis dense) → **prefetch préservé**, **byte-identique** (dense[remap[col]]==pat[col], slot0={0,0}). Livrables develop : la compaction + **`--eval-selfcheck`** (preuve byte-id) + **microbench NPS v1-off vs v1-on** qui TRANCHE : NPS bouge à 74 Mo ⟹ on pousse vers le format 16 Mo embarquable (hash parfait/MPH) ; NPS plat même à 74 Mo ⟹ **B2 mort, on arrête** (pas de MPH pour rien). Aucun bake sans microbench positif ET byte-id prouvé. **⟹ VERDICT B2 (2026-07-13, mesuré `develop` `52a07d5`)** : compaction implémentée (`--eval-selfcheck`), **byte-identique PROUVÉ (0/200k mismatch)**. gen2-mmto = **116 pairs de poids distinctes** (Scan-quantisé) → remap **uint8 palette = 136 Mo→17 Mo (×8)**. **MAIS NPS éval-only = ratio 0.94 (uint32 68 Mo) / 0.987 (uint8 17 Mo) = neutre-à-légèrement-plus-lent** même à ×8 de shrink (L3-résident). ⟹ **le gather n'est PAS le goulot** (prefetch logiciel déjà efficace) ; comme l'éval-only (positions aléatoires = pire cas cache) ne gagne rien, un search réel (buckets corrélés) gagnerait *a fortiori* rien. **B2-pour-NPS = MORT** (gate microbench négatif, pas de bake). **Byproduct gardé** : champion **byte-identique 8× plus petit (17 Mo)** via `JASS_DENSE_REMAP=1` → utile pour l'embarquable/WASM Draught Master (follow-up). Code sur `develop` (défaut OFF, gather inchangé). **B3b** (re-DOE cuts) / **B4** (exceptions-TB équilibrées, corpus C4 dédup+50/50 → wdl_finetune gaté finale) = étapes suivantes gatées.

## (v3, archivé) RELAIS DILF — A1+A2+A3+A5 LIVRÉS (2026-07-12, 24 volumes raffinés)
> La raffinerie dilf (`dilf/scripts/pcblues/`, contrat = section **EXPORTS d'INTEROP.md dilf**) livre dans `dilf/data/exports/pcblues/` (branche `claude/pcblues-corpus-extraction-2i92bj`) : **J1** `corpus_manifest.json` (60 fiches, 10 165 p.). **A2 `pcblues-a2-v1`** = **10 862 combinaisons certifiées-jouées** sur **23 volumes** (BK kombinaties 15/23/56, Klubkompetitie 37/43/51/58, tournois BK 2009-2019 ×13, GMI 17, annoté 12, **deel 2 Kaan = 1 123 combos taggées `mecanisme_kaan`**), 100% `verified=true` par re-jeu FMJD complet depuis ancre diagramme-pixel, +469 récupérées §4.13 (solution unique, RESOLUTIONS), ~5 900 en quarantaine diagnostiquée, `position_hash` = clé de dédup croisée **à faire côté ingestion jass**. **A3 `pcblues-a3-v1`** = **5 778 prefs graduées** : 2 946 positives (!/!!) + **2 780 NÉGATIVES certifiées (?/??)** — signal inédit pour `rank_finetune`. **A5 `pcblues-a5-v1`** = `pcblues_tests.jsonl`, **960 Vaardigheidstesten vérifiés** (deel 47+57) → exercices/QA. **A1 `pcblues-a1-v1`** = 26 parties complètes élite (les tornooiboeken BK sont narratifs — pas de scores complets, leurs fragments partent en A2). **A4 (QA finales) REPORTÉ, motif gravé** (JOURNAL dilf) : dames invisibles à l'extraction pixel + verdicts en prose — pas de FEN silencieusement fausses ; nécessite détection de dames + revalidation moteur. 4 rendus de diagrammes traités (bois / gris-fond-bleu / hachuré-3D / damier bleu sans bordure), tous arbitrés par le re-jeu. Consommation jass : enrichissement combos gen MAINLINE (conversion jnnw côté jass), paires prefs, thermomètre figé. ⛔ **JAMAIS dans le corpus from-scratch** ; ⛔ Result ≠ label WDL. Reste dilf : A4 (dames), 2e passe quarantaine (~5 900, dont deel 2 : 605), volumes divers J9.

## ⚡ VITESSE — 2 VAGUES D'OPTIMS ÉVAL BAKÉES MAIN (2026-07-08→10), TOUTES BYTE-IDENTIQUES
> Programme « convertir la vitesse en profondeur » : optimiser le NPS SANS toucher un seul poids/label (byte-identique → 0 Elo à profondeur fixe, tout écart = pur bénéfice vitesse). **Vague 1** (`scan_eval` : dot-extras creux king-loop + tempo/balance/skew en **popcount masqués** `g_emasks`) = **+13-15% NPS** ; A/B movetime `0662` = **+17 Elo point** (mt0.2 ET mt0.3, rate 0.525) mais **IC englobe 0.5** (n=1320) → neutre-positif, pas hors-IC. `has_any_capture` (prédicat capture bitboard cheap au lieu de gen-complète) baké aussi (movegen+search). **Vague 2 (cette session)** : 4 niches du gather de patterns (le hot-path memory-bound sur 17M buckets) — ① **`pat_mg`/`pat_eg` entrelacés** (`PatPair` : 1 ligne de cache/pattern au lieu de 2) ② **prefetch logiciel** du gather 32 ③ **garde `if(any king)`** sur king-mob/endgame (saute ~16 shifts `man_attacks` sur les nœuds sans dame = la majorité) ④ **drop du `% 531441` prouvablement no-op**. **Baké main** (go JFC). Preuve dure : eval-position **10/10 exact**, arbre search **8/8 identique** (nodes/bestmove/cutoffs). NPS : **+7,3% ouverture / +9,9% milieu / neutre finale-dames / +4,8% agrégat**. *(mini A/B sandbox pour info, IC attendu non-signif.)*
> **🔖 RÉSERVE NPS (2026-07-10, JFC « en réserve »)** : ~15M des 17M buckets sont fantômes (support réel ≈ ~740k). Ils ne coûtent RIEN en calcul (jamais accédés) mais **diluent les ~740k vivants sur 136 Mo** → miss cache/TLB sur le gather 32 (hot-path). Levier = **remap dense collision-free** (`bucket_census.py` le construit déjà : 136→~16 Mo, byte-identique) → gain NPS probable qui s'empile sur entrelacé+prefetch. Coût : **change code éval** (gather via remap) + retrain `.pjtw` dense + **caveat freeze** (nouveaux buckets → slot-0 fallback ; re-census/tour dans la boucle mobile). **NON pris** : le plus rentable sur un champion STABLE (gen2-mmto), pas dans le from-scratch qui bouge la distribution. À dégainer si on fige un champion.

## ❌ FORCING / THREAT EXTENSIONS — RE-TEST `0663` : TOUJOURS NÉGATIF, même moins chères
> Re-test demandé (leur coût/bénéfice a changé : `has_any_capture` cheap + éval +NPS). A/B mt0.2 généraliste, gen2-mmto des 2 côtés : `ext_forcing` **−74**, `qs_forcing_depth=4` **−231**, `combo` **−217** (tous PERD hors-IC) ; `qs_threat_ext` **+9** / `no_reduce` **−17** (neutres). **⟹ les extensions forcing ne composent toujours pas** (elles brûlent le budget nœuds sans gain) — définitivement non-retenues sur ce moteur.

## 🔄 PIVOT MAJEUR (direction JFC 2026-07-09) — ÉVAL FROM-SCRATCH AUTO-APPRENANTE « à la Scan »
> **Décision JFC** : reconstruire une éval **de zéro** avec l'archi actuelle — **zéro prof, zéro distillation, zéro Scan** — en trouvant nous-mêmes notre chemin d'auto-apprentissage depuis la 1re brique self-play (search(eval)>eval = le prof). Motivé par le constat que **gen2-mmto = POINT FIXE linéaire accessible via Scan** (couplage `0645`, piste-1 `0648`, chaîne itérative `0650-56` toutes CLOSE ; headroom<0 depuis gen2-mmto). Recette (mémo `MEMO_AUTO_SCRATCH`) : eval(0)=`zero.pjtw` (corps tout-à-0, matériel-aveugle) → self-play jass avec **qs PLEINE dès le tour-0** (co-adaptation), **adjud-material** (⭐ rend l'issue corrélée au matériel malgré l'éval aveugle), eps décroissant + drop-post-eps, quiet-only ; **fit WDL 100% streamé** (`train_stream --chunk`) ; **gate PUR champion-vs-champion** (eval(1) vs zero, zéro Scan).
> **✅✅ ÇA MARCHE — L'AUTO-APPRENTISSAGE FROM-SCRATCH COMPOSE (2026-07-11).** Le prof = **UNIQUEMENT la recherche** (αβ d10+qs > éval statique ; adjud-material = roues stabilisatrices qui s'estompent, pas un prof). Preuves :
> • **TOUR-0 (`0669` durci)** : eval(1) vs eval(0)=zero **1056-0-0** (rate 1.000, décolle massivement) → le matériel + 1re structure appris PAR NOUS, zéro prof/Scan. *(0664/0665 tués avant : bugs sizing + hang — voir infra.)*
> • **CHAIN AUTONOME `0674`** (UN job qui itère les tours overnight, cap 6, E3 stop-2-plateaux) : **T2 = COMPOSE +170 Elo** vs champion(t−1) (rate 0.727 hors-IC, d9), promu. Puis **T3 REGRESS, T4 REGRESS** → 2 non-composes → STOP à d10. `champion-current` = **T2** (meilleur d10). **Chaque tour = génération 100% NEUVE on-policy (256k, champion(t−1) self-play) + fit ANCRÉ (`wdl_finetune --anchor 0.05`, jamais refit-zéro) + gate compose.**
> • ⟹ **L'éval grimpe zero → T2 (+170) sans AUCUN prof externe** (analogue αβ AlphaZero : αβ_d10(éval)>éval, on entraîne l'éval sur les parties αβ_d10). Piste from-scratch **VIVANTE** (là où re-enseigner gen2-mmto = CLOSE, reconfirmé : **boost Scan-d14 `0672` = PERD −22 vs gen2-mmto** → même le prof le plus fort n'ajoute pas → **gen2-mmto = POINT FIXE définitif**).
> • **🔬 DIAG T3/T4 REGRESS = fade adjud, PAS d10 épuisé** (mécanisme : l'élève jeune connaît le matériel mais pas la CONVERSION → adjud OFF, les gains matériels finissent nulles → labels « matériel ne gagne pas » → désapprend T2 ; indice manifest : nulles 26→39%). Tour-diag `0675` (d10 adjud TENU 4/24 depuis T2) en cours pour confirmer. ⟹ **3 mémos stratégie gravés `develop`** : **TEACHER_LADDER** (quand un barreau sature, MONTER le prof d10→d12→d14→**budget-nœuds ×2/×4/×8** déterministe, PAS movetime ; 1 non-compose=montée, clôture=2 au dernier barreau, volume constant 256k) ; **ADJUD_ESCALIER** (fade en escalier 4/24→5/32→6/48→OFF gaté sur **conv_self≥70-75%** mesurée ; adjud = « TB du pauvre » ; TB-terminate EGDB permanent) ; **SELF_MMTO_FINISHER** (self-MMTO = finisseur TERMINAL de rampe, pas par-tour — oscillation 0648). **1 seul changement/tour** (cran adjud OU barreau prof OU volume).
> **🔧 INFRA DURCIE (bugs from-scratch corrigés + gravés 2026-07-10/11)** : **cap-noeuds `--play-max-nodes`** (fix hang self-play éval-plate : sous éval 0 l'αβ s'effondre + gen-data sans movetime → recherche non bornée ; cap déterministe byte-id quand off, baké develop) ; **fix DEADLOCK monitor+`wait` nu** (le `wait` nu attend le monitor de fond → blocage circulaire ; fix `wait "${pids[@]}"`, gravé check-list) ; **flock anti-double-exec + df + RESULTS/phase + timeout calibré** ; **check-list pré-lancement 12 points** + garde-fou archi gravés CLAUDE.md.
> **⚙️ Règles opérationnelles gravées CLAUDE.md cette session** : (1) **check-list pré-lancement mécanique** (connaître `nproc` réel + micro-calibrer le rate sur la box → ETA chiffrée → valider JFC ; après ma bourde 0665 : sizé sans mesurer nproc=32) ; (2) **reporting en heure française** ; (3) **garde-fou archi** (pull explicite scan_eval/search/movegen + `arch_assert` avant build).
> **⭐ 3 ENGAGEMENTS CHIFFRÉS from-scratch (JFC 2026-07-10, gravés `MEMO_AUTO_SCRATCH`)** — les tueurs de boucle pré-désamorcés : **E1 adjud-material S'ESTOMPE** (T0 2/10 → T1 3/16 → T2 4/24 → T3+ OFF, fade **éval-driven** via conversion-self <60% = tenir le palier ; sinon labels restent biaisés-matériel, le positionnel exige des issues réelles) ; **E2 drop-post-eps = HYPOTHÈSE** (0665 l'embarque malgré la leçon −25 couverture>pureté ; si T2-3 saturent tôt → **1er suspect = re-tester l'A/B couverture** dans ce régime) ; **E3 gate compose-vs-sature PRÉ-ENGAGÉ** : pilote = Elo champion(t) vs (t−1) d9 (IC ±25), **arrêt = 2 tours sans compose hors-IC**, d9-vs-Scan = **thermomètre externe qui ne pilote PAS**, **cap dur ≤6-8 tours**.

## 🏆 BAKE ÉVAL (2026-07-07) — champion `gen2-mmto` : PREMIER GAIN-ÉVAL de la campagne (après +187 search)
> **cand_it3 (boucle externe MMTO, `0632`) BAKÉ comme éval champion** : `jobs/results/BAKE-gen2-mmto/artefacts/champion-gen2-mmto.pjtw.gz`
> (= gen1 + MMTO à-travers-recherche, positions maîtres + prof Scan, boucle externe 3 iters convergée). **Référence future de tous les jobs
> (self-play/A-B/calibrate) = gen2-mmto ; gen1 archivé (bake réversible).** *(L'éval EMBARQUÉE du binaire reste legacy Cycle-8, non touchée
> — les jobs passent `--pattern` explicite ; si un binaire nu doit un jour utiliser gen2-mmto, re-embed = follow-up.)*
> **Preuves (gate `0634`/`0635`, 2 runs indépendants)** : **d9-vs-Scan −310→−276/−295 (+34/+46) = l'éval-PAR-NŒUD a PROGRESSÉ** (la cellule
> éval-pure figée à travers +187 de search a enfin bougé — pas du style/interaction-search) ; **généraliste +52 hors-IC mt0.3** (croissant avec mt),
> **dilf neutre** (garde-fou, pas de régression) ; **survie 0.343→0.334 ↓** (prédiction depth-stability confirmée). mt0.3-vs-Scan = bruit petit-N
> (−14/−25 non-signif., contredit par le +52 jass-vs-jass) ; `0636` (re-mesure haut-N) était redondant → **TUÉ** (kill GitOps). **⟹ +187 search + ce gain-éval COMPOSENT.**
> **✅ RÉFÉRENCE RE-ANCRÉE sur gen2-mmto (`0637`, vs Scan)** : **d9 −310→−276 (+34 fermé, éval-pure)** ; mt0.3 −161→**−155** (+6) ; mt1.0 −133→**−128** (+5) ;
> NPS −134→**−129** (+5). ⟹ **l'éval-par-nœud a nettement progressé (+34 d9)** mais le gap-Scan à MOVETIME ne se ferme que de **+5-6** (le search profond
> dilue déjà l'éval-marge, cf pré-fit 0.686) → **résidu vs Scan encore gros (−128 à −155)**, il faudra plusieurs rondes. **C'est la nouvelle baseline de la campagne.**
> **❌ RONDE MMTO #2 (`0638`→`0641`) : gen3 (conversion Scan + WORKING-SET ON) = −354/−341 Elo vs gen2-mmto** — WS-ON DÉCALIBRE (le +0.042
> pairwise était trompeur, cf leçon rank-loss statique −847). **⟹ WS-OFF obligatoire** (0629 conversion WS-OFF = +50 ; les cas d'accord régularisent).
> `0642` (WS-ON à l'échelle) TUÉ. **`0643` (recette CORRIGÉE : corpus 0638 re-fit WS-OFF ancré gen2, fit streamé) en test** — tranche « WS-OFF sauve /
> conversion mauvais teacher ». **gen2-mmto reste champion.** Plafond volume seed-pool corpus-mix2M (min-pieces 40 → ~57k ; min-pieces 32 débloque).
> **⚙️ OUTILLAGE bâti cette session** : `rank_finetune --chunk` = **fit streamé EXACT** (byte-identique full-batch, plus d'OOM, jusqu'aux millions) ;
> **kill GitOps** (`jobs/state/kill-in-flight-<host>`) ; harnais A/B durci (arch filtre ouvertures vides + `play_game` catch timeout→nulle) ; pipeline
> **chunké + fits par paliers** (courbe de volume). ⚠️ **bug engine** : `go movetime` overshoot 2-3.5× en endgame-dames (contourné harnais ; vrai fix search = à faire).
> **`0643` (WS-OFF) = NEUTRE** vs gen2-mmto (généraliste mt0.2 −16 / mt0.3 −6 / dilf +3, pré-fit 0.699, delta +0.0021) : WS-OFF EST le fix (−354→neutre) MAIS la conversion-Scan WS-OFF **n'AJOUTE PAS** sur gen2-mmto → **levier MMTO-sur-conversion-Scan PLAFONNÉ**.
> **❌ COUPLAGE WDL↔MMTO `0645`/`0646` (base WDL FRAÎCHE de zéro + MMTO) = −33/−50/−61 Elo vs gen2-mmto** (sweep anchor 0.05/0.01/0, tighter=less-bad). Self-play 2-box **3.04M positions** (mix ~50/50 BAL d8-d10 équilibré + ASYM mt0.3/0.03) + **323k prefs** générés OK (BAL rapide à d10 ; lignes RESULTS perdues = gremlin troncature connu). **Cause** : la base WDL fraîche (Scan-outcome, pairwise **0.647**) est un moins bon *ranker* que gen2-mmto (**0.699**) ; MMTO par-dessus ne rattrape pas. **Refit-de-zéro de la base = MAUVAIS** (perd la valeur accumulée du champion).
> **▶ PISTE 1 en cours** (choix JFC) : `wdl_finetune.py` (nouvel outil, sur develop) = **fine-tune WDL ANCRÉ gen2-mmto** (garder la base accumulée, la calibrer sur le nouveau WDL : min CE + 0.5·anchor·‖w−w0‖², fit streamé dans l'espace-champion comme rank_finetune, seules colonnes vues par les données bougent).
> **✅ Smoke `0647` : outil VALIDÉ** (slice 200k + gen2-mmto) — POV gate **0.9992**, z std **2.03** (σ non saturée, T=1 ok), logloss **descend** (0.630→0.559 a0.1 / 0.570 a1), jass charge ; **|Δw| minuscule (~1e-5)** => la calibration WDL bouge d'un cheveu => **ranking gen2-mmto préservé**.
> **❌ `0648` SCREEN : piste 1 base-nue MORTE** — wdl_finetune ancré gen2-mmto (sweep anchor) puis A/B **base seule** vs gen2-mmto : anchor 0.03/0.1/0.3 = **−76 / −63 / −36** (serré = moins pire, jamais neutre). La calibration WDL, même minuscule (|Δw|~1e-5), **décale gen2-mmto de son optimum ranking**.
> **❌ CHAÎNE ITÉRATIVE LONGUE `0650`-`0656` (mémo JFC, distribution MOBILE) : CLOSE — ÉLÈVE-limité.** Test propre des 2 confounds levés ensemble : pilote=champion(t) qui DRIVE le self-play (nouvel outil `scan_selfplay_gen --player-jass` : champion joue, pas Scan) + éval autorisée à dériver (wdl_finetune ancré champion). Teacher = self-asym par depth. **Trend teacher : d8/d3 −100 → d12/d6 −65 → d14/d8 −55** (Δ +35 puis +10, rendement décroissant → **asymptote ~−48/−50, jamais vers 0**). ⟹ **PAS teacher-limité, ÉLÈVE-limité** : gen2-mmto ayant été MMTO-tuné par **Scan** (teacher >> tout jass-self), le ré-enseigner par le champion lui-même (plus faible) ne peut que le tirer SOUS son optimum. d16/d10 condamné par la tendance (non lancé). **⟹ ni le volume ni l'itération sur distribution mobile ne composent : la piste éval-itération est CLOSE, gen2-mmto = POINT FIXE accessible de la classe linéaire.**
> **🔎 DOE SEARCH `0652` (8 knobs OAT) : tout NEUTRE** — LMR/NMP/ProbCut/LMP/aspiration/RFP seuls vs défaut (baseline sanity +9). Seul lead : **asp30 (aspiration 50→30) = +17** (dans l'IC). **`0657` round-2 FINALISÉ (2026-07-10, rc=0) — VERDICT : tout NEUTRE à haut-N (n=1584)** : asp30hn elo **+3** IC=[0.483,0.525], asp20 −3, combo(asp30+lmr_log+nmp_r3) +2, baseline −12 — **aucun knob hors-IC ⟹ le +17 asp30 de 0652 était du bruit intra-IC ; la marge movetime n'est PAS dans ces knobs OAT**. ⟹ B3a CLOS. Reste search : re-DOE des CUTS sur les défauts ACTUELS (co-adaptation post-bakes, cf mémo BOOST B3b) — **seul levier vivant restant = le search** (convertir le d9 +34/+46 en movetime). **B3b DOE cuts (0697) FINALISÉ — NÉGATIF** : sur gen2-mmto actuel, baseline neutre (sanity ✓), probcut_margin=100 (agressif) **PERD (−19)**, ext_single_reply neutre, triple(asp30+lmr_log+pcm100) neutre (+2) — **aucun cut agressif ne convertit éval→movetime** (recoupe 0657). ⟹ le search est épuisé à ce régime de screen ; la marge movetime n'est pas dans ces knobs. Reste éventuel : re-DOE d'autres axes ou confirm haut-N (mais leads neutres/négatifs).
> **⟹ BASCULE (mémo §3, gate pré-engagé) SI DOE r2 neutre** : éval-linéaire à son point fixe ⇒ cap sur **MMTO-prof-fort** (teacher Scan-mt-long, pas d-fixe faible) + **re-DOE cuts / combos search** + **pivot produit**. **gen2-mmto reste champion.**

## ✅ FRONT ORDERING (2026-07-05) — RENVERSEMENT : `hist_mode=1,hist_pure=1` (prob-pur Scan) BAKE, +20 à +43 Elo movetime
> **Le port history-prob de Scan PAIE** (revirement vs conclusion préliminaire 0599 sous-résolue). Confirm haut-N `cpx62-0600`
> (P1nc = `hist_mode=1,hist_pure=1` = EMA prob SANS killers/CM/conthist, vs legacy) — **4/4 cellules GAGNENT hors-IC** :
> dilf mt0.1 +20, dilf mt0.3 +34, gen mt0.1 +27, gen mt0.3 +43 (n=740-1190). Gate passé (dilf ET généraliste, 2 mt).
>
> **Ce que ça prouve** : la thèse Scan « la qualité de l'ESTIMATEUR gagne, pas la machinerie » — l'EMA probabiliste SEULE
> (sort.cpp) bat notre pile complète killers+countermove+conthist+history-additif de **+20 à +43**. Mécanisme : PAS le
> first-move-cutoff (déjà 0.911, cf 0599) mais le **node-EBF** (−8% à d12) → plus de profondeur/temps → +Elo. **Gratuit**
> (ordering, zéro touche éval/labels). Le gain croît avec le temps (mt0.3>mt0.1) = signature d'un vrai gain qui compose.
> ⚠️ Leçon méthodo : 0599 (n=236) l'avait déclaré « neutre/clos » à tort — le confirm haut-N (n≈1000) a révélé le vrai effet.
>
> **⟹ 3e GAIN SEARCH bakable** (après coin +49, threat_ext +108). Codé sur `develop` (2edfbe84, byte-identical legacy à
> hist_mode=0). **✅ BAKÉ ET PROMU SUR MAIN (`9422fc02`)** : défauts `hist_mode=1, hist_pure=1` + code prob-history sur MAIN (diff propre,
> que mes ajouts, compile rc=0 vs main ; main==develop sur les 2 fichiers). **Un build main brut (défaut runner) utilise
> maintenant l'ordering prob-pur.** (Les autres changements develop — gen-siblings/label-hygiene/rank-loss — restent sur
> develop, non promus, encore expérimentaux.) `cpx62-0601` : E3 (`hist_order_captures=1`) N'AJOUTE RIEN (2/4 hors-IC, P1nc≥Scan-pur sur 3/4) → P1nc sans E3 = spec final. Ordering RÉGLÉ.
>
> *(Note : hist_pure=1 DÉSACTIVE conthist — baké 0508 comme −9% nœuds Elo-neutre — mais l'EMA le remplace mieux, d'où le +30 net.)*

## ✅ PISTE (a) — MMTO À-TRAVERS-RECHERCHE PAIE : +47 Elo généraliste mt0.3 (gratuit, croissant), la qualité du prof Scan translate (+23→+47) ; SCALE en cours (statique close −847)
> **Cible** : le défaut mesuré = éval-marge (0591 rang-position à parité ; 0597/0599 survie-1er-choix 0.34<0.43 Scan, départage
> mal les coups-sœurs). Le fit WDL ne pénalise pas une inversion de sœurs → **objectif mal aligné**. La rank-loss sur fratries
> la vise directement. **Statut : méthode championne du monde au shogi (Bonanza 2006 / MMTO 2013, éval linéaire ~40M params),
> jamais portée aux dames.** NON-circulaire vs 0443 (on apprend des ORDRES relatifs, pas des valeurs).
>
> **DOE prévu C/M/S/MS** : M=préférences MAÎTRES (coup joué = préféré ; oracle EXTERNE, zéro biais-de-nulles ; recycle le
> corpus masters par son canal riche) ; S=préférences RECHERCHE-PROFONDE propre (TB-ancré en finale). **G1 = juge de paix**
> (survie held-out 0.34→0.43, quasi-gratuit ; si plat sur les 2 bras → clause d'échec, pivot produit).
>
> **CODÉ (develop)** : `--gen-siblings` (bras S, `874bf36`) + `--played-moves` master mode (bras M Bonanza, `3713b77`).
> **Corpus S validé** (`0602` : 50k parents → 410k paires, finale ~28%). **REGEN avec bake ordering en vol** (`0604` : oracle
> d9 = prob-pur, plus profond → meilleures paires ; corpus 400k prêt `0607`).
> **✅ PIPELINE + FIT VALIDÉS (`0606→0612`)** : `rank_finetune.py` codé, **POV gate=0.9994** (X·w0==eval C++), grad-check OK,
> loader champion robuste (gen1 = v3 plein-espace PJSW, 17M buckets, king=off, n_ext=120). **Le fit APPREND fort sur les 2 bras** :
> pairwise-acc train **bras S 0.41→0.67**, **bras M (maîtres ≥2000) 0.50→0.62/0.68** — le comparison training de Bonanza marche
> sur notre éval linéaire (point technique dur franchi).
> **❌ MAIS G1 *survie* PLATE SUR LES 2 BRAS** : bras S survie held-out **0.344→0.255** (`0612`, quel que soit l'anchor `0613`) ;
> bras M **≈champion** (`0616` : champ 0.344 ; cand 0.001=0.270, 0.01=0.320, 0.1=0.328, 1.0=0.346 — aucun gain hors bruit).
> L'oracle externe non-circulaire (maîtres) ne sauve PAS la survie → ce n'est pas la semi-circularité du bras S qui bloquait.
> **⚠️ HYPOTHÈSE MÉTRIQUE** : le fit apprend (pairwise↑) sans bouger la survie → **la survie (accord d1↔d11) mesure la
> depth-stability, PAS la qualité de jeu** ; une éval affinée peut mieux jouer tout en étant moins depth-stable. **Le seul vrai
> juge = l'Elo.**
> **🔒 VERDICT ELO — PISTE CLOSE (`0617`+`0619`, cpx62)** : A/B Elo DIRECT candidat bras M vs gen1 (même binaire + search-params
> bakés, seule l'éval diffère, mt0.2). **Le rank-loss statique n'est pas neutre : il DÉTRUIT l'Elo, monotone avec l'ampleur du
> fit** — anchor **0.01 (plus gros mouvement, pairwise 0.62) = −847 Elo (rate 0.008)** ; anchor **0.1 = −278** ; anchor **1.0≈champion
> (contrôle) = −24 neutre** (0617 l'avait donné −7, deux runs indépendants concordent sur le contrôle). Plus la rank-loss bouge les
> poids, pire ça joue. **Le pairwise-acc↑ (0.50→0.62) était de l'OVERFIT** à l'objectif de paires qui décalibre l'éval (les buckets
> ajustés s'éloignent de leur valeur WDL calibrée → éval incohérente). **⟹ l'objectif rank-loss STATIQUE (réordonner les enfants
> immédiats au niveau de la feuille-éval) est FONDAMENTALEMENT MAL ALIGNÉ avec la force de jeu de notre éval linéaire.** La survie
> était bien un proxy trompeur — mais dans le mauvais sens : elle SOUS-estimait le désastre. **Clause d'échec confirmée par la
> VRAIE métrique (Elo). Programme sur +187 Elo search bakés ; résidu −133/−161 acté = prix des marges.** (NB gremlin d'archivage runner :
> cellules dilf + entêtes perdues dans RESULTS des 2 runs — cellules gen complètes et concordantes, verdict robuste.)
>
> ## ✅ MMTO À-TRAVERS-RECHERCHE (Hoki-Kaneko) — la MÉTHODE change tout : PAS destructif, petit gain généraliste RÉPLIQUÉ
> **Codé (`develop`)** : `gen-siblings --leaf-mode` émet la **feuille-PV** de chaque enfant (identité negamax : valeur minimax
> couleur-fixe d'un coup = éval couleur-fixe de sa feuille-PV) → le fit apprend **à travers la recherche**, pas sur l'éval des enfants
> immédiats. **Bug POV attrapé & corrigé** (`--leaf-pov`) : les feuilles-PV tombent à parités mixtes → le signe par-record de
> rank_finetune était faux (pré-fit pairwise-acc contaminé 0.307<0.5) ; fix = stocker le stm PARENT (champ score) et en dériver le signe.
> **DÉCOUVERTE CLÉ (`0621`)** : le champion **à travers la recherche d5** classe DÉJÀ le coup maître au-dessus des sœurs à **0.686**
> (vs 0.503 au niveau feuille statique) → **le search compense déjà l'éval-marge**. C'est pourquoi le statique détruit (−847) et MMTO
> a peu de marge : le fit ne bouge que **+0.0014** (30k maîtres).
> **✅✅ A/B Elo — GAIN RÉEL ET CROISSANT, la QUALITÉ DU PROF se traduit en Elo** (même binaire+params bakés, éval seule change ; dilf=garde-fou indépendant, généraliste=signal représentatif) :
>
> | candidat éval | prof | généraliste mt0.2 | généraliste mt0.3 | dilf |
> |---|---|---|---|---|
> | MMTO 30k (`0626`) | humain 2000 | +23 hors-IC | +23 (plat) | +8/+12 neutre |
> | MMTO 44k (`0628`) | **Scan** | **+38 hors-IC** | **+47 hors-IC** | +5/+6 neutre |
>
> **PREMIER VRAI GAIN-ÉVAL de la campagne** : +47 Elo généraliste mt0.3, **GRATUIT** (éval seule), **CROÎT avec le movetime** (+38→+47 =
> signature d'un gain qui COMPOSE avec la profondeur, comme le bake ordering — le humain était plat = douteux). **dilf neutre = pas de
> régression** (garde-fou passé). **⟹ la qualité du prof (humain→Scan) fait +23→+47.**
> **Escalade data-qualité (idée JFC) — le fit monte monotone ×10** : delta pairwise-acc `0621` humain-30k **+0.0014** → `0624` humain-44k
> +0.0029 → `0625` **prof-Scan**-44k +0.0071 → `0627` **positions+prof Scan** 59k **+0.0136**. Chaque marche de qualité double le fit.
> **✅ BOUCLE EXTERNE MMTO CONFIRMÉE (`0632`, multiplicateur idée JFC)** : re-gen feuilles avec éval candidate + re-fit, 3 iters sur corpus 0625
> (positions maîtres + prof Scan). Post-fit pairwise **0.7014→0.7118→0.7120** (converge it3). A/B cand3 vs gen1 : **généraliste +41/+52 (mt0.2/0.3)**
> vs +38/+47 one-shot → **la boucle ajoute ~+5 Elo gratuit et converge** ; dilf −4/−1 neutre (propre). ⟹ boucle = vrai levier, modeste, à garder.
> **⚠️ `0629` combo A/B** : généraliste +30/+50 (en-famille) MAIS dilf +155/+123 = ARTEFACT (N petits/incohérents 380/760, job time-capé) — le dilf
> propre de 0632 (N=1520) est neutre → re-run 0629 propre requis.
> **❌ `0630` scale mixte** : génération OK **308k parents ÉQUILIBRÉS + 3.5M paires** MAIS (a) régime B déséquilibré=0 (l'équilibré sur-produit ~116
> parents/partie × toutes nulles × 2 côtés → consomme tout le temps) ; (b) **fit OOM** sur ccx33 (matrice features ~13GB). Corpus committé/récupérable.
> **EN COURS** : `0633` (cpx62) re-fit du 308k équilibré sous-éch. 120k+maxpp8 (~1M paires, mémoire-safe) — **teste enfin le payoff du VOLUME** (bat-il +52 ?) ;
> `0631` (ccx33) gen complémentaire (va OOM au fit pareil, parents récupérables pour couplage).
> **LECTURE** : MMTO à-travers-recherche = **PREMIER levier éval qui paie** (statique détruisait −847). Gain gratuit +52 généraliste mt0.3, croissant,
> dilf neutre, **boucle externe confirmée (+5)**. Reste : payoff volume (0633), ré-fit mémoire-safe, corriger l'équilibre A/B du mix.
> **Chemin bake** : meilleur candidat sur set LARGE {dilf garde-fou + généraliste + openings-Scan} **+ d9-vs-Scan** (cellule éval-pure figée −310 ; si elle
> BOUGE = preuve que l'éval-par-nœud a progressé, pas le style) **+ survie en diagnostic** (devrait BAISSER si hypothèse depth-stability juste). Sans régression → **BAKE éval**.
> **Méthodo** : dilf = garde-fou (anti-régression/anti-circularité), généraliste pilote ; **fit mémoire-safe** (cap paires/subsample, cpx62 pour gros corpus).
> NB gremlin runner : RESULTS multi-cellules tronqué → cellules lues d'`output.log`.
>
> ## 📋 NEXT STEPS À FAIRE — ne pas oublier (roadmap post-bake MMTO)
> **⭐⭐ PLAN DEMAIN (JFC 2026-07-08) — SI 0648 FLAT/NÉG, 2 pistes // : (cpx62) CHAÎNE ITÉRATIVE LONGUE façon-Scan (anchor GLISSANT au champion(t) + pilote qualitativement meilleur chaque tour = distribution mobile, la condition jamais testée ; gate compose-vs-sature 5 tours) — spec complète : [`docs/MEMO_CHAINE_ITERATIVE_LONGUE.md`](MEMO_CHAINE_ITERATIVE_LONGUE.md) (sur develop) ; (ccx33) DOE SEARCH sur gen2-mmto (convertir gain d9 +34/+46 → force movetime). Déclencheur = verdict 0648.**
> **⭐ PIPELINE GEN MMTO : CHUNKÉ + FITS SÉQUENTIELS PAR PALIERS (idée JFC 2026-07-07)** — au lieu d'un gros bloc gen (8h) puis UN fit (OOM) :
> **(A) courbe de volume** sur un corpus fini (ex. `0640` sur les 218k de 0638) = fits séquentiels sur préfixes cumulatifs {50k,100k,150k,200k},
> chacun ancré champion + candidat + delta → répond « le volume paie-t-il ? » (delta monte ou plateaue) mémoire-safe (maxpp bas, préfixe borné), sans OOM.
> **(B) pipeline chunké producteur-consommateur** pour les FUTURES gens : gen en chunks ~50k (plusieurs `scan_selfplay_gen` courts, chacun committe son chunk)
> + boucle de fit qui consomme chaque chunk dès committé → **premier candidat à ~2h au lieu de 8h**, courbe en direct, jamais d'OOM final, gen/fit se chevauchent
> (ccx33 génère pendant que cpx62 fitte). ⚠️ `scan_selfplay_gen` écrit les parents en FIN de shard (pas de checkpoint) → chunker = plusieurs appels courts, pas un long.
> *(FINDING WS-ON destructeur gen3=−354 : cf bloc BAKE ÉVAL en tête. WS-OFF obligatoire pour toutes les rondes.)*
> **0. Hygiène post-bake** : re-ancrer la matrice vs Scan (d9/mt0.3/mt1.0/NPS) avec le nouveau champion ; re-baseline tous les A/B sur lui.
> **1. Prochaine ronde MMTO** ancrée au NOUVEAU champion (re-itérer le même corpus a déjà convergé → besoin de data FRAÎCHE) : plus de maîtres,
> et/ou **prof Scan sur positions de CONVERSION + filtre working-set ACTIVÉ** (n'entraîner que là où le champion désaccorde). Le search décide la voie :
> si d9 a bougé → marge-éval encore ouverte ; sinon le gain est search-interaction, pas éval-par-nœud.
> **2. ⭐ ALTERNANCE WDL(ou TD-leaf)↔MMTO — recette couplée à retenir (idée JFC)** : WDL et MMTO sont **orthogonaux** — WDL calibre les VALEURS
> absolues (que le search élague : LMR/futility/probcut), MMTO pose le RANG à travers la recherche. Le plateau WDL (gen1) était l'objectif-rang MANQUANT,
> que MMTO fournit. **Un seul gros self-play du champion fort nourrit LES DEUX** : résultats→targets WDL, préférences→paires MMTO.
> **Séquence** : `champion fort → self-play frais → re-fit WDL (recalibre) → re-MMTO PAR-DESSUS (repose le rang) → bake → re-ancre`.
> ⚠️ **MMTO toujours en DERNIÈRE couche** (le WDL re-fitte tout → lave les ~200k buckets MMTO ; MMTO est cheap à ré-appliquer).
>   **Spécifs à caler (demande JFC)** :
>   - **Volume (révisé JFC)** : self-play **~8-10M positions** → WDL sur tout ; MMTO sur le sous-ensemble quiet+contesté **~0.5-1M parents → plusieurs M paires** (cap mémoire STRICT : subsample + maxpp bas, fit sur cpx62 ; le 3.5M a OOM sur ccx33).
>   - **Profondeurs (révisé JFC)** : self-play/teacher = **d8-d9-d10 FIXE (max d10)** — throughput-friendly pour 8-10M, et le prof-d10 reste AU-DESSUS de l'élève-feuille ; **leaf-depth MMTO D=5-6** (quiescence incluse) ; WDL = outcome (ou relabel valeur-deep / TD-leaf).
>   - **Prior (anchor)** : ancrer au **champion COURANT** (WDL frais, pas stale) ; **sweep anchor {0, 0.01, 0.05, 0.1}** — **anchor≈0 pour tirer PLEINEMENT parti de la nouvelle gen sans la biaiser** (intuition JFC), **jouable car le d9-vs-Scan DÉTECTE la décalibration** si anchor trop faible. (λ = poids rank-loss, reste > 0.) MMTO à-travers-recherche tolère un anchor bien plus faible que le statique (qui faisait −847 à anchor 0.01).
> **3. ⭐ AUTONOMIE (endgame, phase 3 briefing)** : swap prof Scan → **jass-mt-long** (le champion lui-même, prof au-dessus de l'élève-d5) → self-play → préférences → MMTO → champion + fort → … Le prof s'améliore AVEC l'élève (contraire du plateau WDL). **Scan = amorce, la boucle autonome = moteur.** Critère d'indépendance : un cycle complet SANS data Scan.
> **4. Co-adaptation search** : une meilleure éval rouvre-t-elle la **quiescence** (0603-style) / l'ordering ? Re-check ciblé après bake.
> **5. Itérer {MMTO meilleure-data → bake → re-ancre} TANT QUE d9-vs-Scan bouge.** Figé → éval linéaire maxée → là seulement la question NNUE (règle gravée).
> **6. Dettes** : gremlin troncature RESULTS ; OOM fit (cap/subsample) ; bug mix (équilibré sur-produit ~116 parents/partie → étouffe le déséquilibré).
> **RÉFÉRENCE RE-ANCRÉE (`0605`)** : vs Scan sur main frais (+187 search) = **d9 −310, mt0.3 −161, mt1.0 −133, NPS-comp −134** (prédictions confirmées, +30 ordering transféré ; gap ~−133/−161, résidu = éval-marge). **Baseline G1 survie = 0.340** (0597).

## 🔎 DOE ORDERING 0599 (préliminaire SOUS-RÉSOLU, n=236 — SUPERSÉDÉ par 0600 ci-dessus qui bake P1nc)
> **Levier testé : porter l'history PROBABILISTE de Scan** (EMA `sort.cpp`, gratuit en nœuds). Diagnostic source-contre-source
> confirmé (E1 additif-non-borné vs EMA, E2 beta-cutoff-seul vs bidirectionnel, E3 captures non triées). **Codé sur `develop`
> (2edfbe84)** : `hist_mode={legacy|prob}` gaté (legacy byte-identical), init 2048, good/bad shift-5, update fin-de-nœud, E3,
> flags `hist_pure`/`hist_order_captures`. Gates passés : `0597` (anchor), `0598` (build : legacy byte-identical ✓, perft ✓).
>
> **❌ VERDICT DOE `cpx62-0599`** — le levier NE PAIE PAS :
> - **(A) first-move-cutoff LITTÉRAL** : baseline **déjà 0.911** (d9) / 0.908 (d12) — **quasi-optimal** (un moteur bien ordonné
>   plafonne ~0.90-0.92). Le prob ne le bouge pas (P1≈0, P2 +0.007). **Notre ordering de cut-node est DÉJÀ excellent.**
> - **(B) node-EBF** : wash (P1nc −8% à d12 mais +13% à d9 ; P2 pire). Pas de gain net gratuit.
> - **(C) Elo movetime** (6 cellules, n=236) : **toutes NEUTRE**. P1/P1nc penchent +15/+30 mais sous-résolus ; P2 ≈0.
>
> **⚡ RECADRAGE MAJEUR** : le briefing prédisait « jass ordonne moins bien que Scan » — le **métrique littéral le RÉFUTE**
> (fmc déjà 0.91). Le gap de 0597 (survie 0.34<0.43) n'était donc **PAS de l'ordering** mais de l'**EVAL-MARGE** : notre coup
> préféré à d1 survit moins souvent à d11 (stabilité de l'éval avec la profondeur ; accord-top1 d11 vs Scan = seulement 0.39).
> C'est le résidu le plus subtil — choisir le coup *exactement* le meilleur aussi fiablement que Scan — **pas adressable par
> l'ordering** (déjà optimal) **ni par le travail éval grossier** (géométrie/labels/parité-ranking déjà faits).
>
> **Reste 1 fil** : P1nc (prob-pur sans E3) penche +30 à mt0.3 mais neutre → **`cpx62-0600`** (en vol) tranche à ~1200 games/
> cellule (dilf + généraliste). Si hors-IC>0.5 des 2 côtés → bake `hist_mode=1,hist_pure=1` (gain gratuit). Sinon → **front
> ordering CLOS**. ⇒ avec eval-parité (0591), labels-épuisés (0590), quiescence-morte (0593), ordering-optimal (0599), les
> leviers search par knob-tuning sont **tapés** ; le résidu −150 vs Scan est de l'**eval-marge** (move-selection fine).

## 🔎 A4-bis ABLATION SEARCH (2026-07-05, `0592`+`0593`) — déficit par-nœud = QUIESCENCE, cure MORTE au movetime (0593) et NE CO-ADAPTE PAS à l'ordering baké (0603 : −144/−215) → front qs CLOS
> **On a localisé le −338 (jass vs Scan à d9).** 8 cellules vs Scan à profondeur fixe, gen1, moteur coin, variantes via
> `--jass-search-params` (merge sur coin). Résultats (rate jass, ±IC95, ~240 g/cellule) :
>
> | cellule | rate | Elo | lecture |
> |---|---|---|---|
> | base d7 / d9 / d11 | 0.114 / 0.127 / 0.195 | −356 / −335 / −246 | re-confirme la courbe 0571 |
> | **qsstrong d9** (`qs_forcing_depth=6,qs_promo_depth=6`) | **0.267** | **−175** | **DOUBLE le rate — quiescence faible !** |
> | **noreduce d9** (LMR/LMP/razor/probcut OFF) | **0.267** | **−175** | on prune/réduit TROP (prof. eff. < nominale) |
> | softlmr d9 | 0.136 | −322 | marginal (dans l'IC) |
> | histlmr d9 (`lmr_hist_div=6000`) | 0.127 | −335 | nul |
> | allon d9 (combiné) | 0.254 | −187 | ≈ qsstrong seul (pas additif) |
>
> **⇒ VERDICT : le déficit par-nœud est dominé par la QUIESCENCE.** Ajouter forcing+promo quiescence (`qs_*_depth=6`)
> **réduit le gap fixed-depth de moitié** (−335 → −175, hors-IC franc). Notre quiescence par défaut est **sous-puissante** →
> feuilles tactiques mal résolues → on saigne ~160 Elo/nœud. `noreduce` double aussi le rate, mais c'est le trade-off
> vitesse/précision (à prof. fixe le pruning ne fait que nuire ; en temps réel il achète de la profondeur) — pas un
> levier gratuit. **La quiescence, elle, améliore la PRÉCISION des feuilles et le forcing/promo qs est ÉTROIT (peu de
> nœuds)** → candidate à un vrai gain net.
>
> **❌ VERDICT MOVETIME (`cpx62-0593`) : la quiescence NE BAKE PAS.** Testée au temps réel (jass-vs-jass A/B vs coin,
> 632 g/cellule), TOUTES les variantes NUISENT hors-IC : f6p6 −125 (mt0.2), −161 (mt0.05), −119 (mt0.5) ; f4p4 −92 ;
> f6-seul −128. **Le +160 fixed-depth était un mirage** : la quiescence coûte trop de nœuds → on perd plus en profondeur
> qu'on ne gagne en précision de feuille (le variant le plus léger f4p4 = le moins mauvais → problème de COÛT confirmé).
> **⇒ Enseignement** : nos feuilles SONT tactiquement faibles (0592 réel), mais les soigner en DÉPENSANT des nœuds LOSE →
> notre équilibre vitesse/précision est **déjà bien réglé**, on ne laisse pas d'Elo facile côté qs/pruning. Le vrai levier
> restant = améliorer la précision par nœud **SANS coûter de profondeur** : **ordering** (ordonner mieux → élaguer plus sûr
> → plus profond, gratuit) ou **eval plus rapide**. C'est la piste search suivante (décompo ordering : first-move-cutoff vs Scan).

## 🎯 A4 EVAL-ORACLE (2026-07-05, `ccx33-0591`) — EVAL À PARITÉ AVEC SCAN ; le retard est le SEARCH, pas l'encodage
> **Re-mesure eval-vs-Scan en RANG (Spearman), join par BITBOARDS.** Corrige le `r=0.04` de 0576 : cause = **désalignement
> d'index** (relabel_with_scan SKIP des positions → join par indice corrompu ; POV OK, Scan sign-correct x1). Après fix
> (Pearson scan-vs-oracle 0.04→0.88), le tableau est net (5964 pos, oracle = self-search d12) :
>
> | phase | ρ jass-oracle | ρ scan-oracle | gap Scan−jass | ρ jass-scan |
> |---|---|---|---|---|
> | GLOBAL | +0.952 | +0.978 | **+0.026** | +0.934 |
> | finale ≤12 | +0.944 | +0.982 | +0.038 | +0.932 |
> | milieu 13-20 | +0.965 | +0.991 | +0.026 | +0.955 |
> | milieu 21-28 | +0.949 | +0.980 | +0.031 | +0.935 |
> | ouverture ≥29 | +0.950 | +0.958 | +0.008 | +0.921 |
>
> Sanity jass vs matériel r=+0.974 (eval bien-formée). **jass-static et Scan-static ORDONNENT les positions quasi à
> l'identique** (ρ jass-scan 0.92-0.955) et suivent l'oracle d12 à 0.94-0.99. **Le gap eval Scan−jass est minuscule
> (+0.026 global), max en finale (+0.038) — la seule phase avec un vrai résidu eval (mais on n'a pas d'outil qui marche pour l'attaquer : cf tb-relabel PHANTOM ci-dessous).**
>
> **⇒ VERDICT : l'hypothèse « CAPACITÉ/encodage » de 0576 est RÉFUTÉE (artefact d'alignement).** Notre eval statique
> 32cf est à ~PARITÉ avec Scan en rang. **Le retard vs Scan n'est PAS l'eval → c'est le SEARCH.** Ça **valide le front
> EBF** (déjà +49 coin + +108 threat_ext). Le résidu eval (+0.026) est petit et concentré en finale, SANS outil qui marche (tb-relabel n'a jamais tiré, cf bloc PHANTOM).
> *(Nuance honnête : mesure au niveau POSITION, pas top-1 move-ordering — un ρ 0.93 peut masquer des écarts au coup de
> décision ; la direction est nette et cohérente avec nos gains search, mais le test définitif serait le top-1.)*
>
> **CONVERGENCE 0590+0591** : la carte des labels (0590 : biais actionnable = finale, déjà traité) ET l'eval-oracle (0591 :
> eval à parité) pointent TOUTES DEUX **hors de l'eval, vers le SEARCH**. Le programme se recentre : **épuiser les leviers
> SEARCH/EBF** (là où on gagne réellement) ; côté eval, ne reste qu'un résidu finale sans outil fonctionnel et un résidu de fit
> marginal. Fin de la chasse géométrie/labels/capacité.

## 🗺️ P2 RE-CUT : CARTE DU BIAIS PAR PHASE (2026-07-05, `ccx33-0590`) — biais actionnable = FINALE ; ouverture = variance
> **Re-cut instrumenté de l'audit P2** (1600 pos, arbitre d14 pur, per-sample CSV committé → re-cut à tout seuil). Sépare
> le désaccord en **C1** (label nul / arbitre décisif = *unconverted*, BIAIS), **C2** (signe inversé, BIAIS), **C3**
> (label décisif / arbitre ~nul = VARIANCE, HORS désaccord). **Hypothèse d'asymétrie du mémo CONFIRMÉE**, robuste T={25,50,100} :
>
> | phase (T=50) | C1 | C2 | C3 var | lecture |
> |---|---|---|---|---|
> | **finale ≤12** | **81** | 9 | 24 | **C1-dominé → BIAIS** (~20% des pos) |
> | milieu 13-20 | 35 | 21 | 67 | mixte, variance montante |
> | milieu 21-28 | 26 | 27 | **148** | variance domine ; biais modeste (C1 6-12% selon seuil) |
> | **ouverture ≥29** | 10 | 14 | **245** | **C3 écrase → VARIANCE, axe label FERMÉ** |
>
> **Méta décisif** : monter T (arbitre franchement décisif) effondre le désaccord total 0.286→0.242→0.132 et gonfle la
> variance C3 272→484→748. ⇒ le gros du « 24% » est de l'arbitre marginal ; le **cœur de biais robuste** (T=100, clairement
> décisif) = 73 pos, **finale-lourd** (C1 finale=29/50). Le désaccord P2 = **C1+C2 = 100% biais par construction** (métrique
> exigeait arbitre-décisif → exclut la variance) ; la variance C3 (484 à T=50, 30% du sample) vit dans un bucket que P2 n'a
> jamais compté. « Le 24% conflate biais et variance » est donc FAUX : le 24% est du biais, la variance est ailleurs.
>
> **⇒ ROUTAGE (mémo §2, gravé)** :
> - **Finale = biais C1** → seule phase avec biais label réel, MAIS l'outil visé (tb-relabel/EGDB) **ne charge pas** (0587/0589 : `tb_relabel=0` ; cf bloc PHANTOM) → biais finale **non traité à ce jour**.
> - **Ouverture + milieu 13-20 = variance** → **axe label FERMÉ**. Leviers = couverture (A2 eps) / volume / itération E3. ⛔ jamais relabel-arbitre (auto-distillation).
> - **Milieu 21-28 = biais MODESTE** (C1 6-12%, sensible au seuil) → seul candidat label résiduel, **faible reward** ; remède = **E3 (meilleur pilote)** ou multi-rollout doux ciblé. ⛔ pas de relabel-arbitre.
>
> **Conclusion stratégique** : le **front label est quasi-épuisé** — le biais actionnable est concentré
> en finale (biais réel mais SANS outil fonctionnel — EGDB ne charge pas) ; le reste est variance saine (à ne pas toucher, leçon −25) ou biais mid-late modeste (E3). ⇒ le plateau
> n'est plus principalement un problème de LABELS → bascule vers **capacité/encodage (A4)** et **itération/échelle (E3)**.
>
> *(Gap : contrôle erreur-arbitre TB N/A — `egdb-relabel` a échoué sur ccx33 (init db). Moins porteur que craint : l'ouverture
> est déjà 91% C3=arbitre-INDÉCIS, pas arbitre-faux. Re-run possible sur cpx62 (EGDB prouvé en 0587) si on veut le chiffre.)*

## ❌ FIX#4 TB-RELABEL-EN-GEN — ABANDONNÉ (0596) ; « +18 » PHANTOM ; EGDB OK via `--egdb-relabel` mais PAS via le gen
> **⛔ ABANDON (2026-07-05, `ccx33-0596`)** : la manche tb-relabel refaite avec le chemin `/app` a ENCORE donné `tb_relabel=0`
> (fail-fast pd8). Cause : le gen utilise `ensure_initialised()` via `JASS_EGDB_PATH` (env) qui **ne charge pas**, alors que
> `--egdb-relabel` via `egdb::init(dir)` (arg) **charge** (0594 : 42 673 résolus). 3 tentatives ratées (0587/0589/0596) pour
> un levier SECONDAIRE (≤6 pièces). **On abandonne le tb-relabel-EN-GEN.** Reframe : si on veut des labels TB-exacts un jour
> (ex. sous-corpus TB-finale du bras S), on passe par `--egdb-relabel` POST-gen (chemin prouvé). Ne plus y revenir en gen.
> **CORRECTION D'UNE ERREUR.** J'avais promu 0587 comme « FIX#4 tb-relabel = +18 Elo, seul levier label qui gagne ».
> **C'était faux.** La re-lecture des logs le prouve : **`tb_relabel=0` sur TOUS les bras de 0587 (y compris B «+TB»)**
> ET sur les 3 phases de 0589. **Le relabel par-sample n'a JAMAIS tiré un seul échantillon.** J'avais inféré le mécanisme
> du différentiel B-vs-C sans vérifier le compteur — erreur.
> - **0587** : B a battu A de +18 hors-IC, MAIS avec `tb_relabel=0` → le +18 n'est PAS du tb-relabel. Reste noise (un match
>   à 2σ ≈ 5% de faux positif, variance de seeds sur fits from-scratch) ou TB-terminate-en-play — non départageable.
> - **0589 (manche prod, 2M, fit prior gen1)** : `tb_relabel=0` partout, champion-tbregen **RÉGRESSE −37 vs gen1** (hors-IC),
>   neutre vs champregen. Le lever ne compose pas — et surtout il n'a jamais agi.
> - **0590** : `--egdb-relabel` a échoué explicitement (init KO). **Trois échecs EGDB indépendants (ccx33 + cpx62 ×2)**.
>
> **🔧 CAUSE RACINE TROUVÉE (2026-07-05) — un CHEMIN faux.** Les fichiers DB (`db2.idx1`, `db5.idx1`… base WLD **6-pièces**)
> sont dans le SOUS-DOSSIER **`/root/egdb_extracted/app`**, pas dans le parent `/root/egdb_extracted`. Mes jobs 0587/0589/0590
> pointaient sur le parent → `egdb_identify()` ne trouve rien → `init` échoue en silence → `available()=false` → `tb_relabel=0`
> et `egdb-relabel echoue`. Les vieux jobs qui marchaient (0286/0287/0295/0319) utilisaient tous `/app`. **`ccx33-0594`**
> (queué) prouve le fix par un A/B de chemin (parent=échec vs `/app`=`egdb-resolved>0`).
>
> **⇒ CONSÉQUENCES** : (1) tb-relabel n'a JAMAIS été testé avec un EGDB fonctionnel — le +18 (0587) reste un **phantom**
> (noise), MAIS le lever lui-même est **non-réfuté** (jamais exécuté). (2) On NE promeut PAS champion-tbregen ; **gen1 reste
> le champion**. (3) Le biais finale (0590 C1) est réel ; une fois `/app` confirmé (0594), on peut re-tester tb-relabel
> **proprement** avec `JASS_EGDB_PATH=/root/egdb_extracted/app`. (4) **⚠️ Couverture 6-pièces** : la base ne couvre que
> les finales ≤6 pièces → tb-relabel n'adresse qu'une **fraction** du biais finale ≤12 de 0590. À doser avant de sur-investir.
>
> **✅ EGDB CONFIRMÉ RÉPARÉ (`ccx33-0594`)** : A/B de chemin décisif — `egdb-relabel` sur le parent = `init failed` (rc=1) ;
> sur **`/root/egdb_extracted/app`** = rc=0, **42 673/300k positions résolues** (16 153 décisives, 26 520 nulles), **9 854
> labels changés (23% des résolues)**, **2 747 stalls** (finales gagnées/perdues étiquetées nulles = le biais finale 0590,
> réel et corrigeable). Base 4,8 Go, db2→db6 (≤6 pièces). **egdb-relabel fonctionne.** ⇒ **TODO** : refaire la manche
> tb-relabel avec `JASS_EGDB_PATH=/root/egdb_extracted/app` — mais c'est un levier LABEL (secondaire vs SEARCH, cf 0591/0592),
> à couverture ≤6 pièces ⇒ gain attendu modeste ; à lancer si on veut fermer le résidu finale, pas prioritaire sur la quiescence.

## ❌ LEVIER LABEL-QUALITY RÉFUTÉ (2026-07-05) — l'hygiène de label DÉGRADE l'eval ; batterie sanity-gen adoptée
> **Branche `develop`** = code (reset sur main HEAD ; git server accepte main+develop ; runner build main ; jobs overlay develop au runtime).
>
> **VERDICT DÉCISIF `cpx62-0582` : les 4 fixes label-hygiène RÉGRESSENT l'eval de −25 Elo** (match from-scratch nouveau vs
> ancien pipeline, IC [0,446 ; 0,482], hors-IC, 2440 games). **La « contamination 85% » était une MAUVAISE INTERPRÉTATION** :
> le label = **issue RÉELLE de la partie jouée (retour Monte-Carlo)**, non-biaisé (le code le disait : « the played-out
> result stays truthful »). L'exploration eps produit V^μ (léger décalage de politique à eps=5%), et surtout de la
> **COUVERTURE off-policy utile**. FIX#1 (retirer eps) a **détruit cette couverture** → distribution rétrécie → −25.
> ⇒ **On n'adopte PAS les fixes ; l'exploration reste.** Le WDL de nos parties n'est PAS le problème. Le « secret de Scan »
> n'est pas la propreté one-shot du label → plus probablement **itération générationnelle + échelle** (E3). (Nuance : FIX#2
> adjudication vise un VRAI biais — les fausses nulles ply-cap 19% — noyé dans le bundle ; isolable si besoin.)
>
> **BRIEFING sanity-gen (JFC) — PRINCIPE ADOPTÉ** : « un gen se vérifie comme un DATASET, pas comme un programme ». Le
> bug ply-cap a vécu car on vérifiait « le code tourne », jamais « la distribution dit la vérité ». Piliers : P1 manifest
> (flags→effets>0), P2 audit arbitre, P3 holdout par partie, C1 gen-témoin figé, D1 calibration. (Note : l'exemple fondateur
> du briefing — les 85% — est justement le contre-exemple, mais les checks restent bons et P3 a trouvé un vrai bug.)
>
> **⚠️ P3 : FUITE dans E1** — `train_stream --holdout-frac` retient la QUEUE ; **E1 v2 (0579) shufflait les positions** →
> positions d'une même partie réparties train+val = **fuite same-game** → log-loss optimiste → **le verdict « courbe plate »
> (famine réfutée) est SUSPECT**. (Comparaison 8cf-vs-32cf tient — même fuite des 2 côtés ; le « volume n'aide pas » non.)
>
> **DEUX JOBS EN VOL** : `ccx33-0583` **P2 audit arbitre** (désaccord label-partie vs deep-arbitre d14 par phase = mesure
> DIRECTE de vérité des labels, le « 23% » chiffré, jamais faite) ; `cpx62-0584` **P3 E1-clean** (holdout PROPRE = val sur
> shard gen SÉPARÉ, sans fuite → la courbe plate famine tient-elle ?). Ces deux tranchent le socle factuel avant de choisir
> la direction (label-quality mort → itération-échelle E3 ? ou autre).

## 🧬 FRONT ANTÉRIEUR : QUALITÉ DES LABELS WDL (2026-07-04) — pas la géométrie, pas le volume, l'ENCODAGE/LABEL
> **Branche `develop`** = branche de code (reset sur main HEAD ; le git server accepte main+develop, le runner build main ;
> les jobs overlay le code develop au runtime). **Distillation EXCLUE** (JFC) · **deep-relabel EXCLU** (auto-distillation, §6).
>
> **Thèse FAMINE (briefing JFC) RÉFUTÉE par E1.** `cpx62-0579` learning-curve 8cf vs 32cf, **val FIXE** (protocole propre) :
> 8cf ≈ 32cf **indistinguables** (écart ~0,0004, 32cf marginalement mieux) ET **courbe log-loss PLATE** avec le volume
> (8cf δ−0,00005 ; 32cf δ−0,00026) → **saturé → PAS de famine** (le volume brut n'aide pas). La prédiction falsifiable
> (8cf meilleur à petit volume) échoue. Outillage : `train_stream --holdout-frac`, `gen_patterns` variant 8cf/v3
> (**8cf ⊂ 32cf confirmé géométriquement** → ⊇ de JFC vrai).
>
> **LA VRAIE CAUSE — mesurée : biais de LABEL, pas volume.** En scopant le gen loop : **84,6% des labels WDL sont
> CONTAMINÉS** par l'exploration mid-game (un coup eps postérieur fait dériver la partie → le sample hérite d'une issue
> fausse), et **19% des parties finissent au ply-cap** (gagnées mais piétinent → fausses nulles). ⇒ la log-loss sature sur
> un signal **pourri** : en rajouter (volume) n'aide pas → E1 plat. **Ce n'est pas plus de labels qu'il faut, c'est des
> labels JUSTES** — le vrai secret de Scan sous « WDL massif itéré » (des labels corrects via jeu fort + itération).
> Pourquoi le WDL marche pour Scan pas nous : nos labels sont **biaisés-faux sur les positions tactiques** (self-play
> convertit 23% des combos → position gagnante étiquetée « pas gagnant », biais systématique que le volume ne moyenne pas).
>
> **4 FIXES LABEL-HYGIÈNE codés+testés+committés sur develop** (autonomes, zéro distillation, défauts off = rétro-compat) :
> • **FIX#1** `--explore-decay-plies` + `--drop-post-eps` → contamination **85% → 3%** (~3% yield perdu).
> • **FIX#2** `--adjud-material`/`--adjud-hold-plies` (adjudication matérielle conservatrice, jamais par score eval) →
>   ply-cap **19-24% → 17%** (~199 parties adjugées). Couplé : retirer eps monte le ply-cap → FIX#2 devient nécessaire.
> • **FIX#3** `--pair-openings` (chaque ouverture 2×, couleur/rôle punisher échangés → biais 1er ordre annulé dans la paire).
> • **FIX#4** `--tb-relabel` (labels EGDB EXACTS par-sample, biais 0 ; no-op sans egdb → dépendance infra à régler).
>
> **TEST DÉCISIF EN VOL** : `cpx62-0581-labelhyg-validate` (mini-validation §7.5) — gen ANCIEN pipeline vs NOUVEAU (fixes),
> fit chacun prior gen1, **match eval-nouveau vs eval-ancien**. Gate : nouveau ≥ ancien ⇒ **les labels propres produisent
> un meilleur eval** ⇒ on intègre les fixes au gen et on va vers un gros gen propre. **C'est LE verdict du levier label-quality.**
>
> **Synthèse du fil** : ni géométrie (⊇ prouvé), ni volume brut (E1 plat) → **encodage via la qualité du label** (biais de
> contamination 85% tué). Le tir volume massif (E2) n'a de sens qu'APRÈS avoir des labels propres (sinon on multiplie le bruit).

## 🏆 DEUX GAINS RECHERCHE BAKÉS (2026-07-04) — coin corner+nmp +49 ET threat_ext-sur-coin +108 ; eval-oracle FAIT (→ 0591, parité)
> **Le coin PAIE — c'était PAS du bruit.** Résolution du sign-flip : 0560 corner +30 (47g) / 0561 corner+nmp +39 (248g,
> capture douteuse) / **0562-clean corner+nmp = +49 Elo, IC [0,5396 ; 0,5991], 872 games, 16/16 shards, crashs=0 →
> GAGNE hors-IC franc.** ⚠️ **Piège évité de justesse** : le « −30 provisoire » que j'avais lu était un **snapshot prog
> périmé de git** (le bug capture, encore) — l'agrégat **job-side live sur 872g donne +49**. Les 3 lectures se réordonnent :
> −28 (173g bruit) / +39 (248g) / **+49 (872g, propre)** = signal réel et robuste.
> **BAKÉ (commit 4bda84da7)** dans `search_params.hpp` : `probcut_min_depth 0→5`, `lmr_first_full_nonpv 4→2`,
> `multicut_min_depth 6→4`, `eg_no_nmp true→false` (NMP finale réactivé, sound via F1). **Premier gain RECHERCHE de la
> campagne.** Mesuré comme delta pur (baseline ère-gen1 threat_ext=0 des 2 côtés). **Build main validé** (0564 : build OK,
> runtime OK ; les 10 test_scan_book FAIL = `mkstemp("/tmp")` refusé par le runner = environnemental, sans rapport).
>
> **2e GAIN — `qs_threat_ext` CONFIRMÉ AU JEU (0565) = +108 Elo sur le coin.** A/B sur le défaut baké (coin des 2 côtés) :
> threat_ext=1 vs =0 → **rate 0,6504, elo +108, IC [0,627 ; 0,674], 1220 games → PAIE hors-IC franc.** **Co-adaptation
> confirmée en beauté** (hypothèse JFC) : threat_ext **coûtait −21** à l'ancien défaut (0554), **paie +108** une fois l'EBF
> réduit par le coin (budget nœuds libéré) = swing ~+130. threat_ext **déjà baké ON** → verdict **valide le défaut**, rien à
> changer (commentaire source doc-maj 0a492bb34). ⚠️ **Alerte infra** : 4/8 shards ont **crashé (OOM ccx33 16gb, 8 process
> jass concurrents)** — le +108 tient sur 1220 games non-biaisés (openings round-robin, ampleur+IC sans ambiguïté), mais
> **réduire la concurrence des jobs ccx33** (8 shards sur 16gb = trop). JFC : pas de re-run, on bake+documente.
>
> **BILAN : moteur nettement renforcé, 2 gains empilés bakés sur main** (coin +49, threat_ext +108). Le PLATEAU disait « la
> marge est dans la recherche » → livrée.
>
> **⚖️ VERDICT BOUCLE VERTUEUSE (0568 fit → 0570 re-juge blindé) : regen NEUTRE, ne recompose PAS.** Fit prior gen1 sur
> corpus-regen-mix2M (2M généré par le pilote coin) + combos, jugé dans le moteur COIN par défaut vs gen1 (2440 games) :
> **regen-vs-gen1 rate 0,5041, elo +3, IC [0,486 ; 0,522] = NEUTRE** ; regen-vs-egdbmix −12 (NEUTRE penche −). ⇒ **même un
> pilote nettement plus fort (meilleurs labels) ne bat PAS gen1.** cand-regen **NON promu**, gen1 reste champion. (Note : le
> verdict 0568 avait été perdu au bug capture — 0568 blindait le champion mais pas le RESULTS — d'où le re-juge 0570.)
> **CONCLUSION FORTE** : profondeur + volume + prior + archi-complète + **meilleurs-labels** tous éliminés ⇒ le plateau
> gen1 est un **plafond de CAPACITÉ** (le jeu de features linéaire ne peut pas représenter plus), pas un problème de
> données/labels/recherche. **La marge eval est dans la CAPACITÉ FEATURES.**
>
> **CONVERSION vs Scan (0567)** : NEW(coin) 0,587 vs OLD(gen1) 0,580 = pas de transfert du gain recherche à cette métrique
> (les 2 saturent les combos à 2s ; le +49/+108 est du gain full-game à 0,3s, pas de la vue tactique brute).
>
> **PIVOT CAPACITÉ → ENCODAGE (2026-07-04)** — recadrage JFC, important.
> **MATRICE vs Scan `cpx62-0571` (gen1, dilf) :** profondeur fixe d7/9/11/13 = **0,113 / 0,125 / 0,192 / 0,229** ;
> movetime 0,1/0,3/1,0 = **0,250 / 0,250 / 0,300** ; NPS-comp j0,6/s0,3 = **0,292**. Lecture : **on est EVAL-limités, PAS
> vitesse-limités** — à profondeur ÉGALE on se fait écraser (0,11–0,23) et le NPS-comp ne décolle pas (donner + de temps
> n'aide quasi rien). La recherche compense partiellement (d7→d13 : 0,11→0,23) mais le trou d'eval est profond.
> (Caveat : dilf = combos tactiques = notre point faible → chiffres absolus pessimistes ; pattern relatif tient.)
>
> **RECADRAGE JFC (décisif) : ce n'est PAS la capacité/géométrie, c'est l'ENCODAGE/FIT.** Notre géométrie 32cf **⊇** celle de
> Scan 8cf, et l'eval de Scan est **linéaire dans cette base** → **les bons poids EXISTENT dans notre espace** (Scan = preuve
> d'existence). Un fit linéaire chez nous *peut* égaler Scan par construction. Donc le mur n'est pas « on ne peut pas
> représenter » mais « **on n'apprend pas les bons poids qui existent** ». La matrice (0,11–0,23 à prof. égale avec un espace
> superset) le confirme : **déficit d'ENCODAGE, pas de capacité.** Causes probables : (a) target WDL self-play trop pauvre
> (regen-NEUTRE = changer le pilote ne suffit pas, c'est le TYPE de cible) ; (b) couverture d'espace (le self-play n'active
> que nos features vues → le reste sous-entraîné/prior-dominé).
> **DISTILLATION DEPUIS SCAN : EXCLUE (JFC).** Nous rendrait dérivés de Scan (⊥ autonomie self-play). Le levier encodage
> doit rester autonome. (La règle gravée la listait ; JFC l'annule.)
>
> **PROCHAIN PROBE : DOE feature-group PROPRE sur cpx62.** But sous le recadrage encodage : **quel groupe de features
> AIDE vs NUIT au fit** (en pruner un net-négatif = meilleur encodage / explique mix2M −18). ⚠️ 3 échecs (0569 mkdir,
> 0572 `--prune`, 0573 réponse-vs-Scan = **effet PLANCHER** : fit-from-scratch réduit perd tout vs Scan → 0,000, aucune
> discrimination). v4 : réponse **vs gen1** (binaires séparés par config → pas de mismatch cross-arch, pas de plancher),
> capture blindée (VERDICT écrit en fin uniquement). eval-oracle d6 aussi à refaire.
>
> **EVAL-ORACLE `ccx33-0563` = INVALIDE tel quel** (à refaire). jass static vs Scan static d1 sur 3969 pos : Pearson
> **0,035**, Spearman 0,030 (≈0). MAIS ancre **scan-vs-label-selfplay = 0,047 (≈0)** = impossible pour un moteur fort →
> **Scan à d1 n'a pas émis de vraie eval** (pas d'`info score=` à profondeur si faible → 0/défaut). Côté jass sain
> (**jass-vs-label = 0,534**). ⇒ contaminé côté Scan. **À RELANCER en Scan d~6** (eval-dominant mais scores réels).
> La fourche capacité/labels reste **non tranchée**.
>
> **Infra durcie ce matin.** (1) Ma ref locale `origin/main` était 22 commits en retard (fetch ne faisait pas avancer le
> tracking) → forcé `+refs/heads/main:...`. (2) Bug capture runner (RESULTS fragmenté / prog périmés) → tous les jobs
> passent au **VERDICT atomique committé JOB-SIDE une fois** (0562/0563). (3) **Git server n'accepte QUE `main`** en push
> (refs non-main rejetées) — établi par test.
>
> **Cleanup dépôt.** La **branche désignée `claude/pattern-i-nnue-skeleton-tGSrb`** = fork vestigial (13→24/06, 338 vieux
> commits jamais mergés, 8556 derrière main, HEAD de **PR #317** « record roulant » périmé). **PR #317 FERMÉE** (record
> repris par `docs/CURRENT.md` sur main). Suppression de branche **bloquée par un ruleset** (« restrict deletions ») → la
> branche reste inerte, sans conséquence (le runner ne lit que main). Reset impossible d'ici (git server main-only).

## ⚖️ VERDICT EBF movetime `cpx62-0560` (2026-07-04) — AUCUN levier ne paie au temps réel ; coin en re-confirmation
> Confirmation Elo temps-fixe des leviers EBF vs baseline **ère-gen1** (threat_ext=0), movetime 0,3s, dilf, eval gen1.
> **RESULTS/RANKING rendus VIDES par le bug runner** (ne re-committe pas les fichiers modifiés) → verdict **reconstruit
> depuis les `prog_*.N`** (une ligne RESULT/shard). Résultat :
> • **probcut** 0,476 (elo −16, IC [0,425 ; 0,528]) — **parité**, penche −.
> • **nmp** (eg_no_nmp=0, sound via F1) 0,450 (elo −35, IC [0,383 ; 0,517]) — **parité**, penche −.
> • **corner** (probcut+lmr_asym+multicut) 0,543 (elo **+30**, IC [0,411 ; 0,674]) — **parité mais SOUS-DIMENSIONNÉ
>   (47 games seulement)**.
> • **corner+nmp** 0,460 (elo −28, IC [0,391 ; 0,528]) — **parité**, penche −.
> ⇒ **Aucun bras >0,5 hors-IC : les économies de nœuds du DOE 0559 ne se convertissent PAS en Elo au movetime sur gen1.**
> La profondeur gagnée ne vaut pas la détection perdue à cette config. **Seul le coin (+30) intrigue** mais sur 47 games
> (IC énorme) = non concluant. Déséquilibre de games (probcut 318 vs corner 47) suspect → shards qui plantent ?
>
> **RE-CONFIRMATION `cpx62-0561-corner-confirm`** (lancée) : 2 bras (corner, corner+nmp), **PAIRS=2 → ~600 games/bras**
> (IC resserré ~±0,04), **capture stderr+rc+compte de crashs par shard** (diagnostique les 47 games du coin — soupçon
> `multicut_min_depth=4` qui crash), **RESULTS/RANKING committés JOB-SIDE**. Critère : corner borne basse IC>0,50
> ⇒ **premier levier search qui paie au jeu** → baker → re-test threat_ext dessus. Sinon ⇒ **on referme la phase EBF**.

## 🎯 PLAN ÉVAL (2026-07-04) — la fourche capacité/labels ; diagnostic eval-vs-Scan FAIT (→ 0591 : parité, gap=search)
> Rappel : **gen1 = optimum de fit saturé** (profondeur, volume, prior, archi complète tous éliminés ; **mix2M RÉGRESSE
> −18** = ajouter de la donnée sur l'archi complète a EMPIRÉ l'eval). ⇒ **ne pas refitter à l'aveugle.** La question eval
> est une fourche : **capacité** (le jeu de features plafonne, changer l'archi) **vs labels** (cibles self-play = notre
> propre eval à prof. limitée → circularité).
> **STEP recommandé = diagnostic, pas un fit** : comparer **static-eval jass vs static-eval Scan** (0 nœud, eval-seul)
> sur un jeu de positions partagé ; régresser `eval_jass` contre `eval_scan`, sortir le **résidu par phase/région/feature**.
> Orthogonal à la recherche, cheap, tourne sur **ccx33 (idle) en parallèle du coin**. Routage :
> • écart faible ⇒ notre retard est *search* → **valide le pivot EBF**, on arrête de creuser l'eval.
> • écart concentré (endgame/une phase) ⇒ **labels** → re-label EGDB-exact (WLD) + refit ciblé (plus haut plafond).
> • écart diffus + mix2M régresse ⇒ **overfit/capacité** → **DOE feature-group** (endgame×king_mob×tempo×scan_parity, 2^4,
>   holdout) → quel morceau d'archi paie / est net-négatif (explique la régression mix2M).
> Pré-requis : static-eval Scan scriptable en batch (sources dispo, `add_sacs` porté bit-for-bit → hub `level depth/go think`). **LANCÉ = `ccx33-0563` (voir bloc de tête).**

## 🧱 PLATEAU DÉCLARÉ à gen1 (2026-07-04) — pivot RECHERCHE (EBF) ; chaîne éval close sur la recette actuelle
> **Décision mécanique par les gates §1.2** (2 non-COMPOSE après diagnostics complets) :
> • gen2 (3M pd6) −5 **NEUTRE** ; cand-feed (2,9M profond) −8 ; **mix2M (3,5M, ARCHI COMPLÈTE, juge ère-gen1) −18
>   RÉGRESSE** (borne haute 0,492 < 0,50). **Tous les artefacts éliminés** : profondeur, volume, prior, archi complète.
> ⇒ **gen1 = optimum robuste de la recette actuelle.** La chaîne éval ne compose plus → **la marge est dans la RECHERCHE.**
> Prochaine relance éval seulement APRÈS un gain de recherche (alternance des gates) OU un changement de recette.
>
> **Phase EBF ouverte** (`ccx33-0559`, DOE node-EBF Res V, eval gen1) :
> • **probcut** = économiseur SÛR (−6,4% nœuds, t=−15,8, détection neutre) → candidat bake.
> • **NMP-on REJETÉ par la guarde-détection FIXE** (fait chuter la détection combos à prof. fixe malgré F1 sound) —
>   MAIS la guarde est *à profondeur fixe*, conservatrice pour un levier qui échange détection-par-prof contre PROFONDEUR
>   à temps fixe → **à re-juger au MOVETIME**.
> • **Confirmation Elo movetime `cpx62-0560` = FINIE (voir bloc verdict en tête)** : aucun bras >0,5 hors-IC. probcut −16,
>   nmp −35, corner+nmp −28 (tous parité, penchent −) ; **corner +30 mais 47 games** → re-confirmé par `cpx62-0561`.
>   Puis, *si* le coin paie, re-test threat_ext dessus (co-adaptation : sa valeur jeu dépend du budget nœuds libéré par l'EBF).

## 🌙 NUIT 03→04/07 — artefacts du plateau ÉLIMINÉS un à un ; F2 BAKÉ ; gen 2M mixte en cours
> **Diagnostics du NEUTRE gen2 (tous à volume/juge standard)** :
> • **Profondeur** ❌ : cand-feed (2,9M profond pd8/pd10) = **−8** vs gen1 ≈ gen2 (pd6, −5). Deep ≈ shallow.
> • **Témoin pd10 600k** = −57 (volume-starved, non concluant seul — le feedpool-fit le remplace).
> • **Prior** ❌ : sweep λ (0555) — λ=0.10 → **−5**, λ=0.25 → −8, λ=0.40 → −7. **Insensible au prior** : pas de sur-ancrage.
> • **Archi** : **F2 `qs_threat_ext` BAKÉ ON** (décision JFC — complète la quiescence de Scan : qs_sacs + threat-ext
>   ENSEMBLE, comme Scan en prod). L'A/B 0554 (détection + node-EBF + Elo) sert de **vérification a posteriori**.
>   **F1 déjà baké** (NMP `!tactical`). F5 (dédup micro-perf) en attente — pas d'édit de code de nuit sans validation.
> ⇒ Si l'A/B 0554 ne montre rien de net non plus : le plateau de la recette actuelle à gen1 est **robuste**
>   (profondeur+volume+prior+archi) → la marge est dans la RECHERCHE (phase EBF), pas dans une gen de plus.
>
> **GEN NUIT `cpx62-0556`** (JFC) : **2M mix 60% pd8 / 20% pd9 / 20% pd10**, pilote gen1, **archi COMPLÈTE**
> (qs_sacs + threat_ext + F1). Gen-only → **fit au matin** sur cette base. Infra durcie : progress numérotés par phase,
> **phases et corpus committés JOB-SIDE** (un kill ne perd que la phase en cours).
>
> **MàJ 02h15 CEST** :
> • **F5 BAKÉ** (`b60920cf`) : dédup `opponent_can_capture` memoïsée (chemin chaud depuis threat_ext ON). Validé
>   **NODE-IDENTICAL 32 runs** (8 pos × 4 configs) + jass_tests 100%. **Audit F1-F5 : CLOS** (F4 = diagnostic moot,
>   corpus pd6 jamais committés + profondeur déjà innocentée). **L'architecture recherche est COMPLÈTE.**
> • **Verdict A/B 0554 (a posteriori du bake F2)** : détection +0,012 ; nœuds **×1,19** ; **Elo temps fixe −21**
>   (0,4705 ±0,036, n.s., 610 parties). **Au gate strict : ÉCHOUE pour le JEU** (profil ext_forcing : gain fixe mangé
>   par le coût à temps égal). **Pour la GEN à prof. fixe : inoffensif/labels plus précis** → la nuit n'est pas
>   compromise. **DÉCISION MATIN (JFC)** : retirer `qs_threat_ext` du défaut *jeu* (reco) ou garder ; option = ON en gen only.
> • **Gen 0556** : pd8 1,2M **FINI+committé** (~250/s) ; pd9 en cours (~113/s) ; moniteur numéroté **fonctionne**.
>   Corpus complet attendu ~05h30-06h30 CEST.
> • **`ccx33-0557` queué** : supplément **300k pd10** (même recette, job-side) → épaissit la tranche profonde du pool
>   au matin, optionnel.

## ⚖️ VERDICT gen2 = NEUTRE (2026-07-03) — diagnostic pd10 en cours ; pd6 = suspect n°1
> **gen2** (`cpx62-0550`, pd6, 3M, pilote+prior gen1) jugé (2440 parties d9 dilf, SE ajustée nulles) :
> • `[gen2-vs-gen1]` rate **0.4934 ±0.0181** (elo −5, IC contient 0,50) = **NEUTRE** par §gates → **gen2 NON promu**.
> • `[gen2-vs-egdbmix]` 0.5008 (**+1** — gen1 était **+14**, donc gen2 a **PERDU** le gain de gen1).
> Signal fort : gen2(pd6) retombe au niveau egdbmix ⇒ **pd6 a-t-il affaibli les données ?** (pilote pd6 = punit moins).
> §gates INTERDIT de conclure « plateau » sans le témoin. **pd6 mesuré ULTRA-rapide** : gen2 3M en ~20min (~50× pd10).
>
> **BRAS TÉMOIN pd10** (`cpx62-0552`, en cours) : ~600k pd10, **même pilote/prior gen1**, juge cand-T vs gen1. →
> **cand-T COMPOSE** (borne basse IC>0,50) alors que gen2(pd6) non ⇒ **pd6 coupable** → chaîne à **pd8/pd10** (retry gate NEUTRE).
> **cand-T aussi ≤ gen1** ⇒ **plateau robuste à la profondeur** → figer gen1 → **phase EBF**.
>
> **BUG INFRA corrigé** : le runner **ne committe PAS les champions des jobs rapides** (champion gen2 PERDU ; gen1 en 15h l'avait) →
> **fix = commit JOB-SIDE** (plumbing git dans le job) appliqué au témoin, **à baker gen3+**. (Télémétrie monitor idem : new-file-per-cycle gen3+.)
> **Feeder** `ccx33-0551` (pd8 1M + salvaged 682k → `feed-pooled` ~1,68M) : **données PROFONDES prêtes pour gen3** si pd6 coupable.

## 🔍 AUDIT repo (2026-07-03, F1-F5) — statut
> • **F1** (trou soundness NMP sans `!tactical` — décline captures forcées, masque réfutations de sac) : **FIX VALIDÉ**
>   (jass_tests 100% ; byte-identical au défaut car NMP off ; corrige les coups faux avec NMP-on). Préservé en **patch**
>   (`docs/patches/F1-nmp-tactical.patch`, search.cpp de main INCHANGÉ) → **À BAKER avant la phase EBF** (le DOE EBF va
>   ré-activer le NMP → le trou polluerait le verdict). LATENT au défaut (eg_no_nmp=true).
> • **F3** (quiet-only au gen) : **VÉRIFIÉ GREEN** — `--quiet-only` sur les 4 jobs de la chaîne (0545/0550/0551/0552),
>   gen2-vs-témoin **iso-config** (identiques sauf play_depth + volume) → comparaison valide, pas de « syndrome −700 Elo ».
> • **F4** (draw-rate pd6 vs pd10 = explication mécanique possible du NEUTRE gen2) : à lire sur les dumps au verdict 0552.
> • **F2** (`qs_threat_ext` — moitié manquante de la quiescence Scan, jamais bakée) : A/B en file **au dégel recherche (EBF)**.
> • **F5** (dédup `opponent_can_capture` ×2 dans la qs calme) : micro-perf opportuniste, noté.

## 🏆 PROMOTION gen1 (2026-07-03) — 1re éval combo-aware, +14 Elo vs egdbmix → nouveau champion
> **`champion-gen1-combo`** (`jobs/results/cpx62-0545-selfplay-gen1-combo/artefacts/champion-gen1-combo.pjtw.gz`) est
> le **nouveau champion**. Première éval entraînée sur du self-play **combo-aware** (qs_sacs baké au jeu+label), fit
> **prior-séquentiel** ancré à egdbmix (λ=0.25) → downside borné. Juge vs egdbmix (2440 parties, d9, dilf) :
> **rate 0.520, elo ~+14, SIGNIFICATIF** (SE ajustée aux nulles → borne basse IC 0.502 > 0.50). egdbmix **archivé**
> (réversible). ⇒ **Première preuve concrète que la boucle marche** : recherche voit les combos → self-play punit →
> l'éval progresse, sans NNUE. Confirmation = le **chaînage gen2** (piloté par gen1).
> **CALIBRATION critique** : le self-play à **play_depth 10 est intenable** (box ~19h/3M, PC ~52h/3M). ⇒ gen2+ passent
> à **play_depth 6** (~10× plus rapide). Gen jobs : **moniteur de volume + checkpoint incrémental** (récup si kill).
> gen2 = `cpx62-0550-gen2-pd6` (pilote+prior gen1, pd6). Verdict attendu = **gen2 vs gen1** (la chaîne compose-t-elle ?).
>
> **ÉTAT COURANT (2026-07-03 ~18h)** : les 2 box génèrent avec **gen1 comme pilote** + qs_sacs.
> • **cpx62-0550** gen2 (pd6, 3M, fit prior gen1 → juge vs gen1 + vs egdbmix).
> • **ccx33-0551** feeder (**pd8, 1M**) → POOL avec le **salvaged 682k** (récupéré du feeder 0547 tué, `ccx33-0549`)
>   → `feed-pooled` ~1,68M **à feed à cpx62** ensuite (pool fit). Corpus diversifié en profondeur (pd6+pd8+pd10-salvaged).
> • **asym punisher CONSERVÉ** en gen (choix JFC) ; ext_forcing symétrique-en-gen = idée valide (distillation) mais non
>   retenue pour l'instant. • **Bug infra** : le runner ne re-committe pas les fichiers modifiés → moniteur/checkpoint
>   figés à leur 1re version → **fix dès gen3 : écrire un NOUVEAU fichier par cycle** (progress-NNN / checkpoint-NNN).
> • **Phase EBF** (réduire ~1,8→~1,25 vs Scan, DOE node-EBF, candidats lmr_asym/probcut) = **APRÈS** le plateau de la
>   chaîne éval (co-adaptation pruning↔éval + éviter la confusion d'attribution ; recherche gelée pendant la chaîne).

## 🔒 GATES DE LA CHAÎNE gen-N (gravées 2026-07-03, AVANT le verdict gen2 — décision MÉCANIQUE)
> **Juge standard** (= gen1, comparabilité) : **2440+ parties, d9, openings dilf, eval-pur no-DB, vs champion précédent** ;
> rate + Elo + **BORNE BASSE IC ajustée aux nulles**. Recherche **GELÉE** pendant la chaîne (hash binaire + params search
> consignés → gel VÉRIFIÉ, pas supposé). But de graver *avant* le verdict : neutraliser l'asymétrie post-succès (promouvoir
> gen2 sur un signal faible / re-rouler jusqu'au heads). La décision devient automatique.
>
> **COMPOSITION (gen-N vs gen-N−1)** :
> • **COMPOSE** = borne basse IC(rate) **> 0,50** (= critère promo gen1) → **PROMOTION** gen-N, enchaîner gen-N+1.
> • **NEUTRE** = IC contient 0,50, rate ∈ [0,48 ; 0,52] → **1 retry** autorisé, APRÈS diagnostic témoin pd10 (↓). 2 NEUTRES consécutifs = PLATEAU.
> • **RÉGRESSE** = borne haute IC **< 0,50** → **STOP**, pas de promo, diagnostic obligatoire. **Jamais retenté à l'identique.**
>
> **GARDE-FOUS anti-mirage (à CHAQUE promotion, hors juge)** — gagner le juge mais rater un garde-fou = **NON promu** :
> • **0440 movetime 0,3s** (eval-pur) : gen-N **≥** gen-N−1 (pas de régression combo réelle).
> • **Self-play GÉNÉRALISTE** (openings équilibrés ≠ dilf) : gen-N **≥ 0,48** vs gen-N−1 (pas de sur-spécialisation dilf).
> • **Finale vs Scan** : conversion **≥** gen-N−1 − bruit (l'acquis egdbmix 0,900 ne s'érode pas ; prior λ protège mais VÉRIFIER).
>
> **DIAGNOSTIC pd10 OBLIGATOIRE** : si NEUTRE/RÉGRESSE, **INTERDIT** de conclure « plateau » tant que le **bras témoin pd10**
> (compute-égal, même pilote/qs_sacs/asym/λ) n'a pas tranché *profondeur-du-pilote vs chaîne-plafonne*. (Risque n°1 = bascule
> pd6 : un pilote pd6 punit moins bien.)
>
> **PLATEAU** = 2 gen consécutives non-COMPOSE **APRÈS** diagnostic témoin → **figer champion** (dernier COMPOSE) → **phase EBF**
> (DOE node-EBF, candidats lmr_asym/probcut) → **re-boucler éval APRÈS** (alternance éval↔recherche, chacune gèle l'autre).
> Le plateau **n'est PAS une fin** — c'est l'alternance.
>
> **BUDGET** : chaîne **≤ 6 générations** OU plateau, premier atteint. Au-delà = décision explicite JFC (pas d'inertie).

## ✅ VERDICT (2026-07-03) — qs_sacs BAKÉ + côté RECHERCHE CLOS (2 DOE) ; self-play combo-aware en cours
> Une COMBINAISON = coup quiet de SACRIFICE → reprise forcée. La quiescence de jass était CAPTURES-ONLY → **aveugle**
> aux combos au horizon. Résolu et **BAKÉ sur main** (`qs_sacs=true` par défaut, commit `a1cfe78c`).

- **Le naïf explose, la sélectivité de Scan transfère.** forcing-qs naïf (`0537`) : 0440 fixe 0,32→0,43 MAIS node-EBF
  ×5-10 → neutre à movetime. Port FIDÈLE de `add_sacs` de Scan (`src/scan_sacs.cpp`, **validé bit-à-bit 640/640** vs oracle) :
  détection combos **d11 fixe 0,58→0,67**, **movetime 0,3s 0,61→0,65 (TRANSFÈRE)**, node-EBF **borné ~1,19× médian**.
  ⇒ **BAKÉ** (`qs_sacs`, gaté men-only+no-threat, depth0-only). Mesuré par DÉTECTION par-position (pas 3660 parties — reproche
  efficacité JFC), branche `claude/scan-sac-quiescence` mergée.
- **DOE factoriels (remplacent l'OFAT — reproche JFC « on fait du OFAT, monte un DOE + calcul de taille »).** 2^(5-1) Res V,
  réponse DÉTERMINISTE (`--search-profile` prof. fixe : détection=payoff, log-nodes=coût), analyse appariée 900 combos,
  effets principaux **+ 10 interactions 2FI**, coin optimal sur 32 coins. **`0543` pruning** (rfp/razor/multicut/no_reduce) =
  **négatif propre** : aucun effet détection signif., relâcher = pur coût (t jusqu'à 81). **`0544` extensions** (ext_forcing/
  single_reply/lmr_asym/iid/probcut) = **ext_forcing aide (d+0,029 t=4,2) MAIS ×10 nœuds ≈ −4 plies** → rejeté par la
  contrainte de budget-nœud. **⇒ côté RECHERCHE CLOS : qs_sacs capte TOUT le gain combo ; les 10 autres leviers n'aident pas
  net.** Bonus force (pas combo) : `lmr_asym`/`probcut` **économisent des nœuds** détection-neutre → candidats Elo pour plus tard.
- **Passe self-play combo-aware `cpx62-0545` EN COURS** : 3M, pilote=champion, **prior séquentiel** (#326, bit self-desc
  strippé), **enrichissement combo** (`combos.jnnw` 0464), **asymétrie CONSERVÉE** (antidote au mislabeling des combos sous-
  exécutés). Juge gen1 vs champion (Elo). Prochaine passe recherche (allégée, jugée Elo) APRÈS la nouvelle éval (co-adaptation).

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

## 🔥 VERDICT 0483 (2026-06-27 nuit) — L'ÉCART 0440 EST EN GRANDE PARTIE DE LA **RECHERCHE** (extension forçante)
> Le décideur #1 du briefing externe a tranché. A/B sur la jauge **0440** (champion egdbmix, depth-fixe d11, eval-pur no-DB,
> vs Scan, **SANS re-entraînement**), reconstruit des 610 parties/bras dumpées :

| bras (search) | 0440 | IC95 | Δ vs base |
|---|---|---|---|
| **A baseline** | 0,302 | [0,254 ; 0,352] | — |
| **B no_reduce_forcing seul** | **0,434** | [0,382 ; 0,485] | +0,13 |
| **C ext_forcing** (extension +1 + exempt LMR/LMP) | **0,603** | [0,552 ; 0,652] | **+0,30 (HORS IC)** |

- **C quasi DOUBLE la baseline** (0,302 → 0,603), IC disjoint (0,552 > 0,352). **À profondeur fixe d11, l'écart 0440 était
  surtout de la RECHERCHE** (l'horizon coupait les lignes forçantes sac→rafle→regain), **pas de l'éval**. Recadre fortement le
  diagnostic « c'est l'éval » (qui n'avait isolé que l'élagage 0436 et la non-réduction 0451, jamais une **extension**).
- **C (0,603) DÉPASSE même la baseline-à-movetime (0,519, 0451)** ⇒ indice que ce n'est pas qu'un « d11 qui rattrape le
  movetime ». **MAIS** ⚠️ à confirmer : 0451 prévient qu'à movetime la profondeur (d14-16) trouve déjà les combos.
- **`ext_forcing` implémenté** (`search.cpp`/`search_params.hpp`, gated OFF) ; check local : changeait 12/13 combos dilf à d11.

## 🎯 VERDICT 0525/0526 (2026-07-01 nuit) — le trou COMBINAISONS est de la RECHERCHE, PAS l'éval-feuille ⇒ distill statique CLOS
> Le localiseur éval-vs-recherche a tranché (demande JFC « Par curiosité va y »). Distille l'éval de Scan (STATIQUE d1 vs
> RECHERCHE d12) → JOUE jass-search+eval vs Scan sur la jauge 0440 (d11, no-DB, N=610). Relance après bug --threads (0523/0524).

| bras | fit train_loss | conv. 0440 (jass au trait) | Scan au trait | vs baseline egdbmix 0,302 |
|---|---|---|---|---|
| **STATIQUE (0525, Scan d1)** | **2,57** (bien posé) | **0,261** | 0,943 | ≈ (−0,04) |
| RECHERCHE (0526, Scan d12) | 20,77 (mal posé, 8×) | 0,179 (n=475) | 0,956 | pire |

- **CONTAMINATION CONFIRMÉE** : fitter l'éval STATIQUE de Scan est bien posé (loss 2,57) ; fitter son SCORE DE RECHERCHE
  est mal posé (loss **20,77 = 8×**) — une fonction statique ne PEUT PAS représenter une valeur de recherche. ⇒ nos
  distillations historiques (0147 = Scan-d10) visaient le **mauvais signal** (le plateau distill était en partie un artefact).
- **MAIS le distill statique PROPRE NE LÈVE PAS la conversion** : **0,261 ≈ baseline 0,302, LOIN de Scan 0,943.** Donner à
  jass une éval DÉRIVÉE de Scan ne le fait PAS convertir comme Scan. ⇒ **le trou 0440 n'est PAS l'éval-feuille → c'est la
  RECHERCHE** (quelles lignes forçantes l'arbre d11 explore). **Converge** avec ext_forcing (0483/0485 : l'EXTENSION forçante
  récupère les combos à profondeur fixe) et DIAG#1a (ordering sain). Les deux bras ≈ baseline, aucun proche de 0,95.
- **IMPLICATION STRATÉGIQUE (majeure)** : une meilleure éval — linéaire riche OU **NNUE** — ne fermera PAS ces combinaisons ;
  c'est un problème d'ARBRE (quelles lignes explorées), pas de feuille. L'axe éval sert le jeu **POSITIONNEL** (0330 : perte à
  profondeur égale), pas ces shots. ⇒ **le levier « distiller l'éval de Scan » est CLOS** (version propre testée, n'aide pas)
  ET **l'argument « ouvrir la gate NNUE pour fermer les combos » est AFFAIBLI** (NNUE = meilleure feuille, pas meilleur arbre).
- **Caveat** : éval Scan-DÉRIVÉE (fit loss 2,57), pas les poids EXACTS de Scan ; signal robuste (les 2 bras ≈ baseline). Version
  airtight = porter les poids réels de Scan (réserve). 0526 : 475/610 parties analysées (dumps manquants), signal 0,179 net.
- ⇒ **RESTE** : (a) **tactique = recherche** (ext_forcing movetime-neutre 0509 → dur) ou **FM** (interactions = encodage
  STATIQUE des paires de motifs, que le linéaire NE peut pas — ce verdict le MOTIVE) ; (b) **positionnel = éval** (vérité-externe #6, FM).

## 🎯 DIAG #1a + COMBO Scan (2026-07-01 soir) — l'éval-structure ÉCARTÉE ; convergence « linéaire proche épuisé »
> Briefing localisateurs (JFC) : mesurer OÙ est le gap d'arbre vs Scan, pas deviner.

- **DIAG #1a (0522, node-count jass d1-d6, instrumentation passive PR #325)** : **cutoff-au-1er-coup = ~90%** (89,9→92,0
  sur d2-d6) + **re-recherche = ~1%** (0,77-1,21%). Un alpha-bêta sain est à ~90%+ ⇒ **jass ordonne DÉJÀ très bien**. La thèse
  JFC « trop de patterns → éval moins fiable → mauvais ordering → arbre gras » est **ÉCARTÉE** (si l'ordering était le canal,
  cutoff-1er serait à 70-80%). ⇒ **l'arbre gras ne vient PAS de la structure/discrimination de l'éval** mais du CALENDRIER
  D'ÉLAGAGE (jass tuné conservateur, 0264/0268 : réduit MOINS pour garder la force). Converge avec 0510 (EBF non-éval-bound).
  JFC : « ça suffit » ⇒ #1b (compare Scan) et #2 (port Scan-eval) et #3 (8cf) NON lancés.
- **COMBO Scan (0520/0521)** : single_reply+asym ensemble = **parité** (combo 0,534@0,1s ≈ single_reply seul, n=610, pas de
  composition) ; **EBF vs Scan AGGRAVÉ** (le single_reply étend, domine l'asym → d15 ratio 2,23→4,98). ⇒ la recette Scan
  assemblée **ne ferme pas l'écart**.
- **CONVERGENCE (bilan de tout)** : (1) EBF = tradeoff d'élagage Elo-LOCKÉ (moins réduire = +Elo, 0264/0268 ⇒ on ne peut pas
  rétrécir l'arbre sans perdre la force) ⇒ **recherche proche épuisée** (conthist −9% baké ; Scan-levers = efficacité parité).
  (2) éval : ordering sain (DIAG#1a), qualité ne pilote pas l'EBF (0510) ⇒ la faiblesse = **jugement positionnel par-ply**
  (0330 : perd à profondeur égale), qui **plafonne** (distill-plateau, from-scratch-plat, hier-l2/asym négatifs, tous ~0,28
  en 0440 / ~0,52 movetime vs Scan 0,95). ⇒ **faisceau de preuves d'un plateau linéaire SOUS Scan** = la condition de la
  règle gravée pour ouvrir la gate NNUE. QUESTION RESTANTE : la distillation Scan a-t-elle visé l'éval STATIQUE de Scan
  (in-class) ou son score de RECHERCHE (contaminé, mur statique-vs-combo) ? = le dernier point à clarifier avant NNUE.

## 🚀 EN TEST (2026-07-01 soir) — LOCALISEUR éval-vs-recherche : distillation STATIQUE de Scan (0525/0526)
> Exécute la QUESTION RESTANTE ci-dessus (« Par curiosité va y », JFC). Le port `src/scan_eval.cpp` EXISTE mais n'a JAMAIS été
> fitté sur l'éval STATIQUE de Scan : toutes nos distillations (0073-0086/0147-0149) visaient son score de RECHERCHE (d10 = contaminé).
> ⚠️ 1re tentative 0523/0524 morte (rc=7 : `relabel_with_scan` n'a pas de `--threads`) → **relancé 0525/0526** (relabel parallélisé par shards, static passé d0→**d1** pour émettre un score Scan fiable ; d1 reste aveugle aux sacrifices).

- **cpx62-0525 (STATIQUE, d1)** : relabel corpus (`0328`, 400k, **shards //**) au Scan **depth 1** (quasi-statique : 1 ply + quiescence forcée
  → aveugle aux SACRIFICES multi-plis = les combos de 0440) → fit le port v3 (features déjà matchées à Scan) →
  JOUE **jass-search + Scan-static-eval vs Scan** sur la jauge **0440** (d11, no-DB).
- **ccx33-0526 (CONTRÔLE, d12)** : jumeau exact, relabel au **score de RECHERCHE** (d12) → static-vs-search apples-to-apples
  (reproduit proprement 0147 sur le corpus/pipeline courant).
- **DÉCIDEUR** : conv ~Scan(0,95) ⇒ **gap = ÉVAL** (notre fit/point-fixe) → re-distiller/enrichir l'éval (pas encore NNUE) ;
  conv ~baseline(0,30-0,52) ≪ Scan ⇒ **gap = RECHERCHE** (jass-search < Scan même AVEC son éval) → avec le faisceau plateau,
  **condition de la gate NNUE remplie (preuve, pas impression)**. Croisé : static ≫ search ⇒ la contamination-recherche
  PLOMBAIT le fit historique (le vrai signal était l'éval statique) ; static ~ search ⇒ la profondeur du label n'est pas le levier.
- **Réserve (si 0523/0524 ambigus)** : porter les **poids RÉELS de Scan** (open-source, présents sur les box `/root/jass-scan`)
  dans le port v3 via convertisseur → mesure jass-search+Scan-eval EXACTE, sans dépendre de notre fit. Non lancé (plus coûteux).

## 🔬 BATCH LEVIERS 2026-07-01 (4 négatifs, 1 lead) — méthodo node-EBF exact
> Après réouverture (mémos Box-Cox + Scan lus dans rhalbersma/scan). Tous mesurés proprement (node-EBF exact / A/B N propre).

| levier | verdict |
|---|---|
| **Box-Cox** (forme LMR, `lmr_formula=2`, PR #323) | ❌ **AUCUNE forme ne domine** le linéaire (ratio<0,92 & accord>0,90 sur d12) → EBF structurel *sur la MAGNITUDE de réduction*, prouvé sur toute la famille |
| **hier-l2** (backoff, PR #322) | ❌ 0440 : baseline 0,279 vs hierA 0,239 / hierB 0,236 / hierC 0,275 → n'aide pas (pires) |
| **asym labels** (0511, robust masters) | ❌ 0440=0,275 ≈ OFF(0,279) ≈ base(0,302) → ne bouge pas l'éval (comme 0486/0489). (OFF arm 0512 a crashé rc=9.) |
| **single_reply** (Scan #1, PR #324) | ⚠️ **0519 : parité vs baseline** (0,487-0,535, penche+ @0,1s) MAIS **bat nettement ext_forcing large** (0,54 vs 0,26) → thèse « étroit≫large » du mémo CONFIRMÉE, mais pas de WIN net |
| **LMR asym pv/non-pv** (Scan #2, PR #324) | −24% nœuds EXACT (0516) MAIS **0518 : Elo ~parité** (asym_2_4=0,491, asym_1_3=0,477) → le −24% nette parité à movetime (profondeur gagnée ≈ coût sur-réduction). **Efficacité, pas gain de force** (comme conthist) |

- **Clé** : le Box-Cox teste la *magnitude* de réduction (dead) ; l'**asymétrie pv/non-pv** teste *où* réduire (−24%). L'axe qui
  compte = **pv/non-pv**, pas la forme. Réduire dès le 2e coup aux nœuds cut (comme Scan) coupe l'arbre 24%.
- **Bilan leviers Scan (0518/0519 FAITS)** : les deux mécanismes de Scan **marchent** (implémentés/lus dans sa source) mais
  isolément = **efficacité (−24% nœuds) sans gain de force mesurable** ; aucun n'est négatif ; single_reply valide « étroit≫large ».
  **En cours** : 0520 (COMBO single_reply+asym ensemble — compose-t-il ?) + 0521 (EBF vs Scan : le croisement d15 recule-t-il ?).
- **PISTES ÉVAL (question JFC 2026-07-01)** : distillation Scan = **DÉJÀ fait massivement** (0073-0086/0147-0149, plafond) ;
  from-scratch bootstrap = **DÉJÀ fait, plat** (0481/0482 ~0,25-0,29). ⇒ pas de re-start. Mur gravé : éval linéaire STATIQUE
  ne peut encoder les combos résolubles par la recherche ⇒ une partie du gap EST la recherche. **Diagnostic manquant = PORTER
  l'éval Scan (open-source) dans NOTRE recherche** : jass-search+Scan-eval ≈ Scan ⇒ gap=éval (re-distiller avec features Scan) ;
  < Scan ⇒ gap=recherche ⇒ ou NNUE avec preuve. C'est le seul test qui LOCALISE le gap (éval vs recherche). Non lancé (choix JFC).

## 🏁 CLÔTURE CHANTIER RECHERCHE/EBF (2026-06-30) — exploré à fond ; 1 gain (conthist) ; l'EBF est éval-bound
> Bilan final du chantier "battre le gap movetime vs Scan par la recherche" (memo EBF v2). Verdict : **l'EBF est largement
> STRUCTUREL/éval-bound en dames ; aucun knob de recherche ne le déplace significativement.** Détail des leviers :

| levier | méthode | verdict |
|---|---|---|
| LMR linéaire→log (#1) | A/B movetime + node-EBF | **aucun** effet EBF (mild=EBF↑, agressif=Elo↓) ; clos |
| sweep `forcing_ext_cap` | A/B movetime dilf | optimum cap~6 (0,491) mais **pas de flip** ; clos |
| ext_forcing @ tous movetimes | A/B clean (0508/0509) | **PERD** (0,357@0,1s, neutre@0,3s, perd@1,0s) ; le 0,543@0,1s était un artefact non-flush ; **CLOS définitif** |
| history-LMR (#2) | A/B | parité ; clos |
| IID (`iid_min_depth`) | **node-EBF EXACT (0507)** | **ratio nœuds 1,000** = ZÉRO effet (le "−9% EBF" de 0504 était du bruit-timing) ; clos |
| **conthist** | node-EBF + A/B | **−9,5% nœuds @d12 (exact) + Elo-neutre → BAKÉ (use_conthist=true, PR #321)** ; seul gain, modeste |
| TT-2-bucket (#5) | lecture `tt.cpp` | **MOOT** : TT déjà 4-way clustered + generation aging (mieux que 2-bucket) ; rien à faire |

- **Méthodo clé acquise** : l'EBF-par-TEMPS est trop bruité (±11%) ; le **node-EBF EXACT** (`--search-profile +search-params`,
  commit 24ef71dc6) est le bon outil. Et le **non-flush est résolu** (stdout shard→output.log + pairs=1 → n=610 propre).
- **Conclusion** : la thèse du mémo (« l'EBF = le grand levier gagnable ») **NE se vérifie pas**. Le seul gain (conthist
  ~9%) est sous le bruit Elo. ⇒ **le détour recherche est CLOS.** Le gap movetime n'est pas réductible par le tuning search.
- **En cours (0510)** : test EVAL-BOUND en node-EBF (hc faible vs egdbmix fort) — si une meilleure éval = moins de nœuds,
  l'EBF gap ET le gap de conversion (0,52 vs Scan 0,95) sont **LE MÊME problème (l'éval)** ⇒ pivot éval unifié et justifié.
- **Prochaine grande étape (décidée avec JFC)** : pivot ÉVAL/GEN — le vrai goulot que tous les diagnostics répètent.
- **0510 — test EVAL-BOUND (node-EBF exact, hc vs egdbmix) : RÉFUTÉ.** L'éval FORTE (egdbmix) cherche PLUS de nœuds
  (ratio egdbmix/hc = 1,44/1,35/1,62 à d9/12/15), pas moins. ⇒ **l'EBF est STRUCTUREL, PAS éval-bound** : améliorer l'éval
  ne baisse PAS l'EBF (au contraire). EBF (movetime) et conversion (force) sont **deux problèmes SÉPARÉS**. Le gap movetime
  est structurel et non réductible (ni par search, ni par éval). Le champion egdbmix est net-positif malgré + de nœuds
  (meilleure éval > coût-nœuds) — situation standard : améliorer l'éval reste gagnant au jeu.
- **Bake conthist validé** (0510) : 6476/6486 assertions OK ; les 10 échecs sont TOUS dans test_scan_book (roundtrip
  save/load de livre — env/filesystem sur la box, SANS rapport avec conthist). Bake maintenu. (À re-vérifier que ces
  échecs scan_book existent aussi sur baseline = bruit d'env.)
- **CONCLUSION FINALE** : chantier recherche CLOS ; EBF structurel (pas réductible) ; la conversion (0,52 vs Scan 0,95)
  reste le goulot et c'est l'ÉVAL. ⇒ pivot ÉVAL/GEN pour la FORCE (pas pour l'EBF, qui est un problème séparé/structurel).

## 🔧 CHANTIER EBF (2026-06-29 soir, memo JFC v2) — le gap movetime = EFFICACITÉ de recherche, pas l'éval
> Recadrage : `ext_forcing` neutre à movetime (0490/0491) **parce que l'EBF (facteur de branchement) de jass est trop
> haut** → il ne peut pas se payer la profondeur que les extensions coûtent. Baisser l'EBF = acheter les ~2-4 plies du gap
> d'éval (0330) **sans toucher l'éval** ET rendre `ext_forcing` abordable. **Tout dans la classe linéaire, gate NNUE fermée.**

**#0 (0495, FAIT) — re-mesure EBF post-combo :**
| profondeur | jass s/pos | scan s/pos | jass/scan |
|---|---|---|---|
| d9 | 0,0059 | 0,0149 | **0,40** (jass + rapide) |
| d12 | 0,0340 | 0,0237 | 1,44 |
| d15 | 0,1377 | 0,0573 | **2,40** |

- **EBF_jass = 1,69 · EBF_scan = 1,25.** Faits qui recadrent : (1) **jass est plus rapide PAR NŒUD** (0,40 à d9 *avec*
  un EBF plus haut → SIMD payé) ⇒ **tout le gap movetime est de l'EBF, zéro du coût/nœud** ; (2) **le croisement est ~d11**
  (jass gagne jusqu'à d11, perd au-delà). **Cible recadrée (atteignable) : repousser le croisement ≥ d15, PAS viser le 1,25
  de Scan.** Arithmétique : R(15)=2,40 → il suffit de **~6 %/ply** d'EBF (`(1−0,06)^15≈0,42`) — un petit écart élevé à la
  puissance 15. Un swap LMR linéaire→log en rend typiquement >6-10 %.
- **SRC** : `lmr_formula` (0=linéaire legacy DÉFAUT byte-identique ; 1=log `R=lmr_log_base+log(d)·log(idx)·lmr_log_mul/100`)
  + `lmr_log_base`/`lmr_log_mul` ajoutés sur **main, gated OFF** (parser int-only respecté). Impl **inline** pour la phase
  A/B (test conservateur : log() coûte/nœud) ; **table-ize obligatoire AVANT tout bake** (sinon on mange le gain d'EBF).

**#1 (0496, FAIT) — A/B log(mul=40) vs linéaire @ movetime, dilf :** score log = **0,444** [0,388 ; 0,500] (n=303, 5/8
shards — non-flush). **Le log mul=40 PERD même sur dilf** (le cas favorable), variance énorme entre shards = **signature
0264/0268** (jass a mesuré +42 Elo en réduisant MOINS ; la sur-réduction rate des lignes forcées). ⇒ **mul=40 sur-réduit**,
pas « log mort ».

**#1b (0497, EN QUEUE) — sweep mul {20,25,30,35}** (plus petit = moins de réduction). **GATE** : un mul **≥0,55 hors-IC** =
garde la force EN réduisant ⇒ CANDIDAT → #1c (re-mesure EBF avec ce mul + A/B jeu GÉNÉRAL **Elo≥baseline** + vs Scan +
table-ize). **TOUS ≤0,5** ⇒ le LMR-log sur-réduit à tout coefficient utile en dames (**prior 0264/0268 confirmé**) ⇒
chantier LMR-log **négatif** ⇒ basculer **diagnostic #3** (part éval-noise de l'EBF : churn PV / re-recherches ; un objectif
d'éval de STABILITÉ ≠ 0440 baisserait l'EBF). ⚠️ **0264/0268 est LE mur de ce chantier** ; le garde-fou Elo≥baseline tranche.

**#1c (0498, FAIT) — R(d)/EBF sous LMR-log : VERDICT NÉGATIF, volet LMR-shape CLOS.** Mesure (cpx62, eval-pur, vs Scan) :
| config | EBF_jass | R(15)=j/s@d15 |
|---|---|---|
| linéaire | 1,578 | 2,40 |
| mul20 | 1,646 (+4,3%) | 3,93 (+64%) |
| mul25 | 1,596 (+1,1%) | 3,61 (+50%) |
| mul30 | 1,617 (+2,4%) | 2,41 |
- **Aucun mul ne baisse l'EBF** — tous égaux/PIRES que le linéaire (et dans le bruit ~7% de la mesure-temps). Verrou :
  mild log (20-30) réduit MOINS que le linéaire → EBF↑ ; aggressive (40) → Elo↓ (0496 0,444). **Aucun coefficient log ne
  baisse l'EBF en gardant la force.** ⇒ **la forme LMR (linéaire→log) N'EST PAS le levier EBF en dames** — l'hypothèse du
  mémo (nœuds calmes dominent l'arbre comme aux échecs) NE transfère pas (captures forcées → structure d'arbre différente).
  **#1 (LMR-log) CLOS NÉGATIF.** Le linéaire actuel est déjà ~Pareto-optimal.
- **#2 (0499) history-LMR** (`lmr_hist_div`) testé en parallèle (levier indépendant) — résultat à venir.
- **Reste du chantier EBF** : si #2 ne paie pas non plus, le seul angle restant = **#3 diagnostic éval-noise** (l'EBF
  1,58 vs Scan 1,25 est-il *mécanique* — alors épuisé — ou *éval-bound* (mauvaise éval → mauvais ordering → arbre touffu) ?
  Si éval-bound ⇒ le levier EBF devient un objectif d'éval-STABILITÉ ≠ 0440). Sinon l'EBF est structurel aux dames ⇒
  le gap movetime n'est PAS adressable par la recherche ⇒ retour au gen/éval. Décision JFC après #2/#3.

### 🔧 FINE-TUNING ext_forcing — `forcing_ext_cap` (insight JFC, 2026-06-30)
> **Correction** : « ext_forcing NEUTRE à movetime » (0490/0491 = 0,473) était mesuré avec **`forcing_ext_cap=0` =
> ILLIMITÉ** (défaut ; `cap<=0` ⇒ extensions sans borne) → blowup de nœuds → neutre. **Test mal tuné** (jass meilleur
> par-nœud à d4-d9 mais perd à d15 ⇒ deepen SÉLECTIVEMENT les combos, pas exploser uniformément).

**0501 (sweep cap) — ext_forcing=1 + cap={4,6,8,12} vs baseline @ movetime 0,3s, dilf :**
| cap | score | IC95 | n |
|---|---|---|---|
| 4 | 0,438 | [0,379;0,497] | 273 (perd, trop serré) |
| **6** | **0,491** | [0,426;0,556] | 227 (optimum) |
| 8 | 0,479 | [0,409;0,550] | 193 |
| ∞ réf | 0,473 | — | (0490/0491) |
- **Le cap COMPTE** (intuition JFC validée) : optimum ~cap=6 (0,491) > illimité (0,473) > cap=4 (0,438). **MAIS pas de
  flip** : ~0,49 = neutre, pas ≥0,55. Le tuning récupère ~+0,018, pas la conversion. Coût-nœuds ≈ gain tactique, même capé.
- ⚠️ **Sous-puissant** (non-flush n~200-270) → IC cap=6 jusqu'à 0,556, positif marginal non exclu.
- **Suite (choix JFC)** : re-run CLEAN haut-N à cap=6 ± balayage movetime (0,1/0,3/1,0s). #2 history-LMR (0499) = tout parité.

### 🧪 PISTE ORDERING + node-EBF EXACT (2026-06-30) — conthist = le seul (petit) gain GRATUIT
> Constat : déficit movetime = EBF concentré en d9-12. En dames captures forcées => l'EBF = ordering des coups CALMES.
> Knobs ordering OFF par défaut : IID (iid_min_depth=0), conthist (use_conthist=false).

- **Méthodo corrigée** : l'EBF-par-TEMPS est trop bruité (0504 vs 0506 contredits, baseline ±11% sur mêmes positions) =>
  incapable de voir ~6%. Fix : **node-EBF EXACT** (`--search-profile <fen> <d> 0 <eval> <params>`, commit 24ef71dc6 ; nodes
  déterministes), **paired** (ratio nodes_knob/nodes_baseline, variance-position annulée).
- **0507 (node-EBF exact, paired) — verdict net** :
  | config | ratio nœuds @d12 | @d15 |
  |---|---|---|
  | iid6/iid8 | 1,00 / 1,00 | aucun effet |
  | **conthist** | **0,905** | 0,941 |
  ⇒ **IID = du vent** (le « IID baisse l'EBF » de 0504 était du BRUIT, confirmé exact). **conthist = vrai gain : −9,5 %
  nœuds @d12, EXACT, et Elo-neutre (0505 n=610)** => **gain EBF GRATUIT** (l'arbre rétrécit ~9% au milieu sans coût force).
- **Lecture chantier EBF** : l'EBF est **largement STRUCTUREL** en dames — ni LMR-shape (#1c) ni IID ne le bougent. **Seul
  conthist** donne une réduction réelle, mais **modeste** (~9% niveau, PAS le 6%/ply compoundé du mémo). Pas le grand
  effondrement promis ; un petit levier gratuit à prendre.
- **Non-flush RÉSOLU** : stdout shard (START/RESULT/DONE) → output.log (committé fiable) + pairs=1 => n=610 propre (0505).
- **En cours** : 0508 (conthist multi-movetime, bake-decider — bémol historique −11 Elo en 0253 à lever) ; 0509 (ext_forcing
  cap=6 @ movetime 0,1s : 0503 penchait 0,543 en budget tendu). Si 0508 ≥ parité partout => **baker use_conthist=true**.


## 🔥 VERDICT 2026-06-29 — ext_forcing au JEU = NEUTRE (le gain depth-fixe NE passe PAS à temps réel) ⇒ recherche-vs-éval tranché
> Re-run propre du bake-decider perdu en 0487 (non-flush). 0490 (n=30) puis **0491 (n=75 ; 4 shards/16 — le non-flush a
> encore mangé 12 shards)** : ext_forcing **ON vs OFF à movetime 0,3 s**, openings dilf tactiques, eval-pur egdbmix.

| test | profondeur | score ON vs OFF | lecture |
|---|---|---|---|
| 0485 | **FIXE** (d11→d15) | 0,60 → 0,73 (hors-IC) | gros gain… mais à profondeur fixe |
| **0490/0491** | **temps fixe** (movetime) | **0,473** [0,360 ; 0,586] | **NEUTRE — le coût-nœuds annule le gain** |

- **Le gain depth-fixe (0485) NE se traduit PAS en jeu chronométré.** À movetime, jass atteint déjà la profondeur où il
  trouve les combos (0451 : 0,519) ; étendre les lignes forçantes coûte autant de nœuds qu'il en rapporte ⇒ wash.
  **⇒ on NE bake PAS ext_forcing comme levier de RECHERCHE au jeu.** La jauge 0440 à d11 **surestimait** sa valeur réelle
  (mirage profondeur-fixe, exactement la crainte 0451). Caveat n=75 (non-flush), mais 0,47 est si loin du seuil bake 0,55
  que « ne pas baker » tient.
- **SYNTHÈSE recherche-vs-éval** (la vraie question stratégique) : ext_forcing est un outil de **recherche**, mais —
  - **comme recherche AU JEU → ne sert pas** (neutre, mesuré 0490/0491) : coût-nœuds = gain.
  - **comme fabricant de labels POUR l'ÉVAL (asym gen) → la SEULE porte** : on **déplace le coût hors-ligne** (le punisher
    paie les nœuds au gen, sans pression temps, pour produire des labels justes `shot-vulnérable → défaite`) ; l'éval
    absorbe le motif **en statique** ⇒ au jeu **coût runtime ZÉRO**. On prend le bénéfice tactique et on le bake dans une
    éval gratuite à l'exécution. **Ce n'est PAS l'inverse** : la recherche-au-jeu est mesurée morte ; l'éval est le pari vivant.
  - **Risque** : suppose que l'éval 32-patterns PEUT représenter « shot-vulnérable » en statique. 0486 (labels propres,
    0,282 ≈ base 0,302) fait craindre un **plafond de représentation**. 0489/0493 tranchent : 0440(asym) ≫ 0,30 ⇒ l'éval
    absorbe ⇒ industrialiser · ≈ 0,30 ⇒ plafond pattern (⇒ archi plus expressive, ou ext_forcing ne sert nulle part à ce stade).
- **Reconnexion** : au jeu réel le goulot reste l'**ÉVAL** (~0,52 vs Scan 0,95), pas la recherche ⇒ la seule voie où
  ext_forcing aide passe par l'éval. L'enthousiasme « l'écart était la recherche » (0483/0485) était un artefact depth-fixe.

### État du ladder asym au 2026-06-29 (en cours)
- **0489** (cpx62) : asym **fallback** dilf+lidraughts 10M (DB box-local absente de cpx62), **⏳ ~37 h**, fin ~21:45 UTC.
- **0492 tué** (10M trop long sur ccx33, 8 cœurs) → **0493** (ccx33) : asym **propre** 3M (vrais ballots+masters SI la DB
  a survécu), à égalité de seeds vs 0486, **⏳ ~3 h / ~18 h total** (fin ~09:40 UTC le 30/06).
- **0494** (`jobs/paused/`, prêt à dégainer) : variante asym **masters ROBUSTES** — masters chargés du corpus committé
  `master-2000.jnnw` (0014, 371k parties ≥2000) au lieu de la DB éphémère ⇒ **masters=OUI garanti**. À promouvoir vers la
  file si 0493 sort en fallback sans masters.
- ⚠️ **Aucun backup hors-box de `expert_games.db`** (0 release ; 0015 jamais exécuté) ⇒ DB = point unique de défaillance sur
  ccx33. Le corpus masters, lui, est durable (`master-2000.jnnw`). 0488 (sym ON/ON) **retiré de la file** (swap JFC).

### Plus-value quiet-only / logistic-WDL / ballots : NON déductible (bundlés) — 2026-06-29
> Question JFC : peut-on chiffrer l'apport de **quiet-only (#4) + logistic-WDL + ballots (#2)** sur le gen-data ?
- **Non, pas isolément** : dans tout le ladder ces trois sont appliqués **ensemble** (+ masters #6 + pilote egdbmix) ⇒
  confondus, **aucun A/B un-à-un**.
- **Seul signal = agrégé et PLAT** : 0486 (les 3 + masters, recette propre) = 0440 **0,282** [0,233 ; 0,330], base egdbmix
  **0,302 DANS l'IC** ⇒ **bundle indistinguable de la base** ⇒ aucune plus-value mesurable, et **le signe de chacun est
  inconnu** (quiet-only pourrait être net-négatif via la perte de volume, ballots net-positif, et s'annuler à ~plat).
- **Cohérent avec le mur des ~11 leviers (2026-06-27)** : le goulot est le **FIT / distribution des labels**, pas les
  features. quiet-only & ballots = leviers de **distribution-données** ⇒ sous le plancher de bruit de 0440 (±0,05).
  **logistic-WDL** est à part (c'est le **FIT** lui-même, baké comme standard car il agit directement sur le goulot).
- **Implication** : l'**asym (0489/0493)** n'est PAS un 12ᵉ levier de ce type — il change les **labels** (ni features, ni
  filtrage) ⇒ attaque le goulot. Pour chiffrer les 3 il faudrait un A/B **factoriel** (8 cellules, seeds/pilote/volume figés,
  jugé 0440) — **reporté** (compute prioritaire = le décideur asym ; vu le mur, attendu « tous marginaux »).

## 🔥 VERDICT 0485 (2026-06-28) — PAS un mirage d11 : ext_forcing tient à TOUTE profondeur
> Test du mirage : 0440 (egdbmix, eval-pur no-DB, vs Scan, sans re-entraînement) aux profondeurs du jeu réel.

| profondeur | baseline | ext_forcing | écart |
|---|---|---|---|
| d11 (0483) | 0,302 | 0,603 | +0,30 |
| d13 | 0,382 | 0,652 | +0,27 |
| **d15** | **0,502** | **0,726** | **+0,22** |

- La baseline monte vers ~0,52 avec la profondeur (cohérent movetime 0,519/0451 — la profondeur substitue en partie).
  **MAIS ext_forcing reste loin au-dessus à toute profondeur**, y compris d15 : **0,726 vs 0,502, IC disjoints**.
  **L'extension est un vrai levier de recherche, au-delà de la profondeur — pas un artefact d11.** (Caveat : d15_ext
  n=93/305, lent ; mais borne basse 0,645 ≫ 0,502 ⇒ direction certaine.)
- ⚠️ **0487 (bake-decider movetime, ON vs OFF @ temps égal) = FINI rc=0 mais SORTIE PERDUE** (non-flush : shards écrits
  en fin de job, committés vides). Le « net positif à temps fixe » n'est pas mesuré ⇒ **à re-run** (shards incrémentaux).
  L'évidence depth-fixe (0485) reste forte pour baker, mais le coût-en-nœuds à movetime n'est pas confirmé.
  **↑ RE-RUN FAIT (0490/0491, voir VERDICT 2026-06-29 ci-dessus) : NEUTRE 0,473 ⇒ coût-nœuds = gain ⇒ NE PAS baker au jeu.**

## 🛠️ FORCING-EXT SPEC (2026-06-28) — 3 slots + self-play ASYMÉTRIQUE + cap (implémenté, vérifié)
> Affinement de #1 (cadrage JFC). Implémenté dans `src/` + déployé `main`. **Découverte pipeline** : dans notre
> `gen-data-wdl`, le **label = RÉSULTAT de la partie (rollout)** ; le « label search » ne fixe que le champ `score`,
> **IGNORÉ par logistic-WDL** (compte seulement pour `--target value`). ⇒ le slot **gen-label est un no-op pour notre
> recette** ; le lever au gen = **gen-play** (le rollout fait le WDL).

- **3 slots** (`search.cpp`/`main.cpp`) : `test` (match, déjà via `--jass-search-params`), `--search-params-play`
  (rollout→WDL, le vrai levier), `--search-params-label` (score, ignoré en WDL). Back-compatible.
- **Asymétrie §4** (`--asym-punisher-params`) : couleur **punisher** aléatoire/partie joue `ext_forcing=1` (voyante) vs
  **victim** aveugle ⇒ fabrique la classe **« shot-vulnérable ATTEINTE par la victime → PUNIE → label DÉFAITE »** que le
  self-play symétrique n'a pas. Réponse directe au mur 0460/0462, **sans Scan**.
- **`forcing_ext_cap`** : garde-fou anti-explosion (cap des extensions accumulées sur un chemin). Vérifié : 187k→87k nœuds.
- Tout **vérifié en local** (gen asym + slots + cap → JNNW valides ; cap réduit les nœuds).

## 🔬 EN TEST MAINTENANT (2026-06-28) — le LADDER de recettes gen (couplé ballot/asym)
> Le décideur gen pour notre pipeline = **gen-play** (pas gen-label). 3 recettes comparées sur 0440, base egdbmix 0,302 :

| box | job | recette gen | rôle |
|---|---|---|---|
| **ccx33** | `0486-selfplay-clean` ⏳ tourne | play **OFF** / label OFF (+ quiet-only #4 + ballots #2 + masters #6) | baseline : vulnérable atteinte mais **non punie** (mur 0460/0462) |
| **ccx33** | `0488-selfplay-extgen` ⏳ en file | play **ON** (symétrique) | punie mais **trop propre** (§3) — + exploration |
| **cpx62** | `0489-selfplay-asym` ⏳ tourne | **ASYMÉTRIE** punisher ON / victim OFF | atteinte **ET** punie = le signal manufacturé (§4) |

- **Lecture** : 0440(asym/0489) **>** 0486 ET 0488, hors-IC ⇒ l'asymétrie débloque l'auto-supervision **sans Scan** ⇒
  industrialiser. Plat ⇒ le résidu est RECHERCHE (baker ext_forcing au jeu, cf 0487 à re-run) ou plafond-de-jeu.
- **Caveat seed** : 0489 sur cpx62 peut tomber en fallback dilf+lidraughts (DB box-local ccx33) ⇒ comparer à égalité de seeds.
- **0484 (vérif outils)** = fini rc=0, sortie perdue (non-flush) ; suites unit vertes en local ; 0486/0489 re-valident #2/#6 sur vraies données.

## 🧭 PLAN DE VALIDATION — clean-run convergence (lignée B) [gravé 2026-06-28, JFC]
> **Test de reproductibilité / indépendance au chemin.** Notre champion actuel (lignée **A**) est atteint en BRICOLANT
> la recette en route (chemin sinueux, params changés en marche). Une fois la **bonne recette FIXÉE** (sortie de
> 0486/0489/0490 + suite) et le champion A **poussé à SON plateau** avec, on lance une **lignée B indépendante, tout figé
> dès la génération 0**, jusqu'à SON plateau, et on vérifie que **B converge vers A**. Successeur de 0481/0482 (from-scratch),
> mais **avec la nouvelle recette forte** (ext_forcing + asymétrie) qui donne à B une raison mécanique d'apprendre ce que
> 0481/0482 ne pouvaient pas (§3).

**Distinction gravée (sinon le test est invalide) :**
- **ARCHITECTURE** (32cf men-only, features bakées, L2, fold) = DESIGN validé (gates 0401/0408/0409) ⇒ B la **garde identique**.
- **RECETTE DONNÉES + lignée des poids** (config gen, seeds, règle de mise-à-jour pilote, volume, slots ext_forcing,
  quiet-only…) = ce qu'on a bricolé ⇒ B la **fige dès le départ** et **repart d'un seed INDÉPENDANT** (matériel-pur 0482 ou
  éval embarquée, **PAS egdbmix**). On ne fige pas les **poids** (ils s'entraînent) — on fige tout le **reste** (règles fixes).

**Protocole :**
1. **Figer la recette gagnante** dès qu'elle sort du ladder courant (0486/0489/0490 + follow-ups).
2. **Pousser le champion A à son plateau** avec cette recette (auto-stop quand 0440/force stagnent K itérations).
3. **Lancer B** : recette identique **figée**, seed indépendant, jusqu'à SON plateau.
4. **Trancher la convergence** (B ≈ A ?) :
   - **tête-à-tête** champion_B vs champion_A ≈ **0,50** (le test le plus propre) ;
   - **0440** : |0440_B − 0440_A| dans l'IC (±0,05) ;
   - **vs-Scan** à temps compensé : même bande.

**Lecture :** B→A = **point fixe reproductible** (le bricolage n'était que l'exploration pour TROUVER la recette ; la recette
seule suffit → c'est elle le livrable). B<A = lignée A **path-dependent** (creuser ce qui manque au spec). B>A = la recette
propre **bat** le chemin sinueux → B devient le champion. **Pour la gate** : B converge vers A (best linéaire) ⇒ preuve solide
que le plateau est une propriété de **(classe + recette)**, pas un artefact ⇒ toute décision « linéaire épuisé → gate » devient
**rigoureuse et reproductible**.

### 🚀 BOOST AU PLATEAU — drawish + FM, AVANT de figer la lignée B [gravé 2026-06-28, JFC]
> **Au plateau du champion A linéaire** (et seulement là — sinon on ne peut pas attribuer le gain à l'option vs « encore
> d'entraînement »), tester si **2 options dormantes** le boostent. Celles qui passent **hors-IC** → **bakées dans la recette
> FIXE** avant de lancer la lignée B. Ordre : (1) plateau A linéaire → (2) A/B isolés → (3) baker les gagnantes → (4) lignée B.

- **Drawish scaling** (`drawish_scaling=1` runtime, ou build `JASS_DRAWISH_SCALING`) : re-test légitime (verdict ☠️ 0353
  datait d'un autre régime) **MAIS** feature de **FINALE** (÷8/÷2 vers nulle) ⊥ trou MILIEU ⇒ juger sur la **force globale**
  (self-play + vs-Scan), **PAS sur 0440**. Cheap (flag + re-juge, sans re-fit). Attente : marginal.
- **FM (Factorization Machine)** = **le 1er pas (doux) de la gate**, légitime AU plateau du linéaire pur. Terme FM fitté sur
  le **RÉSIDU LINÉAIRE** (`train.py --fm-rank`, PJTW v4) ⇒ capte les **interactions de paires de patterns** que la somme
  linéaire ne peut PAS représenter = candidat crédible pour le trou **combinaisons** (0440). Protocole : (a) `fm_fitcheck.py`
  = **GATE cheap** (le terme FM réduit-il le résidu ? sans build C++) ; (b) si oui, fit v4 → juger **0440 + force globale** ;
  (c) ⚠️ **temps compensé** (le FM alourdit l'éval → moins de NPS, comme ext_forcing → gain net à confirmer à movetime).
- **Cohérence règle gravée** : FM n'entre qu'**au plateau PROUVÉ du linéaire pur** ⇒ on ne triche pas. Si FM est baké, B reste
  un test de reproductibilité valide (A et B même classe linéaire+FM).

### ⚙️ VOLUME PAR BOUCLE — gravé 8M plancher [2026-06-28, JFC]
> Principe (TVR + verdict couverture 0428) : le **point fixe** se déplace par **ITÉRATION**, pas par volume/boucle ; la
> couverture **sature ~10M** ⇒ au-delà = précision (variance), pas un point fixe plus haut. ⇒ **max d'itérations sur du
> volume juste-suffisant**, PAS peu d'itérations sur du gros volume (20M/boucle = le pire des deux mondes).
- **Volume MONTÉE = 8M/boucle (PLANCHER — ne pas descendre en dessous)**. Proche de la saturation (~10M) → variance/couverture
  sûres, mais ~20% moins cher que 10M. (Le run actuel 0486/0489 mesure le coût réel de 10M quiet-only : >19 h ccx33 / >13 h cpx62.)
- **Refit FINAL unique à gros volume (20-30M+)** sur la distribution convergée → minimise la variance du **champion déployé**.
  C'est le SEUL endroit où le gros volume sert (le champion final), pas par-boucle.
- **Bruit dominant = le JUGE** (305 pos / 28 paires, ±0,05), pas le fit ⇒ on combat ce bruit en augmentant **N du juge**, pas le gen.

### ⚡ PARALLÉLISME 2-BOX — split-gen pondéré par la vitesse [gravé 2026-06-28, JFC]
> Pour accélérer le **climb**, les deux box génèrent le corpus d'UNE boucle **en parallèle** (modèle « split-gen », ~2×
> plus vite/boucle) — PAS deux lignées indépendantes (ça double le débit, pas la vitesse/boucle).
- **Sync via git uniquement** (les box ne partagent PAS de FS — « cross-box fragile ») : chaque box gén son shard et le
  **commite en `.jnnw.gz`** ; un job `fit-juge` **attend les 2 shards committés** → merge → fit → juge. git = vérité partagée.
- **Split DÉSÉQUILIBRÉ, pondéré par la vitesse** (sinon ccx33, ~1,5-2× plus lent, devient le goulot). Sur 8M/boucle, ex :
  **cpx62 ≈ 5M + ccx33 ≈ 3M** → finissent ensemble. **Ratio exact calibré sur les temps du run 10M en cours.**
- **Orchestration en 3 jobs** : `cpx62-gen` (commite `shard-cpx62.jnnw.gz`) · `ccx33-gen` (commite `shard-ccx33.jnnw.gz`) ·
  `fit-juge` (poll les 2 gz → merge → fit → juge 0440). À monter quand la recette gagnante est figée.

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
