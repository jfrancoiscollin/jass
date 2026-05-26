# Scan methodology gap — ce qui nous sépare, et comment fermer le gap itérativement

> Rédigé le 2026-05-26 après les 4 tentatives D0-D2 sur l'archi pattern
> (jobs 0046/0047/0048/0049, tous flat à 0/54 vs v5 d10). Synthèse
> honnête de POURQUOI notre supervised cheap ne reproduit pas Scan, et
> proposition d'un plan itératif pour fermer le gap progressivement.
>
> À lire avec `docs/SCAN_ARCHITECTURE_NOTES.md` (analyse statique du
> code Scan) et `docs/SESSION_LOG_2026_05.md` (verdicts empiriques).

---

## 1. Ce qu'on sait avec certitude

### 1.1 Scan : ce qu'on a observé dans son code

- ~2.1M poids pattern (8 patterns × 3^12 buckets × 2 phases mg/eg, int16)
- ~50 poids structurels (material count, king PST, mobility, balance)
- Encoding base-3 dans les patterns (no king distinction inside patterns)
- 2 phases (mg/eg) interpolées par game_stage
- Géométrie : 8 colonnes verticales × 12 squares (pas 4×4 blocks)
- Fichier weights binaire chargé au startup, training NON inclus dans
  le repo public

### 1.2 jass : ce qu'on a essayé empiriquement

| Setup | Total poids | Phase split | Skeleton | Base | vs v5 d10 |
|---|---|---|---|---|---|
| 0046 pure pattern | 6.25M | non | non | 5 | 0/54 |
| 0047 + quiet data | 6.25M | non | non | 5 | 0/54 |
| 0048 + skeleton (D1) | 6.25M | non | mat+king | 5 | 0/54 (mais 6/54 d6) |
| 0049 + base-3 (D2) | 105K | non | mat+king | 3 | 0/54 |

**Toutes les variantes supervised plafonnent au même endroit** : aucune
ne capte de signal positionnel exploitable, le trainer optimise vers le
mean trivial sur des labels score bruités.

### 1.3 Diagnostic empirique convergent

Sur D1 et D2, `man_value` et `king_value` convergent vers EXACTEMENT
30.7 / 228.2 cp (vs init 100 / 300). Ce n'est pas un bug : c'est ce
que la loss MSE *préfère* sur depth20-1M, parce que les scores sont
trop bruités pour justifier de plus grosses valeurs structurelles.
Adam trouve correctement ce minimum local. **C'est la formulation
supervised cheap qui est inadéquate, pas le code**.

---

## 2. Le gap : 5 choses que Scan fait et qu'on ne fait pas

Par ordre de probable impact croissant.

### 2.1 Phase split mg/eg (gap modéré)

Scan stocke 2 weights par feature, interpolés par game_stage. Sans ce
split, un même pattern doit représenter sa valeur à la fois en
ouverture (homme avancé ~50cp) et en finale (~200cp), donc le réseau
apprend la moyenne et perd les deux signaux.

**Effort pour combler** : ~6h dev (doubler les tables + ajouter
game_stage extraction). C'est du travail mécanique.

### 2.2 Géométrie pattern (gap modéré)

Notre v2 = 16 blocs 4×4. Scan = 8 colonnes verticales de 12 squares.
Les colonnes capturent des relations longue-distance (forward push,
breakthrough threats) que les blocs 4×4 ratent. C'est un choix de
design empiriquement validé chez Letouzey.

**Effort pour combler** : ~3-4h dev (nouveau pattern set "v3-scan",
+ tests parity). Le code est paramétré sur les listes de squares ;
il suffit de définir les bonnes listes.

### 2.3 Feature engineering complet (gap large)

Scan ajoute : material count, king PST par square, mobility (safe vs
denied moves), balance L/R. Notre D1 hybrid n'a que material + king
count (2 features). Le PST seul ajoute ~50 features (1 weight × 50
squares × 2 phases × 2 colors = 200 weights).

**Effort pour combler** : ~1-2 jours dev (extraire features depuis
bitboards, étendre PatternNetwork et trainer, JPAT v4).

### 2.4 Méthode de training (gap dominant probable)

C'est l'écart le plus fondamental ET le plus opaque. Scan utilise
quasi-certainement (basé sur Buro GLEM + littérature dames) :

- **Régression linéaire full-batch** (pas Adam minibatch) sur la loss
  convexe. L-BFGS converge en dizaines d'itérations vs des époques
  d'Adam qui osciller. Notre `train_pattern.py` utilise Adam parce
  que c'est le default — mais notre loss est *exactement* convexe
  (linear in pattern weights), donc on devrait L-BFGS.
- **TD-leaf** ou **TD-Lambda** : self-play, propager la valeur réelle
  observée depuis le PV-leaf vers les positions de la racine. Cela
  régularise massivement les labels bruités du depth-20-supervised.
  Buro l'utilise pour Logistello, Wiering et al. pour les dames intl.
- **Multi-pass refinement** : entraîner v1, l'utiliser pour jouer,
  régénérer data, entraîner v2, …, sur N=10-100 itérations. C'est
  ce qu'on appelait "Phase 2 self-play" dans `PATTERN_ROADMAP.md`.

**Effort pour combler** : variable — L-BFGS = ~2h dev, TD-leaf =
~1-2 semaines dev + 10 itérations compute, multi-pass = idem.

### 2.5 Décennies de tuning + recipes propriétaires (gap fondamental)

Letouzey a sorti la 1ère version de Scan en 2008. Itéré pendant
~15 ans. Les heuristiques de feature design, les pré-traitements
sur le dataset, les schedules de training, sont des artisanat
accumulé qu'on ne peut pas répliquer en lisant le code (qui ne
montre que l'inférence).

**Effort pour combler** : impossible sans soit décompiler le pipeline
Scan (pas disponible), soit réinventer indépendamment via plusieurs
mois de R&D dédiée.

---

## 3. Plan itératif de fermeture du gap

Idée centrale : on attaque les écarts dans l'ordre **certitude
d'impact décroissante** × **coût croissant**. À chaque étape, decision
gate clair : si l'étape ne bouge pas l'aiguille, on arrête là plutôt
que d'enchaîner les pertes.

### Étape G1 — L-BFGS sur la loss convexe (~€0.5, ~4h dev)

**Pourquoi en premier** : c'est gratuit ET ça teste l'hypothèse la
plus fondamentale (notre Adam est-il en cause ?). La loss
`λ·MSE + (1-λ)·BCE` sur des poids linéaires (pattern lookup =
embedding) est globalement convexe. L-BFGS converge en dizaines
d'itérations sur l'ENTIER du dataset (full-batch), pas en époques
minibatch oscillantes.

Implementation : remplacer Adam par `torch.optim.LBFGS` dans
`train_pattern.py`, retirer warmup/cosine (inadaptés à LBFGS), batch
= full dataset. ~50 lignes Python.

**Decision gate G1** :
- rate vs v5 d10 ≥ 0.10 sur D1 hybrid avec L-BFGS → **Adam était en
  cause, continuer avec L-BFGS pour les étapes suivantes**.
- < 0.05 → Adam n'était pas le problème, pivot vers G2.

### Étape G2 — Knowledge distillation depuis v6 (~€1, ~6h dev)

**Pourquoi** : si patterns peuvent en principe imiter une eval qui
marche, c'est un signal fort que l'archi est viable, juste que les
labels score depth-20 sont trop bruités. La distillation utilise les
*sorties de v6 sur ces mêmes positions* comme labels (cibles plus
propres), pas le score search.

Implementation : tool `tools/generate_v6_targets.py` qui passe le
1M dataset à travers v6 et output un dataset avec score = v6.evaluate(pos).
Puis train_pattern.py classique sur ce nouveau dataset.

**Decision gate G2** :
- rate vs v6 d10 ≥ 0.40 (distillation devrait facile imiter le master) →
  **archi pattern peut représenter une eval ; bug actuel = labels
  bruités** ; pivot vers G3 ou G4.
- < 0.20 → l'archi pattern ne peut pas représenter l'eval v6 ;
  prouve une limite fondamentale ; abandon honnête.

### Étape G3 — Feature engineering complet (~€2, ~2j dev)

**Pourquoi** : ajouter king PST + mobility + balance + phase split.
Aligne la spécification sur Scan exactement. Combiné avec G1 (L-BFGS)
et/ou G2 (distillation) si ceux-ci ont décollé.

Implementation : JPAT v4 = v3 + king_PST[50×2 phases] + mobility[2
phases] + balance[1 phase only?] + game_stage threshold. PatternNetwork
étend evaluate(), trainer étend les modèles.

**Decision gate G3** :
- rate vs v5 d10 ≥ 0.30 → **archi viable**, on a la baseline pour
  Phase 2 self-play.
- < 0.15 → feature engineering n'est pas le facteur dominant ; pivot
  G4 ou abandon.

### Étape G4 — TD-leaf self-play (~€20-40, ~3-4 semaines)

C'est l'ancienne "Phase 2" du PATTERN_ROADMAP. Coût élevé et risque
réel d'échec sur 3-4 semaines. À ne lancer **que si G1+G2+G3 ont
montré que l'archi a un signal exploitable**.

Implementation : nouveau mode C++ `--self-play-pattern N out.jnnw`
qui joue N games pattern-vs-pattern, label = WDL observé + score
intermédiaire (TD-leaf). Loop script `0050+` qui itère 10-20 fois.

**Decision gate G4** : si après 10 itérations le rate ne dépasse pas
0.40 vs v6, **abandon honnête de l'axe pattern pour cette ère du
projet**. Le coût accumulé G1+G2+G3+G4 serait ~€30-50 et 1 mois wall,
ce qui mérite cette borne stricte.

### Étape G5 — Réplication Scan exacte (~€?, ~3-6 mois)

Hors scope pratique. Implique de répliquer 15 ans d'itérations de
Letouzey. Listée pour mémoire ; n'a pas de plan concret. Seulement
envisageable si on identifie un volontaire dédié + budget compute
sur plusieurs mois.

---

## 4. Recommandation finale honnête

**Court terme (cette session ou suivante)** :

- v7 (job 0050) sur axe data — gains éprouvés, ROI clair.
- Si excédent d'envie/budget, **G1 (L-BFGS)** sur D1 pour vérifier
  l'hypothèse Adam. ~€0.5, peut-être décisif.

**Moyen terme (si on relance pattern axis)** :

- G1 → G2 → G3 dans cet ordre. À chaque gate, accepter d'arrêter.
- Budget total pessimiste : ~€5 + ~1 semaine dev.
- ROI si G3 réussit : avoir une baseline pattern viable pour Phase 2.

**Long terme** :

- G4 (TD-leaf self-play) seulement avec G3 validé.
- G5 ignoré sauf décision explicite.

L'**erreur à éviter** : refaire D2/D3 variants sans avoir testé G1.
La piste "supervised pur sur archi pattern" est exhaustée par les 4
expériences. Le gap suivant est méthodologique, pas paramétrique.
