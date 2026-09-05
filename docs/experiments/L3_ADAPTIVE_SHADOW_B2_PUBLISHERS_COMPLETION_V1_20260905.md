# B2 — calibration 1777 et complétion des publishers avant préenregistrement

Date : 5 septembre 2026, Europe/Paris.

Statut : **préparation technique prospective uniquement**. Ce document ne
préenregistre pas B2, ne génère aucun parent B2 frais et n'autorise ni B3, ni
promotion, ni bake.

Le [plan decision-information de la PR #771](L3_DECISION_INFORMATION_IMPLEMENTATION_PLAN_V1_20260903.md)
demande une confirmation B2 indépendante du diagnostic historique B1. Après les
PR #783 à #787, la chaîne possédait la génération/sélection target-blind, le
teacher natif, la fusion/vérification légale, l'allocation, la projection et le
readout statistique, mais les scellés teacher/terminal et les bornes de runtime
mesurées devaient encore être terminés avant de créer le commit normatif Y.

## 1. Calibration historique CPX62 1777

Exécution terminale authentifiée :

```text
job      cpx62-1777-l3-decision-math-b2-parallel-calibration-v1
attempt  20260905T092718Z-82a9a093
code     82a9a09363e9480ed4d55bf2119a9aa687e1b3f9
host     cpx62
state    completed
exit     0
verdict  B2_PARALLEL_TEACHER_AND_FILTER_CALIBRATION_COMPLETE
status   VALID
```

Le reçu `calibration-receipt.json` a :

```text
sha256 = 3bd16cf7a0d49b9c5aa3bdf45837e679846485297ea7aed3d8961fe37f316902
bytes  = 86155
```

Mesures destinées au futur préenregistrement :

```text
teacher_full_timeout_seconds = 390
filter_timeout_seconds_10000 = 1
```

Le job n'a lu aucun parent B2 frais, aucun champ de score teacher pour une
décision scientifique et n'a lancé aucun bootstrap. Il a utilisé 256 parents
teacher historiques uniquement pour la calibration opérationnelle. Son action
suivante déclarée est :

```text
B2_USE_MEASURED_OPERATIONAL_TIMEOUTS_BEFORE_PREREGISTRATION
```

Les anciennes enveloppes larges du wrapper 1777 (`teacher=423`, `filter=120`,
`outer=600`) étaient des plafonds de calibration, pas des paramètres
confirmatoires. Elles ne remplacent pas les mesures ci-dessus.

## 2. Scellé teacher ajouté à X

`jobs/tools/adaptive_sibling_b2_teacher_publish.py` est un publisher
post-recherche strict. Il ne lance aucun search et ne remplace donc pas la
barrière obligatoire avant la première lecture teacher.

Il authentifie :

- le SHA externe du manifeste d'entrée de fusion ;
- le SHA externe et les bytes canoniques du rapport de fusion ;
- le `code_sha` et le schéma `jass.adaptive_sibling_b2_teacher_merge.v1` ;
- les cardinalités parent/action et les compteurs zéro d'actions manquantes,
  supplémentaires ou dupliquées ;
- les bytes `children.jnnw`, `groups.tsv` et du ledger sémantique ;
- le reçu natif embarqué par la fusion et ses compteurs de catalogue légal.

La fusion native supprime volontairement son reçu temporaire après validation.
Le publisher le ré-extrait depuis le rapport scellé et le republie séparément
comme `native-verification-receipt.json`, puis publie exactement la forme déjà
consommée par l'allocation/readout :

```text
schema = jass.adaptive_sibling_b2_teacher_merge_publication.v1
keys   = artifacts, byte_roundtrip_verified, code_sha, input_manifest, schema
```

Les quatre artefacts déclarés sont uniquement :

```text
children_jnnw
groups_tsv
semantic_actions
merge_report
```

Le publisher ne modifie aucun score, aucune observation, aucune policy et aucun
seuil.

## 3. Scellé terminal ajouté à X

`jobs/tools/adaptive_sibling_b2_terminal_publish.py` consomme uniquement un
répertoire déjà produit par `adaptive_sibling_b2_readout.py finalize`.

Il n'appelle pas le noyau statistique et n'évalue aucune gate. Il vérifie :

- le lien du terminal au manifeste d'entrée ;
- le schéma `jass.adaptive_sibling_b2_terminal_readout.v1` ;
- la fermeture du mapping à trois verdicts ;
- la cohérence `all_valid` des huit drapeaux de support ;
- l'association obligatoire entre statistiques `VALID`, `all_gates_passed` et
  verdict `CONFIRMED` / `NOT_CONFIRMED` ;
- la route `SUPPORT_NOT_ESTABLISHED` sans statistiques lorsque le support n'est
  pas disponible ;
- les compteurs `searches/fits/games/promotions/bakes/automatic_downstream_jobs`
  tous nuls ;
- les bytes et descripteurs de `b2-statistics-v1.json` et `progress.json` quand
  ils existent.

Le reçu portable porte :

```text
schema = jass.adaptive_sibling_b2_terminal_publication.v1
automatic_downstream_jobs = 0
promotion_authorized = false
bake_authorized = false
```

La confirmation éventuelle n'enchaîne donc jamais B3 automatiquement.

## 4. Ordre de gel inchangé

La règle de la [publication source #787](L3_ADAPTIVE_SHADOW_B2_SOURCE_PUBLICATION_V1_20260905.md)
reste normative :

```text
X = commit exact contenant toutes les implémentations exécutées
Y = descendant de X qui ne modifie que le Markdown normatif de préenregistrement
F = reçu source/sélection produit après exécution
S = commit documentaire ultérieur qui publie les bytes de F
```

La première lecture teacher doit être précédée de l'authentification de X, Y, S,
F et de la sélection scellée. Le publisher teacher de cette PR est le scellé
post-recherche ; il ne peut pas rendre cette barrière rétroactive.

Conséquence : **Y ne doit pas être créé avant merge et validation de cette
complétion X**.

## 5. Ce qui reste avant donnée fraîche

Après CI/revue de cette PR :

1. merger la complétion des publishers : le merge obtenu devient le candidat X ;
2. fixer les dernières enveloppes du wrapper source autour des mesures 1777 et
   de l'ancre producteur déjà publiée, sans changer la science ;
3. créer un unique commit Y qui ajoute seulement le Markdown normatif B2 ;
4. y geler les 4 000 parents, 8 cellules × 500, seeds 2026110700..2026110717,
   policy `M5=100`, `M50=60`, `minimum_survivors=2`, support et gates déjà
   publiés, runtime CPX62/CPython 3.14.4 et timeouts mesurés ;
5. seulement ensuite lancer la source fraîche target-blind ;
6. auditer F et publier S avant la première lecture teacher ;
7. exécuter teacher → allocation → projection → readout → terminal ;
8. STOP sur l'un des trois verdicts B2.

Aucun de ces travaux ne change `CURRICULUM` ni n'autorise une promotion.
