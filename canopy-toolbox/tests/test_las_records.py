"""Binary layout, malformed input and opaque-byte regression checks; no ArcPy."""
from pathlib import Path
import struct
import tempfile
import unittest
import numpy as np
from canopy import las_records as las
from tests.las_fixture import write_las


class Records(unittest.TestCase):
    def test_legacy_flags_and_extra_bytes_survive_class_edit(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'points.las'; write_las(path)
            raw=bytearray(path.read_bytes()); raw[227+15]=5|64
            path.write_bytes(raw)
            points,scale,offset,modern,info=las.records(path,'r+')
            self.assertFalse(modern)
            self.assertEqual(las.decode(points[:1],scale,offset,modern)[3].tolist(),[5])
            points['classification'][0]=(points['classification'][0]&224)|6
            points.flush(); del points
            changed=[i for i,(a,b) in enumerate(zip(raw,path.read_bytes())) if a!=b]
            self.assertEqual(changed,[242])
            self.assertEqual(path.read_bytes()[242],70)

    def test_layouts_and_empty_files(self):
        for fmt,size in enumerate((20,28,26,34,57,63,30,36,38,59,67)):
            with self.subTest(fmt=fmt),tempfile.TemporaryDirectory() as folder:
                path=Path(folder)/'empty.las'; write_las(path)
                head=bytearray(path.read_bytes()[:227]); head.extend(bytes(148))
                head[24:26]=bytes((1,4)); head[104]=fmt
                struct.pack_into('<HII',head,94,375,375,0)
                struct.pack_into('<HI',head,105,size,0)
                path.write_bytes(head)
                points,*_=las.records(path)
                self.assertEqual(len(points),0)
                self.assertEqual(points.dtype.itemsize,size)

    def test_rejects_short_header_truncated_records_and_invalid_layout(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'bad.las'; write_las(path); original=path.read_bytes()
            for data in (original[:100],original[:-1]):
                path.write_bytes(data)
                with self.assertRaises(ValueError): las.records(path)
            for offset,value,encoding in ((104,63,'B'),(105,19,'H'),(96,100,'I'),(131,float('nan'),'d')):
                data=bytearray(original); struct.pack_into('<'+encoding,data,offset,value)
                path.write_bytes(data)
                with self.assertRaises(ValueError): las.records(path)

    def test_modern_extra_bytes_and_flags(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'modern.las'; write_las(path)
            head=bytearray(path.read_bytes()[:227]); head.extend(bytes(148)); head[25]=4; head[104]=6
            struct.pack_into('<HII',head,94,375,375,0); struct.pack_into('<HI',head,105,34,0)
            struct.pack_into('<Q',head,247,1)
            record=bytearray(34); record[14]=0x21; record[15]=2; record[16]=5; record[30:]=b'abcd'
            path.write_bytes(head+record); before=path.read_bytes()
            points,scale,offset,modern,_=las.records(path,'r+')
            self.assertTrue(modern)
            self.assertTrue(las.clean_flags(points['flags'],modern)[0])
            self.assertEqual(las.return_masks(points['returns'],modern)[1].tolist(),[False])
            points['classification'][0]=6; points.flush(); del points
            after=path.read_bytes()
            self.assertEqual([i for i,(a,b) in enumerate(zip(before,after)) if a!=b],[391])
            self.assertEqual(after[-4:],b'abcd')
