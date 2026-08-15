# CURRICULUM — attribution du gain à `context30` contre le mégacorpus

Enregistrement immuable. Mesure `cpx62-1354`, lue par `cpx62-1355`, le
15 août 2026. **Cette mesure ne débake rien** : CURRICULUM reste champion et
gagne bien. Elle répond à la question que l'enregistrement de promotion laissait
explicitement ouverte — « la recette complète gagne ; l'attribution à un facteur
unique n'est pas établie » — et elle la referme en partie.

## Question

CURRICULUM (bras D, `C_PRIOR_THEN_CURRENT_2M`) est un **curriculum à deux
étages** : pré-entraînement sur `MEGA_FULL_4M`, puis recentrage sur `CURRENT_2M`
avec la cible alignée `CONTEXT_30`. Son gain sur L2LOW peut donc venir de deux
sources radicalement différentes, et l'une coûte cent fois plus cher que l'autre :

- le **volume** du mégacorpus, qui demande de générer et de conserver 4 M de
  positions supplémentaires ;
- le **ré-étiquetage** `context30`, qui ne demande aucune donnée nouvelle : il
  se contente de réécrire les cibles du corpus qu'on a déjà.

Le bras `A = CURRENT_C30` sépare les deux à **un seul facteur** : il partage avec
D l'étiquetage `context30`, la recette de fit, le volume de fit (2 M) et le fold
exact, et n'en diffère que par le **corpus source** — le corpus courant, celui
d'avant le mégacorpus.

## Protocole

`cpx62-1354`, template `l3-model-gate-v1.sh`, code `18c38a33`.

- **même pool d'ouvertures que `cpx62-1349`** (`cpx62-1348`,
  `d-champion-fresh3000`, 3000 ouvertures) — délibérément, pour que l'écart
  A-vs-D se lise sur les mêmes positions de départ, sans variance de pool entre
  les deux mesures ;
- deux vues, `q00` à profondeur 9 fixe et `native` à movetime 0,1 ;
- couleurs appariées, `n = 12 000`, EGDB présent, `NSH=PAR=12` ;
- **zéro refit, zéro self-play** : les deux modèles étaient déjà fittés ;
- durée 63,1 min, `rc=0`, les deux vues jouées.

⛔ Le pool `cpx62-1351` n'a pas été touché : il porte la réplication de D, et le
rejouer aurait cassé la disjonction qui fonde le chaînage du bake.

## Résultats

```text
A_CURRENT_C30 contre L2LOW, n = 12 000
  q00     2897 W   294 N  2809 D   taux 0,507333
  native  2900 W   316 N  2784 D   taux 0,509667
  somme   5797 W   610 N  5593 D   taux 0,508500
          Elo +5,91   IC95 [-0,15 ; +11,97]   P(Elo>0) = 97,2 %
```

| | Elo | IC95 | `P(Elo>0)` |
|---|---|---|---|
| **A** = corpus courant + `context30`, **sans mégacorpus** | **+5,91** | `[−0,15 ; +11,97]` | **97,2 %** |
| **D** = CURRICULUM (`cpx62-1349`, même pool) | +8,22 | `[+2,18 ; +14,28]` | 99,6 % |
| **D − A** = apport marginal du mégacorpus | **+2,32** | `[−6,24 ; +10,88]` | `z = 0,53` |

## Lecture

**L'essentiel du gain baké est reproduit en ré-étiquetant le corpus courant.**
A capture `+5,91` des `+8,22` de D, soit environ **72 % du gain**, sans une seule
position du mégacorpus. L'apport marginal du volume est de `+2,32 Elo` avec un
intervalle qui **n'exclut ni zéro ni +10** : il n'est **pas établi**, et il n'est
pas non plus réfuté.

⚠️ **Le verdict frequentiste du template est `A_FLAT_VS_B_NO_ESTABLISHED_GAIN`,
et il induit en erreur si on le lit seul.** Il vient d'une borne basse à
`−0,15` — un cheveu sous zéro. Sous le critère en vigueur depuis le 5 août — la
position de la masse, pas « l'IC exclut zéro » — A est à **97,2 %**. C'est
exactement le cas de figure pour lequel le critère a été changé, et la première
lecture faite en séance a bien commis l'erreur que le label invite à commettre :
conclure « A n'est pas D, donc le mégacorpus n'est pas décoratif » alors que les
chiffres disaient le contraire.

## Réserves, dans les deux sens

- **Le test de la différence A−D ne peut pas trancher à ce `n`.** Vérifié avant
  la lecture des résultats, sur trois scénarios simulés : même un A parfaitement
  nul (taux 0,500) ne sortirait qu'à `z = −1,88`, donc non distinguable à 95 %.
  Un `|z| < 1,96` ici **ne prouve pas l'égalité**, il ne la réfute pas.
- `se(A−D)` traite les deux portes comme **indépendantes** alors qu'elles
  partagent les ouvertures, ce qui est **conservateur** : le vrai `z` est un peu
  plus grand. Mais il faudrait que la corrélation absorbe ~93 % de la variance
  pour atteindre `1,96`, ce qui n'est pas crédible.
- A et D sont appariés **pool à pool**, pas partie par partie : ce sont deux jobs
  distincts sur les mêmes ouvertures, pas les mêmes réalisations de parties.
- A n'a été mesuré que sur **un** pool. Aucun chaînage, donc aucun critère de
  bake — ce n'est pas une porte de promotion et A n'est candidat à rien.

## Ce que coûterait de trancher

Pour établir un effet de `+2,32 Elo` à 95 % il faut `se ≈ 1,18`, soit
**163 800 parties par bras, ×13,7** — environ **29 h de cpx62 pour un seul
pool**, ~58 h avec la réplication qu'exige le critère de bake.

⛔ **Mesurer directement la valeur marginale du mégacorpus est hors de prix à
cette taille d'effet.** C'est une conclusion de méthode autant que de science :
la question « le volume paie-t-il ? » ne se tranchera pas par une porte de plus
sur ces deux modèles.

## Conséquence pour la ligne de campagne

La direction annoncée le 14 août était « volume + diversité + WDL conditionnel ».
Cette mesure **sépare les trois** :

- le **WDL conditionnel `context30` paie**, mesurément, et il est bon marché —
  il ne demande aucune donnée nouvelle ;
- le **volume n'est pas démontré**, et son plafond crédible est modeste
  (`+10,88` au mieux, sur un intervalle centré sur `+2,32`).

Cela ne ferme pas l'axe volume/diversité — cela dit que **le prochain
investissement rentable est du côté de la cible, pas du côté du corpus**, et que
tout protocole qui cherche à établir un effet de l'ordre de `+2` devra affronter
le même mur de puissance. Toute expérience de type « pooling multi-seed » doit
donc publier son sizing **avant** de lancer sa phase de force.

## Traçabilité

```text
mesure          cpx62-1354-jass-a-vs-l2low-attribution-v1
                20260815T122525Z-18c38a33   rc=0   63,1 min
lecture         cpx62-1355-read-1354-attribution-v1
référence D     cpx62-1349-jass-d-vs-l2low-champion-v1   (même pool, même budget)
pool            cpx62-1348 · d-champion-fresh3000 · 3000 ouvertures
modèle A        cpx62-1340 · 20260814T123246Z-2ce07222 · current_2m.pjtw.gz
modèle L2LOW    cpx62-1164 · 20260803T060626Z-209eb56b · control.pjtw.gz
```

`PROMOTION_AUTHORIZED = false`, `AUTOMATIC_NEXT_JOB = null`.
