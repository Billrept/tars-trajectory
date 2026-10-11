# Deploying TARS to IBM Cloud

Production runs on **Red Hat OpenShift on IBM Cloud** or **IBM Cloud Kubernetes Service (IKS)**: a multizone cluster, with managed data services kept outside the cluster.

```
                      ┌─────────────────────── cluster (3 zones) ───────────────────────┐
browser ──HTTPS──► Ingress ─┬─ /                   → frontend   (2–4 pods)                 │
                            ├─ /api/v1/ephemeris   → ephemeris  (2–6, WebSocket)          │
                            ├─ /api/v1/trajectory  → trajectory (2–8, CPU)                │
                            └─ /api/v1/jobs        → jobs API   (2–4)                     │
                               outbox (2) · worker (2–6, CPU) · loader CronJob            │
                      └──────────────────────────────┬───────────────────────────────────┘
                              private endpoints only │
          Databases for PostgreSQL · Databases for Redis ×2 (queue noeviction, cache LFU)
          Cloud Object Storage (datasets, results; versioned) · Key Protect root key
```

| Layer | Where | Owned by |
|---|---|---|
| VPC, cluster, Postgres, Redis ×2, COS buckets, Key Protect | [`infra/terraform/ibm/platform`](../infra/terraform/ibm/README.md) | Terraform |
| Namespace, runtime secret, CA certificates | [`infra/terraform/ibm/cluster`](../infra/terraform/ibm/README.md) | Terraform |
| Deployments, Services, Ingress, autoscalers, disruption budgets, NetworkPolicies, hook Jobs, CronJob | [`deploy/helm/tars`](helm/tars) | Helm, run by CI |

Credentials never pass through Helm values. The chart only references the `tars-runtime` and `tars-ca-certs` secrets by name.

## What the chart does

- **Two-plus replicas everywhere in production.** Pods spread across zones, with a PodDisruptionBudget of `minAvailable: 1`, rolling updates with `maxUnavailable: 0`, and CPU autoscalers that wait 5 minutes before scaling down.
- **Hardened pods.** Non-root, read-only root filesystem, all capabilities dropped, `seccomp: RuntimeDefault`, no service-account token and no service-link env vars. This passes the **`restricted` Pod Security Standard**, the label the cluster Terraform sets on the namespace. On OpenShift (`values-openshift.yaml`), fixed UIDs are left out so the `restricted-v2` SCC can assign one.
- **Install order.**
  1. A `pre-install`/`pre-upgrade` hook applies the database schema.
  2. A `pre-install` hook publishes the first ephemeris dataset, so ephemeris becomes ready with data.
  3. A monthly CronJob refreshes the dataset. Publication is all-or-nothing.
- **Routing.** Only `/`, `/api/v1/ephemeris`, `/api/v1/trajectory` and `/api/v1/jobs` are routed. The internal dataset API (`/internal/*`) and the legacy unversioned paths are not reachable from outside.
- **NetworkPolicies.** Inbound traffic is denied by default. Only the ingress controller can reach the public services, and only trajectory, jobs, outbox and worker can reach ephemeris.
- **One frontend image for every environment.** It's built `same-origin`, so it calls relative `/api/v1/...` paths on whatever host serves it.

## First deployment

1. **Provision the platform** (cloud resources): see [`infra/terraform/ibm/README.md`](../infra/terraform/ibm/README.md).
2. **Bootstrap the cluster:** apply `infra/terraform/ibm/cluster`. This creates the namespace and both secrets. Note its `helm_values` output.
3. **Create GitHub environments** `staging` and `production`. Give `production` required reviewers and restrict it to `v*` tags.
4. **Environment secret:** `IBM_CLOUD_API_KEY`, a Service ID API key with Writer on the target namespace only.
5. **Environment variables:**

   | Variable | Example |
   |---|---|
   | `IBM_REGION`, `IBM_RESOURCE_GROUP`, `IBM_CLUSTER` | `jp-tok`, `Default`, `tars-prod-cluster` |
   | `K8S_NAMESPACE` | `tars` |
   | `TARS_PLATFORM` | `openshift` or `kubernetes` |
   | `TARS_HOST` | your domain, or the cluster's Ingress subdomain (`terraform output ingress_hostname`) |
   | `TARS_INGRESS_CLASS` | IKS: `public-iks-k8s-nginx`; OpenShift: leave empty |
   | `TARS_INGRESS_TLS_SECRET` | IKS: the cluster's Ingress secret (`terraform output ingress_secret`) or your certificate secret |
   | `TARS_S3_ENDPOINT`, `TARS_DATASET_BUCKET`, `TARS_RESULT_BUCKET` | from `helm_values` |
   | `TARS_TRUSTED_PROXY_HOPS` | `1` (ingress only); `2` if IBM CIS or another proxy sits in front |

6. **Repository variable** `DEPLOY_ENABLED=true`, to switch the deploy stages on.
7. **Images:** make the GHCR packages public, or add a GHCR pull secret and set `image.pullSecrets`.
8. **Release:**
   - A push to `main` deploys **staging**.
   - Tag `v0.1.0` to deploy staging, then **production** after approval.

## How a deploy works (`.github/workflows/deploy.yml`)

1. Logs in with the Service ID key and fetches cluster credentials.
2. Resolves the **digest** of each image built for this commit, so the cluster runs exactly the bytes CI tested.
3. Runs `helm upgrade --install --atomic --wait`. If any pod fails to become ready, Helm **rolls back automatically**.
4. Runs smoke checks through the public host:
   - the page loads
   - an active dataset exists
   - the jobs endpoint sets a `Secure` `tars_uid` cookie
   - `/internal/*` returns 404

## Manual operations

```bash
helm -n tars history tars                 # releases
helm -n tars rollback tars <revision>     # roll back to a known-good release
kubectl -n tars create job --from=cronjob/tars-loader tars-loader-now   # refresh the dataset now
kubectl -n tars get hpa,pdb,pods -o wide  # scaling and spread
```

## Verified so far

Installed with `values-production.yaml` on a local `kind` cluster:
- the namespace enforced `restricted` Pod Security
- in-cluster Postgres, Redis and S3 stand-ins
- an NGINX ingress controller in front

Results:
- **Install:** all hooks ran, and 12 of 12 pods became ready.
- **Routing:** the public routes answered, and `/internal/*` and the legacy paths returned 404.
- **Browser flow** through the ingress:
  - the planet WebSocket streamed
  - an Earth → Mars route search ran the full job pipeline
  - the search appeared in "Your missions"
  - the cookie was `HttpOnly; Path=/api/v1/jobs; SameSite=Lax`

**Not yet verified on IBM Cloud itself:**
- managed-service TLS
- COS HMAC access
- IBM ingress classes
- OpenShift SCC admission
- real autoscaling, which needs metrics-server
