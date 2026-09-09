# Campagne prospective — candidat evaluation/search avant scale-up V1

Date : 2026-09-09. Objectif : poursuivre des interventions scientifiques
légères jusqu'à obtenir un candidat dont tous les gates prospectifs sont verts,
ou jusqu'à une impossibilité documentée. Cette autorisation couvre les étapes
bornées et préenregistrées ci-dessous, sans approbation manuelle entre elles.
Elle n'autorise jamais scale-up, bake, promotion, Pool2 ou remplacement de
`CURRICULUM`.

ED4 est l'essai prospectif `k=1`. ED2/ED3, ED3-T1, le TRAIN512, la confirmation
1884 et le replay CURRENT_2M déjà inspecté sont des données consommées. Ils
servent à motiver et exclure, jamais à confirmer une nouvelle tentative.

## Définition d'un candidat réellement vert

Une tentative `k` ne devient verte que si les quatre conditions suivantes sont
toutes satisfaites par des artefacts scellés et des cohortes définies avant la
première lecture de leurs cibles :

1. **Fit et runtime.** Un seul candidat est produit par la recette gelée ; tous
   les contrôles numériques, quantification et reload natif passent.
2. **Décision statique fraîche.** Sur une cohorte Q200k disjointe de TRAIN et de
   toute cohorte consommée, le candidat réduit le regret parent-weighted face à
   BASE et HARD : pour chaque contraste, borne inférieure positive. Il n'abaisse
   pas le top-hit face au meilleur contrôle et `harmed <= improved`. SOFT est
   descriptif seulement. Priorité terminale, ties et POV reprennent exactement
   le contrat 1884 ; aucun seuil n'est déduit des valeurs observées.
3. **Calibration WDL indépendante.** Sur des issues jamais consultées pour le
   fit, la sélection ou une tentative antérieure, les bornes supérieures des
   deltas candidat-BASE sont `<=0.002` pour logloss et Brier. Une nouvelle tranche
   de CURRENT_2M ne vaut pas, à elle seule, preuve fraîche : ce corpus et ses
   agrégats ont été exposés. À défaut d'une réserve dont l'absence de lecture est
   authentifiable, un nouveau corpus d'issues doit être généré sous protocole
   séparé avant évaluation.
4. **Transfert dans la recherche.** Sur des racines fraîches, le candidat et BASE
   sont branchés dans le même exécutable Jass, mêmes bytes hors évaluateur, même
   cache, threads, limites et budget de nœuds. Un teacher de référence et le
   budget sont gelés avant génération. La borne inférieure du gain de regret de
   choix racine candidat-BASE est positive, les sanities BASE/BASE sont exactes,
   et aucun invariant nodes/configuration ne diverge. HARD est un contrôle
   secondaire gelé ; SOFT reste descriptif. Ce gate démontre un transfert de
   décision à budget égal, pas un Elo ni une promotion.

Chaque protocole de confirmation fixe aussi le volume et exige un minimum par
phase/STM ; support insuffisant n'est jamais transformé en réussite. Les
conditions 2 à 4 doivent porter sur trois sources disjointes entre elles ou
justifier prospectivement leur indépendance statistique et le bootstrap groupé.

## Multiplicité et tentatives adaptatives

Le compteur commence à `k=1` pour ED4. La dépense familiale de la campagne est
`alpha_k = 0.05 / 2^k`, donc la somme sur un nombre quelconque de tentatives est
au plus `0.05`. Une tentative alloue `alpha_k/3` à chacun des trois blocs
confirmatoires décision, calibration et recherche. Dans un bloc conjonctif,
chaque assertion obligatoire utilise un intervalle unilatéral de niveau
`1-alpha_k/3` ; toutes doivent passer. Cela est un test intersection-union, sans
renormalisation postérieure. Les statistiques descriptives restent étiquetées.
Un protocole de tentative peut employer un plan group-sequential seulement s'il
gèle avant lecture ses looks, bornes et dépense dans ce même budget ; sinon le
volume est fixe. Aucun ajout de lignes, nouveau bootstrap, deuxième seed ou
nouvel intervalle après lecture.

Cette dépense est une comptabilité prospective de multiplicité, conditionnelle
à des intervalles valides au niveau annoncé et aux hypothèses de groupement et
d'indépendance du protocole de stage. Un bootstrap percentile approximatif ne
confère pas, à lui seul, une garantie universelle de FWER. Chaque stage doit
justifier prospectivement sa méthode d'intervalle, son unité de rééchantillonnage
et sa couverture ; une hypothèse non défendable rend le résultat insuffisant.

Chaque cohorte échouée ou insuffisante est consommée définitivement. Une piste
ultérieure peut être choisie à partir des échecs antérieurs, mais sa confirmation
utilise des données nouvelles et la tranche alpha suivante. Il est interdit de
répéter des IC95 jusqu'au vert ou de qualifier un holdout exposé de final.

## Automate scientifique

Avant chaque tentative : (a) une note causalement falsifiable choisit une seule
dimension — objectif, représentation, fiabilité teacher ou intégration search ;
(b) un protocole versionné gèle données, contrôles, recette, volume et gates ;
(c) un preflight synthétique/native et une répétition même-code passent ; (d) un
sizing sans cible démontre <=45 min CPX62 par job, 16 CPU max et >=3 Gio libres.
Modifier simultanément la perte de rang et la pondération/contrainte WDL est
interdit. Aucun sweep, recherche de modèles, sélection de checkpoint ou tuning
sur confirmation.

- Tous les gates verts : `CAMPAIGN_REAL_CANDIDATE_GATE_GREEN_V1`, puis arrêt sur
  `PREREGISTER_SCALE_UP_REVIEW`; aucun scale-up automatique.
- Fit valide mais au moins un gate confirmatoire échoue :
  `CAMPAIGN_ATTEMPT_SCIENTIFIC_NOT_SUPPORTED_V1`. Sceller les données, expliquer
  quel signal ne soutient pas la piste — un intervalle imprécis n'est pas une
  falsification causale — puis préenregistrer automatiquement une nouvelle
  intervention à un seul axe avec `k+1`.
- Support/source inadéquat avant cible ou puissance prospectivement impossible
  dans 45 min : `CAMPAIGN_ATTEMPT_INSUFFICIENT_V1`. La suite autorisée est un
  protocole de source/sizing neuf, jamais l'assouplissement du gate.
- Échec mécanique : `CAMPAIGN_ATTEMPT_TECHNICAL_FAILURE_V1`. Réparer et répéter
  le même contrat ; si une cible a été révélée, elle reste consommée.
- Identité non authentifiable, absence durable de données fraîches ou coût
  minimal dépassant la limite : `CAMPAIGN_BLOCKED_BY_EVIDENCE_OR_RESOURCE_V1` et
  arrêt explicite, sans fabriquer un succès.

## Audit obligatoire avant la première confirmation

Un inventaire metadata-only, sans champs Q200k/WDL, doit résoudre et publier :

- l'union canonique de tous les parents TRAIN, benchmarks et confirmations
  consommés, dont les manifests 1875/1878/1884 et leurs `source.json` ;
- les modes/seeds effectivement acceptés par le générateur score-free 1875 et
  la possibilité de créer une nouvelle cohorte disjointe sans inventer un seed ;
- pour WDL, le manifest de split CURRENT_2M, les opening/group IDs, l'union de
  toutes les lignes déjà lues et la provenance des targets Context30 ;
- pour search, l'exécutable, les hashes evaluator/teacher, la source des racines,
  les exclusions historiques et l'unité indépendante du bootstrap.

Tant qu'un de ces points est ambigu, le protocole correspondant ne peut pas
nommer de sélecteur « fresh ». Cet audit peut conclure qu'aucune réserve WDL
indépendante n'existe ; il doit alors préenregistrer une génération nouvelle.

Les jobs ordinaires de code, CI, audit metadata, synthetic preflight, fit et
confirmations légères sont dans la campagne. Tous publient code SHA, entrées,
lectures, coûts, reçus et issue terminale. Les tables consommées restent
interdites au réglage et à la sélection des gates futurs ; cette règle vise les
cibles de confirmation consommées. Elle n'interdit pas la réutilisation du
TRAIN512 et du replay8192 explicitement gelés comme entrées de fit ED4-P1.
