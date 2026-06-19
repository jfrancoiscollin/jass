# Boucle virtuelle distribuée — la voie active (2026-06-19)

> **Référence du système actif** : comment on fait *monter* notre archi linéaire-patterns par
> auto-amélioration itérée, façon Scan, en distribué sur nos boxes. À lire avec [CURRENT.md](CURRENT.md)
> (état 1 page), [SCAN_ARCHITECTURE_NOTES.md §5](SCAN_ARCHITECTURE_NOTES.md) (recette Scan reconstituée)
> et [ARBRE_DECISION.md](ARBRE_DECISION.md) (principe). MAJ : **2026-06-19**.

## 0. Le pivot — on ne se compare PLUS à Scan (jusqu'au plateau)

Tant qu'on n'a pas convergé, **vs-Scan = forcément perdant** (on est loin) et **insensible/bruité** au
plancher (cf 0358/0359 : la même config donnait 0.028 vs 0.083 d'un run à l'autre). Donc :

- **Métrique = SOI-MÊME, EN DIRECT** : `gen_k vs gen_{k-1}` (on monte *encore* ?) et `gen_k vs gen1`
  (montée cumulée), via `jass --benchmark-nnue-vs-nnue` (même binaire, bande ~0.5 = **sensible**).
- **Scan ne ressort qu'AU PLATEAU** (`gen_k vs gen_{k-1} ≈ 0.5`), pour situer le niveau atteint — pas avant.

## 1. Pourquoi une boucle PEUT faire monter du linéaire (et ce qu'elle ne peut pas)

Deux boucles à NE PAS confondre :
- **A — apprentissage de REPRÉSENTATION** (AlphaZero / NNUE) : le réseau invente ses propres features →
  expressivité croissante sans borne. **IMPOSSIBLE en linéaire** (features figées). C'est ce qui permet
  de *dépasser* un bon eval de référence.
- **B — optimisation des POIDS sur features FIXES** (Scan, Texel-tuning, GLEM/Buro) : on améliore la
  **donnée/les cibles** à chaque tour, le fit linéaire converge vers le **meilleur-linéaire**. **POSSIBLE**,
  plafond = best-linéaire-sur-les-features. **C'est ce que fait Scan, et ce qu'on fait ici.**

Notre boucle est de type **B**. Elle converge VERS le meilleur fit (≈ Scan si on a son volume/qualité de
data), pas au-delà. *Dépasser* Scan = type A = NNUE (décision future, hors de cette boucle).

## 2. La recette (de Scan) — self-play + WDL + logistique, ITÉRÉ, depuis zéro

D'après l'audit ([SCAN_ARCHITECTURE_NOTES §5](SCAN_ARCHITECTURE_NOTES.md), posts Letouzey + réplication
Kingsrow) : Scan génère ses labels par **son propre self-play depuis zéro** (seed matériel-seul « 1 dame
≈ 3 pions »), label = **résultat réel** de la partie (WDL), **régression logistique** sur les features,
itéré. Pas de prof, pas de corpus externe. La data WDL est **auto-générée** et c'est un **actif durable**.

Un tour = `eval` joue contre elle-même → positions + résultat WDL → refit logistique → `eval'` plus forte
→ rejoue mieux → … = **policy/value iteration approchée**. L'amélioration vient de l'**info injectée par
le résultat** (vérité externe que l'eval statique n'a pas).

## 3. Les deux découvertes qui ont fixé le réglage (2026-06-19)

1. **« Décisif ≠ véridique » → il faut jouer PROFOND.** Notre bootstrap WDL à **depth 4** (0363) *grimpe
   en interne* (DIRECT gen1→gen6 : 0.50→0.72) **mais reste plat ~0 vs Scan** : il converge dans un bassin
   FAIBLE. Cause (0365) : les parties d4 sont **décisives à 77 %** (signal RICHE, *pas* dégénéré) MAIS
   **blunder-driven** (2 faibles, qqn gaffe) → l'eval apprend la value-function d'un **joueur faible**, pas
   la vraie valeur. Gradient confirmé : d4 77 % décisif > d9 71 % > embarquée 68 % (plus on joue fort, moins
   décisif). → **le levier = FORCE du self-play (profondeur ≥10-12) + VOLUME**, pas la décisivité.
2. **Le jeu profond est QUASI GRATUIT chez nous.** Débit mesuré (sonde 0366) : **24 000 pos/min @ d10**
   sur cpx62 (16 c) — seulement **~2× plus lent que d4** (pas 64× ; le pruning rend la recherche profonde
   bon marché). Donc « qualité (profond) ET volume » **n'est pas un dilemme**.

Corollaires :
- **Branche morte** : boucle WDL/distillation depuis data DÉJÀ FORTE/drawish (0356/0357 ; 0364 distill via
  jass-self-play) = dégénérée ou dégrade. Il faut le **gradient décisif→drawish** d'un départ faible.
- **Réglage** : `play_depth = 10` (cpx62) / `12` (ccx33) ; seed matériel-seul (la recherche d10 compense) ;
  finales adjugées exact par **egdb** (`terminate-at-TB` → WDL non dégénéré) ; cible WDL = résultat.

## 4. Débit & volume (mesuré)

| Box | Profondeur | Débit | Par tour (~30 min gén) | Par heure |
|---|---|---|---|---|
| cpx62 (16 c) | d10 | **24k/min** | ~720k (cap 800k) | ~1,4 M |
| ccx33 (8 c) | d12 | ~4-6k/min* | ~120k | ~0,3 M |
| **pool** | | | **~840k / tour** | **~1,7 M/h** |

\*sonde 0367 à confirmer. Continu : ~**40 M/jour**, ~**100 M+** sur quelques jours (Scan = milliards →
encore 1-2 ordres en dessous, mais ≫ nos 2,4 M précédents → le volume entre en régime utile).
**Cap de génération relevé** : `NPER = débit × 30 min`, plafond **800k** (l'ancien 160k était 3× trop bas).

## 5. Architecture DISTRIBUÉE (les 2 boxes ne partagent QUE git)

Le runner GitOps : 1 worker/box, jobs routés par préfixe (`cpx62-*` / `ccx33-*`), résultats committés sur
`main`. La **gen data WDL est arch-indépendante** → poolable et réutilisable à jamais (actif durable).

**Un TOUR = générer (les 2 boxes) → pooler → refit → redistribuer :**
1. **gen** : chaque box joue self-play piloté par le **champion** (cpx62 d10 = volume, ccx33 d12 = qualité)
   → committe son **shard** WDL dans `artefacts/` (≤95 Mo).
2. **pool** : on étend le **pool durable** (`pooled.jnnw`) avec les nouveaux shards, **fenêtre glissante
   ≤2M records** (on garde les plus RÉCENTS = data des évals les + fortes ; reste sous le cap git 95 Mo).
3. **refit** : régression logistique full-fold sur le pool étendu → **champion+1**.
4. **juge** : `champion+1 vs champion` en DIRECT → le tour a-t-il amélioré ? Committe `champion+1.pjtw` +
   `pooled.jnnw` → pilote du tour suivant. **On enchaîne.**

Transport inter-box = git : un job lit ses prédécesseurs via `git show origin/main:<path>` avec **boucle
d'attente** (chaque job attend la data committée dont il dépend). ⚠️ La data *intra-tour* vit dans
`artefacts.src` (côté-serveur, non committé) → les jobs de pooling lisent la data **locale** de leur box
→ il faut les enchaîner **avant le recyclage du container** (inactivité).

### Pipeline de jobs (2026-06-19)
| Job | Box | Rôle |
|---|---|---|
| `0366` / `0367` | cpx62 / ccx33 | **bootstrap** d10 / d12 (seed matériel, cap 160k) — la boucle grimpe-t-elle ? d10 vs d12 ? |
| `0368` | ccx33 | harvest data 0367 → git |
| `0369` | cpx62 | **poole** 0366+0367 → **champion** (+ pool durable committé) |
| `0370` | ccx33 | **[cap relevé]** champion génère d12 → shard committé |
| `0371` | cpx62 | **[cap relevé]** champion génère d10 + poole le d12 + étend le pool → **champion2**, juge vs champion |

(0370/0371 = **tour 1** ; on les réplique en tour 2, 3, … en faisant tourner `champion_k`.)

## 6. Pièges permanents (à NE PAS reproduire)

- **`gen_patterns --emit` PAS reset-proof** : le runner reset l'arbre vers `main` mid-run → géométrie
  émise révertée (0359/0362 invalidés). **Règle** : build tout de suite (le binaire fige la géométrie) +
  copier `patterns.py` hors-tree + pin **`JASS_PATTERNS_DIR`** (le trainer la lit) + garde-fou « ×32 ».
- **`--minibatch` est L2-only** (incompatible `--loss logistic`). À d10 le goulot = la GÉNÉRATION pas la
  RAM → **full-batch `--lowmem`** suffit (a encaissé 2,4M en 0224).
- **Juger vs Scan au plancher = bruit** (run-to-run ±0.05 sur la même config). Juge = **DIRECT self**.
- **Décisif ≠ véridique** : ne PAS bootstrapper sur du d4 (blunder-driven) — profond (≥10) ou rien.

## 7. Quand on plateau

`gen_k vs gen_{k-1} ≈ 0.5` soutenu (la data fraîche n'améliore plus) ⇒ **plateau du fit linéaire sur ce
volume/cette profondeur**. Leviers AVANT de conclure : ↑ profondeur, ↑ volume (plus de tours/boxes), pool
plus large. **Au vrai plateau** : on ressort Scan (depth-égale) pour situer. Si très en dessous de Scan
malgré volume+profondeur → le reste du gap = **type A (NNUE)**, décision produit.
