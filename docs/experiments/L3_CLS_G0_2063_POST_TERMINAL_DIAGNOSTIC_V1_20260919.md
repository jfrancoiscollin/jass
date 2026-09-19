# CLS-G0 2063 — diagnostic post-terminal autorise le 19 septembre 2026

## Mandat et statut

JFC a explicitement autorise « Ok va y » apres la proposition d'examiner les 512 positions deja produites, sans nouveau fit, search, match, modification de seuil ou requalification du FAIL. Il s'agit d'une analyse descriptive sur donnees deja consommees, pas d'une nouvelle confirmation. Aucun candidat n'est selectionne ou retune.

Source unique : `cpx62-2063-l3-cls-g0-hier-runtime-rehearsal-v1`, tentative `20260919T155826Z-a6f9fa6f`, code `a6f9fa6fbdc66f8d89dd7a5e8c196422cf98a28a`. Le terminal `CLS_G0_RUNTIME_CATASTROPHE_GATE_FAIL_V1` reste immuable. CURRICULUM reste champion. Aucun changement aux fichiers du gate, du probe natif, du moteur ou des anciens resultats.

## Lectures bornees et exhaustives

Authentifier l'inventaire, les checksums, l'identite, l'exit 0 et le recu Launch-V2 `a5b9a83a6a7932920ca23cf1cd7d15f67855c12835ddecb18c4f67bc9b0d6e59`. Lire exactement sept artefacts : probe.tsv, probe-report.json, g0-root-ids.txt, g0-deep512.tsv, g0-deep-reference.tsv, scientific-summary.json et launch-receipt.json. Maximum 512 KiB/fichier et 2 MiB au total. Ne pas lire les poids, corpus, nouvelles cibles ou journaux historiques d'entrainement.

Conserver les 512 racines et leur ordre gele : 128 par phase, 1024 lignes parent/candidat, budget de recherche historique 200k, reference historique CURRICULUM 1M. Recouper les 30 recus HIER manquants et les zero recus parent manquants avec le terminal. Toute incoherence arrete l'analyse, sans inventer de resultat.

## Classification fixee avant lecture des tables

Pour chaque racine : d*=max(1, profondeur_parent-1).

- RECEIPT_PRESENT : recu nodes-to-target effectivement publie.
- DEPTH_BELOW_TARGET : recu absent et profondeur candidate terminee < d*. Ce fichier etablit un retard de profondeur nominale a budget fixe, pas une perte en force.
- TARGET_REACHED_NO_QUALIFYING_RECEIPT : profondeur candidate >= d* mais recu exact/full-root absent. Les traces detaillees n'etant pas publiees, ne pas deviner le predicat manquant ni declarer un bug.

Rapporter les effectifs globaux, par phase et dans les deux sous-groupes. Decrire profondeur, NPS et choix de coup pour l'ensemble des 512. Les ratios nodes-to-target ne portent que sur les paires observables : aucune imputation, aucun surrogate, aucune extrapolation aux manquants. La reference CURRICULUM 1M n'est pas une verite terrain ; accord avec celle-ci ne vaut pas qualite du coup ou Elo. Aucun bootstrap, test de significativite ni nouveau PASS/FAIL.

## Execution et validation

Lecture/calcul seulement, Python standard, un processus, zero nouveau fit/search/self-play/match/alpha/promotion/bake. Le runner publie de nouveaux artefacts dans une nouvelle tentative ; aucune ecriture dans 2063. Sorties : diagnostic JSON, tableau exhaustif TSV, authentification source, resume et manifeste, execution-evidence Launch-V2. Dix tests locaux executes avec succes (classification, 512 racines, identites, quotas, donnees invalides, doublons, ordre, aller-retour, pas de surrogate) ; suite reprise en CI et preflight cible. La limite de lecture borne la memoire et le disque ; le stage doit avoir un timeout fini. Aucun reseau ou build moteur dans les tests synthetiques.

## Limites et suite

L'analyse peut expliquer la classe du rejet, pas son mecanisme causal complet ni la force du candidat. Toute instrumentation necessitant de nouvelles recherches, toute revision du gate ou nouvelle recette est hors de ce diagnostic. `scientific_verdict=null`, classe `EXPLORATORY_CONSUMED_DATA`, aucun enchainement de recherche automatique.
