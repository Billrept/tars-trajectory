export const API = process.env.PUBLIC_API_URL;
export const EPHEMERIS_API = process.env.PUBLIC_EPHEMERIS_URL;
export const JOB_API = process.env.PUBLIC_JOBS_URL;
const pendingKeys = new Map();

// The jobs API identifies the visitor via an HttpOnly cookie scoped to
// /api/v1/jobs. JS never reads it; every jobs fetch must send it.
async function body(response) {
  const data = await response.json().catch(() => null);
  if (!response.ok) {
    const detail = data && typeof data.detail === 'string' ? data.detail : '';
    if (response.status === 429) throw new Error(detail || 'Too many requests right now — please wait a moment and try again.');
    if (response.status === 503) throw new Error(detail || 'The service is busy right now — try again shortly.');
    throw new Error(detail || `Request failed (${response.status})`);
  }
  return data;
}
export async function submitJob(kind, payload) {
  const bytes = new TextEncoder().encode(JSON.stringify({ api: JOB_API, kind, payload }));
  const digest = Array.from(new Uint8Array(await crypto.subtle.digest('SHA-256', bytes)), x => x.toString(16).padStart(2, '0')).join('');
  const storageKey = `tars.pending.${digest}`;
  let key = pendingKeys.get(storageKey);
  try { key ||= sessionStorage.getItem(storageKey); } catch (_) {}
  key ||= crypto.randomUUID();
  pendingKeys.set(storageKey, key);
  try { sessionStorage.setItem(storageKey, key); } catch (_) {}
  let error;
  for (let attempt = 0; attempt < 2; attempt++) {
    try {
      const response = await fetch(`${JOB_API}/api/v1/jobs`, {
        method: 'POST', credentials: 'include',
        headers: { 'Content-Type': 'application/json', 'Idempotency-Key': key },
        body: JSON.stringify({ kind, payload }), signal: AbortSignal.timeout(15000),
      });
      if ([503, 504].includes(response.status)) throw new Error('Job service temporarily unavailable');
      const admitted = await body(response);
      if (!admitted.job_id) throw new Error('Invalid job admission response');
      pendingKeys.delete(storageKey);
      try { sessionStorage.removeItem(storageKey); } catch (_) {}
      return admitted;
    } catch (e) {
      error = e;
      if (attempt === 0) await new Promise(resolve => setTimeout(resolve, 500));
    }
  }
  throw error;
}
export async function waitForJob(jobId, onProgress) {
  const deadline = Date.now() + 35 * 60 * 1000;
  while (Date.now() < deadline) {
    const snapshot = await body(await fetch(`${JOB_API}/api/v1/jobs/${jobId}`, { credentials: 'include', signal: AbortSignal.timeout(15000) }));
    if (onProgress) onProgress({ ...snapshot.progress, status: snapshot.status, job_id: jobId });
    if (snapshot.status === 'failed') throw new Error(snapshot.error || 'Calculation failed');
    if (snapshot.status === 'succeeded') return getJobResult(jobId);
    await new Promise(resolve => setTimeout(resolve, 1000));
  }
  throw new Error('Job is still processing; its ID can be checked again later');
}
export async function getJobResult(jobId) {
  return body(await fetch(`${JOB_API}/api/v1/jobs/${jobId}/result`, { credentials: 'include', signal: AbortSignal.timeout(15000) }));
}
export async function calculateJob(kind, payload, onProgress) {
  const admitted = await submitJob(kind, payload);
  if (onProgress) onProgress({ status: 'starting', job_id: admitted.job_id });
  return waitForJob(admitted.job_id, onProgress);
}

// Anonymous session history. Also called on boot: the response mints the
// identity cookie before any submission, so a lost first response can't
// strand the job under a different owner.
export async function listJobs(limit = 20) {
  const response = await fetch(`${JOB_API}/api/v1/jobs?limit=${limit}`, { credentials: 'include', signal: AbortSignal.timeout(15000) });
  const data = await body(response);
  return Array.isArray(data.jobs) ? data.jobs : [];
}

// "Start fresh": expires the cookie server-side. Old rows age out on their own.
export async function resetSession() {
  const response = await fetch(`${JOB_API}/api/v1/jobs/session`, { method: 'DELETE', credentials: 'include', signal: AbortSignal.timeout(15000) });
  await body(response);
}
