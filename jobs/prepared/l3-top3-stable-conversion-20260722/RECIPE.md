# 0908 — matrice causale de conversion TOP3 stable

Job préparé, non mis en file :
`cpx62-0908-l3-top3-stable-conversion-matrix-v1`.

- Pool : 384 positions atteignables en self-play extraites uniquement des quatre corpus
  standard-only immuables de `cpx62-0842`, avec hashes et profils épinglés.
- Domaine : `16v18`, `17v19`, `18v20`, exactement +2 hommes, aucun roi,
  aucune prise ni promotion immédiate pour les deux couleurs, 32 positions
  dans chacune des 12 cellules `strate × camp avantagé × trait`.
  Ici, « stable » signifie uniquement que le +2 matériel survit à chacun des
  premiers coups légaux. Ce n’est ni une preuve de gain théorique, ni une
  garantie que le +2 survivra également à la réponse suivante.
- Modèles : G0 et G4 immuables de `ccx33-0890bis` ; Scan externe copié dans
  un snapshot en lecture seule et épinglé sur `scan_linux`, `scan.ini`,
  `data/eval` et les huit paramètres HUB effectifs.
- Matrice d10 : `Scan/Scan`, `Scan/G4`, `G4/Scan`, `G0/G0`, `G4/G0`,
  `G0/G4`, `G4/G4`, une partie par même position et par bras, soit
  384 parties/bras et 2 688 au total.
- Mesures : W/D/L du point de vue du camp +2, score, W−L, taux de victoire
  décisif, raisons de fin et deltas pairés attaque/défense/joint/interaction.
  Le global est un estimand standardisé à poids égal sur les 12 cellules, pas
  une estimation de la prévalence naturelle du corpus. L’effet primaire
  pré-spécifié est l’effet d’attaque `G4/G0 − G0/G0`; les autres intervalles
  sont exploratoires. `Scan/G4` et `G4/Scan` séparent les contrastes de Scan
  en conversion et en défense face à G4.
- Sizing : CPX62 `nproc=16`; ancre 0862 = 2 048 parties d10 en 328 s
  (`6,24 parties/s`), projection brute 2 688 = 431 s. ETA totale annoncée
  12–22 min, timeout partie 120 s, shard 1 200 s, cap total dur 2 100 s.
- Le job échoue si le pool n’atteint pas 384, si un bras n’atteint pas 384,
  ou en présence d’une erreur/time-cap. Il ne produit aucune donnée
  d’entraînement, promotion ou continuation automatique.

Avant toute mise en file, renseigner les trois pins restants :

1. `EXPECTED_CODE_SHA` après merge/revue sur `develop` ;
2. `EXPECTED_SCAN_SHA256` après lecture de `/root/jass-scan/scan_linux` sur
   CPX62 ;
3. `EXPECTED_SCAN_RUNTIME_SHA256`, empreinte canonique du binaire, du
   `scan.ini`, de `data/eval` et du contrat HUB effectif.
