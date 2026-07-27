# Bake TURNOVER — procédure préparée, non exécutée

Rédigé le 27 juillet 2026 pendant que `home-0996` tourne. **Rien n'est appliqué
ici.** Ce document existe pour que la promotion soit un `go` à valider et non
une mécanique à dicter.

## Ce qu'un bake est, dans ce projet

Le précédent fait foi : la promotion de F2M (commit `3db4506f`, signé JFC, le
25 juillet) était **purement documentaire**. Aucun binaire n'est déplacé, aucun
modèle n'est « installé ». Le champion est une **référence épinglée par SHA**,
et le modèle vit déjà, immuable, dans l'object store.

Conséquence directe : le bake est **réversible par un simple `git revert`**, et
son coût est nul en compute.

## Préconditions — les quatre doivent tenir

1. `home-0996` termine avec `TURNOVER_SUCCESSION_RECOMMENDED_HUMAN_REVIEW` ;
2. `all_guardrails_pass = true` — force établie sur le pool neuf, aucune
   régression établie contre Gen2, P3 et P4 au-dessus du plancher ;
3. revue humaine explicite de JFC ;
4. `promotion_authorized` reste `false` dans **tous** les artefacts : la porte
   recommande, elle ne promeut jamais.

Si `0996` rend `TURNOVER_SUCCESSION_BLOCKED_GUARDRAIL` ou
`TURNOVER_SUCCESSION_NOT_ESTABLISHED_ON_FRESH_POOL`, **cette procédure ne
s'applique pas** et F2M reste champion.

## Identités concernées

```text
nouveau champion  TURNOVER  b2c79b3617c41087191fee04d9aee0e1929ea63ad621c2efeaebc14ae53a7c16
                  r2:jass-data/runs/home-0977-l3-pure-turnover1to1-train-v1/
                     20260726T071254Z-336bb984/artefacts/turnover1to1.pjtw.gz

champion sortant  F2M       be675b6c1c6360a0a9aa5977ed492284bc8dcc1861ee47bc2e3139046ed769f2
                  r2:jass-data/runs/home-0944-l3-pure-m1-train-resume-v3/
                     20260724T052619Z-faddc80a/artefacts/f2m.pjtw.gz

référence figée   GEN2      inchangée, reste le garde-fou historique externe
```

L'archivage de F2M ne demande aucune action : son modèle est déjà immuable dans
R2 sous un préfixe daté. Le bake se contente d'enregistrer qu'il devient
*champion précédent* au lieu de *champion courant*.

## Les quatre éditions, dans l'ordre

### 1. `docs/L3_CURRENT.md` — §6, référence champion

```diff
-1. champion général courant : F2M, immuable tant qu'aucun gate n'est franchi ;
-   Gen2-mmto reste la référence historique figée ;
+1. champion général courant : TURNOVER, promu après la porte `home-0996` ;
+   F2M devient le champion précédent, archivé et restaurable ; Gen2-mmto reste
+   la référence historique figée ;
```

### 2. `docs/L3_CURRENT.md` — statut scientifique et table §3

Statut : remplacer `turnover50_beats_f2m_established_awaiting_human_review` par
`turnover50_promoted_general_champion`. Ajouter la ligne de campagne :

```text
| champion général | porte de succession TURNOVER vs F2M, garde Gen2, conversion | `home-0995` / `home-0996` | **TURNOVER promu champion général** |
```

### 3. `docs/PROJECT_RESULTS.md` — §2, point 4

```diff
    Depuis le gate réparé `home-0965`, **F2M est le champion général courant** :
    `57,25 %` contre Gen2 en Q00 et `58,60 %` en cadence native, avec les deux
    bornes basses à 95 % au-dessus de 50 %.
+   Depuis la porte `home-0996`, **TURNOVER remplace F2M comme champion général
+   courant** : … (chiffres de la porte) … F2M devient le champion précédent.
```

### 4. `docs/L3_LINEAGE_ROLES_AND_MATURITY.md` — §lignée

```diff
-- F2M a passé le gate de force réparé `home-0965` dans les deux vues et est
-  désormais le champion général courant ; `gen2-mmto` reste le champion
-  historique figé et un garde-fou externe.
+- F2M a passé le gate de force réparé `home-0965` et a été champion général
+  jusqu'au 27 juillet 2026. TURNOVER l'a remplacé après la porte `home-0996` ;
+  `gen2-mmto` reste le champion historique figé et un garde-fou externe.
```

### 5. Nouveau `docs/experiments/L3_TURNOVER_PROMOTION_20260727.md`

Enregistrement immuable de la promotion : chiffres de `0996`, rappel des
11 000 parties accumulées sur le couple, préfixe R2, et la liste explicite des
cellules **non** jouées, pour borner ce que la promotion autorise à dire.

## Ce que le bake ne touche pas — et pourquoi

Le SHA `be675b6c…` est codé en dur dans **19 templates**. Ils ne doivent
**pas** être réécrits : ce sont les templates d'expériences déjà exécutées, et
les modifier corromprait la trace de ce que ces jobs ont réellement fait.

Seuls les **futurs** templates prendront TURNOVER comme référence champion. Le
premier concerné sera la chaîne G2 (`0997`→`0999`), dont le parent est de toute
façon TURNOVER par construction.

## Rollback

```bash
git revert <sha-du-commit-de-bake>
git push origin HEAD:refs/heads/develop
```

Aucun artefact R2 n'est modifié par le bake, donc rien à restaurer côté données.
F2M redevient champion courant par le seul revert. C'est la réversibilité exigée
par les règles du projet.

## Après le bake

La chaîne G2 devient lançable — elle attendait précisément cette confirmation.
Protocole :
[`L3_PURE_TURNOVER_G2_PROTOCOL_20260727.md`](L3_PURE_TURNOVER_G2_PROTOCOL_20260727.md).
