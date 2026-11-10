import unittest
from canopy import parcel_ownership as po


class Ownership(unittest.TestCase):
    def test_government_aliases_and_public_school_and_district(self):
        for owner in ['Salt Lake County', 'MILLCREEK CITY', 'SALT LAKE CITY CORP',
                      'BOARD OF EDUCATION OF GRANITE SCHOOL DIST.', 'UTAH TRANSIT AUTHORITY',
                      'UTAH DEPARTMENT OF TRANSPORTATION', 'MT OLYMPUS IMPROVEMENT DISTRICT']:
            self.assertEqual(po.classify(owner)[0], 'PUBLIC_GOVERNMENT')

    def test_city_and_state_words_do_not_make_private_owners_public(self):
        for owner in ['MILLCREEK PROPERTIES LLC', 'MOUNTAIN STATES BUSINESS PARK ASSOCIATES LLC',
                      'UTAH POWER & LIGHT COMPANY', 'WESTERN GOVERNORS UNIVERSITY',
                      'CHURCH OF JESUS CHRIST OF LATTER-DAY SAINTS', 'COUNTY ROAD PROPERTY LLC']:
            self.assertEqual(po.classify(owner)[0], 'PRIVATE')

    def test_unknown_and_mixed_owners_are_retained(self):
        for owner in [None, '', ' ', 'SALT LAKE COUNTY; PRIVATE OWNER (TC)',
                      'LAKE COUNTY (TITLE BY W.D.)', 'SALT LAKE CITY PROPERTY MANAGEMENT']:
            self.assertEqual(po.classify(owner)[0], 'UNKNOWN_OWNER')

    def test_duplicate_parcels_count_once_and_conflicting_ownership_is_not_guessed(self):
        self.assertEqual(po.resolve(['PRIVATE', 'PRIVATE']), 'PRIVATE')
        self.assertEqual(po.resolve(['PUBLIC_GOVERNMENT', 'PRIVATE']), 'OWNERSHIP_CONFLICT')
        self.assertEqual(po.resolve([]), 'NO_PARCEL')


if __name__ == '__main__':
    unittest.main()
