#!/usr/bin/env bash
# id: ccx33-0549-salvage-feeder
# description: SALVAGE du gen partiel du feeder 0547 tué (JFC "kill ccx33 et essaye de recuperer son gen"). Le feeder
# streame les records sur disque dans /root/cw-feeder/sp.jnnw.* mais ne committe qu'a la fin ; un kill laisse ces
# fichiers (records valides, compteur d'en-tete perime). On recompte depuis la TAILLE (octets/38), on merge les
# records valides, on gzippe et on committe. PAS de build (pur python, rapide). Si le workdir n'a pas survecu au kill,
# on le dit proprement. AUCUN NNUE. expected_duration: <2 min.
set -uo pipefail
cd /root/jass
ART="/root/jass/jobs/results/ccx33-0549-salvage-feeder/artefacts"; mkdir -p "$ART"
RES="$ART/RESULTS.txt"; : > "$RES"; say(){ echo "$@" | tee -a "$RES"; }
FEEDER_W=/root/cw-feeder

say "=== SALVAGE feeder 0547 : harvest $FEEDER_W/sp.jnnw.* ==="
if ! ls "$FEEDER_W"/sp.jnnw.* >/dev/null 2>&1; then
  say "  AUCUN fichier $FEEDER_W/sp.jnnw.* -> le workdir n'a PAS survecu au kill (runner l'a wipe)."
  say "  Rien a recuperer. (Lecon retenue : checkpoint incremental pour les futurs feeders.)"
  say "=== fin salvage (vide) ==="
  exit 0
fi
say "  fichiers trouves :"; ls -l "$FEEDER_W"/sp.jnnw.* 2>/dev/null | awk '{print "    "$5" "$9}' | tee -a "$RES"

python3 - "$FEEDER_W" "$ART/corpus-gen1b-salvaged.jnnw" <<'PY' 2>&1 | tee -a "$RES"
import glob,struct,sys
W,out=sys.argv[1],sys.argv[2]; REC=38; body=b""; tot=0; parts=[]
for f in sorted(glob.glob(f"{W}/sp.jnnw.*")):
    try: raw=open(f,'rb').read()
    except Exception as e: parts.append((f.split('/')[-1],f"ERR:{e}")); continue
    if len(raw)<8 or raw[:4]!=b'JNNW': parts.append((f.split('/')[-1],"NON-JNNW")); continue
    n=(len(raw)-8)//REC            # recompte depuis la taille (en-tete perime, on l'ignore)
    body+=raw[8:8+n*REC]; tot+=n; parts.append((f.split('/')[-1],n))
open(out,'wb').write(b'JNNW'+struct.pack('<I',tot)+body)
print(f"  SALVAGED {tot} positions : "+", ".join(f"{k}={v}" for k,v in parts))
PY

NS=$(python3 -c "import struct;print(struct.unpack('<I',open('$ART/corpus-gen1b-salvaged.jnnw','rb').read(8)[4:8])[0])" 2>/dev/null || echo 0)
if [ "${NS:-0}" -ge 1 ]; then
  gzip -f "$ART/corpus-gen1b-salvaged.jnnw"
  say "  corpus-gen1b-salvaged.jnnw.gz : ${NS} positions, $(du -h "$ART/corpus-gen1b-salvaged.jnnw.gz" | cut -f1)"
  say "  => corpus recupere, poolable (a cabler dans un fit poole si on veut)."
else
  say "  0 position recuperee."
fi
say "=== fin salvage ==="
