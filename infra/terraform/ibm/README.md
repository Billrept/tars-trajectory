# Terraform for IBM Cloud

Two roots, applied in order. Each has its own state in the same Cloud Object Storage bucket.

| Root | Creates | Needs |
|---|---|---|
| [`platform/`](platform) | Resources listed below | An IBM Cloud API key (`IC_API_KEY`) |
| [`cluster/`](cluster) | Namespace `tars` (Pod Security `restricted`), secret `tars-runtime`, secret `tars-ca-certs`, and a generated `SERVICE_TOKEN` | Platform state, and cluster admin through `ibm_container_cluster_config` |

The platform root creates:
- **Network:** a VPC with one subnet and one public gateway per zone (3 zones). The gateways provide egress to JPL Horizons and image registries.
- **Cluster:** multizone, either OpenShift or IKS, with Kubernetes secrets encrypted by Key Protect.
- **Encryption:** Key Protect with one root key, plus the IAM authorization policies that let each service use it.
- **Databases for PostgreSQL** 16. Three members by default, private endpoint only, KMS-encrypted.
- **Databases for Redis** 7.2, twice: the queue (`noeviction`) and the cache (`allkeys-lfu`). Private endpoints, KMS-encrypted.
- **Cloud Object Storage:** an instance with `datasets` and `results` buckets, versioned and KMS-encrypted, plus HMAC credentials scoped to Writer.

The split exists because the Kubernetes provider needs a cluster that already exists. Keeping the namespace and secrets in a second root avoids the provider-ordering problems of a single apply.

## Apply

```bash
export IC_API_KEY=...                                          # never commit; in CI use a Service ID key
export AWS_ACCESS_KEY_ID=... AWS_SECRET_ACCESS_KEY=...         # HMAC keys for the COS state bucket

cd infra/terraform/ibm/platform
cp backend.hcl.example backend.hcl && cp terraform.tfvars.example terraform.tfvars   # both gitignored; edit them
terraform init -backend-config=backend.hcl
terraform plan -out tfplan        # review before applying
terraform apply tfplan

cd ../cluster
cp terraform.tfvars.example terraform.tfvars                   # points at the platform state
terraform init -backend-config=backend.hcl                     # same bucket, key e.g. prod/cluster.tfstate
terraform plan -out tfplan && terraform apply tfplan
terraform output helm_values                                   # copy these into the GitHub environment variables
```

Create the state bucket once, by hand, with versioning on. Run applies from one place at a time, because state locking on COS isn't guaranteed. The CI `concurrency` groups serialize deploys.

## Notes and assumptions

- **Region:** defaults to `jp-tok`, the nearest multizone region to Thailand that this has been written against. Others work, for example `jp-osa`, `au-syd` or `us-south`.
- **OpenShift:** set `openshift_entitlement = "cloud_pak"` only if you hold an entitlement; otherwise the OpenShift licence is billed. OpenShift needs at least 2 workers.
- **Credential format:** the connection strings are built from the Databases for PostgreSQL/Redis service-credential format (`connection.postgres` / `connection.rediss`: hosts, authentication, certificate). Check the generated secret once on the first apply, for example `kubectl -n tars get secret tars-runtime -o jsonpath='{.data.DATABASE_URL}' | base64 -d | sed 's/:[^:@]*@/:***@/'`.
- **Validation status:** both roots pass `terraform fmt` and `terraform validate` against provider `IBM-Cloud/ibm` 1.89.0, and CI re-checks this on every pull request. Validation proves the arguments match the provider's schema. **It does not prove the plan applies**: quotas, entitlements and region availability only show up on a real `terraform plan`.
- **Costs:** a multizone cluster, three-member Postgres and two Redis instances are a real monthly bill. Size `worker_flavor`, `workers_per_zone` and the database memory with the IBM Cloud cost estimator before applying.
