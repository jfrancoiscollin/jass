# PRIORTIGHT — promotion au rang de champion général

Enregistrement immuable. Promotion décidée par revue humaine de JFC le
3 août 2026, après les portes `cpx62-1161` et `cpx62-1163` et les gardes
`cpx62-1162`. Les jobs ont été menés en autonomie la nuit du 2 au 3 août sur
mandat de JFC ; la décision de promouvoir est la sienne, prise au réveil sur
enregistrement complet.

## Identités

```text
nouveau champion  PRIORTIGHT 2bbe1733ca0976ce4934131f83178a9e3757b5bc7a9b5a3bdbc41984781dfec7
                  r2:jass-data/runs/cpx62-1159-l3-prior-tight-refit-v1/
                     20260802T171908Z-646f1149/artefacts/exact.pjtw.gz

champion précédent PRIOR     22e9c903fb504c0f5739a3a13cce9fb3840a6b4b62075ba9c502b785c8d35dc3
                  (empreinte re-vérifiée depuis l'object store, conforme au registre)

bras de contrôle  TIGHT      9c550a9b37aca1de28b5ec2124ebb860108d59b940832e6c6d6a02a078daa8ec
référence figée   GEN2 (gen2-mmto), inchangée
```

Empreintes du `.pjtw` **décompressé**, comme F2M, TURNOVER, EXACT et PRIOR.

## Comment PRIORTIGHT a été construit

**Aucune donnée neuve, aucune capacité neuve, aucune géométrie neuve** — le
quatrième gain d'affilée obtenu sans produire une position de plus.

Deux réglages, tous deux déjà mesurés séparément, appliqués ensemble au même
corpus TURNOVER et au même parent :

```text
--exact-fold                        la seule symétrie exacte du damier (acquis du 1er août)
--prior-mean <parent> --prior-decay 0   le ridge centré sur le parent, pas sur zéro
--lbfgs-gtol 1e-4                   la tolérance d'arrêt du solveur
```

### Le troisième réglage n'est pas un réglage de modèle

`--lbfgs-gtol` ne change ni l'objectif, ni la géométrie, ni la contrainte : il
change **où L-BFGS s'arrête**. À `1e-3` — la valeur employée par toute la
campagne jusqu'au 2 août — les deux recettes s'arrêtaient à **141** et **169**
itérations (`cpx62-1147`). À `1e-4`, les mêmes recettes sur les mêmes données en
prennent **653** et **904** (`cpx62-1156`, `cpx62-1159`).

⛔ **Conséquence à graver : EXACT et PRIOR étaient sous-convergés.** Une partie de
ce que la campagne comparait n'était pas ce que chaque recette vaut, mais
**jusqu'où le solveur était allé** avant de rendre la main. `success=True` était
rendu dans les deux cas, ce qui a masqué le problème pendant toute la campagne —
L-BFGS-B rapporte le succès aussi bien sur convergence du gradient que sur
`max_iter`. Le signal fiable est **l'asymétrie du compte d'itérations**, pas le
rapport `‖∇‖∞/gtol` : les deux bras convergés atterrissent à `0,88` et `0,97` de
la surface, parce que le solveur s'arrête naturellement juste après le seuil.

## Preuve de force

### La porte de succession — le challengeur contre le champion assis

`cpx62-1163`, pool `big3000` de `cpx62-1154` (3000 ouvertures, disjoint des deux
pools de porte antérieurs), estimateur à vues **additionnées**, `n = 12 000`,
EGDB présente :

```text
PRIORTIGHT 5992W 639D 5369L contre PRIOR
taux = 0,5260   IC95 = [0,5173 ; 0,5347]
Elo  = +18,05   IC95 = [+12,0 ; +24,1]
```

**Un seul facteur sépare ces deux modèles : la tolérance.** PRIOR est
`exact-fold + prior` à `1e-3`, PRIORTIGHT est `exact-fold + prior` à `1e-4`.
Cette porte est donc à la fois la porte de succession et la mesure propre du
gain de tolérance sur la recette du prior.

### Décomposition à un facteur

| ce qui change | cellule | pool | n | Elo | IC95 |
|---|---|---|---:|---:|---|
| tolérance, sur `warm` | `cpx62-1157` | `home-1004` | 6000 | `+15,99` | `[+7,4 ; +24,6]` |
| tolérance, sur `prior` | `cpx62-1163` | `big3000` | 12000 | `+18,05` | `[+12,0 ; +24,1]` |
| prior, à `1e-4` | `cpx62-1160` | `home-1004` | 6000 | `+9,38` | `[+0,8 ; +18,0]` |
| prior, à `1e-4` | `cpx62-1161` | `big3000` | 12000 | `+8,02` | `[+2,0 ; +14,0]` |
| **prior à `1e-4`, consolidé** | deux pools disjoints | **18 000** | **`+8,48`** | **`[+3,5 ; +13,4]`** |
| prior, à `1e-3` (registre PRIOR) | deux pools | 12 000 | `+6,66` | `[+0,4 ; +12,9]` |

`8711W 1017D 8272L` pour la ligne consolidée du prior.

⚠️ **`cpx62-1158` (`+12,05`) ne figure PAS dans cette décomposition** : il
opposait TIGHT (`warm` @ `1e-4`) à PRIOR (`prior` @ `1e-3`), soit **deux facteurs
à la fois**. Il reste vrai, il n'est simplement pas interprétable comme une
mesure d'un bouton. `cpx62-1163` le remplace, à un facteur et à double
puissance.

### Cohérence interne

Les deux mesures de la tolérance, prises sur des recettes différentes et des
pools différents, tombent à `+15,99` et `+18,05` — intervalles largement
recouvrants. Et l'addition naïve du gain de tolérance et du gain de prior donne
`~+20` pour PRIORTIGHT sur PRIOR, contre `+18,05` mesuré directement : l'Elo
n'est pas additif en général, mais l'écart reste dans le bruit.

### Réplication du pas « prior », telle que préenregistrée

La règle exigeait un IC95 consolidé excluant zéro **et** deux points de même
signe. Les deux critères sont remplis (`+9,38` et `+8,02`, consolidé
`+8,48 [+3,5 ; +13,4]`). Comme pour PRIOR, **la réplication est tombée sous la
découverte** (`8,02 < 9,38`) : le rétrécissement attendu de la malédiction du
vainqueur, préenregistré avant les chiffres.

À `1e-4` le prior vaut `+8,48` contre `+6,66` à `1e-3`. Les intervalles se
recouvrent largement : **rien ne prouve que le prior vaille davantage une fois le
solveur allé au bout**, seulement que le resserrement de la tolérance ne le
mange pas. Les deux corrections sont distinctes et cumulatives.

## Gardes de succession (`cpx62-1162`)

| garde | PRIORTIGHT | repères |
|---|---|---|
| non-régression Gen2 | `62,14 %`, **`+86,09 Elo`**, IC95 `[0,6091 ; 0,6337]`, `3607W 243D 2150L`, deux vues positives (`q00` `0,6197` · `native` `0,6232`) | PRIOR `+70,01` · EXACT `+68,21` · TURNOVER `+64,19` |
| conversion `p3_mince` | `0,8067` (W242 D14 L44) | plancher `0,70` · PRIOR `0,7600` · EXACT `0,7733` |
| conversion `p4_egal` | `0,7800` (W234 D14 L52) | plancher `0,70` · PRIOR `0,7433` · EXACT `0,7133` |

`SUCCESSION_GUARDS_GREEN`. Les trois gardes sont non seulement au-dessus de leur
seuil mais **au-dessus des trois champions précédents**, y compris sur la
conversion, où le plancher honnête de `~0,76` avait été établi le 1er août après
la démolition du repère de juillet.

## Un contrôle qui n'était pas prévu, et qui tient

TIGHT produit par `cpx62-1156` et le bras `control` de `cpx62-1159` — deux jobs
indépendants, deux dates, même recette — sont **byte-identiques**
(`9c550a9b…` des deux côtés). Toute l'échelle EXACT → TIGHT → PRIORTIGHT est
donc ancrée sur un maillon intermédiaire reproduit bit à bit, et le `+15,99` de
`cpx62-1157` porte sur exactement le modèle qui sert de contrôle à `cpx62-1159`.

## Pertes en holdout, pour information seulement

```text
EXACT       0,442898        (reproduit comme bras control de cpx62-1147)
PRIOR       0,442207   169 itérations @ 1e-3
TIGHT       0,441695   653 itérations @ 1e-4
PRIORTIGHT  0,440121   904 itérations @ 1e-4
```

L'ordre coïncide ici avec celui des portes. **Ce n'est pas une validation** : ce
projet a mesuré quatre fois que la perte en holdout ne prédit pas la force, et
`cpx62-1156` en donne un cinquième exemple le même jour — le bras king-aware rend
`0,441699` contre `0,441695` pour son contrôle, soit un écart nul, sans qu'aucune
porte ne l'ait départagé.

## ⚠️ Ce que cette promotion n'établit pas

- **Le gain de tolérance n'est pas un gain de méthode d'évaluation.** C'est la
  correction d'un arrêt prématuré du solveur. Il ne se re-gagnera pas : une fois
  `1e-4` adopté, il est encaissé. **Tout nouveau fit L3 doit porter
  `--lbfgs-gtol 1e-4` ET `--exact-fold` ET `--prior-mean/--prior-decay 0`.**
- ~~**`1e-4` n'est pas montré optimal.**~~ **TRANCHÉ** (`home-1210`, 3 août) :
  `1e-5` est **inatteignable**. Le bras s'arrête sur le critère de fonction —
  `REL_REDUCTION_OF_F_<=_FACTR*EPSMCH`, 1048 itérations, `‖∇‖∞ = 1,448e-4`, donc
  **pire** que les `8,68e-5` du bras `1e-4` en 801 itérations. L-BFGS-B bute sur
  le plancher de réduction relative de `f` avant de pouvoir satisfaire le test de
  gradient. `1e-4` est le **plancher pratique** du solveur sur cet objectif, pas
  simplement le meilleur point connu. Le seul bouton qui irait plus loin est
  `ftol` (défaut scipy `2,22e-9`), non exposé par `train_stream.py`.
- ⚠️ **Le fit du champion candidat avait 9,6 % de marge sous le plafond
  d'itérations** : 904 itérations sous `max_iter=1000`. Il s'est bien arrêté sur
  le gradient (`PGTOL`, `‖∇‖∞ = 9,840e-5`), donc il est convergé — mais la marge
  était mince, et le plafond n'a été porté à 5000 qu'après (`7025b63f`).
- ⚠️ **Un fit d'une box ne se compare pas à un fit de l'autre.** `home-1210` a
  tourné la pile numérique `historical` (numpy 1.26.4 / scipy 1.14.1) là où
  `cpx62-1159` tournait `current` (2.5.1 / 1.18.0) : la même recette à `1e-4`
  rend 801 itérations et un holdout de `0,441615` sur HOME contre 653 et
  `0,441695` sur cpx62. Toutes les mesures de cet enregistrement viennent de
  **bras appariés dans un même job** ; c'est nécessaire, pas seulement propre.
- **Le pas « tolérance » de la succession repose sur un seul pool.**
  `cpx62-1163` est à `n=12 000` sur `big3000`, ce qui est puissant, mais c'est
  une seule mesure. Le pas « prior », lui, en a deux.
- **Le chiffre du prior est biaisé vers le haut**, comme préenregistré. Borne
  basse consolidée `+3,5`.
- **La dose-réponse du prior reste à faire** (backlog §3.2) : `--prior-decay 0`
  est *un* réglage, et le λ de l'ère 100 % frais ne se transporte pas à un
  mélange 1:1 où la moitié mémoire **est** le parent réinjecté comme donnée.
- **`--hier-l2` n'est pas testé** (backlog §3.1).
- **La question king-aware reste ouverte et vient de se révéler plus chère que
  prévu** — voir ci-dessous.
- **Rien sur Scan, rien au-delà de d8, rien hors 8cf, couverture par bucket non
  recomptée.**

## ⛔ Découverte annexe : la porte king-aware ne peut pas être jouée telle quelle

Les deux modèles nécessaires existent depuis `cpx62-1156` (control = TIGHT,
exact = TIGHT + `--king-patterns`), et j'ai envisagé de jouer la porte cette
nuit sur la box inoccupée. **Elle n'est pas jouable avec
`l3-model-gate-v1.sh`** : un modèle king-aware exige un moteur compilé
`-DJASS_KING_PATTERNS` (`CMakeLists.txt:109`), alors que le template ne produit
**qu'un seul build** pour les deux bras. Il faudrait un build **par bras**, comme
le fait déjà `l3-succession-guards-v1.sh` pour opposer du 8cf à du 32cf.

✅ **Le risque silencieux n'existe pas** : `scan_eval.cpp:370` compare le bit
king de l'en-tête auto-descriptif au `KING_AWARE_PATTERNS` du build et **refuse
le modèle** en cas de désaccord. Une porte naïve échouerait bruyamment à la phase
« modèles chargeables », elle ne comparerait pas du bruit. La piste est donc
bloquée sur du travail de template, pas sur un doute de mesure.

## Réversibilité

Promotion **purement documentaire**, comme F2M (`3db4506f`), TURNOVER
(`54c9dc39`), EXACT (`52e8a448`) et PRIOR (`2dd33a78`). Aucun artefact de
l'object store n'est modifié ; PRIOR reste immuable sous son préfixe daté et
restaurable. `git revert` du commit de bake suffit.

## Trace

- porte de succession contre le champion assis : `r2:jass-data/runs/cpx62-1163-l3-priortight-vs-prior-pool3000-v1`
- gardes de succession : `r2:jass-data/runs/cpx62-1162-l3-priortight-succession-guards-v1`
- réplication du prior à `n=12 000` : `r2:jass-data/runs/cpx62-1161-l3-priortight-pool3000-n12000-v1`
- découverte du prior à `1e-4` : `r2:jass-data/runs/cpx62-1160-l3-priortight-vs-tight-gate-v1`
- refit deux bras (TIGHT / PRIORTIGHT) : `r2:jass-data/runs/cpx62-1159-l3-prior-tight-refit-v1/20260802T171908Z-646f1149`
- tolérance sur `warm` : `r2:jass-data/runs/cpx62-1157-l3-gtol-vs-exact-v1`
- pool de 3000 ouvertures : `r2:jass-data/runs/cpx62-1154-l3-big-opening-pool-v1/20260802T120251Z-9b57e0aa`
- promotion précédente : [`L3_PRIOR_PROMOTION_20260802.md`](L3_PRIOR_PROMOTION_20260802.md)
- règle préenregistrée du prior : [`L3_PRIOR_MEAN_PREREGISTRATION_20260802.md`](L3_PRIOR_MEAN_PREREGISTRATION_20260802.md)
