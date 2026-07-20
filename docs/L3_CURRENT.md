# L3-PURE — état courant et registre de décision

> **Mis à jour : 20 juillet 2026**  
> **Source de vérité active : ce document.** L’historique consolidé reste dans
> [`PROJECT_RESULTS.md`](PROJECT_RESULTS.md) et le contrat normatif de la lignée
> dans [`L3_PURE_PLAN.md`](L3_PURE_PLAN.md).
>
> **Statut scientifique :** `c0_retire_frontier_v1_flat; c1_q1_no_lead;
> c2_x1_no_lead; c3_mf_no_lead; 32cf_no_go_data_limited; recette_figee;
> p1_v2_no_clear_lead; p2_complete_but_no_plateau; p3_not_authorized`.

## 1. Décision active

La lignée autonome est viable, mais le déficit de conversion n’est toujours pas
résorbé. Tous les écrans DoE ont renvoyé `no_lead`; la recette reste donc figée :

- géométrie `8cf` ;
- Q00, 63 paramètres de recherche explicitement épinglés ;
- exploration `8 / 8 % / 60` ;
- labels WDL terminaux, ply-caps exclus ;
- fit logistic, `L2=3e-5` ;
- aucun teacher, aucune frontière mobile, aucun MMTO dans le train ;
- aucune NNUE : la classe linéaire reste la seule classe autorisée.

La branche spécialiste retenue est `L3-IMBALANCE2-ROLE-V2`. Elle pondère par
position et par rôle uniquement dans le domaine exact `|Δ hommes|=2` avec autant
de dames : côté `+2`, W/D/L=`1/2/4`; côté `−2`, W/D/L=`4/2/1`; hors domaine,
poids `1`. Scan et Gen2 restent des thermomètres, jamais des données de train.

**P3 n’est pas autorisé.** Le prochain verdict obligatoire est la consolidation
appariée et stratifiée `G4→G8` sur les mêmes pools A64/B64. Même un résultat
positif ne déclenche aucun job automatiquement.

## 2. Campagnes longues publiées

| Campagne | Job | Palier | Résultat durable |
|---|---|---|---|
| baseline générale | `cpx62-0842` | P1, G1–G4 d8 | saine, référence de pente |
| imbalance2 V1 | `ccx33-0847` | P1, G1–G4 d8 | near-flat sur le diagnostic de train |
| role-aware V2 | `ccx33-0852` | P1, G1–G4 d8 | attribution de crédit plus propre, pas de lead établi |
| comparaison V1/V2 | `0853` récupéré par `0857` | A64/B64 d10 | `V2_NO_CLEAR_LEAD_AT_P1` |
| role-aware V2 | `ccx33-0859` | P2, G5–G8 d10 | chaîne complète, aucune promotion automatique |
| assess P2 | `0864` récupéré par `0869` | A64/B64 d10 | `STILL_IMPROVING_OR_UNSTABLE`, plateau non confirmé |
| difficulté matérielle | `cpx62-0862` | EGDB + Scan d10 | référence W/D/L propre aux 18 strates |

## 3. P1 powered — V1 contre role-aware V2

La comparaison `0853→0857` réutilise les mêmes octets A64/B64, 64 positions par
strate, soit 1 152 positions par pool avant exclusion. Une position
`plateau-a:1100` a déclenché le watchdog moteur; elle a été retirée
symétriquement de V1/V2 et de G1–G4, laissant `n=1151` sur A et `n=1152` sur B.

À G4 :

| coût `2L+D`, côté initialement avantagé | pool A | pool B | global |
|---|---:|---:|---:|
| V1 | 0,951 | 0,965 | **0,958** |
| V2 role-aware | 0,963 | 0,929 | **0,946** |

Delta V2−V1 : **−0,013**, IC95 apparié **[−0,061 ; +0,035]**. L’effet est sous
le seuil pré-engagé de `0,02` et non significatif. La V2 a été conservée comme
décision de programme, car sa sémantique est préférable et aucune régression
n’est établie; ce choix n’est pas une preuve de supériorité.

## 4. P2 d10 — faits d’exécution

`ccx33-0859` a entraîné G5–G8 à d10, 500 000 records par génération, depuis le
G4 immuable de `0852`. La chaîne est saine et publie ses quatre modèles, ses
manifests, les buckets role-aware et les pools A64/B64 inchangés.

L’assess `0864` a produit toutes les parties mais a rencontré le même timeout sur
`plateau-a:1100`. La récupération contractuelle `ccx33-0869` a retiré cette
position de G5–G8 de façon symétrique : quatre lignes retirées au total, `n=1151`
sur A et `n=1152` sur B.

### 4.1 Coût P2 par génération

| Pool | G5 | G6 | G7 | G8 | lecture |
|---|---:|---:|---:|---:|---|
| A | 0,9175 | 0,9531 | 0,9600 | **0,9835** | dégradation nette |
| B | 0,9375 | 0,8767 | 0,9019 | **0,9184** | petit mieux final, instable |

Pool A : amélioration G5→G8 = **−0,0660** au sens du rapport (donc coût en hausse
0,066), IC95 du delta **[0,000 ; 0,133]**, dernière plage-3 `0,0304`.

Pool B : amélioration G5→G8 = **+0,0191**, IC95 **[−0,0868 ; +0,0460]**,
dernière plage-3 `0,0417`, juste au-dessus du seuil `0,04`.

Verdict P2 interne : **`STILL_IMPROVING_OR_UNSTABLE`**, plateau non confirmé.
Ces chiffres ne montrent pas que d10 a amélioré la conversion; ils montrent une
forte dépendance au pool et aucun signal stable autorisant P3.

## 5. Référence de difficulté par quantité de matériel

`cpx62-0862` mesure les mêmes A64/B64 sans intervenir dans le train ni dans les
règles causales :

- `1v3` et `2v4` : WDL **exacte EGDB**, 128 positions chacune ;
- `3v5…18v20` : autojeu **Scan d10**, référence empirique et explicitement non
  exacte, 128 positions par strate.

| Strate | Source | W | D | L | coût `2L+D` |
|---|---|---:|---:|---:|---:|
| 1v3 | EGDB exacte | 0,5547 | 0,4453 | 0,0000 | **0,4453** |
| 2v4 | EGDB exacte | 0,5781 | 0,4141 | 0,0078 | **0,4297** |
| 3v5 | Scan d10 | 0,4844 | 0,4766 | 0,0391 | **0,5547** |
| 6v8 | Scan d10 | 0,4766 | 0,4609 | 0,0625 | **0,5859** |
| 9v11 | Scan d10 | 0,4062 | 0,4844 | 0,1094 | **0,7031** |
| 18v20 | Scan d10 | 0,4922 | 0,3828 | 0,1250 | **0,6328** |

Macro EGDB des deux petites strates : **0,4375**. Macro Scan sur les seize
strates supérieures : **0,6138**. Macro égale sur les dix-huit strates :
**0,5942**.

La difficulté n’est donc pas monotone avec le nombre de pièces et un taux global
brut est insuffisant. Le verdict principal doit rester la macro-moyenne à poids
égal par strate, avec le détail W/D/L et les deux pools séparés.

## 6. Consolidation G4→G8 obligatoire

Le runner `l3-imbalance2-p2-consolidate-v1.sh` consomme les rapports déjà publiés
par `0853`, `0864` et la référence `0862`; il ne rejoue aucune partie.

Politique d’erreur pré-engagée :

1. les clés pool/index doivent être identiques avant nettoyage ;
2. seule l’union des erreurs contenant le timeout explicitement autorisé peut
   être retirée ;
3. cette union est retirée de **toutes** les générations G4–G8 ;
4. maximum deux positions et `0,1 %` du corpus ;
5. toute ligne manquante, mauvais pool, mauvaise strate ou erreur non autorisée
   fait échouer le job.

Le verdict calcule :

- G4→G5, G4→G6, G4→G7 et G4→G8 ;
- G5→G8 à l’intérieur de P2 ;
- global micro, pools A/B, 18 strates et macro égale par strate ;
- bootstrap apparié 10 000 et bootstrap stratifié ;
- distance descriptive à la référence EGDB/Scan.

Un `P2_CLEAR_BROAD_IMPROVEMENT` exige simultanément : amélioration macro d’au
moins `0,02`, borne haute IC95 ≤0, aucun pool dégradé, au moins 12/18 strates non
dégradées et aucune strate régressant de plus de `0,10`. La référence Scan/TB
n’entre pas dans cette règle.

Quel que soit le verdict :

```text
promotion_authorized=false
p3_authorized=false
automatic_next_job=null
```

## 7. Prochaines actions

1. merger la PR de consolidation après CI verte ;
2. lancer **un seul** wrapper de consolidation, cpx62 ou ccx33 selon la box libre ;
3. enregistrer le verdict G4→G8 dans ce document ;
4. sans amélioration large et significative, arrêter avant P3 et redessiner le
   mécanisme plutôt que d’augmenter encore la profondeur ;
5. ne lancer un gate généraliste/Scan de continuation que si le signal interne
   G4→G8 est clairement positif.

## 8. Artefacts de référence

- P1 V2 : `r2:jass-data/runs/ccx33-0852-l3-imbalance2-role-v2-p1/...` ;
- P2 V2 : `r2:jass-data/runs/ccx33-0859-l3-imbalance2-role-v2-p2/...` ;
- référence : `r2:jass-data/runs/cpx62-0862-l3-imbalance2-a64-b64-difficulty-reference/20260720T130310Z-59940065` ;
- récupération P2 : `r2:jass-data/runs/ccx33-0869-p2-plateau-recover/20260720T152038Z-566943ea`.

Les URI exactes et SHA des modèles restent dans les manifests R2 et les statuts
GitOps. Aucun résultat volumineux n’est re-committé dans Git.
