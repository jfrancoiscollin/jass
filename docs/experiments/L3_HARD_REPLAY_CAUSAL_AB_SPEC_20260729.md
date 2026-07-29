# L3-PURE — replay difficile causal v1

Date : 2026-07-29
Statut : implémentation et micro-smoke prêts ; aucun job lancé par cette PR
Portée : PR 2 du mémo `MEMO_CODEX_JASS_QUALITE_SIGNAL_20260728.md`

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

## 6. Micro-smoke local

Les fixtures locales vérifient :

- déterminisme bit à bit ;
- authentification du manifeste hard ;
- sampling uniforme exact dans le train historique ;
- dose et volume exacts ;
- tail holdout commun ;
- absence de fuite d'ouverture ;
- canari WDL sur les corpus assemblés ;
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
