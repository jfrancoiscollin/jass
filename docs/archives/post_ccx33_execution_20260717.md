# Suite scientifique après `ccx33`

Date : 2026-07-17. Statut : implémenté et jobs préparés, aucun job soumis.

## Décision

La chaîne T1-bis → T2 → T3 est complète et non régressive, mais elle ne
montre pas de gain Elo certain. Les trois intervalles recouvrent 50 % et la
conversion globale reste proche de 66–67 %. C'est le cas D de
`codex_review_v3_2.md` : on ferme la sonde ADJ+G1 après T3 et on ne lance ni
T4 ni campagne longue sur ce seul résultat.

La suite vise quatre questions distinctes :

1. l'environnement MTC était-il réellement utilisable sous concurrence ?
2. l'érosion P3 est-elle réelle sur des positions fraîches et aveugles au
   candidat teacher ?
3. un bras teacher retenu par le smoke apporte-t-il au moins +2 points sur
   P3 sans régression générale ni P4 ?
4. pourquoi la seconde tentative T3 a-t-elle perdu son code de sortie alors
   qu'une première tentative complète reste le verdict scientifique ?

## Séquence préparée

| Ordre | Job | Condition d'entrée | Verdict produit |
|---|---|---|---|
| 1a | `ccx33-0778-mtc-audit-v1` | aucune | audit chemin, inventaire, cache et lectures MTC concurrentes sur `ccx33` |
| 1b | `cpx62-0779-mtc-audit-v1` | aucune | même audit sur `cpx62` |
| 2 | `ccx33-0780-t3-attempt-diagnostic-v1` | renseigner le préfixe exact de la tentative T3 `_FAILED` | cause probable et confirmation que le succès antérieur reste autoritaire |
| 3 | `ccx33-0781-p3-blind-holdout-v1` | 0777=`confirm_b1|b2|b3` et 0778 vert | holdout P3/P4 frais, dimensionné avant de voir le bras teacher |
| 4 | `ccx33-0782-teacher-p3-confirm-v1` | 0781=`ready` | confirmation ou rejet de l'unique bras retenu par 0777 |

Les jobs 0781 et 0782 ne doivent pas être soumis si 0777 conclut
`complete_no_signal`. Le job 0775 du fork C est désormais bloqué tant que 0774
n'a pas produit `proceed_t1` **et** que l'audit 0779 du même hôte n'est pas
complet. Aucun T2-C n'est enchaîné automatiquement.

## Audit MTC

L'audit échoue si le chemin MTC est absent, vide ou illisible, si le budget
du pic prévu de 24 processus × 384 Mio dépasse la mémoire, ou si l'un des deux
probes concurrents échoue. Son manifest consigne l'hôte, le chemin exact, le nombre et la taille
des fichiers ainsi qu'une empreinte SHA-256 de l'inventaire noms+tailles.

Cette empreinte identifie l'installation sans relire les quelque 29 Go de la
base. Les jobs scientifiques suivants relisent l'audit vérifié, recalculent
l'inventaire noms+tailles, et exigent `audit_level=complete`,
`concurrent_smoke_ok=true`, le même chemin et le même hostname.

## Confirmation P3 fraîche

Le holdout est généré par self-play T0 fixe avec seed figée `77801`; aucun
poids B1/B2/B3 n'est chargé pendant sa construction. Les positions sont
relabelisées d14+EGDB, limitées aux strates P3/P4 et dédupliquées contre la
jauge et le pool G1 historiques.

La taille P3 est calculée avant confirmation pour détecter un écart absolu de
`+0,02`, avec puissance `0,80` et alpha bilatéral `0,05`. La confirmation :

- n'évalue que le gagnant unique pré-engagé par 0777 ;
- exige le nombre de positions annoncé par le calcul de puissance ;
- exige `ΔP3 >= +0,02` et une borne basse conservatrice strictement positive ;
- rejette une régression générale établie contre A ou la référence absolue ;
- rejette une baisse ponctuelle P4 inférieure à `-0,02`.

Un holdout insuffisant ou une absence de signal est un résultat scientifique
complet, pas une autorisation d'ajuster le seuil puis de relancer.

## Diagnostic de tentative et visibilité GitOps

Le runner écrit désormais le vrai code de sortie depuis un trap `EXIT`. Si le
wrapper disparaît avant de pouvoir l'écrire (SIGKILL, perte d'hôte, cgroup),
il produit un diagnostic explicite avec sa dernière observation `/proc` au
lieu d'un simple `-1`. Le job 0780 compare de façon vérifiée le manifest du
succès T3 et celui de l'échec, puis cherche les indices OOM, disque plein,
teardown de `/tmp`, kill explicite ou signal dans les logs et journaux.

Les statuts `jass-control` embarquent aussi les petits JSON scientifiques
explicitement autorisés (décisions, audits, puissance et diagnostic). Chaque
fichier est limité à 64 Kio et l'ensemble à 256 Kio ; poids, corpus et logs
restent dans le stockage objet.

## Matrice de décision finale

| Résultat | Action |
|---|---|
| 0777 sans signal | fermer teacher v1 ; ne pas fabriquer de confirmation |
| 0777 avec un gagnant, 0781 insuffisant | consigner le manque de positions ; ne pas recycler le holdout |
| 0782 rejet technique | corriger uniquement l'infrastructure puis rejouer à l'identique |
| 0782 sans confirmation ou avec régression | fermer le bras teacher v1 |
| 0782 confirmé | préparer une PR séparée de promotion/campagne longue avec ce seul bras |
| 0774 sans `proceed_t1` | fermer fork C |
| 0774 `proceed_t1` + 0779 vert | autoriser uniquement 0775, puis relire son verdict avant toute suite |
