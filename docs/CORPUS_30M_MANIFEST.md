# Manifeste du corpus 30M — shards committés (traçabilité durable)

> Généré par `tools/corpus_manifest.sh` le **2026-06-20T22:11:53Z**. Ne PAS éditer à la main : re-lancer le script.
> Raison d'être : éviter qu'un shard se "volatilise" sans trace (cf. 0106/0084/9.48M perdus, faute
> d'avoir été committés). Chaque shard ci-dessous est dans git (`artefacts/`, durable), pas en `artefacts.src`.

**Total : 16610792 positions · 152 Mo gz · 11 shards.**

| Shard (chemin git origin/main) | Records | Taille gz |
|---|---|---|
| `jobs/results/ccx33-0384-corpus-d10/artefacts/d10-corpus.jnnw.gz` | 3010792 | 27.6 Mo |
| `jobs/results/ccx33-0385-corpus-d12/artefacts/corpus-d12.jnnw.gz` | 400000 | 3.6 Mo |
| `jobs/results/ccx33-0386-corpus-d10/artefacts/corpus-d10.jnnw.gz` | 800000 | 7.3 Mo |
| `jobs/results/ccx33-0387-corpus-d12/artefacts/corpus-d12.jnnw.gz` | 400000 | 3.6 Mo |
| `jobs/results/ccx33-0388-corpus-d10/artefacts/corpus-d10.jnnw.gz` | 800000 | 7.3 Mo |
| `jobs/results/cpx62-0391-corpus-d10/artefacts/corpus-d10.jnnw.gz` | 1400000 | 12.8 Mo |
| `jobs/results/cpx62-0392-corpus-d10/artefacts/corpus-d10.jnnw.gz` | 1400000 | 12.8 Mo |
| `jobs/results/cpx62-0393-corpus-d10/artefacts/corpus-d10.jnnw.gz` | 1400000 | 12.8 Mo |
| `jobs/results/cpx62-0394-corpus-d10/artefacts/corpus-d10.jnnw.gz` | 1400000 | 12.8 Mo |
| `jobs/results/cpx62-0395-corpus-d10/artefacts/corpus-d10.jnnw.gz` | 2800000 | 25.7 Mo |
| `jobs/results/cpx62-0396-corpus-d10/artefacts/corpus-d10.jnnw.gz` | 2800000 | 25.7 Mo |

## Réassemblage (point de reconstruction)
```bash
tools/corpus_manifest.sh assemble /root/cw-corpus/big.jnnw   # décompresse+fusionne tous les shards en UN .jnnw
```
Puis le fit au scale : `pattern_jass/tools/train_stream.py --data big.jnnw ...` (streaming disque, gradient exact).

## Vérification d'intégrité
- Un shard à `⚠️VIDE/ILLISIBLE` = en-tête JNNW absent → **alerte** (comme 0106 dont les shards committés font 0 octet).
- Re-lancer ce script après chaque finalize de maillon corpus pour rafraîchir le total.
