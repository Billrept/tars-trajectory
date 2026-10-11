from __future__ import annotations
import math
from datetime import datetime, timezone
from typing import Literal
from pydantic import BaseModel as PydanticModel, ConfigDict, Field, field_validator, model_validator
from tars_core.bodies import BODY_BY_ID, BODY_BY_NAME, GM_SUN

def _parse_date(value: str):
    date=datetime.fromisoformat(value.replace('Z','+00:00'))
    return date.replace(tzinfo=timezone.utc) if date.tzinfo is None else date.astimezone(timezone.utc)

def _validate_iso_date(value: str) -> str:
    return _parse_date(value).isoformat()

class BaseModel(PydanticModel):
    @field_validator('origin','target','body_sequence', check_fields=False)
    @classmethod
    def normalize_body(cls, value):
        def resolve(identifier):
            body=BODY_BY_ID.get(int(identifier)) if str(identifier).isdigit() else BODY_BY_NAME.get(str(identifier).lower().strip())
            if body is None: raise ValueError('Unknown body')
            return str(body.naif_id)
        return [resolve(v) for v in value] if isinstance(value,list) else resolve(value)

    model_config = ConfigDict(allow_inf_nan=False, extra='forbid')

    @model_validator(mode='after')
    def valid_bounds(self):
        start, end = getattr(self, 'dep_start', None), getattr(self, 'dep_end', None)
        if bool(start) != bool(end) or (start and _parse_date(start) >= _parse_date(end)):
            raise ValueError('Departure window requires an ordered start and end')
        minimum, maximum = getattr(self, 'tof_min_days', None), getattr(self, 'tof_max_days', None)
        if minimum is not None and minimum >= maximum:
            raise ValueError('Minimum TOF must be below maximum TOF')
        sequence = getattr(self, 'body_sequence', None)
        tofs = getattr(self, 'leg_tof_days', None)
        bounds = getattr(self, 'leg_tof_bounds', None)
        if tofs is not None and (len(tofs) != len(sequence)-1 or any(t <= 0 for t in tofs)):
            raise ValueError('Each leg requires one positive TOF')
        if bounds is not None and (len(bounds) != len(sequence)-1 or any(b[0] <= 0 for b in bounds)):
            raise ValueError('Each leg requires one positive TOF bound pair')
        if getattr(self, 'max_c3', None) is not None and self.max_c3 < 0:
            raise ValueError('Maximum C3 must be nonnegative')
        if hasattr(self, 'a_km') and (self.e < 0 or self.mu <= 0 or not math.isfinite(self.a_km * (1-self.e**2)) or self.a_km*(1-self.e**2) <= 0):
            raise ValueError('Unsupported or inconsistent conic elements')
        return self

class BodyOut(BaseModel):
    naif_id: int
    name: str
    gm: float
    radius: float
    color: str
    parent_id: int | None = None

class EphemerisQuery(BaseModel):
    start: str = Field(description="Start date ISO, e.g. 2026-01-01")
    end: str = Field(description="End date ISO, e.g. 2027-01-01")
    step_days: int = Field(default=10, ge=1, le=365)
    scene_units: bool = Field(default=True, description="Convert to scene units")

    @field_validator("start", "end")
    @classmethod
    def check_iso_date(cls, v: str) -> str:
        return _validate_iso_date(v)

class OptimizeRequest(BaseModel):
    seed: int | None = Field(default=None, ge=0, le=2**32-1)
    origin: str = Field(description="Origin body name or NAIF ID, e.g. 'earth' or '399'")
    target: str = Field(description="Target body name or NAIF ID, e.g. 'mars' or '499'")
    dep_start: str = Field(description="Departure window start, ISO date")
    dep_end: str = Field(description="Departure window end, ISO date")
    tof_min_days: float = Field(default=60, ge=1)
    tof_max_days: float = Field(default=400, ge=1)
    population_size: int = Field(default=30, ge=5, le=100)
    max_iterations: int = Field(default=200, ge=10, le=500)
    mode: str = Field(default="pareto", description="Optimization mode: 'min_dv', 'min_tof', or 'pareto'")

    @field_validator("dep_start", "dep_end")
    @classmethod
    def check_iso_date(cls, v: str) -> str:
        return _validate_iso_date(v)

    @field_validator("mode")
    @classmethod
    def check_mode(cls, v: str) -> str:
        if v not in ("min_dv", "min_tof", "pareto"):
            raise ValueError(f"mode must be 'min_dv', 'min_tof', or 'pareto', got '{v}'")
        return v

class LambertRequest(BaseModel):
    origin: str
    target: str
    departure_date: str
    tof_days: float = Field(ge=1)

    @field_validator("departure_date")
    @classmethod
    def check_iso_date(cls, v: str) -> str:
        return _validate_iso_date(v)

class PorkchopQuery(BaseModel):
    origin: str
    target: str
    dep_start: str
    dep_end: str
    tof_min_days: float = Field(default=60, ge=1)
    tof_max_days: float = Field(default=400, ge=1)
    dep_steps: int = Field(default=80, ge=10, le=100)
    tof_steps: int = Field(default=80, ge=10, le=100)
    binary: bool = Field(default=False, description="Return binary protobuf instead of JSON")

    @field_validator("dep_start", "dep_end")
    @classmethod
    def check_iso_date(cls, v: str) -> str:
        return _validate_iso_date(v)

class MultiLegRequest(BaseModel):
    body_sequence: list[str] = Field(
        description="Ordered list of body names, e.g. ['earth', 'venus', 'earth', 'jupiter']",
        min_length=2,
    )
    departure_date: str = Field(description="Departure date ISO, e.g. 2028-06-01")
    leg_tof_days: list[float] = Field(
        description="TOF in days for each leg (length = len(body_sequence) - 1)",
        min_length=1,
    )

    @field_validator("departure_date")
    @classmethod
    def check_iso_date(cls, v: str) -> str:
        return _validate_iso_date(v)

class MultiLegOptimizeRequest(BaseModel):
    body_sequence: list[str] = Field(
        description="Ordered list of body names, e.g. ['earth', 'venus', 'earth', 'jupiter']",
        min_length=2,
    )
    dep_start: str = Field(description="Departure window start, ISO date")
    dep_end: str = Field(description="Departure window end, ISO date")
    leg_tof_bounds: list[list[float]] = Field(
        description="TOF bounds [[min, max]] for each leg, in days",
        min_length=1,
    )
    population_size: int = Field(default=40, ge=5, le=100)
    max_iterations: int = Field(default=300, ge=10, le=500)
    seed: int | None = Field(default=None, ge=0, le=2**32-1)
    max_c3: float | None = Field(default=None, description="Max departure C3 (km^2/s^2)")
    mode: str = Field(default="pareto", description="Optimization mode: 'min_dv', 'min_tof', or 'pareto'")

    @field_validator("dep_start", "dep_end")
    @classmethod
    def check_iso_date(cls, v: str) -> str:
        return _validate_iso_date(v)

    @field_validator("leg_tof_bounds")
    @classmethod
    def check_tof_bounds(cls, v: list[list[float]]) -> list[list[float]]:
        for i, bounds in enumerate(v):
            if len(bounds) != 2:
                raise ValueError(f"leg_tof_bounds[{i}] must have exactly 2 elements [min, max], got {len(bounds)}")
            if bounds[0] >= bounds[1]:
                raise ValueError(f"leg_tof_bounds[{i}]: min ({bounds[0]}) must be < max ({bounds[1]})")
        return v

    @field_validator("mode")
    @classmethod
    def check_mode(cls, v: str) -> str:
        if v not in ("min_dv", "min_tof", "pareto"):
            raise ValueError(f"mode must be 'min_dv', 'min_tof', or 'pareto', got '{v}'")
        return v

class PlanRequest(BaseModel):
    origin: str
    target: str
    mode: str = Field(default="min_dv", description="'min_dv' or 'min_tof'")
    dep_start: str | None = None
    dep_end: str | None = None

    @field_validator("dep_start", "dep_end")
    @classmethod
    def check_iso_date(cls, v: str | None) -> str | None:
        if v:
            return _validate_iso_date(v)
        return v

class OrbitElementsRequest(BaseModel):
    a_km: float
    e: float
    i_deg: float
    raan_deg: float
    arg_p_deg: float
    mu: float = GM_SUN

class AssessRequest(BaseModel):
    origin: str
    target: str
    departure_date: str
    tof_days: float = Field(ge=1)

    @field_validator("departure_date")
    @classmethod
    def check_iso_date(cls, v: str) -> str:
        return _validate_iso_date(v)

class JobSubmission(PydanticModel):
    model_config = ConfigDict(extra='forbid')
    kind: Literal['plan','porkchop','optimization_single','optimization_multi']
    payload: dict

REQUEST_MODELS = {'plan':PlanRequest,'porkchop':PorkchopQuery,'optimization_single':OptimizeRequest,'optimization_multi':MultiLegOptimizeRequest}

def normalize_submission(submission: JobSubmission) -> dict:
    request=REQUEST_MODELS[submission.kind].model_validate(submission.payload)
    if hasattr(request,'body_sequence') and len(request.body_sequence)>6:
        raise ValueError('Maximum five legs')
    return {'kind':submission.kind,'payload':request.model_dump(mode='json')}
