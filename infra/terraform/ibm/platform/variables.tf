variable "region" {
  description = "IBM Cloud multizone region, e.g. jp-tok, jp-osa, au-syd, us-south."
  type        = string
  default     = "jp-tok"
}

variable "prefix" {
  description = "Name prefix for every resource, e.g. tars-prod or tars-staging."
  type        = string
}

variable "resource_group_name" {
  description = "Existing resource group to create everything in."
  type        = string
  default     = "Default"
}

variable "platform" {
  description = "openshift (Red Hat OpenShift on IBM Cloud) or iks (IBM Cloud Kubernetes Service)."
  type        = string
  default     = "openshift"
  validation {
    condition     = contains(["openshift", "iks"], var.platform)
    error_message = "platform must be openshift or iks."
  }
}

variable "kube_version" {
  description = "Cluster version. OpenShift versions end in _openshift (e.g. 4.17_openshift); IKS e.g. 1.31. Empty = provider default."
  type        = string
  default     = ""
}

variable "openshift_entitlement" {
  description = "Set to cloud_pak if you have an OpenShift entitlement from a Cloud Pak; empty = pay for the license."
  type        = string
  default     = ""
}

variable "zones" {
  description = "Zone suffixes used inside the region (three for a multizone cluster)."
  type        = list(number)
  default     = [1, 2, 3]
}

variable "worker_flavor" {
  description = "VPC worker node flavor."
  type        = string
  default     = "bx2.4x16"
}

variable "workers_per_zone" {
  description = "Worker nodes per zone. OpenShift needs at least 2 workers in total."
  type        = number
  default     = 1
}

variable "postgres_version" {
  type    = string
  default = "16"
}

variable "redis_version" {
  type    = string
  default = "7.2"
}

variable "postgres_memory_mb" {
  description = "Memory per Postgres member (three members by default)."
  type        = number
  default     = 4096
}

variable "postgres_disk_mb" {
  description = "Disk per Postgres member."
  type        = number
  default     = 10240
}

variable "redis_memory_mb" {
  description = "Memory per Redis member."
  type        = number
  default     = 1024
}

variable "tags" {
  type    = list(string)
  default = ["app:tars"]
}
