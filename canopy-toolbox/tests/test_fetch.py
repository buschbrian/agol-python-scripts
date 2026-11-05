"""Offline tests for canopy.fetch against a local server that honours Range."""
import csv
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import struct
import tempfile
import threading
import unittest

from canopy import fetch

def las_header(points,version=(1,4)):
    head=bytearray(375);head[:4]=b"LASF";head[24],head[25]=version
    if version>=(1,4): head[247:255]=struct.pack("<Q",points)
    else: head[107:111]=struct.pack("<I",points)
    return bytes(head)

FILES={"/a.laz":las_header(1234)+b"x"*5000,"/b.laz":las_header(99)+b"y"*300}

class Handler(BaseHTTPRequestHandler):
    ranges=[];ignore_range=False
    def log_message(self,*args): pass
    def do_GET(self):
        body=FILES[self.path];rng=self.headers.get("Range")
        Handler.ranges.append(rng)
        if rng and not Handler.ignore_range:
            start=int(rng.split("=")[1].rstrip("-"));self.send_response(206);body=body[start:]
        else: self.send_response(200)
        self.send_header("Content-Length",str(len(body)));self.end_headers();self.wfile.write(body)

class Fetch(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server=ThreadingHTTPServer(("127.0.0.1",0),Handler)
        threading.Thread(target=cls.server.serve_forever,daemon=True).start()
        cls.base=f"http://127.0.0.1:{cls.server.server_port}"
    @classmethod
    def tearDownClass(cls): cls.server.shutdown()

    def setUp(self):
        Handler.ranges=[];Handler.ignore_range=False
        self.tmp=Path(tempfile.mkdtemp());self.out=self.tmp/"out"

    def manifest(self,rows):
        path=self.tmp/"m.csv"
        with open(path,"w",newline="",encoding="utf-8") as f:
            w=csv.writer(f);w.writerow(["tile","url","bytes","points"])
            for tile,name,points in rows: w.writerow([tile,f"{self.base}{name}",len(FILES[name]),points])
        return path

    def test_header_points_for_both_header_layouts(self):
        self.assertEqual(fetch.header_points(las_header(7)),7)
        self.assertEqual(fetch.header_points(las_header(8,(1,2))),8)
        with self.assertRaises(ValueError): fetch.header_points(b"PK"+bytes(373))

    def test_downloads_and_checks_points(self):
        result=fetch.fetch(self.manifest([("A","/a.laz",1234),("B","/b.laz",99)]),self.out)
        self.assertEqual((result["ok"],result["failed"]),(2,0))
        self.assertEqual((self.out/"a.laz").read_bytes(),FILES["/a.laz"])
        self.assertEqual(Handler.ranges,[None,None])

    def test_resumes_a_partial_file(self):
        self.out.mkdir();(self.out/"a.laz").write_bytes(FILES["/a.laz"][:1000])
        result=fetch.fetch(self.manifest([("A","/a.laz",1234)]),self.out)
        self.assertEqual(result["ok"],1);self.assertEqual(Handler.ranges,["bytes=1000-"])
        self.assertEqual((self.out/"a.laz").read_bytes(),FILES["/a.laz"])

    def test_restarts_when_the_server_ignores_range(self):
        Handler.ignore_range=True
        self.out.mkdir();(self.out/"a.laz").write_bytes(FILES["/a.laz"][:1000])
        self.assertEqual(fetch.fetch(self.manifest([("A","/a.laz",1234)]),self.out)["ok"],1)
        self.assertEqual((self.out/"a.laz").read_bytes(),FILES["/a.laz"])

    def test_skips_complete_and_replaces_oversized_files(self):
        self.out.mkdir();(self.out/"a.laz").write_bytes(FILES["/a.laz"]);(self.out/"b.laz").write_bytes(FILES["/b.laz"]+b"junk")
        result=fetch.fetch(self.manifest([("A","/a.laz",1234),("B","/b.laz",99)]),self.out)
        self.assertEqual(result["ok"],2);self.assertEqual(Handler.ranges,[None])
        self.assertEqual((self.out/"b.laz").read_bytes(),FILES["/b.laz"])

    def test_point_mismatch_and_log(self):
        result=fetch.fetch(self.manifest([("A","/a.laz",1)]),self.out)
        self.assertEqual(result["failed"],1)
        with open(self.out/"download-log.csv",newline="",encoding="utf-8") as f: rows=list(csv.DictReader(f))
        self.assertEqual((rows[0]["tile"],rows[0]["status"],rows[0]["points"]),("A","points-mismatch","1234"))

    def test_parallel_workers(self):
        result=fetch.fetch(self.manifest([("A","/a.laz",1234),("B","/b.laz",99)]),self.out,workers=2)
        self.assertEqual(result["ok"],2)
        self.assertEqual((self.out/"b.laz").read_bytes(),FILES["/b.laz"])
        with self.assertRaises(ValueError): fetch.fetch(self.manifest([("A","/a.laz",1234)]),self.out,workers=9)

    def test_duplicate_files_are_refused(self):
        with self.assertRaises(ValueError): fetch.read_manifest(self.manifest([("A","/a.laz",1234),("A2","/a.laz",1234)]))

    def test_unknown_tiles_are_refused(self):
        with self.assertRaises(ValueError): fetch.read_manifest(self.manifest([("A","/a.laz",1234)]),["Z"])

if __name__=="__main__":
    unittest.main()
