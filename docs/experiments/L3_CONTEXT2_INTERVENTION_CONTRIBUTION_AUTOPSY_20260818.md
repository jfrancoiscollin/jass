# CTX2 intervention contribution autopsy — preregistration

Date: 18 août 2026  
Statut: prêt pour exécution, aucun fit autorisé

## Point de départ

Le corpus CTX2-Intervention-v1 de `cpx62-1409` a bien augmenté la diversité
d'activation (`cpx62-1410`: log-déterminant `+0.424522` contre BASE, 30/30
canaux actifs), mais son mapper aligné a échoué aux trois gardes de
concentration dans `cpx62-1411`:

- top-1 `0.591086`, soit `1.030732 × CURRENT`;
- top-3 `0.786798`, soit `1.026244 × CURRENT`;
- composantes effectives `2.649`, soit `0.944905 × CURRENT`.

L'amélioration de covariance brute ne s'est donc pas transformée en
contributions conditionnelles plus réparties. Aucun fit PatternEval n'a été
lancé.

## Question causale

Le mauvais résultat vient-il seulement des quotas entre les six cellules, ou
les cinq interventions testées n'engendrent-elles pas les directions de signal
conditionnel nécessaires?

## Protocole immuable

Le diagnostic relit les artefacts certifiés de `1409`, `1411` et `home-1397`.
Il reconstruit byte-identiquement le split `opening_id`, recalcule les features
CTX2 avec le dumper de production, puis rejoue sans refit les cinq mappers OOF
et le mapper final de `1411`.

Chaque position est rattachée à sa cellule source:

- `BASE`;
- `ROP16`;
- `EPS16`;
- `DECAY120`;
- `TOPK3M30`;
- `DEPTH10`.

L'analyse publie pour chaque cellule et chaque composante:

- contribution logit absolue moyenne;
- effet local absolu sur la cible dosée à alpha `0.30`;
- part de contribution et taux de dominance;
- top-1, top-3 et nombre effectif de composantes;
- contraste mono-facteur contre BASE;
- effet leave-one-cell-out sur la concentration globale.

La recomposition globale doit reproduire l'audit `1411` à `2e-10` près.

## Test de sauvetage par quotas

Une grille exhaustive à pas `0.05` teste les mélanges des six cellules avec:

- minimum `0.05` par cellule;
- maximum `0.50` par cellule;
- dérive relative du taux de nulles contre BASE au plus `0.15`;
- skew WDL entre côtés au plus `0.02`.

Les trois gardes de `1411` restent inchangées:

- top-1 au plus `90 %` de CURRENT;
- top-3 au plus `95 %` de CURRENT;
- composantes effectives au moins `125 %` de CURRENT.

Deux conclusions seulement sont permises:

1. `quota_only_rescue_exists_under_fixed_mapper`: un mélange admissible passe
   les trois gardes; il devient une prédiction à confirmer avec un nouveau
   mapper, jamais une autorisation de fit PatternEval;
2. `existing_generation_knobs_do_not_span_the_required_conditional_contribution_directions`:
   aucun mélange ne passe; les cinq boutons existants sont fermés comme simple
   solution de réallocation et le prochain pilote doit cibler directement les
   composantes sous-représentées.

## Interdictions

Aucun mapper n'est refitté, aucun PatternEval n'est entraîné, aucune partie
n'est jouée, aucun self-play n'est généré, aucun frozen n'est lu et aucune
promotion ou continuation automatique n'est autorisée.

## Coût

Le job comparable `1411` a duré 323 secondes sur `cpx62` 16 CPU. L'autopsie
répète le fetch, le build et le dump mais retire les six fits mapper: ETA
préenregistrée `5–12 minutes`, timeout global du wrapper `30 minutes`.
