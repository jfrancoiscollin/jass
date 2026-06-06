# Audit `develop` vs `main` — 2026-06-06

## TL;DR

**`main` ne perd rien.** C'est un sur-ensemble complet du contenu de `develop`.
Le seul actif unique à `develop` est le **récit de son historique** (2863 commits),
préservé via l'index/log de cette archive (et le bundle git livré séparément).

## Contexte : deux historiques disjoints

L'historique du dépôt a été réécrit à un moment. Résultat :

| | `develop` | `main` |
|---|---|---|
| Racine | `af53556` | `a7e98278` (+ 2ᵉ racine `678e7645`) |
| Nb commits | 2863 | 75 |
| Nb fichiers | 402 | 2889 |
| Ancêtre commun avec l'autre | **aucun** (`git merge-base --all` → vide) |

`git merge` refuse de les fusionner (*refusing to merge unrelated histories*).
`develop` = ancienne lignée d'origine ; `main` = nouvelle lignée propre, qui est
la branche d'intégration active (toutes les PR récentes y mergent, jusqu'à
l'Option I NNUE skeleton via PR #196).

## Vérification « rien perdu dans main »

| Vérification | Résultat |
|---|---|
| Fichiers présents sur `develop` mais **absents de `main`** | **0** |
| `jobs/results/` (résultats d'expériences) qui diffèrent | **0** — record préservé à l'identique |
| `jobs/queue/` (scripts d'expériences) qui diffèrent | **0** |
| Fichiers communs au contenu différent | 22 |
| … dont `main` est **plus gros / plus récent** | 21 |
| Seule exception (`develop` +6 lignes) | `src/nnue_accumulator.hpp` |

### L'unique exception, analysée

`src/nnue_accumulator.hpp` est plus long sur `develop` **uniquement** parce qu'il
contient un vieux bloc de commentaire « SCAFFOLD ONLY / not yet wired up /
WIRING-UP PLAN ». Sur `main` ce plan a été **remplacé par l'implémentation
réelle** (« WIRED END-TO-END », wiring fait dans `src/search.cpp`, ×1.57 de
speedup mesuré). → `main` est en avance, aucune perte.

### Docs

Seuls 3 docs diffèrent, et `main` est plus complet dans les 3 :

| Doc | `develop` | `main` |
|---|---|---|
| `docs/SESSION_LOG_2026_05.md` | 115 L | 185 L |
| `docs/PATTERN_ROADMAP.md` | 186 L | 223 L |
| `docs/EXTENDING.md` | 212 L | 219 L |

## Ce que contient cette archive (in-repo)

| Fichier | Description |
|---|---|
| `DEVELOP_EXPERIMENTS_INDEX.txt` | 157 commits « réels » (bruit runner retiré) — l'index lisible de **ce qui a été essayé** (jobs 0001→0025a, pattern v1/v2, NNUE accumulator incrémental, scan distillation, master-games fetcher, etc.) |
| `DEVELOP_FULL_LOG.txt` | Log oneline exhaustif (2863 lignes) |
| `AUDIT_REPORT.md` | Ce rapport |

> **Le bundle git complet (`develop-legacy.bundle`, ~62 Mo)** n'est volontairement
> **pas committé** dans le dépôt pour ne pas alourdir `main`. Il a été livré
> séparément comme fichier téléchargeable. Conserve-le si tu veux pouvoir
> re-cloner l'historique complet de `develop` plus tard.

## Restaurer / consulter l'historique complet (depuis le bundle téléchargé)

```bash
# Lister les refs du bundle
git bundle list-heads develop-legacy.bundle

# Cloner l'historique complet dans un dossier
git clone develop-legacy.bundle develop-legacy
cd develop-legacy && git log --oneline

# Ou rattacher le bundle à un clone existant du dépôt
git fetch ../develop-legacy.bundle 'refs/*:refs/develop-legacy/*'
```

## Recommandation

Le contenu et la connaissance (docs, scripts, résultats, verdicts) sont **déjà
intégralement dans `main`** : tu ne risques pas de refaire ce qui a été testé en
travaillant sur `main`. Cette archive in-repo conserve le *récit* (index + log) ;
le bundle téléchargé conserve l'historique git complet. Une fois ces éléments
sauvegardés, la branche `develop` côté remote peut être supprimée sans perte.
