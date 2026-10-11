variable "region" {
  type    = string
  default = "jp-tok"
}

variable "namespace" {
  description = "Namespace the Helm release goes into."
  type        = string
  default     = "tars"
}

variable "platform_state" {
  description = "Where the platform root keeps its state (same COS bucket, platform key)."
  type = object({
    bucket   = string
    key      = string
    region   = string
    endpoint = string
  })
}
