# CTX3 independent-information screen — préenregistrement

Date : 19 août 2026
Statut : prêt pour exécution read-only

## Point de départ

`cpx62-1415/1415a` a montré qu'une sélection d'états peut équilibrer les
contributions des mappers CTX2 figés tout en contractant la géométrie du
contexte : dimension effective `8,668 → 6,812`, log-déterminant
`−30,389070 → −40,002468`. Le prochain levier doit donc changer la
représentation et non le sampler.

## Représentations prédéfinies

Le baseline est le CTX2 brut 30D. Trois candidats strictement
antisymétriques sont évalués :

1. `odd_curvature` : ajoute pour chacun des quinze signaux la transformation
   `x·|x|`, séparée par phase ;
2. `tactical_magnitude_gates` : ajoute dix interactions dirigées
   `x_i·|x_j|`, séparées par phase ;
3. `combined` : union des deux banques.

Les valeurs absolues servent uniquement de portes invariantes ; le facteur
dirigé conserve le signe noir−blanc. Aucune cible, WDL ou information future
n'entre dans les features.

## Protocole

- corpus immuable `cpx62-1409`, split et hashes de `cpx62-1411` ;
- cinq folds atomiques `opening_id`, poids total égal par partie ;
- ridge linéaire streamé identique pour le baseline et les trois candidats ;
- sélection du candidat sur le train OOF uniquement ;
- confirmation unique sur le holdout disjoint ;
- contrôle causal : les augmentations sont mélangées conjointement à
  l'intérieur de `cohorte × fold × phase(4) × matériel(5)`, le CTX2 brut reste
  aligné ;
- bootstrap apparié par `opening_id`, 5 000 réplications.

La géométrie nouvelle est mesurée après projection linéaire de chaque
augmentation hors du sous-espace CTX2 brut. Un whitening ou une rotation ne
peut donc pas fabriquer le PASS.

## Gates conjointes

Le screen passe seulement si :

- l'IC95 du gain MSE OOF contre CTX2 est strictement positif ;
- au moins quatre folds sur cinq sont positifs ;
- l'IC95 du gain holdout contre CTX2 est strictement positif ;
- aligned bat shuffled sur train OOF et holdout, IC95 strictement positifs ;
- il reste au moins deux directions résiduelles effectives ;
- la médiane de variance résiduelle dépasse le bruit numérique (`1e-3`) ;
- le contrôle shuffled n'a aucun point fixe.

Un PASS autorise uniquement un écran suivant avec le vrai mapper tanh CTX3,
aligned contre shuffled, sur exactement ce corpus. Il n'autorise ni self-play,
ni fit PatternEval, ni partie de force, ni lecture frozen, ni promotion.
