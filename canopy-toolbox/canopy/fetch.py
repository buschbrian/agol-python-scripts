"""Download a published LAZ tile list with resume, size and header checks. Pure Python, no arcpy."""
from concurrent.futures import ThreadPoolExecutor, as_completed
import csv
import datetime
from pathlib import Path
import struct
import time
import urllib.request

CHUNK=1<<20

def read_manifest(path,tiles=None):
    with open(path,newline="",encoding="utf-8") as f:
        rows=[{"tile":r["tile"],"url":r["url"],"bytes":int(r["bytes"]),"points":int(r["points"])} for r in csv.DictReader(f)]
    if tiles:
        wanted=set(tiles);rows=[r for r in rows if r["tile"] in wanted]
        missing=wanted-{r["tile"] for r in rows}
        if missing: raise ValueError(f"Not in the manifest: {', '.join(sorted(missing))}")
    names=[r["url"].rsplit("/",1)[1] for r in rows]
    if len(set(names))!=len(names): raise ValueError("The manifest lists the same file twice")
    return rows

def header_points(head):
    """Point count from the first 375 bytes of a LAS or LAZ file (the header is never compressed)."""
    if head[:4]!=b"LASF": raise ValueError("not a LAS/LAZ file")
    if (head[24],head[25])>=(1,4): return struct.unpack("<Q",head[247:255])[0]
    return struct.unpack("<I",head[107:111])[0]

def _download(url,path,size,retries,wait,opener):
    for attempt in range(retries+1):
        have=path.stat().st_size if path.exists() else 0
        if have>size: path.unlink();have=0
        if have==size: return
        headers={"Range":f"bytes={have}-"} if have else {}
        try:
            with opener(urllib.request.Request(url,headers=headers),timeout=60) as r:
                # A server that ignores Range answers 200 with the whole file: start over rather than append.
                with open(path,"ab" if have and r.status==206 else "wb") as out:
                    while chunk:=r.read(CHUNK): out.write(chunk)
        except OSError:
            if attempt==retries: raise
            time.sleep(wait*2**attempt)
    have=path.stat().st_size if path.exists() else 0
    if have!=size: raise IOError(f"{have:,} bytes on disk, expected {size:,}")

def _one(row,out,retries,wait,opener):
    path=out/row["url"].rsplit("/",1)[1];points=None;detail=""
    try:
        _download(row["url"],path,row["bytes"],retries,wait,opener)
        with open(path,"rb") as fh: points=header_points(fh.read(375))
        status="ok" if points==row["points"] else "points-mismatch"
        if status!="ok": detail=f"header says {points:,}, manifest {row['points']:,}"
    except Exception as e:
        status,detail="failed",str(e)
    return row["tile"],status,path.stat().st_size if path.exists() else 0,points,detail

def fetch(manifest,output,tiles=None,workers=4,retries=5,wait=5,opener=urllib.request.urlopen):
    """Download every manifest row into output, skipping complete files. Appends to output/download-log.csv.

    USGS rockyweb limits each connection (about 140 KB/s measured 2026-09-28), not the total,
    so workers download that many tiles at once."""
    if not 1<=workers<=8: raise ValueError("workers must be 1 to 8")
    rows=read_manifest(manifest,tiles)
    out=Path(output);out.mkdir(parents=True,exist_ok=True);log=out/"download-log.csv";new=not log.exists();statuses=[]
    with open(log,"a",newline="",encoding="utf-8") as f, ThreadPoolExecutor(workers) as pool:
        w=csv.writer(f)
        if new: w.writerow(["tile","status","bytes","points","detail","finished"])
        jobs=[pool.submit(_one,row,out,retries,wait,opener) for row in rows]
        for i,job in enumerate(as_completed(jobs),1):
            tile,status,size,points,detail=job.result()
            w.writerow([tile,status,size,"" if points is None else points,detail,
                        datetime.datetime.now().isoformat(timespec="seconds")]);f.flush()
            print(f"[{i}/{len(rows)}] {tile}: {status}{' - '+detail if detail else ''}",flush=True)
            statuses.append(status)
    return {"tiles":len(rows),"ok":statuses.count("ok"),"failed":len(rows)-statuses.count("ok"),"log":str(log)}
