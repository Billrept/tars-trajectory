"""Validated, pinned numerical snapshots; no network or service configuration."""
import math
from typing import Protocol
import numpy as np
from scipy.interpolate import CubicSpline

class EphemerisRangeError(ValueError):
    def __init__(self, naif_id, epoch_jd, epoch_start, epoch_end):
        self.naif_id, self.epoch_jd = naif_id, epoch_jd
        self.epoch_start, self.epoch_end = epoch_start, epoch_end
        super().__init__(f'Epoch {epoch_jd} outside [{epoch_start}, {epoch_end}] for {naif_id}')

class StateProvider(Protocol):
    def get_state(self, naif_id: int, epoch_jd: float) -> tuple[np.ndarray, np.ndarray]: ...

EphemerisCache = StateProvider

class EphemerisSnapshot:
    def __init__(self, dataset_id: str, bodies: dict[int, dict]):
        self.dataset_id = dataset_id
        self._data, self._splines = {}, {}
        for body_id, data in bodies.items():
            epochs = np.asarray(data['epochs'], dtype=np.float64)
            pos = np.asarray(data['positions'], dtype=np.float64)
            vel = np.asarray(data['velocities'], dtype=np.float64)
            if epochs.ndim != 1 or not 4 <= len(epochs) <= 131072 or pos.shape != (len(epochs),3) or vel.shape != pos.shape:
                raise ValueError('Invalid ephemeris array shapes or sample count')
            if not all(np.isfinite(x).all() for x in (epochs,pos,vel)) or not np.all(np.diff(epochs)>0):
                raise ValueError('Ephemeris arrays must be finite with ascending epochs')
            for x in (epochs,pos,vel): x.setflags(write=False)
            self._data[int(body_id)] = {'epochs':epochs,'positions':pos,'velocities':vel}
            self._splines[int(body_id)] = (CubicSpline(epochs,pos,extrapolate=False),CubicSpline(epochs,vel,extrapolate=False))
        if not self._data: raise ValueError('Empty dataset')

    def __contains__(self, body_id): return body_id in self._data
    def __len__(self): return len(self._data)
    def available_bodies(self): return list(self._data)
    def get_epoch_range(self, body_id):
        epochs=self._data[body_id]['epochs'];return float(epochs[0]),float(epochs[-1])
    def validate_epoch(self, body_id, jd):
        start,end=self.get_epoch_range(body_id)
        if not math.isfinite(jd) or jd < start or jd > end:
            raise EphemerisRangeError(body_id,jd,start,end)
    def validate_epoch_range(self, body_id, start, end):
        if start > end: raise ValueError('Reversed epoch range')
        self.validate_epoch(body_id,start);self.validate_epoch(body_id,end)
    def get_state(self, body_id, jd):
        self.validate_epoch(body_id,jd)
        pos,vel=self._splines[body_id];return pos(jd),vel(jd)
    def get_position(self, body_id, jd): return self.get_state(body_id,jd)[0]
    def get_velocity(self, body_id, jd): return self.get_state(body_id,jd)[1]
    def get_positions_batch(self, body_id, epochs):
        epochs=np.asarray(epochs)
        if len(epochs): self.validate_epoch_range(body_id,float(epochs.min()),float(epochs.max()))
        return self._splines[body_id][0](epochs)
