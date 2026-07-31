# L3-PURE — diagnostic de l'inversion reverse-seed 2M/4M

Date : 31 juillet 2026
Statut : diagnostic read-only préenregistré
Promotion : false
Suite automatique : null

## Question

Le readout reverse-seed 2M était positif contre son contrôle apparié, tandis
que la réplication 4M est négative. Ce diagnostic décrit les différences de
distribution des corpus et de géométrie des modèles associées à cette
inversion. Il ne cherche pas un nouveau candidat et n'attribue pas causalement
l'inversion à une strate particulière.

Sources immuables :

- bras 2M `cpx62-1086` et readout indépendant `home-1091` ;
- bras 4M `cpx62-1106` et readout indépendant `home-1108` ;
- parent TURNOVER authentifié `home-0977`.

## Calculs autorisés

Le job :

1. authentifie les quatre résultats et les cinq modèles ;
2. lit les corpus JNNW/JSM1 sans les modifier ;
3. construit l'atlas objectif existant aux préfixes ordonnés 1M/2M pour
   l'expérience 2M et 1M/2M/3M/4M pour l'expérience 4M ;
4. publie les divergences de Jensen-Shannon, les plus grands déplacements de
   masse, WDL et conversion descriptifs par strate ;
5. compare les vecteurs PJTW au parent et le cosinus des deltas
   `treatment-control` 2M et 4M.

Les préfixes suivent l'ordre physique des records. Ils ne sont ni randomisés
ni des checkpoints de fit et ne constituent donc pas une courbe
d'apprentissage. Les WDL et conversions de l'atlas sont corrélés au niveau
record. Les normes et cosinus PJTW ne sont pas des proxys de force.

## Interdictions

- aucun nouveau self-play ;
- aucun fit ;
- aucun match ;
- aucune sélection de modèle ;
- aucune conclusion causale à partir des diagnostics ;
- aucune promotion ni continuation automatique.

Le verdict terminal attendu est
`L3_PURE_REVERSE_SEED_SCALE_DIAGNOSTIC_COMPLETE`, avec
`scientific_result=false`, `promotion_authorized=false` et
`automatic_next_job=null`.

## Sizing CPX62

Le job télécharge environ 105 MiB de corpus compressés et analyse 24 millions
de records cumulés à travers les préfixes. Il est mono-processus hors I/O. Le
budget préenregistré est 20–40 minutes, sans consommation de moteur ; timeout
extérieur 90 minutes et garde disque de 8 GiB.
