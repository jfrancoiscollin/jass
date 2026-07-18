# Jobs préparés — suite de `ccx33`

Ces scripts restent hors de `jobs/queue/` et de
`jass-control/queue/pending/` : les merger ne déclenche aucun calcul.

Ordre recommandé après revue :

1. soumettre indépendamment `ccx33-0778-mtc-audit-v1.sh` et
   `cpx62-0779-mtc-audit-v1.sh` ;
2. renseigner `T3_FAILED_RUN_PREFIX`, puis soumettre
   `ccx33-0780-t3-attempt-diagnostic-v1.sh` ;
3. attendre le verdict exact du job 0777 ;
4. seulement si 0777 vaut `confirm_b1`, `confirm_b2` ou `confirm_b3`, renseigner
   ses préfixes vérifiés et soumettre `ccx33-0781-p3-blind-holdout-v1.sh` ;
5. seulement si 0781 vaut `ready`, soumettre
   `ccx33-0782-teacher-p3-confirm-v1.sh` avec les trois préfixes exacts.

Le job `cpx62-0775-forkc-t1-v1.sh`, préparé dans le lot précédent, exige
maintenant le préfixe exact du C0 0774 et celui de l'audit MTC 0779. Il s'arrête
proprement si C0 n'autorise pas `proceed_t1` et échoue techniquement si l'audit
MTC n'est pas complet ou vient d'un autre hôte.

Voir `docs/archives/post_ccx33_execution_20260717.md` pour les seuils pré-engagés et la
matrice de décision.
