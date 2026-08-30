# L3 — E1/E2/E3 transfer program — O1 terminal amendment

> **Date : 30 août 2026**
> **Statut : amendment preregistration, écrit avant tout lancement E1/E2/E3.**
> Ce document fait partie de la PR `#733` et modifie uniquement les **faits upstream O1** du prereg principal [`L3_F6_TRANSFER_PROGRAM_E1_E3_20260830.md`](L3_F6_TRANSFER_PROGRAM_E1_E3_20260830.md). Les interventions, seeds, volumes, estimands, gates, kill-switches, interdictions et GO distincts E1/E2/E3 du prereg principal restent inchangés sauf contradiction explicitement nommée ci-dessous.

## 1. Fait nouveau observé avant merge de #733 : O1 Gate D PASS

Après rédaction du prereg principal, O1 a poursuivi sa chaîne technique sans aucune partie de force.

Le Gate D complet a été exécuté par :

```text
job     = cpx62-1704-l3-t3-f6-o1-gate-d-preflight-auth-fix-v1
attempt = 20260830T193038Z-53bddb24
code    = 53bddb24a2d144af39df486d8c3e53b7d196cf65
state   = completed
exit    = 0
```

Le run a d'abord réauthentifié le preflight brut O1 et rejoué les Gates A/B/C sur le **même SHA final** avant tout profil D.

Gate D respecte le contrat preregistré :

```text
roots                         = 128
searches                      = 256
threads                       = 1
depth                         = 9
primary wall window           = search-only
setup/teardown in primary     = false
search mismatches OFF vs ON   = 0
nodes OFF == nodes ON         = true
eval calls OFF == eval calls ON = true
strength_games                = 0
scientific_decision           = false
```

Métriques CPX62 terminales publiées :

```text
cache_hit_rate                = 0.322842
wall_ratio_ON_over_OFF        = 0.691964
nps_ratio_ON_over_OFF         = 1.445162
```

Ainsi le cache O1 réduit la fenêtre de recherche mesurée d'environ `30.8 %` et augmente le NPS d'environ `44.5 %` **sans changer un seul résultat ou compteur de recherche faisant partie du contrat d'équivalence**.

Le verdict terminal autorisé par la prereg O1 est `O1_EXACT_CACHE_ESTABLISHED`; sa matérialisation read-only terminale dans `jass-control` est la dernière étape administrative de fermeture O1. Aucune donnée E1/E2/E3 n'a été produite au moment de cet amendment.

## 2. Ce que ce résultat change dans le prereg principal

Toute phrase du prereg principal disant que **Gate D n'a pas encore été lancé**, qu'O1 est seulement `A/B/C PASS`, ou donnant un gain O1 comme simple attente/projection est supersédée par les faits du §1.

La caractérisation correcte devient :

> **O1 est fonctionnellement exact et son Gate D CPX62 est sain. Il apporte environ `1.445x` de NPS / `0.692x` de wall sur la fenêtre search-only, avec `32.3 %` de hits, à arbre strictement identique.**

## 3. Ce que ce résultat ne change PAS

### 3.1 E1 reste nécessaire

Gate D O1 compare **T3-A cache OFF vs T3-A cache ON**. Comme O1 est exact, les deux bras ont nécessairement le même arbre et le même nombre de nœuds. Gate D ne mesure donc **pas** :

```text
nodes_ratio_E1 = nodes(T3-A) / nodes(CURRICULUM)
```

et ne remplace pas E1. La valeur `1.974833` issue de `home-1688` reste une déduction HOME à confirmer directement sur CPX62 par E1 comme preregistré.

### 3.2 Ne pas multiplier naïvement les ratios HOME et CPX62

Les ratios `home-1688` et Gate D O1 proviennent de machines/builds de mesure différents. Les règles permanentes du projet interdisent de transporter aveuglément un rate d'une box à l'autre. Il est donc **interdit** de fabriquer un nouveau coût T3/CURRICULUM CPX62 en multipliant `0.053152` par `1.445162`.

E1 doit mesurer directement sur CPX62 les deux bras pertinents.

### 3.3 E2 reste le verrou causal

O1 n'établit rien sur la valeur en jeu de l'information F6. Il prouve seulement qu'une partie du coût peut être retirée exactement. Le primary estimand E2 reste donc exactement :

```text
delta_info = Elo(C1) + log2(nodes_ratio_E1) * slope(C2)
```

avec le bootstrap conjoint et les gates déjà figés dans le prereg principal.

### 3.4 Aucun nouveau droit de force

O1 Gate D et cet amendment autorisent :

```text
strength games = 0
Pool2 v4       = forbidden
bake            = forbidden
promotion       = forbidden
```

#733 reste une preregistration. Même après son merge, E1, E2 et E3 exigent chacun leur GO explicite distinct et leurs faits machine / sizing pré-lancement tels que déjà écrits.

## 4. Conséquence de programme

Le résultat O1 renforce la séparation entre deux questions :

1. **ingénierie exacte** : O1 récupère ~31 % du wall sans toucher à l'arbre ;
2. **valeur informationnelle** : seule E2 peut établir si F6 apporte un gain de décision une fois le handicap d'arbre explicitement corrigé.

Il ne justifie ni une O2 opportuniste ni une ablation F6. Toute optimisation exacte supplémentaire hors programme E1/E2/E3 exige sa propre couverture preregistrée.
