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

## GARDE-FOUS (leçons câblées)
Elo-first (G1) · WS-OFF (gen3 −354) · through-search jamais statique (−847) · ancré/warm jamais refit-zéro
passé tour 0 (0645) · holdout par partie (P3) · manifest flag⇒effet (+18 phantom) · **couverture eps
préservée (−25)** — ici c'est LE moteur du bootstrap · confirm haut-N (0599→0600) · min-pieces 32 (parents
distincts) · bug movetime-endgame contourné (juger à prof fixe) · fit streamé exact (--chunk, pas d'OOM) ·
NPS +13-15% baké (self-play/A-B plus rapides).

## TOUR 0 (première marche, à lancer après 0662/0663)
zero.pjtw (header gen2 + corps 0) → gen-data-wdl self-play eps-élevé d10-14 (~1-3M positions, jass rapide
~qq min) → train_stream --target wdl frais → eval(1). **Gate : eval(1) bat eval=0 hors-IC** (le matériel
a été appris) ; mesurer aussi eval(1) vs gen2-mmto (distance au champion). Si oui → tour 1 (WDL+MMTO-self).

## EN UNE PHRASE
La recherche est le prof ; une éval fraîche a le headroom maximal ; on bootstrappe eval=0 par la profondeur
de recherche + l'exploration (le matériel émerge des issues), puis on itère WDL + MMTO-self on-policy jusqu'à
saturation — zéro Scan, zéro distillation, notre propre décollage.
