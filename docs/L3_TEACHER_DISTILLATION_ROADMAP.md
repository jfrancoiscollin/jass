# L3 — Teacher distillation roadmap

> **Mis à jour : 28 août 2026**
> **Statut : roadmap active après verdict terminal Q1 deep fresh.**
>
> Situation courante : [`L3_CURRENT.md`](L3_CURRENT.md). Prereg terminale Q1 : [`experiments/L3_JOINT_TD_DEEP_FRESH_CONFIRMATION_V1_20260828.md`](experiments/L3_JOINT_TD_DEEP_FRESH_CONFIRMATION_V1_20260828.md), merge SHA `b280fc1f4878133a41168f4bbc6a537eec526cdc`.

---

## 1. Verdict qui change la roadmap

La campagne Q1 est terminée avec :

```text
JOINT_TD_DEEP_FRESH_NOT_CONFIRMED
A6_G0_DEEP_TRANSFER_CONFIRMED = TRUE
```

Le résultat central est une divergence entre le screen q1000 DEV et le deep fresh q200 :

- sur M3 DEV ciblé q1000, C0 battait D1 de ~`+1.57 pp` pairwise ;
- sur Q1 fresh q200, C0 **perd** contre D1 de `-1.57695 pp`, CI95 entièrement négative ;
- C0 améliore cependant le top-hit contre D1 de `+2.355 pp` avec CI positive ;
- A6-G0 bat T0 de `+0.8677 pp` pairwise et `+1.0254 pp` top-hit, avec CIs positives et gains dans toutes les phases/couleurs.

Donc la roadmap n'est plus « intégrer C0 au runtime ». Le stack C0 tel quel est fermé pour cette campagne.

---

## 2. Références terminales Q1

### Freeze

`cpx62-1616-l3-joint-td-candidate-freeze-v1`, attempt `20260828T104336Z-3348397a`, Jass SHA `3348397a0459b8c3335d46a70af5755d6e9488e0`, verdict `JOINT_TD_CANDIDATE_FREEZE_READY`.

Candidats gelés avant fresh : T0, D1, A6-G0, B1 et C0. Candidate-freeze SHA256 `7f5d28b8a3ea810bde0969959b2fdd01a2e778b9a63e602125c796432c76bf40`.

### Cohort fresh

`cpx62-1617-l3-joint-td-q1-select-v7`, attempt `20260828T114236Z-2034c5c9`, Jass SHA `2034c5c98f3e3260254dd7449bc5032dd125e581`.

- seed `2026090420` ;
- 4000 parents exactement, 1000 par phase ;
- target-blind ;
- overlap canonique M3/M5 = 0 ;
- aucun score deep lu avant sélection.

### Teacher/readout

Le q1-report scientifique est produit par `cpx62-1624-l3-joint-td-q1-teacher-readout-v5`, attempt `20260828T143246Z-8df8f407`, Jass SHA `8df8f4073109b2016e5425a5ac18ec3ac9008c85`.

Le wrapper 1624 échoue techniquement après génération du rapport. Le rapport est authentifié et republié sans recomputation par `cpx62-1625-l3-joint-td-q1-terminal-recover-v1`, attempt `20260828T154226Z-8df8f407`, exit 0, control merge SHA `569540fb5d7c36af5e25ca39f21dad45064ad98f`.

Aucun teacher rerun, rescoring, fit/refit, runtime/Elo, strength ou promotion n'est effectué par le recovery.

---

## 3. Support et métriques de référence

Support Q1 PASS : 3397 parents acceptés, 96862 paires stables. P0/P1/P2/P3 = `903/929/928/637`; white/black = `1710/1687`.

| Modèle | Pairwise q200 | Top-hit |
|---|---:|---:|
| T0 | 0.6084468414 | 0.5540673143 |
| A6-G0 | 0.6171234955 | 0.5643214601 |
| B1 | 0.7089233688 | 0.6452752429 |
| C0 | 0.7184044328 | **0.6764792464** |
| D1 | **0.7341739720** | 0.6529290550 |
| q1000 | **0.9357350801** | **0.8591894809** |

C0−D1 pairwise : mean `-0.0157695392`, CI95 `[-0.0221178885 ; -0.0095172194]`.

C0−D1 top-hit : mean `+0.0235501913`, CI95 `[+0.0088313218 ; +0.0385634383]`.

C0−D1 pairwise par phase : P0 `+0.01147`, P1 `-0.01890`, P2 `-0.03302`, P3 `-0.02470`; par couleur : black `-0.01112`, white `-0.02036`.

A6−T0 pairwise : mean `+0.0086766542`, CI95 `[+0.0071898443 ; +0.0101730833]`.

A6−T0 top-hit : mean `+0.0102541458`, CI95 `[+0.0054950446 ; +0.0151604357]`.

Ratios : `R_C0_from_D=-0.0782370139`, `R_C0_from_T=0.3359656058`.

---

## 4. Voie A — transfert pur-T : ouverte, mais gain modeste

A6-G0 est le seul candidat de cette campagne qui confirme son gate deep fresh.

Ce résultat établit que le DOE de transfert q1000→PatternEval n'était pas seulement un artefact DEV : il apporte environ `+0.87 pp` pairwise contre q200 et `+1.03 pp` top-hit contre T0, de manière homogène sur phases et couleurs.

### Décision

- conserver A6-G0 comme référence pure-T confirmée ;
- ne pas retuner sur Q1 ;
- ne pas lancer de force/Elo automatiquement ;
- un éventuel test de force A6 nécessite une **preregistration séparée** avec budget, pools et gates fixés à l'avance.

Le gain est réel mais petit : il ne résout pas le gap q1000.

---

## 5. Voie B — architecture non linéaire : toujours informative, non gagnante contre D1

B1 monte à `0.7089` pairwise q200, très au-dessus de T0/A6, ce qui confirme que les observables PatternEval contiennent bien plus de signal qu'un score linéaire historique n'en extrait.

Mais B1 reste sous D1 : B1−D1 pairwise mean `-0.0252506032`.

### Décision

B1 reste un **probe d'architecture**, pas un candidat de production. Les futures architectures compactes non linéaires doivent être conçues/tunées hors Q1 puis validées sur un autre cohort fresh.

Q1 ne doit jamais devenir un set de sélection d'hyperparamètres.

---

## 6. Voie C — joint T+D : C0 fermé, hypothèse générale non fermée

C0 améliore B1 (`C0−B1 ≈ +0.948 pp` pairwise) et améliore fortement T0, mais perd contre D1 sur le critère primaire q200.

La complémentarité observée contre q1000 DEV n'est donc **pas suffisamment robuste dans la forme C0** pour justifier une intégration runtime.

### Lecture importante

Le fait que C0 gagne en top-hit contre D1 tout en perdant en pairwise suggère qu'il y a peut-être un problème de forme/objective/ranking, mais **Q1 ne peut pas servir à ajuster C0 après coup**.

### Décision

- ne pas implémenter C0 au runtime ;
- ne pas lancer de force/Elo C0 ;
- ne pas recalibrer les 7 coefficients sur Q1 ;
- si une nouvelle architecture joint est explorée, elle doit être conçue avec M3/anciens corpus autorisés ou un nouveau TRAIN, puis confirmée sur un nouveau fresh réservé.

L'hypothèse générale « T et D peuvent être complémentaires » reste scientifiquement plausible, mais **elle n'est pas confirmée contre q200 sous C0**.

---

## 7. Voie D — le teacher reste la source de headroom dominante

q1000 atteint `0.9357351` pairwise, contre `0.7341740` pour D1 et `0.7184044` pour C0.

Le gap q1000−C0 est encore `+0.21733` pairwise. Le principal problème L3 reste donc de transformer le signal de recherche court en représentation statique compacte qui généralise.

### Priorités de recherche hors Q1

1. autopsie résiduelle sur données de développement autorisées, pas sur Q1 ;
2. nouvelles observables calculables sans search runtime ;
3. objectifs de ranking mieux alignés sur pairwise q200 ;
4. architecture compacte non linéaire exploitant les observables existantes ;
5. éventuel nouveau joint T+D avec interaction non linéaire, mais sélection entièrement hors Q1.

---

## 8. Prochaine bifurcation autorisée

La campagne Q1 est terminée et n'autorise aucun runtime/Elo/promotion.

Deux nouvelles campagnes séparées sont possibles, chacune avec sa propre preregistration :

### Option A — pure-T A6 force gate

Justifiée par le secondary PASS A6. À preregistrer : pools, cadence native, nombre de parties, CI/Elo gate, coût runtime et règles de stop. Aucun lancement automatique.

### Option B — student T2/J2 de nouvelle génération

Construire hors Q1 une architecture plus expressive ou de nouvelles observables, puis :

```text
TRAIN/selection hors Q1
  -> freeze immuable
  -> nouveau cohort deep fresh disjoint
  -> q200 confirmation
  -> seulement si PASS : runtime/force prereg séparée
```

C0 n'est pas le point de départ runtime ; il n'est qu'un résultat historique de screen.

---

## 9. Données désormais interdites au tuning

Le cohort Q1 seed `2026090420` est consommé.

Il est interdit de l'utiliser pour :

- hyperparameter search ;
- sélection d'architecture ;
- calibration C0/B1/A6/D1 ;
- feature selection ;
- choix de gates a posteriori.

Il peut uniquement rester dans les archives comme validation terminale de la prereg b280.

---

## 10. Métriques de pilotage futures

| Niveau | Métrique | Question |
|---|---|---|
| Teacher | q1000 vs q200 fresh | Le lookahead garde-t-il un gros headroom ? |
| Pure transfer | A6-like vs T0 | Le student linéaire absorbe-t-il un gain robuste ? |
| Architecture | nonlinear vs D1 | La capacité supplémentaire dépasse-t-elle la meilleure statique ? |
| Joint | J−D sur nouveau fresh | Le joint généralise-t-il réellement contre deep ? |
| Feature residual | gain hors Q1 | Une nouvelle observable explique-t-elle le résidu teacher ? |
| Runtime | coût eval / NPS / depth | Seulement après deep PASS et prereg dédiée |
| Force | paired Elo | Seulement après runtime/prereg dédiés |

---

## 11. Règles verrouillées après Q1

1. `CURRICULUM` reste champion.
2. Q1 est consommé et ne peut jamais devenir un dataset de tuning.
3. `JOINT_TD_DEEP_FRESH_NOT_CONFIRMED` ferme C0 pour runtime/Elo dans cette campagne.
4. `A6_G0_DEEP_TRANSFER_CONFIRMED` n'autorise qu'une future prereg séparée, pas une promotion.
5. q1000 imitation, q200 accuracy et Elo restent trois niveaux distincts.
6. Aucun post-freeze refit rétroactif.
7. Aucun D1/move-local input runtime sans protocole causal et prereg distincts.
8. Toute nouvelle architecture/feature doit être sélectionnée sans regarder Q1.

---

## 12. Principe directeur

La question L3 après Q1 devient :

> **Comment conserver le headroom massif de q1000 dans un student statique qui dépasse réellement D1 en pairwise deep fresh, sans sélectionner ni tuner sur le cohort de validation ?**

Le résultat Q1 évite une mauvaise bifurcation : C0 semblait excellent sur q1000 DEV, mais ne généralise pas suffisamment. La prochaine génération doit donc améliorer la capacité/les observables et revenir avec une nouvelle validation fresh réellement indépendante.
