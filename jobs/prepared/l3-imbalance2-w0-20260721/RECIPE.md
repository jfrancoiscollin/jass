# L3-IMBALANCE2 W0 — calibration des pénalités adaptatives

- job cible : cpx62 ;
- entrée immuable : référence de difficulté `0862` ;
- aucune génération de partie ;
- aucun entraînement ;
- aucune modification du moteur ;
- durée attendue : 3–8 minutes.

Le job calcule les valeurs oracle par strate, les écarts A/B, un shrinkage par
source, une projection monotone selon le matériel et deux matrices proposées :
valeur absolue et normalisation sur `14v16..18v20`.

Sorties R2 principales :

- `w0-oracle-weight-calibration.json` ;
- `JASS_CONTROL_SUMMARY.json` ;
- `RESULTS.txt` ;
- preuve de source vérifiée.

Marqueurs GitOps : verdict, classification, recommandation, stabilité A/B,
hypothèse de densité et autorisations toutes à `false`.

Le job doit être placé après les jobs prioritaires `L3-PURE` déjà en file. Son
résultat ne déclenche pas W1 automatiquement.
