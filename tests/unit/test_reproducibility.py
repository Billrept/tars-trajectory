import numpy as np
import pytest
from optimizer.gmpa import OptimizationRequest, MultiLegOptimizationRequest
from optimizer.nsga2 import NSGA2Optimizer, MultiLegNSGA2Optimizer
from mechanics.lambert import compute_transfer_dv
from ephemeris.bodies import GM_SUN, AU_KM

class CircularReference:
    """Analytical test fixture, not JPL ephemeris."""
    def get_state(self, body_id, jd):
        radius = AU_KM if body_id == 399 else 1.524*AU_KM
        phase = .4 if body_id == 399 else 1.8
        n = np.sqrt(GM_SUN / radius**3)
        theta = phase + (jd-2461771.5)*86400*n
        return radius*np.array([np.cos(theta),np.sin(theta),0.]), radius*n*np.array([-np.sin(theta),np.cos(theta),0.])

def test_optimizer_seed_covers_selection_crossover_and_mutation():
    request = OptimizationRequest(399,499,2461771.5,2461871.5,120,250,population_size=6,max_iterations=10,seed=42)
    a = list(NSGA2Optimizer(request,CircularReference()).run())[-1]
    b = list(NSGA2Optimizer(request,CircularReference()).run())[-1]
    assert a.population_positions == b.population_positions
    assert a.best_dv_total == b.best_dv_total

def test_active_multileg_optimizer_enforces_c3():
    request = MultiLegOptimizationRequest(['earth','mars'],2461771.5,2461871.5,[(120,250)],population_size=6,max_iterations=10,max_c3=0.)
    result = MultiLegNSGA2Optimizer(request,CircularReference())._evaluate_full(np.array([2461771.5,200.]))
    assert not np.isfinite(result['dv_total'])

def test_hyperbolic_transfer_has_no_apoapsis_marker():
    r1 = np.array([7000.,0.,0.])
    r2 = np.array([0.,14000.,0.])
    result = compute_transfer_dv(r1,np.zeros(3),r2,np.zeros(3),500.,398600.4418)
    assert result['converged']
    assert result['orbit_elements']['e'] > 1
    assert result['orbit_elements']['apoapsis_point_km'] is None
