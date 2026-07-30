# Jass — synthèse consolidée des résultats du projet

> **Périmètre :** du bring-up initial aux verdicts C1-Q1 et C2-X1 (`x1_no_lead`) et à l'autopsie P3-sibling gen2 du 19 juillet 2026
> **Mis à jour :** 2026-07-26
> **Rôle :** mémoire scientifique ; empêcher de rouvrir une piste close sans fait nouveau
> **Plan actif :** [L3_PURE_PLAN.md](L3_PURE_PLAN.md)
> **État vivant L3 :** [L3_CURRENT.md](L3_CURRENT.md)

Ce document consolide les résultats utiles des anciens CURRENT, journaux,
mémos et spécifications. Les documents détaillés restent sous
[`archives/`](archives/). Ils ne sont plus normatifs. En cas de contradiction,
le verdict le plus récent fondé sur un run complet et son manifest prévaut sur
une interprétation antérieure.

## 1. Comment lire ce registre

| Statut | Sens |
|---|---|
| **établi** | résultat direct, suffisamment dimensionné ou répliqué |
| **supporté** | direction cohérente, mais précision ou réplication limitée |
| **clos** | mécanisme testé sans gain utile ou avec régression ; ne pas relancer à l'identique |
| **supersédé** | résultat réel dont l'interprétation a été corrigée par un test ultérieur |
| **non testé** | idée ou exécution incomplète ; ne pas la présenter comme réfutée |
| **décision de programme** | choix de périmètre, distinct d'une preuve scientifique |

Une porte close ne se rouvre que si au moins un élément causal change : source
de vérité, classe de cible, distribution, budget, mécanisme ou erreur démontrée
dans le run précédent. Augmenter seulement le volume ou changer une seed ne
suffit pas quand le mécanisme a déjà été testé à puissance adéquate.

### 1.1 Portée des portes closes pour L3

Un verdict obtenu sur Gen2 ou une ancienne lignée ferme la **répétition du même
protocole**. Il ne prouve pas qu'un paramètre co-adaptatif de recherche,
d'exploration ou de fit est optimal pour une évaluation jeune partie de
matériel seul. L3 autorise une seule réouverture native, pré-enregistrée et
instrumentée, par blocs de mécanismes. Cette exception ne permet ni un nouveau
sweep aveugle de marges, ni de sélectionner les cellules après lecture.

Inversement, les invariants de vérité — terminal WDL, censure ply-cap, absence
de teacher et séparation train/holdout — ne dépendent pas de la lignée et ne
sont pas des facteurs de DoE.

## 2. Résumé exécutif

1. Le moteur, les règles FMJD, le movegen et l'alpha-bêta sont fonctionnels et
   validés. Le projet a construit une évaluation linéaire Scan-like rapide,
   une chaîne de self-play, des fits streamés et une infrastructure GitOps/R2.
2. Les premières lignées MLP/NNUE ont fortement battu le handcrafted mais sont
   restées très loin de Scan au movetime. Le projet a ensuite choisi de pousser
   la classe linéaire avant tout retour aux réseaux. **Aucun NNUE n'est actif.**
3. Les plus gros gains confirmés sont venus de corrections de méthode, de
   recherche et de fit : `--score-drop`, NMP protégé en finale, coin/NMP,
   threat handling, history probabiliste et MMTO à travers la recherche.
4. `gen2-mmto` est le meilleur champion historique consolidé : environ
   **+52 Elo généraliste** contre gen1 à mt0.3, et **+34 Elo** sur la cellule
   d9 contre Scan. Le déficit restant contre Scan est toutefois encore de
   l'ordre de **−128 à −155 Elo au movetime** selon la cellule mesurée.
   Le gate réparé `home-0965` avait fait de F2M le champion général
   (`57,25 %` contre Gen2 en Q00, `58,60 %` en cadence native). Depuis la porte
   `home-0996` du 27 juillet 2026, **TURNOVER remplace F2M comme champion
   général courant** : `51,98 %` contre F2M sur `n=6000` à vues additionnées,
   `+13,73 Elo`, IC95 `[50,72 ; 53,23]`, avec cinq garde-fous sur cinq verts.
   Consolidé sur quatre pools indépendants, l'écart vaut `+11,24 Elo` sur
   17 000 parties. F2M devient le champion précédent, archivé et restaurable.
5. Le problème de conversion est maintenant séparé de la simple détection :
   Jass trouve souvent les premières idées comme Scan, mais réalise mal
   l'avantage. Sur le thermomètre PC Blues, la conversion mesurée était
   **0,136 pour Jass contre 0,904 pour Scan**. Sur la chaîne `ccx33`, elle reste
   autour de **0,66–0,67** pendant trois tours.
6. Les variantes de la famille « re-fit d'un modèle déjà formé avec oracle,
   gymnase fixe, anchor ou teacher externe » ont plafonné ou régressé. La
   nouvelle question ouverte est différente : une lignée autonome partie
   d'une graine matérielle, sans labels externes ni anchor parent, peut-elle
   apprendre la conversion par ses propres trajectoires complètes ?
7. C0 A/B a produit deux chaînes G1–G3 complètes. Son job haut-N `0792` a
   échoué avant les gates (bug de sizing `not enough fixed openings`), relancé
   corrigé en `0795` : verdict pré-engagé **`retire_frontier_v1_flat`**. La
   frontière mobile v1 n'améliore pas la conversion (Δglobal −0,023, P3 mince
   −0,070, IC recouvrant 0) ; le bras A pur atteint la **parité avec
   `gen2-mmto`** (0,497) depuis une graine matérielle en trois générations. La
   revue C1 a en parallèle identifié deux dettes de méthode : seulement 5/63
   paramètres explicités et une recherche de score inutilisée qui préchargeait
   la TT avant le coup joué.
8. C1-Q1 a fermé contract-grade la quiescence dans le régime L3 jeune :
   menace, sacrifices et interaction sont plats ; Q01 gagne légèrement en
   recherche native sans convertir. Q00 devient la baseline, Q2 n'est pas
   déclenché. Le bloc suivant pré-enregistré est C2-X1 sur la distribution
   d'exploration autonome.

## 3. Chronologie scientifique condensée

### 3.1 Fondation et premières évaluations (`pré-0001` à `0202`)

| Phase | Résultat utile | Verdict durable |
|---|---|---|
| moteur handcrafted | movegen/perft et recherche alpha-bêta validés | socle fiable |
| NNUE v5 | 0,852 vs handcrafted, mais 0,009 vs Scan | progrès interne, écart Scan massif |
| NNUE v6→v8 | v7 0,667 vs v6 ; v8 +258 Elo cumulés vs v5 | qualité data utile, rendements décroissants et non-transitivités |
| gros MLP v9/v11 | capacité accrue, toujours 0,009 vs Scan au movetime | gros réseau seul clos |
| v15 128-64 | meilleur compromis NPS/force, +40,7 % NPS après optimisations | bonne baseline interne, mais environ neutre face à Scan |
| POC Othello | pattern bat handcrafted 0,675 | infrastructure pattern validée ; problème spécifique aux dames |
| pattern standalone | variantes très faibles ; hybride squelette+pattern 0,667 vs handcrafted | le pattern augmente un squelette, ne le remplace pas |
| Scan-style 32 patterns | material anchor : 0,000→0,444 vs handcrafted | architecture linéaire viable |
| `--score-drop` | val MSE 38→1,8 ; jeu ~0,42→0,94 vs handcrafted | scores extrêmes ±9989 empoisonnaient les fits précédents |
| ré-ancrage Scan | le champion flatteur contre v15 est ≈0 contre Scan | v15 n'était pas un juge absolu valable |

Sources détaillées : [JOURNAL_DE_BORD.md](archives/JOURNAL_DE_BORD.md),
[PATTERN_PROGRAM_NOTES.md](archives/PATTERN_PROGRAM_NOTES.md) et
[SCAN_METHODOLOGY_GAP.md](archives/SCAN_METHODOLOGY_GAP.md).

### 3.2 Représentation, géométrie et fit au scale (`0203` à `0454`)

- Le full-fold a réduit le nombre de poids distincts et fait monter les matches
  contre handcrafted, mais le proxy Scan est resté quasi plat.
- Enrichir 32→54 patterns n'a pas payé ; retirer huit patterns a coûté environ
  **−31 Elo sans gain de vitesse**. L'importance des patterns était répartie.
- Les patterns men-only étaient structurellement différents de Scan parce que
  les dames étaient lues comme cases vides. Le correctif king-aware a apporté
  **+37 Elo** dans le test distillé `0240`, mais le gate ultérieur au scale
  `0409` a retenu men-only pour la recette active. Cette séquence interdit de
  relire `0240` isolément comme preuve qu'il faut réactiver king-aware.
- Le scale du fit a corrigé plusieurs faux verdicts historiques : géométrie,
  fold et rois doivent être comparés avec le même budget d'optimisation. Les
  gates finaux ont retenu le color-fold et la géométrie compacte.
- `champion-egdbmix` (`0454`) a donné **+58 Elo** contre le champion précédent,
  conversion finale 0,867→0,900 et précision décisive 88,2→94,4 %. Cela a
  démontré qu'une vérité exacte de finale pouvait encore aider le linéaire.

### 3.3 Mur des données tactiques et localisation search/éval (`0460` à `0605`)

- Environ onze variantes de données ou de génération sont restées autour de
  la même conversion : volume, distribution, élagage gen ON/OFF, masters,
  combinaisons externes, sparring v1, bootstrap deep-relabel et asymétrie.
- Les labels de recherche produits par Jass sur ses propres angles morts n'ont
  pas enseigné ces angles morts (`0460`, `0462`). Les vraies combinaisons de
  maîtres surpondérées n'ont pas déplacé la jauge (`0464`, +0,002).
- `ext_forcing` a presque doublé la jauge à profondeur fixe (`0483`), mais le
  gain a disparu au movetime : le coût en nœuds annule le bénéfice. Les re-tests
  ultérieurs sont devenus franchement négatifs.
- La distillation statique propre de Scan (`0525`) n'a pas levé la conversion.
  La distillation du score de recherche (`0526`) était encore plus mal posée.
  Une évaluation statique ne doit pas être forcée à représenter une valeur de
  recherche multi-ply.
- L'audit eval-oracle corrigé (`0591`) a trouvé des rangs proches : Spearman
  global Jass-oracle 0,952 contre Scan-oracle 0,978. Le vieux `r≈0,04` venait
  d'un mauvais alignement des lignes.
- La quiescence renforcée a amélioré la profondeur fixe mais a perdu
  **−92 à −161 Elo au movetime** : meilleure feuille, coût de nœuds excessif.
- La référence post-search `0605` était environ d9 −310, mt0.3 −161,
  mt1.0 −133 et NPS-comp −134 contre Scan.

### 3.4 Gains de recherche et champion `gen2-mmto` (`0600` à `0648`)

- L'history probabiliste pure, d'abord jugée neutre sur un petit N (`0599`), a
  gagné **+20 à +43 Elo** dans la confirmation haut-N `0600`. Le résultat
  préliminaire est supersédé ; le mécanisme a été baké.
- Le rank-finetune statique a augmenté la pairwise accuracy mais détruit le
  jeu : jusqu'à **−847 Elo** à anchor 0,01. La métrique de fit seule ne suffit
  jamais à promouvoir un candidat.
- Le MMTO à travers la recherche a été le premier vrai gain d'évaluation :
  +23 Elo avec professeur humain, puis **+38/+47 Elo** avec professeur Scan ;
  la boucle externe a atteint environ **+52 Elo** et convergé.
- Le bake `gen2-mmto` a déplacé la cellule d9 contre Scan de −310 à −276
  (**+34**) et le match généraliste contre gen1 de **+52 Elo** à mt0.3, tout en
  gardant la jauge dilf neutre.
- Le gain d9 ne s'est transféré que de +5–6 Elo au movetime contre Scan :
  nouvelle référence environ mt0.3 −155, mt1.0 −128, NPS-comp −129.
  **⚠️ Ces chiffres sont des planchers contaminés, pas des valeurs** (constaté
  le 27 juillet 2026, `home-1001`). Ils ont été mesurés sur un moteur dont
  `search()` rendait un coup nul sur toute racine nulle par répétition ou par
  horloge de 50 plies ; le client HUB lisait ce coup nul comme un abandon, et
  Jass perdait donc toute partie atteignant une telle position. Le défaut est
  asymétrique — Scan ne fait rien de tel — et corrigé depuis (`9c1d1e8e`). Sur
  le moteur réparé, `gen2-mmto` mesure `−255 Elo` à `mt0.3` sur un pool réduit,
  intervalle de confiance `[−459 ; −140]` : compatible avec l'ancre, mais
  celle-ci ne doit plus être citée comme référence de campagne.
- Une deuxième ronde MMTO working-set ON a régressé de **−354/−341 Elo**.
  WS-OFF l'a ramenée au neutre mais sans gain : le levier a plafonné.
- Refaire une base WDL fraîche puis MMTO a perdu −33 à −61 Elo. Un fine-tune
  WDL ancré directement sur gen2-mmto a perdu −36 à −76 Elo malgré une baisse
  de log-loss. `gen2-mmto` reste le point de comparaison historique.

### 3.5 Auto-apprentissage autonome et conversion (`0650` à `0777`)

- Les tentatives antérieures ne constituent pas une longue lignée pure menée à
  terme : `0481`/`0482` ont échoué, `0532` mélangeait 4,16 M positions de
  maîtres, et `0536` a échoué pendant G1. Elles ne ferment donc pas la question
  aujourd'hui portée par L3-PURE.
- La chaîne mobile autour de `gen2-mmto` (`0650`–`0656`) est restée sous le
  champion : tendance teacher d8/d3 −100, d12/d6 −65, d14/d8 −55. Réenseigner
  un modèle Scan-tuné avec un professeur Jass plus faible ne le dépasse pas.
- Les DOEs search `0652`, `0657` et `0697` sont restés neutres ou négatifs à
  haut N. Le lead aspiration +17 du screen était du bruit.
- Une vraie lignée from-scratch (`0674`) a décollé : G1 a écrasé l'éval zéro et
  T2 a composé **+170 Elo**. T3 et T4 ont ensuite régressé. Ce résultat prouve
  qu'une boucle autonome peut apprendre, pas qu'elle sait convertir ni qu'elle
  a atteint son plafond.
- L'expérience PC Blues a confirmé le trou de conversion : **0,136 Jass vs
  0,904 Scan** sur 224 combinaisons. Fitter les préférences humaines a pourtant
  perdu **−135 Elo** (`0691`) ; injecter les positions en self-play a été neutre
  ou négatif (`0696`). Le corpus vaut comme thermomètre et QA, pas comme fit
  d'évaluation dans les recettes testées.
- Le DOE `0726` a trouvé environ 0,663–0,673 de conversion dans les quatre
  cellules. Les labels d14+EGDB ont une direction positive sur la force, mais
  le gymnase G4 n'a pas augmenté la conversion. `ADJ+G1` a été retenu pour la
  sonde, sans prétendre à un gain établi.
- La chaîne `ccx33` T1-bis→T3 a été techniquement complète et non régressive,
  mais plate : conversion **0,667 / 0,657 / 0,669** et rates contre T0
  **0,5125 / 0,490 / 0,5033**. Les IC de chaque match recouvrent 0,5.
- Fork C (`cpx62-0774`) : départ 0,3×, refit vs fort **−32,5 Elo** avec
  `ci_high=0,4932`, conversion hard **−0,0111**, malgré une divergence de
  politique 5,5→13,7 %. Verdict `stop_regression`.
- Teacher causal `0777` : B1 −0,010, B2 +0,007, B3 −0,019 contre A sur la
  hard-conversion, tous sous le seuil +0,02. Verdict `complete_no_signal` ;
  aucune confirmation P3 n'a été autorisée.
- **Track parallèle gen2-mmto « tête de conversion P3 » (0811–0822), clos
  négatif.** Deux mécanismes distincts testés sur le champion gelé, tous deux
  morts : (1) **tête statique CVH1** — sidecar `.cvh` bornée, P3-gated ; offline
  +0,016, screen `0813` +0,022 (n=180) prometteur, mais confirmation haut-N
  `0815` A 0,478 vs C10 0,490 → Δ **+0,012 (n=1255) < +0,020**, IC apparié
  recouvrant 0 → `better_fit_no_play_signal` (un meilleur fit offline ne se joue
  pas) ; (2) **décisions-sibling P3** — autopsie D0 `0822`
  `no_actionable_sibling_signal` (recovery 37,4 % < 50 %, Δ pairé +0,035 IC
  [−0,022 ; +0,093], n=339). La correction P3 sur gen2, statique **ou** par
  re-décision, ne déplace pas la conversion jouée. Ce track n'a jamais modifié
  L3 et est refermé.
- C0 L3-PURE `0790/0791` : les deux bras ont terminé G1–G3 avec rc=0 et
  publié modèles, corpus, sidecars, splits et manifests ; B a aussi publié les
  frontières G1/G2. C'est un succès d'exécution, pas encore un verdict.
- Le job haut-N `0792` a échoué avec rc=1 sur `not enough fixed openings`
  (750 requis vs 305 dans `data/dilf_combinations.fen`), avant de produire les
  gates. Relancé à l'identique en `0795` (NOPEN=300, assert de gate dynamique
  `n=2·NOPEN`, gauge et critères §7 inchangés). **Verdict C0 :
  `retire_frontier_v1_flat`** — conversion B−A globale −0,023, P3 mince −0,070,
  toutes IC recouvrant 0 ; gate généraliste B vs A 0,555 (pas de régression) ;
  A vs `gen2-mmto` 0,497 (parité), B vs `gen2-mmto` 0,470. Holdout log-loss
  A 0,451 / B 0,435. La frontière mobile v1 est un levier mort ; la lignée pure
  reproduit le plateau (~0,67) tout en atteignant la parité avec le champion.
- **Matrice causale TOP3 stable `0908/0920` :** 2 688 parties sur 384 positions
  +2 communes, d10. Le gate strict 0908 reste échoué sur un unique cap 400
  plies ; 0920 l’a adjugé nul sans replay et a publié une sensibilité W/L.
  G4/G4 vaut 270/1/113 (70,31 % W), mais le contraste apparié d’attaque
  `G4/G0 − G0/G0` est massivement négatif : −0,6875, IC95
  [−0,8021 ; −0,5677]. L’effet joint vaut −0,3724, IC95
  [−0,4818 ; −0,2656]. Scan domine G4 en attaque (+0,5911) comme en défense
  (+1,3724), IC95 entièrement positifs. Le plateau n’est donc pas une
  conversion apprise mais cachée par l’agrégat : G4 a causalement dégradé le
  rôle attaquant sur ce domaine.
- **Miroir causal L3-PURE `0921` :** protocole identique, 2 688/2 688 parties,
  zéro erreur et zéro cap, avec le G4 pur de `0842`. G4/G0 vaut 374/0/10 et
  l’effet d’attaque est positif : +0,1667, IC95 [+0,0990 ; +0,2344]. G0/G4
  vaut 202/0/182 et l’effet de défense est +0,7292, IC95
  [+0,6146 ; +0,8438]. G4/G4 reste proche de G0/G0 parce que les deux rôles
  progressent simultanément. Le self-play WDL et l’architecture linéaire
  savent donc apprendre la conversion ; la destruction du rôle attaquant est
  localisée à la recette spécialiste 0890bis.
- **Autopsie recette 0842/0890bis :**
  `TOP3_SPECIALIST_RECIPE_FAILURE_LOCALIZED_FACTORS_CONFOUNDED`. Architecture,
  recherche, bootstrap, exploration, fit et labels sont identiques. Le bundle
  0890bis change simultanément les départs TOP3, le volume 500 k→2 M et le
  reweighting `1/2/4`. En G4, 72,59 % de son corpus réel a ≤14 pièces et
  seulement 5,765 % du fit pré-resampling reste dans le domaine exact ±2
  hommes/dames égales (8,038 % après resampling). Les matrices brutes sont
  appariées sur 2 688/2 688 lignes ; remplacer seulement le G4 spécialiste par
  le G4 pur améliore 171 positions contre 7 régressions en attaque vs G0, et
  171 contre 17 en défense. 0890bis reste fermé ; seule une ablation `2 × 2`
  départ standard/TOP3 × reweighting off/on, à volume identique, peut attribuer
  la cause fine.
- **Maturité F2M/M2 `0964→0974bis` :** F2M est confirmé puis promu humainement
  champion L3-PURE et général ; il bat Gen2 à 57,25 % Q00 et 58,60 % native.
  Une continuation M2 d8 sur 2M positions fraîches est plate contre F2M
  (50,60/49,05 %). Les bras appariés d10 et d12 ne créent aucune pente :
  d10 fait 48,80/51,00 %, d12 45,85/46,95 %. À d12, la régression Q00 est
  établie (−28,9 Elo) alors que la loss holdout s'améliore. L'escalade de
  profondeur fraîche est donc close ; le mix d10/d12 reste interdit par son
  garde-fou strict. Le facteur actif suivant est le turnover temporel 1:1 à
  volume constant, pas davantage de profondeur.
- **Turnover temporel `0977→0980` :** à parent, d8, 8cf et volume 2M constants,
  remplacer 1M positions M2 par 1M positions de l'époque F2M produit quatre
  estimations positives : 52,20/51,05 % contre M2 et 52,10/51,15 % contre F2M
  en Q00/native. Conversion P3/P4 : 98/99 % ; couverture : 210 381 buckets
  visités et 28 160 vus au moins 100 fois, au-dessus des deux contrôles.
  La confirmation indépendante `0980` établit ensuite la supériorité sur M2 :
  53,775 % Q00 (+26,28 Elo) et 53,20 % native (+22,27 Elo), avec les deux bornes
  basses à 95 % au-dessus de 50 %. Le cumul atteint 53,25/52,483 % sur 3 000
  parties par cellule. Face à F2M, 50,35/50,90 % reste compatible avec
  l'équivalence : TURNOVER n'est pas un nouveau champion. La mémoire temporelle
  est néanmoins un levier causal confirmé ; le facteur suivant préenregistré
  est REPLAY25, 500k positions époque F2M + 1,5M époque M2 à volume constant.
- **REPLAY25 `0981→0983` :** le préflight autoritatif `0981ter` certifie le mix
  25/75, son split par ouverture et le pool indépendant. `0982` converge
  réellement en 156 itérations sur 2M records (`gradient_inf_norm=0,0008835`,
  loss holdout 0,444145) et publie le modèle `289047ff…`, sans promotion.
  `0983` est le readout indépendant réservé contre M2, TURNOVER, F2M et Gen2.
- **REPLAY25 clos par `0983` :** sur 1 000 parties indépendantes par cellule,
  REPLAY25 marque 51,25/53,90 % contre M2 en Q00/native, mais 46,90/49,00 %
  contre TURNOVER 50/50. La régression Q00 face à TURNOVER est établie
  (IC95 `[43,83 ; 49,97]`) et le modèle reste plat face à F2M (50,05/49,65 %).
  Le dosage 25/75 améliore donc le corpus 100 % frais sans rejoindre le 50/50 :
  **la dose de replay est close, aucune promotion.**
- **Écran L2 `0984→0986` :** à corpus, parent, split, recherche et objectif
  constants, `0984bis` certifie le corpus TURNOVER et un pool indépendant de
  500 ouvertures (`e7b89a5e…`), puis `0985` fitte réellement `L2=1e-5`
  (375 itérations, loss holdout 0,444361, `27cf9bed…`) et `L2=1e-4`
  (170 itérations, loss holdout 0,446187, `0b710b80…`) face au contrôle
  immuable `L2=3e-5` (loss holdout 0,444060, `b2c79b36…`). Les losses sont des
  diagnostics ; seul le readout `0986` décide, et un lead confirmé ne
  promeut rien — il n'autorise que le croisement replay `0/25 %`.
- **Écran L2 tranché par `0987` :** `home-0986` étant tombé sur un bug de
  harnais (témoin de garde appliqué au défenseur figé), la relance `0987`
  conclut `TURNOVER_L2_SCREEN_DIRECTIONAL_CONFIRMATION_REVIEW`.
  **`L2=1e-4` est rejeté** : 47,45 % Q00 et 46,40 % natif contre le contrôle,
  régression native établie (IC95 `[43,33 ; 49,47]`). **`L2=1e-5` est
  directionnel** : 50,15 % Q00 et 51,45 % natif, quatre estimations positives
  mais aucune borne basse au-dessus de 50 %. Ses gardes sont saines
  (52,60/51,60 % contre F2M, 60,80/58,05 % contre Gen2, conversion P3/P4
  appariée au contrôle). **`L2=3e-5` reste donc le réglage retenu** tant qu'une
  confirmation indépendante de `1e-5` n'a pas eu lieu ; le croisement replay
  `0/25 %` reste fermé et aucune promotion n'est autorisée.
- **Facteur L2 clos par `0988→0989` :** la confirmation indépendante de
  `L2_1E5` sur un pool neuf (`71dc575e…`, 1 000 ouvertures, recouvrement nul
  sur treize pools dont celui de l'écran) conclut
  `L2_1E5_DIRECTION_NOT_REPLICATED_RETAIN_3E5`. **Les deux vues s'inversent** à
  modèle identique : la Q00 passe de 50,15 % à 53,02 % (supériorité établie) et
  la native de 51,45 % à 49,68 %. La règle exigeant les deux vues sur le frais
  et sur le cumul, **`L2=3e-5` est retenu et le facteur L2 est clos**. La Q00
  étant déterministe à profondeur fixe, son écart de 2,87 pp entre deux pools
  mesure la variance d'échantillonnage : **à `n=1000`, une lecture mono-vue de
  l'ordre de `±10 Elo` ne porte pas de décision** — c'est le repère
  méthodologique le plus réutilisable de la campagne. Hors question causale,
  `L2_1E5` domine F2M dans les deux vues sur le cumul de 3 000 parties
  (52,42 % et 52,63 %) ; les cellules F2M sont des garde-fous, pas un test de
  promotion, et le candidat comme son contrôle dominent leur parent commun.
  Le croisement replay `0/25 %` au L2 retenu est le prochain bras à
  préenregistrer.
- **Axe de dose replay clos par `0991→0993` :** le croisement `{0 ; 25 %}` du
  plan était déjà mesuré à `L2=3e-5` ; l'axe n'était vierge qu'au-delà de 50 %.
  Le bras `REPLAY75` (1,5M époque F2M + 0,5M époque M2) **régresse contre la
  dose 50 %** : `47,77 %`, IC95 `[46,39 ; 49,15]` sur `n=5000`. La courbe monte
  de 0 à 50 % puis redescend : **l'optimum est intérieur, à 50 %**. `REPLAY75`
  avait pourtant la meilleure loss holdout des quatre doses — il converge en
  6 itérations en ré-apprenant les données de son parent et n'est pas
  distinguable de F2M (`50,11 %`).
- **`TURNOVER` dépasse le champion F2M :** premier bras `L3-PURE` à établir sa
  supériorité sur le champion en titre, dans une cellule préenregistrée et
  dimensionnée pour cela — `51,98 %`, `+13,77 Elo`, IC95 `[50,61 ; 53,35]` sur
  `n=5000` à vues additionnées. Les six mesures indépendantes du couple, sur
  trois pools disjoints, se consolident à `51,42 %`, `+9,89 Elo`, IC95
  `[50,50 ; 52,35]` sur 11 000 parties. `home-0980` n'avait rien conclu faute de
  puissance, pas faute de signal. **Aucune promotion n'est autorisée** : une
  succession de champion exige une revue humaine et les cellules non jouées ici
  (garde Gen2, conversion P3/P4, couverture, pool supplémentaire).
- **TOPK3 ne remplace pas TURNOVER (`home-1040`) :** sur le gate complet,
  frais et disjoint, TOPK3 fait `4496-449-5055` sur 10 000 parties, soit
  `47,205 %` et `-19,44 Elo`. Q00 (`47,16 %`) et natif (`47,25 %`) régressent
  séparément à IC90. TOPK3 reste supérieur à Gen2 (`57,8667 %`, `+55,12 Elo`)
  mais moins que TURNOVER sur cette garde (`59,7667 %`, `+68,75 Elo`).
  Conversion corrigée : P3 `0,763333`/`0,763333`, P4
  `0,743333`/`0,760000` (TOPK3/TURNOVER). Verdict :
  `TOPK3_PROMOTION_NOT_RECOMMENDED_POINT_ESTIMATE`; **TURNOVER reste
  champion**. Le protocole signal passe donc au préflight hard-replay
  UNIFORM, un seul facteur causal.
- **Le hard-replay 1 M est fermé par capacité (`home-1042`) :** sur les 2 M
  records UNIFORM authentifiés, 325 233 portent le signal
  `failed_conversion`, mais il ne reste que 29 454 positions canoniques après
  `one-per-game` et déduplication, soit **58 908 records** avec miroir couleur.
  La dose préenregistrée de 1 M n'est donc pas disponible :
  `L3_PURE_HARD_REPLAY_CATALOGUE_INSUFFICIENT`,
  `training_authorized=false`. Aucun fit n'est lancé et la dose n'est pas
  réduite post-hoc.
- **Le replay `failed_conversion` 50/50 régresse fortement (`1068→1076`) :**
  après réouverture sur une source UNIFORM 40 M, `HARD_REPLAY` fait
  `222-24-9754` contre `UNIFORM_REPLAY` sur 10 000 parties fraîches et
  appariées, soit `2,34 %` et `-648,20 Elo`. Q00 et natif régressent
  séparément. Les optimiseurs convergent et les modèles sont authentifiés ;
  le bras hard outcome-conditioned déplace le prior WDL assemblé à
  51,29 % wins contre 31,52 % losses STM, soit 19,77 points d'asymétrie,
  contre 0,37 point pour UNIFORM. La couverture augmente pourtant de
  194 334 à 210 436 buckets. Verdict
  `L3_PURE_HARD_REPLAY_BELOW_UNIFORM_REPLAY` : la recette brute avec cibles
  historiques conservées est close. La suite est le reverse self-play
  zero-target apparié, qui régénère les WDL terminales.

Sources récentes : [codex_review_v3_2.md](archives/codex_review_v3_2.md),
[post_ccx33_execution_20260717.md](archives/post_ccx33_execution_20260717.md),
[forkc_c0_verdict_20260717.md](archives/forkc_c0_verdict_20260717.md) et
[CURRENT.md](archives/CURRENT.md).

## 4. Résultats de référence à ne pas perdre

### 4.1 Champion et thermomètres historiques

| Objet | Valeur consolidée | Usage futur |
|---|---|---|
| `gen2-mmto` | +52 Elo vs gen1 mt0.3 ; d9-vs-Scan +34 | référence fixe externe, jamais professeur de L3 |
| écart gen2-mmto vs Scan | environ −155 mt0.3 / −128 mt1.0, **plancher contaminé par le coup nul (cf §3.4)** | thermomètre absolu, pas cible de fit |
| PC Blues 224 | Jass 0,136 vs Scan 0,904 | thermomètre tactique figé |
| T3 `ccx33` | conversion globale 0,669 | référence de conversion historique |
| T3 P1/P2/P3/P4 | 0,841 / 0,609 / 0,489 / 0,513 | diagnostic par strate |
| `conv_self` ancien | gen2 environ 0,62 | preuve historique du déficit de réalisation |

Ces chiffres appartiennent à des harness et distributions différents. Ils ne
doivent pas être comparés comme une même probabilité absolue. Seules les
différences au sein d'un protocole apparié portent une causalité.

### 4.2 Gains réellement retenus

| Levier | Signal | Statut |
|---|---:|---|
| `--score-drop` des labels extrêmes | MSE 38→1,8 ; gros gain vs handcrafted | acquis fit |
| capture pre-filter + SIMD | +40,7 % NPS sur v15 | acquis perf |
| protection NMP / améliorations search | gains multiples, environ +187 cumulés selon l'ancien CURRENT | acquis historique, non additif au chiffre près |
| history probabiliste pure | +20 à +43 Elo haut-N | baké |
| optimisations eval 2026-07 | +13–15 %, puis +4,8–9,9 % NPS selon phase | bakées, byte-identiques |
| MMTO à travers recherche | jusqu'à +52 Elo vs gen1 ; +34 d9-vs-Scan | bake `gen2-mmto` |
| EGDB mix exact | +58 Elo dans `0454`, finale améliorée | preuve qu'une vérité exacte peut aider ; recette historique |

## 5. Portes closes à protocole causal identique

Les lignes suivantes interdisent la répétition à l'identique. Les paramètres
marqués co-adaptatifs peuvent être revus une fois dans le DoE L3 décrit au
§1.1 ; le résultat L3 deviendra alors le nouveau verdict de référence.

### 5.1 Modèle et représentation

| Porte | Preuve principale | Pourquoi elle est close | Condition minimale de réouverture |
|---|---|---|---|
| plus gros MLP/NNUE historique | v9/v11 overfit ; v11 0,009 vs Scan | capacité seule sans nouvelle méthode ne paie pas | nouvelle cible et protocole, après décision explicite de changer de classe |
| NNUE maintenant | décision JFC | hors périmètre tant que L3 linéaire n'est pas exécutée | preuve de plafond L3 + go explicite |
| pattern standalone sans squelette | 0118–0127 | s'effondre ; hybride seul viable | nouvelle représentation complète, pas un nouveau seed |
| enrichir la géométrie à petit volume ou en cours de lignée | 54 patterns <32 ; 32cf affamée à petit N, mais gagnante dans d'autres gates au scale | changement prématuré confond capacité et couverture | fork 8cf/32cf depuis G0 après seuil de visites publié et budget d'optimisation apparié |
| passer à 32cf sur la lignée L3 courante (précondition §6.4 mesurée) | visites/bucket publiées : `0828` 300k → coverage 8cf **5,9 %** ; `0832` cumulatif 1,5M (5 cellules X1) → **9,0 %**, croissance **sous-linéaire** (5× données → 1,5× couverture), ge_100 = 1,0 %, Gini 0,85 | 8cf est **data-limité, pas capacité-limité** : la lignée ne remplit pas sa géométrie actuelle ; 32cf (4× buckets) tomberait à ~2-3 % de couverture → encore plus affamé. Précondition visites+volume **mesurée et NON franchie** → **32cf NO-GO** | un curriculum/volume qui remplit réellement 8cf d'abord (mécanisme causalement différent), puis re-mesure des visites |
| élaguer les patterns | −31 Elo, zéro vitesse | lose-lose | nouveau hot-path mesuré, pas une intuition mémoire |
| king-aware par défaut | gate final `0409` en faveur de men-only | gain ancien non transféré au régime scale | A/B au scale sur recette L3 figée, dans un fork séparé |

### 5.2 Données, labels et objectifs

| Porte | Preuve principale | Pourquoi elle est close | Condition minimale de réouverture |
|---|---|---|---|
| plus de volume brut | couverture saturée ; multiples runs plats. **Rouverte puis refermée par `1004`→`1008` (28 juillet 2026)** : la condition de réouverture a été honorée — couverture pré-enregistrée mesurée sur 12 M records, `13,548 %` de buckets contre `9,8 %`, **41,67 observations par paramètre libre contre 4,3**, Gini `0,91`, fit convergé, holdout `0,440449` contre `0,444060`. Force jouée contre TURNOVER, pool neuf de 1500 ouvertures, vues additionnées : **`0,4785`, `−14,95 Elo`, IC95 `[−23,5 ; −6,4]`, `n = 6000`** (`q00` `1360-142-1498` ; `native` `1352-176-1472`). L'IC exclut zéro | le volume achète la couverture et la densité, **pas la force** — et ici il la fait perdre. ⚠️ **Le run ne l'établit pas proprement** : VOL8M s'écarte de la recette TURNOVER sur quatre facteurs (volume `12 M`/`2 M`, frais/mémoire `67/33`/`50/50`, jeu `d9`/`d8`, et l'étiquetage de la moitié mémoire — cf §5.2 bis). Le confond n'est PAS celui que cette ligne affirmait au premier jet : VOL8M est à 67 % post-correctif quand TURNOVER est à 100 % pré-correctif, donc VOL8M a *moins* du défaut. Ce qui reste est un mélange de deux calibrations de nulles incompatibles | **12 M entièrement post-correctif** ; à volume égal et calibration homogène, rien d'autre ne change |
| phase-weight | −210 Elo sur bons labels | décalibre le jeu global | nouvelle loss normalisée avec preuve mathématique et A/B isolé |
| label-depth par phase en WDL | no-op sur la cible, TT polluée, −80 | mauvais canal | cible score explicitement utilisée et TT séparée |
| hygiène `drop-post-eps` comme cure | bundle de fixes −25 Elo | le WDL joué est un vrai retour MC ; « contamination » mal interprétée | preuve directe de biais, pas simple présence d'epsilon |
| distillation score-recherche Scan | loss 8× ; 0526 pire | une feuille statique ne représente pas une recherche | objectif through-search correctement défini |
| distillation statique Scan pour la conversion | 0525 ≈ baseline | ne ferme pas le trou aval | nouveau mécanisme de recherche/trajectoire |
| rank-loss statique | jusqu'à −847 Elo | pairwise↑ mais calibration détruite | objectif through-search ou valeur absolue jointe |
| MMTO conversion sur gen2 | WS-ON −354 ; WS-OFF neutre | plateau autour du champion | nouveau professeur plus informatif et gate indépendant ; interdit dans L3-PURE |
| WDL fine-tune de gen2 | −36 à −76 malgré log-loss↓ | optimum de jeu déplacé | nouveau point de départ et protocole, pas re-fit gen2 |
| PC Blues prefs/seed fit | −135 ; seed neutre/négatif | QA riche, mais mauvais canal d'éval | usage comme thermomètre/recherche, pas fit identique |
| G4/gymnase fixe | `0726` conversion −0,009 à −0,010 | répétition statique ne convertit pas | curriculum mobile réellement différent, testé par C0 |
| teacher causal B1/B2/B3 v1 | 0777 sous +0,02 | aucun signal | nouvelle information causale ou nouveau canal, pas plus de N sur mêmes cellules |
| dose/calendrier d'exploration (écran C2-X1) | verdict `0824` (`l3_x1_verdict.py`, 5 cellules, n appariés 860, bootstrap 10 000) : effets A −0,002 / B +0,002 / C +0,001 / courbure +0,004, tous IC franchissant 0 ; aucun coin Δconv ≥ +0,02 ; gates ≈ 0,5 | `x1_no_lead` — plies d'ouverture, epsilon et décroissance ne déplacent pas la conversion ; plateau ~0,67 | nouveau facteur de trajectoire causalement différent, ou signal sur une lignée plus mûre |
| tête de conversion statique P3 gen2 (CVH1) | offline +0,016 ; screen `0813` +0,022 (n=180) prometteur ; confirmation haut-N `0815` A 0,478 vs C10 0,490 → **Δ +0,012 (n=1255) < +0,020** ; bootstrap apparié IC recouvrant 0 | `not_confirmed_flat` / `better_fit_no_play_signal` — un meilleur fit offline de la correction ne se traduit pas en conversion jouée ; le head statique gelé sur gen2 est un levier mort | canal de correction P3 non-statique (décision réelle), nouveau gate indépendant |
| décisions-sibling P3 gen2 (autopsie D0) | `0822` `no_actionable_sibling_signal` : recovery 37,4 % < 50 %, Δ pairé +0,035 IC [−0,022 ; +0,093] straddle 0, n=339 | rejouer un meilleur sibling au leader P3 ne récupère pas assez de failures ; cohérent avec l'échec du head statique CVH1 (`better_fit_no_play_signal`) | mécanisme de décision P3 causalement différent, gate indépendant |

### 5.2 bis Défaut d'étiquetage pré-`9c1d1e8e` — les nulles supprimées du corpus

Avant `9c1d1e8e` (27 juillet 2026, 16h10 FR), `search()` renvoyait un coup
**nul** dès que la racine répétait une position déjà jouée. En self-play
`--gen-data-wdl`, `Engine::apply_move` rejette ce coup, la boucle de jeu casse,
`hit_ply_cap` reste vrai, et `--drop-plycap` — actif dans toute la chaîne
L3-PURE — jette la **partie entière**. Les répétitions naissent dans les
positions de manœuvre : ce sont donc les **nulles** qui disparaissaient.

Mesuré en rejouant le binaire pré-fix contre le post-fix, mêmes graine, parent,
profondeur `d8` et options, 3000 records, `--drop-plycap` :

| | défaites | **nulles** | victoires |
|---|---:|---:|---:|
| moteur cassé | 47,8 % | **4,8 %** | 47,4 % |
| moteur réparé | 39,5 % | **20,3 %** | 40,2 % |

Facteur **4,2** sur les nulles ; le corpus cassé est décisif à 97,6 %. L'effet
est invisible dans tous les compteurs publiés à l'époque.

**Corpus touchés** — tout ce qui a été généré avant le 27 juillet 16h10 FR :
`M1` (`home-0944`), `M2` (`home-0966bis`), et **TURNOVER lui-même**
(`home-0977`, `new_generation_performed=false`, corpus = 1 M `fresh_m2` + 1 M
`parent_f2m`). Le champion courant est donc entraîné à 100 % sur des données
d'où les nulles avaient été filtrées. VOL8M, à 67 % post-correctif, en a
**moins** — c'est l'inverse de ce qui avait été écrit le 28 juillet au premier
jet, et la correction vaut rectification de la ligne « plus de volume brut ».

**Ce que le défaut n'est pas** : il ne mislabellise rien. Les parties gardées
portent l'étiquette juste ; ce sont des parties entières qui manquent. C'est un
biais de **sélection**, pas d'étiquetage — d'où l'absence totale de signal dans
les contrôles d'étiquetage existants.

**Garde anti-récidive** : `jobs/tools/assert_corpus_wdl.py` refuse un corpus
dont la part de nulles sort de `[0,10 ; 0,60]` ou dont victoires et défaites
s'écartent de plus de 10 points. Elle porte sur les **données**, pas sur le
code, donc elle attrape aussi la prochaine cause inconnue produisant le même
symptôme. Validée sur les deux corpus réels : rejet du cassé (`rc=6`), acceptation
du réparé. Les gardes `grep root_is_drawn` ne couvraient que 2 des 23 templates
appelant `--gen-data-wdl`, et n'auraient de toute façon vu qu'une cause connue.

### 5.3 Recherche

| Porte | Preuve principale | Pourquoi elle est close | Condition minimale de réouverture |
|---|---|---|---|
| forcing extensions au jeu | fixed-depth positif, movetime neutre puis −74/−217 | brûle le budget nœuds | gain NPS structurel rendant le coût négligeable, puis haut-N |
| quiescence forcing plus profonde | −92 à −231 selon variante | profondeur perdue > précision gagnée | Q2 non déclenché après Q1 plat ; réouverture seulement sur signal d'une lignée plus mûre |
| menace × sacrifices sélectifs (écran C1-Q1) | verdict contract-grade `0812` (63 clés, bootstrap apparié, common+native) : effets menace +0,001 / sacs −0,004 / interaction +0,011, tous IC franchissant 0 ; aucun Δconversion ≥ +0,02 ; gates ≈ 0,5 | `q1_no_lead` — aucun effet sur conversion ni force dans la lignée pure | mécanisme de recherche co-adaptatif hors quiescence, ou signal sur une lignée plus mûre |
| LMR/NMP/ProbCut/LMP/aspiration OAT | 0657 haut-N neutre ; 0697 pcm100 −19 | knobs locaux épuisés dans ce régime | une ablation native L3 après profil d'activation ; pas un autre sweep fin de marges |
| offer-no-reduce | détection Jass≈Scan, conversion très différente | attaque la détection, qui n'est pas le goulot | nouvelle mesure montrant un déficit de détection |
| géométrie pour l'ordering | first-move cutoff ~0,91 | ordering déjà bon ; history prob a capté le gain restant | régression mesurée du node-EBF sur un nouveau moteur |

### 5.4 Conversion et lignées

| Porte | Preuve principale | Pourquoi elle est close | Condition minimale de réouverture |
|---|---|---|---|
| ADJ+G1 multi-tours identique | T1/T2/T3 0,667/0,657/0,669 | aucune composition | recette causalement différente |
| fork C départ 0,3× | −32,5 Elo, conv −0,011 | divergence sans progrès | autre mécanisme qu'un simple scaling du départ |
| anchor plus serré | 0716/0719 : vallée réelle, pas bug | fige ou décalibre l'apprentissage | protocole sans anchor — précisément L3-PURE |
| prédicats statiques de verdict | P1 85,01 % exact ; P2 sous-puissant/faux positifs | loin des 99,9 % requis | preuve exacte ou oracle de règle |
| TB exceptions dans l'éval | B4 finale +1 Elo neutre | corpus exact ne transfère pas via ce fit | autre objectif ou représentation, fork séparé |
| chaîne autour de gen2-mmto | 0650–0656 asymptote négative | professeur interne plus faible que le point Scan-tuné | lignée indépendante ne partant pas de gen2 |
| frontière mobile v1 (25 % seeds G2/G3) | C0 `0795` : Δconv global −0,023, P3 −0,070, IC recouvrant 0 ; B vs A 0,555 | pas de gain de conversion à budget apparié | autre mécanisme de curriculum que le re-seed de frontière matérielle |
| continuation fraîche F2M, d8→d10→d12 à 2M | `0970bis` 50,60/49,05 %, `0972` 48,80/51,00 %, `0974bis` 45,85/46,95 % contre F2M Q00/native ; d12 Q00 −28,9 Elo établi malgré loss 0,427862 | plus de profondeur sur 2M frais n'améliore pas la force et finit par rétrécir la distribution | changer un seul facteur de distribution/mémoire à volume et d8 constants |
| pondération role-aware V2 vs globale V1 (imbalance2, @P1 d8) | `0853`→`0857` : pools communs A64/B64 (n=1151/1152, seed 161803, boot 10 k), ΔV2−V1 = −0,013 < 0,02, IC apparié [−0,061 ; +0,035] straddle 0 → `V2_NO_CLEAR_LEAD_AT_P1` ; les deux `STILL_IMPROVING_OR_UNSTABLE` | pas de lead **mesuré** à P1 ; **non close** — V2 retenue (crédit défensif explicite, sémantiquement préférable, décision JFC 20/07) et escaladée P2 | séparation ou plateau V1/V2 en profondeur P2-P4 (d10→d14) — escalade en cours |

## 6. Résultats supersédés ou invalides

| Ancienne lecture | Correction définitive |
|---|---|
| « 0,870 / +331 vs Scan-d10 » | invalide : bug de buffer et forfaits Scan sur coups illégaux |
| « corrélation eval Scan ≈0,04 » | faux alignement par indice ; join bitboards donne Jass-oracle 0,952 |
| « tb-relabel +18 Elo en 0587 » | phantom : compteur `tb_relabel=0`; le mécanisme n'avait pas tiré |
| « EGDB ne marche pas » | mauvais chemin ; `/root/egdb_extracted/app` résout correctement en post-gen |
| « label hygiene corrige 85 % de contamination » | mauvaise notion : l'issue jouée reste un retour MC ; bundle −25 Elo |
| « history probabiliste neutre » | screen `0599` sous-résolu ; `0600` haut-N +20 à +43, baké |
| « ext_forcing est un gain search » | vrai à profondeur fixe, faux au movetime ; coût en nœuds dominant |
| « training loss/pairwise accuracy suffit » | réfuté par rank statique −847, PC Blues −135 et WS-ON −354 |
| « T1 promote implique une lignée gagnante » | régime jeune = non-régression seulement ; T1→T3 est plat |
| « divergence de politique implique apprentissage » | fork C diverge 13,7 % mais perd en force et conversion |
| « #350 épingle toute la recherche C0 » | faux : 5 clés de quiescence explicites, 58 valeurs encore héritées de `SearchParams{}` |
| « la profondeur de label est un no-op pur en WDL » | sa sortie score est ignorée, mais la recherche partage la TT avec le play et peut donc modifier la trajectoire |

## 7. Questions encore ouvertes

Une seule famille est active : `L3-PURE`.

1. C2-X1 : quelle distribution d'ouverture/epsilon/décroissance augmente la
   conversion, notamment P3, sans régression ? Le screen demi-factoriel à cinq
   cellules est pré-enregistré, pas encore exécuté.
2. Après X1, quel budget de jeu, rapport homme/dame, L2 et replay maximisent la
   conversion sans régression ? Ces facteurs restent séquencés, pas combinés
   dans un sweep unique.
3. Une recette confirmée compose-t-elle sur une rampe longue avec deux graines ?
4. Quand 8cf est nourrie, un fork 32cf depuis G0 apporte-t-il un résidu
   représentable supplémentaire ?
5. Comment traiter P4 matériel-égal sans oracle externe ? La piste réservée est
   un ensemble de rollouts internes stochastiques.

Ne sont pas des questions actives : « remettre du Scan », « refaire MMTO sur
gen2 », « resserrer l'anchor », « grossir G4 », changer de géométrie au milieu
d'une lignée, relancer Q2 sans nouveau signal ou refaire un sweep fin non
instrumenté des anciens knobs.

### 7.1 Exécutions incomplètes qui ne valent pas verdict

- L'audit MTC a été ignoré pendant T1-bis→T3 ; il reste une réserve sur cette
  ancienne campagne, pas une dépendance de L3-PURE.
- Une seconde tentative T3 a fini avec `exit_code=-1`. La première exécution
  complète reste le verdict scientifique ; la cause de la tentative perdue
  n'est pas un résultat de force.
- Le sparring-vs-Scan `0784` était annoncé en phase smoke dans l'ancien CURRENT,
  mais aucun résultat complet consolidé n'est inscrit ici. Il est donc
  **non testé/non conclu**, puis sorti du périmètre par la décision L3 sans
  professeur externe — pas présenté comme scientifiquement réfuté.
- Le rollout interne multi-échantillon pour P4 matériel-égal n'est pas encore
  implémenté.
- `0792` reste historiquement un échec technique sans verdict. Sa cause
  (`NOPEN=750` pour 305 ouvertures disponibles) a été corrigée sans changer
  les gates dans `0795`, qui fournit désormais le verdict C0 autoritaire.

## 8. Règles méthodologiques héritées

- juger la force au movetime ou avec un budget apparié ; la profondeur fixe est
  un diagnostic, pas un bake-decider ;
- utiliser un N dimensionné et publier les IC ; un point dans l'IC n'est pas
  un gain ;
- `n=0`, cellule manquante ou manifest incomplet = échec technique, jamais
  neutre ;
- séparer train, holdout et jauges par partie/ouverture ;
- ne jamais promouvoir sur loss, pairwise accuracy ou divergence seules —
  **quatre confirmations** que la loss holdout ne prédit pas la force (rank
  statique `−847`, PC Blues `−135`, WS-ON `−354`, et `1008` où VOL8M a la
  meilleure loss des deux et perd de `−15 Elo`), plus REPLAY75 qui avait la
  meilleure loss des quatre doses en étant le plus faible ;
- ne comparer deux losses holdout que si elles viennent du **même** holdout :
  celles de TURNOVER (`2 M`) et de VOL8M (`12 M`) portent sur des
  distributions différentes et ne se citent pas l'une contre l'autre ;
- un corpus qui change plusieurs facteurs à la fois ne peut pas clore l'axe
  qu'il prétend tester : `1008` mélange volume, ratio, profondeur et un
  étiquetage d'avant correctif moteur, donc son verdict nomme un facteur qu'il
  n'isole pas ;
- pinner code, inputs, référence fixe, seeds et **toutes** les clés de
  configuration par SHA ; un fingerprint partiel ne peut pas déclarer
  `inherited_defaults=false` ;
- supprimer ou isoler tout calcul dont la sortie est ignorée mais dont l'état
  mutable (TT, history, RNG) peut influencer la politique ;
- publier les compteurs qui prouvent qu'un flag a réellement agi ;
- micro-calibrer nproc, débit, disque et timeout sur chaque box ;
- écrire résultats/progress hors de l'arbre Git puis les publier explicitement ;
- garder Scan et Gen2 comme thermomètres externes de L3, jamais comme sources
  d'entraînement ;
- un résultat plat est informatif ; il ne justifie pas d'ajuster le seuil après
  lecture ni d'enchaîner automatiquement un job plus gros.

## 9. Infrastructure et provenance durable

Les runners v3 à v5, `jass-control` et R2 sont les sources d'exécution. Les incidents
suivants ont déjà coûté des runs et ne doivent pas réapparaître : cache EGDB
agrégé trop grand, moteurs morts suivis de `BrokenPipe`, `PrivateTmp` démonté,
glob de merge attrapant les logs, fichier RESULTS réinitialisé par Git, attente
du monitor en plus des shards, disque ccx33 plein, timeout sans `n_min`, et
publication R2 501 intermittente.

Le snapshot historique et la procédure de restauration sont décrits dans
[HISTORICAL_DATA_R2.md](archives/HISTORICAL_DATA_R2.md). Le journal complet et
l'ancien CURRENT restent disponibles pour l'audit, mais ne doivent plus être
mis à jour.

## 10. Index minimal des archives

| Besoin | Document archivé |
|---|---|
| chronologie détaillée 0001→0263 | [JOURNAL_DE_BORD.md](archives/JOURNAL_DE_BORD.md) |
| ancien registre exhaustif des verdicts | [CURRENT.md](archives/CURRENT.md) |
| méthode et écarts par rapport à Scan | [SCAN_METHODOLOGY_GAP.md](archives/SCAN_METHODOLOGY_GAP.md) |
| audit architecture Scan | [SCAN_ARCHITECTURE_NOTES.md](archives/SCAN_ARCHITECTURE_NOTES.md) |
| spec de la sonde T1-bis→T3 | [codex_review_v3_2.md](archives/codex_review_v3_2.md) |
| résultat fork C | [forkc_c0_verdict_20260717.md](archives/forkc_c0_verdict_20260717.md) |
| suite post-ccx33 | [post_ccx33_execution_20260717.md](archives/post_ccx33_execution_20260717.md) |
| plan historique de migration runner v3 | [RUNNER_V3_MIGRATION.md](archives/infra/RUNNER_V3_MIGRATION.md) |
| anciens jobs fork C + teacher | [README.md](archives/jobs/prepared/forkc-teacher-20260717/README.md) |
| anciens jobs post-ccx33 | [README.md](archives/jobs/prepared/post-ccx33-20260717/README.md) |
| ancienne spec L3 C0 | [L3_PURE_PLAN_C0_20260718.md](archives/l3/L3_PURE_PLAN_C0_20260718.md) |
| spec L3 v4.1 avant C2-X1 | [L3_PURE_PLAN_V4_1_20260718.md](archives/l3/L3_PURE_PLAN_V4_1_20260718.md) |
| ancien current L3 C0 en cours | [L3_CURRENT_C0_RUNNING_20260718.md](archives/l3/L3_CURRENT_C0_RUNNING_20260718.md) |
| ancien benchmark GitHub NNUE | [benchmark-nnue.yml](../archive/workflows/benchmark-nnue.yml) |
| boucle from-scratch historique | [MEMO_AUTO_SCRATCH.md](archives/MEMO_AUTO_SCRATCH.md) |
| chaîne itérative historique | [MEMO_CHAINE_ITERATIVE_LONGUE.md](archives/MEMO_CHAINE_ITERATIVE_LONGUE.md) |

Les détails techniques API, architecture, HUB, WASM et extension sont également
conservés sous `docs/archives/`. Ils décrivent l'état du code au moment de leur
rédaction et peuvent être périmés ; le code et les tests restent autoritaires.

Les cinq ZIP NNUE historiques (`2`, `3`, `4`, `5`, `7`) sont conservés sous
`archive/nnue-weights/` et aucun ZIP ne reste à la racine. Le workflow GitHub
qui consommait le ZIP `2` est lui aussi archivé : il mesurait seulement un
tournoi NNUE fixed-depth à très faible N, incompatible avec les gates movetime,
haut-N et manifests du programme actif. Les autres Markdown hors `docs/` sont
des points d'entrée du dépôt, des obligations de contribution/licence ou des
README attachés à un composant encore présent ; ils ne sont donc pas des
documents scientifiques actifs concurrents.
