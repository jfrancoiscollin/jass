# L3 — veille scientifique : Regret-Guided Search Distillation

**Date :** 22 août 2026  
**Statut :** revue de littérature et mémo d'hypothèses  
**Portée :** aucune expérience, promotion ou modification de champion n'est autorisée par ce document  
**Contexte interne :** [`L3_CURRENT.md`](../L3_CURRENT.md), [`L3_BACKLOG.md`](../L3_BACKLOG.md)

## 1. Conclusion exécutive

La prochaine percée de Jass ne viendra probablement pas d'une nouvelle interpolation scalaire du WDL appliquée aux mêmes positions.

Le registre scientifique converge déjà vers ce diagnostic : le volume brut, de nouvelles graines, plusieurs transformations post hoc du corpus, les pondérations temporelles et différentes familles de cibles ont peu ou pas déplacé la force. Par élimination, le levier encore ouvert est principalement **ce que le self-play joue**, la façon dont on identifie ses erreurs, et la supervision fournie aux décisions locales.

La « formule magique » la plus crédible issue de cette revue est une boucle en trois composantes :

1. détecter les positions où Jass prend une décision fragile ou incorrecte ;
2. les réanalyser avec un professeur de recherche plus coûteux ;
3. apprendre directement les préférences de cette recherche entre les coups légaux.

Nom de travail proposé :

> **Regret-Guided Search Distillation** — apprentissage guidé par le regret de recherche.

La boucle combinerait :

- une archive de positions à fort regret : changement du meilleur coup avec la profondeur, inversion WDL, PV instable, faible marge entre les meilleurs coups ;
- des redémarrages occasionnels de self-play depuis ces positions difficiles ;
- une recherche professeur donnant une valeur à plusieurs ou à tous les coups légaux ;
- une loss relative ou listwise qui apprend à classer les coups frères comme le professeur ;
- le WDL terminal conservé comme ancre globale ;
- une mémoire bayésienne structurée des générations précédentes ;
- l'incertitude utilisée pour choisir où chercher et quelles données produire, et non comme bonus arbitraire ajouté à l'évaluation.

Cette direction rassemble les idées de TDLeaf, DAgger, Expert Iteration, ChessBench, KataGo, Gumbel AlphaZero, l'active learning et les travaux 2026 sur le contrôle de recherche guidé par le regret.

**Recommandation principale :** lancer d'abord une instrumentation et un screen causal de la supervision de recherche, sans changer l'architecture PatternEval.

---

## 2. Diagnostic du blocage actuel

### 2.1 Une bonne moyenne globale n'est pas nécessairement une bonne décision locale

Le trainer de production reste essentiellement un modèle linéaire structuré optimisé par L-BFGS. Dans le cas WDL logistique, victoire, nulle et défaite sont ramenées respectivement à `1`, `0.5` et `0`, puis le score linéaire est entraîné par entropie croisée. Voir [`pattern_jass/tools/train.py`](../../pattern_jass/tools/train.py) et [`pattern_jass/tools/train_stream.py`](../../pattern_jass/tools/train_stream.py).

Cette loss estime correctement une forme d'espérance du résultat, mais toutes les erreurs n'ont pas la même importance pour un alpha–bêta. Pour gagner une partie, l'évaluation doit surtout :

- ordonner correctement deux ou trois variantes proches ;
- ne pas inverser le meilleur coup à la frontière de recherche ;
- reconnaître les positions où une petite différence statique masque une différence tactique ou de conversion importante ;
- produire des marges compatibles avec l'ordering, les fenêtres et les mécanismes de pruning ;
- être fiable dans les régions que la recherche sélectionne précisément parce qu'elles semblent favorables.

Une meilleure calibration globale peut donc ne rien acheter en Elo si elle ne corrige aucune décision marginale.

Supposons que la valeur estimée d'un coup soit :

\[
\hat q(a)=q(a)+\varepsilon_a.
\]

La recherche choisit :

\[
a^*=\arg\max_a \hat q(a).
\]

Même si les erreurs sont globalement non biaisées, le coup choisi tend à être celui qui a bénéficié de l'erreur positive la plus élevée. Pour un nombre de coups \(b\) et des erreurs approximativement gaussiennes, le maximum de bruit croît grossièrement comme :

\[
\sigma\sqrt{2\log b}.
\]

L'alpha–bêta ne consomme donc pas une erreur moyenne : il amplifie les erreurs extrêmes et les erreurs de classement.

### 2.2 Le corpus suit les forces et les angles morts du générateur

Un self-play miroir produit essentiellement les positions que le modèle courant juge intéressantes. Lorsque les deux côtés partagent les mêmes préférences et les mêmes erreurs, certaines variantes restent invisibles : aucun des deux joueurs ne les choisit, donc aucune donnée ne vient corriger leur évaluation.

C'est la forme jeu de société du problème traité par DAgger : la distribution future dépend des décisions du nouvel agent. Entraîner sur une distribution fixe ou héritée ne garantit pas une bonne performance sur la distribution que ce nouvel agent induira lui-même.

Le problème n'est donc probablement plus :

> Combien de positions supplémentaires faut-il générer ?

mais plutôt :

> Quelles positions apportent une information nouvelle sur les décisions que le moteur prend réellement ?

### 2.3 Le résultat terminal attribue peu de crédit aux décisions intermédiaires

Une partie de cent coups ne fournit qu'un résultat terminal. Tous les états de la trajectoire héritent ensuite, directement ou indirectement, de cette information agrégée.

Le signal réellement utile peut être beaucoup plus local :

- à ce nœud, le coup joué perdait `0.35` d'espérance par rapport au meilleur ;
- une extension de quatre plis inverse le signe de la position ;
- ce coup conserve une victoire de tablebase, celui-ci la transforme en nulle ;
- les deux meilleurs coups sont équivalents, mais les autres sont nettement inférieurs ;
- l'évaluation statique est correcte en niveau mais incorrecte en ordre.

TDLeaf avait précisément été conçu pour apprendre une fonction d'évaluation en tenant compte des feuilles sélectionnées par la recherche minimax. L'expérience historique KnightCap reste ancienne, mais son mécanisme est directement pertinent pour un moteur alpha–bêta.

### 2.4 La mémoire intergénérationnelle ne crée pas un signal absent

Jass dispose déjà d'un prior séquentiel : le champion précédent devient la moyenne d'un prior gaussien, avec une précision diagonale dérivée des visites. C'est une bonne protection contre l'oubli, mais ce mécanisme agit surtout sur la variance et ne déplace pas, à lui seul, le point fixe du modèle linéaire.

Ce prior ignore notamment :

- la confiance réelle de la prédiction, liée à `p(1-p)` dans la courbure logistique ;
- les corrélations entre motifs actifs ;
- les couplages milieu de jeu / fin de partie ;
- les directions globales où plusieurs poids doivent bouger ensemble.

Une mémoire bayésienne plus structurée peut aider un signal utile à composer. Elle ne peut pas inventer ce signal si les générations continuent de produire les mêmes décisions et les mêmes labels agrégés.

---

## 3. Revue de la littérature pertinente

### 3.1 TDLeaf : apprendre sur les feuilles réellement sélectionnées

TDLeaf applique l'apprentissage temporel aux feuilles de recherche sélectionnées par minimax, plutôt qu'aux seuls états de la trajectoire brute. L'intuition centrale est que la fonction d'évaluation doit être corrigée là où la recherche l'utilise effectivement.

Transposition pour Jass :

- enregistrer les feuilles de PV et leurs valeurs ;
- les réanalyser avec un budget supérieur ;
- apprendre l'écart entre l'évaluation statique et la valeur approfondie ;
- isoler les feuilles où le signe, la PV ou le meilleur coup changent.

L'ancien TD-Leaf de Jass n'épuise pas cette piste s'il ne supervise qu'une feuille de PV par coup et ne compare pas les coups frères d'une même racine.

### 3.2 DAgger : apprendre sur la distribution induite par l'agent

DAgger agrège itérativement les états visités par l'agent courant et les fait annoter par un expert. Son apport essentiel est distributionnel : les erreurs de l'agent changent les états futurs qu'il rencontrera, donc le dataset doit suivre cette évolution.

Transposition pour Jass :

- laisser le Jass courant générer les états réellement visités ;
- identifier les décisions fragiles ou regrettables ;
- demander au professeur de recherche de les annoter ;
- agréger ces nouveaux exemples avec l'historique ;
- recommencer seulement après avoir vérifié que la nouvelle génération apporte un signal mesurable.

### 3.3 Expert Iteration : la recherche améliore la politique, le modèle la généralise

Expert Iteration sépare deux rôles :

- la recherche agit comme expert local ;
- le modèle apprend à généraliser les décisions de cet expert.

Pour Jass, la recherche professeur peut produire deux objets :

- une valeur plus fiable des positions enfants ;
- une politique ou un classement des coups légaux.

Cette politique peut servir soit à la loss de l'évaluation, soit à un head séparé utilisé uniquement pour l'ordre des coups.

### 3.4 ChessBench et DeepChess : apprendre les valeurs relatives des coups

ChessBench montre l'intérêt d'annoter massivement les coups légaux avec un moteur fort. DeepChess défend une idée complémentaire : une fonction d'évaluation est fondamentalement un comparateur de positions.

La conséquence pratique pour Jass est importante : le professeur ne devrait pas seulement émettre une cible scalaire pour l'état joué. Il devrait, sur un sous-ensemble de positions, évaluer plusieurs coups frères.

Pour une position \(s\) et ses coups légaux \(a_1,\ldots,a_m\), le professeur fournit :

\[
Q_T(s,a_1),\ldots,Q_T(s,a_m).
\]

On en déduit une politique professeur :

\[
\pi_T(a\mid s)=\operatorname{softmax}\left(\frac{Q_T(s,a)}{T}\right).
\]

Le modèle statique induit une politique sur les positions enfants :

\[
\pi_w(a\mid s)=\operatorname{softmax}\left(\frac{F_w(s_a)}{T}\right).
\]

La loss listwise est alors :

\[
\mathcal L_{\mathrm{rank}}=\operatorname{CE}(\pi_T,\pi_w).
\]

Cette cible enseigne :

- le meilleur coup ;
- la proximité des meilleurs coups ;
- les coups clairement dominés ;
- les décisions que la recherche profonde a réellement corrigées.

### 3.5 Regret-Guided Search Control : cibler les états où l'agent a le plus à apprendre

Le travail 2026 **Regret-Guided Search Control for Efficient Learning in AlphaZero** est la source la plus directement alignée avec le blocage de Jass.

Son principe est de détecter des états à fort regret, provenant des trajectoires et des arbres de recherche, de les stocker dans une mémoire priorisée, puis de les réutiliser comme positions initiales. Les résultats publiés sur Go, Othello et Hex indiquent que ce ciblage peut continuer à améliorer des agents déjà proches d'un plateau.

La transposition de MCTS vers l'alpha–bêta demande un design spécifique, mais les signaux analogues sont disponibles :

- meilleur coup différent entre deux profondeurs ;
- fail-high ou fail-low d'une fenêtre d'aspiration ;
- changement important de PV ;
- changement de signe WDL ;
- faible marge top1–top2 ;
- grand écart entre valeur statique et valeur approfondie ;
- coup finalement joué ayant un regret élevé après réanalyse.

Définition proposée :

\[
R(s)=Q_T(s,a_T^*)-Q_T(s,a_J),
\]

où :

- \(Q_T\) est la valeur d'une recherche professeur plus forte ;
- \(a_T^*\) est son meilleur coup ;
- \(a_J\) est le coup choisi par le Jass courant.

Les positions avec un regret élevé deviennent les exercices personnalisés du moteur.

### 3.6 KataGo : séparer trajectoires bon marché et cibles coûteuses

KataGo apporte plusieurs idées très transférables :

- beaucoup de recherches peu coûteuses pour terminer davantage de parties ;
- une minorité de recherches complètes pour produire de bonnes cibles ;
- exploration forcée pour découvrir des variantes ;
- pruning de la cible afin que l'exploration artificielle ne devienne pas automatiquement la politique à imiter ;
- têtes auxiliaires pour structurer la représentation.

L'analogue alpha–bêta pour Jass serait :

- la majorité des coups à petit budget pour produire des résultats WDL ;
- une fraction prédéfinie de positions à budget professeur ;
- les parties complètes alimentent la cible terminale ;
- seules les positions profondément réanalysées alimentent la loss de classement et la loss de feuille ;
- un coup joué pour l'exploration n'est pas automatiquement labellisé comme bon coup.

### 3.7 Gumbel AlphaZero et best-arm identification : répartir le budget entre les vrais concurrents

Une recherche profonde de tous les coups peut être coûteuse. Les méthodes de best-arm identification et Gumbel AlphaZero suggèrent une allocation séquentielle :

1. attribuer un petit budget à tous les coups ;
2. éliminer les coups nettement dominés ;
3. doubler le budget sur les survivants ;
4. arrêter lorsque le meilleur coup est suffisamment certifié ou lorsque le budget maximal est atteint.

Pour Jass, ce protocole peut produire des labels frères fiables à coût contrôlé.

### 3.8 Active learning : utiliser l'incertitude pour choisir les données

L'incertitude ne doit pas nécessairement modifier directement le score ou le choix du coup. Elle peut servir à sélectionner les positions à réanalyser.

Pour un modèle linéaire muni d'un posterior approximatif :

\[
U(s)=x(s)^\top\Lambda^{-1}x(s).
\]

Les positions prioritaires sont alors celles qui combinent :

- forte incertitude ;
- fort désaccord entre budgets ou modèles ;
- forte probabilité de regret ;
- nouveauté par rapport à l'archive ;
- coût raisonnable de réanalyse.

Cette utilisation est distincte du screen CTX4. CTX4 testait un canal contextuel pour départager directement les meilleurs coups. Ici, l'incertitude ne change pas l'évaluation : elle change l'allocation du calcul et la distribution des données. Voir [`L3_CONTEXT4_UNCERTAINTY_SCREEN_SPEC_20260820.md`](L3_CONTEXT4_UNCERTAINTY_SCREEN_SPEC_20260820.md).

### 3.9 Bootstrapped DQN et posterior sampling : une exploration cohérente dans le temps

Des graines différentes ne garantissent pas une diversité stratégique. Deux runs peuvent visiter des positions différentes tout en reproduisant les mêmes concepts et les mêmes angles morts.

Une exploration plus profonde consiste à échantillonner des évaluateurs plausibles autour du champion :

\[
w_k\sim\mathcal N(\mu,c\Lambda^{-1}).
\]

Chaque \(w_k\) est conservé pendant une partie entière ou une lignée entière. L'exploration poursuit ainsi une hypothèse stratégique cohérente, au lieu d'ajouter un bruit indépendant à chaque coup.

La version horizontale du self-play deviendrait :

- un champion ;
- plusieurs échantillons postérieurs ;
- quelques champions historiques ;
- éventuellement des adversaires spécialisés cherchant à exploiter le champion ;
- une sélection finale maximisant force minimale et diversité comportementale.

### 3.10 Online structured Laplace : transporter une mémoire de courbure

Une approximation de Laplace en ligne transporte une distribution approximative sur les poids. Au lieu d'un simple rappel diagonal fondé sur les visites, on peut accumuler une approximation de la courbure :

\[
\Lambda_t\approx\Lambda_{t-1}+X_t^\top\operatorname{diag}[p_t(1-p_t)]X_t.
\]

Une progression pragmatique pour Jass serait :

1. Fisher diagonal réel, tenant compte de `p(1-p)` ;
2. blocs 2×2 liant MG et EG d'un même bucket ;
3. bloc complet pour les extras ;
4. approximation globale diagonale plus faible rang :
   \[
   \Lambda=D+UU^\top ;
   \]
5. 64 à 256 directions principales obtenues par produits Hessienne-vecteur.

Le prior devient :

\[
\frac12(w-\mu)^\top\Lambda(w-\mu).
\]

Cette piste est un multiplicateur de compounding, pas une source primaire de signal. Elle doit venir après la validation de la supervision search-aware.

### 3.11 Tablebases et Chinook : exploiter la frontière, pas seulement l'intérieur

Les tablebases ont été décisives pour les grands moteurs de dames et de checkers. Le corpus Jass n'exploite aujourd'hui une vérité exacte que sur la tranche effectivement couverte par l'EGDB.

La meilleure exploitation n'est probablement pas d'ajouter uniformément des positions déjà triviales à sept pièces. Il faut construire un curriculum de **frontière de tablebase** :

- positions à huit, neuf ou dix pièces réellement rencontrées ;
- états situés à quelques plis d'une entrée en tablebase ;
- valeur exacte de chaque coup qui entre dans la zone prouvée ;
- distinction « conserve la victoire / perd la victoire / retarde la conversion » ;
- distance jusqu'à l'entrée ou jusqu'à la conversion.

Un premier corpus très propre pourrait se concentrer sur les positions à huit pièces avec capture obligatoire menant à sept pièces. Chaque alternative enfant serait alors évaluée exactement.

### 3.12 Valeur catégorielle W/D/L

Le score actuel résume approximativement :

\[
P(W)+\frac12P(D).
\]

Cette espérance confond une position presque toujours nulle avec une position gagnée une fois sur deux et perdue une fois sur deux.

Un modèle à trois logits pourrait prédire :

\[
P(W\mid s),\quad P(D\mid s),\quad P(L\mid s).
\]

Le score alpha–bêta resterait initialement :

\[
V(s)=P(W\mid s)-P(L\mid s).
\]

La probabilité de nulle pourrait servir comme diagnostic de conversion, d'incertitude ou de robustesse. Cette piste est cependant secondaire : si la recherche ne consomme qu'une espérance scalaire, son bénéfice peut rester limité sur une architecture strictement linéaire.

### 3.13 NNUE et capacité non linéaire

Les moteurs d'échecs modernes montrent qu'une petite évaluation neuronale rapide peut fonctionner avec l'alpha–bêta. ChessBench indique qu'une partie importante de la planification peut être distillée à partir de valeurs de coups produites par une recherche forte.

Mais la bonne séquence expérimentale est :

1. produire un corpus search-aware ;
2. entraîner l'architecture linéaire actuelle avec la nouvelle loss ;
3. mesurer l'erreur de classement sur train et holdout ;
4. n'ajouter de capacité que si le linéaire ne parvient pas à apprendre les préférences du professeur.

Lectures possibles :

| Observation | Diagnostic probable |
|---|---|
| Erreur de classement élevée sur le train | Capacité ou features insuffisantes |
| Train bon, holdout mauvais | Généralisation, distribution ou régularisation |
| Train et holdout bons, force plate | Mauvais professeur ou mauvaise intégration au search |
| Classement et force progressent | Conserver le linéaire, solution la plus simple |

Si la capacité est réellement limitante, la transition recommandée est un résiduel :

\[
F(s)=F_{\text{PatternEval}}(s)+\alpha R_\theta(s).
\]

Le champion linéaire reste la base sûre ; le petit réseau apprend seulement les erreurs résiduelles et les inversions de classement impossibles à résoudre linéairement.

---

## 4. Fonction objectif proposée

L'évaluation élargie devrait idéalement fournir trois objets :

\[
E(s)=\bigl(V(s),P(\cdot\mid s),U(s)\bigr),
\]

avec :

- \(V(s)\) : valeur utilisée aux feuilles ;
- \(P(a\mid s)\) : prior ou ordre des coups appris à partir de la recherche profonde ;
- \(U(s)\) : incertitude servant à décider où chercher davantage et quelles données produire.

La loss complète proposée est :

\[
\boxed{
\mathcal L=
\lambda_z\mathcal L_{\mathrm{WDL}}
+\lambda_\pi\mathcal L_{\mathrm{rank}}
+\lambda_\ell\mathcal L_{\mathrm{leaf}}
+\frac12(w-\mu)^\top\Lambda(w-\mu)
}
\]

### 4.1 Ancre WDL

\[
\mathcal L_{\mathrm{WDL}}
\]

conserve l'objectif terminal véritable et évite qu'une distillation locale dérive vers un professeur imparfait.

### 4.2 Valeur profonde des feuilles

Pour un score professeur exact ou suffisamment stable :

\[
\mathcal L_{\mathrm{leaf}}
=
\operatorname{Huber}\left(F_w(s),Q_T(s)\right).
\]

La Huber limite l'influence des scores extrêmes et des sentinelles.

### 4.3 Classement listwise ou pairwise

Loss listwise :

\[
\mathcal L_{\mathrm{rank}}
=
\operatorname{CE}\bigl(\pi_T,\pi_w\bigr).
\]

Variante pairwise :

\[
\mathcal L_{\mathrm{pair}}
=
\sum_{i,j}\omega_{ij}
\log\left(1+
\exp\left[-\frac{
\operatorname{sign}(Q_i-Q_j)(F_i-F_j)}{\tau}
\right]\right).
\]

Les exemples sont pondérés plus fortement lorsque :

- le professeur est stable entre plusieurs budgets ;
- le modèle courant classe mal les deux coups ;
- la marge professeur est suffisamment nette pour être informative ;
- la position est rare ou nouvelle ;
- le coup joué présente un regret élevé.

Les très grands écarts faciles et les écarts minuscules instables doivent être moins pondérés.

### 4.4 Bornes alpha–bêta

Tous les scores produits par une recherche PVS ne sont pas exacts. Il faut conserver les types `EXACT`, `LOWER` et `UPPER`.

Pour une borne supérieure \(U\) :

\[
\mathcal L_U=\max(0,F_w-U)^2.
\]

Pour une borne inférieure \(L\) :

\[
\mathcal L_L=\max(0,L-F_w)^2.
\]

Cela permet d'exploiter davantage de nœuds sans transformer une coupure en fausse cible exacte.

### 4.5 Convexité sous PatternEval

Pour un évaluateur linéaire :

\[
F_w(s)=w^\top\phi(s).
\]

La différence entre deux coups reste linéaire :

\[
F_w(s_i)-F_w(s_j)=w^\top\left[\phi(s_i)-\phi(s_j)\right].
\]

Avec des labels professeur figés, la cross-entropie listwise, la loss pairwise logistique, une loss de valeur convexe et le prior quadratique forment encore un problème convexe.

Cette propriété rend la proposition particulièrement adaptée à l'infrastructure scientifique actuelle : L-BFGS, contraintes de symétrie, exact-fold, exact-extras et artefacts PJTW peuvent être conservés.

---

## 5. Fonction d'acquisition des positions

La sélection des positions à réanalyser devrait maximiser l'information décisionnelle par seconde CPU, et non le nombre brut de lignes.

Synthèse proposée pour Jass :

\[
A(s)=
\frac{
(\varepsilon+R(s))
(\varepsilon+D(s))
(\varepsilon+U(s))
(\varepsilon+N(s))
}{C(s)},
\]

avec :

- \(R(s)\) : regret du coup choisi ;
- \(D(s)\) : désaccord entre profondeurs, budgets, snapshots ou évaluateurs ;
- \(U(s)\) : incertitude épistémique ;
- \(N(s)\) : nouveauté par rapport à l'archive ;
- \(C(s)\) : coût estimé de réanalyse.

Cette équation est une synthèse spécifique à Jass, pas une formule reprise telle quelle d'un article.

Les positions prioritaires seraient celles où :

- shallow et deep choisissent des coups différents ;
- le meilleur coup change entre profondeurs ;
- la PV est instable ;
- le modèle est confiant mais un autre snapshot le contredit ;
- la marge top1–top2 est faible mais le professeur est stable ;
- le coup choisi est fortement surestimé ;
- un pattern, une phase ou une structure de matériel est rare ;
- la position précède une finale tablebase ;
- plusieurs lignées indépendantes prennent des décisions différentes.

---

## 6. Réinterprétation du self-play horizontal

L'idée de plusieurs lignées indépendantes est conservée, mais la variable scientifique à diversifier ne devrait pas être seulement la graine.

La diversité utile doit porter sur des hypothèses stratégiques cohérentes :

- échantillons postérieurs autour du champion ;
- champions historiques ;
- styles spécialisés par phase ou structure ;
- adversaires exploitants entraînés contre le champion ;
- budgets et critères d'acquisition différents, figés avant résultat.

La diversité doit être mesurée sur :

- distribution des motifs activés ;
- phases et structures de matériel ;
- ouvertures et familles de trajectoires ;
- décisions où les évaluateurs se contredisent ;
- empreintes de PV ;
- covariance ou rang effectif des features ;
- regret marginal apporté par chaque nouvelle lignée.

Le pool horizontal devient ainsi une source de contre-exemples et de désaccords, plutôt qu'un simple mégacorpus.

---

## 7. Policy head séparé pour l'ordre des coups

Les mêmes annotations de coups frères peuvent entraîner un petit modèle :

\[
P_\theta(a\mid s)\approx\pi_T(a\mid s).
\]

Dans une première version, ce modèle ne modifie ni la valeur statique, ni les bornes, ni les réductions. Il sert uniquement à l'ordre des coups.

Avantages :

- faible risque moteur ;
- gain possible de profondeur effective à temps constant ;
- meilleure proportion de first-move cutoffs ;
- moins de recherches PVS ;
- même corpus professeur que la loss de classement ;
- possibilité de déployer un gain search avant de modifier l'échelle de l'évaluation.

Une meilleure politique d'ordering peut acheter de l'Elo même si la valeur scalaire change peu.

---

## 8. Plan expérimental recommandé

### Étape 0 — laisser finir la gate Context30 en cours

Au moment de la rédaction, l'issue [#552](https://github.com/jfrancoiscollin/jass/issues/552) documente le rerun `cpx62-1459-l3-replay-context30-target-gate-v1`. Le protocole compare la cible Context30 à la cible WDL native sur les mêmes données REPLAY25. Voir [`L3_REPLAY_CONTEXT30_TARGET_GATE_20260821.md`](L3_REPLAY_CONTEXT30_TARGET_GATE_20260821.md).

Son verdict doit être conservé. Positif ou négatif, il ne teste cependant ni la distribution de positions ni la supervision de plusieurs coups légaux.

### Étape 1 — instrumentation sans intervention scientifique

Créer un sidecar de recherche enregistrant, sur des positions fraîches :

- position et identifiant de partie ;
- tous les coups légaux ;
- score et type de borne de chaque coup au budget étudiant ;
- meilleur coup et PV ;
- score au budget professeur ;
- changement du meilleur coup ;
- regret du coup étudiant ;
- stabilité entre deux budgets professeur ;
- éventuelle preuve tablebase ;
- features PatternEval des positions enfants ;
- coût en nœuds et temps.

Aucun fit, aucun match de promotion et aucun changement du champion à cette étape.

### Étape 2 — audit racine shallow/deep

Échantillonner 20 000 à 50 000 positions, stratifiées par :

- nombre de pièces ;
- présence de dames ;
- phase ;
- capture obligatoire ou position calme ;
- facteur de branchement ;
- ouverture ou lignée ;
- rareté des buckets.

Pour chaque position :

1. recherche étudiant au budget courant ;
2. recherche professeur à environ 4 à 8 fois plus de nœuds ;
3. score de chaque coup légal ou sequential halving si le branchement est élevé ;
4. audit d'un sous-échantillon avec Scan profond et tablebase lorsqu'elle s'applique.

Métriques principales :

- accord top-1 ;
- regret moyen du coup choisi ;
- accuracy des marges top-2 ;
- optimisme du coup sélectionné ;
- fréquence de changement du meilleur coup ;
- stabilité de PV ;
- nombre de nœuds nécessaire pour retrouver le meilleur coup profond.

### Étape 3 — screen causal de la loss

Même corpus, mêmes splits, même architecture, même prior et même budget d'optimisation :

| Bras | Intervention |
|---|---|
| A — `BASE` | WDL natif seulement |
| B — `LEAF` | WDL + valeur des feuilles réanalysées |
| C — `RANK` | WDL + classement listwise des coups |
| D — `LEAF_RANK` | WDL + feuille + classement |

Les coups frères d'une même position doivent rester entièrement dans le train ou entièrement dans le holdout.

Les coefficients de loss ne doivent pas être ajustés après lecture des parties. Une méthode propre est de normaliser chaque terme selon sa norme de gradient initiale, puis de verrouiller les coefficients avant le premier résultat de force.

### Étape 4 — gates offline

Critères primaires :

- réduction du regret face au professeur ;
- accord top-1 ;
- réduction des inversions top1/top2 ;
- réduction des changements de classe WDL ;
- stabilité entre deux holdouts disjoints ;
- métriques par phase et structure de matériel.

La log-loss WDL, la calibration et la convergence restent des garde-fous, mais ne sont plus les critères de sélection principaux.

### Étape 5 — force

Seuls les bras montrant une réduction répliquée du regret passent en force.

Le protocole Jass actuel convient :

- deux pools frais et mutuellement disjoints ;
- couleurs appariées ;
- native primaire ;
- Q00 diagnostic ;
- bootstrap par ouverture ;
- aucune promotion automatique.

### Étape 6 — DOE séparé sur la distribution

Après validation du calcul du regret :

| Bras | Départs de self-play |
|---|---|
| A — `NORMAL` | Départs usuels |
| B — `ARCHIVE_RANDOM` | Proportion fixée de départs tirés aléatoirement de l'archive |
| C — `ARCHIVE_REGRET` | Même proportion, tirage pondéré par le regret |

Les trois bras utilisent le même moteur, la même cible WDL et le même volume effectif.

Ce DOE distingue :

- l'effet d'un simple redémarrage depuis des états passés ;
- la valeur spécifique du ciblage par regret ;
- un effet de longueur de partie ou de volume.

### Étape 7 — combinaison dans une génération complète

Si la loss de classement et le ciblage des positions passent séparément :

1. self-play depuis un mélange normal + archive de regret ;
2. réanalyse profonde d'une fraction préenregistrée des décisions ;
3. agrégation des données anciennes et nouvelles ;
4. fit WDL + ranking + leaf ;
5. transport d'un posterior structuré ;
6. une seule génération complète avant d'autoriser une boucle itérative.

---

## 9. Priorisation

| Priorité | Piste | Potentiel | Coût | Commentaire |
|---:|---|---|---|---|
| **P0** | Archive de positions à fort regret | Très élevé | Moyen | Change directement ce que le self-play joue |
| **P0** | Distillation listwise de plusieurs coups | Très élevé | Moyen | Aligne la loss avec les décisions alpha–bêta |
| **P0** | Policy head pour l'ordre des coups | Élevé | Faible à moyen | Gain possible sans casser l'échelle de valeur |
| **P0/P1** | Incertitude pour acquisition et extensions | Élevé | Faible à moyen | Distinct du reranking CTX4 |
| **P1** | Curriculum de frontière tablebase | Élevé sur la conversion | Moyen | Professeur exact et propre |
| **P1** | Posterior Fisher + faible rang | Moyen à élevé | Moyen | Aide le nouveau signal à composer |
| **P1** | Self-play horizontal par échantillons postérieurs | Moyen à élevé | Moyen | Diversité stratégique cohérente |
| **P1** | Budgets de recherche aléatoires structurés | Moyen | Faible | Plus de résultats et de labels profonds par CPU |
| **P2** | W/D/L catégoriel | Moyen | Moyen | Complément, probablement pas la clé seule |
| **P2** | Résiduel NNUE | Élevé si sous-capacité prouvée | Élevé | Après mesure du plafond linéaire |
| **Veille** | Diffusion ou planification latente | Incertain | Très élevé | Recherche émergente |

---

## 10. Ce qui ne doit plus être prioritaire sans argument nouveau

Suspendre, tant qu'une nouvelle source de signal n'est pas démontrée :

- un nouveau très gros corpus WDL produit par la même politique ;
- de nouvelles graines sans mesure de diversité comportementale ;
- une nouvelle famille de mélanges scalaires sur les mêmes lignes ;
- un nouveau dosage de prior sans modification du corpus ou de la loss ;
- de l'incertitude ajoutée directement au score ou utilisée comme reranker ;
- du bruit epsilon indépendant à chaque coup ;
- un grand NNUE entraîné uniquement sur le WDL actuel ;
- une sélection de candidats fondée principalement sur MSE, log-loss ou calibration ;
- une expérience où génération, architecture, cible et optimiseur changent simultanément.

---

## 11. Recommandation finale

Hypothèse scientifique principale :

> Le plafond de Jass vient moins d'un manque de labels que d'un manque de supervision sur les décisions critiques et d'un self-play qui ne revisite pas méthodiquement ses propres erreurs.

Prochaine campagne de référence proposée :

### `L3_REGRET_GUIDED_SEARCH_DISTILLATION_V1`

Noyau de la campagne :

1. calculer le regret des décisions par réanalyse profonde ;
2. construire une archive priorisée de positions difficiles ;
3. annoter plusieurs ou tous les coups légaux sur un sous-ensemble ;
4. ajouter une loss listwise de classement au WDL ;
5. tester sans changement d'architecture ;
6. utiliser l'incertitude pour sélectionner les données, jamais comme bonus arbitraire de valeur ;
7. tester séparément les redémarrages depuis l'archive ;
8. ne passer au résiduel NNUE que si le PatternEval linéaire échoue à apprendre les classements du professeur.

En une phrase :

> Ne plus apprendre seulement « qui a gagné cette partie ? », mais « à cet endroit précis, quel coup la recherche profonde préfère-t-elle, de combien, et pourquoi le moteur courant ne l'a-t-il pas trouvé ? »

C'est la meilleure chance identifiée par cette revue pour sortir du point fixe actuel sans professeur externe obligatoire et sans abandonner l'infrastructure scientifique existante.

---

## 12. Références

### Recherche, imitation et distillation

- Baxter, Tridgell, Weaver — **KnightCap: A Chess Program that Learns by Combining TD(λ) with Game-Tree Search** / TDLeaf : https://arxiv.org/abs/cs/9901001
- Ross, Gordon, Bagnell — **A Reduction of Imitation Learning and Structured Prediction to No-Regret Online Learning** / DAgger : https://proceedings.mlr.press/v15/ross11a.html
- Anthony, Tian, Barber — **Thinking Fast and Slow with Deep Learning and Tree Search** / Expert Iteration : https://arxiv.org/abs/1705.08439
- David, Netanyahu, Wolf — **DeepChess: End-to-End Deep Neural Network for Automatic Learning in Chess** : https://arxiv.org/abs/1711.09667
- Ruoss et al. — **ChessBench: A Large-Scale Benchmark for Chess Understanding** : https://arxiv.org/abs/2402.04494
- **Regret-Guided Search Control for Efficient Learning in AlphaZero** : https://arxiv.org/abs/2602.20809

### Exploration et allocation de recherche

- Schrittwieser et al. / KataGo — **Accelerating Self-Play Learning in Go** : https://arxiv.org/abs/1902.10565
- Danihelka et al. — **Policy Improvement by Planning with Gumbel** : https://arxiv.org/abs/2102.11766
- Osband et al. — **Deep Exploration via Bootstrapped DQN** : https://proceedings.neurips.cc/paper/2016/hash/8d8818c8e140c64c743113f563cf750f-Abstract.html
- Wang et al. — **Adversarial Policies Beat Superhuman Go AIs** : https://proceedings.mlr.press/v202/wang23g.html

### Mémoire et incertitude

- Ritter, Botev, Barber — **Online Structured Laplace Approximations for Overcoming Catastrophic Forgetting** : https://proceedings.neurips.cc/paper/2018/hash/f31b20466ae89669f9741e047487eb37-Abstract.html
- Katz-Samuels et al. — active learning / best-arm identification : https://proceedings.mlr.press/v139/katz-samuels21a.html

### Valeurs catégorielles et architecture

- Farebrother et al. — **Stop Regressing: Training Value Functions via Classification for Scalable Deep RL** : https://proceedings.mlr.press/v235/farebrother24a.html
- Stockfish officiel, architecture et NNUE : https://github.com/official-stockfish/Stockfish

### Dames, checkers et tablebases

- Chinook — bases de finales : https://webdocs.cs.ualberta.ca/~chinook/databases/

### Frontière à surveiller

- **DiffuSearch** : https://arxiv.org/abs/2502.19805
- apprentissage contrastif et planification latente en échecs : https://arxiv.org/abs/2506.04892
