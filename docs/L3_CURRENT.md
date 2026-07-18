# L3-PURE — état courant et registre de résultats

> **Mis à jour : 18 juillet 2026**
> **Statut scientifique : `c0_generation_complete_highn_failed; c1_q1_pr_prepared`**
> **Spécification normative :** [L3_PURE_PLAN.md](L3_PURE_PLAN.md)
> **Ancien état C0 :** [L3_CURRENT_C0_RUNNING_20260718.md](archives/l3/L3_CURRENT_C0_RUNNING_20260718.md)
> **Mémoire du projet :** [PROJECT_RESULTS.md](PROJECT_RESULTS.md)

## 1. État en une phrase

Les deux chaînes C0 A/B ont produit G1–G3 et leurs artefacts complets. Le job
haut-N `0792` a échoué techniquement avant tout verdict scientifique. La revue
des paramètres L3 est terminée et le fork C1-Q1 est préparé en PR, sans job
lancé.

## 2. C0 — faits d'exécution publiés

| Bras / job | Code | Début UTC | Fin UTC | État | Artefacts utiles |
|---|---|---|---|---|---|
| A — `ccx33-0790-l3-pure-c0-a-v1` | `8fc4eacb` | 10:42:49 | 11:09:08 | complet, rc=0 | G0, G1–G3, corpus+sidecars, splits, manifest |
| B — `cpx62-0791-l3-pure-c0-b-v1` | `c80c6792` | 10:41:16 | 11:02:30 | complet, rc=0 | mêmes artefacts + frontières G1/G2 |
| haut-N — `cpx62-0792-l3-pure-c0-highn-v1` | `b954ef97` | 11:39:10 | 11:44:18 | échec, rc=1 | inputs vérifiés et holdouts seulement ; aucun verdict |

URIs publiées :

- A : `r2:jass-data/runs/ccx33-0790-l3-pure-c0-a-v1/20260718T104245Z-8fc4eacb` ;
- B : `r2:jass-data/runs/cpx62-0791-l3-pure-c0-b-v1/20260718T104110Z-c80c6792` ;
- haut-N échoué :
  `r2:jass-data/runs/cpx62-0792-l3-pure-c0-highn-v1/20260718T113904Z-b954ef97`.

Les statuts GitOps prouvent la complétude technique des chaînes, pas la force
des modèles. `0792` n'a publié ni `gate-B-vs-A.json`, ni conversion P1–P4, ni
`c0-highn-verdict.json`. C0 n'a donc encore **aucun verdict A/B**.

## 3. Réserve découverte pendant la revue des paramètres

Le correctif #350 a rendu les cinq paramètres de quiescence explicites pour les
futurs runs, mais la chaîne ne contenait pas les 58 autres clés reconnues par
`SearchParams`. Le manifest indiquait donc à tort
`search_params_inherited_defaults=false` pour la configuration entière.

Cela n'invalide pas `0790/0791` : ils sont appariés et épinglés sur leurs SHA.
Cela interdit en revanche d'utiliser leur fingerprint partiel comme contrat du
nouveau fork. Le runner v4 épingle les 63 clés et un test compare leur ensemble
à celui du parseur C++.

Deuxième réserve : le champ score JNNW n'entre pas dans la loss WDL, mais le
générateur lançait tout de même une recherche de label dans le même `Engine`.
La TT persiste entre les recherches ; le label pouvait donc influencer le
prochain coup joué. C1 utilise `--wdl-zero-score`, exige
`label_score_searches=0` et sépare enfin la politique de jeu d'une sortie
inutilisée.

## 4. Décision de revue

| Groupe | État |
|---|---|
| vérité terminale, EGDB naturelle, censure ply-cap, provenance, holdout par ouverture | invariant |
| recherche de score JNNW | supprimée dans C1 |
| 63 paramètres de recherche | entièrement épinglés |
| menace / sacrifices sélectifs | DoE C1-Q1 immédiat |
| forcing, promotion, récursion des sacs | C1-Q2 conditionnel |
| pruning/réductions/history et budget | profil + ablations après Q |
| ouverture aléatoire / epsilon / décroissance | DoE exploration |
| homme:dame, L2, replay | DoE graine/fit |
| 8cf | fixe pendant les écrans ; 32cf rouvert seulement au scale |
| frontière mobile | verdict C0 haut-N requis avant dose-réponse |

## 5. Fork préparé : C1-Q1

Les quatre cellules sont un factoriel 2×2 menace×sacrifices. Elles partent
toutes de G0, utilisent la graine `271828`, deux générations de 150 k records,
d8, 8cf, aucun teacher et aucune frontière.

| Cellule | Box préparée | Menace | Sacs sélectifs | État |
|---|---|---:|---:|---|
| `Q00_CAPTURE` | ccx33 | 0 | 0 | wrapper hors queue |
| `Q10_THREAT` | cpx62 | 1 | 0 | wrapper hors queue |
| `Q01_SACS` | cpx62 | 0 | 1 | wrapper hors queue |
| `Q11_THREAT_SACS` | ccx33 | 1 | 1 | wrapper hors queue |

Forcing, promotion et récursion des sacrifices restent à zéro/`depth0_only`
pendant Q1. Ils ne sont pas déclarés mauvais : ils sont réservés au bloc Q2
pour ne pas confondre cinq facteurs dans le premier écran.

Aucun wrapper ne contient `FULL_RUN_APPROVED=1`. Une merge de la PR ne crée
aucune entrée GitOps et ne lance aucun calcul.

## 6. Trame de résultats C1-Q1

### 6.1 Santé de génération

| Cellule | G | Statut | Records | Ply-cap | Holdout N | Log-loss | Records/min | SHA modèle |
|---|---:|---|---:|---:|---:|---:|---:|---|
| Q00 | G1 | — | — | — | — | — | — | — |
| Q00 | G2 | — | — | — | — | — | — | — |
| Q10 | G1 | — | — | — | — | — | — | — |
| Q10 | G2 | — | — | — | — | — | — | — |
| Q01 | G1 | — | — | — | — | — | — | — |
| Q01 | G2 | — | — | — | — | — | — | — |
| Q11 | G1 | — | — | — | — | — | — | — |
| Q11 | G2 | — | — | — | — | — | — | — |

### 6.2 Conversion fixe

| Cellule G2 | Global | P1 | P2 | P3 | P4 | N | IC |
|---|---:|---:|---:|---:|---:|---:|---|
| Q00 | — | — | — | — | — | — | — |
| Q10 | — | — | — | — | — | — | — |
| Q01 | — | — | — | — | — | — | — |
| Q11 | — | — | — | — | — | — | — |

### 6.3 Effets factoriels

| Effet | Estimation | IC apparié | Lecture |
|---|---:|---:|---|
| menace | — | — | — |
| sacs | — | — | — |
| interaction menace×sacs | — | — | — |

### 6.4 Force

| Vue | Comparaison | N | Rate | IC95 | Elo | Verdict |
|---|---|---:|---:|---:|---:|---|
| common-search | meilleur vs Q00 | — | — | — | — | — |
| common-search | meilleur vs Q11 | — | — | — | — | — |
| native movetime | meilleur vs contrôle | — | — | — | — | — |

## 7. Gates pré-engagés

Un lead passe en confirmation seulement si :

- tous les artefacts et les 63 paramètres sont vérifiés ;
- `label_score_searches=0` dans chaque shard ;
- pas de régression établie en common-search ;
- gain conversion ponctuel ≥ +0,02, ou coût −20 % à force/conversion tenues ;
- P3 ne se dégrade pas sans compensation démontrée.

La promotion finale exige l'IC de conversion au-dessus de zéro et la réplication
depuis G0 avec la seconde graine `161803`.

## 8. Prochaines actions

1. diagnostiquer et relancer `0792` sans changer ses inputs ni ses gates ;
2. faire revoir la PR C1-Q1 ;
3. après merge seulement, micro-calibrer les quatre profils sur chaque box ;
4. calculer ETA, disque et timeout, puis demander le go explicite ;
5. exécuter Q1 ; publier la matrice common/native avant tout Q2.
