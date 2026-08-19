# CTX3 — audit terminal du gate causal 1419 (19 août 2026)

## Objet

`cpx62-1420-l3-context3-terminal-audit-v1` est un audit **strictement read-only**
du gate causal terminal `cpx62-1419-l3-context3-two-pool-force-v1`, attempt
`20260819T112556Z-8adc506a`.

Il ne rejoue aucune partie et ne refait aucun fit. Il récupère le résumé publié,
les deux certificats et les quatre JSON bruts (deux pools × natif/Q00), puis :

1. authentifie le job, l'attempt, le SHA, l'état `completed` et `exit_code=0` ;
2. recalcule intégralement le readout avec les mêmes quatre seeds et 200 000
   bootstraps appariés ;
3. exige l'égalité JSON exacte entre le readout recalculé et celui publié par
   1419 ;
4. réauthentifie WDL, taux, IC, erreurs, hashes bruts, modèles, pools,
   disjonctions et budgets ;
5. publie chaque métrique décisive dans un marqueur visible par le runner ;
6. classe l'échec positif préenregistré en neutralité, inversion ou
   hétérogénéité, sans modifier le seuil après observation.

## Invariants

- source immuable : 1419 / `20260819T112556Z-8adc506a` / code `8adc506a...` ;
- 24 000 parties sources auditées, zéro partie rejouée ;
- modèles 1418 réutilisés, zéro refit ;
- zéro nouveau self-play ;
- zéro lecture frozen ;
- Q00 reste diagnostic et ne peut pas renverser le verdict natif ;
- aucune promotion et aucune continuation automatique.

Le certificat attendu est `JASS_CONTEXT3_TERMINAL_AUDIT_READY`. Il atteste la
lecture et la classification du verdict, pas un résultat positif.
