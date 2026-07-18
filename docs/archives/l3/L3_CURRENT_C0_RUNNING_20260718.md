# L3-PURE — état courant et registre de résultats

> **ARCHIVE FIGÉE LE 18 JUILLET 2026.** État C0 au moment où les bras complets étaient encore annoncés en cours ; ne plus modifier.

> **Mis à jour : 2026-07-18**
> **Statut scientifique : `c0_full_running`**
> **Spécification normative :** [L3_PURE_PLAN.md](../../L3_PURE_PLAN.md)
> **Mémoire du projet et portes closes :** [PROJECT_RESULTS.md](../../PROJECT_RESULTS.md)

Ce document est la source de vérité vivante de la lignée `L3-PURE`. Il reste
court, factuel et mis à jour après chaque changement d'état ou résultat. Il ne
redéfinit pas la recette : en cas de conflit, la spécification prévaut jusqu'à
ce qu'une décision explicite la modifie.

## 1. État en une phrase

Le correctif #346 et les recalibrations `0788/0789` sont verts de bout en bout ;
les deux bras complets appariés C0 sont lancés sur ccx33 et cpx62.

## 2. Identité de l'expérience active

| Champ | Valeur |
|---|---|
| Lignée | `L3-PURE` |
| Expérience | `C0 — causalité de la frontière mobile` |
| Phase | exécution des deux bras complets C0 |
| PR | [#344](https://github.com/jfrancoiscollin/jass/pull/344) + correctif [#346](https://github.com/jfrancoiscollin/jass/pull/346), mergées |
| Branche | `develop` |
| Référence code calibrée | `c80c6792df1801ae6c0797700ce5333f3f20c1f3` |
| Champion externe de contrôle | `gen2-mmto`, figé ; évaluation seulement |
| Référence de conversion historique | T3 `ccx33`, figée ; évaluation seulement |
| Jobs actifs | `ccx33-0790-l3-pure-c0-a-v1`, `cpx62-0791-l3-pure-c0-b-v1` |
| Dernière décision | calibrations vertes + go JFC : lancer les deux bras complets appariés |

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
- fingerprint de quiescence identique pour le jeu et le label, explicitement publié.

Toute violation rend le run `invalid_science`, même si le processus termine
avec un code de sortie nul.

## 4. État de l'implémentation C0

| Élément | État | Preuve ou reste à faire |
|---|---|---|
| `--drop-plycap` | implémenté | syntaxe C++ validée ; smoke binaire réel attendu en CI/box |
| sidecar `JSM1` | implémenté | tests merge/split synthétiques verts |
| split holdout par ouverture | implémenté | paires d'ouverture conservées dans le même fold |
| mineur de frontière | implémenté | sorties score/WDL à zéro ; aucun input teacher |
| `train_stream --warm-start` | validé | #346 accepte la base v3 auto-descriptive ; G1 zéro-init, G2/G3 depuis le student précédent |
| `--holdout-count` | implémenté | tail holdout exact après split |
| runner v3 d'un bras | préparé | garde nproc/disque/timeout/progress/manifests |
| fingerprint quiescence | explicité pour les futurs runs | chaîne, SHA-256, portée et code SHA publiés ; aucune modification des jobs en cours |
| bras A `ccx33` | en cours | calibration `0788` intégralement verte |
| bras B `cpx62` | en cours | calibration `0789` verte, mineur de frontière inclus |
| build CMake + link | validé sur les deux boxes | `0785/0786` atteignent génération et fit |
| smoke moteur JNNW↔JSM1 | validé | 3 200 records éligibles par bras, ply-cap 0 % |
| évaluation haut-N A/B | hors PR C0 actuelle | à préparer après production des G3 |

## 5. Jobs préparés

| Bras | Job | Générations | Autojeu frais | Particularité | État |
|---|---|---:|---:|---|---|
| A | `ccx33-0790-l3-pure-c0-a-v1` | 3 | 500 k / génération | contrôle pur | lancé |
| B | `cpx62-0791-l3-pure-c0-b-v1` | 3 | 500 k / génération | 25 % frontière en G2/G3 | lancé |

Paramètres appariés : mêmes seeds, 8 shards, d8/d8/d10, huit plies
d'ouverture aléatoires, epsilon 8 % décroissant à zéro au ply 60,
`max_plies=260`, holdout 1/10 par ouverture, L2 `3e-5`.

Empreinte effective des jobs `0790/0791` sur le SHA calibré `c80c6792` :

```text
qs_threat_ext=1,qs_sacs=1,qs_sacs_depth0_only=1,qs_forcing_depth=0,qs_promo_depth=0
```

Ces deux jobs héritent encore de ces mêmes valeurs depuis `SearchParams{}` et
restent donc causalement appariés ; ils ne doivent pas être redémarrés. À partir
du prochain run ou rerun sur un nouveau SHA, le runner passe explicitement la
chaîne au moteur et la publie avec son SHA-256 dans `l3-run-config.json` et
`l3-pure-manifest.json`.

Les recalibrations `0788/0789` projettent chacune environ **1,14 h** à partir
d'un débit d8 agrégé de 64 k records/min. Le tour G3 à d10 peut prolonger cette
estimation ; le timeout conservateur reste de 6 h par shard. Le go JFC et
`FULL_RUN_APPROVED=1` ont été donnés après les deux calibrations vertes.

Avant tout futur GitOps, publier pour chaque box :

1. `nproc` réellement mesuré ;
2. débit d'une micro-sonde avec la recette exacte ;
3. volume et ETA recalculés ;
4. timeout par shard dérivé du débit ;
5. espace disque disponible ;
6. go JFC explicite et `FULL_RUN_APPROVED=1`.

## 6. Résultats C0

### 6.0 Micro-calibration et diagnostic

| Job | Box | Résultat utile | Verdict |
|---|---|---|---|
| `ccx33-0785-l3cal-a` | ccx33, `nproc=8` | 3 200 records en 3 s ; ply-cap 0 % | abort fit, `fit_path_ok=false` |
| `cpx62-0786-l3cal-b` | cpx62, `nproc=16` | 3 200 records en 4 s ; ply-cap 0 % | abort fit, `fit_path_ok=false` |
| `cpx62-0787-l3diag` | cpx62, `nproc=16` | 500 samples / 19 parties ; ply-cap 0 % | seed jouable C++, rejeté par `load_v3_weights_float` |
| `ccx33-0788-l3cal-a-v2` | ccx33, `nproc=8` | 3 200 records en 3 s ; ply-cap 0 % | `status=ok`, fit/reload v3 OK |
| `cpx62-0789-l3cal-b-v2` | cpx62, `nproc=16` | 3 200 records en 3 s ; ply-cap 0 % | `status=ok`, fit/reload v3 + mineur OK |

Cause exacte : `make_bootstrap_eval.py` écrit un PJTW valide de magic
`0x57544A50`, version `0x203` (base v3 + bit auto-descriptif). Le loader Python
comparait le mot complet à `3`. Ce même défaut aurait aussi empêché G2/G3 de
charger les students v3 produits par `train_stream`. La réparation conserve G0
comme seed de jeu, démarre le fit G1 à zéro, puis warm-starte G2/G3 depuis le
student précédent conformément au §2.3.

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
| 2026-07-18 | micro-calibrations A/B | génération saine, fit invalide ; aucun résultat scientifique | `0785`, `0786` |
| 2026-07-18 | diagnostic du fit | corriger le décodage de version et réserver le warm-start aux students précédents | `0787` |
| 2026-07-18 | correctif et recalibrations verts | lancer les deux bras complets après go JFC | #346, `0788`, `0789` |

Chaque nouvelle ligne doit indiquer un fait observé, la décision qu'il entraîne
et le manifest ou SHA qui permet de le reproduire. Les discussions et pistes
non exécutées n'entrent pas dans ce tableau.

## 9. Prochaine action unique

Suivre `0790/0791` génération par génération, publier les compteurs de santé et
mettre à jour ce registre à chaque finalisation. Ne préparer l'évaluation haut-N
qu'après deux G3 techniquement valides.
