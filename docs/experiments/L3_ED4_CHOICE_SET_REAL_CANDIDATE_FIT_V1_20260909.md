# ED4-P1 — préenregistrement du fit réel du candidat choice-set V1

Date : 2026-09-09. Ce document est prospectif : aucune ligne TRAIN/replay,
aucun modèle réel et aucune métrique cible ne sont lus pour le rédiger. ED4-P0
a seulement établi la cohérence numérique synthétique de l'objectif. ED3 reste
terminal (`STOP_ED3`) et ses résultats ne règlent aucun paramètre ED4.

## Question et intervention unique

La question est uniquement : la recette ED4-P0, appliquée une fois au corpus
historique gelé, produit-elle un artefact réel fini, stationnaire au sens du
contrat, quantifié et reproductible nativement ? Ce stage ne teste ni transfert,
ni calibration hors échantillon, ni recherche.

L'unique changement par rapport à ED3 est le remplacement de toute la perte
ordinale par la perte choice-set ED4-P0. Sont immuables : BASE
`e4d510fbb9b81cbe74574d92da48e8de6f61d8f98de6472eeb409713785f0de0`,
les 120 extras et leurs 240 coordonnées MG/EG dans l'ordre PJTW, les 512 parents
TRAIN, le replay WDL de 8192 lignes, coefficient choice `1`, coefficient WDL
`1`, ridge `0.0005`, point initial nul, signe POV, labels PARTIAL Q5k/Q50k et
seal source `31f763049fef50544bd1cbb240eeb4f51670728ae0697a77e982186df007152c`.
HARD et SOFT restent des contrôles scellés, jamais des initialisations.

Les quatre rôles d'entrée sont exactement les identités `P0`, `N1`, `BASE` et
`TARGET` authentifiées par l'audit source ED3-P1, avec les allowlists littérales ci-dessous
et ses hashes de fichiers. L'implémentation les reprend sans découverte de
fichier, fallback ni préfixe élargi : source score-free scellée P0, huit shards
TRAIN et labels/support scellés N1, table native et PJTW BASE, sélection replay
et tableau Context30 TARGET. Le transport et le hash du tableau Context30 entier
sont permis, mais seules les 8192 positions replay scellées peuvent être
déréférencées. Aucun index TEST/confirmation ne l'est. HARD et SOFT n'entrent que
comme hashes/metadata de contrôle ; leurs fichiers réels ne sont pas lus par P1.

Pour chaque parent, l'objectif, les ensembles `V_p/A_p`, les cas
all-admissible/terminal/invalides, le gradient, le Hessien, le solveur
`trust-exact`, ses paramètres, les caps, la stationnarité, la courbure locale,
la quantification scale-1000 ties-to-even et le double reload natif sont
exactement ceux de `L3_ED4_CHOICE_SET_PREFLIGHT_V1_20260909.md`. Aucun restart,
fallback, température, clipping, marge, checkpoint ou alternative n'existe.
Les identifiants TRAIN clairsemés sont des entiers ; le loader les remappe vers
des indices locaux contigus en conservant strictement l'ordre des row IDs
originaux au sein de chaque parent.

Le code peut mettre en cache des appels de dérivées dont l'entrée est
bit-identique et pré-calculer `z+x beta` une seule fois par appel. Cette
optimisation est purement mécanique : le preflight synthétique doit établir la
parité valeur/gradient/Hessien avec la formule de référence, sans tolérance ou
critère scientifique modifié.

## Exécution gelée et absence de sélection

La répétition CPX62 et la production utilisent toutes deux les 512 parents et
les 8192 lignes replay, avec normaliseur parent `512`, et le même code. Chacune
effectue exactement une optimisation depuis zéro. La première est une
répétition technique development-only ; elle ne choisit aucune option. La
production ne peut démarrer que si cette répétition a publié un reçu authentifié.
Les champs scientifiques purs du rapport numérique, le beta float64, le vecteur
quantifié et les bytes PJTW doivent être identiques. Les champs de mode, temps,
tentative, chemins et reçus ne sont pas comparés. Cela compte
`real_optimizer_invocations=2` et un seul candidat
scientifique scellé. Une différence arrête le stage ; aucun des deux résultats
n'est préféré.

Chaque exécution est bornée à 300 s pour le solveur, 900 s pour le stage et
1500 s côté runner, 16 CPU maximum, bibliothèques numériques à un thread et
minimum 3 Gio libres. Un sizing metadata-only préalable doit démontrer un ETA
compatible ; aucune cible heldout n'est autorisée. Aucun Scan/Jass search,
nouveau label, partie, self-play, promotion ou bake.
Les murs ED3 observés, environ 302 s en répétition et 308 s en production avec
publication, sont seulement des ancres de sizing. Le résultat CI local de P0 et
les versions différentes de Python/NumPy/SciPy ne se transportent pas comme ETA
ou preuve : le véritable chemin numérique CPX62 doit être exercé.

## Issues terminales

- La répétition passe seule :
  `ED4_CHOICE_SET_REAL_FIT_REHEARSAL_COMPLETE_V1`. Ce terminal ne scelle aucun
  candidat scientifique.
- Tous les contrôles P0, identité, stationnarité, courbure locale, objectif
  quantifié et reload natif passent en production, et les charges scientifiques
  pures des deux exécutions sont identiques :
  `ED4_CHOICE_SET_REAL_CANDIDATE_SEALED_V1`.
- Le solveur refuse, ou beta/objectif/gradient/Hessien est non fini, ou un
  critère gelé de stationnarité/courbure/objectif float64 échoue :
  `ED4_CHOICE_SET_REAL_FIT_NUMERICAL_FAILURE_V1`. C'est un échec numérique,
  pas une preuve scientifique contre l'objectif ; aucune relaxation V1. Un
  objectif du beta quantifié non fini ou supérieur à `L(0)+1e-12` relève aussi
  de ce terminal numérique.
- Identité, provenance, format/sérialisation, parité ou reload natif, timeout,
  mémoire, build ou transport échoue :
  `ED4_CHOICE_SET_REAL_FIT_TECHNICAL_FAILURE_V1`. Une correction mécanique peut
  répéter exactement le contrat, sans changer la science.

Le terminal positif produit `ED4_CHOICE.pjtw`, le beta float64, le rapport de
fit, le rapport quantifié/natif, les reçus de sources et un ledger. Il n'autorise
aucune lecture de confirmation. Avant toute cible fraîche, un protocole distinct
doit geler la source, les exclusions, le volume, les contrôles, les métriques,
les intervalles et la dépense alpha de la campagne.

## Identités et allowlists de transport

- P0 : `cpx62-1875-l3-ed2-data-teacher-preflight-v1` /
  `20260908T171140Z-bc30d685`, code `bc30d6858c4d590625f8831c4995f055816b95c2` ;
  `source/groups.tsv`, `source/children.jnnw`, `ed2-source-seal.json`.
- N1 : `cpx62-1878-l3-ed2-numerical-recovery-n1` /
  `20260908T191343Z-d71679e9`, code `d71679e96d78609b6d32052be80ca78c0deaece0` ;
  `train-0.jsonl` à `train-7.jsonl`, `train-labels-sealed.json`, `label-support.json`,
  `wdl-selection.json`, `wdl-selection.seal.json`, `replay.jnnw`,
  `native/train-native.tsv.gz`, `native/replay-native.tsv.gz`,
  `build-outputs/jass_ed2_value_probe.gz`, `scratch-cleanup.json`.
- BASE : `cpx62-1849-l3-decision-math-d1-wdl-listwise-fit-stage-env-recovery-requeue-v1` /
  `20260906T222203Z-08fd187a`, code `08fd187aa187f26bd7179df2c68056a74e28355d` ;
  `WDL_CONTROL.pjtw.gz`.
- TARGET : `cpx62-1340-jass-megacorpus-comparative-fit-v1` /
  `20260814T123246Z-2ce07222`, code `2ce07222f86c1468a1081fbdc53e9e17a0c5326e` ;
  `current_2m-context30.npy.gz`.

Ces chemins désignent les artefacts publiés ; les manifests, inventaires et
checksums requis par le fetcher commun restent lus pour leur authentification.
Aucun fichier PARTIAL/SOFT, label TEST ou native holdout n'est transporté par P1.
