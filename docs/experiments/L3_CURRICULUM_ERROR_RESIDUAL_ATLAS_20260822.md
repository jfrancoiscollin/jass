# L3 — atlas résiduel des erreurs de CURRICULUM

Date : 22 août 2026

Statut : protocole read-only préenregistré ; aucun fit ni gate de force dans cet écran

## Pourquoi une seconde attribution

L’autopsie 1474 comptait les buckets actifs à la racine. Elle a correctement
échoué : seulement 10 contrôles étaient appariés, la perspective conservait un
écart de 8 cp et aucun bucket ne confirmait. Les jobs 1476–1478 ont depuis
réparé ces deux défauts : jugement exactement symétrisé, matching maximum de
353 paires (90,98 %) et 290 erreurs encore présentes. Ils ont aussi fermé la
piste recherche : Q00 retrouve mieux le choix enseignant que toutes les
ablations, et aucun contrôleur profondeur/pruning n’est budget-neutre dès le
split de découverte.

La question restante porte donc sur l’évaluation : quels coefficients ont
localement classé le mauvais coup devant le meilleur à l’intérieur de la
recherche ? Une simple fréquence de racine ne répond pas à cette question.

## Mesure

Pour chaque décision certifiée de 1476, on fixe avant le nouveau calcul :

- l’action enseignante issue du jugement profond exactement symétrisé ;
- l’action historique fautive pour une erreur ;
- le meilleur rival non choisi pour un contrôle propre ;
- le split `discovery/confirm`, l’ouverture, le modèle et les paramètres Q00.

Le moteur rejoue uniquement les deux enfants à la profondeur 12 déjà certifiée.
Le protocole HUB publie désormais `pvleaf=<FEN>` directement depuis les objets
`Move` complets du moteur. Cela évite toute reconstruction ambiguë des captures
multi-sauts à partir de leurs seuls endpoints. Le score de chaque enfant doit
être strictement identique au score 1476, sinon le job avorte.

À la feuille de PV, le dumper reproduit le design exact du fit : patterns 8cf,
fold exact rot180+échange des couleurs, RMS non concerné, interpolation
`tempo-stage` MG/EG. Pour une orientation, le Jacobien sparse est :

```text
g = signe_du_joueur_racine × (phi(feuille_teacher) − phi(feuille_rivale))
```

La même mesure est refaite sur l’image exacte. Les deux gradients sont moyennés
et leur cosinus est audité. Le moteur de production n’utilisera jamais l’image
exacte : elle reste un instrument de mesure.

Un contrôle à coup légal unique n’a aucun classement alternatif et donc aucun
Jacobien enseignant–rival définissable. Il reste authentifié dans la population
mais est marqué `forced_single_legal_action` et exclu des statistiques contrôle
et appariées : le remplacer par un vecteur nul fabriquerait artificiellement
une paire favorable. Le protocole échoue si ces contrôles dépassent 5 % de la
population ou si moins de 95 % des paires `confirm` restent informatives.

Le matching des 353 paires a précédé le juge profond exactement symétrisé de
1476. Ce juge a préenregistré 290 erreurs exactes de regret au moins 50 cp. Les
63 autres lignes sont ensuite passées sous ce seuil ; certaines ont même une
action enseignante exacte identique à l’action historique et un regret nul.
Ces lignes restent authentifiées mais la paire entière (pseudo-erreur et
contrôle associé) est exclue de toute sélection et de toute statistique de fit.
Elles ne sont jamais transformées en observations nulles. Le job exige
exactement 290 paires informatives ; tout autre compte signale une dérive de
1476 et avorte.

## Sélection scellée

`discovery` fixe une seule direction bornée :

- au moins 6 activations erreur par coordonnée ;
- cohérence de signe d’au moins 75 % ;
- au plus 128 buckets canoniques ;
- MG et EG restent des coordonnées séparées dans le diagnostic, mais le futur
  refit autorisera les deux poids d’un bucket retenu.

Le split `confirm` ne retire ni n’ajoute aucune coordonnée. Il teste une seule
hypothèse agrégée, ce qui évite une déclaration multiple bucket par bucket :

- au moins 70 % des coordonnées répliquent support et signe ;
- IC95 de la projection sur erreurs strictement positif ;
- borne basse IC95 de la projection contrôle au moins `−0,02` ;
- IC95 de `(erreur − contrôle)` strictement positif ;
- permutation appariée par paire, 10 000 signes, `p <= 0,025` ;
- au moins 90 % des mesures original/image ont un cosinus non négatif ;
- entre 8 et 128 buckets canoniques.
- contrôles forcés au plus 5 % et au moins 95 % de paires `confirm`
  informatives.
- exactement 290 erreurs exactes informatives sur les 353 paires authentifiées.

Le bootstrap utilise 100 000 tirages et la seed `2026082222`. Il n’existe aucun
balayage post-hoc des seuils sur `confirm`.

L’exécution utilise quatre workers à la fois. Cette borne ne modifie aucune
observation ni aucun gate ; elle empêche seulement la duplication simultanée
des tables exact-fold dans seize processus. Tout échec de worker publie son
shard, son code retour et les 40 dernières lignes du traceback.

## Sorties et suite conditionnelle

Un PASS produit un `jass.l3_curriculum_error_region.v1` compatible avec le gel
exact déjà implémenté par `train_stream.py` : MG/EG des seuls buckets retenus
sont entraînables, extras et tous les autres poids restent byte-identiques à
CURRICULUM après sérialisation. Ce PASS autorise seulement la préparation du
refit résiduel local et de son bras sham ; il ne lance rien automatiquement.

Un échec publie `JASS_CURRICULUM_ERROR_RESIDUAL_REGION_NOT_ESTABLISHED`, une
liste exhaustive des gates négatifs et `NEXT_STAGE__NONE`. Il ferme alors la
voie « correction de buckets individuels » plutôt que d’abaisser les seuils.

Dans les deux cas : zéro nouvelle partie, zéro self-play, zéro fit, zéro frozen,
zéro gate de force et aucune promotion.
