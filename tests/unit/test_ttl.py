import pytest
from tars_contracts.ttl import TTLValue

class Clock:
    def __init__(self):self.now=0.0
    def __call__(self):return self.now

def counting(values):
    calls=[]
    def fetch():
        calls.append(1);value=values[len(calls)-1]
        if isinstance(value,Exception):raise value
        return value
    return fetch,calls

def test_reuses_value_until_ttl_expires_then_refetches():
    clock=Clock();fetch,calls=counting(['a','b']);value=TTLValue(fetch,60,clock)
    assert value.get()=='a' and value.get()=='a' and len(calls)==1
    clock.now=59.9;assert value.get()=='a' and len(calls)==1
    clock.now=60;assert value.get()=='b' and len(calls)==2

def test_zero_ttl_always_refetches():
    fetch,calls=counting(['a','b','c']);value=TTLValue(fetch,0,Clock())
    assert [value.get(),value.get(),value.get()]==['a','b','c']

def test_failed_fetch_caches_nothing_and_next_call_retries():
    clock=Clock();fetch,calls=counting([RuntimeError('down'),'ok']);value=TTLValue(fetch,60,clock)
    with pytest.raises(RuntimeError):value.get()
    assert value.get()=='ok' and len(calls)==2
