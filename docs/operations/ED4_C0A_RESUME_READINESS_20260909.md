# ED4-C0A — reprise technique du 9 septembre 2026

La PR #886 a été revue puis intégrée à `develop` au commit
`f21de03bdc1d356f90fe7cbfaa36757aef6c7400` après lecture des résultats CI :
94 tests Python de `pattern_jass`, 13 tests descriptor ED4, builds natif/WASM,
retirement-readiness et registre technique réussis. La revue Copilot était
indisponible pour quota ; la revue a été faite dans la session de reprise.
Les reçus ED4-P1 sont consignés par #886 ; cette reprise ne revendique pas une
nouvelle authentification R2 des fits 1887/1888.

## Ajout technique borné

`ed4_source_inventory_stage.py` branche l'admission descriptor-only existante
sur les preuves `StageEvidence` du lanceur V2. Le profil enregistré fixe le
même chemin dans les deux modes, les quatre phases, le reçu metadata unique,
les suites de régression et tous les effets scientifiques à zéro. La garde
disque est de 3 Gio. `ED4_CONTROL_REPO` doit nommer le clone contrôle disponible
sur la machine ; le snapshot lu reste exactement
`3ae5a3980ee60816ef078124deafa72b2e2f4662`, jamais sa tête courante.

L'outil d'inventaire, les allowlists, le parser de projection et le protocole
C0A de #886 restent byte-identiques. Le nouveau wrapper ne sélectionne aucune
position et n'ouvre aucun payload de source. Un descripteur absent ou un
producteur inconnu donne un terminal technique terminé avec verdict
`ED4_C0A_INVENTORY_ADMISSION_INSUFFICIENT_V1`, pas une réussite scientifique.
Les échecs d'authentification ou de relecture ferment l'admission et publient
seulement le type d'erreur et les positions de code, pas les messages bruts.

## Validation et frontière restante

La validation locale de la session est limitée à la compilation syntaxique des
nouveaux modules Python. Les tests ajoutés exercent les fixtures synthétiques,
les phases, les deux modes, les corruptions, les compteurs et le profil. Le test
pipeline passe par le véritable runner v1, le publisher et le fetcher avec le
seul transport R2 remplacé par un stockage local. La CI dédiée exécute les deux
suites génériques et les trois suites C0A. Son résultat doit être lu avant
fusion ; l'existence du workflow ne constitue pas une preuve de réussite.

Aucune file CPX n'est créée par ce changement. Avant admission distante, il
reste à figer le code validé, publier une spec et une admission V2 hash-pinnées,
vérifier le sizing et exécuter la répétition sur la machine cible. Sa publication
R2 et sa relecture sont nécessaires avant une production identique. Les reçus
des fits ED4-P1 ne peuvent pas autoriser ce nouveau profil.

Même une admission inventory-only complète n'est pas l'audit structurel C0A,
ne prouve pas un univers frais et n'autorise aucune confirmation. Le candidat
ED4, `STOP_ED3`, les seuils, les budgets alpha et `CURRICULUM` restent inchangés.
