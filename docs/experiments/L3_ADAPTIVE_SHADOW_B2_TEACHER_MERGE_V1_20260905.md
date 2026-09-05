# B2 — fusion physique du teacher et vérification native des coups

Date : 5 septembre 2026. Statut : préparation technique prospective du
[programme decision-information](L3_DECISION_INFORMATION_IMPLEMENTATION_PLAN_V1_20260903.md).
Ce contrat ne constitue pas le préenregistrement B2 et ne lance aucune cohorte.

Le [sélecteur et l'adapter teacher](L3_ADAPTIVE_SHADOW_B2_COHORT_TOOLING_V1_20260905.md)
produisent des parents scellés puis seize triples teacher. La fusion doit
conserver les observations de chaque ligne et prouver que toutes les actions
légales de chaque parent figurent exactement une fois dans le résultat.

## Contrat de fusion

`jobs/tools/adaptive_sibling_b2_teacher_merge.py` exige un manifeste d'entrée
authentifié par son SHA256, le reçu de sélection et les seize triples
`children.jnnw`, `groups.tsv`, `report.json`. Les parents sélectionnés restent
exactement 4 000, avec 500 parents dans chacune des huit cellules phase × STM.
Chaque parent possède entre deux et seize actions légales. Aucun paramètre CLI
ne permet de réduire ces cardinalités pour un smoke.

Le shard teacher `i` contient les parents `i, i+16, …`, soit 250 parents. La
fusion entrelace ces blocs dans l'ordre global des parents `0..3999` ; elle ne
concatène pas simplement les shards. Elle conserve les 43 colonnes du teacher,
à l'exception du `row_index` qui est réindexé globalement. Les cinq octets de
targets de chaque record JNNW doivent rester nuls. Les compteurs de recherche
et de création des moteurs restent ceux du teacher authentifié.

Les différences entre les plateaux parent et enfant reconstruisent le masque
complet des pièces capturées. Le registre structural définit une action par
`(from, to, num_captures, promotes, captured_square_bitboard)` et impose l'ordre
`(from, to, captured_square_bitboard, promotes)`. Plusieurs chemins décrivant
la même action ont un poids unitaire ; deux captures de mêmes extrémités mais
de masques différents restent distinctes. Un retour sur la case de départ
pendant une capture n'est pas interdit par principe.

## Preuve native

`jass_adaptive_sibling_b2_teacher_merge_verify` reçoit exactement trois
payloads : les parents sélectionnés, les enfants globaux temporaires et le
registre structural temporaire. Il utilise les vrais `Position`, `Move`,
`generate_legal_moves` et `Position::after` du moteur. Pour chaque parent, il
compare le catalogue légal complet, son ordre, chaque action et chaque plateau
enfant. Une différence de plateaux, seule, ne prouve pas la légalité d'une
capture ; le catalogue natif est donc obligatoire avant publication.

Le vérificateur n'ouvre aucun groups TSV, modèle ou fichier EGDB. Il n'effectue
ni recherche, ni fit, ni partie. Son reçu contient les SHA256 et tailles des
trois payloads et de l'exécutable. La provenance du build transmise en CLI est
explicitement nommée `build_provenance_declared` : le wrapper doit la relier
au checkout et au build réellement authentifiés.

## Provenance et publication

Les manifestes et registres de contrôle utilisent JSON ASCII canonique,
clés triées et LF final ; les clés dupliquées, types incorrects, valeurs hors
bornes, cardinalités incomplètes et collisions de chemins sont refusés.
Les reçus existants du teacher sont authentifiés dans leur encodage réel.
L'adapter n'atteste pas lui-même un `code_sha` ou le SHA de son outil : le
wrapper relie les bytes Git de l'outil, la source de base, le rendu reproduit
et les reçus. Les reports shard n'attestent pas non plus un commit absent de
leur schéma.

La fusion publie quatre fichiers après validation native :

- `children.jnnw` : enfants globaux, avec targets nuls ;
- `groups.tsv` : observations teacher conservées et index global ;
- `semantic-actions.jsonl` : identité complète et transition de chaque action ;
- le report de fusion, avec provenance, compteurs et reçu natif.

Le report décrit les trois payloads. Son propre SHA est calculé après
sérialisation et appartient au reçu externe de publication du wrapper, qui
authentifie les quatre artefacts. Le merger ne prétend pas produire une
empreinte de lui-même à l'intérieur du fichier qu'elle décrirait.

## Validation technique

Le build Release GCC 13.3 du vérificateur et son selftest CTest passent.
Une vérification native séparée valide 4 000 parents et 36 000 actions ; les
altérations d'enfant ou d'identité sont rejetées. Les sorties préexistantes,
liens symboliques pendants et fichiers temporaires appartenant à un autre
processus sont préservés lors du refus de publication.

La suite Python finale passe **9 tests sur 9 en 16,307 s sous Linux**, avec
les deux exécutables natifs fournis explicitement. Elle comprend la chaîne
complète sur une cohorte synthétique de 4 000 parents uniques, équilibrée en
huit cellules de 500, répartie en seize shards, puis la vérification native
des catalogues et des transitions. Elle vérifie aussi les compteurs, les
empreintes d'exclusion du contrat scellé, les dérives de blocs, les aliases,
les targets non nuls et l'invariance de l'identité aux valeurs des scores.

Le helper C++ des tests utilise les vrais coups légaux et `Position::after`.
Les observations et compteurs teacher de ces fixtures sont synthétiques :
ils testent le transport et ses contrôles, sans prouver l'exécution réelle
d'une recherche teacher. Cette preuve runtime relève du smoke historique
1776 et de son reçu terminal distinct.

Empreintes SHA256 des deux implémentations vérifiées :

- merger Python : `51d4e5464eac86258842ae4c37787edb7c039eab27716e48a49d4fbbb6b0c0d8` ;
- vérificateur C++ : `4daca7170bd98bf7cf62ffb549e43075b1a49f8a8094ed8cd8c9239a8e3a35ea`.

## Portée scientifique

Ces contrôles établissent une propriété technique du nouveau format et de sa
chaîne d'exécution. Ils ne complètent pas rétroactivement l'identité des coups
du TSV B1 historique, qui omet le masque de capture. Le reçu historique 1775
conserve ses [limites publiées](L3_ADAPTIVE_SHADOW_B2_LEGACY_EQUIVALENCE_RESULTS_20260905.md).

L'allocation sans q200, son scellement, le readout ultérieur, les statistiques
et le préenregistrement final restent des étapes distinctes. Aucun seuil de
confirmation, verdict B2, résultat de force, bake ou promotion ne découle de
la seule réussite de cette fusion. `CURRICULUM` reste champion.
