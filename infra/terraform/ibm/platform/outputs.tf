output "cluster_id" {
  value = ibm_container_vpc_cluster.this.id
}

output "cluster_name" {
  value = ibm_container_vpc_cluster.this.name
}

output "ingress_hostname" {
  description = "Cluster-provided Ingress subdomain; usable as the public host before a custom domain exists."
  value       = ibm_container_vpc_cluster.this.ingress_hostname
}

output "ingress_secret" {
  description = "TLS secret the cluster created for its Ingress subdomain."
  value       = ibm_container_vpc_cluster.this.ingress_secret
  sensitive   = true
}

output "cos_endpoint" {
  value = local.cos_endpoint
}

output "buckets" {
  value = { for k, b in ibm_cos_bucket.this : k => b.bucket_name }
}

# Connection details for the cluster root (sensitive: kept in state, never printed).
output "runtime" {
  sensitive = true
  value = {
    postgres = jsondecode(ibm_resource_key.postgres.credentials_json).connection.postgres
    redis    = { for k, key in ibm_resource_key.redis : k => jsondecode(key.credentials_json).connection.rediss }
    cos_hmac = jsondecode(ibm_resource_key.cos_hmac.credentials_json).cos_hmac_keys
  }
}
