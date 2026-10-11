data "ibm_resource_group" "this" {
  name = var.resource_group_name
}

locals {
  rg           = data.ibm_resource_group.this.id
  zone_names   = [for z in var.zones : "${var.region}-${z}"]
  default_kube = var.platform == "openshift" ? "4.17_openshift" : "1.31"
  kube_version = var.kube_version != "" ? var.kube_version : local.default_kube
  redis_queue  = "{\"maxmemory-policy\":\"noeviction\"}"  # the job queue must never evict
  redis_cache  = "{\"maxmemory-policy\":\"allkeys-lfu\"}" # disposable cache
  cos_endpoint = "https://s3.direct.${var.region}.cloud-object-storage.appdomain.cloud"
}

# ── Network: one VPC, a subnet and a public gateway per zone (egress to JPL Horizons and image registries) ──

resource "ibm_is_vpc" "this" {
  name           = "${var.prefix}-vpc"
  resource_group = local.rg
  tags           = var.tags
}

resource "ibm_is_public_gateway" "zone" {
  for_each       = toset(local.zone_names)
  name           = "${var.prefix}-pgw-${each.key}"
  vpc            = ibm_is_vpc.this.id
  zone           = each.key
  resource_group = local.rg
  tags           = var.tags
}

resource "ibm_is_subnet" "zone" {
  for_each                 = toset(local.zone_names)
  name                     = "${var.prefix}-subnet-${each.key}"
  vpc                      = ibm_is_vpc.this.id
  zone                     = each.key
  total_ipv4_address_count = 256
  public_gateway           = ibm_is_public_gateway.zone[each.key].id
  resource_group           = local.rg
  tags                     = var.tags
}

# ── Encryption: one Key Protect root key for the cluster secrets, databases and buckets ──

resource "ibm_resource_instance" "kms" {
  name              = "${var.prefix}-kms"
  service           = "kms"
  plan              = "tiered-pricing"
  location          = var.region
  resource_group_id = local.rg
  tags              = var.tags
}

resource "ibm_kms_key" "root" {
  instance_id  = ibm_resource_instance.kms.guid
  key_name     = "${var.prefix}-root"
  standard_key = false
  force_delete = false
}

resource "ibm_iam_authorization_policy" "cos_kms" {
  source_service_name         = "cloud-object-storage"
  source_resource_instance_id = ibm_resource_instance.cos.guid
  target_service_name         = "kms"
  target_resource_instance_id = ibm_resource_instance.kms.guid
  roles                       = ["Reader"]
}

resource "ibm_iam_authorization_policy" "databases_kms" {
  for_each                    = toset(["databases-for-postgresql", "databases-for-redis"])
  source_service_name         = each.key
  target_service_name         = "kms"
  target_resource_instance_id = ibm_resource_instance.kms.guid
  roles                       = ["Reader"]
}

resource "ibm_iam_authorization_policy" "cluster_kms" {
  source_service_name         = "containers-kubernetes"
  target_service_name         = "kms"
  target_resource_instance_id = ibm_resource_instance.kms.guid
  roles                       = ["Reader"]
}

# ── Object storage: datasets and results (S3-compatible, versioned, KMS-encrypted) ──

resource "ibm_resource_instance" "cos" {
  name              = "${var.prefix}-cos"
  service           = "cloud-object-storage"
  plan              = "standard"
  location          = "global"
  resource_group_id = local.rg
  tags              = var.tags
}

resource "ibm_cos_bucket" "this" {
  for_each             = toset(["datasets", "results"])
  bucket_name          = "${var.prefix}-${each.key}"
  resource_instance_id = ibm_resource_instance.cos.id
  region_location      = var.region
  storage_class        = "standard"
  kms_key_crn          = ibm_kms_key.root.crn
  object_versioning {
    enable = true
  }
  depends_on = [ibm_iam_authorization_policy.cos_kms]
}

# HMAC credentials let the services use COS through the S3 API (boto3), scoped to Writer.
resource "ibm_resource_key" "cos_hmac" {
  name                 = "${var.prefix}-cos-hmac"
  resource_instance_id = ibm_resource_instance.cos.id
  role                 = "Writer"
  parameters           = { HMAC = true }
}

# ── Managed databases: Postgres (jobs, idempotency, outbox) and two Redis instances (queue, cache) ──
# Private service endpoints only: the cluster reaches them inside IBM Cloud; nothing is internet-facing.

resource "ibm_database" "postgres" {
  name              = "${var.prefix}-postgres"
  service           = "databases-for-postgresql"
  plan              = "standard"
  version           = var.postgres_version
  location          = var.region
  resource_group_id = local.rg
  service_endpoints = "private"
  key_protect_key   = ibm_kms_key.root.crn
  tags              = var.tags
  group {
    group_id = "member"
    memory { allocation_mb = var.postgres_memory_mb }
    disk { allocation_mb = var.postgres_disk_mb }
    host_flavor { id = "multitenant" }
  }
  depends_on = [ibm_iam_authorization_policy.databases_kms]
}

resource "ibm_database" "redis" {
  for_each          = { queue = local.redis_queue, cache = local.redis_cache }
  name              = "${var.prefix}-redis-${each.key}"
  service           = "databases-for-redis"
  plan              = "standard"
  version           = var.redis_version
  location          = var.region
  resource_group_id = local.rg
  service_endpoints = "private"
  key_protect_key   = ibm_kms_key.root.crn
  configuration     = each.value
  tags              = var.tags
  group {
    group_id = "member"
    memory { allocation_mb = var.redis_memory_mb }
    host_flavor { id = "multitenant" }
  }
  depends_on = [ibm_iam_authorization_policy.databases_kms]
}

resource "ibm_resource_key" "postgres" {
  name                 = "${var.prefix}-postgres-app"
  resource_instance_id = ibm_database.postgres.id
  role                 = "Editor"
}

resource "ibm_resource_key" "redis" {
  for_each             = ibm_database.redis
  name                 = "${var.prefix}-redis-${each.key}-app"
  resource_instance_id = each.value.id
  role                 = "Editor"
}

# ── Cluster: multizone, secrets encrypted with the Key Protect root key ──

resource "ibm_container_vpc_cluster" "this" {
  name              = "${var.prefix}-cluster"
  vpc_id            = ibm_is_vpc.this.id
  kube_version      = local.kube_version
  flavor            = var.worker_flavor
  worker_count      = var.workers_per_zone
  resource_group_id = local.rg
  cos_instance_crn  = var.platform == "openshift" ? ibm_resource_instance.cos.crn : null
  entitlement       = var.platform == "openshift" && var.openshift_entitlement != "" ? var.openshift_entitlement : null
  wait_till         = "IngressReady"
  tags              = var.tags

  dynamic "zones" {
    for_each = ibm_is_subnet.zone
    content {
      name      = zones.value.zone
      subnet_id = zones.value.id
    }
  }

  kms_config {
    instance_id      = ibm_resource_instance.kms.guid
    crk_id           = ibm_kms_key.root.key_id
    private_endpoint = true
  }

  depends_on = [ibm_iam_authorization_policy.cluster_kms]
}
