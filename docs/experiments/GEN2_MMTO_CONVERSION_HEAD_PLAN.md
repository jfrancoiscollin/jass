# Gen2-MMTO — expert de conversion P3 (CVH1)

> **Statut :** screen initial passé ; C10 sélectionné ; suivi généraliste préparé
> **Implémentation :** PR #353 mergée (`61c0e20f`), optimisation NPS `6bfc700fc`
> **Campagne active :** Gen2-MMTO gelé uniquement ; aucune intégration L3

## 1. Question causale

À valeur générale Gen2-MMTO strictement inchangée, une petite estimation
leader-relative de la convertibilité permet-elle de mieux choisir les
continuations qui réalisent un avantage matériel de valeur `+1` ?

Le symptôme ciblé est la faiblesse P3 : avantage mince détecté mais mal réalisé.
Ce test ne remplace pas la loss WDL et ne modifie pas la campagne L3.

## 2. Invariant principal : Gen2-MMTO gelé

Le champion `.pjtw` n'est jamais réécrit ni requantifié.

Le candidat est constitué de deux fichiers :

```text
candidate.pjtw      # copie byte-identique du champion
candidate.pjtw.cvh  # petite tête CVH1 optionnelle
```

Le packer compare les SHA-256 du champion et de la copie et échoue si les octets
diffèrent. Sans sidecar, le loader suit exactement le chemin historique. Un
sidecar présent mais invalide fait échouer le chargement.

## 3. Domaine du MVP

Valeur matérielle : homme = 1, dame = 3.

La tête n'est active que lorsque :

- la marge matérielle absolue vaut exactement `1` ;
- le nombre total de pièces est au moins `8` ;
- activation pleine de `8` à `12` pièces ;
- décroissance linéaire entre `12` et `20` ;
- activation nulle à partir de `20` pièces.

Les positions à sept pièces ou moins sont laissées au domaine exact EGDB. P4
matériel égal reste hors périmètre.

## 4. Features CVH1

Toutes les features sont exprimées par rapport au leader et au défenseur :

1. nombre total de pièces ;
2. hommes du leader ;
3. dames du leader ;
4. hommes du défenseur ;
5. dames du défenseur ;
6. mobilité du leader ;
7. mobilité du défenseur ;
8. différence de mobilité ;
9. centralité des dames du leader ;
10. centralité des dames du défenseur ;
11. avancement des hommes du leader ;
12. avancement des hommes du défenseur ;
13. hommes du leader à une ligne de la promotion ;
14. hommes du défenseur à une ligne de la promotion ;
15. déséquilibre gauche/droite du leader ;
16. déséquilibre gauche/droite du défenseur.

Aucune feature n'utilise le futur, l'ouverture, un score de recherche, Scan ou
l'appartenance à un pool de mesure.

## 5. Modèle et correction

La cible auxiliaire est `1` si le leader matériel courant gagne la partie, `0`
si la partie est nulle ou si le leader perd.

```text
raw       = bias + Σ weight_i × standardized_feature_i
centered  = raw - center_logit
delta_cp  = leader_sign × phase_gate × lambda_cp × tanh(centered / tanh_scale)
```

La correction est bornée par `lambda_cp` et antisymétrique par couleur.

## 6. Contrat de données

Le split train/holdout est fait par partie ou paire d'ouverture, jamais par
ligne. Chaque groupe reçoit une masse totale comparable dans la loss.

Interdictions :

- PC Blues ou pool de mesure au training ;
- `conv_self_eval_set.fen` au training ;
- labels Scan, teacher ou deep-relabel externe ;
- fine-tune des poids Gen2-MMTO.

## 7. Résultat offline

Mesure ccx33 :

| Métrique | Valeur |
|---|---:|
| débit self-play Gen2 | 33 100 positions/min |
| positions P3 éligibles | 8 985 |
| holdout log-loss tête | 0,683 |
| intercept seul | 0,699 |
| gain absolu | +0,016 |

Verdict offline : `head_discriminates`.

## 8. Screen initial A/Z/C5/C10/C20

Job : `ccx33-0813-cvh-p3-screen`, `n=180` par cellule, défenseur Gen2 fixe.

| Cellule | Conversion P3 | Δ vs A |
|---|---:|---:|
| A | 0,500 | — |
| Z (`lambda=0`) | 0,500 | 0,000 |
| C5 | 0,500 | 0,000 |
| **C10** | **0,522** | **+0,022** |
| C20 | 0,494 | -0,006 |

Le contrôle A/Z passe (`az_ok=True`). C10 franchit le seuil pré-enregistré
`ΔP3 >= +0,02`. C20 montre une sur-correction. Aucun nouveau sweep de lambda
n'est autorisé avant confirmation : **C10 est gelé comme seul candidat**.

Verdict : `candidate_for_generalist_screen`.

## 9. Correctif NPS

Le screen 0813 a montré environ `-44 %` de NPS parce que les 16 features étaient
calculées avant la vérification du gate. Le commit `6bfc700fc` effectue d'abord
un pré-gate par `popcount` (marge + nombre de pièces), puis extrait les features
uniquement lorsque le gate est actif.

Le delta reste identique dans les positions actives. Le sweep de conversion n'a
pas à être rejoué ; seule la vitesse post-correctif doit être remesurée.

## 10. Suivi pré-enregistré

La suite est divisée en trois jobs séparés pour conserver des décisions causales
et un go explicite avant chaque coût supplémentaire.

### Étape 1 — NPS post-correctif puis common-search

Template : `jobs/templates/cvh-p3-postfix-nps-common-v1.sh`.

Mesures appariées A/Z/C10 sur les mêmes positions et profondeurs :

- corpus généraliste hors gate à la racine ;
- corpus P3 actif ;
- contrôle exact des coups A/Z.

Gates par défaut :

- zéro erreur et zéro divergence de coup A/Z ;
- ratio NPS général C10/A `>= 0,98` ;
- ratio Z/A dans `[0,99 ; 1,01]` ;
- common-search C10 vs A : `n >= 64`, score ponctuel `>= 0,49`, et borne haute
  de l'IC 95 % au moins égale à `0,50`.

Échec NPS : arrêt avant match. Échec common-search : arrêt avant movetime.

### Étape 2 — movetime court

Template : `jobs/templates/cvh-p3-movetime-v1.sh`.

- exige le JSON `common_search_pass` ;
- ouvertures déterministes strictement disjointes de l'étape 1 ;
- même binaire, même recherche, même temps pour A et C10 ;
- gate par défaut identique : `n >= 64`, score `>= 0,49`, borne haute IC >= 0,50.

Échec : `conversion_gain_not_bakeable`. Passage : confirmation P3 autorisée.

### Étape 3 — confirmation P3 appariée haut N

Template : `jobs/templates/cvh-p3-confirm-v1.sh`.

- exige le JSON `movetime_pass` ;
- pool indépendant du fit et du screen 0813 ;
- sous-pool gelé de 600 positions P3 décisives par défaut ;
- A et C10 jouent exactement les mêmes indices contre le même défenseur A ;
- plancher apparié `n >= 400` ;
- gain `>= +0,02` ;
- borne basse de l'IC apparié 95 % strictement supérieure à zéro.

Passage final : `candidate_for_l3_fork`. Sinon : `p3_not_confirmed`.

## 11. Outils de garde

- `tools/cvh_nps_ab.py` : benchmark fixe apparié, nodes/s, temps/recherche,
  erreurs et divergence A/Z ;
- `jobs/tools/cvh_followup_verdict.py` : agrégation des shards et gates fail-closed ;
- `pattern_jass/tests/test_cvh_followup.py` : filtres, IC, pairing et `bash -n`.

Les templates exigent : commit `6bfc700fc`, identité byte-à-byte des PJTW,
sidecars corrects, garde disque, `nproc`, timeout par shard, PIDs explicites,
smoke write/read, ETA approuvée et `JFC_GO=1`.

## 12. Hors périmètre

- aucun script n'est placé dans `jobs/queue` ;
- aucun job n'est lancé par cette PR ;
- aucun corpus ou chemin d'artefact n'est deviné ;
- aucune modification de `docs/L3_CURRENT.md`, `docs/L3_PURE_PLAN.md` ou
  `docs/PROJECT_RESULTS.md` avant verdict scientifique complet ;
- aucune intégration à la nouvelle lignée avant confirmation.
