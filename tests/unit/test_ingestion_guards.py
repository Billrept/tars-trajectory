from types import SimpleNamespace
import numpy as np
import pytest
from astropy.time import Time
from tars_contracts.horizons import _parse_horizons_response, validate_epoch_grid
from tars_core.planner import engine

TEXT='$$SOE\n2461041.5, A.D. 2026-Jan-01, 1, 2, 3, 4, 5, 6,\n$$EOE'
def test_ut_vectors_are_converted_to_tdb():
    data=_parse_horizons_response(TEXT,time_scale='utc')
    assert data['epochs'][0]==pytest.approx(Time(2461041.5,format='jd',scale='utc').tdb.jd,abs=1e-10)
def test_malformed_records_are_rejected():
    with pytest.raises(ValueError):_parse_horizons_response(TEXT.replace('1, 2, 3, 4, 5, 6','1, 2'))
def test_partial_epoch_grid_is_rejected():
    epochs=Time(np.arange(2461041.5,2461046.5),format='jd',scale='utc').tdb.jd
    validate_epoch_grid(epochs,'2026-01-01','2026-01-05',1)
    for bad in (epochs[:-1],np.delete(epochs,2)):
        with pytest.raises(ValueError):validate_epoch_grid(bad,'2026-01-01','2026-01-05',1)
def test_planner_rejects_failed_leg(monkeypatch):
    monkeypatch.setattr(engine,'compute_multileg_trajectory',lambda *a,**k:SimpleNamespace(total_dv_km_s=2,legs=[SimpleNamespace(converged=False)]))
    monkeypatch.setattr(engine,'multileg_result_to_dict',lambda r:{})
    assert engine._eval_multileg(['earth','mars'],2461041.5,[200],'bad',None) is None
