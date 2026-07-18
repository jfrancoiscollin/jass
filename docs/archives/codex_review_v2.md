# Revue Codex v2 — stratégie d’apprentissage de la conversion

> **Date : 2026-07-15**  
> **Statut : proposition technique amendée pour nouvelle revue par Fable / Claude Code**  
> **Relation aux documents précédents :** cette v2 ne remplace pas `codex_review.md`. Elle le conserve comme première formulation du diagnostic, puis intègre la contre-revue « Revue Codex v2 — AMENDEMENTS CLAUDE » et la réponse de Codex à ces amendements.  
> **Périmètre :** améliorer la conservation et la réalisation des positions gagnantes sans changer de classe de modèle.  
> **Règle projet :** aucun NNUE ; rester dans l’évaluation linéaire-patterns tant que son meilleur fit n’est pas atteint.

---

## 0. Résumé exécutif

Le diagnostic central de la v1 est maintenu : **Jass manque d’un mécanisme de crédit causal du coup de conversion**.

Le self-play WDL actuel sait dire qu’une partie a finalement été gagnée, nulle ou perdue. Il ne fournit pas directement l’information locale suivante :

```text
position certifiée WIN
├── coup effectivement joué       → enfant DRAW/LOSS
└── frère jamais joué             → enfant WIN
```

Le véritable actif nouveau d’un `conversion_teacher` est donc **l’information contrefactuelle produite par l’énumération des frères et leur notation par un oracle**. Le moteur découvre un enfant gagnant qu’aucune trajectoire jouée n’avait visité et localise le coup précis qui a abandonné le gain.

La v1 supposait trop rapidement que cette information devait être injectée par une rank-loss statique. L’historique du projet oblige à séparer :

- **l’information**, probablement précieuse ;
- **la forme de loss**, potentiellement dangereuse.

Trois amendements structurants sont adoptés.

### M1 — Smoke teacher à quatre cellules

Le premier test ne sera plus un simple A/B « WDL seul contre rank-finetune ». Les mêmes événements contrefactuels alimenteront quatre cellules :

```text
A   baseline WDL adjudicated seule
B1  A + frères oracle ajoutés comme enregistrements WDL ordinaires
B2  A + rank-finetune STATIQUE sur les paires good > bad
B3  A + rank-finetune THROUGH-SEARCH / leaf-mode sur les mêmes décisions
```

Ce plan tranche séparément la valeur de l’information, de la calibration WDL et de la forme préférence.

### M2 — Le verdict du gymnase attend la jauge WDL-grounded

`0722` a montré que le gymnase ×4 n’ajoutait pas de force généraliste mesurable à T1. Il n’a pas prouvé proprement que la conversion ne montait pas, car la jauge `conv_self.py` déterminait le camp gagnant par le matériel et ignorait précisément les positions `p4_egal`, dominantes dans le nouveau tip.

La conclusion correcte devient :

> **le gymnase statique ×4 n’a pas composé avec la force générale à T1 ; son effet réel sur la conversion reste à mesurer avec la jauge WDL-grounded et le factoriel complet.**

La PR #329 a été fusionnée. `0723` a échoué pour une cause technique d’OOM ; `0724`, identique avec cache réduit, était en cours lors de la rédaction de cette v2. Son résultat doit précéder toute conclusion ferme sur l’effet GYM.

### M3 — Sonde courte et campagne longue sont deux régimes différents

La boucle T1-bis→T3 proposée dans la v1 devient une **sonde de direction**. Elle peut s’arrêter rapidement, mais elle ne clôt pas scientifiquement la piste.

La campagne complète, une fois les briques validées, reste gouvernée par la doctrine L3 de long terme : montée des barreaux de professeur, gymnase réellement saturé, métriques établies et plateau confirmé pendant plusieurs tours au dernier régime pertinent.

### Réserve principale — hiérarchie `CERT`

Le principe `TB > preuve robuste > recherche stable > ambigu` est adopté. En revanche, une ancienne certification d14 ne doit pas dominer automatiquement un nouveau relabel simplement parce qu’elle est appelée « CERT ». Un certificat doit embarquer sa provenance, sa marge et idéalement une preuve d’atteinte TB ou une stabilité d14/d16.

### Verdict global v2

La voie rationnelle est désormais :

1. finir le DOE WDL-grounded ;
2. lancer une sonde multi-tours à labels propres et quota de positions ;
3. miner les premiers jets de gain et leurs frères oracle ;
4. comparer quatre canaux d’injection de la même information ;
5. intégrer le canal gagnant dans une campagne longue ;
6. n’ouvrir `DEEP_EG` que si le signal local est réel mais ne se traduit pas dans le jeu.

---

## 1. Ce qui change par rapport à `codex_review.md`

### 1.1 Éléments conservés

La v2 conserve les éléments suivants de la v1 :

- le trou principal est en aval de la détection des combinaisons ;
- les labels d14+EGDB sont un préalable à une boucle L3 sérieuse ;
- la répétition brute de lignes ne vaut pas un curriculum de trajectoires fraîches ;
- le quota du gymnase doit être défini en **positions produites**, pas seulement en parties ;
- MTC comme cible globale reste une voie fermée ;
- MTC dans la recherche et comme métrique reste utile ;
- une banque linéaire `DEEP_EG` est une piste conditionnelle, pas la prochaine étape ;
- la métrique native du teacher est la **win-preservation** ;
- la promotion doit exiger conversion réelle et non-régression généraliste.

### 1.2 Éléments corrigés

La v2 corrige quatre formulations de la v1 :

1. **« Le gymnase ne monte pas la conversion »** devient **« 0722 ne pouvait pas trancher proprement l’effet conversion du gymnase sur `p4_egal` »**.
2. **« La brique manquante est une rank-loss »** devient **« la brique manquante est l’information contrefactuelle ; la meilleure loss doit être testée »**.
3. **« Deux tours plats permettent d’arrêter »** devient une règle réservée à une sonde, jamais à la campagne complète.
4. **« CERT domine le draw-band »** devient une hiérarchie de preuves versionnée et vérifiable, non un simple statut hérité.

### 1.3 Correction factuelle MMTO

La contre-revue mentionnait un MMTO à environ +47 Elo. Les artefacts relus montrent plutôt :

- premier A/B : environ +33 Elo sur le corpus généraliste, neutre sur DILF ;
- confirmation : environ +23 Elo hors intervalle sur les budgets testés.

La substance reste inchangée : le ranking statique a été catastrophique, tandis que le signal through-search a été positif et confirmé.

---

## 2. Faits établis à ne plus rediagnostiquer

## 2.1 Le trou principal est la conversion, pas la détection

Le thermomètre PC Blues a montré que Jass et Scan détectent les premiers coups à des taux proches, alors que leur conversion diverge massivement. L’augmentation de budget n’a pas révélé une offre calme systématiquement enterrée par le search de Jass.

Conséquence :

- ne pas rouvrir LMR, cuts, dense-NPS ou préférences humaines générales comme causes premières du trou ;
- utiliser les combinaisons et finales comme oracles, seeds et instruments de conversion ;
- concentrer l’apprentissage sur la conservation du gain et les transitions vers la tablebase.

## 2.2 Les labels profonds protègent le fit

`0722`, sur support strictement apparié, a montré :

- 105 000 positions communes ;
- 61,5 % de labels modifiés par le relabel profond ;
- on-policy autour de −46 Elo contre le bootstrap ;
- adjudicated autour de +3 Elo ;
- effet label d’environ +49 Elo.

L’adjudication ne garantit pas à elle seule une meilleure conversion immédiate. Elle empêche surtout le modèle d’apprendre les issues erronées d’un pilote jeune.

## 2.3 `0722` n’a pas tranché l’effet conversion du gymnase

La cellule `adjudW4` n’a pas battu `adjudW0` en force générale. Ce résultat reste valide.

La métrique conversion de ce run était toutefois inadéquate pour la strate dominante du tip :

- le camp testé était choisi à partir de l’avantage en nombre de pièces ;
- une position à matériel égal pouvait être exclue ;
- `p4_egal` représente une part majeure du tip certifié ;
- les tailles de témoins différaient entre cellules.

La formulation désormais autorisée est :

> **W4 n’a pas composé au premier tour avec la force générale. L’effet conversion pur doit être relu par `conv_fixed_wdl.py`, avec les mêmes positions, le gagnant dérivé du label d14+EGDB et une comparaison appariée.**

## 2.4 Les préférences statiques ont un historique défavorable

Le rank-finetune statique sur parents/enfants a déjà produit :

- une forte hausse de pairwise accuracy ;
- jusqu’à environ −847 Elo sur le généraliste ;
- environ −135 Elo pour les préférences positives PC Blues.

Cela démontre qu’une bonne accuracy sur paires ne prouve ni calibration, ni force, ni conversion.

## 2.5 Through-search est le seul canal préférence ayant composé

Le pipeline MMTO génère les frères, cherche chaque branche jusqu’à une feuille et entraîne l’ordre sur les feuilles réellement comparées par le search. Après correction du POV, il a produit un gain généraliste positif et confirmé.

Cela ne prouve pas que through-search gagnera sur les événements de conversion. Cela justifie de le tester comme canal séparé et de ne pas promouvoir une rank-loss statique par défaut.

## 2.6 Les boucles peuvent être non monotones

L’historique contient :

- des T1 faibles suivis d’un T2 beaucoup plus fort ;
- des campagnes qui culminent puis régressent ;
- des améliorations de métriques de finale qui dégradent l’Elo ;
- des gains rapides qui disparaissent au volume ou à la confirmation.

Une lecture tour-par-tour doit donc distinguer :

- progression de compétence ;
- bruit de juge ;
- changement de distribution ;
- conflit de phase ;
- perte de calibration générale.

---

## 3. Hypothèse centrale amendée

### 3.1 Le problème du WDL global

Le générateur propage le résultat final à toutes les positions visitées. Ce signal est utile pour apprendre une value-function globale, mais il attribue mal le crédit lorsque plusieurs décisions ont précédé l’issue.

Exemple :

```text
P0 : WIN
P1 après bon coup : WIN
P2 après manœuvre neutre : WIN
P3 après faute : DRAW
partie finale : DRAW
```

Un label global de partie peut marquer P0, P1 et P2 comme DRAW alors qu’ils étaient encore gagnants. Un relabel profond corrige leur valeur, mais ne révèle pas automatiquement quel frère de P3 conservait le gain.

### 3.2 Information contrefactuelle recherchée

Pour chaque parent critique P :

```text
Oracle(P) = WIN
C_played = enfant du coup joué
Oracle(C_played) = DRAW ou LOSS
∃ C_alt : Oracle(C_alt) = WIN
```

Le teacher doit produire :

- le parent ;
- le coup joué ;
- le premier enfant où le verdict chute ;
- les frères légaux ;
- le verdict oracle de chaque frère ;
- la provenance et la confiance de chaque verdict ;
- le contexte de partie et la strate de finale.

### 3.3 Ce qui reste à trancher

Une fois l’information extraite, trois formes d’injection sont plausibles :

1. **WDL ordinaire sur les enfants immédiats** ;
2. **ranking statique sur les enfants immédiats** ;
3. **ranking through-search sur les feuilles de leurs branches**.

Aucune ne doit être considérée comme gagnante avant le smoke à quatre cellules.

---

## 4. M1 — Smoke teacher à quatre cellules

## 4.1 Principe expérimental

Toutes les cellules partent de la même baseline WDL-adjudicated, du même binaire, des mêmes événements, des mêmes splits et du même budget effectif de teacher.

```text
A   baseline
B1  baseline + frères WDL
B2  baseline + ranking statique
B3  baseline + ranking through-search
```

Le facteur expérimental n’est que le canal d’injection.

## 4.2 Cellule A — contrôle

A est la baseline exacte du tour :

- corpus généraliste adjudicated ;
- même ancrage ;
- même L2 ;
- mêmes options de fold et d’extras ;
- aucun enregistrement teacher ;
- aucun fine-tune supplémentaire.

Elle doit être reconstruite dans le même job, pas référencée uniquement par un ancien artefact, afin d’éviter les différences de SHA et de paramètres.

## 4.3 Cellule B1 — frères comme WDL ordinaires

Pour chaque événement, ajouter au corpus :

```text
C_good : label WIN
C_bad  : label DRAW ou LOSS
```

Les labels viennent de la hiérarchie d’oracle définie au §6.

### Avantages attendus

- reste dans la loss logistique WDL principale ;
- conserve la calibration absolue ;
- évite une nouvelle loss spécialisée ;
- le ranking good>bad est impliqué par les cibles ;
- réutilise le trainer de production.

### Risques

- déséquilibre WIN/DRAW du corpus ;
- surpondération de quelques parents à beaucoup de frères ;
- enfant immédiat trop éloigné de la distribution des feuilles réellement consultées ;
- conflit avec le corpus généraliste ;
- difficulté de la classe à calibrer des positions proches de frontière.

### Règles de poids

Un parent ne doit jamais peser proportionnellement au nombre de ses frères.

```text
poids_teacher_total_par_parent = constant
poids_par_ligne = poids_parent / nombre_de_lignes_du_parent
```

Le premier smoke peut limiter à :

- un `C_bad` : le coup réellement joué qui jette ;
- un ou deux `C_good` sélectionnés parmi les meilleurs frères WIN ;
- au maximum une paire WIN>DRAW et une paire WIN>LOSS par parent.

Les manifests doivent rapporter :

- nombre de parents ;
- nombre de lignes ;
- poids total ;
- W/D/L ;
- pièces ;
- phases ;
- sources d’oracle.

## 4.4 Cellule B2 — rank-finetune statique

B2 applique `rank_finetune.py` sur les enfants immédiats :

```text
C_good > C_bad
```

Elle existe principalement pour trancher si l’information objective de conversion rend enfin viable une forme statique historiquement morte.

### Pré-engagement

- pairwise accuracy seule ne permet aucune promotion ;
- une régression Elo ferme la forme statique pour cet usage ;
- une hausse de win-preservation sans hausse de playout reste insuffisante ;
- commencer avec un lambda faible et plusieurs ancres raisonnables, mais limiter le nombre de bras.

## 4.5 Cellule B3 — rank-finetune through-search

B3 ne compare pas directement l’évaluation de `C_good` et `C_bad`. Pour chaque enfant :

1. lancer une recherche courte gelée, par exemple d5 ;
2. extraire la feuille/PV réellement utilisée ;
3. comparer les feuilles selon le choix parent ;
4. stocker le STM du parent pour le contrat `--leaf-pov` ;
5. appliquer la rank-loss sur ces feuilles.

### Pourquoi B3 peut réussir là où B1 échoue

La recherche choisit les coups via des valeurs remontées depuis ses feuilles, pas simplement par l’évaluation statique des enfants immédiats. B3 agit sur la distribution décisionnelle réelle.

Autre mécanisme : B1 exige une calibration absolue WIN/DRAW. B3 exige seulement un ordre local. Une classe qui ne peut pas produire une probabilité absolue parfaite peut néanmoins apprendre l’ordre utile.

### Pourquoi B3 peut échouer

- le d5 peut masquer ou déformer l’oracle profond ;
- le leaf-mode ajoute une distribution différente ;
- le ranking peut encore décalibrer la value-function ;
- le coût de génération est supérieur ;
- les feuilles de branches différentes peuvent avoir des phases ou STM différents, exigeant un POV irréprochable.

## 4.6 Lectures pré-engagées

```text
B1 ≈ B3 > A > B2
    information utile ; WDL ou through-search suffisent ; statique confirmé mort

B3 > B1 > A
    le crédit d’action a besoin de passer par la distribution des feuilles de recherche

B1 > B3
    l’information contrefactuelle suffit ; through-search ajoute bruit ou covariate shift

B2 > A
    surprise : les paires objectives de conversion rendent le ranking statique viable
    => exiger confirmation haut-N avant adoption

B1,B2,B3 ≈ A
    information locale non compressible, volume insuffisant ou oracle mal construit

B1,B2,B3 < A
    teacher nuisible, conflit de calibration ou contamination ; ne pas conclure immédiatement
    que le crédit causal est inutile avant audit des poids et des verdicts
```

## 4.7 Contrôle optionnel ultérieur

Si B1 gagne, un cinquième contrôle peut comparer :

- mêmes volumes de frères oracle ciblés sur les jets ;
- mêmes volumes d’enfants oracle échantillonnés sans événement de jet.

Cela vérifierait que le gain vient du ciblage causal plutôt que de « plus de labels propres ». Ce contrôle n’est pas requis dans le premier smoke.

---

## 5. M2 — Jauge WDL-grounded et DOE avant conclusion GYM

## 5.1 Défaut de l’ancienne jauge

`conv_self.py` v2 a corrigé le défenseur confondu, mais conserve un autre biais : il choisit le camp gagnant selon l’avantage en nombre de pièces. Les positions sans avance suffisante sont ignorées.

Cette hypothèse fonctionnait pour les anciens pools à avantage matériel. Elle devient fausse pour les gains techniques à matériel égal.

## 5.2 Jauge correcte

`conv_fixed_wdl.py` doit :

- recevoir un témoin figé de positions ;
- dériver le camp gagnant du label d14+EGDB, pas du matériel ;
- faire jouer le candidat contre un défenseur fixe ;
- conserver les mêmes positions et couleurs entre cellules ;
- rapporter les erreurs, exclusions et résultats position par position ;
- permettre un contraste apparié.

## 5.3 Statut de 0723/0724 à la rédaction

- PR #329 fusionnée ;
- `0723` lancé puis échoué `rc=1` ;
- cause : 16 shards × cache 2048 Mo, saturation RAM et mort de shards ;
- `0724` relancé avec cache 512 Mo, recette sinon identique ;
- verdict encore en attente lors de cette v2.

## 5.4 Décisions possibles après 0724

### Effet LABEL positif, GYM plat sur jauge saine

Cela renforce :

- labels propres indispensables ;
- multiplication statique du tip insuffisante ;
- teacher de jets et trajectoires fraîches prioritaire.

### Effet GYM positif sur conversion mais plat/négatif en Elo

Cela confirme un **conflit conversion ↔ généraliste**. Le teacher doit alors chercher un signal plus local, un meilleur dosage ou une séparation de phase.

### Effet GYM positif en conversion et en Elo

Le gymnase est utile ; il doit entrer dans la sonde et la campagne. Le teacher reste intéressant, mais n’est plus automatiquement le premier goulot.

### Interaction LABEL×GYM forte

Le gymnase ne doit être évalué qu’avec labels propres. Toute conclusion issue d’une cellule on-policy seule devient non transférable.

---

## 6. m4 — Hiérarchie de labels et certificats

## 6.1 Principe

La hiérarchie retenue est :

```text
TB exact > CERT-PROOF > SEARCH-STABLE > AMBIGUOUS
```

Le draw-band sert à exprimer l’humilité d’une recherche peu décisive. Il ne doit pas annuler une preuve réellement plus forte. En revanche, une ancienne sortie d14 ne devient pas une preuve simplement parce qu’elle est enregistrée dans un pool « certifié ».

## 6.2 Canal TB

Position directement résolue par EGDB :

- verdict exact W/D/L ;
- version/path de base consignés ;
- STM/POV consignés ;
- aucune draw-band ;
- priorité maximale.

## 6.3 Canal CERT-PROOF

Un certificat acceptable doit fournir au moins :

```text
position_hash
fen
stm
engine_sha
search_params_hash
depth_or_movetime
score
margin
egdb_version
oracle_timestamp
proof_kind
```

`proof_kind` peut être :

- `PV_REACHES_TB` : la recherche atteint une position TB et remonte le verdict ;
- `D14_D16_STABLE` : même signe à d14 et d16 avec marge minimale ;
- `DUAL_ENGINE_AGREE` : option future, deux configurations indépendantes s’accordent ;
- `BOOK_ORACLE_REVALIDATED` : uniquement si revalidé moteur, jamais simple claim humain.

Le canal `PV_REACHES_TB` est plus fort que `D14_D16_STABLE`.

## 6.4 Canal SEARCH-STABLE

Verdict de recherche sans preuve TB, mais :

- même signe sur deux profondeurs ;
- marge au-dessus du seuil ;
- absence d’instabilité de PV majeure ;
- paramètres gelés ;
- POV vérifié.

## 6.5 Canal AMBIGUOUS

Quarantaine si :

- d14 et d16 divergent ;
- score dans la draw-band sans preuve ;
- marge trop faible ;
- erreur oracle ;
- parent ou enfant illégal ;
- position répétée avec verdicts contradictoires.

Les positions ambiguës peuvent servir à l’évaluation diagnostique, pas au teacher v1.

## 6.6 Cas du tip relabellisé nul

Le fait qu’une part importante du tip devienne DRAW sous draw-band-50 peut signifier deux choses :

1. le draw-band jette des gains techniques à score faible ;
2. le premier certificat était trop optimiste.

Il faut auditer un échantillon des divergences :

- PV atteint-elle la TB gagnante ?
- d16 confirme-t-il le WIN ?
- la certification initiale avait-elle une marge ?
- les paramètres/POV sont-ils identiques ?

Le seuil « ≥90 % du tip survit » est une **métrique d’audit**, pas une obligation de conserver artificiellement 90 % des positions.

## 6.7 Unification teacher / gymnase

Le gymnase, la jauge et le teacher doivent utiliser la même fonction d’oracle et le même format de provenance. Aucune branche ne doit réimplémenter sa propre notion de WIN.

Proposition :

```text
tools/conversion_oracle.py
```

API logique :

```python
OracleResult(
    wdl,
    confidence,
    channel,
    score,
    depth,
    proof_kind,
    metadata,
)
```

---

## 7. M3 — Deux niveaux de boucle et trois niveaux d’arrêt

## 7.1 La sonde

La sonde T1-bis→T3 teste une recette simple et instrumentée :

- labels hiérarchisés ;
- quota en positions ;
- pas de teacher au départ ;
- éventuelle profondeur par phase introduite séparément ;
- corpus frais ;
- même fenêtre et mêmes jauges.

Objectif : obtenir une courbe de direction et produire des parties exploitables par le teacher.

Un résultat plat peut arrêter la sonde et déclencher une révision de recette. Il ne ferme pas l’axe campagne.

## 7.2 La campagne

La campagne commence après validation du canal teacher et de la recette complète. Elle peut couvrir 20–30 tours selon la doctrine, avec :

- montée de qualité du professeur ;
- renouvellement réel du corpus ;
- gymnase saturé en positions, non en parties ;
- mining continu des nouveaux jets ;
- métriques retardées observées sur plusieurs tours ;
- dernier barreau de budget/profondeur atteint avant verdict de plateau.

## 7.3 Trois niveaux d’arrêt

### Abort technique immédiat

- corpus corrompu ;
- shards manquants hors tolérance ;
- fuite train/eval ;
- POV faux ;
- oracle incohérent ;
- candidate PJTW invalide ;
- juge incomplet ;
- hashes/manifests incompatibles.

### Arrêt de sonde

- pas de signal directionnel après le nombre prévu de tours ;
- coût incompatible avec la campagne ;
- recette mal calibrée ;
- instrumentation insuffisante ;
- conflit généraliste massif nécessitant un nouveau design.

### Clôture scientifique de campagne

Seulement après :

- régime établi ;
- dernier barreau de professeur testé ;
- gymnase/teacher correctement nourris ;
- au moins quatre tours de plateau sur les jauges maîtresses ;
- absence d’amélioration cumulée ;
- vérification que le turnover et les nouveaux événements ne sont pas tombés à zéro artificiellement.

## 7.4 Promotion ≠ poursuite de la recherche

Un candidat peut ne pas être promu parce qu’il régresse en généraliste. Cela ne signifie pas nécessairement que la piste est fermée. L’artefact et ses événements restent utiles pour diagnostiquer le conflit.

---

## 8. m5 — Profondeur de jeu par phase

## 8.1 Hypothèse

Le générateur doit être capable de **démontrer** la conversion. Jouer l’endgame plus profondément peut produire :

- de meilleures trajectoires ;
- davantage d’entrées TB ;
- moins de jets artificiels ;
- des labels de partie plus cohérents ;
- un meilleur professeur pour la génération suivante.

Cette piste est distincte d’un relabel profond après coup. Le relabel corrige la valeur des positions ; la profondeur de jeu change les coups réellement visités.

## 8.2 Discipline d’introduction

La profondeur par phase compte comme **un changement de recette**. Elle ne doit pas être introduite le même tour que le teacher.

Ordre recommandé :

1. T1-bis à recette propre sans changement de profondeur ;
2. microbenchmark ;
3. introduction à T2 si coût acceptable ;
4. teacher évalué dans un smoke séparé.

## 8.3 Microbenchmark proposé

Même seeds, même nombre de parties :

```text
P0  profondeur actuelle
P1  endgame=d16, deep-eg=d18
P2  endgame=d14, deep-eg=d16
```

Mesures :

- wall-clock total ;
- positions/s ;
- parties/h ;
- temps par phase ;
- profondeur atteinte ;
- taux d’entrée EGDB ;
- plies moyennes ;
- stalls ;
- verdicts ;
- coût marginal par position utile.

Attente prudente, non garantie : +10 à +25 % si l’activation est tardive et les cutoffs TB fréquents. Un surcoût supérieur impose P2 ou un seuil de pièces plus bas.

## 8.4 Gate d’adoption

- coût ≤ +25 % : P1 admissible ;
- coût > +25 % mais P2 ≤ +25 % : adopter P2 ;
- coût élevé sans amélioration de trajectoire/TB : garder profondeur actuelle.

---

## 9. m6 — MTC

## 9.1 Voie fermée

Ne pas réutiliser MTC/proxy comme cible globale d’entraînement. Le signal gradué réel était trop rare et le proxy a dominé, avec dégradation du moteur.

## 9.2 Usages autorisés

- score terminal dans la recherche TB ;
- choix d’une conversion plus rapide entre plusieurs WIN ;
- génération de trajectoires-professeur ;
- métrique MTC-regret ;
- tie-break secondaire entre deux `C_good` tous deux WIN, après validation.

## 9.3 Audit Phase 0

Vérifier :

- `JASS_EGDB_MTC_PATH` réellement exporté ;
- base disponible sur chaque box ;
- logs indiquant l’activation ;
- MTC-on vs MTC-off sur témoin exact ;
- aucune utilisation involontaire dans les matches où l’éval pure doit être mesurée.

---

## 10. m8 — Quota par positions

## 10.1 Défaut de `seed_frac`

Une partie de finale est courte. Une fraction élevée de parties gymnase peut produire une fraction négligeable de lignes, comme les 0,04 % observés dans un corpus T1.

## 10.2 Flag canonique

Un seul contrat :

```text
--conversion-record-frac 0.10
```

Le générateur continue à tirer des seeds de conversion jusqu’à atteindre approximativement la fraction cible d’enregistrements.

## 10.3 Garde-fous

- quota mesuré en records ;
- limite de lignes par partie ;
- limite de réutilisation par seed ;
- dédup positionnelle ;
- paires de couleurs ;
- sharding disjoint ;
- pas de duplication brute d’un JNNW final ;
- rapport `n_records/n_unique/n_games/mean_plies` ;
- distribution par strate p1–p4.

## 10.4 Interaction avec le teacher

Le quota alimente les trajectoires. Le teacher mine ensuite les jets. Les lignes teacher ne doivent pas être comptées silencieusement dans le quota de génération ; leur poids est rapporté séparément.

---

## 11. Implémentation détaillée du `conversion_teacher`

## 11.1 Architecture proposée

```text
tools/conversion_oracle.py
    oracle commun TB / CERT / SEARCH / ambigu

tools/conversion_teacher.py
    lit trajectoires, détecte jets, énumère frères, appelle oracle

pattern_jass/tools/rank_finetune.py
    réutilisé pour B2/B3, changements minimaux si possible

tools/scan_selfplay_gen.py
    émet événements/trajectoires et quota positions

tools/conv_fixed_wdl.py
    jauge WDL-grounded appariée
```

## 11.2 Entrées du teacher

Minimum :

- trajectoires FEN ordonnées ;
- coups joués ;
- résultat de partie ;
- identifiant de partie ;
- seed/opening ;
- champion SHA/pattern SHA ;
- paramètres de jeu ;
- labels oracle éventuels déjà calculés.

Le format JNNW seul ne contient pas les coups et frontières de parties nécessaires. Le générateur doit produire un sidecar ou un format événementiel.

## 11.3 Sidecar de trajectoire

Proposition JSONL par partie :

```json
{
  "game_id": "...",
  "seed_hash": "...",
  "white_pattern_sha": "...",
  "black_pattern_sha": "...",
  "play_params": "...",
  "outcome": "D",
  "reason": "25-move",
  "fens": ["..."],
  "moves": ["31-27", "..."],
  "sources": ["GYM", "..."],
  "schema": "conversion-traj-v1"
}
```

Pour le volume, une version binaire pourra venir ensuite. Le smoke privilégie l’auditabilité.

## 11.4 Détection du premier jet

Pour chaque trajectoire candidate :

1. sélectionner les parties démarrées d’un parent WIN ou contenant une position WIN ;
2. oracle en batch sur les positions échantillonnées ;
3. trouver le premier index `k` tel que :

```text
Oracle(P_k) = WIN
Oracle(P_{k+1}) ∈ {DRAW, LOSS}
```

4. vérifier la stabilité du parent et de l’enfant ;
5. conserver principalement le **premier** jet pour éviter plusieurs paires corrélées de la même erreur ;
6. permettre plus tard un mode « tous les jets » plafonné.

## 11.5 Filtrage avant oracle coûteux

Pipeline coût :

```text
screen d10/d12
→ parents où signe semble chuter
→ confirmation d14/d16 + EGDB
→ énumération frères uniquement sur événements confirmés
```

Cache par hash de position obligatoire.

## 11.6 Énumération des frères

Pour le parent P :

- générer tous les coups légaux ;
- inclure captures multiples ;
- ne pas rejeter arbitrairement les captures ;
- calculer l’enfant exact avec le movegen Jass ;
- oracle batch sur tous les enfants ;
- identifier `C_good` WIN ;
- confirmer que `C_bad` est bien le coup joué et DRAW/LOSS ;
- rejeter si aucun frère conserve WIN ;
- rejeter si un seul coup légal.

## 11.7 Sélection de `C_good`

Version 1 :

- prendre un frère WIN stable ;
- priorité à une preuve TB ;
- sinon meilleure confiance/marge ;
- limiter à deux bons frères par parent.

Version future : parmi plusieurs WIN, utiliser MTC ou distance-TB uniquement comme tie-break validé.

## 11.8 Sorties

```text
teacher/events.jsonl
teacher/parents.jnnw
teacher/siblings_wdl.jnnw
teacher/pairs_static.jnnw
teacher/pairs_leaf_d5.jnnw
teacher/played_moves.bin
teacher/manifest.json
teacher/train_ids.txt
teacher/holdout_ids.txt
```

### `events.jsonl`

Doit contenir :

- parent FEN/hash ;
- move joué ;
- move(s) good ;
- verdict parent/bad/good ;
- canal d’oracle ;
- profondeurs/scores/marges ;
- nombre de pièces ;
- strate ;
- game_id/ply ;
- raisons de rejet éventuelles.

### `siblings_wdl.jnnw`

Enregistrements pour B1, avec labels oracle et sidecar de poids par parent si le trainer le nécessite.

### `pairs_static.jnnw`

Ordre compatible avec `rank_finetune.py` :

```text
[better, worse]
```

Le champ `score` doit porter le STM parent si `--leaf-pov` ou un nouveau contrat unifié est utilisé.

### `pairs_leaf_d5.jnnw`

Généré via `--gen-siblings --leaf-mode`, mais l’ordre de préférence vient de l’oracle de l’enfant, pas du coup historique d’un maître.

## 11.9 Splits

Split dur par `game_id` et parent hash :

- aucun parent dans train et holdout ;
- aucun frère d’un parent holdout dans train ;
- aucune seed commune si possible ;
- aucune intersection avec conv-1600, thermo-224 ou jauges maîtresses ;
- rapport d’intersection à zéro.

## 11.10 Pondération et diversité

Stratifier au minimum :

- 3–7 pièces ;
- 8–12 ;
- 13–20 ;
- p1/p2/p3/p4 ;
- hommes/dames ;
- WIN→DRAW et WIN→LOSS ;
- captures et coups quiets.

Plafond par famille et par parent pour éviter qu’une finale fréquente domine.

---

## 12. Plan expérimental amendé

## Phase 0a — DOE propre

Finir `0724` et consigner :

- effet LABEL ;
- effet GYM ;
- interaction ;
- conversion WDL-grounded ;
- force directe ;
- support et erreurs.

Aucune conclusion ferme sur GYM avant ce verdict.

## Phase 0b — audits

- SHA exact de `develop` et des outils ;
- versions EGDB/MTC ;
- `terminate-at-TB` ;
- `play-depth-by-phase` ;
- oracle commun et canaux ;
- jauges figées ;
- disjonctions ;
- cache/sharding ;
- provenance du tip.

## Phase 1 — sonde sans teacher

Recette :

- labels hiérarchisés ;
- quota par positions ;
- corpus frais ;
- T1-bis→T3 ;
- profondeur par phase introduite seule après mesure ;
- mêmes gates à chaque tour.

La sonde produit aussi les trajectoires pour Phase 2.

## Phase 2 — mining teacher

Objectif smoke : 5 000 à 20 000 parents utiles, pas seulement paires.

Gates :

- parent WIN ;
- bad DRAW/LOSS ;
- good WIN ;
- oracle stable ;
- aucun parent à un coup ;
- aucun overlap ;
- diversité minimale par strates.

## Phase 3 — quatre cellules

Même baseline, mêmes événements, mêmes budgets : A/B1/B2/B3.

Ordre des évaluations :

1. intégrité ;
2. accuracy holdout ;
3. win-preservation ;
4. conv WDL-grounded ;
5. match direct ;
6. thermomètre ;
7. haut-N si signal.

## Phase 4 — campagne

Le bras gagnant devient une brique de la campagne :

```text
joue
→ mine les jets
→ construit information contrefactuelle
→ injecte par canal validé
→ juge
→ régénère avec nouveau champion
```

Gouvernance doctrine longue, pas stop-rule de sonde.

## Phase 5 — `DEEP_EG`

Seulement si le déclencheur durci du §15 est atteint.

---

## 13. Métriques et tableau de bord

## 13.1 Jauges maîtresses

- conv WDL-grounded appariée ;
- thermomètre PC Blues 224 ;
- direct champion_k vs parent ;
- cumulé vs T0 ;
- stalls ;
- taux d’entrée TB.

## 13.2 Métrique native du teacher : win-preservation

Sur holdout :

- proportion où le meilleur coup choisi par l’éval conserve WIN ;
- proportion sur parents critiques ayant au moins un coup qui jette ;
- top-k preservation ;
- ventilation par pièces et canal d’oracle.

## 13.3 Regret de verdict

```text
WIN→WIN   = 0
WIN→DRAW  = 1
WIN→LOSS  = 2
```

Rapporter moyenne et distribution.

## 13.4 Indicateurs avancés et retardés

Avancés :

- pairwise holdout ;
- win-preservation ;
- regret ;
- score des good/bad ;
- first-throw rate.

Retardés :

- conversion en playout ;
- stalls ;
- Elo ;
- progression multi-tours.

Une hausse d’indicateur avancé sans transfert retardé ne permet pas de promouvoir.

## 13.5 Ce qui ne suffit jamais

- train loss ;
- pairwise accuracy seule ;
- MSE finale ;
- score sur train ;
- un petit N de conversion ;
- un gain contre bootstrap sans contraste direct ;
- survie du tip imposée comme objectif.

---

## 14. Gates de promotion

## 14.1 Smoke

Un bras mérite confirmation si :

- win-preservation holdout monte nettement ;
- conversion ne régresse pas ;
- généraliste ne régresse pas clairement ;
- intégrité parfaite ;
- résultat non expliqué par une seule strate.

## 14.2 Confirmation

- match direct haut-N ;
- même conv témoin ;
- réplication autre seed ;
- mêmes paramètres ;
- manifests comparables.

## 14.3 Campagne

Promotion d’un champion :

- conversion en hausse sur fenêtre de deux tours ou preuve robuste au tour courant ;
- généraliste non régressif ;
- aucun veto d’intégrité ;
- pas de détérioration massive d’une phase.

Une non-promotion n’est pas une clôture de programme.

---

## 15. m9 — Déclencheur `DEEP_EG`

La banque linéaire :

```text
MG ↔ EG ↔ DEEP_EG
```

reste compatible avec la doctrine aucun NNUE.

Elle ne devient admissible que si, pendant au moins deux tours :

- le teacher améliore le holdout ;
- la win-preservation monte ;
- le regret baisse ;
- la conversion réelle reste plate ;
- le plat est concentré dans la zone 8–12 pièces ;
- la force générale ne montre pas que l’oracle est simplement mauvais.

Première implémentation prudente : banque `DEEP_EG` uniquement sur les extras, pas duplication immédiate de tous les patterns.

Features candidates :

- mobilité de dames ;
- dames enfermées ;
- proximité/confinement ;
- promotion ;
- contrôle de grandes diagonales ;
- ressources de nulle mesurables ;
- distance à la frontière TB.

---

## 16. Tests demandés

## 16.1 `conversion_oracle.py`

- TB exact ;
- POV ;
- d14/d16 stable ;
- divergence → ambigu ;
- certificat PV→TB ;
- provenance sérialisée ;
- cache déterministe ;
- draw-band sans veto sur TB.

## 16.2 `conversion_teacher.py`

- parsing trajectoire ;
- premier jet ;
- parent WIN/enfant bad DRAW ;
- parent WIN/enfant bad LOSS ;
- frère WIN ;
- aucun frère → rejet ;
- un seul coup → rejet ;
- captures multiples ;
- dédup ;
- split ;
- ordre better/worse ;
- poids total par parent ;
- strates ;
- absence d’intersection.

## 16.3 B1

- labels WDL corrects ;
- poids par parent ;
- distribution rapportée ;
- round-trip JNNW ;
- trainer accepte les poids ou duplication contrôlée documentée.

## 16.4 B2/B3

- POV gate > seuil ;
- feuilles alignées ;
- STM parent stocké ;
- grad-check ;
- pairwise accuracy augmente sans être utilisée comme gate de force ;
- PJTW chargeable ;
- `--eval-position` cohérent.

## 16.5 Runner

Abort si :

- EGDB absent ;
- MTC annoncé mais non chargé ;
- shard manquant ;
- OOM probable selon cache×shards ;
- nombre d’événements insuffisant ;
- fuite ;
- oracle contradictoire ;
- candidate invalide ;
- conv incomplet hors tolérance.

---

## 17. Risques et réponses

### 17.1 B1 déséquilibre la calibration

Réponse : poids teacher borné, rapport WDL, dose faible, contraste direct.

### 17.2 B3 apprend le d5 au lieu de la vérité profonde

Réponse : l’ordre des branches vient de l’oracle profond ; le d5 sert seulement à localiser les feuilles décisionnelles. Tester d3/d5 sur smoke si nécessaire.

### 17.3 Oracle d14 faux au-dessus des TB

Réponse : stabilité d14/d16, preuve PV→TB, ambigu en quarantaine.

### 17.4 Teacher dominé par les finales faciles

Réponse : strates et plafonds par famille ; quota 8–12 et 13–20.

### 17.5 Corrélation de milliers de paires

Réponse : poids constant par parent, split par partie, nombre de parents comme unité statistique.

### 17.6 Contamination des jauges

Réponse : blacklist de hashes commune à tous les outils.

### 17.7 Coût oracle

Réponse : screen, batch, cache, parallélisation, C++ seulement après preuve de goulot.

### 17.8 Trop de changements simultanés

Réponse : discipline « un changement de recette par introduction » : labels/quota, puis profondeur, puis teacher.

---

## 18. Réponses explicites aux questions de la contre-revue

### Q1 — L’information contrefactuelle est-elle la valeur, la forme rank le risque ?

**Oui.** Le teacher doit être défini comme un mineur d’information oracle, pas comme un ranker. Le ranking est un consommateur possible.

Défaut principal possible de B1 : calibration et distribution. Il est contrôlable par pondération et A/B.

### Q2 — Maintenir la pause de #329 ?

**Non.** La conclusion gymnase de 0722 était instrumentellement limitée. La PR a été fusionnée et le run corrigé doit être consommé.

### Q3 — Hiérarchie sonde/campagne ?

**Oui.** Les stop-rules rapides ne valent que pour la sonde. La campagne suit la doctrine et le plateau multi-tours.

### Q4 — Le teacher peut-il utiliser TB > CERT > D14 ?

**Oui sous une définition stricte de CERT.** Il faut remplacer le simple statut par `CERT-PROOF`, avec provenance, marge et type de preuve.

### Q5 — Surcoût d16/d18 ?

Estimation prudente +10–25 % si activation tardive et TB efficace, mais aucune décision sans microbenchmark.

### Q6 — Pourquoi B1 pourrait échouer et B3 réussir ?

Parce que la décision du search dépend des feuilles explorées, pas seulement de la valeur statique de l’enfant. B3 entraîne la distribution décisionnelle réelle et n’exige qu’un ordre relatif ; B1 exige une calibration absolue des enfants.

---

## 19. Questions pour la nouvelle revue Fable / Claude

Merci de challenger précisément :

1. Le smoke A/B1/B2/B3 isole-t-il correctement information et forme de loss ?
2. B1 nécessite-t-il un support natif de poids par ligne, ou une construction équivalente existe-t-elle déjà ?
3. Comment garantir un poids constant par parent avec les trainers actuels ?
4. Le leaf-mode d5 de B3 respecte-t-il exactement le contrat `rank_finetune --leaf-pov` ?
5. Peut-on réutiliser `--gen-siblings` sans introduire une préférence historique parasite ?
6. Quel format de sidecar de trajectoire minimise le dev tout en restant audit-proof ?
7. La détection du premier jet doit-elle oracle-labeliser chaque ply ou utiliser une recherche dichotomique/coarse-to-fine ?
8. `PV_REACHES_TB` est-il techniquement extractible avec les outils actuels ?
9. Comment versionner proprement un `CERT-PROOF` ?
10. Le draw-band actuel doit-il être identique pour parents et enfants ?
11. Le microbenchmark profondeur-par-phase mesure-t-il le bon coût marginal ?
12. Quels seuils de pièces pour d16/d18 sur cpx62 et ccx33 ?
13. `JASS_EGDB_MTC_PATH` est-il réellement actif dans la chaîne L3 ?
14. `--conversion-record-frac` peut-il être ajouté sans casser le sharding déterministe ?
15. Quels résultats de 0724 modifieraient la priorité teacher vs campagne simple ?
16. La blacklist train/eval doit-elle vivre dans un fichier canonique unique ?
17. Quelle dose teacher initiale pour B1/B2/B3 permet un test équitable ?
18. Faut-il limiter le smoke aux WIN→DRAW ou inclure WIN→LOSS dès v1 ?
19. Le déclencheur `DEEP_EG` est-il suffisamment dur ?
20. Existe-t-il dans le repo une brique déjà implémentée qui rendrait une partie de ce plan redondante ?

---

## 20. Conclusion finale

Le diagnostic central est renforcé, mais formulé plus précisément :

> **Jass ne manque probablement pas d’une nouvelle boucle générique. Il manque d’un système qui découvre les alternatives non jouées, localise le premier abandon de gain, certifie les frères et transforme cette information contrefactuelle en signal d’apprentissage.**

La v2 refuse toutefois de confondre ce système avec une forme de loss particulière.

```text
information :
parent WIN
coup joué → DRAW
frère non joué → WIN

canaux à trancher :
B1  valeurs WDL ordinaires
B2  préférence statique
B3  préférence through-search
```

Le DOE WDL-grounded doit d’abord préciser ce que le gymnase sait déjà enseigner. La sonde T1-bis→T3 mesure ensuite la direction sans prétendre clôturer la campagne. Le teacher est miné en parallèle, puis évalué à quatre bras. Le canal gagnant rejoint une campagne longue gouvernée par la doctrine, et `DEEP_EG` ne s’ouvre qu’en présence d’un signal local réel mais non transféré.

Cette séquence protège le projet contre ses deux erreurs historiques :

- **apprendre une préférence qui améliore son propre proxy mais détruit le jeu** ;
- **arrêter une boucle avant que son signal retardé ait eu le temps d’apparaître**.

Elle reste entièrement linéaire, auditée par oracles et compatible avec la règle « aucun NNUE ».
