#!/usr/bin/env bash
# id: ccx33-0576-eval-oracle-d6
# description: DIAGNOSTIC EVAL-vs-SCAN (JFC "Va y", plan eval). Isole l'EVAL de la RECHERCHE : compare la static-eval de
# jass (gen1, --eval-position, depth 0) a la static-eval de Scan (relabel_with_scan, depth 1 = le plus proche du static,
# book off) sur ~4000 positions reelles echantillonnees a travers corpus-mix2M (2M, mix pd8/9/10, toutes phases).
# Sorties : correlation Pearson + Spearman (rang), fit lineaire s_jass~a*s_scan+b, RESIDU bucketé par PHASE (nb pieces)
# et par |s_scan| ; + ancres : correl jass-vs-label-selfplay et scan-vs-label (detecte la circularite/plafond-label).
# ROUTAGE : (a) correl haute + residu faible => notre retard est SEARCH, valide le pivot EBF, on arrete l'eval. (b) residu
# concentre (finale/une phase) => LABELS => re-label EGDB-exact + refit cible. (c) residu diffus / correl basse =>
# CAPACITE/overfit => DOE feature-group. VERDICT committe JOB-SIDE. AUCUN NNUE, aucune recherche modifiee (juste mesure).
set -uo pipefail
cd /root/jass
NCPU=$(nproc); export TMPDIR=/root/jass/.compile-tmp; mkdir -p "$TMPDIR"
ART="/root/jass/jobs/results/ccx33-0576-eval-oracle-d6/artefacts"; mkdir -p "$ART"
ARTREL="jobs/results/ccx33-0576-eval-oracle-d6/artefacts"
W=/root/cw-evaloracle; rm -rf "$W"; mkdir -p "$W"
GEN1_GZ=jobs/results/cpx62-0545-selfplay-gen1-combo/artefacts/champion-gen1-combo.pjtw.gz
CORPUS_GZ=jobs/results/cpx62-0556-gen2M-mixdepth/artefacts/corpus-mix2M.jnnw.gz
K=4000; SCAN_DEPTH=6
LOG="$W/run.log"; note(){ echo "$@" | tee -a "$LOG"; }

commit_to_main(){ local abspath="$1" relpath="$2" msg="$3"
  for a in 1 2 3 4 5; do
    git fetch origin main --quiet 2>/dev/null || true
    local idx="/root/.ti.$$.$RANDOM"; rm -f "$idx"
    GIT_INDEX_FILE="$idx" git read-tree origin/main 2>/dev/null || return 1
    local blob; blob=$(git hash-object -w "$abspath") || return 1
    GIT_INDEX_FILE="$idx" git update-index --add --cacheinfo 100644 "$blob" "$relpath"
    local tree; tree=$(GIT_INDEX_FILE="$idx" git write-tree)
    local commit; commit=$(printf '%s\n' "$msg" | git commit-tree "$tree" -p origin/main)
    if git push origin "$commit:main" 2>/dev/null; then rm -f "$idx"; return 0; fi
    sleep $((a*3))
  done; return 1; }

# ---------- 0. Scan pret (binaire pre-build persistant, data binary-relative) ----------
SCAN_BIN=/root/jass-scan/scan_linux
if [ ! -x "$SCAN_BIN" ]; then
  note "install Scan (rhalbersma/scan pre-built)..."
  SRC=/root/jass-scan-src
  [ -d "$SRC" ] || git clone --depth=1 https://github.com/rhalbersma/scan.git "$SRC" || { note "ABORT clone scan"; exit 3; }
  mkdir -p /root/jass-scan
  cp "$SRC/scan_linux" "$SCAN_BIN"; chmod +x "$SCAN_BIN"
  cp -r "$SRC/data" /root/jass-scan/data 2>/dev/null || true
  cp "$SRC/scan.ini" /root/jass-scan/scan.ini 2>/dev/null || true
fi
[ -x "$SCAN_BIN" ] || { note "ABORT Scan absent"; exit 3; }
note "Scan pret : $SCAN_BIN"

# ---------- 1. build jass + gen1 + corpus ----------
note "=== build jass depuis main (archi complete) — HEAD $(git log --oneline -1|cat) ==="
cmake -S . -B "$W/build" -DCMAKE_BUILD_TYPE=Release -DJASS_ENDGAME_FEATURES=ON -DJASS_KING_MOBILITY=ON \
      -DJASS_SCAN_PARITY=ON -DJASS_TEMPO_STAGE=ON >"$W/cmake.log" 2>&1
cmake --build "$W/build" -j"$NCPU" --target jass >"$W/build.log" 2>&1 || { note "BUILD FAIL"; tail -12 "$W/build.log"|sed 's/^/  /'; exit 6; }
J="$W/build/jass"
git show "origin/main:$GEN1_GZ" | gunzip > "$W/gen1.pjtw" || { note "ABORT gen1"; exit 4; }
git show "origin/main:$CORPUS_GZ" | gunzip > "$W/corpus.jnnw" || { note "ABORT corpus"; exit 4; }
note "  gen1 + corpus-mix2M prets"

# ---------- 2. echantillonne K positions reparties, ecrit sub.jnnw + fens.txt ----------
python3 - "$W/corpus.jnnw" "$W/sub.jnnw" "$W/fens.txt" "$W/meta.tsv" "$K" <<'PY' 2>&1 | tee -a "$LOG"
import sys,struct
inp,subp,fenp,metap,K=sys.argv[1],sys.argv[2],sys.argv[3],sys.argv[4],int(sys.argv[5])
REC=38
with open(inp,'rb') as f:
    magic=f.read(4); cnt=struct.unpack('<I',f.read(4))[0]
    assert magic==b'JNNW', magic
    data=f.read()
tot=len(data)//REC
step=max(1,tot//K)
idxs=list(range(0,tot,step))[:K]
def fen(wm,wk,bm,bk,stm):
    Wl=[];Bl=[]
    for sq in range(1,51):
        b=1<<(sq-1)
        if wm&b:Wl.append(str(sq))
        elif wk&b:Wl.append("K"+str(sq))
        elif bm&b:Bl.append(str(sq))
        elif bk&b:Bl.append("K"+str(sq))
    return f"{'B' if stm==1 else 'W'}:W{','.join(Wl)}:B{','.join(Bl)}"
recs=[]; fens=[]; meta=[]
for i in idxs:
    r=data[i*REC:(i+1)*REC]
    wm,wk,bm,bk=struct.unpack('<QQQQ',r[0:32])
    stm=r[32]; score=struct.unpack('<i',r[33:37])[0]; wdl=struct.unpack('<b',r[37:38])[0]
    pieces=bin(wm).count('1')+bin(wk).count('1')+bin(bm).count('1')+bin(bk).count('1')
    recs.append(r); fens.append(fen(wm,wk,bm,bk,stm)); meta.append((pieces,score,wdl))
with open(subp,'wb') as f:
    f.write(b'JNNW'); f.write(struct.pack('<I',len(recs)))
    for r in recs: f.write(r)
open(fenp,'w').write("\n".join(fens)+"\n")
with open(metap,'w') as f:
    for (p,s,w) in meta: f.write(f"{p}\t{s}\t{w}\n")
print(f"  echantillon : {len(recs)} positions (corpus {tot}, step {step})")
PY
NPOS=$(wc -l < "$W/fens.txt"); note "  positions retenues : $NPOS"

# ---------- 3. Scan static (depth 1, book off) sur sub.jnnw ----------
note "=== Scan static depth $SCAN_DEPTH (book off) sur $NPOS positions ==="
python3 tools/relabel_with_scan.py --in "$W/sub.jnnw" --out "$W/sub_scan.jnnw" \
    --scan "$SCAN_BIN" --depth "$SCAN_DEPTH" --timeout 20 --progress-every 500 >"$W/scan.log" 2>&1 \
    || { note "ABORT relabel scan"; tail -8 "$W/scan.log"|sed 's/^/  /'; exit 7; }
tail -3 "$W/scan.log"|sed 's/^/  scan> /'|tee -a "$LOG"

# ---------- 4. jass static-eval (gen1) sur les memes FENs, shardé ----------
note "=== jass static-eval (gen1) sur $NPOS positions, $NCPU shards ==="
split -n l/$NCPU --numeric-suffixes=0 -a2 "$W/fens.txt" "$W/fenshard."
jass_eval_shard(){ local sh="$1"; local out="$W/jass_${sh}.txt"; : >"$out"
  local ln=0
  while IFS= read -r fen; do
    [ -z "$fen" ] && continue
    v=$("$J" --eval-position "$W/gen1.pjtw" "$fen" 2>/dev/null | head -1)
    echo "$v" >> "$out"; ln=$((ln+1))
  done < "$W/fenshard.$sh"
}
for f in "$W"/fenshard.*; do sh="${f##*.}"; jass_eval_shard "$sh" & done; wait
# reassemble jass evals dans l'ordre des shards (split -n l = lignes contigues => concat = ordre original)
cat $(ls -v "$W"/jass_*.txt) > "$W/jass_eval.txt" 2>/dev/null || cat "$W"/jass_*.txt > "$W/jass_eval.txt"
note "  jass evals : $(wc -l < "$W/jass_eval.txt") / $NPOS"

# ---------- 5. analyse : correlations, residu par phase, ancres ----------
VERD="$ART/VERDICT_evaloracle.txt"
python3 - "$W/sub_scan.jnnw" "$W/jass_eval.txt" "$W/meta.tsv" "$SCAN_DEPTH" > "$VERD" <<'PY'
import sys,struct,math
scanf,jassf,metaf,sd=sys.argv[1],sys.argv[2],sys.argv[3],sys.argv[4]
REC=38
with open(scanf,'rb') as f:
    f.read(8); d=f.read()
n=len(d)//REC
s_scan=[struct.unpack('<i',d[i*REC+33:i*REC+37])[0] for i in range(n)]
jass=[l.strip() for l in open(jassf) if l.strip()!=""]
meta=[tuple(map(int,l.split('\t'))) for l in open(metaf) if l.strip()]
m=min(len(s_scan),len(jass),len(meta))
def num(x):
    try:return float(x)
    except:return None
s_jass=[num(x) for x in jass[:m]]
pairs=[(s_jass[i],float(s_scan[i]),meta[i][0],float(meta[i][1]),meta[i][2]) for i in range(m) if s_jass[i] is not None]
def pearson(xs,ys):
    k=len(xs);
    if k<3:return float('nan')
    mx=sum(xs)/k;my=sum(ys)/k
    sx=math.sqrt(sum((x-mx)**2 for x in xs));sy=math.sqrt(sum((y-my)**2 for y in ys))
    if sx==0 or sy==0:return float('nan')
    return sum((xs[i]-mx)*(ys[i]-my) for i in range(k))/(sx*sy)
def spearman(xs,ys):
    def rank(v):
        order=sorted(range(len(v)),key=lambda i:v[i]); r=[0]*len(v)
        for pos,i in enumerate(order): r[i]=pos
        return r
    return pearson(rank(xs),rank(ys))
J=[p[0] for p in pairs]; S=[p[1] for p in pairs]
print("=== VERDICT ccx33-0563 EVAL-vs-SCAN (isole l'eval de la recherche) ===")
print(f"positions appariees : {len(pairs)} ; jass=static(gen1,d0) ; scan=static(d{sd},book off) ; STM-POV cp")
print("")
r=pearson(J,S); rho=spearman(J,S)
print(f"CORRELATION globale : Pearson r={r:.4f}  Spearman rho={rho:.4f}")
# fit lineaire s_jass ~ a*s_scan+b
k=len(J);mx=sum(S)/k;my=sum(J)/k
den=sum((s-mx)**2 for s in S)
a=(sum((S[i]-mx)*(J[i]-my) for i in range(k))/den) if den else 0.0; b=my-a*mx
res=[J[i]-(a*S[i]+b) for i in range(k)]
rms=math.sqrt(sum(e*e for e in res)/k)
print(f"fit s_jass ~ {a:.3f}*s_scan + {b:.1f}  ; residu RMS global = {rms:.0f} cp")
print("")
print("RESIDU RMS par PHASE (nb pieces) — ou jass s'ecarte de Scan :")
for lo,hi,lab in [(0,8,'finale <=8'),(9,16,'milieu-fin 9-16'),(17,24,'milieu 17-24'),(25,40,'ouverture >=25')]:
    grp=[i for i in range(k) if lo<=pairs[i][2]<=hi]
    if not grp: print(f"  {lab:16s} : (aucune)"); continue
    rr=math.sqrt(sum(res[i]**2 for i in grp)/len(grp))
    rr2=pearson([J[i] for i in grp],[S[i] for i in grp])
    print(f"  {lab:16s} : n={len(grp):4d}  residu RMS={rr:6.0f} cp  correl_locale={rr2:.3f}")
print("")
print("RESIDU RMS par |s_scan| (equilibre vs decisif) :")
for lo,hi,lab in [(0,50,'|scan|<=50 equilibre'),(51,150,'51-150'),(151,400,'151-400'),(401,99999,'>400 decisif')]:
    grp=[i for i in range(k) if lo<=abs(pairs[i][1])<=hi]
    if not grp: print(f"  {lab:22s} : (aucune)"); continue
    rr=math.sqrt(sum(res[i]**2 for i in grp)/len(grp))
    print(f"  {lab:22s} : n={len(grp):4d}  residu RMS={rr:6.0f} cp")
print("")
# ancres : correl vs label self-play (circularite ?)
lab_score=[pairs[i][3] for i in range(k)]
print("ANCRES (label = score self-play stocke dans le corpus, STM-POV) :")
print(f"  correl jass-vs-label-selfplay : Pearson {pearson(J,lab_score):.4f}   (jass suit-il SA cible ?)")
print(f"  correl scan-vs-label-selfplay : Pearson {pearson(S,lab_score):.4f}   (Scan suit-il notre cible ?)")
print("")
print("ROUTAGE :")
print(f"  Pearson>~0.90 & residu faible & plat par phase => retard = SEARCH => valide pivot EBF, stop eval.")
print(f"  residu concentre finale/une phase            => LABELS => re-label EGDB-exact + refit cible.")
print(f"  correl basse / residu diffus                 => CAPACITE/overfit => DOE feature-group.")
print(f"  jass-vs-label >> jass-vs-scan                 => circularite (on fit notre propre vue, pas Scan).")
PY
cat "$VERD"

commit_to_main "$VERD" "$ARTREL/VERDICT_evaloracle.txt" "0563 eval-oracle : VERDICT job-side (jass static vs Scan static, residu par phase)" \
  && note "  VERDICT committe job-side ✓" || note "  ⚠ commit VERDICT echoue"
note "=== fin 0563 eval-oracle ==="
