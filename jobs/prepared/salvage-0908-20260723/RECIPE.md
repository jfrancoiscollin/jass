# 0920 — salvage auditable de 0908, sans replay

Le job `cpx62-0920-salvage-0908-stable-top3-matrix-v1` relit exclusivement
le résultat 0908 échoué et immuable
`20260723T131042Z-e4f1b5f7`.

- Aucun moteur n'est relancé et aucune partie n'est rejouée.
- Le tar brut est épinglé par SHA-256
  `9fa4bedd93df491bd0a46828dd5da30abf74fd53b116354869d453d70f2a5277`.
- Le gate strict original reste `FAILED` à cause d'un unique `ply cap`.
- Cette seule ligne, elle-même épinglée par bras, position, cellule et
  `plies=400`, est adjugée nulle dans une copie dérivée.
- La sortie calcule la matrice complète, les IC bootstrap stratifiés à
  10 000 réplications, et les deux bornes de sensibilité si la partie
  capée était attribuée W ou L au camp +2.
- La sortie ne peut ni entraîner, ni promouvoir, ni lancer un job suivant.

Sizing : CPX62 `nproc=16`, aucun build et aucune partie ; téléchargement
inférieur à 1 Mio puis agrégation. ETA 2–5 min, cap dur 10 min.
