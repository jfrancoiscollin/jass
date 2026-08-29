# T3-A/F6 — autopsie du témoin negamax R0-v2

Date : 2026-08-29. Statut : **diagnostic post-terminal read-only terminé**.

Verdict exact :

```text
QUIESCENCE_OR_DEPTH_SEMANTICS_EXPLAINS_MISMATCH
```

## Périmètre immuable

Le terminal v2 reste `R0_V2_NEGAMAX_OR_TERMINAL_PRECEDENCE_FAILED`, job
`cpx62-1649-l3-t3-f6-runtime-r0-v2-terminal-readout`, attempt
`20260829T133232Z-f559baed`, code
`f559baede4047f47abe13724b16d1ad669c5f36f`. Ce document ne le corrige pas et
ne réinterprète pas les gates déjà clos : position/transposition, invariance
F6/résiduel, drift relatif, terminal et tablebase ont passé. Le seul objet est
le témoin `search(root, depth=1) == max(-eval(child))`, dont le score T3 observé
était `-51`.

L’autopsie ne réalise aucun fit, refit, calibrage, changement de feature,
retuning, modification de modèle, changement des paramètres de search, partie
de force, Q00, bake ou promotion. Les SHA256 restent :

- T3-A : `16e5db8fd78849bba12b158eee5c1da4ab170129d8aeac1b91ab7a40ad9d0bb2` ;
- CURRICULUM : `319d174f4b548b1655aad4bb30d4c6dc86c08dd715c9c23f8b19ba1937dc0be1` ;
- ordre F6 : `cc4837e6829d937f7330f7bc71280f3ec0bed3f431e57b2664c651e1d763db4e`.

## Méthode diagnostique

Une trace passive, nulle par défaut, observe la recherche sans modifier ses
décisions. Un test compare trace OFF/ON et exige l’identité du score, du best
move, des nodes et des eval calls. Sur la racine exacte
`Position::start_position()` utilisée par R0-v2, l’outil publie tous les coups,
children, STM, T0, T3, résiduel, replies, capture `any(reply.is_capture())`,
classe TB, retours internes et PV. T0 et T3 utilisent chacun une TT fraîche et
le même `SearchParams{}` réel de R0-v2.

La lecture du search établit le chemin à tester, sans encore préjuger du
résultat numérique :

```text
search(root, depth=1)
  -> pour chaque move : negamax(child, depth=0, ply=1)
  -> draw -> TB -> TT -> terminal
  -> depth<=0 : quiescence(child)
  -> captures forcées, ou threat extension,
     ou stand-pat + sacrifices sélectifs
  -> retour child, puis une négation à la racine
```

Ainsi, une profondeur 1 n’est par construction « un ply puis eval statique »
que lorsque la quiescence du child revient exactement au stand-pat. Le contraste
principal reste néanmoins entièrement empirique :

- `search_depth1(T0)` contre `max(-T0(child))` ;
- `search_depth1(T3)` contre `max(-T3(child))` ;
- première divergence move par move entre eval statique et retour réel.

Trois positions synthétiques, sélectionnées par une énumération déterministe
seed `2026082901`, servent uniquement de tests mécaniques : multi-move avec
leaf isolée, exactement un coup légal, puis contrôle non terminal/non-TB/sans
capture où le retour direct doit être retrouvé avec T0 et T3. Elles ne forment
aucune cohorte scientifique.

## Convention T3 vérifiée

Le contrat training frozen est
`S(parent,child) = -T0_child + r_parent(child)`, donc
`T3_child = T0_child - r_parent(child)`. L’artefact déclare
`higher_is_better_for_parent`; l’inférence native calcule sur la position child
`round_clamp(T0_child - residual_parent(F6(child)))`; le search consomme une
valeur STM du child et applique une seule négation au retour réel du child.
L’artefact final compte toute violation de cette égalité sur tous les coups.

## Exécution et provenance

L’implémentation diagnostique est la PR Jass `#707`, merge
`2a4d151956eab0c74674b812ca75bb2d6386d875`. Les deux jobs terminent avec
exit `0` :

| Rôle | Job | Attempt | Code |
|---|---|---|---|
| autopsie | `cpx62-1650-l3-t3-f6-negamax-autopsy-v1` | `20260829T141312Z-2a4d1519` | `2a4d151956eab0c74674b812ca75bb2d6386d875` |
| projection read-only | `cpx62-1651-l3-t3-f6-negamax-autopsy-readout-v1` | `20260829T142315Z-2a4d1519` | `2a4d151956eab0c74674b812ca75bb2d6386d875` |

L’artefact obligatoire `negamax-autopsy.json` est publié sous le résultat
`r2:jass-data/runs/cpx62-1650-l3-t3-f6-negamax-autopsy-v1/20260829T141312Z-2a4d1519`.
Il contient le FEN, les children complets, les traces internes, les PV et les
contrôles synthétiques. Le score T3 `-51` de R0-v2 est reproduit exactement.

## Contraste principal T0/T3

La racine est exactement :

```text
W:W31,32,33,34,35,36,37,38,39,40,41,42,43,44,45,46,47,48,49,50:B1,2,3,4,5,6,7,8,9,10,11,12,13,14,15,16,17,18,19,20
```

STM blanc, `9` coups légaux. Chaque child a STM noir, `9` replies, aucune
capture dans **toute** la liste, n’est ni terminal ni TB, et ne produit aucune
menace `opponent_can_capture`. Le contrôle `replies[0]` et le contrôle
`any(reply.is_capture())` concordent donc sur les neuf children.

| Bras | max direct | search d1 | Classe | Best move | Nodes | Qnodes | Evals | Children divergents |
|---|---:|---:|---|---|---:|---:|---:|---:|
| T0/CURRICULUM | `0` | `-1` | `T0_DIRECT_NEGAMAX_FAIL` | `33-28` | `33` | `24` | `16` | `1/9` |
| T3-A/F6 | `+85` | `-51` | `T3_DIRECT_NEGAMAX_FAIL` | `31-27` | `50` | `41` | `23` | `9/9` |

Le détail child-POV expose le premier point de divergence. `q-return` est le
retour réel de `negamax(child,0)` avant la négation racine :

| Move | T0 child | T0 q-return / étage | T3 child | T3 q-return / étage | Sacrifices sélectifs |
|---|---:|---|---:|---|---:|
| `31-26` | `7` | `7` / selective sac | `-85` | `69` / selective sac | `1` |
| `31-27` | `15` | `15` / stand-pat beta cutoff | `-50` | `51` / selective sac | `1` |
| `32-27` | `14` | `14` / stand-pat beta cutoff | `-47` | `55` / selective sac | `1` |
| `32-28` | `5` | `5` / stand-pat beta cutoff | `-56` | `73` / selective sac | `2` |
| `33-28` | `1` | `1` / selective sac | `-60` | `67` / selective sac | `2` |
| `33-29` | `3` | `3` / stand-pat beta cutoff | `-58` | `86` / selective sac | `2` |
| `34-29` | `0` | **`2` / selective sac** | `-61` | `81` / selective sac | `2` |
| `34-30` | `3` | `3` / stand-pat beta cutoff | `-61` | `51` / selective sac | `1` |
| `35-30` | `5` | `5` / stand-pat beta cutoff | `-56` | `59` / selective sac | `1` |

La première divergence T0 est `34-29`; la première divergence T3 est
`31-26`. Dans les deux cas, l’étage exact est `qsearch_selective_sac`. Les
probes TB ne trouvent aucun hit, aucun terminal ne remplace l’eval, et aucune
capture immédiate n’explique le résultat.

## Cause exacte

Le témoin v2 était trop étroit. La position « quiet » au sens des captures ne
désactive pas la quiescence de production : le board est men-only,
`qs_sacs=true` par défaut et `scan_add_sacs` génère `1` ou `2` sacrifices
sélectifs sur chacun des neuf children. `depth=1` signifie donc un ply principal
**puis une recherche de quiescence**, pas un ply puis l’eval statique.

CURRICULUM échoue lui-même à l’égalité directe (`0 != -1`). T3 modifie les
stand-pat et fenêtres alpha/beta, ce qui fait parcourir davantage les mêmes
branches génériques de sacrifices ; cela explique que ses neuf children
divergent et que `+85` devienne `-51`. Ce contraste d’amplitude n’est pas une
erreur de signe T3 : il est la réponse normale d’une recherche non linéaire à
des valeurs leaf différentes.

La formule native est exacte sur `9/9` children :
`T3_child = round_clamp(T0_child - residual_parent(F6(child)))`. Mismatches POV,
formule ou conversion : `0`. Le reçu conclut explicitement
`specific_t3_pov_defect_observed=false`.

## Contrôles synthétiques

| Cas | Condition | T0 direct/search | T3 direct/search | Résultat |
|---|---|---:|---:|---|
| A | multi-move, leaf isolée, `10` moves | `-5 / -5` | `119 / 119` | PASS/PASS |
| B | exactement `1` move | `65 / -71` | `172 / -137` | FAIL/FAIL |
| C/D | non terminal, non-TB, sans capture, leaf isolée, `9` moves | `4 / 4` | `66 / 66` | PASS/PASS |

Le cas B montre que le mismatch ne dépend pas de PVS, de l’ordre des siblings
ou d’une mécanique multi-move de la racine. Les cas A et C/D montrent qu’une
leaf réellement isolée retrouve exactement la convention directe pour T0 et
T3.

## Décision et éventuel gate futur

Classification terminale :

```text
QUIESCENCE_OR_DEPTH_SEMANTICS_EXPLAINS_MISMATCH
```

Le FAIL R0-v2 ne révèle aucun défaut spécifique T3-A. Il révèle que
`max(-eval(child))` n’est pas le référentiel de `search(depth=1)` sous les
paramètres de production.

Un futur gate scientifiquement valide devra être preregistré séparément. Deux
témoins mécaniques sont justifiables : (1) un leaf réellement isolé qui prouve
la seule inversion/POV, avec absence explicite de capture, menace, TB, terminal
et sacrifice sélectif ; (2) pour le search réel, une référence qui rejoue les
semantics exactes de quiescence au lieu de les remplacer par l’eval statique.
Aucune v3 ni partie de force n’est créée ou exécutée par cette autopsie.

Gardes terminales : `strength_games=0`, `force_authorized=false`,
`v3_executed=false`, aucun fit/refit/calibrage/retune/bake/promotion.
