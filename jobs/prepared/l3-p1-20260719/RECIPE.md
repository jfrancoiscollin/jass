# L3-PURE P1 — recette figée pour cpx62

## Décision

P1 repart de **G0 matériel** et produit une lignée fraîche **G1–G4**. Aucun
artefact d'un screen n'est réutilisé comme parent : les screens ont servi à
choisir la recette, pas à amorcer la campagne longue.

La recette retenue est la baseline de contrôle, car aucun levier préliminaire
n'a franchi son gate :

- C0 : frontière mobile v1 retirée ;
- C1-Q1 : `q1_no_lead`, donc fingerprint Q00 ;
- C2-X1 : `x1_no_lead`, donc exploration contrôle `8 / 8 % / 60` ;
- C3-MF : `screen_no_lead`, donc L2 `3e-5` ;
- capacité : 32cf `NO-GO` car la lignée est data-limitée, donc 8cf ;
- benchmark matériel 0841 : Scan convertit 89/100 contre 63/100 pour Gen2-MMTO.
  Ce résultat confirme que la conversion reste le thermomètre prioritaire, mais
  Scan et Gen2 restent strictement externes à l'entraînement.

Le screen budget B n'a pas sélectionné de recette : P1 utilise donc le palier d8
pré-enregistré dans le plan initial. Cette PR ne présente pas d8 comme un gain
causal ; elle lance la trajectoire baseline nécessaire pour observer une pente
longue avant les paliers P2–P4.

## Contrat P1

| Élément | Valeur figée |
|---|---|
| départ | G0 matériel, homme=1, dame=3, autres termes=0 |
| générations | G1–G4 |
| corpus | 500 000 records frais par génération |
| recherche de jeu | d8, 63 paramètres explicitement épinglés, Q00 |
| exploration | 8 plies aléatoires, epsilon 8 %, décroissance à 0 au ply 60 |
| vérité | WDL terminal, EGDB exacte après atteinte naturelle |
| censure | partie au ply-cap entièrement exclue |
| fit | logistique WDL, color-fold, tempo-stage, L2=3e-5 |
| continuité | G1 optimisé depuis zéro ; G2+ warm-start du student précédent |
| représentation | 8cf |
| interdits | teacher, frontière, replay, relabel, MMTO, adjudication |
| seed primaire | 271828 |
| box | cpx62, 32 GiB |
| promotion | aucune promotion automatique ; évaluation séparée après G4 |

## Lancement GitOps après merge

Le job jass-control doit :

1. épingler `EXPECTED_CODE_SHA` au SHA mergé ;
2. copier le wrapper `cpx62-l3-p1-frozen-v1.sh` dans la queue ;
3. router cpx62 vers l'identifiant du job ;
4. ne définir aucun `automatic_next_job`.

Le runner refuse toute dérive de volume, profondeur, exploration, L2,
fingerprint, géométrie, seed, RAM ou espace disque.
