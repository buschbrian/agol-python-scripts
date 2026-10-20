"""Offline checks for the dated Nearmap WMS contract."""
import tempfile
import unittest
from pathlib import Path

from nearmap_historical_wms import layers_from_capabilities, read_service, request_bbox


class NearmapHistoricalWMS(unittest.TestCase):
    def test_only_dated_layers_are_listed_with_inherited_srs(self):
        xml=b'''<WMT_MS_Capabilities version="1.1.1"><Capability><Layer>
        <SRS>EPSG:4326 EPSG:3857</SRS><Title>Millcreek</Title>
        <Layer><Name>latest</Name><Title>Combined latest</Title></Layer>
        <Layer><Name>survey_2023_10</Name><Title>2023-10-21 Salt Lake City</Title></Layer>
        </Layer></Capability></WMT_MS_Capabilities>'''
        rows=layers_from_capabilities(xml)
        self.assertEqual(len(rows),1)
        self.assertEqual(rows[0]['dates'],['2023-10-21'])
        self.assertEqual(rows[0]['srs'],['EPSG:3857','EPSG:4326'])

    def test_requires_custom_service_and_keeps_pilot_extent(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'url.txt'
            path.write_text('https://api.nearmap.com/wms/v1/latest/apikey/fake')
            with self.assertRaises(ValueError): read_service(path)
            path.write_text('https://api.nearmap.com/wms/v1/places/example/apikey/fake')
            self.assertEqual(read_service(path),path.read_text())
        self.assertEqual(request_bbox('EPSG:6341'),(428100,4504100,428400,4504400))

if __name__=='__main__': unittest.main()
