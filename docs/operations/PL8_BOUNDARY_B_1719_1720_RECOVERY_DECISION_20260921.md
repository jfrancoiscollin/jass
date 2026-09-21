# PL8 Boundary B — décision de reprise technique 1719 / 1720

Date : **21 septembre 2026**. Terminal de la réconciliation technique bornée :
**`PL8_BOUNDARY_B_TECHNICAL_RECOVERY_NOT_ADMISSIBLE_V1`**.

Le [contrat PL8 gelé](../experiments/L3_PATTERN_LATENT_MICROSEARCH_PL8_V1_20260831.md)
reste inchangé. La reprise exige une cause mécanique démontrée, une preuve d'arrêt
avant fit et nouvelles cibles, puis une réparation qui conserve chaque paramètre
scientifique. Le mandat utilisateur fournit déjà l'autorité ; aucune nouvelle
demande de permission n'est requise. Ce document ne vaut pas admission d'exécution.

## Sources exactes et portée

- 1719 : `cpx62-1719-l3-pl8-boundary-b-v2`, tentative
  `20260831T183547Z-3ca55d35`, échec technique, sortie 1.
- 1720 : `cpx62-1720-l3-pl8-boundary-b-v2-diagnostic-v1`, tentative
  `20260831T185118Z-3ca55d35`, diagnostic publié avec sortie 0.
- Code commun : `3ca55d350e9ec324c0c1e47ff96324f4b6af0f2b`.
- Diagnostic 1720 authentifié et relu sur R2 le 21 septembre : 694 octets,
  SHA256 `8182301ac14cd91fde3ebb94f4ee71cd1f96e0e35ac6682b64aba2056dc4b4ff`.
- Base exacte du wrapper : commit contrôle
  `8c6b30801d191b734efa5e62c2df8fd4bd5954f3`, blob
  `bdcdb96eae6acb93609930bb8e6675553e8b630d`. Cet objet référencé a été récupéré
  explicitement pour compléter le checkout local peu profond.

La réconciliation examine seulement les deux statuts, le diagnostic, son reçu
d'authentification, le wrapper immuable matérialisé comme texte et le contrat gelé.
Elle ne lit aucun payload PL8 de fit, d'ancrage ou de confirmation. Aucune recherche,
génération de cible, partie, modification de code ou de file n'est exécutée.

## Fait établi et limite du diagnostic

Le diagnostic place l'arrêt dans `fetch-target-blind-catalog-and-exclusions` :
ligne 145, retour 1, invocation du bloc Python produisant `normalized-identities.tsv`.
Il ne contient ni traceback, ni classe d'exception, ni ligne d'entrée fautive.
Ce code retour ne distingue donc pas les causes possibles d'un échec Python.

Les champs `fit_runs=0`, `fresh_labels=0` et `strength_games=0` ont été écrits comme
constantes par le wrapper de diagnostic. Leur authentification prouve les octets
publiés ; elle ne les transforme pas en compteurs mesurés de l'exécution 1719.
La position de l'arrêt est établie séparément depuis le script exact : normalisation
à la ligne 145, avant build (166), sélection (193), fit (207), ancrage (219) et
confirmation fraîche (229). Aucun fit, cible d'ancrage ou label frais n'a donc été
atteint. Cela ne signifie pas qu'aucune ancienne source n'avait été téléchargée.

La cause mécanique unique reste inconnue. Sans stderr ni entrée fautive identifiée,
aucune correction ni régression reproduisant le défaut exact ne peut être justifiée
par ce dossier. La condition de reprise est conjointe : la frontière pré-fit prouvée
ne suffit pas. La reprise est donc non admissible, sans modification du protocole,
nouvelle variante PL8, nouvelle file ou retry. Cette décision clôt ce contrôle borné,
pas la recherche scientifique globale autorisée.

Le dossier est conservé avec ses empreintes dans le
[reçu de réconciliation](PL8_BOUNDARY_B_1719_1720_RECOVERY_DECISION_20260921.json).
TI-090 reste un incident technique ouvert tant qu'aucune réparation durable n'est
démontrée. Aucun résultat scientifique négatif ou favorable de PL8 n'est inféré.
