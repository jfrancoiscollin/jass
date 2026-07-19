# L3-IMBALANCE2 — recette préparée

Cette campagne est une lignée autonome spécialisée sur les départs `n v n+2`
avec uniquement des pions simples, pour `n=1..18`. P1 reprend les paramètres de
la PR #358. P2/P3/P4 suivent d10/d12/d14 et exigent le parent immuable du palier
précédent.

Après chaque palier, exécuter le wrapper Scan gate. `STOP_LINEAGE_SCAN_EQUIVALENT`
arrête la campagne ; `CONTINUE_NEXT_PHASE` autorise seulement la préparation du
palier suivant. Aucun fichier de ce dossier n’est mis automatiquement en queue.
