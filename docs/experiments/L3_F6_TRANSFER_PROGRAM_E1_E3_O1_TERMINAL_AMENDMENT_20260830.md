# L3 — E1/E2/E3 transfer program — O1 terminal amendment

> **Date : 30 août 2026**
> **Statut : amendment preregistration, écrit avant tout lancement E1/E2/E3.**
> Ce document fait partie de la PR `#733` et modifie les **faits upstream O1** et ferme trois ambiguïtés de protocole du prereg principal [`L3_F6_TRANSFER_PROGRAM_E1_E3_20260830.md`](L3_F6_TRANSFER_PROGRAM_E1_E3_20260830.md). Les autres interventions, seeds, volumes, gates, kill-switches, interdictions et GO distincts E1/E2/E3 du prereg principal restent inchangés.

## 1. Fait nouveau observé avant merge de #733 : O1 terminal

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
roots                            = 128
searches                         = 256
threads                          = 1
depth                            = 9
primary wall window              = search-only
setup/teardown in primary        = false
search mismatches OFF vs ON      = 0
nodes OFF == nodes ON            = true
eval calls OFF == eval calls ON  = true
strength_games                   = 0
scientific_decision              = false
```

Métriques CPX62 terminales publiées :

```text
cache_hit_rate                = 0.322842
wall_ratio_ON_over_OFF        = 0.691964
nps_ratio_ON_over_OFF         = 1.445162
```

Ainsi le cache O1 réduit la fenêtre de recherche mesurée d'environ `30.8 %` et augmente le NPS d'environ `44.5 %` **sans changer un seul résultat ou compteur de recherche faisant partie du contrat d'équivalence**.

Le reçu read-only terminal est lui aussi terminé :

```text
job     = cpx62-1705-l3-t3-f6-o1-terminal-receipt-v1
attempt = 20260830T195143Z-53bddb24
code    = 53bddb24a2d144af39df486d8c3e53b7d196cf65
state   = completed
exit    = 0
verdict = O1_EXACT_CACHE_ESTABLISHED
```

Le reçu publie explicitement `O1_EXACT_CACHE_ESTABLISHED`, `O1_GATE_A_PASS`, `O1_GATE_B_PASS`, `O1_GATE_C_PASS`, `O1_GATE_D_PASS`, `O1_TERMINAL_READY`, `STRENGTH_GAMES__0`, `PROMOTION_AUTHORIZED__FALSE` et `BAKE__FALSE`. Aucune donnée E1/E2/E3 n'a été produite avant cet amendment.

## 2. Ce que ce résultat change dans le prereg principal

Toute phrase du prereg principal disant que **Gate D n'a pas encore été lancé**, qu'O1 est seulement `A/B/C PASS`, ou donnant un gain O1 comme simple attente/projection est supersédée par les faits du §1.

La caractérisation correcte devient :

> **O1 est `O1_EXACT_CACHE_ESTABLISHED`. Son Gate D CPX62 apporte environ `1.445x` de NPS / `0.692x` de wall sur la fenêtre search-only, avec `32.3 %` de hits, à arbre strictement identique.**

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

### 3.3 E2 reste le verrou du programme

O1 n'établit rien sur la valeur en jeu de l'information F6. Il prouve seulement qu'une partie du coût peut être retirée exactement. Le primary estimand E2 reste :

```text
delta_info = Elo(C1) + log2(nodes_ratio_E1) * slope(C2)
```

avec le bootstrap conjoint et les gates déjà figés dans le prereg principal.

### 3.4 Aucun nouveau droit de force

O1 terminal et cet amendment autorisent :

```text
strength games = 0
Pool2 v4       = forbidden
bake            = forbidden
promotion       = forbidden
```

#733 reste une preregistration. Même après son merge, E1, E2 et E3 exigent chacun leur GO explicite distinct et leurs faits machine / sizing pré-lancement tels que déjà écrits.

## 4. Clarifications gelées avant E1/E2/E3

### 4.1 E1 — état du cache pendant l'attribution de coût

Le prereg principal pouvait laisser implicitement ouverte la question « cache ON ou OFF » pendant l'instrumentation E1. Elle est maintenant fermée :

- **E1 primaire utilise T3-A avec cache O1 OFF.** Les chronomètres F1..F5/MLP/base mesurent ainsi le coût intrinsèque de l'évaluateur F6, sans conditionnement par le hit-rate d'un cache ;
- `nodes_ratio_E1 = sum(nodes_T3_A)/sum(nodes_CURRICULUM)` est calculé sur ce même bras T3-A cache OFF et CURRICULUM, mêmes `128` racines depth-9 ;
- O1 ayant établi l'équivalence exacte de l'arbre, une répétition cache ON ne peut être qu'un **contrôle technique non primaire** de l'égalité des nodes. Elle ne peut ni remplacer le ratio primaire, ni modifier une décision E1, ni sélectionner une variante ;
- aucune autre taille/hash/lifecycle de cache n'est testée dans E1.

Cette clarification ne choisit aucune variante à partir du résultat O1 : elle fixe simplement la baseline non mémoïsée nécessaire pour attribuer le coût F1..F5.

### 4.2 E2 — portée exacte de `delta_info`

`C1` est le contraste expérimental direct à nœuds égaux. En revanche, `delta_info` est une **décomposition mécanistique preregistrée**, pas une identification non-paramétrique garantie du « pur effet information F6 ».

Elle repose explicitement sur l'approximation locale suivante :

1. autour des budgets `10k→20k`, la réponse Elo de CURRICULUM à un facteur de nœuds est localement représentable par `slope(C2) * log2(facteur)` ;
2. ce péage local peut être appliqué au `nodes_ratio_E1` mesuré à depth-9 pour construire le contre-factuel `h0_c1` ;
3. l'interaction résiduelle entre identité de l'évaluateur et réponse marginale aux nœuds n'est pas séparément identifiée par E2.

Conséquence :

- une CI95 basse de `delta_info > 0` autorise **uniquement la poursuite du mécanisme de transfert E3** selon la politique pré-déclarée ;
- elle ne signifie pas « T3-A est prouvé plus fort » et ne peut autoriser bake/promotion/Pool2 ;
- `elo_c1` et ses diagnostics de profondeur/nodes restent publiés séparément afin que la donnée directe ne soit jamais masquée par le modèle de décomposition ;
- si `C2` n'établit pas une pente positive ou si les gardes du harnais échouent, E2 reste inconclusif comme déjà preregistré.

Aucune autre forme fonctionnelle, pente ou correction post-hoc ne peut remplacer cette décomposition après lecture des données.

### 4.3 E3 — corpus de fit résolu de manière unique

La phrase « corpus courant du champion » ne donne **aucun droit de choisir un dataset au moment du job**. Avant le premier label T3-A E3 et avant le fit, le job doit résoudre fail-closed une seule provenance :

> **le byte-stream exact utilisé comme entrée de données du dernier stage de fit ayant produit les bytes CURRICULUM SHA256 `319d174f4b548b1655aad4bb30d4c6dc86c08dd715c9c23f8b19ba1937dc0be1`.**

Règles :

- l'identité doit provenir d'un reçu/manifest historique immuable qui relie explicitement ce stage final aux bytes CURRICULUM ;
- publier avant tout fit : job/attempt source, URI/nom d'artefact, SHA256 du corpus, nombre de lignes/parents et SHA/config de la recette source ;
- si plusieurs corpus peuvent raisonnablement satisfaire la description, si le manifest ne permet pas de désigner **un unique artefact**, ou si son SHA ne peut pas être authentifié, verdict `E3_TECHNICAL_FAILED` **avant fit** ; aucune sélection manuelle n'est permise ;
- dans une chaîne multi-stage, les données d'un pré-entraînement antérieur ne sont pas concaténées automatiquement : seul l'input byte-exact du **stage final qui produit les bytes champion** est ré-étiqueté, sauf si ce stage final consommait lui-même explicitement un artefact déjà concaténé ;
- volume, lignes, poids/duplications et ordre du corpus restent ceux de cet artefact ; seule la cible pairwise est remplacée par le teacher T3-A conformément au prereg principal ;
- le corpus `1638/1639/1640` et toutes les autres exclusions déjà gravées restent interdits.

Ainsi E3 ne possède plus de degré de liberté de choix de corpus après observation.

## 5. Conséquence de programme

Le résultat O1 renforce la séparation entre deux questions :

1. **ingénierie exacte** : O1 récupère ~31 % du wall sans toucher à l'arbre ;
2. **valeur informationnelle / mécanisme de transfert** : E2 teste le contraste direct C1 puis la décomposition `delta_info` preregistrée ; seul son gate peut ouvrir E3.

Il ne justifie ni une O2 opportuniste ni une ablation F6. Toute optimisation exacte supplémentaire hors programme E1/E2/E3 exige sa propre couverture preregistrée.
