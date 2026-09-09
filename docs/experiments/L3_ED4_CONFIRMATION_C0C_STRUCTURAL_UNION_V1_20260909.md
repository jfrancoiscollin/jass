# ED4 C0C — union structurelle d'exclusion

Date : 2026-09-09. Statut : **PRÉENREGISTREMENT PROSPECTIF AVANT LECTURE DES PAYLOADS C0B**.

Parent immuable : `cpx62-1897-l3-ed4-c0b-structural-payload-freeze-v2`, attempt `20260909T210053Z-a3efc988`, code `a3efc988d8ff0b5642ab65fa0bf133897ee2f54c`. Manifest C0B : `c04c5ad0a3c6b98d6d3c86575f1ba5607cdad17e92ae5b1ed4108aeb81274bda`. C0A : `0af828dbc84b7103ad2aa54196c2ca18f81b3afab01b4daa6e256ffd87ecb219`.

C0C ouvre uniquement les 726 candidats gelés par C0B afin d'en extraire des **identités de positions à exclure**. Cela n'est pas un corpus de confirmation et ne peut autoriser aucune évaluation ED4.

## Contrat de lecture

Pour JNNW/JNNW.gz, le format compté est `JNNW + u32 count + count * 38 bytes`. C0C décode seulement les 33 premiers octets de chaque record (`wm,wk,bm,bk,stm`) et saute les cinq derniers octets sans les décompacter ni les interpréter. `target_fields_decoded` doit donc rester exactement 0. Les FEN sont canonicalisées avec l'implémentation historique gelée. Les TSV n'acceptent que les colonnes explicites `canonical_identity`, `canonical_fingerprint`, `raw_fingerprint` ou `fen`; toute autre structure échoue fermée. Les fichiers d'identités doivent contenir uniquement des fingerprints canoniques valides. JSM/JSM.gz sont des sidecars de contexte alignés aux JNNW et ne portent pas seuls une position : ils contribuent zéro identité.

Chaque payload est téléchargé uniquement après authentification runner-v3 et doit correspondre exactement au chemin, SHA256 et `size_bytes` du manifest C0B. Un drift, un format non reconnu, une ligne invalide ou un fichier candidat sans champ de position reconnu donne un échec technique/parse, jamais une autorisation.

## Sortie et frontière

La sortie est une union ASCII triée et unique de fingerprints canoniques. Elle est **sur-inclusive** : elle servira à exclure des positions de la future confirmation. Elle ne peut jamais rendre une position ancienne fraîche. Ce C0C ne couvre encore que les 34 producteurs restés ambigus après C0A-v2 ; les sources `included_exact`/superset de C0A seront combinées séparément avant la sélection fraîche terminale.

Zéro search, teacher, fit, game, promotion, bake ou alpha. Zéro score/WDL/q-value/modèle lu. ED4, CURRICULUM, les seuils et les gates restent inchangés.
