# L3-PURE — sample weights d’échec de conversion v1

Date : 2026-07-30
Statut : formule, contrôles et template fit-only préenregistrés ; lancement
interdit avant clôture du readout reverse-seed

## Question causale

À corpus, split, warm-start, features et fit identiques, un multiplicateur
borné sur les lignes `failed_conversion` améliore-t-il la force par rapport à
l’objectif historique non pondéré ?

Le parent général reste `TURNOVER`. Le DOE repart de son corpus immuable de
2 000 000 lignes publié par `home-0977`, pas d’un nouveau self-play :

- JNNW SHA256
  `9b7db67a87025baf9115c72512312ac13ace076cef700c54ff1862f4ab240a2d` ;
- JSM1 SHA256
  `acf3bbf4a28e7b44a1077df06bca9658cd4b189fc4cf11ee7f56720661626682` ;
- warm-start F2M SHA256
  `be675b6c1c6360a0a9aa5977ed492284bc8dcc1861ee47bc2e3139046ed769f2`.

## Facteur unique

Les deux bras utilisent le même JNNW réordonné par le même split par
`opening_id`, le même fichier de features dumpé une seule fois et les mêmes
hyperparamètres L-BFGS.

| Élément | CONTROL | TREATMENT |
|---|---:|---:|
| poids brut train, autre ligne | 1 | 1 |
| poids brut train, `failed_conversion` | 1 | 2 |
| poids brut holdout | 1 | 1 |
| normalisation | `mean-train-1` | `mean-train-1` |
| holdout pondéré | non | non |
| oversampling | non | non |

`failed_conversion` reprend exactement la définition data-only du hard mining
v1 : avec hommes=1 et dames=3, une couleur mène matériellement mais ne gagne
pas le WDL terminal. La formule ne consulte que la partition train. Le holdout
complet reçoit des poids bruts à 1 et reste évalué sans pondération.

Le multiplicateur 2 est fixé avant calcul. C’est une dose beaucoup plus douce
que le remplacement de 50 % du corpus par le replay hard, axe fermé par
`home-1076`. Aucun clipping, teacher, oracle, TOPK, reweight V2 ou modification
de box n’est autorisé.

## Contrôles obligatoires

`jobs/tools/l3_failed_conversion_weights.py` publie atomiquement un `.npy`
float32 aligné et un rapport versionné avec hashes, comptes train, fréquence
du signal, bornes, moyenne brute et ESS de Kish. Le signal n’est pas évalué
sur le holdout. `train_stream.py` doit ensuite publier son propre rapport de
normalisation, quantiles et ESS.

Le bras CONTROL passe un vecteur uniforme à l’interface sample-weights. Le
trainer doit reconnaître ce vecteur comme uniforme et reprendre exactement le
chemin historique `sw_all=None`. Le template
`jobs/templates/l3-pure-failed-conversion-weights-causal-ab-v1.sh` vérifie que
la géométrie et la routine du feature dumper 8cf sont identiques au SHA source,
reproduit le split certifié puis exige que le modèle CONTROL soit
byte-identique au modèle TURNOVER historique. Une dérive ferme le DOE avant de
lancer le fit TREATMENT.

Les deux optimiseurs doivent converger. La holdout commune est diagnostique
seulement et ne sélectionne jamais un bras.

Le template ne génère aucun self-play. Il authentifie le résultat `home-0977`,
son corpus, son JSM1, son split et le warm-start F2M. Il dumpe les features une
seule fois et réutilise exactement les mêmes données, features, warm-start et
hyperparamètres pour les deux fits séquentiels. Le certificat terminal
`L3_PURE_FAILED_CONVERSION_WEIGHTS_CAUSAL_AB_ARMS_READY` ne constitue pas un
résultat de force. La couverture d’entraînement est calculée une seule fois ;
elle est commune aux deux bras par construction et son delta causal vaut zéro.

## Readout indépendant préenregistré

Après deux fits valides seulement, le traitement sera joué directement contre
le contrôle sur 1 500 ouvertures fraîches uniques, couleurs appariées, soit
3 000 parties en Q00 profondeur 9 et 3 000 parties en native 0,1 seconde par
coup. Le pool, seed `1094001`, sera disjoint de DILF et des pools publiés par
les readouts TOPK, hard replay et reverse seeds.

Le score primaire additionne les W/D/L des deux vues avant de publier taux,
Elo, IC90 et IC95. Les classes préenregistrées sont :

- `ABOVE_UNWEIGHTED_IC95` si les deux vues ont un point estimate positif et
  que la borne basse additionnée IC95 dépasse 0,5 ;
- `ABOVE_UNWEIGHTED_IC90` avec la même règle à IC90 ;
- `BELOW_UNWEIGHTED` si la borne haute additionnée IC90 est sous 0,5 ou si
  une vue régresse à IC90 ;
- `DIRECTIONAL` si le point estimate additionné est positif sans régression
  de vue établie ;
- `INCONCLUSIVE` sinon.

La couverture d’entraînement est commune et son delta est exactement nul par
construction. W/D/L, Elo, IC90/IC95 et couverture seront publiés. Aucun seuil
ne sera modifié après les fits.

Le certificat de fit conserve volontairement le rapport canonique complet
`l3_bucket_visits` (`coverage`, `concentration`, `geometry`, `corpus`). Le
readout normalise ce rapport vers sa vue compacte seulement après avoir
vérifié le schéma, les 2 000 000 records, la cohérence du taux de couverture,
la monotonie des seuils `ge_10`/`ge_100` et les bornes du Gini. Cette
normalisation est une opération de certificat ; elle ne recalcule ni ne
sélectionne aucun bras.

```json
{
  "external_teacher_inputs": 0,
  "promotion_authorized": false,
  "automatic_next_job": null
}
```
