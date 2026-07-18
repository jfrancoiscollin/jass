> ⚠️ **ARCHIVE — NE PAS PRENDRE COMME CONSIGNE ACTIVE.** Doc historique (ère pré-fit-volume / NNUE).
> Source de vérité unique = [CURRENT.md](../L3_CURRENT.md) (+ docs système : BOUCLE_VIRTUEUSE, SCAN_METHODOLOGY_GAP,
> DIAGNOSTIC_VS_SCAN, BIAIS_FIT_VOLUME, PROGRESSION_LITTERATURE). Conservé pour l'historique seulement. _(Classé archive 2026-06-24.)_

# Stockage objet durable (object-store) — préparation & activation

> **État : PRÉPARÉ, DORMANT.** L'outillage (`tools/objstore.sh`) est en place et no-op tant qu'il n'est pas
> configuré (il ne casse aucun job). Il s'active dès que tu fournis **un remote + des credentials**. Construit
> maintenant pour ne pas reproduire la perte des gros datasets historiques (0106/0084/9.48M, jamais committés).

## Pourquoi (rappel)
- **git** stocke durablement jusqu'à ~**30-50M** de corpus (shards gz ≤95Mo ; repo qui reste raisonnable, ≤~500Mo).
- **Au-delà** (100M → 1B = ~**1 à 9 Go** de shards), git devient ingérable → il faut un **store objet** S3-compatible.
- Les labels **WDL sont arch-indépendants** ⇒ ce corpus est **réutilisable à jamais**, y compris pour un futur **NNUE**.

## Ce que TU dois fournir (3 choses)
1. **Un bucket** chez un fournisseur S3-compatible. Reco : **Cloudflare R2** (pas de frais d'egress) ou **Backblaze B2** (très bon marché). AWS S3 / MinIO / Wasabi / DO Spaces marchent aussi.
2. **Des credentials** (Access Key ID + Secret) avec accès en lecture/écriture à ce bucket.
3. **Confirmer l'egress** : la policy réseau du runner doit autoriser les sorties vers l'endpoint du bucket (et vers `downloads.rclone.org` pour bootstrapper le binaire rclone, une fois).

## Méthode FACILE — variables d'env natives rclone (recommandée, ni terminal ni base64)
Pose directement ces variables dans la config d'environnement du runner (la dernière est un SECRET).
Le nom du remote (`R2` ici) doit matcher le préfixe de `JASS_OBJSTORE_REMOTE` (`r2:`), insensible à la casse.
```
JASS_OBJSTORE_REMOTE              = r2:jass-data
JASS_OBJSTORE_PREFIX              = corpus
RCLONE_CONFIG_R2_TYPE             = s3
RCLONE_CONFIG_R2_PROVIDER         = Cloudflare
RCLONE_CONFIG_R2_ENDPOINT         = https://<ACCOUNT_ID>.r2.cloudflarestorage.com
RCLONE_CONFIG_R2_ACCESS_KEY_ID    = <ACCESS_KEY_ID>
RCLONE_CONFIG_R2_SECRET_ACCESS_KEY= <SECRET_ACCESS_KEY>   # SECRET
```

## Méthode B (alternative) — un seul secret base64
```
JASS_OBJSTORE_REMOTE = "r2:jass-data"            # <remote rclone>:<bucket>
JASS_OBJSTORE_PREFIX = "corpus"                  # optionnel (sous-dossier)
RCLONE_CONF_B64      = "<base64 de rclone.conf>" # SECRET — contient les credentials
```
Génère `RCLONE_CONF_B64` à partir d'un `rclone.conf` (un des modèles ci-dessous) :
```bash
base64 -w0 rclone.conf      # colle la sortie dans le secret RCLONE_CONF_B64
```

### Modèle rclone.conf — Cloudflare R2 (recommandé)
```ini
[r2]
type = s3
provider = Cloudflare
access_key_id = <ACCESS_KEY>
secret_access_key = <SECRET>
endpoint = https://<ACCOUNT_ID>.r2.cloudflarestorage.com
acl = private
```
### Modèle — Backblaze B2 (via S3)
```ini
[b2]
type = s3
provider = Other
access_key_id = <KEY_ID>
secret_access_key = <APP_KEY>
endpoint = https://s3.<REGION>.backblazeb2.com
acl = private
```
### Modèle — AWS S3
```ini
[s3]
type = s3
provider = AWS
access_key_id = <ACCESS_KEY>
secret_access_key = <SECRET>
region = <REGION>
```
> Le nom de section (`r2`/`b2`/`s3`) doit matcher le préfixe de `JASS_OBJSTORE_REMOTE`.

## Utilisation (une fois activé)
```bash
tools/objstore.sh check         # vérifie config + connectivité (lsd)
tools/objstore.sh sync-shards   # pousse TOUS les shards corpus committés vers le bucket
tools/objstore.sh list          # liste le contenu distant
tools/objstore.sh pull <name> <localfile>   # récupère un shard
```
`sync-shards` nomme chaque objet `<job-id>__<fichier>` (ex. `cpx62-0391-corpus-d10__corpus-d10.jnnw.gz`)
pour une traçabilité 1:1 avec le manifeste (`docs/CORPUS_30M_MANIFEST.md`).

## Intégration dans le flux (quand on dépassera ~30-50M)
- **Job de sync dédié** : un maillon `jobs/queue/<host>-NNNN-objstore-sync.sh` qui appelle `objstore.sh sync-shards`
  (tourne sur une box → a la data + le réseau). Modèle prêt sur la branche, **non déployé** tant que dormant.
- **Option** : à terme, faire committer aux maillons un **petit pointeur** (nom + compte + taille) au lieu du shard gz
  lui-même → git ne porte plus que l'index, le store porte la data. À décider au moment du basculement >50M.

## État actuel
- ≤30M visés pour GATE 0/1 → **git suffit**, le store n'est pas encore nécessaire (mais prêt).
- Bascule recommandée vers le store **si** les gates montrent que le volume paie encore et qu'on vise 100M+.

## Diagnostic 2026-06-21 — testé, encore DORMANT (et pourquoi)
Variables R2 posées (session Claude + bucket Cloudflare R2 OK), mais **personne ne peut pousser en l'état**.
Cause structurelle : les credentials et l'egress ne se trouvent jamais dans le **même** environnement.

| Environnement | Creds R2 | Egress R2 | Peut pousser ? | Vérif |
|---|---|---|---|---|
| Session Claude (conteneur orchestrateur) | ✅ (config env claude.ai) | ❌ **proxy 503** | non | session parallèle |
| **Box runner** (Hetzner cpx62/ccx33) | ❌ (config claude.ai n'y descend PAS) | ✅ ouvert | non | probe **0406** |
| Cette session (ancienne) | ❌ | ❌ | non | env vide |

- La config d'environnement claude.ai **n'alimente que les conteneurs Claude**, jamais les machines Hetzner du runner.
- On **ne committe jamais** de secret dans un job (git) → on ne peut pas « passer » les creds au runner par ce canal.

**Aucune perte possible pour autant** : le corpus 30M est déjà durable (shards ≤95 Mo committés `origin/main`).
R2 ne sert qu'au **futur** (>95 Mo : bitbases Kingsrow, corpus 100M+). Donc déféré sans risque.

### Les deux seuls chemins d'activation
1. **Ouvrir l'egress de l'environnement** (pas d'accès box requis) : autoriser **l'hôte de
   `RCLONE_CONFIG_R2_ENDPOINT`** (`…r2.cloudflarestorage.com`) dans la policy réseau → la session Claude
   pousse via `tools/objstore.sh sync-shards`. Resservira pour `pull`.
2. **Poser les creds sur les box runner** (accès direct aux machines Hetzner requis) → le runner pousse
   (il a déjà l'egress ouvert, confirmé par 0406).

**Reco** : option 1 le jour où un artefact dépasse 95 Mo. D'ici là, rien à faire.
