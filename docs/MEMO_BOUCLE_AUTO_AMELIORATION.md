# MÉMO — BOUCLE D'AUTO-AMÉLIORATION « à la Scan » : prof = SOI + DU TEMPS (jass-mt-long)

> Auteur : JFC (2026-07-09). À passer à Claude Code. Branche `develop`, jamais `main`.
> **Corrige le « théorème élève-limité » (0650-0656)** : ces chaînes n'ont testé que des profs
> d8-d14 < le tutorat Scan-mt0.2 déjà absorbé par gen2-mmto. La thèse : un moteur peut toujours
> se fabriquer un prof plus fort = lui + du temps (jass-mt-30-60s), jamais essayé.

## ÉTAPE 0 — PRÉ-TEST HEADROOM (une soirée, conditionne tout)
Match jass(gen2-mmto)-mt-30s (et mt-10s) vs Scan-mt0.2 (= le niveau-prof absorbé, cf 0625).
~100-150 games, openings appariés. Gates : jass-mt-30s >= Scan-mt0.2 => carburant existe =>
ÉTAPE 1 ; sinon STOP éval, search d'abord, re-tester après bake search. ⚠ contourner le bug
go-movetime overshoot endgame au harnais AVANT (timeout élargi).

## ÉTAPE 1 — CORPUS PROF-SOI (si headroom>0)
1.1 played-moves à mt-30-60s (self-play gen2 vs gen2, symétrique = tous coups du prof, eps
    préservé, quiet-only) ; ~500 parties ≈ 25-30k prefs d'élite (qualité > volume, dose-réponse ×10).
    Option asym mt30 vs mt1 pour positions de conversion (prefs côté fort).
1.2 child-scored à mt-3-5s sur ~5-10k parents (marges -> filtre m_min). PAS de child-scored 60s.
1.3 fratries TB (ordre exact W>D>L, sur-pondéré).

## ÉTAPE 2 — FIT + BOUCLE
MMTO through-search (jamais statique, -847), WS-OFF (gen3 -354), ancré champion courant
(rank_finetune --chunk, anchor {0.05,0.1}). Gate Elo-first (dilf+généraliste, >=90 paires,
confirm haut-N) + d9-vs-Scan. Si tour 1 compose : champion(t+1) -> son mt-long plus fort ->
l'écart 0621 se re-crée -> regen -> re-fit ancré -> boucle (le prof grandit avec l'élève).
Entre les tours : re-DOE cuts (convertir d9 en movetime).

## GATES PROGRAMME
Tour 1 compose (+hors-IC) => auto-amélioration amorcée, autonomie de fait (Scan hors boucle).
Tour 1 neutre malgré headroom>0 => le savoir prof-soi-long ne se compresse pas dans la classe =>
clôture éval DÉFINITIVE (prouvée avec le meilleur prof constructible) => cap search + produit.
Headroom <=0 => pas de carburant aujourd'hui => search d'abord, re-tester après bake search.

## GARDE-FOUS
Elo-first (G1) · WS-OFF (gen3) · through-search (-847) · ancré jamais refit-zéro (0645) ·
holdout/partie (P3) · manifest flag=>effet (+18 phantom) · couverture eps (-25) · confirm
haut-N (0599->0600) · fix movetime-endgame AVANT matchs mt-long · min-pieces 32 · bake réversible.

## COÛT
Étape 0 : ~1 soirée. Tour 1 : gen nuit mt-30 + child-scored + fit + A/B ≈ 2-3 jours.

## EN UNE PHRASE
Le prof c'est soi + du temps et il grandit avec l'élève ; 0650-0656 n'a testé que des profs au
rabais (d8-d14 < Scan absorbé) ; ce mémo donne à la boucle son vrai prof (jass-mt-30-60s), mesure
d'abord si le carburant existe (headroom, une soirée), et grave les 2 sorties : boucle amorcée
(autonomie) ou clôture éval définitive avec le meilleur prof constructible.
