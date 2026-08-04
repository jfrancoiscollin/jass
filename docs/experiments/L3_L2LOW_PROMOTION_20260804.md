# L2LOW — promotion au rang de champion général

Enregistrement immuable. Promotion décidée par revue humaine de JFC le
4 août 2026, après la réplication `cpx62-1170` et les gardes `cpx62-1171`.

## Identités

```text
nouveau champion  L2LOW      ec47e4b37fc7e95dcb390c0a5eddf207e98c0818c1708636d2df9e85b1d149b4
                  r2:jass-data/runs/cpx62-1164-l3-prior-dose-l2-refit-v1/
                     20260803T060626Z-209eb56b/artefacts/control.pjtw.gz

champion précédent PRIORTIGHT 2bbe1733ca0976ce4934131f83178a9e3757b5bc7a9b5a3bdbc41984781dfec7
référence figée   GEN2 (gen2-mmto), inchangée
```

Empreintes du `.pjtw` **décompressé**, comme F2M, TURNOVER, EXACT, PRIOR et
PRIORTIGHT.

## Comment L2LOW a été construit

**Aucune donnée neuve, aucune capacité neuve, aucune géométrie neuve** — le
cinquième gain d'affilée obtenu en retirant quelque chose que le fit imposait à
tort. Recette identique à PRIORTIGHT, à un nombre près :

```text
--exact-fold                          inchangé
--prior-mean <parent> --prior-decay 0 inchangé
--lbfgs-gtol 1e-4                     inchangé
--l2 1e-5                             ← le seul changement (PRIORTIGHT : 3e-5)
```

`1519` itérations, `1690` évaluations de fonction, arrêt sur `PGTOL`,
`‖∇‖∞ = 7,809e-5`, holdout `0,438816`.

### Ce que `l2` veut dire depuis qu'il y a un prior, et pourquoi ça change tout

La question venait de JFC : le prior bayésien a été calibré à l'ère **100 %
frais**, et la campagne est passée à un **mélange 1:1** où la moitié mémoire
**est** le parent réinjecté comme donnée. Un prior centré sur le parent risque
donc de le **compter deux fois**.

La lecture du code a déplacé la question. La précision du prior vaut
`prec = l2 + decay · λ · (visites/N)`, donc à `--prior-decay 0` — la recette
championne — **`λ` est strictement inerte** et la force du prior **est `l2`**.
Or sous `--prior-mean`, `l2` n'est plus un rétrécissement vers zéro : c'est la
**force du rappel vers le parent**. Le même nombre, un autre sens.

⛔ **`3e-5` n'était pas un mauvais réglage : c'était un bon réglage transporté
hors de son domaine.** Il a été clos en juillet (`l2_factor_closed_on_3e5`) sur
un ridge centré sur **zéro**, puis réutilisé tel quel une fois le ridge recentré
sur le parent. La fermeture ne se transportait pas, et personne ne l'avait
rouverte.

## Preuve de force

Règle appliquée telle qu'écrite avant les chiffres
([`L3_PRIOR_DOSE_PREREGISTRATION_20260803.md`](L3_PRIOR_DOSE_PREREGISTRATION_20260803.md)).

| cellule | pool | n | Elo | IC95 |
|---|---|---:|---:|---|
| `cpx62-1165` découverte | `big3000` | 12 000 | `+12,54` | `[+6,5 ; +18,6]` |
| `cpx62-1170` réplication | `home-1004` (disjoint) | 6 000 | `+8,86` | `[+0,3 ; +17,4]` |
| **consolidé** | deux pools disjoints | **18 000** | **`+11,31`** | **`[+6,4 ; +16,3]`** |

`8811W 964D 8225L`. IC95 consolidé excluant zéro **et** deux points de même
signe : les deux critères préenregistrés sont remplis.

### La dose complète, à un seul facteur

Quatre points, tous contre PRIORTIGHT, tous à `n = 12 000` sur `big3000` :

| `l2` | itérations | holdout | Elo contre PRIORTIGHT | IC95 |
|---|---:|---:|---:|---|
| `1e-4` | 511 | `0,441706` | **`−15,65`** | `[−21,7 ; −9,6]` |
| `3e-5` *(PRIORTIGHT)* | 904 | `0,440121` | `0` | — |
| `1e-5` *(L2LOW)* | 1519 | `0,438816` | **`+12,54`** | `[+6,5 ; +18,6]` |
| `3e-6` | 2317 | `0,438339` | **`+14,25`** | `[+8,2 ; +20,3]` |

La courbe est **monotone et bornée des deux côtés** : un rappel plus fort perd,
un rappel plus faible gagne, et les deux bornes excluent zéro chacune de son
côté. La clause d'incohérence de la règle — gagner à la fois avec un rappel plus
fort et plus faible — n'a pas tiré.

✅ **L'axe se ferme par PLATEAU, pas par mur.** Le pas `3e-5 → 1e-5` achète
`+12,54` ; le pas suivant, de même taille en échelle log, achète `+1,71` avec
`SE(diff) ≤ 4,37`, soit **`z = 0,39`**. `1e-5` et `3e-6` sont **indiscernables**.

## Gardes de succession (`cpx62-1171`)

| garde | L2LOW | plancher | repère PRIORTIGHT |
|---|---|---|---|
| non-régression Gen2 | `61,90 %`, **`+84,31 Elo`**, `3582W 264D 2154L`, deux vues positives (`q00` `0,6185` · `native` `0,6195`) | — | `+86,09` |
| conversion `p3_mince` | `0,7500` (W225 D23 L52) | `0,70` | `0,8067` |
| conversion `p4_egal` | `0,7667` (W230 D16 L54) | `0,70` | `0,7800` |

`SUCCESSION_GUARDS_GREEN`.

⚠️ **La conversion `p3` recule de `5,67 pp` contre le champion assis.** À
`n = 300`, `z = −1,39` : ce n'est pas un signal, et `p4` bouge en sens inverse
(`z = −0,33`). C'est néanmoins **le seul chiffre de la campagne qui va dans le
mauvais sens**, et il est consigné ici parce qu'il avait été annoncé comme un
point à regarder avant d'être mesuré — pas découvert après coup.

## Contrôle non prévu, et il tient

Les deux refits de la dose (`cpx62-1164` et `cpx62-1168`) portaient chacun un
bras `l2 = 1e-4`. Ils sont **byte-identiques** —
`9178ec8d63216ece33f8ff5d3f2531cc0d715c2dbc541efc72108a64bcd16105` des deux
côtés, mêmes `511` itérations, mêmes `570` évaluations de fonction, même norme
de gradient jusqu'à la dernière décimale. C'est ce qui autorise à comparer un
modèle de `1164` à un champion fitté dans `1159`.

## ⚠️ Ce que cette promotion n'établit pas

- **Le chiffre est BIAISÉ VERS LE HAUT**, comme préenregistré. La réplication
  est tombée de `+12,54` à `+8,86` — **troisième fois d'affilée** après PRIOR et
  PRIORTIGHT. Borne basse de la réplication seule : **`+0,3`**, elle passe d'un
  cheveu. Citer le consolidé `+11,31`, borne basse `+6,4`, jamais `+12,54`.
- ⛔ **Le départage `1e-5` / `3e-6` a été choisi APRÈS les chiffres.** La règle
  préenregistrée prévoyait une gagnante, aucune, ou deux **de part et d'autre**
  du champion ; elle est **muette sur deux gagnantes du même côté,
  indiscernables**. Le critère retenu — coût de refit (`1519` contre `2317`
  itérations) et distance à la falaise numérique — est indépendant de l'Elo
  mesuré, et il désigne le **plus faible** des deux points estimés. Cela atténue
  le grief sans l'effacer.
- **`1e-6` n'est PAS montré hors d'atteinte.** `cpx62-1167` l'a tué à `4h30` de
  `FIT_TIMEOUT` sans converger et **sans laisser de compte d'itérations** (log
  bufferisé, `0` octet — corrigé depuis par `PYTHONUNBUFFERED=1`). L'extrapolation
  de la suite `511 → 904 → 1519 → 2317` le place vers `~3500-4000` itérations,
  soit ~4h-4h40 : il a été coupé **de peu**. Ce n'est pas le mur structurel de
  `gtol = 1e-5`. Il n'a simplement plus d'intérêt, la pente étant nulle.
- **Rien sur Scan.** La matrice `home-1300`/`1301` a été jouée sur PRIORTIGHT,
  pas sur L2LOW.
- **Rien au-delà de d8, rien hors 8cf, couverture par bucket non recomptée.**

## Conséquence pour la suite

⛔ **Recette de fit obligatoire : `--exact-fold` + `--prior-mean <parent>
--prior-decay 0` + `--lbfgs-gtol 1e-4` + `--l2 1e-5`.**

Et la leçon générale, qui vaut au-delà de ce réglage : **une constante close
dans un régime ne reste close que dans ce régime.** `l2` a changé de sens le
jour où le ridge a changé de centre ; sa fermeture de juillet aurait dû être
rouverte le même jour. Toute constante héritée doit être re-testée quand ce
qu'elle module change de nature.

## Réversibilité

Promotion **purement documentaire**, comme F2M (`3db4506f`), TURNOVER
(`54c9dc39`), EXACT (`52e8a448`), PRIOR (`2dd33a78`) et PRIORTIGHT (`fb8bd123`).
Aucun artefact de l'object store n'est modifié ; PRIORTIGHT reste immuable sous
son préfixe daté et restaurable. `git revert` du commit de bake suffit.

## Trace

- réplication : `r2:jass-data/runs/cpx62-1170-l3-l2low-replication-pool1004-v1`
- gardes : `r2:jass-data/runs/cpx62-1171-l3-l2low-succession-guards-v1`
- découverte : `r2:jass-data/runs/cpx62-1165-l3-prior-dose-gate-l2low-v1`
- borne haute de la dose : `r2:jass-data/runs/cpx62-1166-l3-prior-dose-gate-l2high-v1`
- quatrième point `3e-6` : `r2:jass-data/runs/cpx62-1169-l3-prior-dose-gate-l2vlow-v1`
- refit `1e-5` / `1e-4` : `r2:jass-data/runs/cpx62-1164-l3-prior-dose-l2-refit-v1/20260803T060626Z-209eb56b`
- refit `3e-6` / `1e-4` (contrôle d'identité) : `r2:jass-data/runs/cpx62-1168-l3-prior-dose-l2-3e6-refit-v1/20260803T182826Z-7df186d9`
- règle préenregistrée : [`L3_PRIOR_DOSE_PREREGISTRATION_20260803.md`](L3_PRIOR_DOSE_PREREGISTRATION_20260803.md)
- promotion précédente : [`L3_PRIORTIGHT_PROMOTION_20260803.md`](L3_PRIORTIGHT_PROMOTION_20260803.md)
