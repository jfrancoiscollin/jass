# Gen2-MMTO — expert de conversion P3 (CVH1)

> **Statut :** infrastructure proposée, aucun job lancé
> **Branche :** `agent/gen2-mmto-conversion-head`
> **Cible de PR :** `develop`

## 1. Question causale

À valeur générale Gen2-MMTO strictement inchangée, une petite estimation
leader-relative de la convertibilité permet-elle de mieux choisir les
continuations qui réalisent un avantage matériel de valeur `+1` ?

Le symptôme ciblé est la faiblesse P3 : avantage mince détecté mais mal réalisé.
Ce test ne remplace pas la loss WDL et ne modifie pas la campagne L3 active.

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

Cette conception remplace volontairement le PJTW-v5 envisagé dans le premier
mémo : elle réduit le risque de compatibilité et rend le contrôle `lambda=0`
plus lisible.

## 3. Domaine du MVP

Valeur matérielle :

```text
homme = 1
dame  = 3
```

La tête n'est active que lorsque :

- la marge matérielle absolue vaut exactement `1` ;
- le nombre total de pièces est au moins `8` ;
- activation pleine de `8` à `12` pièces ;
- décroissance linéaire entre `12` et `20` ;
- activation nulle à partir de `20` pièces.

Les positions à sept pièces ou moins sont laissées au domaine exact EGDB.
P4 matériel égal est hors périmètre : le leader ne peut pas y être défini sans
un mécanisme supplémentaire.

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

Le fit auxiliaire est une logistique binaire :

```text
y = 1  si le leader matériel courant gagne la partie
y = 0  si la partie est nulle ou si le leader perd
```

La sortie est recentrée par le logit de prévalence du train. Au runtime :

```text
raw       = bias + Σ weight_i × standardized_feature_i
centered  = raw - center_logit
delta_cp  = leader_sign × phase_gate × lambda_cp × tanh(centered / tanh_scale)
```

La correction est donc bornée par `lambda_cp` et antisymétrique par couleur.

## 6. Contrat de données

Le fit exige un identifiant de groupe par ligne JNNW. Le groupe doit représenter
au minimum une partie, idéalement une paire d'ouverture.

Le split train/holdout est fait par groupe complet. Un split aléatoire par ligne
est interdit. Chaque groupe reçoit une masse totale comparable dans la loss pour
qu'une partie longue ne domine pas le fit.

Interdictions :

- PC Blues au training ;
- `conv_self_eval_set.fen` au training ;
- pool de gate au training ;
- labels Scan, deep-relabel externe ou teacher ;
- fine-tune des poids Gen2-MMTO.

## 7. Fichiers et outils

- `src/conversion_head.hpp/.cpp` : format, features, gate et wrapper runtime ;
- `pattern_jass/tools/conversion_head.py` : contrat Python identique ;
- `pattern_jass/tools/train_conversion_head.py` : fit groupé ;
- `pattern_jass/tools/pack_conversion_head.py` : copie immuable + sidecar ;
- tests C++ et Python couvrant gate, signes, format et absence de fuite de groupe.

Exemple de fit, à ne lancer qu'après résolution de la provenance et accord JFC :

```bash
python pattern_jass/tools/train_conversion_head.py \
  --data corpus.jnnw \
  --groups game_ids.npy \
  --out-json head.json \
  --lambda-cp 10
```

Création de cellules sans refaire le fit :

```bash
python pattern_jass/tools/pack_conversion_head.py \
  --champion gen2-mmto.pjtw \
  --head-json head.json \
  --out candidate-l10.pjtw \
  --lambda-cp 10
```

## 8. Screen pré-enregistré proposé

Cellules :

| Cellule | Description |
|---|---|
| A | Gen2-MMTO original, aucun sidecar |
| Z | copie identique + CVH1 avec `lambda_cp=0` |
| C5 | même tête, `lambda_cp=5` |
| C10 | même tête, `lambda_cp=10` |
| C20 | même tête, `lambda_cp=20` |

Ordre :

1. tests et contrôle A/Z ;
2. microbenchmark NPS ;
3. conversion P3 avec défenseur Gen2-MMTO fixe ;
4. common-search généraliste ;
5. movetime court ;
6. confirmation haut N seulement en cas de signal.

Seuil de passage du screen : amélioration P3 ponctuelle d'au moins `+0,02`,
sans régression généraliste établie ni coût NPS prohibitif.

## 9. Décisions possibles

- `better_fit_no_play_signal` : diagnostics hors ligne meilleurs, jeu plat ;
- `conversion_gain_not_bakeable` : P3 meilleur mais force générale en baisse ;
- `candidate_for_l3_fork` : P3 et force non régressive, à confirmer ;
- `no_signal_close` : aucune cellule ne justifie une confirmation.

## 10. Hors périmètre de cette PR

- résolution du chemin et du SHA canonique de Gen2-MMTO ;
- génération d'un nouveau corpus ;
- exécution du screen ;
- modification de `docs/L3_CURRENT.md`, `docs/L3_PURE_PLAN.md` ou
  `docs/PROJECT_RESULTS.md` ;
- intégration à la lignée L3 ;
- P4 et rollouts stochastiques.

Aucun job ne doit être copié dans la queue sans micro-calibration, ETA, contrôles
`CLAUDE.md` et go explicite JFC.
