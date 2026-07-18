# F1 — garde `!tactical` manquant sur le NMP (fix validé, PAS encore baké)

**Statut : VALIDÉ, prêt à baker AVANT la phase EBF.** `search.cpp` sur main est
INCHANGÉ (chaîne intacte) — ce patch est en attente d'application.

## Le trou
`src/search.cpp` bloc NMP (~l.710) : `!was_null`, `!is_mate_score(beta)`,
`!(eg && eg_no_nmp)` mais **PAS `!tactical`** — contrairement à RFP (l.666) et razor
(l.683), alors que le commentaire l.611 dit « RFP / NMP / razoring all want it ».
Sur un nœud en capture FORCÉE (post-sacrifice → +1 matériel → `static_eval>=beta`
trivial) le null-move décline une capture obligatoire (illégal aux dames) → cutoff à
beta → la reprise forcée (réfutation du sac) n'est jamais explorée. Signature 0440
DANS l'arbre.

## Latent
Défauts `eg_pieces=40 + eg_no_nmp=true` ⇒ NMP OFF ⇒ code mort AUJOURD'HUI. Mais la
**phase EBF** va balayer des ré-activations du NMP → désamorcer avant, sinon le trou
pollue le verdict du DOE en silence.

## Validation (branche `claude/audit-f1-nmp-tactical`, commit b85ca681b)
- `jass_tests` : **100% PASSED**.
- **Byte-identical au défaut** : 5 positions, nœuds ET coups EXACTEMENT identiques F1
  vs base (NMP off au défaut → fix no-op).
- **Fix live avec NMP forcé ON** (`eg_pieces=0,eg_no_nmp=0`) : la base choisit des
  coups FAUX (28-22 / 30-24 / 34-30) que F1 corrige (37-31 / 38-32 / **28-23** — ce
  dernier = le coup sain du défaut). Le NMP corrompait bien la recherche sur nœud
  tactique.

## Baker (avant EBF)
`git apply docs/patches/F1-nmp-tactical.patch` sur main → build → `jass_tests` →
push. No-op au défaut donc bake sûr pour la chaîne en cours.
