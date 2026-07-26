# L3-PURE — turnover temporel 1:1 à volume constant

Date de préenregistrement : 26 juillet 2026, après le verdict complet de
`home-0974bis` et avant tout fit ou match du candidat turnover.

## Déclencheur et question causale

Les trois bras frais issus du même parent F2M ne créent aucune pente de force :

- M2 d8 : 50,60 % Q00 et 49,05 % native contre F2M ;
- d10 : 48,80 % Q00 et 51,00 % native contre F2M ;
- d12 : 45,85 % Q00 et 46,95 % native contre F2M, avec régression Q00 établie.

La loss holdout baisse pourtant avec la profondeur. Augmenter encore la
profondeur ou relancer 2M frais à recette identique est donc fermé.
Le mix d10/d12 n'est pas autorisé, car son déclencheur exigeait tous les
garde-fous d12 verts.

La nouvelle question est : **à parent, profondeur, volume, architecture,
objectif, split et optimisation constants, conserver 1M positions de l'époque
F2M et 1M positions fraîches de M2 fait-il mieux que les 2M positions fraîches
de M2 ?**

| Facteur | contrôle M2 frais | bras TURNOVER 1:1 |
|---|---:|---:|
| parent et warm-start | F2M | F2M |
| volume de fit | 2 000 000 | 2 000 000 |
| positions époque F2M | 0 | 1 000 000 |
| positions fraîches M2 d8 | 2 000 000 | 1 000 000 |
| profondeur des sources | d8 | d8 |
| architecture / recherche | 8cf / Q00 | identique |
| objectif | WDL terminal pur | identique |
| split | JSM par ouverture | identique |
| fit | L-BFGS, L2 3e-5 | identique |

Il n'y a aucune nouvelle génération. Le bras change uniquement la distribution
temporelle du corpus. Sont interdits : oracle, teacher, TOP3, reweight V2,
L3-IMBALANCE2, augmentation de volume, changement de géométrie, changement de
profondeur ou de régularisation.

## Construction déterministe et preflight pleine échelle

Les 2M positions historiques ayant produit F2M sont reconstruites depuis
`common-fresh-500k` et `extra-fresh-1500k`, avec namespacing imbriqué :

- F2M JNNW :
  `15261c89bd6520e17c03bcf2843b226600ff334130656aab7b1a1f2d1ca03248` ;
- F2M JSM :
  `6b12a940128033652afe578c61e48c8570ba4db14cb4cde363d56d4bdcdf2d7f` ;
- M2 frais JNNW :
  `ee8d685cea331940403da82830d7b4cc045fe50acc1e5764d23f0467d4f7ffb8` ;
- M2 frais JSM :
  `42b184456375bb581192651262f3981879bd04e5ee3162a6186883c2f8f66729`.

Le run M2 historique utilise un schéma de certificat antérieur : la profondeur
n'était pas encore recopiée dans son JSON. Le preflight l'authentifie donc par
son SHA de code immuable `012b9c716dadf2c3df668c23a7dd9d5ece423b8c`
(recette d8), son seed `1618033`, ses hashes corpus/sidecar, son parent F2M et
les champs 8cf/Q00/départs standards/sans TOP3 ni reweight du contrat.

`tools/selfplay_frontier.py mix`, seed `141421`, sélectionne uniformément et
exactement 1 000 000 lignes de chaque source. Les IDs de partie **et
d'ouverture** sont namespacés par source : les deux époques n'utilisent pas les
mêmes tirages d'ouverture, donc une collision numérique ne doit pas les
présenter comme un groupe apparié.

Deux reconstructions indépendantes sont bit-identiques :

- corpus TURNOVER JNNW :
  `9b7db67a87025baf9115c72512312ac13ace076cef700c54ff1862f4ab240a2d` ;
- sidecar JSM :
  `acf3bbf4a28e7b44a1077df06bca9658cd4b189fc4cf11ee7f56720661626682` ;
- `external_teacher_inputs=0`.

Le split ouverture, seed `577215`, donne 1 800 796 records train et 199 204
holdout, sur 70 041/7 759 ouvertures. Ses SHA de preflight sont
`6ac60a9b3d0ede59fe68c91bf896f551908912cc6c4192370757420ca084deaf`
(JNNW) et
`756de534a71e5acebb69e92b5cd062b614d8a1634fd4217200c576c99b3c9218`
(JSM).

La couverture diagnostique 8cf exacte du corpus mixé atteint 210 381 buckets
visités et 28 160 buckets vus au moins 100 fois. C'est supérieur aux corpus
certifiés M2 (206 565 / 27 796) et F2M (204 490 / 27 444), mais ce diagnostic
n'est ni un résultat de force ni une règle de promotion.

## Exécution réservée

1. `home-0977-l3-pure-turnover1to1-train-v1` authentifie F2M, M2 d8,
   l'évaluation M2 et la clôture d12 ; reconstruit le corpus aux SHA ci-dessus ;
   splitte par ouverture ; fitte depuis F2M jusqu'à convergence réelle ;
   publie corpus, sidecar, optimiseur, loss, RAM et modèle.
2. Après succès uniquement,
   `home-0978-l3-pure-turnover1to1-independent-eval-v1` utilise 500 nouvelles
   ouvertures appariées, seed `732051`, disjointes de DILF et des pools F2M,
   M2, d10 et d12. Le pool préflighté a le SHA
   `6ebd2a5ecd79d5e11fc35100c00babb33c98c47843a7b9aadbed7eaef2b6930d`.
3. Le readout compare TURNOVER à M2 frais et F2M en Q00 d9 et cadence native,
   garde Gen2 comme thermomètre, puis rejoue P3/P4 contre le défenseur fixe et
   mesure la couverture exacte des trois corpus.

Chaque confrontation contient 1 000 parties, 500 ouvertures avec couleurs
appariées. Une preuve forte de l'effet temporel exige la borne basse à 95 %
au-dessus de 50 % contre M2 dans les deux vues et tous les garde-fous valides.
Une revue de promotion exige en plus cette même preuve contre F2M. Un signal
directionnel dans les deux vues ouvre seulement une confirmation indépendante.
Sinon le facteur 1:1 est clos.

`promotion_authorized=false` et `automatic_next_job=null` dans tous les cas.

## Sizing HOME et ETA avant lancement

HOME fournit 16 CPU logiques, 15,6 Go de RAM (environ 15 Go disponibles au
preflight) et plus de 960 Go libres. Le build reste limité à `-j4`; le fit
streamé utilise le venv épinglé NumPy 1.26.4 / SciPy 1.14.1.

Le bras ne génère aucune position. `home-0944` a exécuté trois fits comparables
en 1 h 50, soit environ 37 minutes par fit. Avec fetch, reconstruction, tests et
build, l'ETA de `home-0977` est **45–70 minutes**. `home-0974bis`, readout de
taille identique (6 000 parties plus conversion/couverture), a duré 37 min ;
l'ETA de `home-0978` est **35–55 minutes**. Total séquentiel attendu :
**1 h 20 à 2 h 05**.

## Résultats exécutés

`home-0977` a terminé en environ 36 minutes. Le fit converge en 204 itérations,
avec une loss holdout de `0,444060`, un pic RSS de 1 406 684 KiB et le modèle
SHA-256
`b2c79b3617c41087191fee04d9aee0e1929ea63ad621c2efeaebc14ae53a7c16`.

`home-0978` a terminé en environ 35 minutes. Les scores TURNOVER sont :

- contre M2 : 52,20 % Q00 (+15,3 Elo), 51,05 % native (+7,3 Elo) ;
- contre F2M : 52,10 % Q00 (+14,6 Elo), 51,15 % native (+8,0 Elo) ;
- contre Gen2 : 58,70 % Q00 et 61,10 % native.

P3/P4 valent 98/99 %, tous les garde-fous sont verts, et la couverture vaut
210 381 buckets visités / 28 160 à fréquence ≥100. Les quatre estimations
principales sont positives mais sous-résolues : aucune borne basse à 95 % ne
dépasse 50 %. Le verdict est donc
`TURNOVER_DIRECTIONAL_CONFIRMATION_REVIEW`.

La confirmation indépendante est préenregistrée séparément dans
[`L3_PURE_TURNOVER_CONFIRMATION_PROTOCOL_20260726.md`](L3_PURE_TURNOVER_CONFIRMATION_PROTOCOL_20260726.md).
