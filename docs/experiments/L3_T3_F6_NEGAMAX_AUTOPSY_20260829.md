# T3-A/F6 — autopsie du témoin negamax R0-v2

Date : 2026-08-29. Statut initial : **diagnostic post-terminal read-only ;
résultat CPX62 en attente**.

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
L’artefact final comptera toute violation de cette égalité sur tous les coups.

## Sortie et décision

Le job diagnostique produit `negamax-autopsy.json`, sans aucune partie de
force, et choisit exactement une classification autorisée par la mission. Une
éventuelle v3 nécessitera une prereg séparée et n’est ni créée ni exécutée ici.
Ce document sera complété après le readout CPX62 avec les valeurs T0/T3 et la
cause exacte.
