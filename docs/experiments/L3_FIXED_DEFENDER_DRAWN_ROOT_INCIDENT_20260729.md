# L3 — incident du défenseur Gen2 figé avant le correctif de racine nulle

Date : 29 juillet 2026.

## Portée

`home-1028-l3-pure-topk3-promotion-gate-v1` a terminé ses six cellules de
force, puis a échoué sur la première vague de conversion `p3_mince`. Il n'a
produit ni matrice P3/P4 complète, ni résumé final, ni verdict scientifique.
Ses cellules de force ne sont donc pas réutilisables et aucune promotion ne
peut en être tirée.

Les diagnostics read-only `home-1029` à `home-1032` ont établi la chaîne
causale suivante :

1. les huit shards P3 ont exécuté le même harnais et ont écrit des résumés ;
2. `TOPK3` et `TURNOVER` ont respectivement 49,333 % et 50,000 % d'erreurs ;
3. les erreurs détaillées sont de la forme
   `returned no move ... in a position with legal moves` ;
4. l'attaquant utilisait le code réparé, mais le défenseur Gen2 était compilé
   depuis `038a2001854f2805bc0045acd56c617826e5ff15` ;
5. ce SHA précède `9c1d1e8eaaa5b9bbd86105f7f9807a3033784186`,
   qui impose qu'une racine nulle par répétition ou règle des 25 coups rende
   encore un coup légal au lieu de `bestmove 0-0`.

Le taux proche de 50 % commun aux deux candidats est donc un défaut du
défenseur partagé, pas un signal propre à leurs poids.

## Correction de contrat

Le défenseur historique reste défini par les poids Gen2 et la géométrie v4.
Son moteur de référence est désormais figé au premier SHA portant les deux
réparations de légalité/terminaison :

```text
9c1d1e8eaaa5b9bbd86105f7f9807a3033784186
```

Les templates actifs refusent un arbre source qui ne contient pas le contrat
`root_is_drawn`. `conv_fixed_wdl.py` attribue aussi des labels distincts à
`candidate` et `fixed-defender`, afin qu'un futur journal identifie sans
ambiguïté le processus fautif.

Cette correction ne change ni les poids Gen2, ni les jauges JNNW, ni les
budgets, ni les seuils. Elle rend seulement le défenseur capable de jouer un
coup légal dans une position nulle non terminale.

## Relance

Toute relance doit :

- recalculer toutes les cellules de force, sans reprendre les sorties de 1028 ;
- exclure explicitement le pool d'ouvertures 1028 du nouveau pool ;
- rejouer P3 et P4 contre le défenseur réparé ;
- conserver `promotion_authorized=false` et `automatic_next_job=null` dans le
  job scientifique ;
- ne baker TOPK3 qu'après un résumé terminal complet satisfaisant les critères
  préenregistrés et la revue humaine déjà autorisée.
