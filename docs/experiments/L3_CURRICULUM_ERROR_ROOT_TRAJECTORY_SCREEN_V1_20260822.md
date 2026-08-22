# CURRICULUM — écran action-conditionnel par trajectoire root

Les audits 1486–1489 ferment les mises à jour PatternEval : aucune direction
globale ou conditionnelle phase/rois/tactique ne réplique sans abaisser les
seuils. Les contrôleurs de profondeur/pruning 1476–1478 et le conseil child-WDL
CTX4 sont également fermés.

Cette nouvelle hypothèse ne modifie ni la value CURRICULUM ni l’arbre exploré.
Pour chaque action root déjà scorée aux profondeurs complètes 8 et 9, elle
extrapole une pente bornée : `s9 + beta × clip(s9-s8, ±100 cp)`. La règle ne
peut remplacer le choix depth-9 que lorsque sa marge top1-top2 appartient à
une bande préenregistrée. Elle consomme donc exactement zéro nœud additionnel.

La famille est fixée avant lecture : beta 0,25/0,5/1,0 croisé avec des bandes
20/50/100 cp et « toujours », soit douze candidats. Seules les 160 erreurs
exactes du outer-discovery 1476 et leurs contrôles appariés sont ouvertes. Le
outer-confirm 1476 est consommé et interdit. Paires, openings et états exacts
restent atomiques dans un inner split 75/25. La sélection utilise inner-fit ;
un seul candidat sélectionné est évalué une fois sur inner-validation.

Un PASS interne n’autorise aucune règle de production. Il scelle seulement un
beta et une bande à confirmer sur une campagne entièrement fraîche, sans
overlap opening/état exact et avec le même champion, teacher, juge et search.

L’écran exécute zéro fit PatternEval, zéro modèle de production, zéro partie,
zéro self-play, zéro frozen et zéro promotion.
