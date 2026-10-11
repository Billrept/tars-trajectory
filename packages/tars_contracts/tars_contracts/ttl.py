"""Single cached value with a time-to-live.

Datasets are immutable and only the active pointer moves (rarely), so callers can
reuse the active manifest for a short while instead of fetching it on every request.
A failed fetch raises and caches nothing; the next call retries.
"""
import time

class TTLValue:
    def __init__(self,fetch,seconds,clock=time.monotonic):
        self.fetch=fetch;self.seconds=seconds;self.clock=clock
        self.value=None;self.expires=float('-inf')
    def get(self):
        now=self.clock()
        if now>=self.expires:
            self.value=self.fetch();self.expires=now+self.seconds
        return self.value
