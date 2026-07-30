# L3-PURE — replay difficile causal v1

Date : 2026-07-29
Statut : DOE exécuté ; recette v1 close le 2026-07-30
Portée : PR 2 du mémo `MEMO_CODEX_JASS_QUALITE_SIGNAL_20260728.md`

Résultat autoritatif :
[`L3_HARD_REPLAY_READOUT_20260730.md`](L3_HARD_REPLAY_READOUT_20260730.md).
`HARD_REPLAY` fait `222-24-9754` sur 10 000 parties contre
`UNIFORM_REPLAY`, soit 0,023400 et -648,20 Elo. Le verdict est
`L3_PURE_HARD_REPLAY_BELOW_UNIFORM_REPLAY`. La recette
`50 % fresh + 50 % failed_conversion` avec cibles historiques conservées est
close ; elle ne doit pas être relancée à l'identique.

## 1. Question

À parent, fraîcheur, volume, split et fit constants, remplacer un million
d'observations de replay historique tirées uniformément par un million
d'observations sélectionnées sur des échecs de conversion améliore-t-il la
force jouée ?

La comparaison primaire est :

```text
HARD_REPLAY minus UNIFORM_REPLAY
```

Elle ne compare ni une nouvelle profondeur, ni un nouveau parent, ni deux
budgets de données différents.

## 2. Source historique admissible

Le catalogue historique est immuable et authentifié par :

- job, tentative, état et SHA de code ;
- SHA256 JNNW/JSM1 compressés et décompressés ;
- policy de génération, parent, profondeur et mode de label documentés ;
- canari WDL valide ;
- split par `opening_id` reproductible bit à bit.

Le préflight ne reçoit pas de hashes bruts recopiés à la main. Il authentifie
d'abord le certificat de catalogue amont, vérifie les hashes compressés des
artefacts téléchargés, recalcule les hashes bruts et les inscrit dans son
propre certificat. Le job de fit réauthentifie ensuite la même source contre
ce certificat de préflight.

Le split historique est construit avant le mining. Le mineur voit uniquement
le préfixe train ; le holdout historique est exclu des deux bras et ne
participe ni au signal, ni aux quotas, ni au fit.

La dose complète exige exactement 1 000 000 de records hard après
one-per-game, déduplication canonique et miroirs. Une capacité inférieure ferme
le préflight avec le verdict terminal
`L3_PURE_HARD_REPLAY_CATALOGUE_INSUFFICIENT` et
`training_authorized=false`. Elle n'autorise ni une réduction post-hoc de la
dose, ni le lancement du fit.

### Résultat du premier préflight

`home-1042` authentifie le bras UNIFORM de `home-1017` et mesure seulement
58 908 records disponibles après `one-per-game`, déduplication canonique et
miroir couleur (29 454 positions de base), contre 1 000 000 requis. Verdict :
`L3_PURE_HARD_REPLAY_CATALOGUE_INSUFFICIENT`,
`training_authorized=false`. Le DOE décrit ci-dessous n'a donc pas été lancé.
Une source plus large ou un nouveau DOE de dose exigent un préenregistrement
séparé ; ce document n'autorise pas à abaisser la dose après observation.

### Réouverture par source plus large

La source `UNIFORM` 40M est préenregistrée dans
`L3_HARD_REPLAY_LARGE_SOURCE_20260729.md`. Elle conserve parent, policy,
profondeur et calibration post-correctif, avec de nouvelles graines. Son volume
de 40M ajoute 17,8 % de marge à l'extrapolation ponctuelle de 33,95M issue de
`home-1042`. Elle ne modifie ni la dose hard requise de 1M, ni le DOE de fit.
Un nouveau préflight reste obligatoire après sa production.

## 3. Bras causal

| Paramètre | CONTROL | TREATMENT |
|---|---:|---:|
| parent et warm-start | identiques | identiques |
| données fraîches | 1 000 000 communes | les mêmes 1 000 000 |
| replay historique | 1 000 000 uniforme | 1 000 000 `failed_conversion` |
| source historique | identique | identique |
| profondeur de jeu | d8 | d8 |
| label | d4, WDL-only | identique |
| Q00 / 8cf / L2 | identiques | identiques |
| split et holdout | identiques | identiques |
| budget optimiseur | identique | identique |
| total fit | 2 000 000 | 2 000 000 |

Le facteur est la **politique de sélection du replay historique**. La policy
commune qui produit le million frais est épinglée dans le wrapper du job. Si
TOPK3 passe sa porte de succession, elle vaut `topk3` avec `K=3`,
`explore-margin=50` et RNG séparés ; sinon un protocole TURNOVER distinct doit
être préenregistré et ne peut pas réutiliser ce wrapper comme si le parent
n'avait pas changé.

## 4. Holdout commun

Le million frais est généré une seule fois puis séparé par `opening_id`.
L'assembleur construit :

```text
CONTROL   = uniform_replay + fresh_train + fresh_holdout
TREATMENT = hard_replay    + fresh_train + fresh_holdout
```

`fresh_holdout` est le tail des deux fichiers, bit-identique dans les données
et le sidecar JSM1. Ses ouvertures sont disjointes des trains des deux bras.
Les losses qui en résultent sont donc comparables entre bras, mais restent des
diagnostics et ne sélectionnent jamais un modèle.

## 5. Implémentation

- `jobs/templates/l3-pure-hard-replay-preflight-v1.sh`
  authentifie le catalogue historique, reproduit son split, mine deux fois et
  exige une sortie bit-identique de cardinalité exacte ;
- `jobs/tools/l3_hard_replay_assembly.py` échantillonne le contrôle uniforme
  uniquement dans le train historique et assemble les deux corpus avec le
  holdout commun ;
- `jobs/templates/l3-pure-hard-replay-train-v1.sh` génère le frais une fois,
  vérifie la policy effective, assemble, profile et fitte les deux bras
  séquentiellement ;
- les deux templates épinglent code, entrées, parent, graines, Q00, volume et
  budget de fit, publient les codes de sortie producteurs et échouent fermés.

Le préflight et le fit sont deux jobs distincts. Aucun second job n'est lancé
automatiquement.

### Portabilité de la pile scientifique

Le fit exige des versions NumPy et SciPy complètes (`x.y.z`) fournies par le
wrapper. Les deux bras utilisent le même environnement isolé et le certificat
publie les versions Python, NumPy et SciPy réellement importées. Les valeurs
par défaut historiques restent NumPy 1.26.4 et SciPy 1.14.1, mais un hôte dont
la version de Python ne possède plus ces roues doit fournir de nouveaux pins
explicites compatibles. Il n'existe aucun fallback implicite vers « latest ».

Le SHA du préflight est authentifié séparément du SHA du job de fit. Une
correction strictement opérationnelle du fit peut ainsi réutiliser un catalogue
immuable déjà validé, à condition que son job, son attempt, son état, son SHA
de code et tous ses hashes soient encore vérifiés. L'assembleur reçoit donc
deux identités distinctes : `code_sha` pour le code qui assemble et entraîne,
et `hard_manifest_code_sha` pour authentifier le manifeste miné immuable.

La source historique 40M ne doit jamais être matérialisée en objets Python.
L'assembleur vérifie ses en-têtes, son split et ses hashes en flux, calcule
l'échantillon uniforme exact avec l'algorithme déterministe préenregistré, puis
ne conserve en mémoire que la dose sélectionnée. Le manifeste final certifie
`history.read_mode=streaming_exact_sample`. Cette contrainte de ressources ne
change ni les indices tirés, ni leur ordre source, ni aucun facteur scientifique.

L'assembleur est lancé comme module depuis la racine du dépôt
(`python3 -m jobs.tools.l3_hard_replay_assembly`). L'appel direct par chemin est
interdit : Python remplacerait la racine dans `sys.path` par `jobs/tools` et
l'import authentifié de `tools.selfplay_frontier` échouerait avant l'assemblage.

## 6. Micro-smoke local

Les fixtures locales vérifient :

- déterminisme bit à bit ;
- authentification du manifeste hard ;
- sampling uniforme exact dans le train historique ;
- lecture streaming de la source historique, sans appel à `read_pair` ;
- dose et volume exacts ;
- tail holdout commun ;
- absence de fuite d'ouverture ;
- canari WDL sur les corpus assemblés ;
- garde de distribution WDL complète sur le frais brut et le contrôle
  uniforme ;
- histogramme WDL publié mais seulement diagnostique sur le traitement :
  `failed_conversion` est sélectionné à partir de l'issue terminale, donc sa
  part de nulles comme son équilibre W/L STM sont conditionnés par
  construction ; le miroir couleur préserve ce WDL et ne peut pas le
  rééquilibrer. Le domaine des labels, les hashes et le manifeste restent
  vérifiés strictement ;
- refus d'écraser une sortie ;
- échec fermé sur manifeste, compte ou split divergent ;
- contrat statique des deux templates et syntaxe Bash.

Le micro-smoke n'est ni un fit scientifique, ni un screen Elo.

## 7. Readout futur

Après deux fits convergés et authentifiés seulement :

- `HARD_REPLAY` contre `UNIFORM_REPLAY` ;
- au moins 2 500 ouvertures fraîches appariées et disjointes ;
- deux couleurs ;
- Q00 et native 0,1 s/coup ;
- W/D/L, score, Elo, IC90 et IC95 par vue et additionnés ;
- couverture, densité, diversité, duplication et conversion P1–P4.

Le point estimate additionné est publié sans l'arrondir. Les intervalles
quantifient l'incertitude ; ils ne sont pas remplacés par la loss holdout.
Ce DOE peut retenir une direction expérimentale, pas promouvoir
automatiquement un champion.

```json
{
  "promotion_authorized": false,
  "automatic_next_job": null,
  "external_teacher_inputs": 0
}
```

## 8. Séquencement

1. fermer la porte de succession TOPK3 et, si elle passe, baker le parent ;
2. lancer le préflight hard sous un nouvel identifiant ;
3. examiner la capacité et le certificat ;
4. lancer le fit A/B sous un autre identifiant ;
5. préenregistrer le pool indépendant avant le readout ;
6. ne poursuivre vers les reverse seeds qu'après le verdict hard replay.

Aucun oracle, teacher, moteur externe, reweight V2, suppression de box ou
mélange avec `L3-IMBALANCE2` n'entre dans ce protocole.
