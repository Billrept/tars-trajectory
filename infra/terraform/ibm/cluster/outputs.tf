output "namespace" {
  value = kubernetes_namespace_v1.tars.metadata[0].name
}

output "helm_values" {
  description = "Non-secret values to pass to the Helm chart for this environment."
  value = {
    "config.s3EndpointUrl" = local.platform.cos_endpoint
    "config.region"        = var.region
    "config.datasetBucket" = local.platform.buckets["datasets"]
    "config.resultBucket"  = local.platform.buckets["results"]
    "ingress.host"         = local.platform.ingress_hostname
  }
}
