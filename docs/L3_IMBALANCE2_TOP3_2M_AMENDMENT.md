# L3-IMBALANCE2-TOP3 — amendement corpus 2M

> 21 juillet 2026 — remplace avant exécution le contrat 500k/gen de la PR #375.

Le premier job `ccx33-0889` a été retiré de la queue avant prise en charge. Aucun calcul 500k n'a été consommé.

Le protocole scientifique reste identique, sauf pour le volume source :

- `2 000 000` records frais par génération ;
- G1–G4 à d8, soit `8 000 000` records source au total ;
- répartition égale entre `16v18`, `17v19`, `18v20`, puis entre les deux couleurs avantagées ;
- `CHUNK=500000` conservé pour le fit en streaming ;
- mêmes seeds, exploration, pondération role-aware 1/2/4, holdout et évaluation appariée G0/G4 ;
- aucun professeur externe et aucune continuation automatique.

Le runner 2M est un adaptateur fail-closed du runner TOP3 mergé : il exige exactement quatre substitutions auditées (volume par défaut, garde de volume, manifeste et bannière), puis refuse de démarrer si le contrat 500k subsiste.

Durée indicative sur ccx33 : 30–60 heures. Le coût supérieur est assumé afin que l'absence de signal soit moins facilement imputable à un corpus trop court.
