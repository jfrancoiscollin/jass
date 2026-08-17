# Jass 10×10 — Curriculum intégral réétiqueté CTX2

## Question

La recette du champion `CURRICULUM` est-elle améliorée lorsque ses deux
étages d'entraînement sont entièrement réétiquetés par l'enseignant
`CTX2_PHASE_TACTICAL`, sans conserver de mélange avec le W/D/L terminal ?

Le changement testé est volontairement agressif : `alpha=1,00`. La cible est
donc la prédiction conditionnelle CTX2 out-of-fold, et non plus
`0,70 × outcome + 0,30 × contexte`.

## Contraste

| Bras | Recette |
|---|---|
| A | champion `CURRICULUM` certifié, réutilisé byte pour byte |
| B | même curriculum `MEGA_FULL_4M → CURRENT_2M`, entièrement refitté avec CTX2 aligné `alpha=1,00` |

Tout le reste est maintenu : sources, échantillonnage, splits par ouverture,
architecture 8cf exact-fold tempo avec 120 extras, parent L2LOW du premier
étage, prior du second étage, `l2=1e-5`, `prior_decay=0`, solveur et seuil de
convergence.

## Construction de B

1. Reproduire `MEGA_FULL_4M` depuis l'autojeu UNIFORM 40M avec la sélection
   certifiée (`game_hash_mod=10`, résidu 0, seed 20260814).
2. Reproduire `CURRENT_2M` depuis TURNOVER avec le split certifié
   (`holdout_mod=10`, seed 577215).
3. Extraire pour chaque corpus les 120 features d'inférence et les 30
   composantes CTX2 phase+tactique.
4. Construire des prédictions conditionnelles sans fuite : cinq folds
   atomiques par `opening_id`, RMS propre au train de chaque fold, poids total
   égal par partie et convergence obligatoire.
5. Fitter `MEGA_FULL_4M_CTX2_A100` avec L2LOW comme moyenne du prior.
6. Fitter `CURRENT_2M_CTX2_A100` avec le modèle de l'étape 5 comme moyenne du
   prior. Ce modèle final est B.

Les manifests reconstruits doivent correspondre aux certificats de
`cpx62-1340`; A doit correspondre au hash du champion de `cpx62-1341`.

## Évaluation

Le fit ne joue aucune partie. Après audit du modèle :

- contraste primaire : `B − A` en natif 0,1 s sur un pool frais de 3 000
  ouvertures, couleurs inversées, bootstrap apparié 200k ;
- diagnostic : même pool en Q00 d9 ;
- réplication sur un second pool frais disjoint uniquement si le premier pool
  est positif dans les deux vues ;
- aucune lecture frozen, aucun self-play d'entraînement supplémentaire et
  aucune promotion automatique.

## Interprétation

Un gain de B sur A attribue l'effet à la nouvelle cible complète sous la
recette Curriculum fixée. Un résultat nul ou négatif ferme `alpha=1,00`, mais
ne réfute ni CTX2 à dose partielle, ni une utilisation séparée du contexte à
la décision.
