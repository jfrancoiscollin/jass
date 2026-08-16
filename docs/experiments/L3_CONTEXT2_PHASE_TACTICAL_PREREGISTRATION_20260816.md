# Jass 10×10 — CTX2 phase+tactique

## Question

Le signal conditionnel causal de `CONTEXT_30` est établi à profondeur fixe,
mais pas robuste à tous les budgets natifs. Le contexte historique est une
projection de onze extras déjà visibles par PatternEval, sans phase explicite,
avec une mobilité non légale, une redondance exacte sur les dames et un terme
de balance incompatible avec la vraie symétrie rotation 180° + échange des
couleurs.

CTX2 teste une amélioration unique : un enseignant de cible plus informatif et
strictement antisymétrique, sans modifier le corpus, le parent, l’architecture
du modèle ni la dose conditionnelle `alpha=0,30`.

## Contexte

Le binaire produit quinze différences noir−blanc :

1. hommes ;
2. présence d’au moins une dame ;
3. dames supplémentaires ;
4. nombre exact de coups légaux ;
5. nombre exact d’options de capture légales ;
6. longueur maximale de capture ;
7. coup forcé ;
8. pression de promotion ;
9. hommes bloqués ;
10. présence au centre ;
11. déséquilibre absolu des ailes ;
12. centralité des dames ;
13. proximité dame−adversaire ;
14. mobilité sûre des dames ;
15. mobilité refusée aux dames.

Les quatre composantes tactiques utilisent `generate_legal_moves`, donc les
captures obligatoires et la règle FMJD de capture majoritaire. Chaque base est
conservée dans deux canaux : `tempo_wmg × base` et
`(1-tempo_wmg) × base`, soit trente dimensions effectives.

## Cross-fit

- cinq folds atomiques par `opening_id` ;
- aucune ouverture entre train et holdout ;
- RMS calculé uniquement sur les lignes d’entraînement de chaque fold ;
- chaque partie reçoit un poids total égal, indépendamment de sa longueur ;
- convergence obligatoire de chaque mapper OOF et du mapper final ;
- rang, variances, corrélations et coefficients publiés.

Le contrôle shuffled conserve exactement la cohorte, le fold d’ouverture, le
W/D/L terminal et quatre bins de phase tempo. Il détruit uniquement
l’association fine entre position et prédiction conditionnelle.

## Bras

| Bras | Cible | Fit |
|---|---|---|
| A | CTX1 legacy, alpha 0,30 | modèle certifié `cpx62-1340`, sans refit |
| B | CTX2 aligné, alpha 0,30 | nouveau fit CURRENT_2M |
| C | CTX2 shuffled WDL×phase, alpha 0,30 | nouveau fit CURRENT_2M |

Même TURNOVER CURRENT_2M, même split, parent L2LOW, 8cf exact-fold tempo,
120 extras, `l2=1e-5`, `prior_decay=0`.

## Décision

Contraste primaire : `B−C` en force native sur deux pools d’ouvertures frais,
disjoints et indépendants. `Q00 d9` reste diagnostique.

Contraste secondaire hiérarchique : `B−A`, interprété seulement si `B−C` est
établi positif. Une meilleure loss statique ne sauve jamais un échec de force.

Le job de fit ne lit aucun frozen, ne génère aucun self-play, ne joue aucune
partie et n’autorise aucune promotion automatique.
