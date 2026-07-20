# L3 — rôles des lignées et extension de maturité

> **Statut : décision de programme — 21 juillet 2026**
> **Portée :** clarifier la relation entre `L3-PURE`, `L3-IMBALANCE2` et le champion historique `gen2-mmto`.

## 1. Deux objectifs distincts

### `L3-PURE` — lignée généraliste autonome

`L3-PURE` est la seule lignée destinée à produire une évaluation généraliste autonome et, si les résultats le permettent, un successeur au champion historique `gen2-mmto`.

Son contrat reste : graine matérielle, autojeu uniquement, résultats terminaux WDL, aucun teacher moteur, aucune position externe, aucun MMTO et aucun anchor vers Gen2. Scan et Gen2 peuvent mesurer la lignée, mais ne participent jamais à son entraînement.

Le résultat C0 du bras pur A-G3 est donc un résultat majeur : après seulement trois générations de 500 000 records frais, il a obtenu un score de `0,497` contre `gen2-mmto`, soit une parité pratique dans ce protocole. Ce résultat ne prouve pas encore une supériorité ni un plafond, mais il démontre qu'une lignée linéaire entièrement autonome peut rejoindre le champion historique avec un volume encore faible au regard de la géométrie 8cf.

### `L3-IMBALANCE2` — laboratoire spécialiste

`L3-IMBALANCE2` et sa variante `ROLE-V2` ne sont pas des lignées candidates au remplacement généraliste de `L3-PURE` ou de `gen2-mmto`.

Elles répondent à une question bornée : peut-on apprendre une compétence spécialisée de conversion et de résilience dans les positions présentant exactement deux hommes d'écart ? Leurs pools, leurs pondérations et leurs gates sont spécialisés. Un résultat favorable sur ces pools ne constitue pas un Elo généraliste et n'autorise pas une promotion comme moteur principal.

La mention « référence V2 » signifie uniquement **référence interne du track spécialiste**. Elle ne signifie ni champion généraliste, ni parent de `L3-PURE`, ni remplaçant de Gen2.

Au mieux, un spécialiste confirmé pourrait devenir ultérieurement :

- un sidecar ou correcteur borné ;
- une composante d'une méta-évaluation ;
- un expert appelé par un routeur de domaine.

Toute combinaison avec `L3-PURE` devra faire l'objet d'une expérience séparée, avec activation bornée, comparaison à budget égal, garde de débit et non-régression généraliste. Aucun mélange de poids ou de données n'est autorisé par les résultats actuels.

## 2. Pourquoi poursuivre `L3-PURE` reste rationnel

La parité C0 a été obtenue après trois générations seulement, à 500 000 records par génération. Les audits de couverture indiquent que la géométrie 8cf reste fortement sous-alimentée :

- environ `5,9 %` de buckets visités sur un corpus de 300 000 records ;
- environ `9,0 %` sur 1,5 million de records agrégés dans l'audit X1 ;
- seulement `1,0 %` des buckets atteignent au moins 100 visites ;
- Gini des visites d'environ `0,85`.

Ces chiffres montrent une forte famine de représentation. Ils ne prouvent toutefois pas qu'ajouter mécaniquement des générations identiques fera monter l'Elo.

Chaque génération courante refitte principalement sur un corpus frais. Si l'optimiseur converge, le warm-start est d'abord une initialisation numérique : il ne transforme pas automatiquement trois corpus de 500 000 records en un fit cumulatif de 1,5 million. Pour nourrir réellement les buckets, il faut mesurer séparément :

1. l'effet de générations supplémentaires à recette identique ;
2. l'effet d'un corpus plus grand dans un même fit ;
3. l'effet d'une mémoire explicite par replay ou cumul de données.

## 3. Extension recommandée : `L3-PURE-MATURITY`

Cette extension est indépendante du track `L3-IMBALANCE2`.

### M0 — choisir et figer le parent généraliste

Comparer sur les mêmes ouvertures appariées et couleurs inversées :

1. C0 A-G3, modèle ayant obtenu `0,497` contre Gen2 ;
2. la baseline générale propre `0842` G4, avec Q00 et les 63 paramètres explicitement épinglés ;
3. `gen2-mmto`, figé.

Le but est de ne pas confondre la force démontrée de l'ancien C0 avec la propreté méthodologique de la baseline Q00. Le modèle retenu devient le parent immuable de M1. Ce benchmark ne fournit aucune donnée d'entraînement.

### M1 — séparer maturité, volume et mémoire

Depuis le même parent et avec la même recherche de génération :

- **F500 — contrôle :** 500 000 records frais ;
- **F2M — volume :** 2 millions de records frais dans un même fit ;
- **R2M — mémoire :** 500 000 records frais plus 1,5 million de records historiques de la même lignée, avec provenance et split par ouverture conservés.

Les trois bras doivent utiliser la même architecture 8cf, le même objectif WDL, le même L2 initial, le même budget d'optimisation convergé et aucun teacher. Le bras replay est une expérience de mémoire, pas une continuation automatique.

### Mesures obligatoires

- Elo contre le parent et contre `gen2-mmto` à recherche commune ;
- réplication au movetime ;
- conversion globale et P1–P4 ;
- couverture non nulle, `ge_10`, `ge_100`, Gini et nouvelles visites ;
- log-loss holdout non pondérée ;
- diversité des ouvertures et positions ;
- débit et NPS.

### Règle de décision

Une simple baisse de loss ou une hausse de couverture ne suffit pas. Un bras mérite une continuation seulement s'il montre simultanément :

- une pente de force positive contre le parent ;
- aucune régression établie contre Gen2 ou sur la conversion ;
- une amélioration mesurable de la couverture utile ;
- un coût de calcul compatible avec le gain.

Deux étapes consécutives sans pente de force positive ferment la continuation mécanique de la recette testée. Aucun résultat M0/M1 ne déclenche automatiquement une promotion ou une campagne longue.

## 4. Lecture de programme

- `gen2-mmto` reste le champion historique figé tant qu'un candidat généraliste n'a pas passé un gate de force complet.
- `L3-PURE` est la voie générale et mérite une expérience de maturité contrôlée.
- `L3-IMBALANCE2` reste un laboratoire spécialiste indépendant ; son éventuelle valeur future réside dans une combinaison bornée avec `L3-PURE`, pas dans son remplacement.
