CREATE TABLE IF NOT EXISTS schema_migrations(version integer PRIMARY KEY);
CREATE TABLE IF NOT EXISTS jobs (
 id uuid PRIMARY KEY, owner text NOT NULL, kind text NOT NULL,
 idempotency_key text NOT NULL, fingerprint text NOT NULL,
 payload jsonb NOT NULL, dataset_id text NOT NULL, seed bigint NOT NULL,
 schema_version text NOT NULL DEFAULT '1', solver_version text NOT NULL DEFAULT '1.0.0',
 solver_digest text NOT NULL,
 status text NOT NULL DEFAULT 'queued' CHECK(status IN ('queued','running','succeeded','failed')),
 attempt integer NOT NULL DEFAULT 0, fencing_token bigint NOT NULL DEFAULT 0,
 worker_id text, lease_until timestamptz, sequence bigint NOT NULL DEFAULT 0,
 progress jsonb NOT NULL DEFAULT '{}', result_ref jsonb, error text,
 created_at timestamptz NOT NULL DEFAULT now(), updated_at timestamptz NOT NULL DEFAULT now(),
 ended_at timestamptz,
 UNIQUE(owner, kind, schema_version, idempotency_key)
);
CREATE INDEX IF NOT EXISTS jobs_recovery ON jobs(status,lease_until,created_at);
CREATE TABLE IF NOT EXISTS outbox (
 job_id uuid PRIMARY KEY REFERENCES jobs(id) ON DELETE CASCADE,
 sent_at timestamptz, lease_until timestamptz, claim_token uuid
);
CREATE TABLE IF NOT EXISTS attempts (
 job_id uuid NOT NULL REFERENCES jobs(id) ON DELETE CASCADE,
 fencing_token bigint NOT NULL, worker_id text NOT NULL,
 started_at timestamptz NOT NULL DEFAULT now(), ended_at timestamptz,
 status text NOT NULL DEFAULT 'running', error text,
 PRIMARY KEY(job_id,fencing_token)
);
INSERT INTO schema_migrations(version) VALUES(1) ON CONFLICT DO NOTHING;
