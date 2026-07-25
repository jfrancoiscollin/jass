# L3 — incident du gauge de conversion FEN

Date : 25 juillet 2026.

## Cause

`tools/mine_conversion_pool.py::rec_to_fen` associait les hommes noirs au
bitboard des dames noires et réciproquement. Le gauge historique
`conv_self_eval_strat_v2.fen` était donc une transformation non fidèle des
records JNNW certifiés.

- SHA-256 du gauge invalidé :
  `e5e20043a1c32916548f76fd1ff430efa1f1a2156ceefca6c3c8470dfb9b9c72` ;
- blob source :
  `ff359c28c6e6ccdc491635141a2167ea0fe896be` ;
- correction :
  `8efd1c45dd5355db0a4825d7fd9a48fa3704db8c`.

La correction a été vérifiée sur les 9 658 records réels de 0953 :
JNNW → FEN → JNNW restitue désormais les 9 658 clés bit à bit.

## Portée

Sont supersédés :

- le volet conversion de `home-0945-l3-pure-m1-eval-v1` ;
- le volet conversion de `home-0949-l3-pure-m1-causal-ablation-v1` ;
- tout readout de conversion construit depuis ce gauge FEN.

Ne sont pas invalidés :

- le triangle M0, constitué de matchs directs sur ouvertures standards ;
- les poids C0, P1, F500, F2M et R2M ;
- les constructions de poids AB_MAT, AB_KING et AB_EXTRAS ;
- les volets de force générale indépendants du gauge.

## Remplacement

`home-0954-l3-pure-m1-abextras-validation-v5` a sélectionné directement les
records JNNW stables après deux certifications d14 :

- P3 : 300 records,
  SHA-256 `cd92710fec7934d113ccade22180d4cddf029b084dd20c8fa9e30ca686767c91` ;
- P4 : 300 records,
  SHA-256 `0d925c4fbd7e7928bf6d86bd2cd40f796ee6805e0010e51d5d6483986da2a1ac`.

`home-0955-l3-pure-m1-corrected-matrix-v1` doit rejouer les huit modèles sur
ces deux pools immuables avec Gen2 fixe, Q00, profondeur 10 et comparaison
appariée par index. Les nulles restent des non-conversions valides dans
l’échantillon apparié. Le meilleur challenger P4 positif reçoit ensuite les
trois gates de force ; aucune promotion ni continuation n’est automatique.
