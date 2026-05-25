# Scan architecture notes — pattern eval design

> Rédigé le 2026-05-25 après lecture de `src/eval.cpp` et `readme.txt` de
> [rhalbersma/scan](https://github.com/rhalbersma/scan) (mirror du moteur
> de Fabien Letouzey). À lire en complément de `PATTERN_ROADMAP.md` et
> `REFERENCES_BIBLIOGRAPHIE.md` axe 1.
>
> Objet : consolider ce qu'on a appris sur l'archi pattern Scan, qui est
> *très différente* de notre tentative v2. Sert de référence pour les
> expériences diagnostic D1-D3 du plan post-0046.

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

D'après `readme.txt` : *"8 overlapping rectangles (2-26, 3-27, ..., 25-49)"*.
D'après `eval.cpp` : `Pattern_Size = 12` et 4 décalages `>> 0,1,2,3`.

Reconstruction probable :
- Les 50 squares dark de la dame 10×10 sont organisés en 10 lignes × 5
  colonnes (1 case noire sur 2).
- Un "rectangle" est une fenêtre verticale couvrant 5 lignes × 5
  colonnes = 25 squares dark, soit la moitié du board.
- Le pattern de 12 squares est extrait via `Perm_0` / `Perm_1` qui
  réordonnent ces squares pour qu'un même motif (ex. centre-ligne occupé,
  flanc vide) ait le même index ternaire dans toutes les fenêtres.

Géométrie ≠ nos blocs 4×4. Scan capture des **relations longue distance
verticales** (forward-backward), pas des **motifs locaux 2D**.

---

## 4. Quantization : int16 « simple », pas de scale-aware

Scan stocke chaque poids comme un **int16 raw** (lu via `ml::get_bytes(f, 2)`).
Pas de scale factor, pas de int8 packed. La sortie eval est aussi int16
(centipawn). 2.1M × 2 bytes = 4.2 MB pour le fichier de poids.

Pour comparaison, notre JPAT v2 est 25 MB (int32 = 4 bytes × 6.25M).

---

## 5. Training methodology — UNKNOWN

Le code public ne contient PAS le pipeline d'entraînement. Les poids
arrivent comme un blob binaire dans `data/eval`. Letouzey n'a pas publié
le trainer. Hypothèses sur ce qu'il utilise :

- **Régression linéaire par moindres carrés** (Buro GLEM style) sur des
  millions de positions labellisées par minimax shallow (ex. self-play
  depth 4-6). Convergence en quelques itérations parce que la loss est
  convexe.
- **Itération TD-leaf** : self-play → corriger les poids vers la valeur
  observée à la prochaine PV-leaf. Sur N itérations.
- **Combinaison** : régression initiale + raffinement TD-leaf.

Ce qu'on sait empiriquement (cf. [4] Wiering et al.) : les méthodes TD
sur les dames internationales atteignent un niveau correct en quelques
heures avec databases de parties. Donc l'investissement training réel
est modeste — le coût est dans la définition des features, pas la durée
d'entraînement.

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

## Annexe — fichiers Scan lus

- `src/eval.cpp` : 100% des patterns + composition de la sortie
- `src/eval.hpp` : interface minimale (juste `eval_init()` + `eval(pos)`)
- `readme.txt` : mention "8 overlapping rectangles", pas plus de detail
- `src/var.cpp`, `src/main.cpp`, training pipeline — non lus pour l'instant

**Sources non accessibles** (403) : Lidraughts blog post sur Scan,
damforum thread NNUE Bert Tuyt. Si re-tentés via gh CLI ou archive.org
pourraient ajouter de l'info sur la méthodo training réelle.

Code Scan : <https://github.com/rhalbersma/scan>, GPL v3, lisible et
relativement court (~2000 LOC évalue + search confondus).
