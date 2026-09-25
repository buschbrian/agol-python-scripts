"""Tiny LAS 1.2 fixture with known classes, roofs, and a bare-ground gap."""
import struct
from pathlib import Path

def write_las(path, vegetation=True, wkt=None, origin=(500000,4500000)):
    points=[]
    for y in range(11):
        for x in range(11):
            points.append((x,y,100,2))
            if vegetation and (x<=2 or x>=8):
                points.append((x,y,110,5))
    points.extend([(5,5,115,1),(5,6,118,6),(1,1,130,7),(2,2,135,18)])
    ox,oy=origin
    vlr=b""
    if wkt:
        content=wkt.encode("utf-8")+b"\0"
        vlr=struct.pack("<H16sHH32s",0,b"LASF_Projection",2112,len(content),
                        b"Coordinate system WKT")+content
    header=bytearray(227);header[:4]=b"LASF";header[24:26]=bytes([1,2])
    header[26:58]=b"Synthetic regression".ljust(32,b"\0")
    header[58:90]=b"Canopy toolbox tests".ljust(32,b"\0")
    struct.pack_into("<HHHII",header,90,260,2026,227,227+len(vlr),1 if vlr else 0)
    struct.pack_into("<BHI",header,104,0,20,len(points))
    struct.pack_into("<5I",header,111,len(points),0,0,0,0)
    struct.pack_into("<3d",header,131,.01,.01,.01)
    struct.pack_into("<3d",header,155,ox,oy,0)
    struct.pack_into("<6d",header,179,ox+10,ox,oy+10,oy,135,100)
    with Path(path).open("wb") as handle:
        handle.write(header)
        handle.write(vlr)
        for x,y,z,code in points:
            handle.write(struct.pack("<iiiHBBbBH",x*100,y*100,z*100,10,9,code,0,0,0))
