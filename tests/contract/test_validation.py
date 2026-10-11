import pytest
from pydantic import ValidationError
from api.routes_http import LambertRequest, MultiLegRequest, MultiLegOptimizeRequest, OptimizeRequest, PorkchopQuery, OrbitElementsRequest

@pytest.mark.parametrize('value',[float('nan'),float('inf')])
def test_nonfinite_transfer_time_is_rejected(value):
    with pytest.raises(ValidationError):
        LambertRequest(origin='earth',target='mars',departure_date='2028-01-01',tof_days=value)

@pytest.mark.parametrize('tofs',[[-1.],[0.],[float('nan')],[100.,200.]])
def test_multileg_requires_one_positive_tof_per_leg(tofs):
    with pytest.raises(ValidationError):
        MultiLegRequest(body_sequence=['earth','mars'],departure_date='2028-01-01',leg_tof_days=tofs)

def test_negative_multileg_bounds_and_c3_are_rejected():
    with pytest.raises(ValidationError):
        MultiLegOptimizeRequest(body_sequence=['earth','mars'],dep_start='2028-01-01',dep_end='2029-01-01',leg_tof_bounds=[[-2,100]],max_c3=-1)

@pytest.mark.parametrize('model',[OptimizeRequest,PorkchopQuery])
def test_reversed_search_windows_are_rejected_by_contract(model):
    with pytest.raises(ValidationError):
        model(origin='earth',target='mars',dep_start='2029-01-01',dep_end='2028-01-01')

def test_orbit_elements_reject_inconsistent_conic_signs():
    with pytest.raises(ValidationError):
        OrbitElementsRequest(a_km=1000,e=1.4,i_deg=0,raan_deg=0,arg_p_deg=0)
