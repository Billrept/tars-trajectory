data "terraform_remote_state" "platform" {
  backend = "s3"
  config = {
    bucket                      = var.platform_state.bucket
    key                         = var.platform_state.key
    region                      = var.platform_state.region
    endpoints                   = { s3 = var.platform_state.endpoint }
    skip_region_validation      = true
    skip_credentials_validation = true
    skip_requesting_account_id  = true
    skip_metadata_api_check     = true
    skip_s3_checksum            = true
    use_path_style              = true
  }
}

locals {
  platform = data.terraform_remote_state.platform.outputs
  runtime  = local.platform.runtime
  pg       = local.runtime.postgres
  ca_dir   = "/etc/tars/certs"
  # Managed services use private CAs; the services verify them from the mounted secret.
  database_url = "postgresql://${local.pg.authentication.username}:${local.pg.authentication.password}@${local.pg.hosts[0].hostname}:${local.pg.hosts[0].port}/${local.pg.database}?sslmode=verify-full&sslrootcert=${local.ca_dir}/postgres-ca.crt"
  redis_url = { for k, r in local.runtime.redis :
    k => "rediss://${r.authentication.username}:${r.authentication.password}@${r.hosts[0].hostname}:${r.hosts[0].port}/0"
  }
}

resource "kubernetes_namespace_v1" "tars" {
  metadata {
    name = var.namespace
    labels = {
      "app.kubernetes.io/part-of"          = "tars"
      "pod-security.kubernetes.io/enforce" = "restricted" # matches the chart's hardened pods
    }
  }
}

resource "random_password" "service_token" {
  length  = 48
  special = false
}

# Names match deploy/helm/tars/values.yaml (secrets.runtime, secrets.caCerts).
resource "kubernetes_secret_v1" "runtime" {
  metadata {
    name      = "tars-runtime"
    namespace = kubernetes_namespace_v1.tars.metadata[0].name
  }
  data = {
    DATABASE_URL          = local.database_url
    QUEUE_REDIS_URL       = local.redis_url["queue"]
    CACHE_REDIS_URL       = local.redis_url["cache"]
    AWS_ACCESS_KEY_ID     = local.runtime.cos_hmac.access_key_id
    AWS_SECRET_ACCESS_KEY = local.runtime.cos_hmac.secret_access_key
    SERVICE_TOKEN         = random_password.service_token.result
  }
}

resource "kubernetes_secret_v1" "ca_certs" {
  metadata {
    name      = "tars-ca-certs"
    namespace = kubernetes_namespace_v1.tars.metadata[0].name
  }
  data = {
    "postgres-ca.crt"    = base64decode(local.pg.certificate.certificate_base64)
    "queue-redis-ca.crt" = base64decode(local.runtime.redis["queue"].certificate.certificate_base64)
    "cache-redis-ca.crt" = base64decode(local.runtime.redis["cache"].certificate.certificate_base64)
  }
}
