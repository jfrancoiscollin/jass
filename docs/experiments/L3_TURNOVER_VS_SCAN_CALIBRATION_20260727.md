# TURNOVER contre Scan — situer le champion, et cartographier l'équivalence

Préparé le 27 juillet 2026. **Séquencé après la promotion de TURNOVER et avant
G2.** Rien n'est lancé.

## Les deux questions

1. **À armes égales**, quel est le W/D/L entre TURNOVER et Scan, à profondeur
   identique et à cadence identique ?
2. **Quelle est la table d'équivalence** ? Notre d10 vaut-il un d8 de Scan ?
   Notre `mt0,2` vaut-il un `mt0,1` de Scan ?

## Un avertissement qui structure tout le protocole

Les deux questions n'ont pas la même réponse, et l'écart est connu et large.
`gen2-mmto` mesurait **+34 Elo** sur la cellule d9 contre Scan, mais **−128 à
−155 Elo au movetime**. La raison est mécanique : à profondeur imposée on
compare deux évaluations, à temps imposé on compare aussi deux vitesses — et
Scan cherche beaucoup plus vite.

Donc : **une seule « équivalence » n'existe pas.** Il y en a deux, et elles
diront des choses opposées. Le protocole les sépare explicitement pour qu'aucun
chiffre ne soit cité hors de son régime.

## Changement de régime de mesure

Toute la campagne récente traquait des effets de `±10 Elo`, d'où des cellules de
2 500 à 3 000 parties. **Ici les effets sont de plusieurs dizaines à plusieurs
centaines d'Elo** : un pas de profondeur vaut typiquement 50 à 70 Elo.

Des cellules de **400 parties** (200 ouvertures × 2 couleurs) suffisent donc
largement à situer un croisement à ±1 pas de profondeur. Sur-dimensionner ici
serait du gâchis pur.

## Harnais et équité

`jobs/tools/calibrate_vs_scan.py` gère déjà l'asymétrie nécessaire :
`--jass-depth` / `--scan-depth` et `--jass-movetime` / `--scan-movetime`.

Réglages d'équité, qui sont les défauts de l'outil et seront épinglés
explicitement :

```text
livre d'ouvertures   off des deux côtés   (--scan-book off, pas de --jass-book)
bitbase Scan         --scan-bb-size 0
threads              --jass-threads 1     (Scan mono-thread)
runtime Scan         figé par home-0925, vérifié par empreinte avant tout match
modèle Jass          TURNOVER b2c79b36…, recherche Q00 (63 paramètres épinglés)
```

Le runtime Scan est **figé**, donc la mesure est reproductible et comparable aux
mesures historiques.

## Matrice proposée

**Bloc A — armes égales, profondeur.** Répond directement à la question 1.

| cellule | TURNOVER | Scan |
|---|---|---|
| A1 | d8 | d8 |
| A2 | d10 | d10 |
| A3 | d12 | d12 |

**Bloc B — échelle de profondeur.** Localise le croisement à 50 %.

| cellule | TURNOVER | Scan |
|---|---|---|
| B1…B5 | **d10 fixe** | d6, d7, d8, d9, d10 |

**Bloc C — armes égales, cadence.** Question 1 en régime temporel.

| cellule | TURNOVER | Scan |
|---|---|---|
| C1 | mt 0,1 | mt 0,1 |
| C2 | mt 0,2 | mt 0,2 |
| C3 | mt 0,5 | mt 0,5 |

**Bloc D — échelle de cadence.** Localise le croisement temporel.

| cellule | TURNOVER | Scan |
|---|---|---|
| D1…D4 | **mt 0,2 fixe** | 0,02, 0,05, 0,1, 0,2 |

15 cellules, dont deux partagées entre blocs (A2≡B5, C2≡D4) → **13 cellules
distinctes**, 5 200 parties à `n=400`.

## Sizing — une sonde d'abord, obligatoirement

Les ancres disponibles sont anciennes et sur une autre box :
`calibrate_vs_scan` d9 + mt0,3, `N≈1300`, **≈2 h sur cpx62**, avec la note
« la cellule mt1.0 = goulot ~4h ». Extrapoler de là serait exactement la faute
qui a coûté `0665`.

**Job 1 — sonde `home-10xx`, ~20-30 min.** `n=40` par cellule sur les quatre
types extrêmes : `d12/d12`, `d10/d6`, `mt0,5/mt0,5`, `mt0,2/mt0,02`. Elle mesure
le débit réel de chaque régime sur HOME et publie une ETA chiffrée pour la
matrice complète.

**Job 2 — matrice complète**, dimensionnée depuis la sonde, avec un `timeout`
par cellule calibré à `temps_sain × 1,3` pour qu'une cellule bloquée ne gèle pas
le job.

Estimation grossière avant sonde, à ne pas traiter comme une ETA : les cellules
de cadence coûtent `n × plies × mt / parallélisme`, soit ~3 min pour C1 et
~17 min pour C3 à 12 workers. Les cellules de profondeur sont imprévisibles sans
mesure, en particulier d12.

## Lecture attendue

Le livrable est un tableau à deux colonnes d'équivalence :

```text
régime profondeur   notre dN  ≈  Scan d(N − k)      k mesuré par le bloc B
régime cadence      notre mtX ≈  Scan mt(X / f)     f mesuré par le bloc D
```

Plus le W/D/L brut de chaque cellule à armes égales.

Une prédiction est posée d'avance, pour qu'elle soit falsifiable : **`k` sera
petit** — 0 à 2 pas — et **`f` sera nettement supérieur à 1**, c'est-à-dire
qu'il faudra donner beaucoup moins de temps à Scan qu'à nous pour égaliser. Si
`k` s'avère grand, c'est l'évaluation qui est en cause ; si seul `f` est grand,
c'est la vitesse de recherche. Les deux diagnostics appellent des travaux
totalement différents.

## Ce que ce test n'est pas

Ce n'est **pas un gate de promotion**. Scan n'est pas dans notre lignée et n'est
pas un candidat champion. C'est une mesure de situation, destinée à savoir où
l'on se trouve et lequel des deux déficits — évaluation ou vitesse — mérite le
prochain effort.

`promotion_authorized=false`, `automatic_next_job=null`.
