# MÉMO CONSOLIDÉ — 2026-07-12 : curriculum de la boucle from-scratch

> Mémo JFC (verbatim consolidé). Branche `develop`, jamais `main`. Complète (ne remplace pas) :
> MEMO_TEACHER_LADDER, MEMO_ADJUD_ESCALIER, MEMO_SELF_MMTO_FINISHER, MEMO_ADJUD_PREDICATS.
> **Cadre gravé** : la boucle = **AMPLIFICATEUR (search) × ORACLE (ce qui est vrai)**. La recherche
> amplifie, elle ne crée pas ; le savoir n'entre QUE par les labels ; prédicats/adjud/TB = le
> **CURRICULUM** de l'école from-scratch, pas de l'hygiène.

## A. VERDICT NOTATION P2/P3/P4 — REVERSER EN VETOS, jeter les verdicts
Harnais TB : conditions matérielles ⇒ DRAW plafonnent à **78,6%** (`def_bare_king & absnet≤3`),
72,5% (`def_has_king & npieces≤5`), 59,4% (`def_has_king`). Seuil verdict = 99,9% ⟹ **REJET comme
verdicts** (un DRAW faux 1/5 = le poison anti-savoir T3/T4). **MAIS lecture inversée = vetos
excellents** : 72,5% de nulles ⇒ l'adjud matérielle se tromperait ~72% si elle tirait WIN là (coût
d'erreur veto = NUL, la partie continue).
1. **Veto V1** : `if defender_has_king: adjud_material NE TIRE PAS` (hors-TB). Admission veto =
   **recall de la zone dangereuse** (pas 99,9% précision). Mesuré : 0682 → `def_has_king` couvre 69%.
2. **Périmètre gravé** : `npieces ≤ N_TB` = territoire TB (la TB adjudique déjà exactement) — vetos/prédicats n'agissent QU'au-delà.
3. **Leçon** : les classes MATÉRIELLES ne font pas 99,9% en finale-à-dames (vérité géométrique = raison d'être des TB). Tout verdict DRAW futur = STRUCTUREL (mobilité/blocage, zéro coup non-suicidaire 2 camps), jamais des comptes.
4. **P1 (percée) RESTE À NOTER** — course géométrique, verdict WIN hors-TB, la plus prometteuse. Décide si le programme a un étage « verdicts » ou seulement « vetos ». **(→ job 0683)**

## B. BOOTSTRAP TB-DIRECT (cible = le mur de conversion T3/T4)
La TB = labels PARFAITS et PURS (règles du jeu seules, zéro Scan/humain).
- **Contingent TB-direct** 10-20% du corpus/tour (~25-50k/256k) : finales étiquetées valeur TB exacte,
  (a) trajectoires du tour plongeant dans la TB (on-policy, prioritaire), (b) complément uniforme-TB. `label_src=TB`.
- **Mécanisme (à vérifier)** : éval apprend les vraies valeurs de finale → conversion ↑ → conv_self ↑ → le fade adjud accélère. TB-direct = ACCÉLÉRANT de l'escalier.
- **Garde-fous** : contingent modeste (anchor protège), UN changement de tour, jugé compose-gate + pente conv_self. APRÈS confirmation escalier.
- ❌ Porte eval(0) artisanale (trop tard, T2≈ça). ❌ Données externes en seed (casse la pureté ; = lignée mainline gen2-mmto).

## C. INSTRUMENTATION (pendant que les tours tournent)
1. **`conv_self` au manifest** : % positions ≥+3 pions converties en VRAIE victoire, via lot témoin adjud-off ~2k parties/tour. Sans ça le fade repart au calendrier.
2. **Thermomètre par motifs** (18 détecteurs dilf) : set d'éval FIXE (fixtures dilf) → benchmark par champion → courbe d'acquisition par motif. Instrument, jamais signal.
3. Watchlist : fix `go movetime` overshoot-endgame (les JUGES en dépendent) ; re-embed gen2-mmto binaire (avant déploiement) ; E2 drop-post-eps = 1er suspect si saturation précoce après fix adjud.

## D. SOURCES EXTERNES (par rôle)
| source | rôle | prio | garde-fou |
|---|---|---|---|
| **TB étendue** (réf. KingsRow EGDB 8 pièces) | oracle exact (labels+harnais+périmètre vetos) | 1 chantier | compute lourd, gain définitif |
| **Toernooibase Dammen** (parties OTB élite GMI) | prof de préférences ÉLITE (played-moves) | 2 chantier | JAMAIS les WDL ; accès/format/licence |
| **Compositions/problémisme** (FMJD) | QA-set prédicats + benchmark + graines | 3 | re-valider moteur ; instrument, pas corpus train |
| **KingsRow moteur** | dual-oracle QA (accord Scan×KingsRow) | 4 | filtre de vérité, pas distillation |
| **Parties annotées** (`!`/`?` dilf) | qualité de coup graduée | 5 | volume modeste |
| **Graines d'ouverture** (Keller/Roozenburg) | couverture structures jouables-humain | 6 | complément |
| ❌ lidraughts tout-venant · WDL humains · prose non-exécutable | — | — | morts/interdits |

Action D immédiate (recherche) : vérifier accès/format/licence Toernooibase + compositions → rapport court.

## E. ORDRE D'EXÉCUTION
```
PARALLÈLE  : C1 conv_self + lot témoin ; C2 thermomètre motifs ; A1 veto V1 (def_has_king) recall+branché ; A4 P1 noté (0683)
POST-escalier : escalier adjud (conv_self-gaté) → re-composer
TOUR SUIVANT  : B contingent TB-direct (1 changement, gate compose + pente conv_self)
PUIS          : teacher-ladder quand un barreau sature ; prédicats admis 1 à 1 ; self-MMTO finisseur
FOND          : D (TB étendue continu ; Toernooibase = rapport d'accès d'abord)
```

## F. EN UNE PHRASE
Verdicts matériels morts au harnais (78,6%<99,9%) mais renaissent en **vetos** (coût nul) ; **P1 reste
l'espoir verdict** ; le **contingent TB-direct** est l'accélérant pur de l'escalier de conversion ;
`conv_self` + thermomètre s'instrumentent en parallèle ; sources externes chacune par son rôle, jamais en vrac.

---
## ÉTAT (Claude, 2026-07-12)
- A4 : **P1 percée** codé (`adjud/predicates.py`) + **job 0683** (notation vs TB) → décide l'étage verdicts.
- A1 : `def_has_king` veto déjà mesuré (0682 : recall 69% des nulles). Branchement gen = étape escalier (jass adjud, post-escalier).
- C/B/D : à venir (C1/C2 instrumentation, B TB-direct, D rapport d'accès sources).
