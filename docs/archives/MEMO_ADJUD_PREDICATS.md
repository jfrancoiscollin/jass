# MÉMO — PRÉDICATS D'ADJUDICATION : composés depuis `dilf/pedagogy/features`, notés par la TB

> Mémo JFC (2026-07-12), verbatim. Branche `develop` (des DEUX repos), jamais `main`.
> **Contexte** : l'adjudication est un membre permanent de la hiérarchie d'oracles de labels
> (TB > adjud > jeu). Ce mémo ajoute les **crans fins** : des prédicats structurels déterministes
> qui étendent l'adjudication au-delà du matériel brut, là où le ply-cap pollue encore (~19 % mesuré).
> **dilf en a livré les primitives** (`pedagogy/features/`, mypy --strict, `EngineProtocol` injectable).
>
> **Principe de confiance** : Claude ÉCRIT les prédicats (code déterministe sur primitives moteur —
> jamais du jugement) ; **la TB les NOTE** (précision exacte sur des positions à vérité connue) ; seuls
> les prédicats ≥ 99,9 % entrent dans l'oracle. Un prédicat à 97 % est REJETÉ.

## 0. ARCHITECTURE (où ça vit)
- **Prédicats** : composés depuis `features/geometry|mobility|structure|material`. Purs, typés, testés.
- **Branchement gen** : jass implémente `EngineProtocol` (`legal_moves` suffit pour v0). Coût Python trop
  élevé dans la boucle chaude ⇒ prédicats validés RE-PORTÉS en C++ dans jass, dilf = oracle d'équivalence.
- **Ordre d'appel à la terminaison gen** : `TB (exact) → prédicats (≥99,9 %) → adjud matérielle (cran courant) → jeu`.
  Chaque label porte `label_oracle ∈ {TB, PRED_<nom>, ADJUD, GAME}`.

## 1. LES 4 PRÉDICATS v0
- **P1 — PERCÉE IMPRENABLE (runaway) → WIN** : pion à distance de promo `d` sans intercepteur ≤ d tempi,
  pas de contre-runaway. Briques : `promotion_distance`, `min_promotion_distance`, `squares_between`,
  `threatened_captures`. Conservatisme v0 : `d ≤ 4`, zéro intercepteur, pas de contre-runaway ≤ d+1.
- **P2 — BLOCAGE TOTAL → DRAW** : coups non-capturants des 2 camps tous « suicidaires » (recapture nette,
  test 1-ply) OU structure figée + garde tempi. Briques : `count_legal_moves`, `threatened_captures`,
  `find_holes`. Conservatisme v0 : ≤1 coup libre/camp, sans dames, stable 2 plies.
- **P3 — DAME ENFERMÉE / matériel mort → veto** : dame géométriquement enfermée ⇒ **veto** sur l'adjud
  matérielle (pas un verdict autonome). Briques : `count_legal_moves` (pièce), `diagonal_neighbors`.
- **P4 — VETO FORTERESSE (miné §3)** : classe « +matériel mais nul », patterns extraits du minage TB.

> P1/P2 = **verdicts** (adjudiquent) ; P3/P4 = **vetos** (empêchent l'adjud matérielle de mentir, zéro risque).

## 2. HARNAIS DE NOTATION TB (le juge — à construire EN PREMIER)
1. Échantillon N≥1M positions ≤ N_TB pièces : (a) trajectoires gen réelles (distribution d'usage) + (b) TB uniforme.
2. Verdict prédicat vs valeur TB exacte.
3. Métriques/prédicat : **précision** (≥99,9 % = admission) ; **taux de tir** (couverture = ply-cap économisé) ; matrice phase/matériel.
4. Second examen hors-TB : QA-set dilf (forteresses/blocages documentés) — WIN ne doit jamais tirer, vetos devraient.
5. Admission gravée au manifest : `precision_tb`, `fire_rate`, date, N.

## 3. MINAGE DES EXCEPTIONS (les prédicats sortent des données, pas des priors)
- Énumérer/échantillonner la TB pour **|matériel| ≥ +2 mais valeur = DRAW** → corpus d'exceptions.
- Analyser AVEC les features dilf : qu'est-ce qui caractérise structurellement ces positions ? → prédicats P4.x → re-notés §2.
- Boucle vertueuse : la TB fournit les exceptions, Claude les formalise, la TB note la formalisation.

## 4. INTÉGRATION BOUCLE FROM-SCRATCH
- Prédicats admis = crans supplémentaires de l'escalier d'adjud ; le ply-cap recule sans que les labels mentent.
- **Un changement par tour**. Bénéfice permanent (tous les gens futurs + moteur explicatif). ⛔ Jamais d'adjud par SCORE d'éval.

## 5. ORDRE D'EXÉCUTION
1. Harnais TB (§2) — le juge d'abord. 2. P3+P2 (vetos/draw). 3. P1 (percée). 4. Minage → P4.x. 5. Branchement gen (1 prédicat/tour). 6. Re-port C++ si coût.

## 6. EN UNE PHRASE
Claude compose des prédicats déterministes depuis les primitives dilf, **la TB les note** (≥99,9 % sinon rejet),
les admis deviennent des crans fins de l'escalier d'adjudication — le ply-cap recule, les labels disent la vérité plus tôt.

---

## JOURNAL D'EXÉCUTION (Claude)
- **2026-07-12** — Infra : jass `--dump-legal` + module `pattern_jass/tools/adjud/` (DumpEngine + P2/P3) sur develop ; dilf cloné/importé sur box.
- **0680** (harnais §2 + baseline) : juge TB OK, pont dilf OK. Baseline matérielle vs TB (200k uniformes ≤7pc) :
  M=4 → prec 81% / 16k faux-WIN ; M=12 → prec 99,977% / fire 2,2%.
- **0681** (P2/P3 v0) : **REJETÉS** — P3 veto prec 38,9% ; P2 draw prec 45-48% (≪99,9%). Priors main faux en finale creuse.
- **0682** (à venir) : **minage §3** du corpus faux-WIN (|net|≥M & TB=nulle) → features dilf → prédicats data-driven.
