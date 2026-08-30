# L3 — T3-A/F6 Runtime Exact Cache O1 — terminal result

> **Date : 30 août 2026**
> **Statut : terminal technique O1.**
> **Verdict preregistré : `O1_EXACT_CACHE_ESTABLISHED`.**
> Ce résultat est strictement technique : `strength_games=0`, aucune décision scientifique de force, aucun refit/retune/calibration, aucun D1, aucun retrait F6, aucun bake et aucune promotion.

## 1. Question fermée

La preregistration [`L3_T3_F6_RUNTIME_EXACT_CACHE_O1_20260830.md`](L3_T3_F6_RUNTIME_EXACT_CACHE_O1_20260830.md) posait une seule question :

> Peut-on éviter les recomputations F6 répétées pendant une recherche tout en conservant exactement le modèle T3-A, les 66 features F6, les poids, la normalisation, l'arrondi/clamp, le POV et tout le comportement de recherche ?

**Réponse : oui.**

Le cache O1 est fonctionnellement exact sur les gates leaf et search preregistrés, et son coût a été mesuré sainement sur CPX62.

## 2. Identités immuables

```text
T3-A/F6 SHA256   = 16e5db8fd78849bba12b158eee5c1da4ab170129d8aeac1b91ab7a40ad9d0bb2
CURRICULUM SHA256= 319d174f4b548b1655aad4bb30d4c6dc86c08dd715c9c23f8b19ba1937dc0be1
Q00 SHA256       = 61cdaf50cc1948537990331d78f5b296dc6aee71cc7c2b98bcbd0969977619e1
R0 corpus SHA256 = e22b5d8c8a89ff8491ca096a10219f8936f046a9b22977fcf2cfe48f96b309c5
final code SHA   = 53bddb24a2d144af39df486d8c3e53b7d196cf65
```

Le champion de production reste `CURRICULUM`. Le terminal Pool1 v4 `T3_F6_RUNTIME_STRENGTH_NOT_SUPPORTED` reste immuable.

## 3. Contrat O1 effectivement testé

Le cache conserve exclusivement le **résiduel raw `double`** F6. Son contrat reste exactement celui du prereg :

- capacité fixe `65536` ;
- clé complète `white_men, white_kings, black_men, black_kings, side_to_move` ;
- sérialisation canonique de `33` octets, bitboards little-endian puis STM ;
- FNV-1a 64-bit gelé, index `h & 0xFFFF` ;
- direct-mapped déterministe ;
- `valid=false` à vide ; hit seulement si `valid && full_key_equal` ;
- sur miss, ancien chemin exact `extract_f6(pos).all_new()` puis MLP ; clé/résiduel écrits avant `valid=true` ;
- `base_->evaluate(pos)` inchangé et non caché ;
- toutes les 66 features F6 inchangées ;
- modèle, poids, normalisation, précision, rounding/clamp, POV, movegen, qsearch, pruning, ordering, TT et terminal/TB inchangés ;
- activation O1 uniquement sous `threads=1` ;
- Network/cache neuf par unité root×budget ; aucune réutilisation inter-root/inter-budget et aucun warm-up hors recherche mesurée.

## 4. Gates A/B/C — équivalence exacte

La chaîne A/B/C a d'abord passé sur `cpx62-1700-l3-t3-f6-o1-gates-abc-q00-auth-v1`, puis a été **rejouée sur le SHA final du profiler** avant Gate D dans `1704`.

### Gate A

- build Release production avec EGDB ;
- tests cache miss/hit/collision/remplacement/STM/valid/FNV/concurrence/lifecycle ;
- tests natifs T3/F6 ;
- `O1_GATE_A_PASS`.

### Gate B — leaf

Support exact : `4096` positions R0-v4.

```text
raw residual mismatches        = 0
integer score mismatches       = 0
replay residual mismatches     = 0
replay score mismatches        = 0
flush residual mismatches      = 0
flush score mismatches         = 0
saturations                    = 0
nonfinite                      = 0
real cache hits                > 0
```

### Gate C — search

Support exact : `64` racines, `16` par phase, quatre budgets par racine (`depth 1`, `depth 9`, `nodes 1000`, `nodes 10000`), soit `256` paires OFF/ON.

Le contrat complet `same_result` est identique sur chaque paire, incluant best move, score, depth/effective/completed depth, stop reason, nodes, cutoffs, PVS, eval calls, qsearch, TB, TT, reductions/extensions, root ordering, PV et book state.

```text
search mismatches = 0
cache-hit evidence > 0
```

Aucune mesure de coût n'a été interprétée avant cette équivalence.

## 5. Gate D CPX62 — coût technique

Run terminal de profil :

```text
job     = cpx62-1704-l3-t3-f6-o1-gate-d-preflight-auth-fix-v1
attempt = 20260830T193038Z-53bddb24
code    = 53bddb24a2d144af39df486d8c3e53b7d196cf65
state   = completed
exit    = 0
host    = cpx62
nproc   = 16
```

Le préflight obligatoire avait été exécuté et authentifié avant le GO explicite Gate D. Le premier full-run `1703` avait échoué **avant Gate D** sur une erreur purement technique d'authentification du format de reçu (`1702` readout pris pour le reçu raw `1701`). `1704` a corrigé uniquement cette plomberie et a réutilisé le contrat scientifique/technique inchangé.

### Support exact Gate D

```text
roots                    = 128 (32 / phase)
searches                 = 256
threads                   = 1
depth                     = 9
TT                        = 16 MiB
order_seed                = 2026092505
primary wall window       = search-only
setup/teardown included   = false
OFF/ON order              = alterné par index de racine
search mismatches         = 0
nodes OFF == nodes ON     = true
eval calls OFF == ON      = true
strength_games            = 0
scientific_decision       = false
```

### Mesures

```text
cache_hit_rate          = 0.322842
wall_ratio ON / OFF     = 0.691964
nps_ratio  ON / OFF     = 1.445162
```

Interprétation descriptive :

- environ **32,3 %** des lookups O1 sont des hits ;
- la fenêtre de recherche O1 prend environ **69,2 %** du temps OFF, soit **~30,8 % de wall économisé** ;
- le NPS est multiplié par environ **1,445** (`+44,5 %`) ;
- l'arbre étant strictement identique, le gain observé est uniquement un gain de coût d'évaluation, pas un changement de search.

Aucun seuil de performance n'était un gate O1 : le PASS vient de l'équivalence exacte A/B/C plus l'exécution saine de D.

## 6. Verdict terminal

```text
VERDICT = O1_EXACT_CACHE_ESTABLISHED
gate_a = PASS
gate_b = PASS
gate_c = PASS
gate_d = PASS
strength_games = 0
scientific_decision = false
promotion_authorized = false
bake = false
```

La matérialisation read-only finale est `cpx62-1705-l3-t3-f6-o1-terminal-receipt-v1`; son attempt exact est ajouté au présent document dès publication du reçu runner.

## 7. Ce qu'O1 établit — et ce qu'il n'établit pas

O1 établit qu'une partie des recomputations F6 peut être supprimée **exactement**.

O1 **n'établit pas** :

- que T3-A est compétitif contre CURRICULUM au runtime ;
- que le signal F6 a une valeur causale positive en jeu ;
- un nouveau droit de force ;
- une autorisation Pool2/bake/promotion ;
- la valeur CPX62 du ratio de nœuds T3-A / CURRICULUM.

En particulier, les ratios HOME de `1688` ne doivent pas être multipliés naïvement par le gain CPX62 O1 : les règles du projet interdisent le transport aveugle de rates entre machines/builds de mesure différents.

## 8. Frontière suivante

Aucune O2 n'est autorisée automatiquement par ce terminal. La piste suivante est le programme de transfert E1/E2/E3 de la PR `#733`, qui répond à une question différente : **la valeur de l'information F6 une fois son coût et son effet d'expansion d'arbre séparés**.

Même après merge de cette preregistration, chaque bloc E1/E2/E3 conserve son propre GO explicite et ses checks pré-lancement. Aucun strength game n'est implicitement autorisé.
