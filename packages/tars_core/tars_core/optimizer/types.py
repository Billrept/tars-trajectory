from __future__ import annotations
from dataclasses import dataclass,field

@dataclass
class OptimizationProgress:
    """Yielded by the optimizer at each iteration improvement."""
    iteration: int
    max_iterations: int
    best_dv_total: float
    best_departure_jd: float
    best_tof_days: float
    best_dv_departure: float
    best_dv_arrival: float
    converged: bool
    population_best_dvs: list[float] = field(default_factory=list)  # top-3
    population_positions: list[list[float]] = field(default_factory=list)  # [[dep_jd, tof], ...]
    pareto_front: list[dict] = field(default_factory=list)  # [{dv, tof, dep_jd, ...}]
    mode: str = "min_dv"
    insight: str = ""
    orbit_elements: dict | None = None

@dataclass
class OptimizationRequest:
    """Input parameters for an optimization run."""
    origin_id: int
    target_id: int
    dep_start_jd: float
    dep_end_jd: float
    tof_min_days: float
    tof_max_days: float
    population_size: int = 30
    max_iterations: int = 200
    prograde: bool = True
    mode: str = "pareto"  # "min_dv", "min_tof", "pareto"
    seed: int | None = None

class ParetoArchive:
    """Maintains a set of non-dominated solutions (Pareto front)."""

    def __init__(self, max_size: int = 50):
        self.solutions: list[dict] = []
        self.max_size = max_size

    def add(self, sol: dict) -> bool:
        dv = sol.get("dv_total", float("inf"))
        tof = sol.get("tof_days", sol.get("total_tof_days", 0))
        if dv == float("inf") or tof <= 0:
            return False

        to_remove = []
        for existing in self.solutions:
            e_dv = existing.get("dv_total", float("inf"))
            e_tof = existing.get("tof_days", existing.get("total_tof_days", 0))
            if e_dv <= dv and e_tof <= tof and (e_dv < dv or e_tof < tof):
                return False
            if dv <= e_dv and tof <= e_tof and (dv < e_dv or tof < e_tof):
                to_remove.append(existing)

        for r in to_remove:
            self.solutions.remove(r)

        self.solutions.append(sol)
        self.solutions.sort(key=lambda x: x.get("dv_total", float("inf")))

        if len(self.solutions) > self.max_size:
            self.solutions = self.solutions[::2]
        return True

    def to_list(self) -> list[dict]:
        return [
            {
                "dv_total": s.get("dv_total"),
                "tof_days": s.get("tof_days", s.get("total_tof_days")),
                "departure_jd": s.get("departure_jd"),
            }
            for s in self.solutions
        ]

@dataclass
class MultiLegOptimizationProgress:
    """Yielded by the multi-leg optimizer at each iteration improvement."""
    iteration: int
    max_iterations: int
    best_dv_total: float
    best_departure_jd: float
    best_leg_tof_days: list[float]
    best_total_tof_days: float
    best_dv_departure: float
    best_dv_arrival: float
    best_dv_flyby: float
    converged: bool
    body_sequence: list[str]
    population_best_dvs: list[float] = field(default_factory=list)
    population_positions: list[list[float]] = field(default_factory=list)
    pareto_front: list[dict] = field(default_factory=list)
    mode: str = "min_dv"
    insight: str = ""
    orbit_elements_list: list[dict] | None = None

@dataclass
class MultiLegOptimizationRequest:
    """Input parameters for a multi-leg optimization run.

    The search space is (N+1)-dimensional:
        x[0] = departure Julian Date
        x[1..N] = TOF in days for each of the N legs
    """
    body_names: list[str]
    dep_start_jd: float
    dep_end_jd: float
    leg_tof_bounds: list[tuple[float, float]]
    population_size: int = 40
    max_iterations: int = 300
    max_c3: float | None = None
    mode: str = "pareto"  # "min_dv", "min_tof", "pareto"
    seed: int | None = None
