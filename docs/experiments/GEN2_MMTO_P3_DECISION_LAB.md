# Gen2-MMTO — laboratoire de décision P3 et MMTO-v2

> **Statut :** protocole préparé, aucun job lancé
> **Champion :** Gen2-MMTO gelé
> **Suite de CVH1 :** `weak_directional_signal_not_bakeable`

## 1. Point de départ

La tête CVH1 a gardé le bon signe sur un pool frais de 1 255 positions P3, mais
son gain apparié n'a été que `+0,012` (`0,478 -> 0,490`), sous le seuil
pré-enregistré `+0,020`. Elle ne doit donc pas être intégrée au runtime.

Cette campagne change de question. Elle ne cherche plus à corriger la valeur
absolue d'une position. Elle teste la décision entre coups frères :

1. Gen2 choisit-il parfois un coup qui ne convertit pas alors qu'un frère le fait ?
2. Une seconde passe plus profonde sur les enfants retrouve-t-elle ce frère ?
3. Un ranker de frères apprend-il le signal hors échantillon ?
4. Ce signal peut-il être transféré aux poids Gen2 par un MMTO-v2 through-search ?

Aucun résultat de cette campagne ne modifie la lignée L3.

## 2. Invariants

- le PJTW Gen2-MMTO de référence reste byte-identique ;
- les pools d'autopsie, de screen frais et de confirmation sont disjoints ;
- le gagnant P3 est le leader matériel certifié, homme=1 et dame=3 ;
- chaque erreur, timeout ou restart est un échec technique, jamais une nulle ;
- le défenseur et son fingerprint restent fixes ;
- aucun réglage n'est choisi sur le pool de confirmation ;
- aucun job n'est mis en queue sans SHA mergé, calibration, ETA et go JFC.

## 3. D0 — autopsie des échecs P3

Entrées : pool P3 certifié et résultat baseline `conv_fixed_wdl` schema 2.

Le MVP porte sur les décisions calmes à plusieurs coups. Les positions à capture
obligatoire sont comptées mais différées, car le contrat MMTO historique à deux
octets ne distingue pas toutes les trajectoires de capture de mêmes extrémités.

Pour chaque position que Gen2 n'a pas convertie :

1. rejouer la décision Gen2 au budget baseline ;
2. énumérer tous les enfants légaux ;
3. rechercher chaque enfant au budget de vérification ;
4. conserver les trois meilleurs enfants vérifiés et l'enfant baseline ;
5. jouer chacun contre le même défenseur fixe ;
6. publier l'événement complet et, pour les décisions calmes, une paire
   `bon frère > frère baseline` utilisable par MMTO.

Gate exploratoire :

- au moins 100 parents ;
- au moins 50 paires calmes ;
- un frère sauve au moins 10 % des échecs ;
- la seconde passe retrouve au moins 50 % des sauvetages disponibles.

Un échec ferme la piste décisionnelle. Il ne déclenche pas un nouveau modèle.

## 4. D1 — seconde passe conditionnelle

Le même mécanisme est rejoué sur un pool frais, cette fois sur **toutes** les
positions P3. La politique testée reste extérieure au moteur : elle choisit
l'enfant ayant la meilleure valeur après vérification plus profonde, puis la
conversion est mesurée depuis cet enfant.

Le screen ne passe que si :

- `n apparié >= 400` ;
- `Delta conversion >= +0,020` ;
- borne basse IC95 appariée strictement positive.

Cette étape mesure la valeur maximale plausible d'une seconde passe P3 avant
toute intégration C++ et avant toute étude de coût NPS.

## 5. D2 — ranker de coups frères

Les paires calmes de D0 sont séparées par parent, jamais par ligne. Le ranker
utilise les 16 features leader-relatives de CVH1, soit linéairement, soit avec
interactions quadratiques. La standardisation est calculée sur le train seul.

Le ranker est uniquement un diagnostic offline. Il passe si :

- holdout >= 20 paires ;
- accuracy holdout >= 0,55 ;
- log-loss holdout meilleure que l'intercept `ln(2)`.

Un signal ranker ne justifie pas un sidecar runtime. Il autorise seulement le
fit MMTO-v2 sur les poids existants.

## 6. D3 — MMTO-v2 hard negatives

Les paires D0 sont transformées en feuilles PV par le chemin existant :

```text
jass --gen-siblings ... --leaf-mode --keep-all-pairs
rank_finetune.py --leaf-pov --chunk ...
```

Contraintes reprises des campagnes précédentes :

- through-search obligatoire ;
- warm-start MMTO interdit ;
- champion Gen2 comme ancre ;
- sweep léger d'ancre `{0,05 ; 0,10}` ;
- aucun refit WDL ou CVH concurrent.

Chaque candidat passe ensuite :

1. conversion P3 appariée contre la baseline immuable ;
2. common-search généraliste ;
3. movetime natif ;
4. confirmation fraîche seulement si `Delta P3 >= +0,020`, IC basse > 0 et
   aucune régression de force établie.

## 7. D4 — profil recherche Gen2

En parallèle, un wrapper générique compare des fingerprints de recherche
**entièrement résolus** sur le même PJTW :

- profondeur fixe ;
- movetime natif ;
- conversion P3 optionnelle.

La PR ne préremplit pas de valeurs LMR/NMP/ProbCut/MultiCut : les 63 clés du
fingerprint canonique doivent être résolues avant lancement. Les bras sont
fournis par un TSV `nom|fingerprint_complet`. Cette étape distingue un gain de
recherche généraliste d'un gain d'apprentissage MMTO.

## 8. Fichiers

- `jobs/tools/gen2_p3_decision_lab.py` : autopsie et screen seconde passe ;
- `pattern_jass/tools/p3_sibling_ranker.py` : ranker offline linéaire/quadratique ;
- `jobs/tools/gen2_p3_decision_verdict.py` : gates fail-closed ;
- `jobs/templates/gen2-p3-decision-autopsy-v1.sh` ;
- `jobs/templates/gen2-p3-decision-screen-v1.sh` ;
- `jobs/templates/gen2-p3-mmto-v2-v1.sh` ;
- `jobs/templates/gen2-search-native-profile-v1.sh`.

## 9. Arbre de décision

```text
D0 sans sauvetages                 -> close decision hypothesis
D0 positif, D1 négatif             -> search can rescue anecdotes, not scalable
D1 positif, ranker négatif         -> conditional search only
ranker positif, MMTO-v2 négatif    -> signal not transferable to frozen weights
MMTO-v2 positif                    -> fresh high-N confirmation
```

Aucune branche n'est enchaînée automatiquement.
