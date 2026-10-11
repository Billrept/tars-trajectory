import pytest
from tars_contracts.requests import JobSubmission, normalize_submission

def test_equivalent_body_names_and_defaults_have_one_fingerprint():
    a=normalize_submission(JobSubmission(kind='optimization_single',payload={'origin':'Earth','target':'mars','dep_start':'2026-06-01','dep_end':'2026-08-01'}))
    b=normalize_submission(JobSubmission(kind='optimization_single',payload={'origin':'399','target':'499','dep_start':'2026-06-01','dep_end':'2026-08-01','tof_min_days':60,'tof_max_days':400,'population_size':30,'max_iterations':200,'mode':'pareto'}))
    assert a==b

def test_unknown_body_and_excessive_work_are_rejected():
    with pytest.raises(ValueError):
        normalize_submission(JobSubmission(kind='optimization_single',payload={'origin':'unknown','target':'mars','dep_start':'2026-06-01','dep_end':'2026-08-01'}))
    with pytest.raises(ValueError):
        normalize_submission(JobSubmission(kind='optimization_single',payload={'origin':'earth','target':'mars','dep_start':'2026-06-01','dep_end':'2026-08-01','max_iterations':501}))
