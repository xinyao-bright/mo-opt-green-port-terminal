"""Numerical, constraint-regression and metric checks; run python test_model.py."""
from pathlib import Path
import ast
import unittest
import numpy as np
import kernel as K
from scheduling_objectives import objective_breakdown, preference_scores, validate_parameters
from run_experiments import initial_population, solve
from plot_results import hypervolume, igd


class ModelTests(unittest.TestCase):
    def setUp(self):
        K.PortConfig.OBJECTIVE_PARAMETERS=validate_parameters()
        self.ships=[dict(id=1,name='A',eta=0,workload=96,len=400,auv1=.2,auv2=100,auv3=.5)]
    def test_dimensional_components(self):
        o,rows,totals=objective_breakdown(self.ships,[2],[3],[2],K.PortConfig)
        self.assertAlmostEqual(totals['waitingCarbon'],63)
        self.assertAlmostEqual(totals['serviceCarbon'],31.5)
        self.assertAlmostEqual(totals['electricityCarbon'],530.6)
        self.assertAlmostEqual(totals['cost'],192+6+800+20)
        self.assertTrue(np.allclose(o,[625.1,3,1018]))
    def test_crane_energy_invariant(self):
        one=objective_breakdown(self.ships,[0],[2],[1],K.PortConfig)[2]
        two=objective_breakdown(self.ships,[0],[1],[2],K.PortConfig)[2]
        self.assertEqual(one['qcEnergyKwh'],two['qcEnergyKwh'])
        self.assertGreater(one['serviceCarbon'],two['serviceCarbon'])
        self.assertLess(one['coordinationCost'],two['coordinationCost'])
    def test_weights_correct_direction(self):
        o=np.array([[0,10,5],[10,0,5]])
        self.assertEqual(np.argmin(preference_scores(o,[.9,.1,0])[0]),0)
        self.assertEqual(np.argmin(preference_scores(o,[.1,.9,0])[0]),1)
        self.assertTrue(np.isfinite(preference_scores([[1,2,3]],[0,0,0])[0]).all())
    def test_reject_invalid_accounting(self):
        for v in [float('nan'),float('inf'),-1]:
            with self.assertRaises(ValueError):validate_parameters({'gridEmissionFactor':v})
    def test_constraints_unchanged(self):
        before=ast.parse((Path(__file__).parent/'baseline/app_before_objective_v2.py').read_text(encoding='utf-8'))
        after=ast.parse((Path(__file__).parent/'kernel.py').read_text(encoding='utf-8'))
        for name in ['decode_solution','calculate_penalty']:
            get=lambda tree:ast.dump(next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name==name),include_attributes=False)
            self.assertEqual(get(before),get(after))
    def test_static_crossing_even_without_time_overlap(self):
        p=K.calculate_penalty(2,[1,2],[0,10],[1,11],[5,1],[1,1],15)
        self.assertEqual(p,200000)
    def test_endpoint_rule_is_strict_greater(self):
        self.assertEqual(K.calculate_penalty(2,[1,2],[0,10],[1,11],[1,3],[3,1],15),0)
        self.assertGreater(K.calculate_penalty(2,[1,2],[0,0],[1,1],[1,3],[3,1],15),0)
    def test_repair_reports_redecoded_penalty(self):
        ships=self.ships*9;rng=np.random.default_rng(7)
        p=initial_population(ships,8,rng,False)
        for x in p:
            x[9:18]+=80
            r,pen=K.repair_qc_conflict(x,ships)
            self.assertEqual(pen,K.calculate_objectives(r,ships)[1])
    def test_anchor_feasibility_and_no_length_constraint(self):
        ships=self.ships*30
        for p in initial_population(ships,2,np.random.default_rng(4)):
            self.assertEqual(K.calculate_objectives(p,ships)[1],0)
        # ship length=400>350: intentionally no length restriction in the real backend.
    def test_physical_values_do_not_include_penalty(self):
        ships=self.ships*2;p=np.array([0,1,0,0,1,1,5,1],float)
        o,pen=K.calculate_objectives(p,ships)
        self.assertGreater(pen,0);self.assertLess(o[1],100)
    def test_hypervolume_exact(self):
        self.assertAlmostEqual(hypervolume([[1,1,1]],[2,2,2]),1)
        self.assertAlmostEqual(hypervolume([[0,1,1],[1,0,1]],[2,2,2]),3)
        self.assertEqual(hypervolume([], [2,2,2]),0)
        self.assertEqual(igd(np.array([[1,2,3]]),np.array([[1,2,3]])),0)
    def test_budget_accounting(self):
        for m in ['NSGA2-Repair','NSGA2-NoRepair','NSGA2-NoAnchor','NSGA2-None','WeightedGA','RandomSearch']:
            r=solve(self.ships*3,m,4,40,6,K.calculate_objectives)
            self.assertEqual(r['evaluations'],40)
            self.assertGreaterEqual(r['repairCalls'],0)


if __name__=='__main__':unittest.main(verbosity=2)
