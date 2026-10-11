terraform {
  required_version = ">= 1.11, < 2.0"
  required_providers {
    ibm = {
      source  = "IBM-Cloud/ibm"
      version = "~> 1.89"
    }
    kubernetes = {
      source  = "hashicorp/kubernetes"
      version = "~> 3.3"
    }
    random = {
      source  = "hashicorp/random"
      version = "~> 3.9"
    }
  }
  backend "s3" {} # same COS state bucket as platform, different key (see platform/backend.hcl.example)
}

provider "ibm" {
  region = var.region
}

data "ibm_container_cluster_config" "this" {
  cluster_name_id = local.platform.cluster_id
  admin           = true
}

provider "kubernetes" {
  host                   = data.ibm_container_cluster_config.this.host
  client_certificate     = data.ibm_container_cluster_config.this.admin_certificate
  client_key             = data.ibm_container_cluster_config.this.admin_key
  cluster_ca_certificate = data.ibm_container_cluster_config.this.ca_certificate
}
