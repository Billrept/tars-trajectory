terraform {
  required_version = ">= 1.11, < 2.0"
  required_providers {
    ibm = {
      source  = "IBM-Cloud/ibm"
      version = "~> 1.89"
    }
  }
  # State lives in IBM Cloud Object Storage through the S3-compatible backend.
  # terraform init -backend-config=backend.hcl   (see backend.hcl.example)
  backend "s3" {}
}

provider "ibm" {
  region = var.region # credentials: IC_API_KEY environment variable (a Service ID key in CI)
}
