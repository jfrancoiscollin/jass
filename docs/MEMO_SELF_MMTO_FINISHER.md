# MINI-MÉMO — SELF-MMTO sur la lignée from-scratch : FINISSEUR de rampe, pas par-tour

> À passer à Claude Code. Branche `develop`, jamais `main`. **Question JFC** : composer la
> boucle WDL from-scratch avec MMTO ? **Réponse : OUI, mais en FINISSEUR terminal de rampe —
> PAS intercalé par-tour.** Ce mémo grave le créneau, le protocole, et l'expérience optionnelle
> qui tranche l'alternance.

---

## 0. POURQUOI LA COMPOSITION EST FONDÉE
- WDL calibre les **valeurs** (rang grossier) ; MMTO sculpte les **marges de décision**
  (départager les sœurs) — le défaut structurel que le WDL n'optimise pas (0591/0597). La
  lignée from-scratch, WDL-pure, développera le même défaut de marges que gen1.
- **Précédent mesuré** : gen1 (WDL) + MMTO = gen2-mmto, **+34 d9**. La composition marche.
- **Le prof-soi est LÉGITIME dans cette lignée** : le « élève-limité » (0650-56) venait de ce
  que gen2-mmto avait absorbé un prof-Scan > tout jass-self. La lignée from-scratch n'a
  JAMAIS eu de prof plus fort que sa propre recherche → ses préférences profondes ont du
  carburant, par le même mécanisme qui fait composer le WDL aujourd'hui.

## 1. POURQUOI PAS PAR-TOUR (3 raisons, dont une mesurée)
1. **Oscillation documentée** : 0648-screen — une recalibration WDL même minuscule
   (|Δw|~1e-5) déplace un optimum MMTO (−36/−76). En alternance, chaque fit WDL du tour t+1
   déferait le sculptage MMTO du tour t.
2. **Sculpter des marges sur une base qui bouge = sculpter du sable.** La base apprend encore
   le grossier (T2 +170). MMTO est arrivé APRÈS le plateau WDL de gen1 — ordre logique, pas
   accident.
3. **La cadence est la richesse de la boucle** : gen-siblings + leaf-search par tour =
   +heures/tour pour un gain douteux (cf. 1-2).

## 2. LE CRÉNEAU : FINISSEUR TERMINAL (déclenché par E3 ou son approche)
Quand l'échelle sature (2 non-composes au dernier barreau, ou compose < +40 répétés) :
- **Corpus prefs** : played-moves extraits des parties du DERNIER BARREAU (elles existent
  déjà — extraction quasi gratuite) + sous-lot **child-scored au budget-nœuds du barreau**
  (marges → filtre m_min). Fratries TB en bonus (ordre exact, sur-pondéré).
- **Fit** : MMTO **through-search** (leaf-mode — jamais statique, leçon −847), **WS-OFF**
  (leçon −354), **ancré sur le champion from-scratch final**, `rank_finetune --chunk`,
  anchor sweep léger {0.05, 0.1}.
- **Gates** : Elo-first vs champion from-scratch (généraliste mt, ≥90 paires, confirm haut-N
  si penche-dans-IC) ; d9-vs-Scan sur le promu (l'éval-pure doit bouger, comme gen2 : +34) ;
  dilf garde-fou.
- **Si ça compose** ⟹ recette autonome COMPLÈTE démontrée : **WDL-ladder (valeurs) +
  self-MMTO (marges)**, zéro Scan à aucun étage — la réplique intégrale de gen1→gen2-mmto en
  version souveraine. Section papier assurée.

## 3. OPTION — L'EXPÉRIENCE D'OSCILLATION (1 tour, si impatience avant fin de rampe)
À une frontière de barreau : une passe MMTO → puis mesurer si **le tour WDL suivant la
défait** (pairwise-acc held-out avant/après le tour WDL).
- pairwise **survit** ⟹ l'alternance est viable → passes MMTO autorisées aux frontières de
  barreaux.
- pairwise **rongé** ⟹ finisseur terminal confirmé comme seul créneau. Question close.

## 4. CE QU'ON NE FAIT PAS
- ❌ MMTO intercalé par-tour (§1) sans l'expérience §3 positive.
- ❌ MMTO statique (−847) ; WS-ON (−354) ; refit-de-zéro (0645).
- ❌ Ralentir la rampe WDL actuelle : **elle compose — on ne touche à rien.**

## 5. EN UNE PHRASE
La rampe WDL fabrique les valeurs ; le self-MMTO taillera les marges **quand la base tiendra
debout** (finisseur de rampe, prof = ses propres parties au dernier barreau) — l'alternance
par-tour est interdite par défaut (oscillation 0648) sauf si l'expérience-1-tour (§3) prouve
que le pairwise survit à un tour WDL.
