# L3 adaptive shadow B2 — implémentation et preflight statistique synthétique v1

> **STATUS: PREFLIGHT SYNTHETIC-ONLY 1774 TERMINÉ ET AUTHENTIFIÉ — B2 NON PRÉENREGISTRÉ, NON GELÉ**

Le reçu terminal du §14 actualise l'état d'exécution. Les mentions « futur » et « non exécuté » des sections initiales décrivent l'état au moment de l'implémentation, avant le lancement 1774 ; ses paramètres sont restés inchangés.

Date : 2026-09-05, Europe/Paris.

## 1. Portée

Ce document spécifie l'implémentation statistique prospective issue du draft B2 v3 et de sa revue indépendante v2. Il ne change aucun endpoint, seuil, support, seed, ordre, type, quantile ou nombre de réplications.

Fichiers possédés par cette étape :

```text
jobs/tools/adaptive_sibling_b2_statistics.py
jobs/tests/test_adaptive_sibling_b2_statistics.py
docs/experiments/L3_ADAPTIVE_SHADOW_B2_STATISTICAL_PREFLIGHT_V1_20260905.md
```

L'implémentation consomme seulement des lignes de statistiques suffisantes déjà scellées. Elle ne reçoit aucun full ladder, score brut, label q200, position historique, FEN, sibling, modèle ou objet de policy. Elle ne réexécute jamais la policy et ne touche pas au projecteur q200-free.

Cette étape de code n'autorise :

```text
preflight complet 800M    = non exécuté
donnée B2 fraîche         = 0
lecture historique        = 0
teacher/search            = 0
partie/fit                = 0
promotion/bake            = false
commit/push/job           = 0
```

## 2. Paramètres prospectifs conservés

```text
parents                   = 4000
cellules                  = 8
parents/cellule           = 500
bootstrap R               = 200000
seed SplitMix64           = 2026110717
alpha global              = 0.05
alpha cellulaire          = 0.05/8 = 0.00625
ordre des cellules        = P0_stm0,P0_stm1,P1_stm0,P1_stm1,
                            P2_stm0,P2_stm1,P3_stm0,P3_stm1
ordre de boucle           = réplication, cellule, 500 tirages
quantile                  = inverse EDF type 1
arithmétique entrée       = uint64/int64 vérifiée
conversion ratios         = IEEE-754 binary64 après sommes entières
```

Le CLI ne possède aucun argument `--replications`, `--seed`, `--alpha`, `--cells` ou `--cell-size`. Son preflight appelle toujours l'entrée publique à R=200 000. Une fonction privée accepte un petit R uniquement pour les tests locaux ; elle n'est ni exposée par le CLI ni utilisée par le chemin production.

## 3. API ParentStatsSufficientV1

Le `ParentStatsV1` normatif du draft v3 reste le type riche du readout : il contient notamment rows, scores, bands, families, catégorie de comparaison, ledger et hashes upstream. Ce module ne réutilise pas son nom ni son schéma. Il consomme une projection statistique distincte, `ParentStatsSufficientV1`, avec le schéma `jass.adaptive_sibling_b2_parent_stats_sufficient.v1`.

Dans le futur chemin B2, la jointure produit et scelle d'abord les 4 000 lignes riches. Après validation du ledger exhaustif, un projecteur déterministe 1:1 écrit exactement une ligne suffisante par `parent_id`, dans le même ordre. Son reçu doit publier le SHA des bytes `ParentStatsV1` riches, le SHA des bytes suffisants, les deux nombres de lignes égaux à 4 000, l'égalité ordonnée des `parent_id`, le succès du ledger externe et le SHA du code de projection. Toute perte, duplication, réorganisation ou validation de ledger absente échoue avant ce module. Le preflight synthetic-only exerce exactement le parser et le wire suffisants qui seront ensuite utilisés ; il n'invente pas de faux ledger riche synthétique.

Chaque ligne JSONL contient exactement :

| Champ | Type | Contrat |
|---|---|---|
| `schema` | string | `jass.adaptive_sibling_b2_parent_stats_sufficient.v1` |
| `parent_id` | int64 non négatif | unique, ordre global strictement croissant |
| `cell` | enum | une des huit cellules, exactement 500 lignes par cellule |
| `full_nodes` | uint64 | strictement positif |
| `shadow_nodes` | uint64 | non négatif |
| `fully_nonexact` | bool | définit le sous-groupe de saving |
| `same_row` | bool | implique `value_equivalent` |
| `value_equivalent` | bool | équivalence déjà classifiée après jointure |
| `exact_mismatch` | bool | incompatible avec value-equivalence et signal |
| `signal_event` | bool | exactement l'union des trois directions descendantes |
| `signal_direction_code` | int | enum fermé 0..6, publié séparément |
| `numeric_eligible` | bool | soustraction q200 admissible |
| `numeric_component` | int64 non négatif | delta si éligible, zéro si inéligible ou value-equivalent |

Les booléens doivent être de type bool exact ; les entiers ne peuvent pas être des booléens. Les lignes ont JSON canonique UTF-8/LF, clés triées, séparateurs compacts, `allow_nan=false`, newline final.

Codes de direction :

```text
0 NONE
1 WIN_TO_UNRESOLVED
2 WIN_TO_LOSS
3 UNRESOLVED_TO_LOSS
4 LOSS_TO_UNRESOLVED
5 LOSS_TO_WIN
6 UNRESOLVED_TO_WIN
```

`signal_event` doit être vrai si et seulement si le code vaut 1, 2 ou 3. Tout code non nul est incompatible avec value-equivalence, exact mismatch et numeric eligibility. `exact_mismatch` est également incompatible avec numeric eligibility : une paire exacte/exacte ou mixte ne peut pas contaminer les endpoints de soustraction entre deux choix non exacts. Les six directions sont comptées séparément globalement et par cellule ; `WIN_TO_LOSS` ne peut donc pas disparaître dans l'union.

Composantes dérivées :

```text
moderate_1_99 = numeric_component si 1 <= component <= 99, sinon 0
total_component = numeric_component
numeric_ge_100 = 1 si eligible et delta >= 100, sinon 0
```

Dans le type riche, `delta` reste `undefined` lorsque la soustraction est inéligible, conformément au draft v3. Seule la projection suffisante matérialise alors `numeric_component=0`; ce champ ne doit jamais être interprété comme un delta défini.

Le module valide la borne maximale par cellule puis la somme des huit bornes avant le bootstrap. Cette preuve garantit que tout cumul possible sous le rééchantillonnage stratifié tient en uint64 pour les nœuds et en int64 pour les deltas. Les sommes observées utilisent aussi des additions vérifiées. Zéro dénominateur, overflow, non-finite ou dérive de type échoue fermé.

## 4. Estimands

Les ratios de saving sont toujours des ratios de sommes :

```text
all_parent_saving = 1 - sum(shadow_nodes)/sum(full_nodes)
fully_nonexact_saving =
  1 - sum(shadow_nodes | fully_nonexact)/sum(full_nodes | fully_nonexact)
```

Les autres estimands globaux sont :

```text
same_row_rate
value_equivalence_rate
conditional_numeric_mean = sum(delta)/count(numeric_eligible)
all_parent_component_mean = sum(delta)/4000
```

`conditional_numeric_mean` et `all_parent_component_mean` restent distincts. Le premier mesure la sévérité là où la soustraction est admissible. Le second mesure la contribution numérique par parent sélectionné et reste descriptif ; zéro pour l'inéligible ne prétend pas que son regret total est nul.

Par cellule :

```text
all_parent_saving
fully_nonexact_saving
value_equivalence_rate
signal_event_rate
moderate_1_99_mean = sum(moderate_1_99)/500
total_component_mean = sum(total_component)/500
numeric_ge_100_rate = count(numeric_ge_100)/500
```

Les exacts et inéligibles restent dans le dénominateur fixe 500 des trois taux CP comme non-événements.

## 5. Bootstrap exact

Les 500 lignes suffisantes de chaque cellule sont ordonnées par `parent_id`. Pour chaque réplication 0..199999 et chaque cellule dans l'ordre normatif, le moteur tire 500 indices avec remplacement.

SplitMix64 :

```text
state += 0x9E3779B97F4A7C15 modulo 2^64
z = state
z = (z ^ (z >> 30)) * 0xBF58476D1CE4E5B9 modulo 2^64
z = (z ^ (z >> 27)) * 0x94D049BB133111EB modulo 2^64
u = z ^ (z >> 31)
```

Pour `n=500`, `limit=2^64-(2^64 mod 500)=18446744073709551500`. Le générateur rejette `u>=limit`, sinon retourne `u mod 500`. Il publie tirages acceptés, uint64 générés et rejets.

Les 20 uint64 et les 20 indices de référence du draft v3 sont des tests obligatoires. Aucun autre PRNG, NumPy, SciPy ou parallélisme modifiant l'ordre du flux n'est utilisé.

Chaque réplication recalcule depuis les lignes tirées :

- les six séries globales : deux savings, same-row, value-equivalence, moyenne conditionnelle et composante tous-parents ;
- quatre séries dans chacune des huit cellules : deux savings, moyenne modérée et composante totale.

Une réplication sans fully-nonexact ou sans numeric-eligible rend le résultat `INVALID_UNKNOWN`. Elle n'est jamais supprimée ou remplacée.

Le CLI écrit atomiquement `progress.json` toutes les 1 000 réplications et à la réplication finale. Il publie réplications terminées/total, tirages acceptés, uint64 générés, rejets et temps écoulé. Ce reporting ne consomme aucun tirage et ne change pas l'ordre du flux.

Les quantiles trient les R valeurs binary64 et appliquent :

```text
Q(p) = x_sorted[ceil(p*R)-1]
LCB95 global        Q(0.05),    index 9999
UCB95 global        Q(0.95),    index 189999
LCBsim95 cellulaire Q(0.00625), index 1249
UCBsim95 cellulaire Q(0.99375), index 198749
```

Il n'y a aucune interpolation ou suppression de valeur.

## 6. Clopper-Pearson

Les trois familles binomiales utilisent `n=500` dans chaque cellule :

- LCB de value-equivalence ;
- UCB de l'union des abaissements de signal ;
- UCB de `numeric_ge_100`.

Le solveur standard-library effectue exactement 256 bissections binary64. La CDF binomiale somme les termes `j=0..x` en log-space avec `math.lgamma`, `math.log`, `math.log1p`, `math.exp` et `math.fsum`. Les cas x=0 et x=n sont fermés explicitement.

Les huit références obligatoires sont :

```text
Upper(0,250,0.00625)     0.020096023480...
Upper(0,500,0.00625)     0.010099006708...
Upper(5,500,0.00625)     0.027393870699...
Upper(9,500,0.00625)     0.038810264081...
Lower(467,500,0.00625)   0.901155260433...
Lower(466,500,0.00625)   0.898794333267...
Upper(500,500,0.00625)   1
Lower(0,500,0.00625)     0
```

Tolérance de test absolue : 1e-12.

## 7. Support

Avant tout bootstrap :

```text
parents                         = 4000
parents par cellule             = 500
fully_nonexact global           >= 2000
fully_nonexact par cellule      >= 100
numeric_eligible global         >= 1000
numeric_eligible par cellule    >= 50
full/shadow observés par cellule non nuls
structure/types/overflow        valides
```

Une violation de support produit `status=INVALID_UNKNOWN`, `scientific_gates_evaluated=false` et aucune série bootstrap. Les erreurs structurelles de parsing ou de schéma lèvent une erreur contractuelle et doivent faire échouer le futur job.

## 8. Sept familles cellulaires et gates

La décision est une intersection-union : toutes les portes doivent passer. Il n'y a pas de correction alpha entre familles. Chacune des sept familles cellulaires possède ses huit bornes avec `alpha_cell=0.00625`.

| Famille | Méthode cellulaire | Gate |
|---|---|---|
| all-parent saving | bootstrap LCBsim95 | chaque cellule ≥0.20 |
| fully-nonexact saving | bootstrap LCBsim95 | chaque cellule ≥0.20 |
| value-equivalence | CP-LCBsim95 | chaque cellule ≥0.90 |
| signal event | CP-UCBsim95 | moyenne des huit ≤0.020 et maximum ≤0.040 |
| moderate_1_99 | bootstrap UCBsim95 | chaque cellule ≤4.0 |
| total_component | bootstrap UCBsim95 | chaque cellule ≤6.0 |
| numeric_ge_100 | CP-UCBsim95 | moyenne des huit ≤0.015 et maximum ≤0.030 |

Gates globaux conservés :

```text
all-parent saving LCB95          >= 0.30
fully-nonexact saving LCB95      >= 0.30
same-row LCB95                   >= 0.94
value-equivalence LCB95          >= 0.96
conditional numeric mean UCB95   <= 2.0
exact mismatch count             == 0
maximum numeric delta observé    <= 1000
```

Le rapport publie les sept familles dans cet ordre exact, leurs huit booléens, leurs gates agrégés et les gates globaux. `all_passed` est vrai seulement si toutes les portes globales et familiales sont vraies. Le module ne transforme pas ce booléen en verdict scientifique terminal ; ce mapping appartient à la future preregistration finale.

## 9. Fixture synthétique

Le fixture possède exactement 4 000 parents, 500 par cellule. Pour la cellule d'index `c=0..7` et la ligne `j=0..499` :

```text
parent_id        = 500*c+j
full_nodes       = 1000000 + 1000*c + j
shadow_nodes     = 500000  +  500*c + j
fully_nonexact   = (j % 5 != 0)
value_equivalent = (j % 25 != 0)
same_row         = (j % 20 != 0) and value_equivalent
signal_direction = 1 si j=25, 2 si j=125, 3 si j=225,
                   5 si j=325, sinon 0
signal_event     = signal_direction in {1,2,3}
numeric_eligible = (j % 2 == 0)
numeric_component = 0 si inéligible ou value-equivalent,
                   sinon j % 151
exact_mismatch   = false
```

Truth globale exacte :

Les champs agrégés `numeric_delta` et `maximum_numeric_delta` ci-dessous portent uniquement sur les deltas définis des parents éligibles ; ils sont calculés depuis `numeric_component` après contrôle de `numeric_eligible` et ne recréent aucun delta pour les autres parents.

```text
rows                              4000
full_nodes                        4014998000
shadow_nodes                      2007998000
fully_nonexact                    3200
fully_nonexact_full_nodes         3212000000
fully_nonexact_shadow_nodes       1606400000
same_row                          3680
value_equivalent                  3840
exact_mismatch                    0
signal_event                      24
signal_win_to_unresolved          8
signal_win_to_loss                8
signal_unresolved_to_loss         8
signal_loss_to_unresolved         0
signal_loss_to_win                8
signal_unresolved_to_win          0
numeric_eligible                  2000
numeric_delta                     7128
moderate_1_99                     2752
numeric_ge_100                    32
maximum_numeric_delta             150
```

Dans chaque cellule :

```text
rows                              500
full_nodes                        500124750 + 500000*c
shadow_nodes                      250124750 + 250000*c
fully_nonexact                    400
fully_nonexact_full_nodes         400100000 + 400000*c
fully_nonexact_shadow_nodes       200100000 + 200000*c
same_row                          460
value_equivalent                  480
signal_event                      3
signal_win_to_unresolved          1
signal_win_to_loss                1
signal_unresolved_to_loss         1
signal_loss_to_unresolved         0
signal_loss_to_win                1
signal_unresolved_to_win          0
numeric_eligible                  250
numeric_delta                     891
moderate_1_99                     344
numeric_ge_100                    4
maximum_numeric_delta             150
```

La fixture respecte les implications structurelles et exerce des gates positives et négatives. Ses booléens de gate sont une vérification de plomberie synthétique, jamais une conclusion B2.

## 10. Lien au reçu kernel 1773 et runtime

Le premier attempt 1773 a échoué techniquement après les 40 fetches : Q1 réel possède le schéma compact à neuf colonnes, alors que le mapping historique l'avait dirigé vers le schéma catalogue à quatorze colonnes. Il n'a publié ni union valide ni probe kernel complet et ne peut donc pas satisfaire `--kernel-receipt`. Cette panne ne contient aucune observation B2 et doit être corrigée uniquement dans le mapping de sources possédé par l'outillage historique.

L'artefact authentifié `statistical-runtime-environment.json` du premier attempt établit l'environnement CPX suivant :

```text
python_implementation = CPython
python_version        = 3.14.4
python_executable     = /usr/bin/python3
platform              = Linux-7.0.0-30-generic-x86_64-with-glibc2.43
machine               = x86_64
libc                  = glibc 2.43
nproc                 = 16
```

Le traceback cohérent passe par `/usr/lib/python3.14`. CPython 3.12.14 n'est donc pas présumé disponible sur CPX62. Cet artefact authentifie l'environnement, mais l'échec avant la sonde ne fournit toujours aucune durée kernel.

Le futur CLI exige `--kernel-receipt` et accepte seulement le schéma matériel du fichier 1773 `synthetic-statistical-runtime-probe.json` :

```text
kind                              SYNTHETIC_ARITHMETIC_ONLY
scientific_parents                0
draws                             2000000
integer_accumulations_per_draw    10
splitmix_test_vector_pass         true
kernel_only_excludes_...          true
```

Il vérifie aussi les durées/débits finis positifs, la présence de l'environnement et les dix checksums normatifs exacts de la fixture 1773 :

```text
500934807,1001869614,1502804421,2003739228,2504674035,
3005608842,3506543649,4007478456,4508413263,5009348070
```

Ces valeurs ont été exécutées localement sur exactement 2 000 000 tirages du flux fixé, avec 2 000 000 uint64 générés et zéro rejet. Le chargeur publie ensuite le SHA des bytes canoniques reçus ; une différence de checksum échoue avant le full preflight.

Au lancement du preflight complet, les sept champs `python_version`, `python_implementation`, `python_executable`, `platform`, `machine`, `libc` et `nproc` doivent être exactement égaux entre l'environnement courant et le reçu kernel authentifié. Une différence échoue avant création du répertoire de sortie. Le reçu final publie `runtime_matches_kernel_environment=true`.

Le code est portable et n'impose aucune version Python avant la décision de protocole. Le futur preflight doit épingler CPython 3.14.4 et `/usr/bin/python3` tels qu'authentifiés, ou un autre runtime réellement disponible, provisionné et mesuré avant gel. Dans les deux cas, les vecteurs et références sont rejoués prospectivement ; l'algorithme, les graines, les seuils et les méthodes ne changent pas. Aucun résultat frais ne peut guider ce choix. Le futur probe 2M×10 reste une mesure de kernel et ne devient jamais une mesure du full bootstrap.

## 11. CLI et artefacts du futur preflight

Commande future, non exécutée ici :

```text
python jobs/tools/adaptive_sibling_b2_statistics.py \
  --preflight-synthetic \
  --kernel-receipt <1773/synthetic-statistical-runtime-probe.json> \
  --out-dir <répertoire neuf>
```

Artefacts :

```text
synthetic-parent-stats-sufficient-v1.jsonl
synthetic-parent-stats-truth-v1.json
synthetic-statistics-v1.json
statistical-preflight-receipt-v1.json
progress.json
```

Le reçu publie :

- `synthetic_only=true`, `scientific_parents=0`, fresh reads/games/fits=0 ;
- promotion/bake false ;
- R=200 000 et exactement 800 000 000 tirages acceptés ;
- SHA du reçu kernel, du fixture, de la truth et du rapport ;
- scope chronométré, temps monotone, temps CPU, pic RSS, tailles des trois artefacts produits et environnement observé ;
- `gate_exercise_only=true` et `scientific_verdict=null`.

Le scope `wire_parse_bootstrap_cp_quantiles_report_serialization_and_write` commence avant la relecture du JSONL suffisant et finit après la sérialisation canonique et l'écriture du rapport. Le code exige que les bytes relus et les 4 000 objets soient identiques à la fixture construite avant d'analyser les objets reparsés. La construction/écriture de la fixture et l'écriture du reçu auto-descriptif restent hors chrono et sont publiées séparément par tailles ; le sizing final ne doit pas les dissimuler.

Sous Linux, le pic RSS est converti de KiB en bytes depuis `resource.getrusage(RUSAGE_SELF).ru_maxrss`. Sous macOS, la valeur native est déjà en bytes. Sur un runtime sans module `resource`, le champ vaut `null` et ne permet pas le gel : le preflight CPX final doit fournir une mesure de RAM exploitable. Les tailles publiées sont celles des bytes canoniques du JSONL d'entrée, de la truth et du rapport statistique ; elles ne sont pas extrapolées depuis le probe kernel 2M×10.

Le répertoire de sortie doit être absent. Le CLI n'écrase aucun artefact existant.

## 12. Validation locale bornée

Les tests locaux n'exécutent jamais R=200 000. Ils couvrent :

- les vecteurs SplitMix64 bruts et bornés ;
- les quantiles type 1 ;
- les huit références CP ;
- les types et implications ParentStats ;
- le round-trip JSONL canonique et le rejet des clés dupliquées/bytes non canoniques ;
- les bornes d'overflow ;
- les agrégats exacts de la fixture ;
- un bootstrap interne R=20 déterministe avec checksum fixé sur flux et quantiles, séparé des valeurs `lgamma` contrôlées à `1e-12` ;
- le payload de progrès final sans altération du flux ;
- les sept familles et alpha/8 ;
- les seuils inclusifs de chaque gate global et des sept familles ;
- le support cellulaire nul fail-closed et une réplication à dénominateur nul malgré un support initial valide ;
- le reçu kernel et l'absence d'override R dans le CLI.
- l'égalité exacte du runtime courant avec l'environnement kernel authentifié.

Résultat de développement au moment de rédaction :

```text
python -m unittest jobs.tests.test_adaptive_sibling_b2_statistics
15 tests, OK
microsonde privée R=1000, 4 000 000 tirages: 7.594 s, VALID
full 800M preflight: NON EXÉCUTÉ
```

## 13. Conditions avant gel

Le code et ces microtests ne suffisent pas à geler B2. Il reste obligatoirement :

1. conserver l'environnement CPX authentifié du premier attempt et recevoir un retry 1773 réussi avec son probe kernel-only ;
2. revoir indépendamment ce code, son API scellée, ses tests et sa fixture ;
3. merger un commit exact sans modifier les paramètres scientifiques ;
4. dimensionner et autoriser séparément le preflight complet ;
5. exécuter le preflight synthetic-only complet sur CPX et publier ses reçus ;
6. vérifier runtime, vecteurs, checksum, 800M tirages, temps, RAM et disque réels ;
7. seulement alors finaliser et revoir la preregistration B2 avant toute fraîcheur.

Un échec de support, runtime, checksum ou reproductibilité est technique et arrête la séquence. Il ne devient jamais une preuve négative ou positive sur la policy B2. Aucun preflight ne queue automatiquement sélection, teacher, readout, B3, promotion ou bake.

## 14. Reçu terminal authentifié 1774

La [PR #780](https://github.com/jfrancoiscollin/jass/pull/780) a intégré les outils de projection et de statistiques au commit `519ebe314688e37f91dba67398e87273cef9e14c`, après revue indépendante sans P1/P2 et CI native/Python/WASM verte. Le launcher séparé a passé sept tests hors ligne et la vérification de syntaxe shell. Son SHA256 final est `be54d2169c1bc0712a706a7ea3b54975544f9818804b78813a0103281c262df9`.

```text
job        cpx62-1774-l3-decision-math-b2-statistical-preflight-v1
attempt    20260905T020003Z-519ebe31
code       519ebe314688e37f91dba67398e87273cef9e14c
start UTC  2026-09-05T02:00:08+00:00
end UTC    2026-09-05T02:10:18+00:00
state      completed
exit       0
verdict    B2_SYNTHETIC_STATISTICAL_PREFLIGHT_COMPLETE
next       B2_IMPLEMENTATION_EQUIVALENCE_AND_PREREGISTRATION_BEFORE_FRESH_DATA
control    002681c (publication terminale)
```

Les six artefacts suivants ont été relus dans le résultat publié, puis rapprochés du manifeste terminal, de l'inventaire et de `checksums.sha256`. Le préfixe est `r2:jass-data/runs/cpx62-1774-l3-decision-math-b2-statistical-preflight-v1/20260905T020003Z-519ebe31`. Les cinq fichiers de calcul sont sous `artefacts/synthetic-statistical-preflight/`; le résumé est sous `artefacts/`.

| Fichier | Octets | SHA256 |
|---|---:|---|
| `scientific-summary.json` | 6840 | `03994f7a6d09d4a948fba3457dda0d5f7e03baf67d5d1be02b70a47cafa5e008` |
| `synthetic-parent-stats-sufficient-v1.jsonl` | 1282250 | `e74779620c279eef55c77e23924054a5f7450964e7dc698edfbb05fac906350a` |
| `synthetic-parent-stats-truth-v1.json` | 4741 | `a82ffd476287467b04fea8ab1d1195a2daa9c08a89b05a6e19fa43d66cdf045e` |
| `synthetic-statistics-v1.json` | 14310 | `7f8b958e9259f34bd6d3184ae5d248ad74d3b184700064a7932e5b125a217627` |
| `statistical-preflight-receipt-v1.json` | 2509 | `355ab81a76c81ebba0051a813078ff6474dcfb918a97a49a1a79a90df568804d` |
| `progress.json` | 260 | `d9544f69584c482011a3185d41e968bbf7dec0acf65e46881e8fb68bc5e43f5f` |

Le runtime observé correspond exactement aux sept champs du kernel 1773 : `/usr/bin/python3`, CPython **3.14.4**, Linux `7.0.0-30-generic-x86_64-with-glibc2.43`, x86_64, glibc 2.43 et `nproc=16`. Le PID du calcul, 17660, concorde avec celui du monitor. La mesure complète inclut relecture du JSONL, bootstrap, CP, quantiles, sérialisation et écriture du rapport.

```text
réplications                    200000
tirages acceptés                 800000000
uint64 générés                   800000000
rejets                          0
temps bootstrap au dernier point 520.402573329 s
temps chaîne complète            525.156240400 s
temps CPU processus              525.109475791 s
pic RSS                         349532160 octets (333.34 Mio)
status technique                VALID
scientific_verdict              null
```

Le dimensionnement reposait sur une microsonde du même code et du même CPX : 4 millions de tirages en 2.735854463 s, soit une extrapolation linéaire de 547.1708926 s et une enveloppe de 831.32216038 s avec marge et préparation. Les limites du launcher étaient 180 s de préparation, 900 s de calcul complet, 1080 s au total et 300 s sans progrès. Le calcul reste à l'intérieur de ces limites ; le temps `start→end` de 610 s inclut la publication du runner et ne se confond pas avec les 525.156 s mesurées dans le processus.

La fixture exerce volontairement des portes vraies et fausses. `VALID` et le verdict du publisher valident seulement l'exécution technique synthétique. Ils ne constituent aucune confirmation de la policy. Le reçu conserve zéro nouveau parent, zéro lecture fraîche, zéro recherche/fit/partie et `false` pour préenregistrement, confirmation, promotion et bake. Avant toute génération B2 restent l'équivalence exhaustive sur les 8 000 parents historiques, l'implémentation/revue des barrières sélection/teacher/readout et le préenregistrement final épinglant le runtime effectivement authentifié.
