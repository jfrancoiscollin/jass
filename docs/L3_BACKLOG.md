# L3 — pistes ouvertes et orchestration

Tenu à jour au fil de l'eau. Une piste qui n'est pas ici est oubliée ; une piste
ici sans **déclencheur** ni **coût** n'est pas une piste, c'est un souhait.

> État vivant : [`L3_CURRENT.md`](L3_CURRENT.md) · Portes closes :
> [`PROJECT_RESULTS.md`](PROJECT_RESULTS.md)

## 1. Le fil conducteur

Le 1er août a mesuré la même chose trois fois : **produire plus ou plus large ne
paie pas** (autojeu on-policy plat, couverture en régression établie, top-k
négatif), tandis que **retirer une contrainte fausse paie** (`--exact-fold`,
`+15,12 Elo`, sans une donnée neuve). Les pistes ci-dessous sont ordonnées par
cette leçon : d'abord ce que le fit impose à tort, ensuite le reste.

## 2. En vol

| # | piste | job | état |
|---|---|---|---|
| A | prior centré sur le parent — réplication | `cpx62-1149` | ✅ **clos**, PRIOR promu le 2 août ; re-mesuré à `1e-4` : `+8,48` IC95 `[+3,5 ; +13,4]`, `n=18 000` |
| B | reproductibilité machine/build | `home-1150` | **hors consolidation** (même pool que la découverte) |
| C | pool de 3000 ouvertures | `cpx62-1154` | ✅ **livré et utilisé** par `1161` et `1163` : `n=12 000` par porte |
| D | `--king-patterns` A/B au scale | `cpx62-1156` | ⛔ **modèles prêts, porte BLOQUÉE** — voir §3.5 |
| E | tolérance du solveur `1e-4` | `cpx62-1157`/`1159`/`1160`/`1161`/`1163` | ✅ **PRIORTIGHT promu champion général le 3 août** : [`experiments/L3_PRIORTIGHT_PROMOTION_20260803.md`](experiments/L3_PRIORTIGHT_PROMOTION_20260803.md) |
| F | dose de tolérance `1e-5` | `home-1210` | ✅ **AXE CLOS** : `1e-5` inatteignable, L-BFGS-B bute sur `REL_REDUCTION_OF_F` avant le test de gradient. `1e-4` est le plancher pratique |
| G | dose du prior = dose de `l2` | `cpx62-1164`→`1171` | ✅ **L2LOW promu champion général le 4 août** : axe clos par plateau — voir §3.2 |

## 3. En file, par ordre de valeur attendue

### 3.1 `--hier-l2` — reculer vers la moyenne du pattern, pas vers zéro
**Même famille que le prior** : le régulariseur affirme qu'un bucket sans données
vaut `0`, alors que la meilleure estimation est soit le parent (`--prior-mean`,
piste A), soit **la moyenne de son pattern**. Le code ajoute HIER au ridge
ordinaire ; il ne le remplace pas. `cpx62-0517` l'a essayé avant EXACT, avec des
doses de 33 à 333 fois `l2` et deux cellules qui changeaient aussi `l2` : négatif,
mais pas le bouton unique actuel.

**Préenregistré, pas lancé** : CONTROL `hier_l2=0` contre HIER `hier_l2=3e-5`,
`l2=3e-5`, EXACT et tous les autres facteurs identiques ; porte sur le pool 3000,
`n=12000`. Après l'artefact de convergence de `cpx62-1155`, le refit est
fail-closed : `success=True` ne suffit pas, chaque bras doit publier
`||grad||∞ <= 1e-4` avant toute porte. Le garde apparié porte uniquement sur un
ratio d'itérations `>=5` ; le ratio `grad/gtol` est diagnostique, car L-BFGS-B
termine naturellement près de cette surface. Règle :
[`experiments/L3_HIER_L2_PREREGISTRATION_20260802.md`](experiments/L3_HIER_L2_PREREGISTRATION_20260802.md).
**Déclencheur scientifique satisfait** (PRIOR est promu) ; dépôt en attente du
verdict king-aware et du go de JFC. Un succès rouvre seulement `PRIOR+HIER` contre
`PRIOR`, sans promotion directe.
**Coût** : refit deux bras, puis porte deux vues ; sizing/ETA à confirmer sur HOME
juste avant le dépôt.

### 3.2 Dose-réponse sur la force du prior
**La question de JFC, et elle est plus fine que le test binaire de A.** Le prior
bayésien était le mécanisme de production de l'ère gen1/gen2 (`0545`…`0555`, dont
un balayage de λ dédié) et `gen2-mmto` en est issu. La campagne L3 est passée à
`--warm-start` **et** la composition des données est passée de **100 % frais** à
un **mélange 1:1** — deux changements jamais réévalués l'un à la lumière de
l'autre. En 100 % frais le prior était le **seul** porteur du passé ; avec un
mélange 1:1, **la moitié mémoire EST le parent réinjecté comme donnée**, donc un
prior centré sur le parent risque de le **compter deux fois**. Le λ calibré à
l'ère 100 % frais **ne se transporte pas**.
✅ **CLOS le 4 août : L2LOW (`l2=1e-5`) promu champion général.** La dose
n'était pas sur `λ` — inerte à `decay 0` — mais sur `l2`, qui sous
`--prior-mean` est la force du rappel vers le parent. Quatre points, courbe
monotone bornée des deux côtés (`1e-4 : −15,65` · `1e-5 : +12,54` ·
`3e-6 : +14,25`), axe fermé par **plateau** (`1e-5` ≡ `3e-6`, `z = 0,39`).
Consolidé `+11,31 Elo` IC95 `[+6,4 ; +16,3]`, `n = 18 000`, gardes vertes.
Enregistrement : [`experiments/L3_L2LOW_PROMOTION_20260804.md`](experiments/L3_L2LOW_PROMOTION_20260804.md).

**Déclencheur historique : SATISFAIT deux fois.** A conclut positivement (PRIOR promu le
2 août), et le prior survit au resserrement de la tolérance (`+8,48` à `1e-4`
contre `+6,66` à `1e-3`). ⚠️ **Tout balayage doit désormais tourner à
`--lbfgs-gtol 1e-4`** : un balayage de λ sous `1e-3` mesurerait pour partie
jusqu'où chaque cellule a convergé, pas ce que chaque λ vaut.
**Coût** : 3-4 bras (`--prior-visit-scale` / `--prior-decay`) + portes. Le pool
de 3000 (piste C) est livré, donc `n=12 000` par cellule. ⚠️ Les fits à `1e-4`
prennent `~5×` plus d'itérations qu'à `1e-3` (`904` contre `169`) : re-sizer
l'ETA avant de proposer, ne pas transporter l'ancre des refits du 2 août matin.

### 3.3 Réouverture de la quiescence
**FERMÉE le 2 août (`home-1200` + readout immuable `home-1202`)** : la cellule
décisive `Q01_SACS` reste plate sur les deux co-primaires préenregistrés avec le
moteur courant et EXACT. Force native `0,508333`, IC97,5
`[0,488435 ; 0,528231]`, `n=3000` ; conversion P3/P4 appariée `+1,1667 pp`,
IC97,5 `[−1,0000 ; +3,3333]`, `n=600`. Le mouvement positif à profondeur 9
est diagnostique seulement et ne satisfait pas la règle de réouverture.
**Verdict : `QUIESCENCE_CLOSE_CONFIRMED` ; ne pas rejouer les 63 cellules.**
Readout immuable :
`r2:jass-data/runs/home-1202-codex-quiescence-q01-readout-at-ddec2fc6-v2/20260802T125117Z-ddec2fc6`.

Le registre la ferme deux fois (`−92 à −231 Elo` sur le forcing profond ;
`q1_no_lead` contract-grade sur `0812`, 63 clés, IC franchissant tous zéro).
**L'argument de réouverture n'est pas « on est plus forts » mais « l'instrument
était cassé »** : `0812` et les variantes datent d'**avant `9c1d1e8e`**, donc d'un
moteur qui rendait un coup nul sur toute racine nulle par répétition — et la
quiescence résout précisément des séquences tactiques qui débouchent sur des
répétitions. On a **établi le 1er août, chiffres à l'appui**, que ce bug a
fabriqué un repère faux de 22 points sur la conversion.
⚠️ **Hypothèse, pas cause** : le replay mesure désormais la conséquence utile
pour la décision, mais n'établit toujours pas que le bug expliquait les anciens
résultats de `0812`. Le test préenregistré est resté plat ; la porte est donc
refermée sans promouvoir ce mécanisme plausible en cause.

### 3.4 Attribution causale du différentiel d'atlas
Le témoin EXACT/Gen2 (`home-1143quater`/`1144bis`/`1145`) compare deux bras qui
ont visité **des positions différentes** (shards dimensionnés en temps, `1 108 434`
contre `776 034`). Un « coût par position » entre deux distributions n'est pas un
contraste contrôlé. Une attribution causale exigerait **un corpus de positions
fixe et apparié**.
**Déclencheur** : seulement si une décision en dépend. Ce n'est pas le cas
aujourd'hui — le témoin a fermé le soupçon 32cf, ce qu'on lui demandait.

### 3.5 ⛔ Porte king-aware — bloquée sur un build PAR BRAS
**Les deux modèles existent** depuis `cpx62-1156` : `control` = TIGHT,
`exact` = TIGHT + `--king-patterns`, un seul facteur, tous deux convergés à
`1e-4` (`653` et `820` itérations). Leurs pertes en holdout sont **à égalité
au millionième** (`0,441695` contre `0,441699`), ce qui ne tranche rien — la
porte est le seul juge.

**Ce qui bloque** : un modèle king-aware exige un moteur compilé
`-DJASS_KING_PATTERNS` (`CMakeLists.txt:109`, et l'occupancy devient `men|kings`
dans `scan_eval.hpp:61`). Or `l3-model-gate-v1.sh` ne produit **qu'un seul
build** pour les deux bras. Il faut donc un build **par bras**, exactement comme
`l3-succession-guards-v1.sh` le fait déjà pour opposer du 8cf à du 32cf.

✅ **Aucun risque de mesure silencieuse** : `scan_eval.cpp:370` compare le bit
king de l'en-tête auto-descriptif au `KING_AWARE_PATTERNS` du build et **refuse
le modèle**. Une porte naïve échouerait bruyamment à « modèles chargeables ».

**Déclencheur** : travail de template (une variante `l3-model-gate-2build-v1.sh`,
ou un `PER_ARM_CMAKE_FLAGS` dans le template existant). C'est du code : candidat
naturel pour Codex, revue par moi.
**Coût** : template + une porte deux vues. Le pool 3000 est disponible, donc
`n=12 000` d'emblée — nécessaire, vu que les holdouts n'écartent rien.


## 4. Orchestration à deux agents

Codex et moi partageons `develop`, la file et l'espace de numérotation. Ce qui a
déjà coûté des jobs le 1-2 août :

- **`cpx62-1140`, `1143`, `1146`** : morts sur `code SHA mismatch`. Le runner
  checkout **le tip de `develop` au claim**, et `EXPECTED_CODE_SHA` est une
  assertion — donc un pin périme dès que l'autre agent pousse, **même quand le
  commit intercalé ne touche rien du job**.
  `cpx62-1151`, `cpx62-1152` et `home-1150` ont confirmé le même défaut le
  2 août : une discipline temporelle seule ne ferme pas la course.
- **Deux `1143`** ont coexisté (`home-1143quater` et `cpx62-1143`).
  → **Plages disjointes** : `home-*` à Codex, `cpx62-*` à moi.
- **Rebaser avant de pousser** sur `develop`, systématiquement.

### Nomenclature et pin immuable

Pour tout nouveau job :

```text
<runner>-<num>-<auteur>-<piste>-<étape>-at-<sha8>-v<n>
```

Par exemple :
`home-1200-codex-quiescence-q01-at-9b57e0aa-v1` et
`cpx62-1153-claude-prior-guards-at-9b57e0aa-v1`.

- `home-12xx` est la plage Codex ; Claude conserve `cpx62-*` ;
- `codex` / `claude` nomme le déposant, pas la machine ;
- `at-<sha8>` rend l'époque de code visible ; le script porte obligatoirement
  le SHA complet et littéral dans `EXPECTED_CODE_SHA` ;
- le runner vérifie la concordance du SHA visible, vérifie que le commit est
  dans l'historique de `origin/develop`, puis crée le worktree détaché **sur ce
  pin**. Un push ultérieur sur `develop` ne périme donc plus le job ;
- pendant la transition d'un runner encore ancien, aucun push sur `develop`
  tant qu'un job adverse reste dans `queue/pending`. Un job déjà claimé est
  hors course : son worktree est détaché et immuable.

**Répartition proposée** : Codex écrit du code et les jobs `home-*` ; je revois
et je tiens les jobs `cpx62-*`. Toute revue porte d'abord sur trois points, parce
que ce sont les trois qui ont coûté du compute cette nuit :
1. **le round-trip écriture→lecture** — les clés que le job lit sont-elles celles
   que l'outil écrit ? (`conversion`/`n_pos`, pas `conversion_rate`/`records`) ;
2. **chaque entrée consommée a-t-elle un producteur ?** (les jauges P3/P4 ne
   viennent pas du bundle figé) ;
3. **les assertions survivent-elles à la paramétrisation ?** (le verify du refit
   exigeait qu'un bras viole une symétrie, ce qui n'avait de sens qu'avant que
   les folds deviennent des boutons).

## 5. Règles acquises qui s'appliquent à toute piste

- **Une porte appariée ne voit pas ce qui frappe ses deux bras.** Seule une
  cellule à référence figée voit une dérive absolue.
- **Protéger la moitié d'un instrument ne protège rien** — figer le défenseur et
  laisser l'attaquant suivre `develop` rend toute série temporelle incomparable.
- **La couverture et la loss holdout sont des diagnostics**, jamais des critères
  de sélection.
- **`n` est plafonné par la taille du pool** (moteur déterministe à profondeur
  fixe) : plus de `--pairs` ne fabrique que des doublons.
- **Préenregistrer la règle de décision** avant de voir les chiffres.
