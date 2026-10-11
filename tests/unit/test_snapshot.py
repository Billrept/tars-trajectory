import numpy as np
import pytest
from tars_core.ephemeris import EphemerisSnapshot

def test_snapshot_rejects_nonfinite_unsorted_or_misshapen_data():
    for epochs in [np.array([1.,2.,float('nan'),4.]),np.array([1.,3.,2.,4.])]:
        with pytest.raises(ValueError): EphemerisSnapshot('fixture',{399:{'epochs':epochs,'positions':np.zeros((4,3)),'velocities':np.zeros((4,3))}})

def test_snapshot_validates_every_batch_epoch_and_keeps_dataset_identity():
    snapshot=EphemerisSnapshot('fixture',{399:{'epochs':np.arange(4.),'positions':np.zeros((4,3)),'velocities':np.zeros((4,3))}})
    assert snapshot.dataset_id=='fixture'
    with pytest.raises(ValueError): snapshot.get_positions_batch(399,np.array([1.,4.,2.]))
    with pytest.raises(ValueError): snapshot.get_state(399,float('nan'))
