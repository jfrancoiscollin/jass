# 0921 — miroir causal TOP3 de L3-PURE

`cpx62-0921-l3-pure-top3-stable-conversion-matrix-v1` répète le protocole
causal 0908 avec une seule substitution scientifique : les modèles évalués
G0/G4 proviennent de la lignée généraliste pure immuable `cpx62-0842`.

- Même pool déterministe : 384 positions self-play atteignables, exactement +2
  hommes, sans roi, équilibrées sur 12 cellules à 32 positions.
- Même matrice d10 : Scan/Scan, Scan/G4, G4/Scan, G0/G0, G4/G0, G0/G4 et
  G4/G4, soit 2 688 parties.
- G0 brut SHA-256 :
  `4dd50bd836375d825234fa263a964a2b684e865c6513cd7813d5ff93dbe97864`.
- G4 L3-PURE brut SHA-256 :
  `93c76031be3a039aa08eec4a1d3166321d93d602ca78a139509f8c6e90de5e86`.
- Recherche, Scan, géométrie 8cf, budget et bootstrap identiques à 0908.
- Gate strict : 384 parties par bras, zéro erreur et zéro cap. Aucun
  entraînement, aucune promotion et aucune continuation automatique.

Sizing approuvé : CPX62 `nproc=16`, `-j4`, observation 0908 complète
2 688 parties en environ 5 min 20 s ; ETA prudente 7–12 min, cap dur 20 min.
