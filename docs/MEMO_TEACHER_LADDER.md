# MÉMO v2 — BOUCLE FROM-SCRATCH : L'ÉCHELLE DU PROFESSEUR (teacher-ladder) + politique de VOLUME
> À passer à Claude Code. Branche `develop`, jamais `main`. **Contexte** : la boucle
> auto-apprenante compose (T0 1056-0-0 ; T2 +170 hors-IC ; chain `0674` T4+). Ce mémo ajoute
> le mécanisme d'échelle qui empêche le plateau prématuré : **quand les tours cessent de
> composer à profondeur fixe, on ne conclut pas « plateau » — on monte le professeur.**
> **v2 (décision actée avec Claude Code)** : le haut de rampe passe en **BUDGET-NŒUDS
> (`--play-max-nodes`), PAS en movetime** — déterminisme, reproductibilité, immunité au bug
> overshoot-endgame. Et réponse à la question volume : **constant par défaut, montée
> déclenchée par signaux nommés** (§2).
---
## 0. LE MÉCANISME (cadre 0621 — pourquoi l'échelle est nécessaire)
Le professeur de la boucle = **l'amplification de recherche** : l'écart entre ce que
`αβ_budget(éval)` choisit et ce que l'éval statique choisit (mesuré : 0.503 statique vs
0.686 à-travers-d5 sur gen2). **Chaque tour consomme cet écart au budget courant** — le fit
compresse le savoir-de-recherche dans l'éval, jusqu'à ce que ce budget n'ait plus rien à
enseigner. Ce n'est PAS un plateau de la classe : c'est l'épuisement du prof courant.
**Monter le budget re-crée l'écart enseignable.** C'est la rampe que Scan a nécessairement
gravie (thèse JFC validée par T0-T4) : pas N tours à budget fixe — un budget de gen qui
grandit avec l'élève.
## 1. L'ÉCHELLE (v2 : profondeur fixe en bas, budget-nœuds en haut)
### Pourquoi budget-nœuds et pas movetime (décision gravée)
1. **Le prof doit être une fonction, pas une variable aléatoire** : un prof-movetime varie
   avec la charge box, le NPS positionnel, et le bug overshoot-endgame (2-3.5× = un prof
   incontrôlément 2× plus fort en finale). Un prof-node-cap enseigne exactement pareil à
   charge nulle ou pleine — chaque barreau est comparable au précédent.
2. **Déterminisme = rejouabilité bit-à-bit** d'un gen (la campagne a perdu assez de verdicts
   sur des artefacts d'infra).
3. **Le movetime n'a aucune vertu pédagogique propre** : la force du prof = le budget de
   calcul par décision ; le node-cap EST le budget, sans le proxy temps. Et à budget égal,
   le node-cap est un prof plus intelligent que d-fixe (l'iterative deepening va plus
   profond dans les positions étroites, moins dans les larges).
⚠ Le fix du bug movetime-endgame RESTE dans la file — pas pour la boucle, pour les JUGES
(A/B mt0.2/0.3 et matrice vs Scan restent en movetime ; le node-cap sauve le gen, pas le juge).
### Barreaux
```
R1 : gen d10                    (actuel — barreau de départ)
R2 : gen d12                    (profondeur fixe)
R3 : gen d14                    (profondeur fixe)
R4+ : gen node-cap croissant    N1 = médiane_nodes(d14) ×2
                                N2 = ×4 · N3 = ×8 · (×16 si la courbe le mérite)
```
**Calibration R4+ (obligatoire, pas d'équivalence théorique)** : mesurer `nodes/coup` MÉDIAN
sur un échantillon de parties d14 (le manifest l'émet), poser les barreaux en multiples ×2 —
échelle log propre → l'axe de la courbe finale devient log-budget et l'asymptote se lit.
### Règle d'unicité (nouvelle, v2)
**Un seul régime de prof par tour** : jamais de mélange d-fixe/node-cap (ni deux caps) dans
un même corpus — sinon deux profs de niveaux différents et le compose-gate ne mesure plus
rien. Le manifest porte `teacher_mode` + `teacher_budget` par shard ; **le gate ASSERTE leur
unicité par tour**.
### Déclencheur de montée (éval-driven, pas calendaire — cohérent avec le fade E1)
- **1 tour sans compose hors-IC au barreau courant → MONTER d'un barreau** (ce n'est PAS un
  strike E3 — c'est le signal « le prof courant est absorbé »).
- Après montée : le tour suivant repart avec le nouveau prof. S'il compose → on reste sur ce
  barreau jusqu'au prochain épuisement.
- **E3 v2 (clôture, pré-engagé)** : **2 tours consécutifs sans compose AU DERNIER BARREAU**
  = plateau réel de la classe → STOP, bilan. **Cap global dur : 12 tours** toutes échelles
  confondues (protection budget).
- Option agressive (si JFC veut accélérer) : monter aussi après **2 composes consécutifs
  faibles** (< +40) — ne pas attendre l'épuisement complet d'un barreau qui rapporte peu.
### À chaque montée de barreau (checklist)
1. Vérifier **adjud=OFF** (E1 terminé bien avant R2 ; sinon investiguer le fade).
2. **Contrôle complet** sur le champion du barreau clos : généraliste movetime + **d9-vs-Scan**
   (thermomètre externe — ne pilote pas, mais DATE chaque barreau pour la courbe finale).
   Seul moment où on paie le contrôle complet — pas à chaque tour.
3. Re-calibrer le débit réel (positions/h chute avec le budget — ETA chiffrée, check-list
   12 points, validation JFC).
4. (R4+) Mesurer la médiane nodes(d14) si pas déjà fait ; graver N1/N2/N3 au manifest.
## 2. POLITIQUE DE VOLUME (la réponse à la question)
**Défaut : CONSTANT à 256k/tour.** Raisons : (a) le levier de la boucle est la **qualité du
prof** (dose-réponse ×10 démontré), pas la masse — le barreau EST la montée en qualité ;
(b) 256k suffit au fit ancré (T2 +170 le prouve) ; (c) le wall-clock/tour explose déjà avec
le budget — gonfler le volume en même temps tuerait la cadence d'itération, qui est la vraie
richesse de la boucle.
**Deux déclencheurs NOMMÉS pour monter le volume (+50 %, une fois chacun max par barreau)** :
1. **Famine du fit** : compose faiblit ET `|Δw|` minuscule ET logloss holdout figée → les
   données n'arrivent plus à « dévisser » l'anchor → +50 % volume AVANT de monter de barreau
   (moins cher qu'un barreau).
2. **Chute de couverture** : `cov20` < ~70 % (une éval forte fait moins de blunders → le
   self-play se rétrécit) → +50 % volume ET re-vérifier l'hypothèse E2 (eps/couverture —
   premier suspect pré-enregistré ; en régime fort, rallonger eps peut valoir plus que du
   volume).
**Jamais** : baisser sous 256k aux barreaux profonds « pour tenir le wall-clock » — le fit
WDL a besoin de sa masse ; on paie le temps, pas la masse (§3).
**Knob de réserve — anchor** : si le fit ne bouge plus malgré volume ↑ (|Δw|→0, compose
neutre), tester **anchor 0.05 → 0.03** sur UN tour (drift autorisé plus grand). Rollback si
régression (leçon 0645 : trop lâche détruit).
## 3. ÉCONOMIE (à re-calibrer sur box réelle — ordres de grandeur, EBF ~1.6)
| barreau | coût/position vs d10 | 256k ≈ wall-clock | tours/nuit |
|---|---|---|---|
| R1 d10 | ×1 | ~2-3 h | 3-4 |
| R2 d12 | ~×2.5 | ~5-7 h | 1-2 |
| R3 d14 | ~×6 | ~12-16 h | 1 |
| R4 N1 (×2 d14) | ~×12 | ~1 j | 1/jour |
| R5 N2 (×4 d14) | ~×24 | ~2 j | — |
⟹ la boucle passe naturellement de « beaucoup de tours pas chers » à « peu de tours riches ».
Attendu et sain — c'est la rampe de Scan. Micro-calibrer AVANT chaque barreau.
## 4. CE QUI NE CHANGE PAS (acquis de la chaîne 0674)
Gen 100 % neuve on-policy par tour (champion(t−1) self-play) · fit **ancré** champion(t−1)
(`wdl_finetune --anchor 0.05`, capitalisation, jamais refit-zéro) · gate compose d9 IC ±25
par tour · quiet-only · eps décroissant + drop-post-eps (E2 : hypothèse surveillée) ·
`--play-max-nodes` safety (désormais AUSSI l'instrument des barreaux R4+) · manifest
flag⇒effet · holdout par partie · champions committés par tour (réversible).
## 5. LIVRABLE FINAL DE LA BOUCLE (quel que soit le verdict)
**La courbe complète** : Elo(tour) champion-vs-champion + d9-vs-Scan(barreau) — axe
log-budget, annotée des montées de barreau, des +volume, du fade adjud. La pièce maîtresse :
où le self-play pur atterrit vs gen1 (point WDL-Scan-outcome) et vs gen2-mmto (point
Scan-enseigné) — la réponse expérimentale à « comment Scan a fait », et la section 4.6 du
papier.
## 6. EN UNE PHRASE
Le prof de la boucle est l'amplification de recherche et chaque tour la consomme : quand un
barreau s'épuise (1 non-compose), on **monte le prof** — d10→d12→d14 puis **budget-nœuds
croissant ×2/×4/×8 (déterministe, rejouable, immunisé au bug movetime-endgame ; un seul
régime par tour, asserté au manifest)** — au lieu de conclure au plateau ; le **volume reste
constant à 256k** (la qualité du prof est le levier) avec deux déclencheurs nommés (+50 % :
famine du fit, chute de couverture) ; la clôture n'est prononcée que sur **2 non-composes au
dernier barreau** — et la courbe complète, en log-budget, est la réponse expérimentale à la
question qui a lancé tout ça.
