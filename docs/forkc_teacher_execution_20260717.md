# Fork C et teacher causal — plan d'exécution après T3

Date : 2026-07-17. Statut : implémenté et jobs préparés, aucun job soumis.

## Lecture des résultats

T1-bis, T2 et T3 sont plats à la fois sur la conversion
(`0,667 / 0,657 / 0,669`) et sur le gate absolu T0
(`0,5125 / 0,490 / 0,5033`). C'est le cas D de
`codex_review_v3_2.md` : la prochaine expérience causale principale est le
smoke teacher A/B1/B2/B3.

Le bundle publié par le job 773 reste une expérience utile mais étroite : ses
poids matériels (`0,3 / 0,9 / 0,06 / 0,015`) sont exactement `0,3×` le
bootstrap fort (`1 / 3 / 0,2 / 0,05`). Il teste donc surtout un changement
d'échelle, de pruning et de bassin d'optimisation, pas une nouvelle source de
connaissance. Un tour C complet n'est lancé que si C0 montre un comportement
et un signal de conversion réellement différents.

## Séquence pré-engagée

| Étape | Job préparé | Go | Stop |
|---|---|---|---|
| C0 | `cpx62-0774-forkc-c0-v1` | divergence policy raw/refit ≥ 5 %, Δ moyen p3/p4 ≥ +0,02, pas de régression vs T0 fort | même policy, conversion plate, régression ou mesure incomplète |
| T1-C | `cpx62-0775-forkc-t1-v1` | C0=`proceed_t1`; gates parent, fixed faible et T0 fort tous non-régressifs | aucun enchaînement automatique T2 |
| Mining | `ccx33-0776-teacher-mine-t3-v1` | au moins un parent WIN→DRAW/LOSS avec sibling WIN certifié | corpus vide : smoke non soumis |
| Smoke | `ccx33-0777-teacher-smoke-v1` | ≥ 50 parents teacher ; même jauge et mêmes gates pour A/B1/B2/B3 | aucune cellule Δp3/p4 ≥ +0,02 sans régression |

Le fork C et le mining teacher sont indépendants. Le teacher peut partir du T3
clos sans attendre C0.

## Ce que C0 isole

1. Agreement des meilleurs coups strong/weak à profondeur et positions figées.
2. Refit du **même** corpus `adj.jnnw` T1 depuis le bootstrap faible.
3. Agreement strong/refit, gate refit vs T0 fort et conversion p3/p4.

Ce montage sépare l'effet « autre bassin d'optimisation » de l'effet « autre
distribution générée ». Si C0 est plat, payer une régénération T1-C ne se
justifie pas.

## Contrat teacher A/B1/B2/B3

Le mineur accepte deux sources :

- les nouveaux sidecars `trajectories.jsonl.gz`, avec frontières de partie et
  coups joués explicites ;
- les anciens couples `gen.jnnw.gz` / `deep.jnnw.gz`. Une adjacency historique
  n'est reconnue que si le moteur prouve que le record suivant est un enfant
  légal ; sinon elle devient une frontière de partie.

Pour chaque parent quiet certifié WIN dont le coup joué mène à DRAW/LOSS, tous
les siblings sont soumis au même oracle d14+EGDB. Un événement n'entre dans le
teacher que si au moins un sibling reste WIN.

À chaque nouveau tour natif, `probe_mining.py` transforme déjà le sidecar et le
`deep.jnnw` aligné en `mining-events.json` / `mining-summary.json`, puis
inventorie les siblings légaux comme **non certifiés**. Cette étape reste hors
boucle : ses sorties ne sont lues ni par le fit ni par la promotion.

- A : candidat WDL adjudicated T3, inchangé.
- B1 : A + siblings oracle comme records WDL ordinaires.
- B2 : A + rank-finetune sur l'enfant WIN et l'enfant joué DRAW/LOSS.
- B3 : mêmes parents, bons/mauvais coups et split que B2, mais feuilles de
  recherche (`leaf-mode`).

Le split est par partie. B2 et B3 ont exactement une paire par parent ; le mode
`--dominated-moves` empêche B3 d'ajouter des siblings non appariés. Le verdict
préfère l'objectif le plus simple si les gains diffèrent de moins de `0,005`.

## Référence absolue et garde-fous

Le runner natif accepte désormais un second bundle immuable via
`ABSOLUTE_INPUTS_PREFIX`. Avec `REQUIRE_ABSOLUTE_REFERENCE=1`, une comparaison
absente ou incomplète est technique et une régression établie bloque la
promotion. Le fork faible ne peut donc plus se promouvoir uniquement contre
son propre parent/fixed affaibli.

Les artefacts externes consommés par C0 et le teacher sont relus à travers
`manifest.json`, `inventory.json` et `checksums.sha256`. Les jobs préparés sont
hors des répertoires réclamés par les runners ; leur présence dans la PR ne
déclenche rien.
