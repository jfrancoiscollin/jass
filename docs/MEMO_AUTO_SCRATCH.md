# MÉMO — ÉVAL FROM-SCRATCH AUTO-APPRENANTE (zéro prof, zéro distillation) — décoller seuls « à la Scan »

> Auteur : JFC (2026-07-10, direction programme). À passer à Claude Code. Branche `develop`.
> Objectif : reconstruire une éval de ZÉRO avec l'archi actuelle (32cf v4 + extras + phase), SANS aucun
> prof, SANS distillation Scan, depuis la toute première brique self-play — trouver NOTRE propre chemin
> d'apprentissage auto-apprenant. Reco Claude validée : **eval=0 + WDL + MMTO-self**.

## PRINCIPE MOTEUR
`search(eval)` joue toujours mieux que `eval` seule → **la recherche EST le prof**. On entraîne l'éval sur
ce que sa propre recherche plus profonde révèle. eval↑ → search(eval)↑ révèle plus → eval absorbe → …
jusqu'à saturation. (Samuel 1959, TD-Gammon, AlphaZero.)

## POURQUOI D'ICI, ALORS QUE RE-ENSEIGNER gen2-mmto A ÉCHOUÉ
gen2-mmto est au point fixe Scan-mt0.2 (headroom < 0 mesuré, 0658 : jass-mt-long < Scan-mt0.2). Une éval
FRAÎCHE a un headroom ÉNORME (search >> eval-nulle). On repart de là où le gap search-vs-eval est maximal
→ ça compose vite au début, plafonne plus haut (on espère ≥ gen2-mmto, et NOUS l'aurons construit).

## BOOTSTRAP (le plus pur, décolle quand même)
- **eval(0) = ZÉRO** (header v3 gen2 + corps tout-à-0 ; aucun prior, même pas le matériel).
- Self-play à **profondeur FIXE profonde** (d10-14) + **exploration eps élevée** : même avec eval=0,
  l'alpha-beta profond VOIT les gains matériels/tactiques dans l'horizon, et l'eps crée les déséquilibres
  matériels que la recherche PUNIT → parties décisives → le WDL apprend le MATÉRIEL d'abord, puis le
  positionnel (patterns) par-dessus. **La profondeur de recherche = le signal de bootstrap** (analogue
  alpha-beta du random-net+MCTS d'AlphaZero). L'eps est CRUCIAL (sans lui, zéro-eval = trop nul/nulle).
- Repli si le signal tour-0 est trop faible (trop de nulles) : **matériel-only** (men=1,king=3 — pas un prof,
  la règle du jeu) pour amorcer, puis pareil. Mais on ESSAIE le pur-zéro d'abord (gate = eval(1) bat eval=0).

## LA BOUCLE (outillage existant)
Tour t → t+1 :
1. **champion(t) self-play** : `jass --gen-data-wdl N out eval_d play_d maxplies seed --nnue champion(t)
   --explore-eps E --random-open-plies K` (+ seed-pool min-pieces 32) → corpus WDL (issues de parties).
2. **Fit WDL** : `train_stream --target wdl --chunk` (frais au tour 0 ; warm/ancré léger au champion(t) ensuite
   pour stabilité — mémoire qui s'accumule, JAMAIS de refit-zéro passé le tour 0, leçon 0645).
3. **MMTO-self last layer** (dès tour 1, quand eval(t)≠0 donne un rang) : `gen-siblings --leaf-mode` avec le
   coup de la recherche PROFONDE de champion(t) ≻ frères peu profonds (self-asym prof-vs-feuille), `rank_finetune
   --chunk` WS-OFF. Soi + profondeur = prof plus fort que la feuille → carburant. (0650-0656 échouait car
   partait de gen2-mmto ; from-scratch le gap est énorme.)
4. **Gate Elo** champion(t+1) vs champion(t) (self-play A/B, généraliste + dilf, ≥90 paires, confirm haut-N).
   Promu si + fort. Distribution MOBILE on-policy. Bake réversible chaque tour.
5. Itérer TANT QUE ça compose (pairwise held-out ↑ ET Elo ↑). Repère de succès : dépasser gen2-mmto SANS
   avoir jamais touché Scan = autonomie de fait.

## ⭐ TROIS ENGAGEMENTS CHIFFRÉS (JFC 2026-07-10) — ce qui FAIT ou CASSE les tours intermédiaires

### E1. adjud-material DOIT S'ESTOMPER avec les tours (le paramètre décisif)
`adjud-material` **bootstrappe le matériel** au tour 0 (éval aveugle), MAIS tant qu'il **tranche les parties**,
les labels restent **biaisés-matériel** → le savoir POSITIONNEL (ce qui fait la différence après T2-3) exige
des **issues de jeu RÉELLES**. Donc **resserrage progressif puis OFF**, pré-engagé :
| Tour | ADJM (seuil) | ADJH (hold) | esprit |
|---|---|---|---|
| T0 | 2 | 10 | bootstrap matériel, éval aveugle |
| T1 | 3 | 16 | l'éval commence à convertir → exiger + d'avance, tenue + longue |
| T2 | 4 | 24 | quasi-fin du filet matériel |
| **T3+** | **OFF** | — | **issues réelles uniquement** (positionnel) |
**Fade ÉVAL-DRIVEN, pas calendaire** : chaque tour, mesurer la **conversion-self** de champion(t) = depuis des
positions matériel-up (ex. +2 hommes), gagne-t-il en **playout SANS adjud** ? Si conversion **< ~60%**, **NE PAS
desserrer** (tenir le palier — l'éval ne sait pas encore convertir, retirer le filet = labels-nulles inexploitables).
Ce mini-run conversion se committe chaque tour et **décide du palier adjud du tour suivant**.

### E2. drop-post-eps vs la leçon −25 (hypothèse, PAS acquis)
0665 embarque `--drop-post-eps` (hygiène), que la **leçon 0582 couverture>pureté (−25)** avait enterré. Hypothèse
from-scratch : **labels adjudiqués = la pureté re-compte** (le bruit post-eps pollue davantage quand l'issue est
tranchée par le matériel) → drop-post-eps **peut** se justifier ICI. Mais c'est une **hypothèse**. **Pré-engagement :
si T2-3 saturent tôt** (le compose faiblit vite), **1er suspect = re-tester l'A/B couverture** (drop-post-eps ON vs
OFF, eps-frac ↑) DANS ce régime, AVANT d'incriminer autre chose. Ne présumer ni que la leçon −25 tient, ni qu'elle
tombe — la trancher par un A/B dédié au régime from-scratch.

### E3. DISCIPLINE DE COURBE — gate compose-vs-sature PRÉ-ENGAGÉ (anti « encore un tour »)
- **Métrique PILOTE** (décide de continuer) : **Elo champion(t) vs champion(t−1)**, prof fixe **d9**, généraliste+dilf,
  N calibré pour **IC ~±25 Elo**. « Compose » = champion(t) bat champion(t−1) **hors-IC**.
- **RÈGLE D'ARRÊT** : **2 tours consécutifs SANS compose hors-IC ⟹ CLÔTURE** (1 tour plat = bruit possible ;
  2 = plateau réel). Bake du dernier champion qui composait.
- **THERMOMÈTRE EXTERNE (ne PILOTE JAMAIS)** : **d9-vs-Scan** Elo, tracké chaque tour = progrès absolu vers Scan.
  On le REGARDE (rattrape-t-on ?) mais il **ne gate pas** la boucle — on ne distille pas Scan, la boucle est
  champion-vs-champion. (Séparer thermomètre externe / pilote interne = ne pas re-piloter sur Scan par la bande.)
- **CAP DUR** : **≤ 6-8 tours** quoi qu'il arrive **À PROFONDEUR DONNÉE** (borne anti-boucle-infinie par palier — PAS un cap global, cf E5).
- **BUT** : dépasser gen2-mmto **sans jamais toucher Scan** = autonomie de fait.

### E5. ⭐ RAMPE DU PROF — MONTER LA PROFONDEUR DE GEN AVANT DE CLÔTURER (JFC 2026-07-11, DÉCISIF)
**Le carburant de la boucle = l'ÉCART statique↔recherche** (gap éval / αβ). À profondeur de gen FIXE, chaque tour **CONSOMME** ce gap : l'éval absorbe ce que d10 révèle jusqu'à `d10(éval) ≈ éval` ⟹ « plateau ». **MAIS ce n'est PAS un plafond** — c'est juste que **le prof (d10) a été rattrapé** (cf `0621` : le gap statique↔recherche est le carburant, chaque tour le consomme). **Monter le prof RE-CRÉE du gap enseignable.** ⟹ **RÈGLE CORRIGÉE (surclasse le « 2-plateaux = STOP » de E3)** :
- **Quand les tours cessent de composer à profondeur D, NE PAS conclure « plateau/clôture » — MONTER LE PROF d'abord.** La rampe naturelle : **gen d10 → d12 → d14 → movetime** (mt0.5 → mt1.0 → mt2.0). Chaque montée re-crée de l'écart → la compose repart.
- **E3 (2-plateaux) devient un déclencheur DE MONTÉE, pas de clôture** : 2 tours sans compose à profondeur D ⟹ **grimper D d'un cran** (pas STOP), repartir du même champion au prof supérieur.
- **CLÔTURE seulement quand ça plateau au SOMMET de la rampe** (movetime long épuisé) = vrai plafond de la classe linéaire, cette fois mérité.
- C'est **exactement la rampe qu'un Scan a gravie sur des années** : PAS N tours à profondeur fixe, mais une **profondeur de gen qui grandit avec l'élève**. l'élève monte, le prof monte avec.
- ⚠️ movetime : bug overshoot endgame connu → soit durcir le harnais, soit **utiliser le cap-noeuds comme amplificateur déterministe** (monter `--play-max-nodes` = prof plus profond, sans overshoot) en alternative/complément de la profondeur fixe.
- **Coût** : chaque montée = gen plus lente (d14 ≫ d10). Compute illimité (JFC) ⟹ acceptable tant que ça fait grimper l'éval.

### E4. SIZING PAR COUVERTURE DE BUCKETS (mesuré 2026-07-10, corpus-mix2M)
Chaque position active **32 buckets** (1/pattern) sur 17M ; distribution **Zipf** (support réel ≈ **~740k buckets** sur 17M, le reste jamais vu). Métrique de sizing = **cov20/cov30** = % des 32 activations d'une position tombant dans un bucket vu ≥20/≥30 fois (⟹ SE ~1/√K sur le poids). **Courbe mesurée** :
| N positions | cov20 | cov30 |
|---|---|---|
| 100k | 61% | 50% |
| 200k | 76% | 67% |
| **500k** | **89%** | 84% |
| **1M** | **94%** | **91%** |
| 2M | 96% | 95% |
**RÈGLE** : **tours de travail (positionnel) = viser ~500k-1M positions/fit** (genou à 500k ≈ cov20 89% ; 1M = 94/91%). Au-delà de ~1-2M = rendement décroissant (traîne Zipf que la **L2 gère**, inutile de viser 100%). **`--color-fold` ≈ double l'effectif/bucket** (symétrie) → l'intégrer (~250-500k brut suffit alors pour cov20~89%). **Tour-0 = EXCEPTION** : le matériel vit dans les **extras DENSES** (toujours bien estimés), pas dans les buckets → 64k suffit pour le gate « bat zero » (0669 : 5% nulles = signal décisif OK). ⚠️ mesuré sur corpus Scan-ish ; le from-scratch (eps + ouvertures random) **étale plus** → **re-mesurer sur les vraies données du tour**.
**CENSUS AUTO DANS LES JOBS (JFC)** : chaque job from-scratch committe cov20/cov30 après merge du self-play (snippet ci-dessous) → sizing **auto-vérifié**, on voit tour par tour si le volume suffit. Snippet (après `merge_jnnw` → `$W/wdl.jnnw`) :
```python
# census couverture buckets : committe cov20/cov30 dans RESULTS
import numpy as np,struct,sys; sys.path.insert(0,'pattern_jass/tools'); import patterns as P
b=open("$W/wdl.jnnw",'rb').read(); n=struct.unpack('<I',b[4:8])[0]; REC=38
a=np.frombuffer(b[8:8+n*REC],dtype=np.uint8).reshape(n,REC); bb=a[:,0:32].copy().view('<u8').reshape(n,4)
cols=P.flat_feature_columns(P.extract_indices(bb[:,2],bb[:,0])).astype(np.int32); flat=cols.ravel()
c=np.bincount(flat,minlength=P.TOTAL_BUCKETS)
print(f"  COUVERTURE : N={n} buckets_vus={int((c>0).sum())} cov20={float((c>=20)[flat].mean())*100:.1f}% cov30={float((c>=30)[flat].mean())*100:.1f}%")
```

## GARDE-FOUS (leçons câblées)
Elo-first (G1) · WS-OFF (gen3 −354) · through-search jamais statique (−847) · ancré/warm jamais refit-zéro
passé tour 0 (0645) · holdout par partie (P3) · manifest flag⇒effet (+18 phantom) · **couverture eps
préservée (−25)** — ici c'est LE moteur du bootstrap · confirm haut-N (0599→0600) · min-pieces 32 (parents
distincts) · bug movetime-endgame contourné (juger à prof fixe) · fit streamé exact (--chunk, pas d'OOM) ·
NPS +13-15% baké (self-play/A-B plus rapides).

## ⭐ QUIESCENCE PLEINE DÈS LE TOUR 0 (insight JFC — co-adaptation bâtie dedans)
Le mismatch qs de gen2-mmto (0660/0661 : +84 fixed-depth mais −340 movetime, ne co-adapte pas) venait de ce
que gen2-mmto a été entraîné sur un search à qs FAIBLE. From-scratch, on active la **qs PLEINE dès le tour 0**
(`qs_forcing_depth=6,qs_promo_depth=6` via `--search-params`, éventuellement +qs_threat_ext/qs_sacs) sur TOUT
le pipeline (self-play, labels WDL, MMTO-self, gate). Conséquences :
- l'éval s'entraîne sur des feuilles **qs-résolues** → elle apprend la valeur POSITIONNELLE de positions
  tactiquement CALMES (la qs gère la tactique) = le bon découpage eval/search d'un moteur fort ;
- **co-adaptation eval↔search bâtie dedans** dès la 1re brique (pas d'ajout après coup) ;
- au fixed-depth du build, la qs pleine est un PUR gain (+84 mesuré, zéro coût-temps).
- ⟹ **ré-ouvre la question movetime** : une fois l'éval co-adaptée, re-tester full-qs vs default au movetime
  AVEC cette éval (pourrait payer là où gen2-mmto mourait −340). Test de fin de chaîne.
Détail à câbler : gen-siblings (MMTO leaf) + le gate A/B doivent AUSSI passer `--search-params` qs-pleine
(cohérence : toutes les feuilles/parties du pipeline sous la même qs).

## TOUR 0 (première marche, à lancer après 0662/0663)
zero.pjtw (header gen2 + corps 0) → gen-data-wdl self-play eps-élevé d10-14 (~1-3M positions, jass rapide
~qq min) → train_stream --target wdl frais → eval(1). **Gate : eval(1) bat eval=0 hors-IC** (le matériel
a été appris) ; mesurer aussi eval(1) vs gen2-mmto (distance au champion). Si oui → tour 1 (WDL+MMTO-self).

## EN UNE PHRASE
La recherche est le prof ; une éval fraîche a le headroom maximal ; on bootstrappe eval=0 par la profondeur
de recherche + l'exploration (le matériel émerge des issues), puis on itère WDL + MMTO-self on-policy jusqu'à
saturation — zéro Scan, zéro distillation, notre propre décollage.
