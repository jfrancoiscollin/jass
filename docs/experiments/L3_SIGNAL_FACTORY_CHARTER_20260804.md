# Usine à signal — document de cadrage

Écrit le 4 août 2026, avant toute ligne de code et avant toute heure de box.
Destiné à une mise en œuvre par Codex, revue par Claude. JFC arbitre.

> **But** : rendre l'autojeu **mesurable**, pour pouvoir l'écarter ou l'incriminer
> comme cause de stagnation, puis produire un autojeu **informatif** au lieu d'un
> autojeu **abondant**.

---

## 0. Le principe qui gouverne tout le chantier

⛔ **Une métrique de signal qui n'a pas été montrée capable de prédire l'Elo ne
vaut rien dans ce projet.**

Ce n'est pas une précaution rhétorique, c'est le résumé de cinq mesures :

| proxy | verdict |
|---|---|
| perte en holdout | ne prédit pas la force — **5 fois**, dont une à l'envers (VOL8M : meilleur holdout, `−14,95 Elo`) |
| couverture en buckets | **réfutée** comme critère : `+2,83 %` de buckets pour `−9,27 Elo` |
| accuracy pairwise (rank-finetune) | `+` sur la métrique, **`−847 Elo`** en jeu |

Conséquence structurante : **le chantier ne construit pas un score à optimiser.
Il construit des CANDIDATS-métriques, puis les valide contre des portes.** Le
jalon M3 existe pour ça, et son issue légitime inclut « aucune de ces métriques
ne prédit l'Elo » — auquel cas on aura économisé une campagne au lieu d'en rater
une.

⚠️ **Aucun jalon postérieur à M3 ne doit être lancé avant que M3 ait rendu.**

---

## 1. Ce qui bloque aujourd'hui, concrètement

Les filtres demandés — parties sans gaffe, avec gaffe, équilibrées, finales à
dames, blocages, supériorité matérielle — **ne peuvent pas être appliqués après
coup**, parce que rien ne les enregistre.

- Le record **JNNW** fait **38 octets** : `4×u64` bitboards, `u8` trait,
  `i32` score, `i8` WDL. Il décrit **la position**, pas son contexte.
- Le sidecar **JSM1** fait `4B magic + u32 count + count × (u64 game_id,
  u64 opening_id, u8 seeded)`, soit **17 octets/record**. Il ne porte **ni le
  ply, ni le résultat de la partie, ni sa longueur, ni la contamination**.

⛔ **Donc chaque filtre coûte aujourd'hui une régénération complète du corpus.**
C'est le verrou : tant qu'il tient, on n'a pas une usine, on a une file de
commandes.

✅ **En revanche, tout ce qui est propriété de la POSITION est déjà dérivable du
JNNW seul** — compte de pièces, présence de dames, balance matérielle, phase.
Le sidecar n'a donc à porter que **le contexte de partie et le contexte
temporel**.

---

## 2. Les métriques candidates

Quatre familles. Aucune n'est acquise ; toutes passent par M3.

### 2.1 Exactitude de l'étiquette — *l'étiquette est-elle VRAIE ?*

Le corpus étiquette chaque position par le **résultat de la partie**. Sur les
positions que la tablebase connaît, ce résultat peut être faux : une position
théoriquement nulle, gagnée par une bourde ultérieure, porte « gain ».

**Mesure** : `--egdb-audit` (livré le 4 août, lecture seule) — matrice de
confusion `3×3` étiquette × vérité, taux de désaccord, taux d'**inversion**
(`gain` étiqueté là où la vérité dit `perte`).

⚠️ Ne couvre que `≤ 7` pièces, c'est-à-dire là où le résultat de partie est le
**plus** fiable : **borne optimiste** du bruit réel.

### 2.2 Contamination — *l'étiquette parle-t-elle de CETTE partie ?*

Un échantillon est **contaminé** si `ply ≤ last_eps_ply` : la partie a déraillé
**après** lui par un coup d'exploration aléatoire, donc son étiquette est le
résultat d'une partie qui n'aurait pas fini ainsi sans le bruit qu'on injecte.

Le moteur **compte déjà** (`LABELHYG contaminated_samples=…`) et sait déjà
filtrer (`--drop-post-eps`) — **le drapeau n'est pas activé dans nos
générations**. Mécanisme irréfutable, coût nul, jamais mesuré en Elo.

### 2.3 Information de Fisher — *la position APPREND-elle quelque chose ?*

Pour une régression logistique, l'information portée par une position vaut
**`p(1−p)`**, où `p` est la probabilité prédite **par le modèle courant**.

- Une position que le champion juge déjà tranchée (`p≈0` ou `p≈1`) ne pèse
  presque rien dans le fit, quelle que soit la justesse de son étiquette.
- Les positions **incertaines** portent presque toute l'information.

✅ C'est la formulation propre de « trop *quiet* » : Scan-vs-Scan a échoué parce
que **`p(1−p)` y est faible partout**, pas parce que les parties sont mauvaises.

⚠️ **Piège à énoncer** : maximiser `p(1−p)` sous le modèle courant, c'est de
l'apprentissage actif — et ça peut dégénérer vers des positions bizarres que
nulle partie réelle ne visite, exactement comme la couverture a dégénéré avec
`--random-open-plies 24`. **C'est un candidat, pas un objectif.**

### 2.4 Structure du corpus — *couverture et redondance*

Couverture par bucket (`l3_bucket_visits.py`, existe), observations par
paramètre libre, part de buckets neufs qu'un lot ajoute.
⚠️ **La couverture est déjà réfutée comme critère de sélection.** Elle reste un
diagnostic, jamais un objectif.

---

## 3. Jalons

Chaque jalon est **testable seul** et **ne dépend que du précédent**.

### M0 — Sidecar de provenance `JSM2` *(le verrou)*

**Objet** : rendre les filtres post-hoc possibles, sans toucher au corpus.

**Format proposé** — `magic "JSM2"` + `u32 count` + `count ×` :

| champ | type | sens |
|---|---|---|
| `game_id` | `u64` | inchangé depuis JSM1 |
| `opening_id` | `u64` | inchangé |
| `seeded` | `u8` | inchangé |
| `ply` | `u16` | ply de CETTE position dans la partie |
| `game_plies` | `u16` | longueur totale de la partie |
| `last_eps_ply` | `u16` | dernier ply d'exploration ; `0xFFFF` = aucune |
| `game_result` | `i8` | résultat de la partie, **POV BLANC**, `{−1,0,+1}` |
| `flags` | `u8` | `b0` plycap · `b1` adjudicated · `b2` tb_relabelled · `b3` réservé |

= **25 octets/record**.

⚠️ **`game_result` est POV BLANC, alors que le WDL du JNNW est POV TRAIT.** Deux
conventions différentes dans deux fichiers alignés : à écrire dans le code, dans
le doc de format, et à couvrir par un test. C'est le piège numéro un de ce jalon.

**Contraintes non négociables**

1. ⛔ **Le JNNW produit doit être BYTE-IDENTIQUE avec et sans l'extension.**
   Le corpus ne change pas ; seul le sidecar s'enrichit.
2. Les lecteurs de `JSM1` continuent de lire du `JSM1` (dispatch sur le magic).
   Les corpus historiques restent exploitables.
3. `tools/selfplay_frontier.py` (`merge`, `mix`) doit **propager** les nouveaux
   champs, y compris à travers le re-namespacing des `game_id`/`opening_id`.

**Tests d'acceptation**

- `t0` un JSM1 existant se relit sans changement de comportement ;
- `t1` écriture→relecture d'un JSM2 : tous les champs identiques ;
- `t2` **génération courte lancée deux fois, avec et sans JSM2 → JNNW identique
  au bit près** (`cmp`) ;
- `t3` `merge` de deux corpus JSM2 : champs préservés, `game_id` renamespacés,
  `ply`/`game_plies`/`last_eps_ply` inchangés ;
- `t4` `mix` à deux sources : idem, et le manifeste déclare le schéma du sidecar ;
- `t5` cohérence : pour chaque record, `ply < game_plies`, et
  `flags.plycap ⇒ game_plies == MAXPLIES`.

### M1 — Fiche signalétique de corpus

**Objet** : un outil qui rend, pour n'importe quel couple `(jnnw, jsm)`, un JSON
unique regroupant les quatre familles du §2.

`jobs/tools/corpus_signal_report.py --data … --meta … [--model …] [--egdb …] --out …`

Contenu minimal :

```
records, games, positions_par_partie
wdl : loss/draw/win (part)
contamination : part de ply<=last_eps_ply
plycap : part de parties et de positions concernées
positions : histogramme du compte de pièces, part avec dames, balance matérielle
couverture : buckets visités, observations par paramètre libre
fisher : moyenne et déciles de p(1-p) sous --model
egdb : in_range, désaccord, inversion   (si --egdb)
```

⚠️ **Définition de `p` à figer** : `p = σ(w·x)` avec `w` les poids du `.pjtw`
fourni et `x` les features 8cf **du même dump que le fit** — pas une
ré-implémentation. Si les deux divergent, la métrique ne mesure pas le modèle
qu'on entraîne.

**Tests** : corpus synthétique aux propriétés connues → la fiche rend ces
propriétés ; corpus vide → échec propre ; `--model` absent → tout sauf `fisher`.

### M2 — Filtrage post-hoc

`jobs/tools/corpus_filter.py --data … --meta … --select "<expr>" --out-data … --out-meta … --manifest …`

Prédicats sur les champs du sidecar **et** sur les propriétés dérivées de la
position. Déterministe, **ordre préservé**, manifeste avec compte avant/après et
hash des sorties.

**Tests** : `--select true` rend un corpus **byte-identique** à l'entrée ;
composition de deux filtres = filtre conjoint ; les comptes du manifeste
concordent avec la fiche M1 recalculée sur la sortie.

### M3 — ⚖️ Validation contre l'Elo *(le seul juge)*

**Un seul pool généré**, `K` variantes qui ne diffèrent **que par un filtre**,
`K` fits sous la recette championne, `K` portes contre L2LOW.

Cellules de départ, par force de mécanisme décroissante :

| # | variante | mécanisme |
|---|---|---|
| C0 | pool brut | contrôle |
| C1 | `--drop-post-eps` | retire les étiquettes qui parlent d'une autre partie |
| C2 | `--tb-relabel` | remplace du faux par du vrai |
| C3 | sans les parties jetées au ply-cap | teste le biais de sélection |

⚠️ **`C1` et `C3` réduisent le volume.** Une cellule qui gagne en ayant moins de
données confond filtre et volume. **Chaque variante doit être ramenée au même
compte de records** que `C0` par troncature déterministe, ou le résultat n'est
pas interprétable.

**Règle de décision, à figer AVANT de lancer** :
- une cellule « gagne » si son IC95 contre L2LOW exclut zéro ;
- **l'ordre des métriques M1 doit reproduire l'ordre des Elo** — c'est ça qui
  valide l'instrument, pas le gain d'une cellule ;
- si aucune cellule ne gagne **et** que les métriques ne s'ordonnent pas comme
  les Elo, **l'instrument est invalide** et M4 ne se lance pas.

**Coût** : ancres mesurées — fit `2 M` à `gtol 1e-4` ≈ **1h34** ; porte
`n=12 000` ≈ **1h**. Soit **~3h par cellule**, **~12h pour quatre**, hors
génération du pool.

> ⛔ **LE POOL DE M3 DOIT ÊTRE REGÉNÉRÉ EN JSM2 — constat de la revue de la PR
> 417, 5 août.** `corpus_signal_report.py` refuse explicitement un sidecar JSM1
> (`"requires JSM2 game context; JSM1 is insufficient"`), et c'est correct : les
> champs de contexte n'existent nulle part dans un JSM1, il n'y a rien à
> reconstituer. Or **aucun corpus de l'historique n'est en JSM2**, y compris le
> 12 M de `home-1310` (`magic = JSM1`, vérifié sur l'artefact). Et `merge`/`mix`
> **refusent les schémas mélangés** (`"mix inputs must all use the same sidecar
> schema"`), donc la recette 1:1 mémoire + frais casse net dès qu'une moitié est
> en JSM2 — comportement fail-closed voulu, pas un défaut.
> ✅ **Conséquence sur le sizing** : les quatre cellules partent d'un corpus
> **100 % frais en JSM2**, ce que le chemin all-fresh de
> `l3-pure-volume8m-preflight-v1.sh` sait déjà produire. Compter **~3h de
> génération** (12 M à d8, ancre re-mesurée du 4 août : 6 210 pos/min/shard sur
> 12 producteurs) **AVANT** les ~12h de portes. **M3 ≈ 15h**, pas 12.

### M4 — L'usine

Composition d'un corpus par la métrique **validée** en M3, puis génération à
grande échelle. **Ne pas spécifier davantage avant le verdict M3** : le dessin
dépend de ce que M3 aura retenu.

---

## 4. Hors périmètre

- ⛔ Aucun NNUE, aucun réseau, aucun changement de classe de modèle.
- ⛔ Aucune feature neuve, aucune géométrie neuve.
- ⛔ Aucune promotion automatique. Tout bake reste sur go explicite de JFC.
- Les axes **profondeur / movetime / budget-nœuds** touchent la force du joueur,
  donc l'exactitude des étiquettes : ils appartiennent à M4, pas à M3.
- Les axes de **style** (finales à dames, blocages, déséquilibre matériel)
  demandent un classifieur à écrire ; ils appartiennent à M4. ⚠️ La lignée
  `imbalance2` a déjà plafonné sur des spécialistes stratifiés — le registre est
  à relire avant d'y revenir.

---

## 5. Ce que la revue vérifiera

Pour chaque jalon, dans cet ordre :

1. **round-trip écriture→lecture** sur les formats touchés — les clés lues sont
   celles écrites, même compte, même sens ;
2. **byte-identité de ce qui ne doit pas changer** — `t2` de M0 est le test qui
   décide si M0 est sûr ;
3. **fail-closed** : un outil qui ne peut pas mesurer **échoue**, il ne rend pas
   zéro. Un corpus vide, un modèle absent, une tablebase absente doivent tuer le
   job avec un message, jamais produire une fiche silencieusement fausse ;
4. **les conventions de signe** — POV blanc contre POV trait, `{−1,0,+1}` contre
   `{0,0.5,1}` — sont la source d'erreur la plus probable de tout ce chantier ;
5. **aucune mesure ne sort d'un job marqué `failed`** ;
6. les compteurs de la fiche M1 **concordent** avec ceux que le moteur imprime
   déjà (`LABELHYG`, `WDLDIST`) sur le même corpus — deux implémentations qui
   divergent, c'est un bug, pas deux chiffres.
   ⚠️ **CORRECTION DU 5 AOÛT — ce critère était insatisfaisable tel qu'écrit, et
   l'erreur est de moi, pas de l'implémentation.** Les deux comptes n'ont pas le
   même dénominateur : le moteur compte sur les échantillons **candidats**,
   AVANT le rejet des parties plafonnées, la fiche divise par les records
   **présents dans le corpus**, APRÈS. Sur `home-1310` : contamination
   `2 611 826 / 13 226 109 = 19,75 %` côté moteur, contre un rapport sur
   `12 000 000` côté fiche. Pire, sous `--drop-plycap` — la recette courante —
   les parties plafonnées n'émettent AUCUN échantillon, donc la fiche annonce
   `plycap.games = 0` là où le moteur annonce `4,80 %`, et les deux ont raison.
   ✅ **Critère corrigé** : la fiche doit exposer, pour la contamination et le
   ply-cap, **le compte brut ET le dénominateur qu'elle utilise** ; la
   concordance se vérifie alors sur `WDLDIST` (mêmes records des deux côtés) et
   sur les comptes bruts, jamais sur les parts. Une part qui diffère n'est un
   bug que si le dénominateur est le même.

---

## 6. État à l'ouverture du chantier

- `--egdb-audit` : **livré** (`develop`, 4 août), lecture seule, non encore exécuté.
- `--drop-post-eps`, `--tb-relabel` : **existent dans le moteur**, jamais activés
  dans nos générations.
- `l3_bucket_visits.py` : existe, couverture déjà réfutée comme critère.
- Champion de référence pour les portes : **L2LOW**
  `ec47e4b37fc7e95dcb390c0a5eddf207e98c0818c1708636d2df9e85b1d149b4`.
- Recette de fit obligatoire : `--exact-fold` + `--prior-mean <parent>
  --prior-decay 0` + `--lbfgs-gtol 1e-4` + `--l2 1e-5`.
