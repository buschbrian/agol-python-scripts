import unittest
from canopy import validation_metrics as vm


class AnalyticIntervals(unittest.TestCase):
    def test_total_variance_includes_strata_and_finite_population_correction(self):
        d=vm.Design(['a','a','b','b'],{'a':10,'b':20},{'y':[0,1,0,2]})
        r=vm.estimate({'s':d},lambda t:{'total':t['s']['y']},replicates=20)['total']
        self.assertEqual(r['interval_status'],'ANALYTIC_TAYLOR_T')
        self.assertAlmostEqual(r['variance'],380.,places=4)
        self.assertEqual(r['estimate'],25.)
        self.assertIn('bootstrap',r)

    def test_ratio_accounts_for_covariance_and_census_has_zero_variance(self):
        d=vm.Design(['a']*4,{'a':40},{'x':[1,2,3,4],'y':[2,4,6,8]})
        r=vm.estimate({'s':d},lambda t:{'ratio':t['s']['y']/t['s']['x']},replicates=20)['ratio']
        self.assertAlmostEqual(r['variance'],0.,places=12)
        self.assertEqual(r['interval_status'],'DEGENERATE_LINEARIZATION')
        census=vm.Design(['a','a'],{'a':2},{'y':[0,1]})
        r=vm.estimate({'s':census},lambda t:{'total':t['s']['y']},replicates=20)['total']
        self.assertEqual((r['low'],r['high']),(1.,1.))

    def test_singleton_and_homogeneous_non_census_are_suppressed(self):
        for values in ([1],[1,1]):
            d=vm.Design(['a']*len(values),{'a':40},{'y':values})
            r=vm.estimate({'s':d},lambda t:{'total':t['s']['y']},replicates=20)['total']
            self.assertIsNone(r['low'])
            self.assertIsNone(r['high'])

    def test_nonconstant_ratio_uses_joint_unit_covariance(self):
        d=vm.Design(['a']*4,{'a':40},{'x':[1,2,3,4],'y':[1,0,1,0]})
        r=vm.estimate({'s':d},lambda t:{'ratio':t['s']['y']/t['s']['x']},replicates=20)['ratio']
        self.assertAlmostEqual(r['estimate'],.2)
        self.assertAlmostEqual(r['variance'],.0192,places=7)
        self.assertAlmostEqual(r['degrees_freedom'],3.)
