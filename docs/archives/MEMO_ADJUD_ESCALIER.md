# MINI-MÉMO — FADE ADJUDICATION EN ESCALIER (gaté sur conversion-self mesurée)

> À passer à Claude Code. Branche `develop`, jamais `main`. **Diagnostic (T2→T4)** : la boucle
> compose avec adjud ON (+170), régresse dès OFF (×2). Mécanisme : l'élève (d10, jeune)
> connaît le matériel mais AUCUNE technique de conversion → adjud OFF, les parties
> matériellement gagnées finissent nulles (shuffle/50 coups/ply-cap) → **les labels disent
> « le matériel ne gagne pas » → le fit désapprend T2.** Le biais V^π, majoritaire et dirigé
> contre l'acquis en régime jeune. L'indice était au manifest : nulles 26 %→39 % à
> l'extinction = conversions ratées qui inondent, pas « issues réelles qui prennent le
> relais ». **L'adjud n'est pas un échafaudage honteux : c'est le TB du pauvre — elle reste
> tant que l'élève n'a pas la technique qu'elle simule.**

---

## 0. VÉRIFICATION D'ABORD (lecture dumps T2/T3/T4, zéro run, ~1 h)
- **Taux de conversion ratée** : % de parties où un camp a atteint ≥+3 pions et qui
  finissent NULLES. Prédiction : explose T3/T4 vs T2. + `plycap_rate` par tour.
- Si confirmé → appliquer §1. Sinon → STOP, rediagnostiquer (le fix ne précède pas le fait).

## 1. LE FIX — fade en ESCALIER, jamais interrupteur

### 1.1. Retour immédiat au régime qui compose
- **Rejouer T3 avec adjud ON (4 pions / 24 plies)** — le régime T2, seul où les labels
  disent la vérité au niveau actuel de l'élève. Le champion reste T2 (rien n'a été perdu,
  gate de compose = réversibilité).

### 1.2. L'escalier de resserrement (chaque cran = adjud plus difficile à déclencher)
```
cran 0 : 4 pions / 24 plies   (T2 — départ)
cran 1 : 5 pions / 32 plies
cran 2 : 6 pions / 48 plies
cran 3 : OFF
```
- On ne franchit un cran QUE si le tour courant compose. Un non-compose après franchissement
  → redescendre d'un cran, rejouer.

### 1.3. Le critère de franchissement : CONVERSION-SELF mesurée (éval-driven, pas calendaire)
- **Métrique** (au manifest, chaque tour) : `conv_self` = % de positions où le pilote a
  ≥+3 pions ET convertit en VRAIE victoire (sans adjudication — se mesure sur les parties
  où l'adjud n'a pas tiré, ou par un lot témoin adjud-off de ~2k parties par tour).
- **Règle** : `conv_self ≥ ~70-75 %` au cran courant → franchir le cran suivant.
- C'est l'esprit E1 (fade piloté par l'éval) avec la BONNE variable : celle qui mesure
  exactement ce que l'adjudication remplace.

### 1.4. TB-terminate = l'adjudicateur PARFAIT, en parallèle et permanent
- Partout où la position plonge dans l'EGDB : trancher par la valeur TB exacte (vérité,
  zéro biais). Compteur `egdb-resolved>0` asserté au manifest (leçon +18 phantom).
- Bonus pédagogique : la TB enseigne les VRAIES exceptions (+matériel qui ne gagne PAS —
  forteresses, blocages) que l'adjud matérielle ignore. L'adjud matérielle s'estompe ;
  la TB, jamais.

### 1.5. Couplage aux barreaux du prof (mémo teacher-ladder)
- La conversion s'améliore mécaniquement avec le budget de recherche (la recherche convertit
  ce que l'éval ne sait pas encore). **Chaque montée de barreau (d10→d12→d14→node-cap)
  devrait autoriser ~un cran de fade de plus.** Deux escaliers couplés, tous deux gatés sur
  mesures — ne JAMAIS franchir les deux dans le même tour (attribution).

## 2. GARDE-FOUS
- **Un changement par tour** : cran de fade OU barreau de prof OU volume — jamais deux
  (sinon le compose-gate ne sait plus ce qu'il juge).
- Le manifest porte : `adjud_cran`, `conv_self`, `plycap_rate`, `draw_rate`, `teacher_budget`
  — la courbe finale les annote tous.
- La leçon inverse reste vraie (mémo hygiène §2) : adjudiquer par SCORE d'éval = interdit
  (circularité). Matériel et TB uniquement.
- `draw_rate` qui MONTE à l'extinction d'un cran = signal d'alerte conversion, pas de santé —
  le lire avec `conv_self`, plus jamais seul.

## 3. EN UNE PHRASE
L'adjudication est le TB du pauvre : elle se retire **cran par cran** (4/24 → 5/32 → 6/48 →
OFF), chaque cran gaté sur la **conversion-self mesurée** (≥70-75 %) et couplé aux montées de
barreau du prof — jamais d'interrupteur, jamais deux changements par tour, et la TB tranche
en permanence là où elle voit.
