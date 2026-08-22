# CURRICULUM — refit résiduel local des erreurs v1

## But

Transformer une attribution causale confirmée `erreur → poids PatternEval` en
un candidat minimal, sans réentraîner l'évaluation complète et sans déplacer
les acquis hors de la région confirmée.

Ce protocole est conditionné au certificat
`JASS_CURRICULUM_ERROR_RESIDUAL_REGION_CONFIRMED`. Un atlas négatif ou incomplet
interdit le fit.

## Deux bras, un seul degré de liberté

- `ERROR_REGION` reprend exactement les coordonnées et les signes fixés sur le
  split discovery de l'atlas.
- `SHAM_REGION` contient le même nombre de buckets et de coordonnées. Chaque
  bucket est apparié dans les contrôles discovery sur le pattern, les phases
  MG/EG et la fréquence d'activation. Il ne peut chevaucher la région d'erreur.
  Le matching ne lit que le sous-split fit de discovery ; le sous-split
  calibration reste scellé.
- Les deux bras reçoivent le même pas entier.

Le seul hyperparamètre appris est ce pas. La grille préenregistrée est
`0,1,2,4,8,16,32,64` ticks du PJTW. La sélection minimise sur discovery une
loss de rang enseignant-rival, une pénalité des contrôles appariés et une
pénalité quadratique de trust-region. La confirmation n'est jamais lue pour
choisir le pas.

Cette construction évite un refit haute dimension sur quelques centaines de
décisions : la direction vient de l'atlas causal, le fit ne choisit que sa
dose.

Si aucune dose non nulle n'améliore l'objectif ancré, le job se termine avec
un verdict scientifique `NOT_ESTABLISHED` et ne publie aucun modèle.

## Gel exact

Les mises à jour sont appliquées dans l'espace canonique
rotation-180°+échange-des-couleurs puis répliquées avec le signe exact sur toute
l'orbite. Après sérialisation :

- le header du champion est copié octet pour octet ;
- aucun extra dense ne bouge ;
- aucun coefficient PatternEval hors orbite autorisée ne bouge ;
- chaque orbite reste antisymétrique en entiers ;
- tout drift hors région avorte le job.

## Écrans

Le modèle n'est publié que si, sur le split confirmation scellé :

1. le gain de marge enseignant-rival de `ERROR_REGION` est positif à 95 % ;
2. `ERROR_REGION − SHAM_REGION` est positif à 95 % ;
3. les contrôles ne sont pas dégradés à 95 % au-delà de la tolérance
   préenregistrée ;
4. le gain erreur moins contrôle est positif à 95 %.

Ce PASS n'autorise encore aucune partie de force. Il autorise seulement une
nouvelle campagne d'erreurs sur ouvertures fraîches, avec le même teacher et
le même juge, afin de mesurer le transfert à travers la recherche native :

- baisse du taux d'erreurs de regret ≥50 cp ;
- baisse du regret moyen ;
- `ERROR_REGION` supérieur au sham ;
- absence de hausse hors région ;
- symétrie exacte et calibration conservées.

Le refit authentifie les 353 paires sources, mais exige exactement les 290
erreurs qui restent >= 50 cp après le juge exact. Les 63 sources reclassées et
leurs contrôles appariés sont exclues ensemble du matching sham, du choix du
pas, de la calibration et de la confirmation. Un gradient nul reclassé ne peut
donc jamais compter comme observation favorable.

Seulement après ce second écran peuvent être lancés deux pools frais disjoints
de force, native 0,1 s primaire et Q00 d9 diagnostic. Aucune promotion n'est
automatique.

## Interdits

Cette étape ne lit aucune cohorte frozen, ne génère aucun self-play, ne joue
aucune partie de force et ne modifie jamais CURRICULUM en place.

Le wrapper de production authentifie l'atlas immuable 1485, ses 16 shards et
le CURRICULUM brut par SHA-256. Un verdict atlas autre que `CONFIRMED` avorte
avant refit. Une science locale négative termine normalement mais ne publie
aucun candidat; une science positive publie les deux bras ERROR et SHAM avec
header identique et audit indépendant du gel hors région.
