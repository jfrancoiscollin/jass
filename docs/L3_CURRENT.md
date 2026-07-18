# L3-PURE — état courant et registre de résultats

> **Mis à jour : 2026-07-18**
> **Statut scientifique : `implementation_review`**
> **Spécification normative :** [L3_PURE_PLAN.md](L3_PURE_PLAN.md)
> **Mémoire du projet et portes closes :** [PROJECT_RESULTS.md](PROJECT_RESULTS.md)

Ce document est la source de vérité vivante de la lignée `L3-PURE`. Il reste
court, factuel et mis à jour après chaque changement d'état ou résultat. Il ne
redéfinit pas la recette : en cas de conflit, la spécification prévaut jusqu'à
ce qu'une décision explicite la modifie.

## 1. État en une phrase

La première PR C0 est en revue : elle implémente les fondations d'une lignée
8cf partie d'une graine matérielle, entraînée uniquement sur les WDL terminaux
de son propre autojeu, et prépare un A/B entre autojeu ordinaire et frontière
mobile de conversion. Aucun job L3 n'est encore soumis.

## 2. Identité de l'expérience active

| Champ | Valeur |
|---|---|
| Lignée | `L3-PURE` |
| Expérience | `C0 — causalité de la frontière mobile` |
| Phase | revue d'implémentation et pré-calibration |
| PR | [#344](https://github.com/jfrancoiscollin/jass/pull/344) |
| Branche | `agent/l3-pure-c0-foundations` |
| Référence code | à figer après merge |
| Champion externe de contrôle | `gen2-mmto`, figé ; évaluation seulement |
| Référence de conversion historique | T3 `ccx33`, figée ; évaluation seulement |
| Jobs actifs | aucun |
| Dernière décision | préparer C0 A/B, ne rien queuer avant revue et calibration |

## 3. Invariants à vérifier à chaque run

- géométrie `8cf` figée ;
- graine G0 : homme `1`, dame `3`, tout terme appris à zéro ;
- aucune position, partie, cible, préférence ou politique Scan/Gen2/maître ;
- autojeu de la lignée uniquement ;
- cible du fit : résultat terminal WDL uniquement ;
- partie au ply-cap entièrement censurée, jamais transformée en nul ;
- EGDB seulement après atteinte naturelle d'une position couverte ;
- aucun deep relabel, MMTO, adjudication matérielle ou anchor parent ;
- warm-start du fit autorisé comme initialisation numérique seulement ;
- holdout par ouverture complète ;
- score et WDL des seeds de frontière neutralisés avant leur rejeu ;
- provenance, seeds, SHA, compteurs et exclusions publiés dans les manifests.

Toute violation rend le run `invalid_science`, même si le processus termine
avec un code de sortie nul.

## 4. État de l'implémentation C0

| Élément | État | Preuve ou reste à faire |
|---|---|---|
| `--drop-plycap` | implémenté | syntaxe C++ validée ; smoke binaire réel attendu en CI/box |
| sidecar `JSM1` | implémenté | tests merge/split synthétiques verts |
| split holdout par ouverture | implémenté | paires d'ouverture conservées dans le même fold |
| mineur de frontière | implémenté | sorties score/WDL à zéro ; aucun input teacher |
| `train_stream --warm-start` | implémenté | même optimum L2 que le départ zéro dans le test jouet |
| `--holdout-count` | implémenté | tail holdout exact après split |
| runner v3 d'un bras | préparé | garde nproc/disque/timeout/progress/manifests |
| bras A `ccx33` | préparé hors queue | micro-calibration requise |
| bras B `cpx62` | préparé hors queue | micro-calibration requise |
| build CMake + link | à valider | CI GitHub ou box |
| smoke moteur JNNW↔JSM1 | à valider | vérifier alignement sur une vraie partie |
| évaluation haut-N A/B | hors PR C0 actuelle | à préparer après production des G3 |

## 5. Jobs préparés

| Bras | Job | Générations | Autojeu frais | Particularité | État |
|---|---|---:|---:|---|---|
| A | `ccx33-l3-pure-c0-a-v1` | 3 | 500 k / génération | contrôle pur | hors queue |
| B | `cpx62-l3-pure-c0-b-v1` | 3 | 500 k / génération | 25 % frontière en G2/G3 | hors queue |

Paramètres appariés : mêmes seeds, 8 shards, d8/d8/d10, huit plies
d'ouverture aléatoires, epsilon 8 % décroissant à zéro au ply 60,
`max_plies=260`, holdout 1/10 par ouverture, L2 `3e-5`.

L'ETA provisoire est de 14–18 h par bras à partir de l'ancre `0665`. Elle n'est
pas une autorisation de lancement. Avant GitOps, publier pour chaque box :

1. `nproc` réellement mesuré ;
2. débit d'une micro-sonde avec la recette exacte ;
3. volume et ETA recalculés ;
4. timeout par shard dérivé du débit ;
5. espace disque disponible ;
6. go JFC explicite et `FULL_RUN_APPROVED=1`.

## 6. Résultats C0

### 6.1 Santé technique par génération

| Bras | Génération | Statut | Records éligibles | Parties ply-cap | Samples exclus | Holdout | Log-loss | SHA modèle |
|---|---:|---|---:|---:|---:|---:|---:|---|
| A | G1 | — | — | — | — | — | — | — |
| A | G2 | — | — | — | — | — | — | — |
| A | G3 | — | — | — | — | — | — | — |
| B | G1 | — | — | — | — | — | — | — |
| B | G2 | — | — | — | — | — | — | — |
| B | G3 | — | — | — | — | — | — | — |

### 6.2 Provenance et frontière

| Bras | Génération | Standard | Frontière | Candidats échec | Candidats convertis | Seeds retenus | Teacher externe |
|---|---:|---:|---:|---:|---:|---:|---:|
| A | G1 | — | 0 | n/a | n/a | 0 | 0 |
| A | G2 | — | 0 | n/a | n/a | 0 | 0 |
| A | G3 | — | 0 | n/a | n/a | 0 | 0 |
| B | G1 | — | 0 | — | — | — | 0 |
| B | G2 | — | — | — | — | — | 0 |
| B | G3 | — | — | — | — | — | 0 |

### 6.3 Conversion finale

| Modèle | Global | P1 net | P2 moyen | P3 mince | P4 égal | N | IC / notes |
|---|---:|---:|---:|---:|---:|---:|---|
| A-G3 | — | — | — | — | — | — | — |
| B-G3 | — | — | — | — | — | — | — |
| B−A | — | — | — | — | — | — | — |

### 6.4 Force généraliste

| Comparaison | W | D | L | Rate | IC95 | Elo | Verdict |
|---|---:|---:|---:|---:|---:|---:|---|
| B-G3 vs A-G3 | — | — | — | — | — | — | — |
| A-G3 vs référence fixe | — | — | — | — | — | — | — |
| B-G3 vs référence fixe | — | — | — | — | — | — | — |

## 7. Décision C0 pré-engagée

Le mécanisme de frontière est conservé si, à budget égal :

- `conversion(B-G3) − conversion(A-G3) >= +0,03` ;
- P3 mince progresse de façon visible ;
- aucune régression généraliste de B contre A n'est établie.

| Résultat | Décision |
|---|---|
| frontière positive et non régressive | conserver le mécanisme pour la campagne longue |
| frontière plate, bras A sain | retirer la frontière v1 ; poursuivre l'hypothèse de lignée pure |
| frontière régressive | retirer la frontière et diagnostiquer la distribution injectée |
| A et B tous deux techniquement invalides | corriger l'infrastructure et rejouer à l'identique |
| A et B sains mais faibles à G3 | ne pas conclure au plafond ; C0 n'est qu'une sonde à trois générations |

## 8. Journal de décisions L3

| Date | Événement | Décision | Référence |
|---|---|---|---|
| 2026-07-18 | choix d'une nouvelle lignée sans professeur externe | ouvrir `L3-PURE` | `L3_PURE_PLAN.md` |
| 2026-07-18 | fondations C0 proposées | PR brouillon, jobs hors queue | PR #344 |

Chaque nouvelle ligne doit indiquer un fait observé, la décision qu'il entraîne
et le manifest ou SHA qui permet de le reproduire. Les discussions et pistes
non exécutées n'entrent pas dans ce tableau.

## 9. Prochaine action unique

Faire relire la PR #344 par Claude Code, résoudre ses remarques, obtenir un
build/smoke moteur vert, puis micro-calibrer les deux bras. Aucun déplacement
vers `jass-control/queue/pending/` avant ces quatre étapes.
