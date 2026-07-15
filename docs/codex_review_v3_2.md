# Revue Codex v3.2 — spécification exécutable de la sonde de conversion

> **Date : 2026-07-15**  
> **Statut : conception figée, DOE `0726` clos, prérequis d’exécution approuvés, bon pour implémentation par Claude Code**  
> **Relation aux versions précédentes :** cette v3.2 conserve `codex_review.md`, `codex_review_v2.md`, `codex_review_v3.md` et `codex_review_v3_1.md` comme historique. Elle reprend les décisions de la v3.1 et ajoute la spécification opérationnelle manquante pour la sonde multi-tours.  
> **Périmètre :** sonde `ADJ + G1` de T1-bis à T3, mining passif des jets de gain, préparation du futur smoke teacher.  
> **Règle projet :** aucun NNUE ; rester dans la classe linéaire-patterns tant que son meilleur fit n’est pas atteint.

---

## 0. Résumé exécutif

Le diagnostic scientifique reste inchangé : Jass détecte les premières idées tactiques à un niveau proche de Scan, mais convertit beaucoup moins bien les positions gagnantes. Le problème principal est donc **en aval de la détection**, dans la conservation et la réalisation de l’avantage.

Le DOE `0726` a clos la phase à un tour :

- les labels profonds `d14 + EGDB` sont le seul levier présentant une direction positive sur la force générale ;
- la répétition G4 du gymnase existant ne monte pas la conversion WDL-grounded ;
- aucune interaction utile `LABEL × GYM` n’est démontrée ;
- `ADJ + G1` est la recette minimale retenue ;
- le plafond à un tour est réel pour la recette testée.

La prochaine expérience est une sonde multi-tours bornée :

```text
T1-bis assemblé
→ promotion régime jeune
→ T2
→ promotion régime jeune
→ T3
→ verdict de sonde
```

Trois prérequis sont désormais gravés :

1. une preuve exacte ou vérifiée peut bloquer le draw-band ; une simple stabilité de recherche ne le peut pas ;
2. la promotion des tours jeunes exige l’absence de régression généraliste établie contre le parent **et** contre une référence fixe ; la conversion est mesurée mais non exigée ;
3. T1-bis est le premier tour assemblé de bout en bout, avec un PASS pré-engagé et des manifests complets.

Le mining des jets de gain peut tourner pendant la sonde, mais reste **strictement hors boucle** : inventaire seulement, sans fit, sans injection et sans influence sur les promotions T1-bis→T3.

### Séquence figée

```text
implémenter les prérequis de sonde
→ T1-bis ADJ + G1
→ T2
→ T3
→ verdict de sonde
→ smoke teacher A/B1/B2/B3 si nécessaire
→ confirmation du bras gagnant
→ campagne longue seulement ensuite
```

---

## 1. Faits expérimentaux de référence

### 1.1 DOE `0726`

| Cellule | Conversion WDL-grounded | N conversion | Gate vs bootstrap | N gate |
|---|---:|---:|---:|---:|
| `onp_g1` | 0,672986 | 422 | −8,11 Elo | 600 |
| `adj_g1` | 0,671362 | 426 | **+18,55 Elo** | 600 |
| `onp_g4` | 0,662679 | 418 | −29,02 Elo | 600 |
| `adj_g4` | 0,662679 | 418 | +16,23 Elo | 600 |

Contrastes directs :

```text
LABEL à G1       : +7,53 Elo ; conversion −0,0016
LABEL à G4       : +23,20 Elo ; conversion +0,0000
GYM sous ONP      : −2,90 Elo ; conversion −0,0103
GYM sous ADJ      : +5,79 Elo ; conversion −0,0087
interaction Elo   : non utile démontrée
interaction conv  : +0,0016
```

`adj_g1` est le choix opérationnel, mais son gate individuel reste compatible avec le neutre à N=600. La sonde doit donc tester la **composition multi-tours**, pas proclamer un gain Elo définitivement établi à T1.

### 1.2 Incidents d’infrastructure clos

```text
0723 : OOM par cache EGDB agrégé
0724 : morts de moteurs Jass puis cascade BrokenPipe/EOF dans conv_fixed_wdl
0725 : preuve par shard du mécanisme de cascade
0726 : restart-on-death actif, DOE terminé rc=0
```

Ces incidents sont distincts et ont reçu des corrections distinctes.

Pour tout job d14+EGDB shardé :

```text
cache_mb × nombre maximal de processus EGDB simultanés
< budget mémoire réservé au job
```

La recette doit conserver une marge pour l’OS, les workers, les buffers et les processus arbitres. Sur la machine 32 Go utilisée, la configuration doit rester nettement sous environ 24 Go de cache EGDB agrégé.

---

## 2. Décisions scientifiques toujours figées

### 2.1 Le trou est en aval de la détection

La ligne « modifier le search générique pour trouver les premières combinaisons » reste close. Les territoires actifs sont :

- vérité des trajectoires ;
- labels profonds ;
- value-function de conversion ;
- technique de finale ;
- crédit causal de l’action ;
- oracles ;
- éventuellement capacité linéaire spécialisée, uniquement après preuve d’un signal qui ne transfère pas.

### 2.2 L’information contrefactuelle reste le cœur du futur teacher

```text
parent certifié WIN
├── coup joué            → enfant DRAW ou LOSS
└── frère jamais joué    → enfant WIN
```

Le teacher est défini par cette information, pas par la forme de loss utilisée pour l’apprendre.

Le futur smoke reste :

```text
A   baseline WDL adjudicated
B1  A + frères oracle comme records WDL ordinaires
B2  A + rank-finetune statique good > bad
B3  A + rank-finetune through-search / leaf-mode
```

### 2.3 B2 est le témoin de décalibration de B3

```text
B2 régresse et B3 compose
→ bénéfice spécifique du through-search

B2 régresse et B3 régresse
→ préférence toxique même à travers la recherche

B2 ≈ B3
→ complexité leaf-mode non justifiée

B1 compose
→ information contrefactuelle assimilable par le canal WDL ordinaire
```

B2 et B3 devront partager les mêmes parents, paires, splits, plafonds par parent, seeds, gates et budgets d’optimisation.

### 2.4 Sonde et campagne longue sont deux régimes distincts

La sonde T1-bis→T3 teste un signal rapide et la capacité de la vérité adjudicated à composer. Elle ne prouve pas l’épuisement de L3.

Une sonde plate signifie :

```text
pas de signal rapide avec ADJ + G1 et ce budget
```

Elle ne signifie pas :

```text
teacher inutile
ou campagne longue impossible
ou classe linéaire épuisée
```

---

## 3. Priorité des labels et protection contre le draw-band

### 3.1 Hiérarchie de référence

```text
TB_EXACT
>
CERT_PROOF vérifié
>
SEARCH_STABLE d14/d16
>
on-policy final
>
AMBIGUOUS / quarantaine
```

La hiérarchie exprime l’autorité du label. Elle ne doit jamais être réduite à un nom de fichier ou à un statut historique.

### 3.2 Règle `blocks_draw_band`

Le conflit entre une certification et le draw-band doit être résolu explicitement dans les données et dans le code.

`blocks_draw_band = true` uniquement pour :

1. `TB_EXACT` : résultat directement résolu par la tablebase ;
2. `CERT_PROOF` vérifié : preuve reproductible validée, par exemple une PV forcée atteignant une tablebase ou un objet de preuve contrôlé par un vérificateur versionné.

Une simple stabilité de signe ou de score entre d14 et d16 reste `SEARCH_STABLE` :

```text
SEARCH_STABLE
≠
preuve exacte
```

Elle peut dominer un label on-policy mais ne bloque pas automatiquement le draw-band.

### 3.3 Schéma minimal du certificat

```json
{
  "position_hash": "...",
  "oracle_tier": "TB_EXACT | CERT_PROOF | SEARCH_STABLE | ON_POLICY | AMBIGUOUS",
  "proof_type": "tb_direct | pv_to_tb | reproducible_proof | search_stable | none",
  "proof_validated": true,
  "blocks_draw_band": true,
  "engine_sha": "...",
  "oracle_parameters": {
    "depth_primary": 14,
    "depth_confirmation": 16,
    "draw_band": 50
  },
  "score": 0,
  "score_margin": 0,
  "side_to_move": "black | white",
  "pov": "black | stm | absolute",
  "egdb_path_id": "...",
  "egdb_version": "...",
  "pv": [],
  "tb_reached": true,
  "verifier_version": "...",
  "created_at": "..."
}
```

Le loader doit rejeter les combinaisons incohérentes, par exemple :

```text
blocks_draw_band=true
avec oracle_tier=SEARCH_STABLE
```

ou :

```text
oracle_tier=CERT_PROOF
avec proof_validated=false
```

### 3.4 Algorithme de résolution du label

```text
si TB_EXACT valide :
    conserver le résultat exact
    ignorer le draw-band

sinon si CERT_PROOF valide et vérifié :
    conserver le résultat certifié
    ignorer le draw-band

sinon si SEARCH_STABLE valide :
    appliquer la politique SEARCH_STABLE documentée
    le draw-band reste autorisé

sinon :
    appliquer relabel d14+EGDB et draw-band normal
```

Cette résolution doit être identique pour :

- les positions de la sonde ;
- les positions du gymnase G1 ;
- les futurs parents teacher ;
- les enfants joués ;
- les siblings oracle.

### 3.5 Gates de conservation du tip

Invariants durs :

```text
100 % des TB_EXACT valides survivent au draw-band
100 % des CERT_PROOF valides survivent au draw-band
0 certificat invalide ne peut bloquer le draw-band
```

Télémétrie :

```text
taux de survie total du tip
survie par oracle_tier
survie par strate p1/p2/p3/p4
survie par provenance et par tour
```

Un taux total du tip inférieur à 90 % déclenche une investigation par tier et provenance. Il ne doit pas conduire à promouvoir artificiellement `SEARCH_STABLE` au rang de preuve.

---

## 4. Promotion inter-tours

### 4.1 Deux régimes explicites

`promotion_gate.py` doit exposer :

```text
--regime young
--regime established
```

Le même outil peut produire les deux décisions suivantes, qui doivent rester séparées dans le manifest :

- décision opérationnelle de promotion ;
- conclusion scientifique ou état de la sonde.

### 4.2 Régime jeune : T1-bis, T2, T3

But : permettre à une amélioration généraliste de composer avant d’exiger une hausse de conversion.

Pour chaque tour `t`, comparer le candidat :

1. au parent qui a généré son corpus ;
2. à la référence fixe T0/bootstrap de la sonde.

La conversion WDL-grounded est mesurée et ventilée, mais n’est pas une condition de promotion en régime jeune.

#### Règle de rejet

```text
REJET si la borne haute de l’intervalle de confiance du taux
est strictement inférieure à 0,500
contre le parent OU contre la référence fixe.
```

Autrement dit :

- résultat positif : promotion autorisée ;
- résultat neutre ou incertain : promotion autorisée pendant la sonde bornée ;
- régression statistiquement établie : promotion interdite.

Cette double comparaison empêche une dérive cumulative par random walk de plusieurs modèles successivement un peu plus faibles.

Le régime jeune est limité à T1-bis→T3. Il ne peut pas devenir la règle permanente de la campagne.

### 4.3 Régime établi

Après la sonde :

```text
promotion =
    généraliste non-régressif
    ET conversion en hausse sur une fenêtre de deux tours
```

La définition exacte de la hausse de conversion, de sa marge et de la fenêtre doit être pré-engagée avant la campagne longue.

### 4.4 Sortie obligatoire de `promotion_gate.py`

```json
{
  "regime": "young",
  "tour": "T1-bis",
  "candidate_sha": "...",
  "parent_sha": "...",
  "fixed_reference_sha": "...",
  "vs_parent": {
    "rate": 0.5,
    "ci_low": 0.0,
    "ci_high": 1.0,
    "n": 0,
    "decision": "pass | reject"
  },
  "vs_fixed_reference": {
    "rate": 0.5,
    "ci_low": 0.0,
    "ci_high": 1.0,
    "n": 0,
    "decision": "pass | reject"
  },
  "conversion": {
    "global": 0.0,
    "p1_net": 0.0,
    "p2_moyen": 0.0,
    "p3_mince": 0.0,
    "p4_egal": 0.0
  },
  "promotion_decision": "promote | reject",
  "scientific_status": "continue_probe | stop_technical | stop_regression | complete_probe",
  "reasons": []
}
```

### 4.5 d9 contre Scan

La mesure d9 contre Scan reste une télémétrie et une mesure de clôture. Elle ne devient pas un troisième veto inter-tour sans nouvelle décision pré-engagée.

---

## 5. T1-bis : recette assemblée

T1-bis est le premier passage complet de la recette multi-tours. Il ne doit pas être traité comme un simple fit supplémentaire du DOE.

### 5.1 Génération

```text
pilote             = bootstrap / T0 figé
labels de sortie   = --label-src-out actif
gymnase            = G1
quota               = quota de POSITIONS, pas multiplication G4
cap-arbiter         = actif
provenance          = obligatoire
hashes              = corpus, positions, shards et configuration
```

Le G1 doit conserver sa composition et sa pointe p3/p4 ; il ne doit pas être redéfini implicitement pendant la sonde.

### 5.2 Relabel complet

```text
oracle              = d14 + EGDB
confirmation        = selon politique CERT/SEARCH_STABLE
priorité            = section 3
protection tip      = invariants blocks_draw_band
télémétrie          = canaux TB/CERT/SEARCH_STABLE/D14/on-policy
cache agrégé        = vérifié avant lancement
restart-on-death    = actif dans les jauges concernées
```

Le relabel doit produire un manifest de provenance par record et un résumé par canal.

### 5.3 Fit

```text
outil               = wdl_finetune
anchor              = 0.05
cellule contrôle    = lambda très élevée / retour près de la référence
z-stats             = obligatoires
déplacement poids   = global + groupes EXTRA/PST/patterns
seed                = figée
configuration       = committée
```

La cellule lambda élevée est un garde-fou de pipeline, pas un candidat à promouvoir.

### 5.4 Jauges

```text
conversion          = WDL-grounded v2
corpus conversion   = 1600 figé
ventilation         = p1_net, p2_moyen, p3_mince, p4_egal
gate généraliste    = candidat vs parent
gate référence      = candidat vs T0/bootstrap fixe
d9 vs Scan          = télémétrie
```

Chaque jauge doit consigner :

- N demandé ;
- N joué ;
- W/D/L ;
- erreurs ;
- redémarrages ;
- taux et intervalle ;
- hashes du corpus ;
- SHA moteur et poids ;
- paramètres exacts.

### 5.5 PASS pré-engagé

T1-bis passe si :

```text
aucune régression généraliste statistiquement établie
contre le parent et contre la référence fixe

ET

artefacts complets et chargeables

ET

canaux de labels cohérents

ET

100 % des TB_EXACT et CERT_PROOF valides protégés

ET

jauge de conversion lisible dans les quatre strates

ET

manifests et hashes complets
```

Une conversion plate n’empêche pas la promotion en régime jeune.

### 5.6 FAIL

#### Régression généraliste établie

```text
ne pas promouvoir
ne pas lancer T2
ouvrir une investigation ciblée
```

Premiers suspects :

- divergence par shard ;
- provenance des labels ;
- fuite du draw-band ;
- corpus ou hashes non appariés ;
- config du fit ;
- déplacement des poids ;
- ressource EGDB ou moteur instable.

#### Échec technique

```text
aucune conclusion scientifique
corriger le harnais
reprendre depuis le dernier artefact vérifié
```

Il est interdit de transformer un échec technique en PASS par simple desserrage de seuil.

---

## 6. Exécution T2 et T3

Après PASS de T1-bis :

```text
champion T1-bis génère T2
→ même recette ADJ + G1
→ mêmes corpus de jauge figés
→ promotion --regime young
```

Après PASS de T2 :

```text
champion T2 génère T3
→ même recette ADJ + G1
→ mêmes corpus de jauge figés
→ verdict final de sonde
```

Aucun changement de recette ne doit intervenir entre les tours, sauf correction technique documentée qui n’altère pas le traitement scientifique.

À chaque tour, publier :

- composition du corpus ;
- sources de labels ;
- survie du tip par tier et strate ;
- z-stats ;
- déplacement des poids ;
- conversion globale et p1–p4 ;
- gate vs parent ;
- gate vs référence fixe ;
- d9 vs Scan ;
- décision de promotion ;
- inventaire mining passif.

---

## 7. Mining passif des jets de gain

### 7.1 Principe

Le mining peut utiliser les trajectoires T1-bis→T3, mais il ne participe pas causalement à la sonde.

```text
trajectoires
→ extraction
→ inventaire versionné
→ aucun fit
→ aucune injection
→ aucune modification de la génération suivante
→ aucune influence sur promotion_gate
```

### 7.2 Unité et split

L’unité statistique est le parent décisionnel, pas chaque sibling pris indépendamment.

Les splits futurs doivent être faits par :

- parent ;
- partie source ;
- éventuellement famille canonique de position.

Aucun parent ou sibling associé ne peut fuiter entre train et holdout.

### 7.3 Événements à extraire

Dès la première version :

```text
parent WIN
→ enfant joué DRAW

parent WIN
→ enfant joué LOSS
```

`WIN→LOSS` ne doit pas être reporté à une version ultérieure.

Les siblings sont inventoriés, mais leur certification complète peut attendre la phase teacher.

### 7.4 Schéma minimal

```json
{
  "probe_tour": "T1-bis | T2 | T3",
  "source_game_id": "...",
  "parent_id": "...",
  "parent_fen": "...",
  "parent_hash": "...",
  "played_move": "...",
  "played_child_fen": "...",
  "played_child_oracle": "WIN | DRAW | LOSS | AMBIGUOUS",
  "event_type": "WIN_TO_DRAW | WIN_TO_LOSS",
  "siblings": [],
  "oracle_provenance": {},
  "engine_sha": "...",
  "weights_sha": "...",
  "trajectory_hash": "..."
}
```

### 7.5 Sorties par tour

- nombre de parties inspectées ;
- nombre de parents WIN ;
- WIN→DRAW ;
- WIN→LOSS ;
- parents uniques ;
- distribution par nombre de pièces ;
- distribution p1–p4 ;
- distribution par tier oracle ;
- cap d’événements par parent ;
- hashes et provenance.

---

## 8. Verdict de la sonde

### 8.1 Cas A — généraliste compose et conversion monte

```text
signal multi-tours positif
→ confirmer à budget plus large
→ préparer campagne longue ADJ + G1
→ teacher non prioritaire immédiatement
```

### 8.2 Cas B — généraliste compose, conversion reste plate

```text
meilleure vérité WDL assimilée
mais crédit causal toujours absent
→ lancer smoke teacher A/B1/B2/B3
```

### 8.3 Cas C — généraliste neutre, conversion monte

```text
signal spécialisé possible
→ confirmer avec N supérieur
→ vérifier absence de coût caché contre référence fixe et Scan
```

### 8.4 Cas D — généraliste neutre et conversion plate

```text
sonde rapide close sans signal
→ smoke teacher devient la prochaine expérience causale
```

### 8.5 Cas E — régression généraliste établie

```text
stop sonde
→ investigation des labels, corpus, fit et progression inter-tours
→ ne pas ouvrir teacher tant que la régression de base n’est pas comprise
```

---

## 9. Spécification du futur teacher, inchangée

Le teacher reste post-sonde.

### 9.1 Oracle symétrique

Parents, enfants joués et siblings doivent utiliser la même hiérarchie :

```text
TB_EXACT
>
CERT_PROOF vérifié
>
SEARCH_STABLE
>
AMBIGUOUS
```

### 9.2 Quatre cellules

```text
A   WDL adjudicated
B1  WDL + siblings oracle comme records ordinaires
B2  préférence statique
B3  préférence through-search / leaf-mode
```

### 9.3 Contrôles M1

- cap de records par parent ;
- cap de masse de loss par parent ;
- normalisation des poids ;
- split par parent/game ;
- distribution WDL ;
- distribution du nombre de pièces ;
- mouvement des poids ;
- gates communs ;
- mêmes parents et paires entre B2 et B3.

### 9.4 Interdictions avant le verdict de sonde

- aucun fit teacher ;
- aucune injection de siblings ;
- aucun objectif joint WDL + rank ;
- aucune banque `DEEP_EG` ;
- aucune profondeur-par-phase d16/d18 ;
- aucune réintroduction de G4 ;
- aucun classement MTC entre enfants tous gagnants.

---

## 10. Audit MTC et ressources

Avant la sonde :

```text
vérifier que JASS_EGDB_MTC_PATH est réellement actif
consigner la valeur et la version
vérifier l’accès en lecture par tous les workers
faire un smoke concurrent court
calculer le cache agrégé maximal
```

L’audit MTC est une vérification d’environnement. Il ne devient pas un objectif d’apprentissage.

---

## 11. Tests obligatoires avant lancement

### 11.1 Labels et draw-band

- TB_EXACT survit au draw-band ;
- CERT_PROOF vérifié survit au draw-band ;
- CERT_PROOF non vérifié est rejeté ou déclassé ;
- SEARCH_STABLE ne peut pas poser `blocks_draw_band=true` ;
- résolution identique parent/enfant/sibling ;
- compteurs de survie par tier exacts.

### 11.2 Promotion

- régime jeune accepte un résultat neutre/incertain ;
- régime jeune rejette si `ci_high < 0.5` contre le parent ;
- régime jeune rejette si `ci_high < 0.5` contre la référence fixe ;
- régime établi exige la conversion sur fenêtre ;
- manifest contient les deux comparaisons ;
- T1-bis, T2 et T3 sont les seuls tours autorisés en `young` dans le runner de sonde.

### 11.3 Mining passif

- aucune sortie mining n’est consommée par le fit ;
- aucune sortie mining n’est consommée par la génération ;
- aucune sortie mining n’est consommée par la promotion ;
- split futur par parent/game ;
- WIN→DRAW et WIN→LOSS présents ;
- hashes des trajectoires consignés.

### 11.4 Infrastructure

- restart-on-death testé ;
- `n_restarts` agrégé ;
- cache agrégé calculé avant lancement ;
- artefacts intermédiaires chargeables ;
- reprise depuis checkpoint vérifiée ;
- erreurs et timeouts séparés.

---

## 12. Livrables attendus de Claude Code

### Phase 0 — pré-sonde

1. règle `blocks_draw_band` et vérificateur de certificat ;
2. compteurs de survie du tip ;
3. `promotion_gate.py --regime young|established` ;
4. comparaison parent + référence fixe ;
5. manifests JSON ;
6. audit MTC ;
7. garde cache×processus ;
8. tests unitaires et intégration ;
9. runner T1-bis reproductible.

### Phase 1 — sonde

1. T1-bis assemblé ;
2. PASS/FAIL committé ;
3. T2 si PASS ;
4. T3 si PASS ;
5. mining passif par tour ;
6. rapport final de sonde.

### Phase 2 — post-sonde

Selon le verdict :

- confirmation et campagne longue ; ou
- smoke teacher A/B1/B2/B3.

---

## 13. Critères de bon pour lancement

Claude Code peut lancer T1-bis uniquement lorsque :

```text
[ ] tests labels/draw-band verts
[ ] tests promotion verts
[ ] tests mining hors-boucle verts
[ ] audit MTC documenté
[ ] cache agrégé sous budget
[ ] corpus et jauges figés/hashés
[ ] référence fixe identifiée
[ ] seeds et paramètres committés
[ ] manifests de sortie définis
[ ] aucun front teacher/DEEP_EG ouvert
```

---

## 14. Verdict final v3.2

La conception est figée et les prérequis d’exécution sont maintenant complets.

```text
ADJ + G1
+
priorité de labels vérifiable
+
promotion jeune protégée contre la dérive cumulative
+
T1-bis assemblé à PASS pré-engagé
+
mining strictement passif
```

constitue la seule ligne active.

**Feu vert d’implémentation pour Claude Code.**

Le prochain événement scientifique attendu n’est pas un nouveau débat de conception, mais le résultat reproductible de T1-bis, puis de T2 et T3 si les gates de régime jeune passent.
