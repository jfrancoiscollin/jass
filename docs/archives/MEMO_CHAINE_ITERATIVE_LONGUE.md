# MÉMO — LA CHAÎNE ITÉRATIVE LONGUE : tester la recette Scan qu'on n'a jamais tirée en entier

> **Auteur : JFC (2026-07-08).** À passer à Claude Code. Branche `develop`, jamais `main`.
> **Déclencheur** : à exécuter SI 0648 (piste 1 wdl_finetune ancré + MMTO last) est **flat/négatif**
> (le screen cpx62 penche déjà −76 sur anchor 0.03). En parallèle sur l'AUTRE box : DOE search gen2-mmto.
>
> **Origine** : la question récurrente de JFC — « comment Scan a fait ? le volume ne paie pas chez nous ».
> Réponse honnête : **on ne connaît pas la recette de Scan** (bribes de forum Letouzey, pas de papier).
> L'explication « volume » que j'ai propagée est **contredite par nos plateaux** (chaîne gen1→gen3 plate,
> WDL-from-scratch 0.647 sature vite). L'hypothèse la plus sérieuse restante : le secret n'est pas le
> VOLUME par génération, c'est **l'ITÉRATION LONGUE sur une distribution qui se déplace** — jamais testée
> ici. Ce mémo la teste proprement, avec un gate compose-vs-sature.

---

## 0. CE QU'ON SAIT / CE QU'ON NE SAIT PAS (à garder honnête)

**Su** : Scan a un meilleur fit (pairwise > 0.72 estimé vs 0.699 gen2-mmto). Régression WDL
logistique + self-play + itération (résumé communautaire).
**Inconnu** : nombre d'itérations, profondeur de gen par tour, pondération, régularisation, **et
surtout le bootstrap initial** (comment la 1ère éval a été créée — heuristique ? éval réglée
main pré-2015 ? on n'a AUCUNE visibilité). ⟹ on tente une **reconstruction**, pas une copie.

**Pourquoi la famine-volume est probablement FAUSSE** (mes propres torts) : si c'était le
volume, en ajouter paierait — or non (0645 from-scratch −33/−61 ; chaîne plate). Le
from-scratch atteint 0.647 **vite** puis stagne ⟹ le volume sature sur ce que le WDL extrait ;
le gap restant n'est pas quantitatif.

---

## 1. POURQUOI LES CHAÎNES PRÉCÉDENTES ONT PLAFONNÉ (2 confonds jamais levés ensemble)

1. **Anchor toujours ancré à gen1** → le fit est tiré vers gen1 par construction → l'éval **ne
   peut pas dériver** de génération en génération. On a protégé l'acquis au prix du mouvement.
2. **Le pilote ne changeait pas QUALITATIVEMENT entre tours** → gains full-game (search) sans
   vision tactique neuve (0567) → corpus quasi-identique d'un tour à l'autre → rien de neuf à
   apprendre → plateau en 1 génération.

⟹ **La chaîne longue n'a jamais tourné avec (a) une éval autorisée à bouger substantiellement
ET (b) un pilote qualitativement différent à chaque tour.** C'est exactement la condition qui
rendrait la distribution mobile — le mécanisme Scan supposé.

---

## 2. LE TEST : chaîne itérative longue « façon Scan »

### Principe
5-10 générations, où à CHAQUE tour : le pilote = **champion précédent**, on **re-génère TOUT**
le corpus (distribution mobile), et l'éval a le **droit de dériver** (anchor au tour précédent,
pas à gen1 — ou anchor décroissant).

### Protocole
- **G0 = gen2-mmto** (le champion actuel, meilleur point de départ — PAS from-scratch, leçon
  0645 : ne pas jeter l'acquis).
- **Boucle tour t → t+1** :
  1. **Self-play** avec pilote = champion(t), recette réhabilitée (couverture eps préservée
     leçon −25 ; quiet-only ; asym pur pour la conversion ; tb-relabel VÉRIFIÉ tirant ;
     manifest flag⇒effet). Volume modéré par tour (2-3M — le pari est le NOMBRE de tours, pas
     le volume par tour).
  2. **Fit** : `wdl_finetune` **ancré au champion(t)** (pas gen1), anchor **décroissant** avec
     t (ex. 0.3 → 0.1 → 0.05 : serré au début pour ne pas exploser, relâché ensuite pour
     laisser dériver). Fit streamé exact (`--chunk`).
  3. **MMTO last layer** (gen-siblings WS-OFF + rank_finetune) sur le même corpus → champion
     candidat(t+1).
  4. **Gate Elo** vs champion(t) : compose (borne basse > 0) → promu → tour suivant. Neutre →
     voir §3.
- **Mesure clé par tour** : le **pairwise held-out** ET la **d9-vs-Scan** (l'éval-pure). La
  question empirique = *ces deux métriques montent-elles À CHAQUE tour, ou saturent-elles ?*

### Ce qui rend ce test différent des chaînes mortes
- anchor **glissant** (au tour t, pas à gen1) → dérive autorisée.
- pilote **qualitativement meilleur** chaque tour (éval, pas juste search) → corpus mobile.
- **le nombre de tours EST la variable testée**, pas le volume/tour.

---

## 3. GATES PRÉ-ENGAGÉS (compose-vs-sature — trancher AVANT de lire)

- **Chaque tour compose (+ hors-IC), pairwise ↑ ET d9 ↑ monotone** ⇒ **LA RECETTE SCAN EST
  L'ITÉRATION** — on l'a trouvée, on itère jusqu'à saturation, et la question « comment Scan a
  fait » est répondue empiriquement. Énorme.
- **Sature au tour 2-3** (pairwise plafonne, d9 fige, Elo neutre) malgré anchor glissant +
  pilote mobile ⇒ **ni le volume ni l'itération ne sont le levier** → la recette Scan repose
  sur quelque chose qu'on ne reproduit pas (bootstrap initial inconnu, ou détail de fit) →
  **le volume/itération est CLOS définitivement, par la grande porte** → le programme bascule
  sur : re-DOE cuts (convertir d9→movetime) + MMTO prof plus fort (asym scale / jass-mt-long)
  + pivot produit.
- **Dérive destructrice** (anchor trop relâché → régression, style 0645) ⇒ resserrer l'anchor,
  re-tour ; si tout anchor mène soit au plateau soit à la régression, c'est le signal fort que
  la classe est à son point fixe accessible depuis gen2-mmto.

---

## 4. GARDE-FOUS (toutes les leçons câblées)
- **Elo-first** : pairwise/d9 = diagnostics de tour ; le gate de promotion est l'Elo (dilf +
  généraliste, ≥90 paires). (Leçon G1.)
- **WS-OFF obligatoire** au MMTO last (leçon gen3 −354).
- **Holdout par partie** à chaque fit (leçon P3).
- **Manifest flag⇒effet** chaque gen ; tb-relabel compteur `egdb-resolved>0` en gate (leçon
  +18 phantom).
- **Couverture eps préservée** (leçon −25) ; asym pur pour éviter starvation-mix (bug non
  résolu — surveiller ~116 parents/partie).
- **min-pieces 32** pour élargir le seed-pool de parents distincts (le vrai levier de
  diversité, vs empiler des positions sur les mêmes 57k parents).
- **Confirm haut-N** avant d'enterrer un tour qui penche + (leçon 0599→0600).
- **Bug `go movetime` overshoot endgame** : contourné harnais ; ne pas juger un tour sur la
  seule cellule finale movetime tant que le fix search n'est pas fait.
- **Bake réversible** chaque tour (champion(t) archivé).

## 5. COÛT / DÉCISION
- Par tour : ~2-3M gen (≈20-40 min) + fit chunké + MMTO last + A/B ≈ quelques heures.
- 5 tours ≈ 1-2 jours de box. **Bien moins cher que la spéculation continue sur Letouzey.**
- **Préalable** : lire 0648 (le couplage wdl_finetune+MMTO d'un tour) — s'il compose déjà, ce
  mémo EST sa version itérée longue (enchaîner les tours). S'il est neutre, ce mémo teste si
  **plusieurs** tours débloquent ce qu'**un** tour ne fait pas.

## 6. EN UNE PHRASE
On ne connaît pas la recette de Scan ; l'hypothèse « volume » est démentie par nos plateaux ;
le candidat restant est **l'itération longue sur distribution mobile** (anchor glissant +
pilote qualitativement meilleur chaque tour) — jamais tirée en entier — et ce test la tranche
en 5 tours : soit chaque tour compose (on a trouvé la recette), soit ça sature au tour 2-3 (le
volume/itération est clos pour de bon, et le secret de Scan est ailleurs — bootstrap initial ou
détail de fit qu'on ne reproduira pas — donc cap sur MMTO-prof-fort + re-DOE cuts + produit).

---

## PISTE PARALLÈLE (ccx33) — DOE SEARCH sur gen2-mmto
Pendant que cpx62 tourne la chaîne longue, ccx33 fait une passe **design-of-experiments** sur les
paramètres de RECHERCHE de gen2-mmto (LMR, futility/history pruning, aspiration, move-ordering,
node-check granularité), pour **convertir le gain éval-par-nœud (d9 +34/+46) en force movetime**
(le résidu −128 à −155 vs Scan à movetime vient en partie du search, pas seulement de l'éval).
Elo-first (dilf + généraliste). Attention au **bug go-movetime overshoot endgame** (contourné harnais).
