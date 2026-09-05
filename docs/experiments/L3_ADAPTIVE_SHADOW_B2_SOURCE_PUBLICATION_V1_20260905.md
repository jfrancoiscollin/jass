# PR #771 — publication de la source et de la sélection B2

Date : 2026-09-05, Europe/Paris.

Statut : préparation technique prospective, revue terminée. Ce document
ne remplace pas le préenregistrement confirmatoire et n'annonce aucune
cohorte B2 exécutée.

Le [plan de la PR #771](L3_DECISION_INFORMATION_IMPLEMENTATION_PLAN_V1_20260903.md)
exige une confirmation B2 indépendante du diagnostic historique B1. Le
publisher `jobs/tools/adaptive_sibling_b2_source_publish.py` prépare le
transport entre les [producteurs et le sélecteur](L3_ADAPTIVE_SHADOW_B2_COHORT_TOOLING_V1_20260905.md)
et la future exécution teacher. Le teacher attend une sélection authentifiée
et publiée dans un commit documentaire distinct.

## 1. Commits et reçus distincts

Le protocole distingue quatre objets :

- **X** : commit exact des implémentations exécutées ; le runner et le checkout
  utilisent ce commit, avec les outils identiques aux blobs publiés.
- **Y** : descendant de X qui ajoute seulement le Markdown normatif de
  préenregistrement ; ses bytes sont authentifiés avant génération.
- **F** : reçu final de source et sélection, créé après validation, replay,
  copie des sorties autorisées et suppression des seize fichiers bruts.
- **S** : commit documentaire ultérieur qui publie les bytes de F après audit
  distant, sans inscrire le SHA de S dans F lui-même.

Y conserve les implémentations de X. La génération utilise X et les pins de Y.
Le teacher doit ensuite vérifier X, Y, S et F avant toute première lecture
teacher. Une ref flottante, un répertoire local ou un simple statut de job ne
remplace pas cette chaîne.

## 2. Génération finie et sélection aveugle aux cibles

La recette prospective conserve seize producteurs de 10 000 enregistrements,
le même CURRICULUM et les seeds `2026110700` à `2026110715`. Les producteurs
ont des groupes de processus distincts, une barrière de départ et un
environnement vide. Les filtres s'exécutent ensuite en série.

Le sélecteur utilise la seed `2026110716`, l'exclusion historique authentifiée
par 1773 et huit cellules de 500 parents. Les paramètres et la recette de
sélection appartiennent au contrat publié et au préenregistrement final.
Aucun score teacher n'intervient dans la sélection ni dans son replay.

L'autojeu du producteur effectue ses propres recherches. Les compteurs nuls
de teacher, fit et parties de force ne prétendent pas que le générateur
n'effectue aucune partie ni recherche interne. Les valeurs internes non
mesurées restent explicitement non renseignées.

## 3. Publication et support insuffisant

Une sélection complète est rejouée à l'identique, puis scellée localement.
Les bytes de parents, métadonnées, identités ordonnées et rapport doivent
conserver leurs identités pendant le transport. Les sorties publiées suivent
une liste fermée : reçus, manifests, logs, fichiers filtrés et sélection.
Les seize JNNW bruts, le modèle décompressé et les exécutables de travail
restent dans le scratch ; ils ne sont pas des artefacts de publication.

Le reçu réussi porte le schéma
`jass.adaptive_sibling_b2_source_selection_publication.v1` et le verdict
technique `B2_SOURCE_SELECTION_LOCAL_SEAL_COMPLETE`. Il ne contient pas son
propre hash. Il décrit les artefacts effectivement copiés et le nettoyage
des fichiers bruts.

Le code retour 4 du sélecteur est réservé au schéma typé
`jass.adaptive_sibling_b2_target_blind_support.v1`. Après authentification et
replay concordant, le publisher peut rendre
`B2_SOURCE_SELECTION_SUPPORT_NOT_ESTABLISHED_V1`, sans sortie parent,
complément de cellule, nouvelle seed ni nouvelle génération. Une erreur de
fichier, de processus, de timeout, de format ou de provenance reste technique.

`runner-launch.json` appartient au runner. Le publisher accepte ce fichier
réservé à l'arrivée et ne fige pas ses bytes transitoires dans F. L'audit R2
authentifie sa version finale séparément.

## 4. Bornes opérationnelles

Les timeouts obligatoires sont liés aux bytes de Y. Le bloc canonique
`jass.pr771_b2_source_operational_pins.v1` fixe les trois valeurs
`filter_timeout_seconds`, `launcher_timeout_seconds` et
`outer_timeout_seconds`, entre les marqueurs uniques
`B2_SOURCE_OPERATIONAL_PINS_V1_BEGIN` et
`B2_SOURCE_OPERATIONAL_PINS_V1_END`. Les arguments du launcher doivent
correspondre exactement à ces valeurs ; aucun défaut ne remplace une mesure
manquante.

Le plafond producteur de 413 s provient de l'ancre CPX62 1578 : même volume
16 × 10 000, recette comparable, chaîne complète mesurée à 317 s, marge 1,3.
Le filtre et le reste de l'enveloppe attendent la calibration historique et
la revue opérationnelle avant le gel de Y.

Les secrets R2 appartiennent uniquement au processus fetch. Les commandes
Git/build utilisent un environnement minimal explicite ; les processus de
génération et sélection reçoivent l'environnement vide. Les secrets ne
figurent ni dans les arguments ni dans les artefacts.

## 5. Validation et dépendances

La suite ciblée passe sous Linux : **14/14 tests**, reproduits par le root
en 8,084 s avec `ResourceWarning` fatal. La validation auteur sous Windows
compte 13 tests réussis et un test POSIX ignoré (26,439 s). La revue
indépendante finale ne conserve aucun problème P1/P2.

Les fixtures offline couvrent le transport, les identités, le replay, le
support typé, les collisions et mutations de fichiers, ainsi que les arrêts
bornés des groupes de processus. Elles ne créent aucune preuve scientifique
B2. La compilation Python et la vérification des espaces du diff passent.

Les publishers teacher et terminal, les mesures de coût manquantes et le
préenregistrement final restent nécessaires. Le [readout B2](L3_ADAPTIVE_SHADOW_B2_READOUT_V1_20260905.md)
conserve ses trois verdicts propres. La publication source n'autorise aucune
promotion, aucun bake ni aucun changement de CURRICULUM.
