# Portability: OpenShift to AWS (or any Kubernetes)

TARS is built so the **application layer never changes** between platforms. Only the platform layer, meaning where Postgres, Redis and object storage come from and how CI logs in, is platform-specific.

| Layer | OpenShift (today) | AWS (EKS) | Changes? |
|---|---|---|---|
| Container images | GHCR, by digest | GHCR (or mirror to ECR) | No |
| App chart `deploy/helm/tars` | `values-openshift.yaml` | `values-eks.yaml` (ALB ingress class, annotations) | One values file |
| Object storage | NooBaa S3 (ObjectBucketClaim) | S3 | No code change: the app uses the S3 API through boto3. EKS Pod Identity replaces static keys. |
| Postgres | CloudNativePG (in cluster) or IBM Databases | RDS for PostgreSQL (Multi-AZ) | Connection string and CA only (`sslmode=verify-full`, RDS CA bundle) |
| Redis queue and cache | In-cluster StatefulSets or IBM Databases | ElastiCache ×2 (queue `noeviction`, cache `allkeys-lfu`) | `rediss://` URL and CA; already supported (`QUEUE_REDIS_CA_CERT`, `CACHE_REDIS_CA_CERT`) |
| Ingress and TLS | Router + `*.apps` wildcard certificate | AWS Load Balancer Controller + ACM certificate; optionally CloudFront and WAF | Values file |
| Client IP | `TRUSTED_PROXY_HOPS=1` | `1` for ALB only; `2` with CloudFront in front | Values |
| Infrastructure as code | `deploy/openshift/bootstrap.sh` or `infra/terraform/ibm` | New `infra/terraform/aws`: VPC, EKS, RDS, ElastiCache ×2, S3, KMS, IAM | New Terraform root |
| CI login | ServiceAccount token (`DEPLOY_AUTH=token`) | GitHub OIDC → IAM role → `aws eks update-kubeconfig`; no stored keys | One more auth mode in `deploy.yml` |

## Migration runbook (zero data loss, short write freeze)

1. **Build the AWS platform** with Terraform, and deploy the same image digests to EKS with `values-eks.yaml`. Point it at the new RDS, ElastiCache and S3. Run smoke checks on an internal hostname.
2. **Copy the object storage:** `rclone sync noobaa:tars-… s3:tars-…`. Datasets are immutable and content-addressed, so re-running the sync is safe.
3. **Postgres:**
   - **Short downtime (simplest):** put the app into maintenance (scale the jobs API to 0), `pg_dump` from CloudNativePG, `pg_restore` into RDS.
   - **Near-zero downtime:** logical replication, a CloudNativePG publication to an RDS subscription, then cut over.
4. **Redis: nothing to migrate.** The cache is disposable. Queued jobs live in Postgres as outbox rows, so the outbox publisher on AWS re-enqueues anything unfinished.
5. **Cut over DNS** to the AWS load balancer, with a low TTL set beforehand. Keep OpenShift running read-only for the rollback window.
6. **Roll back** by pointing DNS back. Writes made during the window exist only on AWS, so keep the freeze short, or replicate back.

## What keeps it portable (don't break these)

- The application talks only to standard protocols: the S3 API, PostgreSQL wire protocol, Redis and HTTP. No cloud SDK is used beyond S3.
- All platform differences live in **values files, secrets and Terraform**, never in the images.
- The chart uses plain Kubernetes objects (Deployment, Service, Ingress, HPA, PDB, NetworkPolicy, Job, CronJob). OpenShift-only behaviour is limited to annotations and the `platform: openshift` switch.
- Pods run as non-root, with a read-only root filesystem and no fixed UID on OpenShift. That's compatible with EKS Pod Security `restricted` as well as the OpenShift SCCs.
