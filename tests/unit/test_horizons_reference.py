from pathlib import Path
import numpy as np
import pytest
from scipy.integrate import solve_ivp
from tars_core.ephemeris import EphemerisSnapshot
from tars_core.bodies import GM_SUN
from tars_core.mechanics.lambert import solve_lambert

@pytest.mark.parametrize('tof_days',[120.,200.,260.])
def test_jpl_earth_mars_lambert_boundary_matches_independent_dynamics(tof_days):
    arrays={}
    for name,bid in [('earth',399),('mars',499)]:
        with np.load(Path('tests/fixtures')/f'{name}_horizons.npz',allow_pickle=False) as data:arrays[bid]=dict(data)
    snapshot=EphemerisSnapshot('JPL reference fixture',arrays)
    jd=2461300.5;r1,_=snapshot.get_state(399,jd);r2,_=snapshot.get_state(499,jd+tof_days)
    result=solve_lambert(r1,r2,tof_days*86400,GM_SUN)
    assert result['converged']
    def dynamics(t,y):return np.concatenate((y[3:],-GM_SUN*y[:3]/np.linalg.norm(y[:3])**3))
    reference=solve_ivp(dynamics,(0,tof_days*86400),np.concatenate((r1,result['v1'])),method='DOP853',rtol=1e-11,atol=1e-8)
    assert reference.success
    assert np.linalg.norm(reference.y[:3,-1]-r2)<1.0
