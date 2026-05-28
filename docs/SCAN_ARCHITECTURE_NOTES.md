# Scan architecture notes — pattern eval design

> Rédigé le 2026-05-25 après lecture de `src/eval.cpp` et `readme.txt` de
> [rhalbersma/scan](https://github.com/rhalbersma/scan) (mirror du moteur
> de Fabien Letouzey). À lire en complément de `PATTERN_ROADMAP.md` et
> `REFERENCES_BIBLIOGRAPHIE.md` axe 1.
>
> **Révisé 2026-05-28** suite à une note de relecture détaillée du code
> Scan (extraits verbatim de `eval.cpp`) + posts forum Letouzey + crédit
> Kingsrow d'Ed Gilbert. Plusieurs sections corrigent des approximations
> de la première version. Les corrections importantes : géométrie pattern
> §3 (4 colonnes décalées × 2 top/bottom = 8 fenêtres) et methodology §5
> (auparavant "UNKNOWN" ; maintenant : **self-play + WDL + régression
> logistique sur features sparses**).
>
> Objet : consolider ce qu'on a appris sur l'archi pattern Scan, qui est
> *très différente* de notre tentative v2. Sert de référence pour les
> expériences diagnostic D1-D3 du plan post-0046 et pour la séquence
> G1-G4 (`docs/SCAN_METHODOLOGY_GAP.md`).

---

## Vue d'ensemble

Scan ≠ « MLP remplacé par patterns ». C'est un **hybride structuré** :

```
eval(pos) = material_count + king_PST + king_mobility + balance
          + pattern_sum                   ← le gros morceau
          + game_phase_interpolation(mg, eg)
```

Les patterns ne **remplacent pas** l'éval, ils s'**ajoutent** à un squelette
material/PST classique. Notre pattern v2 (qui remplace toute l'éval avec
6.25M poids sparse) viole cette hypothèse — et c'est probablement la cause
racine du flat-line 0046.

---

## 1. Encoding par square : base-3 (pas base-5)

Scan encode chaque square en **ternaire** :
- `0` = empty
- `1` = white piece
- `2` = black piece

Ce qui est notable : **Scan ne distingue PAS man vs king dans les
patterns**. Les kings sont traités séparément via un PST dédié (king_pos
features). Conséquence directe :

|  | Scan (base-3) | jass v2 (base-5) |
|---|---|---|
| Squares / pattern | 12 | 8 |
| Buckets / pattern | 3¹² = 531,441 | 5⁸ = 390,625 |
| Patterns | 4 columns × 2 = 8 lookups | 16 blocs |
| Total weights pattern | ~2.1M (int16) | 6.25M (int32) |

**Pourquoi base-3 c'est mieux** : les kings représentent ~5-10% des
positions matures et ~0% des ouvertures. En base-5, les buckets contenant
des kings sont quasi-vides (~1-2 visits sur 1M records pour les buckets
≥2 kings). Résultat : les poids king-rare sont essentiellement non
entraînés. En base-3, on amalgame man+king sous le même symbole "piece",
les buckets sont visités ~5× plus, et la perte de granularité king/man
est compensée par le PST séparé.

---

## 2. Game phase interpolation (mg + eg)

Scan stocke **2 weights par feature** : un pour midgame (`mg`), un pour
endgame (`eg`). La sortie finale interpole :

```c
sc = round((s2.mg() * (Stage_Size - stage) + s2.eg() * stage)
            / (Unit * Stage_Size));
```

Où `stage` est calculé à partir du matériel restant (plus de matériel =
plus tôt dans la partie). C'est important parce que :

- En ouverture, la valeur d'un homme avancé (forme centrale) est ~+50cp.
- En finale, le même homme avancé vaut potentiellement +200cp (proche
  promotion).

Une éval mono-phase doit faire la moyenne → labels bruités → réseau
trivial qui apprend la moyenne. **Notre v2 est mono-phase**, autre
source plausible du `pred=0` observé en 0046.

---

## 3. Géométrie des patterns Scan

D'après `eval.cpp` (extraits clés) :

```cpp
const int Pattern_Size {12};                        // 12 cases par pattern
const int Perm_0[12] { 11,10, 7, 6, 3, 2, 9, 8, 5, 4, 1, 0 };
const int Perm_1[12] {  0, 1, 4, 5, 8, 9, 2, 3, 6, 7,10,11 };

static void indices_column(uint64 b, int& i0, int& i2) {
    uint64 left    = b & 0x0C3061830C1860C3;        // masque 4 files
    uint64 shuffle = (left >> 0) | (left >> 11) | (left >> 22);
    uint64 mask    = (1 << Pattern_Size) - 1;
    i0 = (shuffle >>  0) & mask;                    // top
    i2 = (shuffle >> 26) & mask;                    // bottom
}

static void pattern(Score_2& s2, int var, const Pos& pos) {
    int i0,i1,i2,i3, i4,i5,i6,i7;
    indices_column(pos.wm() >> 0, pos.bm() >> 0, i0, i4);
    indices_column(pos.wm() >> 1, pos.bm() >> 1, i1, i5);
    indices_column(pos.wm() >> 2, pos.bm() >> 2, i2, i6);
    indices_column(pos.wm() >> 3, pos.bm() >> 3, i3, i7);
    s2.add(var +  265720 + i0, +1);                 // 4 sous-tables top
    s2.add(var +  797161 + i1, +1);
    s2.add(var + 1328602 + i2, +1);
    s2.add(var + 1860043 + i3, +1);
    s2.add(var + 1860043 - i4, -1);                 // 4 sous-tables bottom
    s2.add(var + 1328602 - i5, -1);                 // (symétrie par soustraction)
    s2.add(var +  797161 - i6, -1);
    s2.add(var +  265720 - i7, -1);
}
```

Lecture :
- **Pattern_Size = 12 cases** par pattern (pas 12 colonnes).
- **4 décalages de colonnes** `>> 0..3` (chaque shift sélectionne 4 files
  différentes via le masque `0x0C3061830C1860C3`).
- **2 moitiés top/bottom** par décalage, extraites du même mot par
  shuffle (`>> 0` pour top, `>> 26` pour bottom).
- **Total : 4 × 2 = 8 fenêtres** indexant 4 sous-tables (les bottoms
  réutilisent les sous-tables des tops avec signe inversé pour la
  symétrie blanc/noir).
- **Encoding ternaire malin** : `Trits_*` précalcule la conversion
  bitmask 12 bits → index base-3 via `Perm_0/Perm_1`. L'index final
  pour une fenêtre est `Trits[noir] - Trits[blanc]` : sur chaque trit,
  `0-0 = vide`, `+t = blanc`, `-t = noir`. Un seul int encode les 3
  états des 12 cases.

**Pattern_Size = 12 → 3¹² = 531 441 buckets par sous-table** (4
sous-tables × 2 phases MG/EG = ~4.2M poids pattern, à confirmer avec
le P = 2,125,820 dont la moitié est dans les patterns).

**Note importante** : les **kings ne participent PAS** aux patterns
(seul `pos.wm()` et `pos.bm()` sont passés). Kings + matériel +
mobilité = features dédiées hors-pattern (cf §4 du même doc).

Géométrie ≠ nos blocs 4×4. Scan capture des **relations longue
distance verticales** (forward-backward, breakthrough threats), pas
des **motifs locaux 2D**.

---

## 4. Quantization : int16 « simple », pas de scale-aware

Scan stocke chaque poids comme un **int16 raw** (lu via `ml::get_bytes(f, 2)`).
Pas de scale factor, pas de int8 packed. La sortie eval est aussi int16
(centipawn). 2.1M × 2 bytes = 4.2 MB pour le fichier de poids.

Pour comparaison, notre JPAT v2 est 25 MB (int32 = 4 bytes × 6.25M).

---

## 4bis. Features non-pattern (composition exacte)

L'éval Scan n'est PAS que des patterns. `eval()` accumule dans l'ordre
(chaque bloc avance le compteur `var` qui indexe `G_Weight`) :

1. **Matériel** (3 vars) :
   - `nwm - nbm` (différence pions blancs/noirs)
   - présence d'≥1 dame
   - dames supplémentaires
   *(les dames sont TRAITÉES ICI, pas dans les patterns.)*
2. **PST des dames** (`pst`, **50 vars** = `Dense_Size`) : table
   position-case pour les dames uniquement.
3. **Mobilité des dames** (`king_mob`, **2 vars**) : cases sûres vs
   cases attaquées accessibles aux dames.
4. **Équilibre gauche/droite** (`skew`, **1 var**, sauf variante
   Losing).
5. **Patterns** (cf §3) : ~4.2M poids MG/EG combinés, le gros morceau.
6. **Post-traitement** : interpolation MG/EG par `stage`, règle Wolf
   (variante Frisian), atténuation des finales nulles (divise le score
   si peu de matériel).

→ Tout porteur de l'archi doit implémenter au minimum : matériel + PST
dame + mobilité dame + phase de jeu, en plus des patterns. Les pions
sont DANS les patterns ; les dames sont DANS les features dédiées.
C'est exactement le type de "squelette structurel" que notre D1 hybrid
a tenté en cheap (juste man_value + king_value scalaires, sans PST
50-square ni mobilité).

---

## 5. Training methodology — reconstituée

Le code public ne contient PAS le pipeline d'entraînement. Mais
Letouzey l'a décrit aux posts forum (damforum.nl) et Ed Gilbert
(Kingsrow) l'a publiquement répliqué avec crédit à Letouzey/Buro. Le
pipeline est :

1. **Self-play à partir de zéro.** Scan démarre sans connaissance,
   sauf les règles et heuristique `1 dame ≈ 3 pions`. Génère des
   parties contre lui-même.
2. **Labellisation par RÉSULTAT de partie (WDL), PAS par score de
   recherche.** Chaque position extraite reçoit la valeur win/draw/
   loss du résultat final de la partie. **Scan ne labellise JAMAIS
   par une éval depth-N**. Le signal est l'issue réelle. (≈ exactement
   le Cycle 8 master-games de jass, mais sur self-play au lieu de
   parties humaines.)
3. **Régression logistique** sur les features sparses (patterns +
   matériel + PST + mobilité). Poids initialisés aléatoirement. Output =
   somme pondérée des features actives → sigmoïde. Gradient descent
   sur log-loss WDL. C'est un **GLM (= GLEM de Buro, Logistello)**,
   pas un réseau profond. La connaissance est entièrement dans la
   table de poids.
4. **Itération.** Nouvel évaluateur rejoue, meilleures parties,
   relabel WDL, retrain. Quelques cycles.

**Enseignements directs pour jass** :
- Cible *n'a jamais payé de recherche profonde* pour labelliser →
  conforte priorité "WDL / master games" déjà observée en Cycle 8 et
  v6/v7.
- Représentation **linéaire sur patterns** → toute la force est dans
  le *feature engineering*, pas dans la profondeur du modèle.
- Inférence quasi gratuite (lookups + additions) → Scan cherche
  profond très vite ; un MLP même incrémental ne rivalisera pas sur
  ce poste.

**Conséquence sur notre plan G** : notre G2 (job 0052) distille
score = `v7.evaluate(pos)`. C'est une approche supervised score-based,
qui n'a pas d'équivalent direct chez Scan. Si G2 plateau < 0.40,
ajouter une variante **G2-WDL** (loss = pure BCE sur WDL, no score
MSE, sur le même dataset 1M + master games) qui réplique exactement
la méthodo Scan. À documenter dans `SCAN_METHODOLOGY_GAP.md`.

**Caveat fiabilité** : la *structure* de l'éval (§3, §4bis) est tirée
du code GPL, fait foi. La *méthode* (§5) est reconstituée de posts
forum + réplication Kingsrow, pas d'un papier primaire. Les détails
exacts du fit (learning rate, nombre d'itérations self-play,
régularisation, ratio self-play vs corpus externe) ne sont **pas
publics** et devront être ré-explorés empiriquement.

---

## 6. Implications pour jass

Lecture honnête de pourquoi 0046 a flat-liné : on a essayé de remplacer
toute l'éval par un MLP-équivalent en patterns sparse, sans le squelette
material/PST que Scan attache aux patterns. Le réseau a optimisé vers
la prédiction triviale (mean = 0) parce que c'est ce qu'il pouvait faire
de mieux sans signal structurel.

Trois directions diagnostic possibles, par ordre cheap → cher :

### D3 — Pattern v2 sur dataset quiet-only 0043

Hypothèse : le data 0010 (1M depth-20 sans filtre) avait trop de positions
tactiques, bruitait le signal score. Tester v2 sur les 200K quiet-only
de 0043 (mêmes flags 0046 sinon). **Coût : ~€0.5, 1h dev**.

Decision : si rate vs v5 d10 reste 0, **data quality n'est pas la racine**
→ confirme que c'est l'archi/le squelette.

### D2 — Pattern v2 base-3 (drop king distinction)

Hypothèse : 6.25M poids à 40 visits/bucket moyens, mais bcp moins pour
les buckets king-heavy. Passer en base-3 = ×4 plus dense, et c'est ce
que Scan fait.

Coût : ~€1, ~2-3h dev (changer l'encoding pattern_indices + retrain).

Decision : si rate vs v5 d10 saute à ≥0.10, **sparsité était le bottleneck**.
Si ça reste 0, c'est le manque de squelette structurel.

### D1 — Hybrid pattern + material/PST

Hypothèse : les patterns ont besoin du squelette pour ne pas avoir à
apprendre la valeur absolue des pièces. Ajouter material_count(W-B) +
king_count(W-B) comme features supplémentaires (juste 2 paramètres en
plus !), avec patterns comme correction additive.

Coût : ~€2, ~4-6h dev (changer `PatternNetwork::evaluate` côté C++ pour
ajouter les features structurelles + adapter trainer).

Decision : si rate vs v5 d10 saute à ≥0.20, **archi pattern est viable
en hybride**. C'est le résultat le plus intéressant car ça déverrouille
Phase 2 self-play sur une base saine.

---

## Annexe — sources

**Code Scan** (fait foi pour structure §3, §4, §4bis) :
- `src/eval.cpp` : patterns + Trits + composition de la sortie
- `src/eval.hpp` : interface minimale (`eval_init()` + `eval(pos)`)
- `src/common.cpp` (`Square_Sparse`) : layout case ↔ bit, **différent
  probable de jass**, à mapper si porting des masques `0x0C30...`
- `src/pos.hpp` : `stage`, `phase` pour interpolation MG/EG
- `readme.txt` : mention "8 overlapping rectangles"

Code Scan : <https://github.com/rhalbersma/scan>, GPL v3, ~2000 LOC
évalue + search confondus.

**Sources pour méthodo §5** (reconstituée, pas papier primaire) :
- Posts forum Letouzey, `damforum.nl` (threads "Scan" et "NNUE") —
  description du self-play + WDL + logistique
- Ed Gilbert (Kingsrow), *Machine Learning Comes To Kingsrow*, The
  Checker Maven — réplication du même pipeline avec crédit explicite
  à Letouzey + Buro
- Buro, *Improving Heuristic Mini-Max Search by Supervised Learning*
  (AI 2002) — fondation théorique (GLEM/Logistello) en éval Othello,
  réutilisée pour Scan

**Sources non lues / non accessibles depuis cette session** :
- Lidraughts blog post sur Scan (403)
- damforum thread NNUE Bert Tuyt (403)
- Detail exact du trainer Letouzey (non publié)
