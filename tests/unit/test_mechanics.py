import math
import numpy as np
import pytest
from scipy.integrate import solve_ivp
from mechanics.kepler import elements_to_state, propagate_kepler, state_to_elements
from mechanics.lambert import solve_lambert, _stumpff_dc2, _stumpff_dc3
from mechanics.transforms import iso_to_jd, jd_to_iso
from mechanics.multileg import _compute_flyby
from ephemeris.bodies import EARTH

MU = 398600.4418

def test_circular_equatorial_phase_is_preserved():
    r = np.array([0., 7000., 0.])
    v = np.array([-math.sqrt(MU / 7000), 0., 0.])
    for dt in [0., 1200.]:
        actual, _ = propagate_kepler(r, v, dt, MU)
        angle = math.pi / 2 + math.sqrt(MU / 7000**3) * dt
        np.testing.assert_allclose(actual, [7000*math.cos(angle), 7000*math.sin(angle), 0.], atol=1e-6)

@pytest.mark.parametrize('a,e', [(12000., .3), (-12000., 1.4)])
def test_elements_roundtrip_and_propagation_match_independent_integrator(a, e):
    r, v = elements_to_state(a, e, .4, .7, 1.2, .3, MU)
    recovered = state_to_elements(r, v, MU)
    rr, vv = elements_to_state(*recovered, MU)
    np.testing.assert_allclose(rr, r, atol=1e-6)
    np.testing.assert_allclose(vv, v, atol=1e-9)
    def rhs(t, y):
        return np.concatenate((y[3:], -MU*y[:3]/np.linalg.norm(y[:3])**3))
    reference = solve_ivp(rhs, (0, 1800), np.concatenate((r,v)), method='DOP853', rtol=1e-11, atol=1e-11).y[:,-1]
    actual_r, actual_v = propagate_kepler(r, v, 1800., MU)
    np.testing.assert_allclose(actual_r, reference[:3], atol=1e-4)
    np.testing.assert_allclose(actual_v, reference[3:], atol=1e-7)

def test_lambert_reaches_known_circular_boundary():
    r1 = np.array([7000., 0., 0.])
    angle = 1.2
    r2 = 7000*np.array([math.cos(angle), math.sin(angle), 0.])
    tof = angle / math.sqrt(MU / 7000**3)
    result = solve_lambert(r1, r2, tof, MU)
    assert result['converged']
    np.testing.assert_allclose(result['v1'], [0., math.sqrt(MU/7000), 0.], atol=1e-6)
    reached, _ = propagate_kepler(r1, result['v1'], tof, MU)
    assert np.linalg.norm(reached-r2) < 1e-3

def test_collinear_lambert_is_explicitly_infeasible():
    r = np.array([7000.,0.,0.])
    assert not solve_lambert(r, r, 1000., MU)['converged']

def test_stumpff_series_derivatives():
    assert _stumpff_dc2(0., .5, 1/6) == pytest.approx(-1/24)
    assert _stumpff_dc3(0., .5, 1/6) == pytest.approx(-1/120)

def test_utc_offsets_map_to_same_tdb_epoch_and_roundtrip():
    a = iso_to_jd('2028-01-01T00:00:00Z')
    b = iso_to_jd('2028-01-01T07:00:00+07:00')
    assert a == pytest.approx(b, abs=1e-9)
    assert a > 2461771.5  # TDB is ahead of UTC, not merely calendar JD.
    assert jd_to_iso(a).startswith('2028-01-01T00:00:00')

def test_speed_mismatched_flyby_is_not_free_unpowered_assist():
    flyby = _compute_flyby(EARTH, 2461771.5, np.array([3.,0.,0.]), np.array([4.,1.,0.]), np.zeros(3))
    assert not flyby.feasible_unpowered
    assert flyby.powered_dv_km_s > 0

def test_radial_degenerate_orbit_is_rejected():
    with pytest.raises(ValueError):
        state_to_elements(np.array([7000.,0.,0.]), np.array([1.,0.,0.]), MU)
