# L3 — apprentissage local des erreurs de CURRICULUM v1

Date : 22 août 2026

Statut : mécanisme et critères préenregistrés ; aucune exécution autorisée par ce document seul

Promotion automatique : interdite

## Question

Peut-on partir des parties réellement perdues par le champion, localiser les
décisions où une recherche plus profonde du **même champion** trouve une action
meilleure, identifier les buckets PatternEval associés, puis corriger seulement
ces buckets sans dégrader le reste du modèle ?

La chaîne teste quatre affirmations dans cet ordre :

1. la défaite contient une erreur de décision mesurable, pas seulement un
   mauvais résultat terminal ;
2. les mêmes buckets sont enrichis en erreurs sur des ouvertures de
   confirmation jamais utilisées pour les découvrir ;
3. un refit ciblé réduit ces regrets sur un holdout scellé tout en laissant les
   autres poids du champion strictement inchangés ;
4. la correction se convertit en force générale sur deux pools frais.

Une défaite n'est donc **jamais** utilisée directement comme exemple dur. Cette
garde répond à l'échec autoritatif du hard replay `failed_conversion` : la
sélection par issue terminale avait déplacé le prior WDL et produit `−648 Elo`.

## Sources à épingler dans la PR d'activation

La PR d'activation future doit fixer avant lecture des regrets :

- le modèle CURRICULUM et son SHA brut ;
- le binaire exact-fold/tempo-stage et ses paramètres de recherche ;
- au moins deux campagnes fraîches dont **toutes** les parties sont dumpées,
  gagnées, nulles et perdues ;
- les pools d'ouvertures, couleurs, budgets et hashes ;
- le corpus historique exact de CURRICULUM, son sidecar, son split
  `opening_id` et ses hashes ;
- les seeds de split, de matching, de génération ciblée et de bootstrap.

Les parties perdues seules ne suffisent pas : les parties gagnées/nulles du
même gate fournissent les contrôles appariés nécessaires pour ne pas confondre
« bucket fréquent » et « bucket causalement faible ».

## Étape A — autopsie décisionnelle read-only

Implémentation : `jobs/tools/l3_curriculum_error_learning.py`.

### Split scellé

`prepare` affecte chaque `opening_id` à `discovery` ou `confirm` par hash avant
toute recherche profonde. Toutes les décisions d'une ouverture restent dans la
même moitié. Chaque coup joué par CURRICULUM est conservé. Le prepareur échoue
si une position, canonisée sous la symétrie exacte rot180+colour-swap, apparaît
dans les deux moitiés : une transposition ne peut donc pas contaminer la
confirmation.

### Regret

Pour chaque décision historique :

1. CURRICULUM est rejoué à profondeur 10 pour proposer une action ;
2. si elle diffère de l'action historique, les deux enfants sont jugés à
   profondeur 12 par CURRICULUM ;
3. les valeurs enfants STM sont remises dans le POV racine par
   `V_root(action) = -V_child_stm` ;
4. `regret = V_root(action_d10) - V_root(action_historique)`.

Le teacher est le même modèle avec davantage de calcul. Il n'y a ni Scan, ni
oracle externe, ni EGDB injectée dans les cibles. Des sondes exactes
rot180+colour-swap doivent être identiques au centipion près.

Une erreur candidate exige conjointement :

- partie perdue par CURRICULUM ;
- action profonde différente ;
- regret d'au moins 50 cp ;
- au plus une erreur, la plus coûteuse, par `opening_id`.

Une ligne de contrôle vient d'une partie gagnée ou nulle, a un regret maximal
de 10 cp et est appariée sans remise dans le même
`split × phase × présence de dames × capture/quiet`.

### Attribution des buckets

Sur `discovery`, un bucket doit apparaître dans au moins 4 erreurs et avoir un
risque relatif erreur/contrôle d'au moins 1,5. Seuls les 512 meilleurs buckets
peuvent atteindre `confirm`.

Sur `confirm`, le risque relatif doit rester au moins 1,5 et la borne basse
Wilson 95 % de sa fréquence dans les erreurs doit dépasser la borne haute dans
les contrôles. Le screen passe seulement si :

- au moins 64 ouvertures perdues contiennent une erreur qualifiée ;
- au moins 80 % ont un contrôle apparié ;
- les deux splits sont non vides ;
- la symétrie exacte passe ;
- au moins 8 buckets sont confirmés.

Le certificat `JASS_CURRICULUM_ERROR_REGION_CONFIRMED` publie alors :

- `jass.l3_curriculum_error_region.v1` ;
- un JNNW de graines neutres, une par ouverture erronée confirmée ;
- toutes les décisions et statistiques discovery/confirm.

Un screen négatif interdit la génération et le fit. Il ne déclenche pas un
abaissement post-hoc des seuils.

## Étape B — petit corpus de réparation

Seulement après PASS de A :

- démarrer 100 % des parties depuis les graines d'erreur confirmées ;
- générer exactement 500 000 nouvelles positions avec CURRICULUM comme parent ;
- mêmes paramètres de jeu et d'étiquette dans tous les bras ;
- pair-openings, `opening_id`, couleurs et hashes obligatoires ;
- WDL naturel, sans suréchantillonnage des victoires/défaites ;
- holdout par opening avant toute pondération ;
- garder au plus deux trajectoires par graine et contrôler la concentration.

Le générateur doit donc utiliser `--seed-frac 100`,
`--seed-without-replacement` et `--pair-openings`. Le mode sans remise parcourt
une permutation déterministe du catalogue et avorte si les graines sont
épuisées avant 500 000 lignes ; il ne
retombe jamais sur une graine déjà consommée. Les compteurs
`seed_unique_used` et `seed_reuses=0` font partie du certificat.

Le corpus de réparation n'est pas la partie perdue répétée. C'est une nouvelle
distribution de continuations à partir de l'état où l'erreur a été mesurée.

## Étape C — refit local strict

Le corpus d'entraînement mélange :

- 80 % de masse de loss effective : replay opening-stratifié du corpus
  CURRICULUM original ;
- 20 % : toutes les nouvelles lignes de réparation.

Le ratio 80/20 est fixé pour la première expérience et ne sera pas balayé sur
les mêmes gates. `tools/contextual_replay_mix.py` produit les poids float32 et
garantit que les holdouts ne sont jamais lus dans le train.

Le candidat utilise :

```bash
python3 pattern_jass/tools/train_stream_exact.py \
  --data repair-mix.jnnw --feat repair-mix.feat \
  --target wdl --loss logistic \
  --sample-weights repair-mix-weights.npy \
  --weight-min "$WEIGHT_MIN" --weight-max "$WEIGHT_MAX" \
  --weights-report repair-weights.json \
  --prior-mean CURRICULUM.pjtw --prior-decay 0 \
  --exact-fold --tempo-stage --prune-min-visits 1 \
  --trainable-region error-region.json \
  --trainable-region-report frozen-region-audit.json \
  ...recette L2/optimiseur identique à CURRICULUM...
```

Le nouvel argument `--trainable-region` optimise uniquement les coordonnées MG
et EG des buckets confirmés. Les extras denses sont figées en v1. Tous les
autres coefficients restent au parent ; le trainer relit le PJTW produit et
échoue si un seul coefficient hors zone diffère du champion après
sérialisation. Ce n'est pas un gros L2 approximatif : c'est un gel exact.

Deux bras sont nécessaires :

- `A — SHAM_REGION` : même nombre de buckets, tirés dans les contrôles appariés,
  même corpus, mêmes poids, même prior ;
- `B — ERROR_REGION` : buckets confirmés.

Le contraste primaire `B−A` sépare l'effet de la zone d'erreur du simple fait
d'autoriser quelques coefficients à bouger. CURRICULUM inchangé reste la
référence anti-régression.

Les deux optimiseurs doivent converger. Une baisse de loss ne sélectionne rien.

## Étape D — gates

### Gate mécanistique scellé

Sur des parties perdues et ouvertures jamais lues par discovery/confirm :

- baisse du regret moyen et du taux d'erreurs ≥50 cp pour B contre A ;
- bootstrap par `opening_id`, IC95 de l'amélioration excluant zéro ;
- aucune hausse établie des regrets hors région ;
- stabilité du WDL et de la loss du holdout CURRICULUM original.

### Gate de force

Si et seulement si le gate mécanistique passe :

1. `B` contre `A` sur deux pools frais disjoints ;
2. `B` contre CURRICULUM sur deux autres pools frais disjoints ;
3. native 0,1 s primaire, Q00 d9 diagnostic ;
4. couleurs appariées, 6 000 parties par pool et par vue ;
5. bootstrap opening-cluster 200 000.

La direction est retenue seulement si, pour le contraste natif B−CURRICULUM :

- chaque pool est >50 % ;
- les pools sont compatibles à 95 % ;
- l'IC95 combiné exclut 50 % ;
- `P(taux>50 %) >= 0,975` ;
- le stress-gate des anciennes erreurs ne régresse pas.

Q00 ne peut pas renverser le verdict natif. Aucun PASS ne promeut
automatiquement le modèle.

## Ce que cette PR fait

- ajoute l'autopsie all-games → regret → attribution discovery/confirm ;
- produit des graines de réparation et une région auditable ;
- ajoute au trainer le refit local avec gel exact hors région ;
- ajoute les tests unitaires des gardes et du gel.

## Ce qu'elle ne fait pas

- ne choisit pas post-hoc une campagne de parties ;
- ne lance ni self-play, ni fit, ni partie de force ;
- ne lit aucune cohorte frozen ;
- ne modifie pas le champion ;
- n'autorise aucune promotion ou continuation automatique.
