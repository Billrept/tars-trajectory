# Tests

```bash
docker compose -p tars-test -f docker-compose.test.yml up -d   # Postgres :54329, Redis :63791/:63792, SeaweedFS S3 :9009
.venv/bin/python -m pytest -q                                  # whole suite
.venv/bin/python -m pytest tests/unit/test_mechanics.py -q     # one file
.venv/bin/python -m pytest tests/integration/test_anonymous_identity.py::test_cookie_minted_with_private_scoped_attributes -q
```

`pytest.ini` puts `src/`, both shared packages and all three services on the Python path. It skips `tests/test_api.py`, a manual script for the legacy monolith.

| Folder | What it covers | Needs test infra |
|---|---|---|
| `unit/` | Orbital mechanics against JPL Horizons reference fixtures, reproducibility of seeded runs, snapshot and ingestion guards, `TTLValue` | No |
| `contract/` | Request validation and the service API contracts | No |
| `integration/` | Real PostgreSQL, Redis and S3: dataset publication, job admission and idempotency, outbox and queue recovery, worker fencing, anonymous cookie identity and limits, service APIs and caching headers | Yes |
| `fixtures/` | Earth and Mars Horizons reference data, with provenance in `horizons_provenance.json` | — |

Rules:
- Never regenerate expected numbers from the code under test. Use the Horizons fixtures, and label any synthetic fixture as synthetic.
- Integration tests create their own Postgres schema and S3 bucket per test and clean up afterwards. They never touch the `tars-local` stack.

Frontend tests are separate: `cd frontend && bun test`.
