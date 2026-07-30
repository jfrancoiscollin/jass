# L3-PURE — blend PJTW statique TURNOVER/reverse-seed v1

## Question causale

Le modèle reverse-seed a battu son contrôle apparié dans
`home-1091-l3-pure-reverse-seed-independent-readout-v2`, mais il ne remplace
pas le champion général. Cette expérience demande si son signal peut compléter
le champion `TURNOVER` sans entraînement supplémentaire ni coût NPS :

```text
BLEND50 = 0,50 × TURNOVER + 0,50 × REVERSE_SEED_TREATMENT
contraste primaire = BLEND50 − TURNOVER
```

Le facteur mobile unique est l’interpolation statique des poids PJTW. Le
parent reverse-seed est figé au SHA256
`2fc29ab61282f3e2f1bbe4495490e761a44ef1a08801b67e29b36be68c00aa5d`;
le champion est figé au SHA256
`b2c79b3617c41087191fee04d9aee0e1929ea63ad621c2efeaebc14ae53a7c16`.

La dose 50/50 est fixée avant tout match. Il n’y a ni grille d’alpha ni
sélection sur le pool de force dans cette v1. Une autre dose serait une
expérience séparée.

## Construction CPX62

`l3-pure-reverse-seed-static-blend-build-v1.sh` :

1. authentifie le champion `home-0977`, les bras reverse-seed `cpx62-1086` et
   le verdict positif `home-1091`;
2. vérifie les hashes des deux PJTW;
3. déquantifie, interpole et requantifie par arrondi pair déterministe;
4. refuse toute saturation et toute dérive de header/géométrie/flags;
5. écrit atomiquement le modèle;
6. vérifie la linéarité statique sur 64 positions DILF légales et figées :
   l’écart absolu à la moyenne des deux évaluations doit rester inférieur ou
   égal à 8 centipions, marge bornée couvrant l’arrondi individuel des poids
   et le retour entier de l’évaluateur;
7. publie le hash exact de `blend50.pjtw.gz`.

Ce job ne joue aucune partie, n’entraîne rien et produit
`scientific_result=false`, `promotion_authorized=false` et
`automatic_next_job=null`.

## Readout HOME

Le readout ne peut être lancé qu’après certification du blend. Il utilise :

- 1 500 ouvertures fraîches, seed `1105001`;
- couleurs appariées, soit 3 000 parties par vue et 6 000 au total;
- vue `Q00` profondeur 9;
- vue native à 0,1 s/coup;
- le même moteur 8cf réparé, les mêmes paramètres de recherche et la même
  défense historique des deux côtés;
- un pool disjoint de DILF et des pools TOPK, hard replay, reverse-seed et
  FAILED_X2 déjà consommés.

La holdout d’entraînement n’intervient ni dans l’alpha ni dans la décision.

## Verdicts préenregistrés

- `L3_PURE_BLEND50_ABOVE_TURNOVER_IC95` : les deux vues ont un point estimate
  positif et l’IC95 additionné est au-dessus de 0,5;
- `L3_PURE_BLEND50_ABOVE_TURNOVER_IC90` : même condition à l’IC90;
- `L3_PURE_BLEND50_DIRECTIONAL` : score additionné supérieur à 0,5 sans
  régression IC90 d’une vue;
- `L3_PURE_BLEND50_BELOW_TURNOVER` : borne haute IC90 additionnée sous 0,5 ou
  régression IC90 d’une vue;
- `L3_PURE_BLEND50_VS_TURNOVER_INCONCLUSIVE` sinon.

Tous les W/D/L, scores, Elo, IC90 et IC95 sont publiés par vue et additionnés.
Le readout garde `promotion_authorized=false` et
`automatic_next_job=null`.

Un résultat positif autorise seulement une porte ultérieure contre Gen2 et en
conversion P3/P4. Il ne bake pas automatiquement le blend. Un résultat
négatif ferme la dose 50/50; une dose différente exige un nouveau
préenregistrement et un nouveau pool.

## Budget

- CPX62 build + tests + probe : cible 10–20 minutes, 16 CPU logiques minimum;
- HOME readout : ancre mesurée `home-1102`, 6 000 parties en 33 min 30 s;
  budget annoncé 35–50 minutes avec build et marge.

Les deux étapes restent séquentielles. Aucun autre facteur signal n’est lancé
en parallèle.
