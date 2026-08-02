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
| A | prior centré sur le parent — réplication | `cpx62-1149` | règle de décision **préenregistrée** : [`experiments/L3_PRIOR_MEAN_PREREGISTRATION_20260802.md`](experiments/L3_PRIOR_MEAN_PREREGISTRATION_20260802.md) |
| B | reproductibilité machine/build | `home-1150` | **hors consolidation** (même pool que la découverte) |
| C | pool de 3000 ouvertures | `cpx62-1151` | lève le plafond `n` : `n=12000`, puissance `56 % → 84 %` sur `+9 Elo` |
| D | `--king-patterns` A/B au scale | `cpx62-1152` | condition de réouverture de la porte `0409`, jamais jouée |

## 3. En file, par ordre de valeur attendue

### 3.1 `--hier-l2` — reculer vers la moyenne du pattern, pas vers zéro
**Même famille que le prior** : le régulariseur affirme qu'un bucket sans données
vaut `0`, alors que la meilleure estimation est soit le parent (`--prior-mean`,
piste A), soit **la moyenne de son pattern**. Implémenté, jamais utilisé
(`0 = off (legacy L2→0)`).
**Déclencheur** : après la conclusion de A, quelle qu'elle soit — les deux
mécanismes se combinent et il faut savoir ce que chacun vaut seul.
**Coût** : refit deux bras ~30 min + porte ~35 min.

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
**Déclencheur** : A conclut positivement.
**Coût** : 3-4 bras (`--prior-visit-scale` / `--prior-decay`) + portes. Attendre
le pool de 3000 (piste C) : à `n=6000` un balayage n'aurait pas la puissance de
séparer ses cellules.

### 3.3 Réouverture de la quiescence
Le registre la ferme deux fois (`−92 à −231 Elo` sur le forcing profond ;
`q1_no_lead` contract-grade sur `0812`, 63 clés, IC franchissant tous zéro).
**L'argument de réouverture n'est pas « on est plus forts » mais « l'instrument
était cassé »** : `0812` et les variantes datent d'**avant `9c1d1e8e`**, donc d'un
moteur qui rendait un coup nul sur toute racine nulle par répétition — et la
quiescence résout précisément des séquences tactiques qui débouchent sur des
répétitions. On a **établi le 1er août, chiffres à l'appui**, que ce bug a
fabriqué un repère faux de 22 points sur la conversion.
⚠️ **Hypothèse, pas cause** : rien n'est mesuré, et promouvoir un mécanisme
plausible en cause est l'erreur commise sur la couverture le matin même.
**Coût** : rejouer **la cellule décisive seule** avec le moteur d'aujourd'hui et
EXACT, pas les 63 cellules de `0812`. Plat → la porte se referme pour de bon ;
mouvement → `0812` entier redevient justifié.

### 3.4 Attribution causale du différentiel d'atlas
Le témoin EXACT/Gen2 (`home-1143quater`/`1144bis`/`1145`) compare deux bras qui
ont visité **des positions différentes** (shards dimensionnés en temps, `1 108 434`
contre `776 034`). Un « coût par position » entre deux distributions n'est pas un
contraste contrôlé. Une attribution causale exigerait **un corpus de positions
fixe et apparié**.
**Déclencheur** : seulement si une décision en dépend. Ce n'est pas le cas
aujourd'hui — le témoin a fermé le soupçon 32cf, ce qu'on lui demandait.

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
