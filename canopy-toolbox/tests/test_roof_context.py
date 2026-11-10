import unittest
from canopy import roof_context as rc
from canopy import building_rules as br, validation_metrics as vm


class Context(unittest.TestCase):
    def test_common_thresholds_and_compatibility_names(self):
        for height,canonical,flag in ((5.5,'ROOF_LEVEL','ROOF_EDGE'),(7.,'ROOF_MID','NEAR_ROOF'),
                                      (7.01,'ABOVE_ROOF','OVERHANG')):
            self.assertEqual(rc.context(.5,height,5.)[0],canonical)
            self.assertEqual(vm.treetop_context(.5,height,5.),canonical)
            self.assertEqual(br.candidate_flag(height,5.,False,None,br.parameters())[0],flag)

    def test_unknown_height_is_never_a_known_roof_category(self):
        self.assertEqual(rc.context(.5,5.,None),('UNKNOWN',None))
        self.assertEqual(rc.context(.5,float('nan'),5.),('UNKNOWN',None))
        self.assertEqual(rc.context(1.01,5.,5.),('AWAY',None))
        self.assertEqual(br.candidate_flag(5.,float('nan'),False,None,br.parameters())[0],'UNKNOWN')
