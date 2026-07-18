# L3-PURE — lignée autonome Scan-like centrée sur la conversion

> **Date : 2026-07-18**
> **Statut : plan scientifique pré-engagé ; première PR C0**
> **Document de départ :** `docs/archives/codex_review_v3_2.md`
> **Classe de modèle :** évaluation linéaire patterns ; aucun NNUE
> **Règle cardinale :** aucun professeur externe dans la génération ou le fit
> **État et résultats L3 :** [L3_CURRENT.md](L3_CURRENT.md)
> **Mémoire des expériences closes :** [PROJECT_RESULTS.md](PROJECT_RESULTS.md)

## 0. Décision

La prochaine lignée est `L3-PURE`. Elle repart d'une évaluation matérielle,
joue contre elle-même, attache à chaque position le résultat terminal de sa
propre partie et recommence. Scan, Gen2, les parties de maîtres, les labels
d14, MMTO et les positions fixes de gymnase ne fournissent ni coup, ni position,
ni label, ni adversaire d'entraînement.

Le problème de conversion est traité comme un problème de **trajectoire**. Une
évaluation n'apprend pas « le bon premier coup » : chaque état successif de la
partie est un nouvel exemple, et la recherche choisit un coup en comparant la
valeur de ses successeurs. Si un avantage se dissipe au deuxième ou au dixième
coup, les états correspondants doivent réapparaître dans le corpus avec leur
résultat final réel.

## 1. Pourquoi cette expérience reste ouverte

Les essais historiques ne constituent pas l'exécution complète de cette recette :

| Essai | Ce qui a réellement été exécuté | Limite pour la question L3-PURE |
|---|---|---|
| `0481`, `0482` | jobs from-scratch terminés en échec | pas de lignée ni d'artefacts complets |
| `0532` | une génération avec 400 k autojeu, 4,16 M positions de maîtres et 200 k EGDB | corpus non autonome |
| `0536` | chaîne pure prévue sur 15 générations | échec pendant G1 |
| `0674` | quatre tours autonomes à d10 ; T2 +170 Elo puis T3/T4 en retrait | profondeur fixe, arrêt précoce, fit ancré au parent |
| T1-bis → T3 | labels d14+EGDB et G1 ; conversion ≈ 66–67 % | stable mais plat ; autre mécanisme de labels |
| fork C C0 | divergence politique sans conversion ; −32,5 Elo | rejeté, ne teste pas une lignée pure longue |
| teacher `0777` | aucune cellule B1/B2/B3 à +2 points | professeur causal clos faute de signal |

Les gymnases statiques, les doses G4, MMTO par tour et le professeur causal ne
sont donc pas répétés. L'expérience encore manquante est une boucle WDL
autonome, assez longue, avec montée du budget de recherche et un curriculum
mobile issu exclusivement des échecs de la lignée elle-même.

## 2. Contrat scientifique non négociable

### 2.1 Graine et représentation

- géométrie `8cf`, sous-ensemble vertical Scan-like, figée pendant la lignée ;
- squelette structurel matériel/dames/extras disponible dès le départ ;
- graine : homme = 1, dame = 3 ; tous les patterns, bonus de centre et mobilité à 0 ;
- phases MG/EG conservées ;
- aucun poids copié depuis Scan, Gen2 ou un autre champion.

Le choix `8cf` minimise la complexité d'échantillonnage. `0579` n'a pas montré
d'écart utile de log-loss entre 8cf et 32cf au régime mesuré. Un changement de
géométrie, s'il devient nécessaire, fera l'objet d'un fork séparé et ne sera pas
introduit au milieu de la lignée.

### 2.2 Vérité des labels

Labels d'entraînement autorisés :

1. absence de coup légal ;
2. nul de règle effectivement détecté par le moteur ;
3. résultat EGDB exact après qu'une partie a atteint naturellement la tablebase.

Labels interdits :

- score de recherche d14/d16 ;
- adjudication matérielle ;
- deep relabel ;
- MMTO/ranking ;
- résultat Scan, Gen2 ou partie humaine ;
- transformation d'une partie arrêtée au ply-cap en nul.

Les parties au ply-cap sont **censurées** : tous leurs samples sont exclus. EGDB
peut terminer une partie naturellement atteinte, mais aucune position EGDB
aléatoire n'est injectée dans le corpus. EGDB joue ici le rôle de règle exacte,
pas celui de professeur.

### 2.3 Fit

- régression logistique WDL uniquement ; le champ score du JNNW n'est pas une cible ;
- split train/holdout par ouverture complète, jamais par ligne aléatoire ;
- symétrie couleur ;
- démarrage de l'optimiseur aux poids du student précédent ;
- L2 ordinaire vers zéro, **aucun ridge ou anchor vers le parent** ;
- corpus frais à chaque génération pour C0.

Le warm-start assure la continuité numérique sans transformer le parent en
cible. La mémoire explicite par replay de parties anciennes sera testée dans une
PR ultérieure, séparément du signal causal de la frontière.

### 2.4 Exploration

L'exploration est nécessaire à la couverture, mais ne doit pas casser la
conversion tardive :

- huit plies d'ouverture aléatoires issus des règles ;
- epsilon initial de 8 % ;
- décroissance linéaire jusqu'à zéro au ply 60 ;
- aucun `drop-post-eps` : les continuations restent jouées et apprises ;
- aucun coup exploratoire après la zone de décroissance.

## 3. Frontière mobile de conversion

Après une génération, on examine uniquement ses propres samples WDL. Une
position entre dans la frontière v1 si :

- elle a été réellement atteinte par la lignée ;
- il reste 8 à 24 pièces ;
- un camp possède un avantage matériel de 1 à 3 unités ;
- ce camp n'a pas gagné la partie, ou a effectivement converti dans la petite
  fraction témoin.

Le mineur conserve au maximum un exemple par partie et par type, stratifie par
marge et phase, déduplique, puis ajoute le miroir couleur. Les champs score et
WDL des records de départ sont remis à zéro. Quand la position est rejouée à la
génération suivante, sa continuation doit produire un **nouveau résultat
terminal** ; l'ancien résultat sert uniquement à sélectionner la difficulté.

Ce mécanisme diffère du gymnase G4 :

- distribution courante et mobile ;
- aucune position externe ou certifiée d14 ;
- aucun label réutilisé ;
- quota modéré de parties, pas de duplication massive de positions courtes ;
- renouvellement complet à chaque génération.

La v1 cible les avantages matériellement observables, donc surtout P2/P3. La
frontière P4 matériel-égal exigera une estimation interne par plusieurs rollouts
stochastiques ; elle est volontairement hors de cette première PR afin de ne pas
confondre le test C0.

## 4. C0 pré-engagé : causalité de la frontière

Deux bras partent du même fichier matériel, des mêmes seeds et des mêmes budgets.

| Génération | Bras A — contrôle | Bras B — frontière mobile |
|---|---|---|
| G1 | autojeu standard | autojeu standard identique ; minage de F1 après le fit |
| G2 | autojeu standard | 75 % standard + 25 % départs depuis F1 ; minage de F2 |
| G3 | autojeu standard | 75 % standard + 25 % départs depuis F2 |

Paramètres de travail :

- 500 k positions éligibles par bras et génération ;
- d8 en G1/G2, d10 en G3 ;
- `max_plies=260`, terminaison EGDB exacte, ply-cap exclu ;
- holdout 1/10 par ouverture ;
- `color-fold`, WDL logistic, L2 `3e-5`, 25 itérations maximum ;
- checkpoints par génération et artefacts reprenables.

C0 ne décide pas de la viabilité finale de L3-PURE. Il répond seulement à :

```text
à budget et graine identiques, rejouer une frontière mobile auto-générée
améliore-t-il la pente de conversion par rapport à l'autojeu ordinaire ?
```

Signal attendu pour conserver le mécanisme :

- delta de conversion B−A ≥ +0,03 à G3 ;
- amélioration visible de P3 mince ;
- absence de régression généraliste établie de B contre A.

Si ce signal manque, la frontière v1 est retirée, mais la lignée pure A n'est
pas déclarée morte après trois générations.

## 5. Campagne longue après C0

Le student poursuit les générations tant que les invariants techniques et le
fit restent sains. Le champion reste le meilleur modèle ayant satisfait les
gates conversion et non-régression.

| Palier | Générations | Budget de jeu |
|---|---:|---:|
| P1 | G1–G4 | d8 |
| P2 | G5–G8 | d10 |
| P3 | G9–G12 | d12 |
| P4 | G13–G16 | d14 ou plafond de nœuds équivalent |
| confirmation | meilleure recette | seconde graine indépendante |

Une génération plate ne bloque pas le student. Deux générations plates
déclenchent la montée du budget, pas l'arrêt. Une régression catastrophique
provoque un rollback ; une fluctuation incluse dans l'intervalle de confiance
ne détruit pas la trajectoire.

Arrêt scientifique seulement si :

- le budget maximal a été atteint ;
- quatre générations consécutives n'ont plus de pente conversion/force ;
- deux graines indépendantes convergent vers le même plafond.

## 6. Mesures et promotions

Les thermomètres Scan et Gen2 sont autorisés uniquement en évaluation externe.
Ils ne pilotent pas les données.

Jalons :

1. **signal causal** : +3 points contre le contrôle C0 ;
2. **convertisseur crédible** : conversion globale ≥ 75 %, P3 en hausse nette ;
3. **convertisseur mature** : conversion globale ≥ 85 %, sans régression contre
   le champion ni contre la référence Gen2 figée.

Chaque rapport doit publier : provenance des records, taux de ply-cap et samples
exclus, W/D/L, couverture, part standard/frontière, split par ouverture,
holdout log-loss, conversion P1–P4 et gates généralistes avec intervalles de
confiance.

## 7. Première PR d'implémentation

Cette PR fournit les fondations C0 suivantes :

- `--drop-plycap` dans `--gen-data-wdl` ;
- sidecar `JSM1` par sample : identifiants partie/ouverture et provenance seed ;
- merge et split holdout par ouverture ;
- mineur de frontière mobile avec labels de sortie neutralisés ;
- `train_stream --warm-start` sans modification de l'objectif L2 ;
- `train_stream --holdout-count` pour un tail holdout exact ;
- runner-v3 d'un bras C0 sur trois générations ;
- deux wrappers préparés A/B, hors queue.

Restent explicitement hors de cette PR : league student/parent/champion, replay
inter-générations, rollout multi-échantillon pour P4, comparaison C0 haut-N et
orchestrateur G1–G16. Ils doivent être ajoutés après revue des invariants de ce
premier incrément.

## 8. Jobs préparés

- `ccx33-l3-pure-c0-a-v1` : contrôle autojeu pur ;
- `cpx62-l3-pure-c0-b-v1` : même chaîne avec frontière à 25 % en G2/G3.

Ils restent sous `jobs/prepared/l3-pure-c0-20260718/`. Les merger ne lance aucun
calcul. Après merge de la PR moteur, leurs copies GitOps devront être figées sur
le SHA exact dans `jass-control/queue/pending/`.
