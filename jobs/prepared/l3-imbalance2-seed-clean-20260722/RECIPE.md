# L3-IMBALANCE2 seed-clean screen

Statut : préparé, non mis en queue tant que le préflight ccx33 n'a pas publié
`nproc`, débit mesuré, ETA et espace disque.

Question causale : une génération WDL depuis G0 apprend-elle mieux la conversion
quand les positions TOP3 sont réellement présentes dans le corpus ?

Différences intentionnelles par rapport à `0890bis` :

- 100 000 positions, une seule génération ;
- zéro coup aléatoire avant la seed et zéro epsilon ;
- ply 0 systématiquement retenu s'il est calme ;
- positions à capture obligatoire exclues ;
- WDL naturel, aucun rééchantillonnage 1/2/4 ;
- aucune fausse paire dupliquée quand la politique est déterministe ;
- même G0 matériel, géométrie 8cf, d8/Q00, split et gate apparié 384 parties.

Ce screen n'autorise ni promotion ni continuation automatique.
