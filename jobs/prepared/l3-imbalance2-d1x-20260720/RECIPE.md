# D1-X — autopsie RC4 après `D1_RC4_NO_GO`

## Question

Le pilote RC4 a-t-il échoué parce que ses quatre features étaient rarement actives,
ignorées par le fit, fortement colinéaires, ou parce qu'elles étaient actives mais
sans effet causal utile sur les décisions de conversion ?

D1-X est un diagnostic de lecture seule. Il ne doit pas être interprété comme un
pilote search, un nouveau fit ou une autorisation de continuer.

## Sources immuables

- P1 role-aware V2 `ccx33-0852` : corpus brut G4 de 500 000 positions ;
- D1-RC4 `cpx62-0872` : décision, garde généraliste, rapports C64/D64,
  replays sentinelles, contrôle refitté et modèle RC4 ;
- code : SHA mergé exact de la PR D1-X.

## Mesures

1. **Activité des features** sur le corpus G4 brut et sur C64/D64 :
   taux du domaine `|Δ hommes|=2` avec autant de dames, taux non nul par feature,
   quantiles et corrélations.
2. **Poids appris** : poids MG/EG des quatre termes, dérive des poids communs
   contrôle→RC4 et similarité des blocs pattern/extras.
3. **Conversion** : transitions W/D/L appariées, classement des 18 strates et
   positions où RC4 améliore ou dégrade le coût `2L+D`.
4. **Sentinelles** : changement de coup, changement de score et nœuds sur les 30
   cas D0.
5. **Généraliste** : reconstruction déterministe des 64 FEN, paires les plus
   défavorables, matériel racine et raisons de terminaison.

## Sortie

Le rapport produit une classification parmi :

- `RC4_CHANNEL_RARELY_ACTIVE_IN_TRAINING` ;
- `RC4_FEATURES_IGNORED_BY_FIT` ;
- `RC4_ACTIVE_BUT_NONCAUSAL_FOR_CONVERSION` ;
- `RC4_MIXED_FAILURE_REQUIRES_MANUAL_REVIEW`.

Il peut proposer pour revue un seul concept search-only, sous le nom de travail
`S1_ROLE_STABILITY_EXTENSION`, mais ne l'autorise pas.

## Contrats de sécurité

```text
training_authorized=false
search_pilot_authorized=false
promotion_authorized=false
automatic_next_job=null
```

Aucun self-play, aucun entraînement, aucun Scan, aucun EGDB et aucune partie
nouvelle. Le seul calcul moteur est un dump statique des quatre features RC4.

## Exécution

Wrappers interchangeables :

```text
jobs/prepared/l3-imbalance2-d1x-20260720/ccx33-l3-imbalance2-d1x-autopsy.sh
jobs/prepared/l3-imbalance2-d1x-20260720/cpx62-l3-imbalance2-d1x-autopsy.sh
```

Un seul wrapper doit être mis en file après merge, avec le SHA mergé exact.
Durée attendue : environ 5–15 minutes, principalement pour reconstruire
l'extracteur RC4 et dumper les features des 500 000 positions.
