# L3-PURE — préenregistrement causal UNIFORM vs TOPK3

> Date : 28 juillet 2026  
> Statut : **implémentation prête — lancement HOME explicitement autorisé par
> JFC le 28 juillet 2026 ; aucune promotion automatique**

## 1. Question

À recette d'entraînement identique, remplacer le bruit d'exploration uniforme
par un tirage parmi des coups plausibles produit-il :

1. une couverture déplacée vers des trajectoires utiles de jeu fort ;
2. une évaluation plus forte que le contrôle uniforme ?

La comparaison primaire est **TOPK3 contre UNIFORM**, pas TOPK3 contre le
parent historique. Les runs `home-1009` et `home-1010` ont été arrêtés parce
qu'ils déplaçaient simultanément plusieurs axes et ne permettaient pas cette
attribution.

## 2. Correctifs bloquants avant génération

Le binaire utilisé par les deux bras doit contenir et tester les invariants
suivants :

- un coup racine joué à profondeur `d` est classé depuis son enfant à
  `d - 1`, ce qui conserve le même horizon racine ;
- la recherche de classement reçoit l'historique réel des prédécesseurs,
  complété par la position racine courante, afin qu'un retour sur une position
  antérieure soit correctement évalué comme répétition ;
- les représentations sémantiquement identiques d'un coup ne peuvent occuper
  plusieurs places dans le Top-K ;
- les flux aléatoires `opening`, `sampling`, `exploration` et `role` sont
  séparés sous une option explicite. Consommer davantage d'aléa dans le bras
  TOPK ne doit donc pas modifier les ouvertures futures du bras.

Le mode historique à RNG unique reste le défaut pour ne pas modifier les jobs
anciens. Le DOE causal doit obligatoirement activer le mode séparé.

## 3. Plan expérimental

### 3.1 Facteur unique

| Paramètre | Bras A — UNIFORM | Bras B — TOPK3 |
|---|---:|---:|
| parent de self-play | identique | identique |
| warm start | identique | identique |
| records frais | 2 000 000 | 2 000 000 |
| replay | 0 % | 0 % |
| profondeur de jeu | d8 | d8 |
| profondeur label | d4, WDL-only | d4, WDL-only |
| ouverture aléatoire | 8 plis | 8 plis |
| epsilon | 8 %, décroissance à 0 au pli 60 | identique |
| choix lors d'un événement epsilon | tous les coups légaux | `K=3`, marge `50` |
| Q00 / géométrie / L2 | identiques | identiques |
| graine d'ouverture et split | identiques | identiques |
| RNG séparés | activés | activés |

Le corpus est 100 % frais dans les deux bras. Cet écart au parent n'est donc
pas un facteur entre les bras ; il interdit seulement d'interpréter une
comparaison secondaire au parent comme une attribution propre au Top-K.

### 3.2 Exécution

- génération séquentielle des bras sur la même machine, six shards concurrents
  au maximum : UNIFORM puis TOPK3 ;
- mêmes graines de shard et même suite d'ouvertures par index de partie ;
- aucun mix d8/d9 dans ce DOE ;
- split holdout identique et groupé par ouverture appariée ;
- aucun job suivant lancé automatiquement.

Implémentation autoritative :
[`jobs/templates/l3-pure-explore-topk-causal-ab-v1.sh`](../../jobs/templates/l3-pure-explore-topk-causal-ab-v1.sh).
Le template historique monobras `l3-pure-explore-topk-v1.sh` n'est pas une
implémentation de ce DOE et ne doit pas être utilisé pour en tirer une
conclusion causale.

Le lancement `home-1013` a montré que lancer simultanément les douze
producteurs (deux bras × six shards) invalide le budget HOME mesuré sur six
producteurs : les six shards UNIFORM ont été interrompus vers 113–115 k
records sur 333 k, sans erreur moteur, avant le terme. L'ordonnancement
séquentiel ne change aucun facteur scientifique entre les bras ; il restaure
le régime de ressources mesuré, porte les délais par bras à 75/90 minutes et
publie désormais le code de sortie de chaque producteur.

## 4. Gardes techniques

La génération échoue fermée si l'une des conditions suivantes est vraie :

- SHA code, parent, géométrie ou Q00 non conformes ;
- nombre de records différent du contrat ;
- canari WDL hors limites ;
- pli classé dans le bras UNIFORM ;
- zéro pli classé dans le bras TOPK3 ;
- option de RNG séparés absente ;
- profondeur effective de classement différente de `play_depth - 1` ;
- fit non convergé ;
- pool, split ou inventaire non authentifiable.

Les compteurs publiés par bras incluent au minimum : événements epsilon,
changements du meilleur coup, plis classés, singletons de marge, candidats
dupliqués retirés, parties et plis joués.

## 5. Mesures de couverture

Les métriques historiques restent publiées : buckets visités, Gini, buckets
avec au moins 10 et 100 observations, répartition par phase et nombre de
pièces.

Le readout causal ajoute :

- Jaccard des ensembles de buckets UNIFORM/TOPK3 ;
- masse déplacée et divergence de Jensen-Shannon ;
- densité dans un probe figé de positions issues de jeu fort, si le probe Scan
  est disponible et authentifié ;
- couverture et densité par phase afin de distinguer une simple contraction
  d'une redirection utile.

Une hausse du pourcentage brut de buckets n'est pas exigée : l'hypothèse porte
sur la **direction** et la densité de la couverture.

## 6. Mesure de force

La cellule primaire joue **TOPK3 contre UNIFORM** sur un nouveau pool de
1 500 ouvertures, deux couleurs, vues Q00 et native, compteurs bruts additionnés
avant calcul du score. Cible : `n=6000` parties au total.

Les comparaisons de chaque bras au parent sont des gardes secondaires de
continuité. La loss holdout reste un diagnostic et ne sélectionne jamais le
modèle.

## 7. Règle de décision

- IC95 Elo entièrement positif dans la cellule primaire et gardes vertes :
  effet Top-K établi, candidat autorisé pour une porte de succession séparée ;
- IC95 entièrement négatif : recette `K=3, marge=50` rejetée ;
- intervalle recouvrant zéro : résultat non conclusif, aucune promotion ; une
  réplication n'est justifiée que par un signal de couverture préenregistré et
  positif sur le probe fort ;
- aucune conclusion causale ne peut être tirée d'une comparaison TOPK3-parent
  seule.

```text
promotion_authorized=false
automatic_next_job=null
```
